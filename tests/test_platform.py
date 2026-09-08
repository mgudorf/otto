"""Revision, registry, and the read-only guarantee for scheduled agent work."""

import ast
import sys
from pathlib import Path

from app import revision
from app.claude import READ_BUILTINS
from app.config import ROOT
from app.modules import Registry
from app.runner import JobContext

FORBIDDEN_IN_TASKS = {"session_turn", "oneshot", "write_tools"}


def test_revision_changes_with_content(tmp_path: Path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "x.py").write_text("a = 1\n")
    (tmp_path / "config.toml").write_text("[x]\n")
    r1 = revision.compute(tmp_path)
    (tmp_path / "app" / "x.py").write_text("a = 2\n")
    r2 = revision.compute(tmp_path)
    (tmp_path / "app" / "__pycache__").mkdir()
    (tmp_path / "app" / "__pycache__" / "x.py").write_text("ignored")
    r3 = revision.compute(tmp_path)
    assert r1 != r2 and r2 == r3 and len(r1) == 12


def test_registry_loads_real_modules():
    reg = Registry()
    reg.load()
    assert reg.errors == {}
    assert {"home", "memory", "system"} <= set(reg.modules)
    assert reg.get("memory").manifest.agent is not None
    assert "suggest" in reg.get("memory").tasks
    # hooks take the store, never a request: a route handler must not shadow a hook name
    import inspect

    for m in reg.modules.values():
        for hook in (m.numbers, m.today, m.item, m.context):
            if hook is not None:
                assert "request" not in inspect.signature(hook).parameters, f"{m.name}: {hook.__name__} is a route, not a hook"
    assert reg.get("home").numbers is None and reg.get("home").context is not None


def test_registry_skips_broken_module(tmp_path: Path, monkeypatch):
    pkg = tmp_path / "pkgx"
    (pkg / "good").mkdir(parents=True)
    (pkg / "bad").mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "good" / "__init__.py").write_text("from app.modules import Manifest\nMANIFEST = Manifest(name='good', title='G', hue='#fff', icon='', order=1)\n")
    (pkg / "bad" / "__init__.py").write_text("raise RuntimeError('broken on purpose')\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    reg = Registry()
    reg.load("pkgx")
    assert set(reg.modules) == {"good"}
    assert "broken on purpose" in reg.errors["bad"]


def test_tasks_never_reach_interactive_claude():
    for tasks_py in (ROOT / "app" / "modules").glob("*/tasks.py"):
        names = {n.attr for n in ast.walk(ast.parse(tasks_py.read_text("utf-8"))) if isinstance(n, ast.Attribute)}
        names |= {n.id for n in ast.walk(ast.parse(tasks_py.read_text("utf-8"))) if isinstance(n, ast.Name)}
        assert not (names & FORBIDDEN_IN_TASKS), f"{tasks_py} reaches an interactive Claude entry point"
    assert not hasattr(JobContext, "session_turn") and not hasattr(JobContext, "oneshot")


def test_read_builtins_exclude_writers():
    assert not {"Write", "Edit", "Bash", "NotebookEdit", "MultiEdit"} & set(READ_BUILTINS)


def test_docs_tools_confined(store):
    from app.modules.feedback import tools

    class FakeServer:
        def __init__(self):
            self.tools = {}

        def tool(self):
            def deco(fn):
                self.tools[fn.__name__] = fn
                return fn

            return deco

    store.migrate((ROOT / "app" / "modules" / "feedback" / "schema.sql").read_text("utf-8"))
    read, full = FakeServer(), FakeServer()
    tools.register(read, full, store)
    assert set(read.tools) == set(full.tools) == {"docs_list", "docs_read", "feedback_list"}
    paths = {d["path"] for d in read.tools["docs_list"]()}
    assert "docs/ARCHITECTURE.md" in paths and all(p.startswith("docs/") and p.endswith(".md") for p in paths)
    assert read.tools["docs_read"]("docs/ARCHITECTURE.md")["text"].startswith("# Architecture")
    for bad in ("config.toml", "../app/config.py", "docs/design/support.js", "docs/../app/claude.py"):
        assert "error" in read.tools["docs_read"](bad), bad
    assert read.tools["feedback_list"]() == []
