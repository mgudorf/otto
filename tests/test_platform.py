"""Revision, registry, and the read-only guarantee for scheduled agent work."""

import ast
import sys
from pathlib import Path

from app import revision
from app.claude import READ_BUILTINS
from app.config import ROOT
from app.modules import Registry
from app.runner import JobContext
from app.store import add_tags, all_tags, remove_tag, tags_for

FORBIDDEN_IN_TASKS = {"session_turn", "oneshot", "write_tools"}
ACTION_KEYS = {"verb", "label", "primary", "confirm", "href", "removes"}    # everything the inspector reads off an action


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
    assert {"home", "second_brain", "system"} <= set(reg.modules)
    assert reg.get("second_brain").manifest.agent is not None
    assert "suggest" in reg.get("second_brain").tasks
    # hooks take the store, never a request: a route handler must not shadow a hook name
    import inspect

    for m in reg.modules.values():
        for hook in (m.numbers, m.today, m.queue, m.rows, m.item, m.context):
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


def test_registry_picks_up_queue_hook(tmp_path: Path, monkeypatch):
    """A routes.py that defines queue(store) reaches Module.queue; one that does not leaves it None."""
    pkg = tmp_path / "pkgq"
    (pkg / "withq").mkdir(parents=True)
    (pkg / "without").mkdir()
    (pkg / "__init__.py").write_text("")
    manifest = "from app.modules import Manifest\nMANIFEST = Manifest(name='{n}', title='{n}', hue='#fff', icon='', order=1)\n"
    (pkg / "withq" / "__init__.py").write_text(manifest.format(n="withq"))
    (pkg / "withq" / "routes.py").write_text("def queue(store):\n    return [{'id': 1, 'text': 'waiting'}]\n")
    (pkg / "without" / "__init__.py").write_text(manifest.format(n="without"))
    monkeypatch.syspath_prepend(str(tmp_path))
    reg = Registry()
    reg.load("pkgq")
    assert reg.errors == {}
    assert reg.get("withq").queue(None) == [{"id": 1, "text": "waiting"}]
    assert reg.get("without").queue is None


def test_tags_are_one_system(store):
    """A tag written on any module's row reads back through one helper; Second Brain keeps its own table, so its
    tools still see what the page wrote. Spelling is normalised on the way in."""
    store.migrate((ROOT / "app" / "modules" / "second_brain" / "schema.sql").read_text("utf-8"))
    store.execute("INSERT INTO second_brain_items(id, kind, text, created_at, updated_at) VALUES (1, 'note', 'x', '2026-09-18', '2026-09-18')")
    add_tags(store, "second_brain", 1, ["Thesis", " causal "])
    add_tags(store, "email", "18f2a", ["THESIS", "tax"])
    assert store.query("SELECT tag FROM second_brain_tags ORDER BY tag") == [{"tag": "causal"}, {"tag": "thesis"}]
    assert tags_for(store, "second_brain", [1])[1] == ["causal", "thesis"]
    assert tags_for(store, "email", ["18f2a"])["18f2a"] == ["tax", "thesis"]
    assert [t["tag"] for t in all_tags(store)] == ["thesis", "causal", "tax"]
    assert next(t for t in all_tags(store) if t["tag"] == "thesis")["modules"] == ["email", "second_brain"]
    assert remove_tag(store, "email", "18f2a", "Tax") and not remove_tag(store, "email", "18f2a", "tax")
    assert tags_for(store, "email", ["18f2a"])["18f2a"] == ["thesis"]


def _action_literals(tree: ast.AST) -> list[dict]:
    """Every {"verb": ...} dict in a routes.py, as {key: value node}: what item() offers the inspector."""
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        pairs = {k.value: v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        if "verb" in pairs:
            out.append(pairs)
    return out


def test_item_verbs_are_routes_the_module_serves():
    """Home's inspector posts /api/<module>/action/<verb> with {id} and reads nothing else off an action, so a verb
    without an href must be a served action and a misspelled key (removes, not remove) must fail here, not in the browser."""
    for routes_py in sorted((ROOT / "app" / "modules").glob("*/routes.py")):
        name = routes_py.parent.name
        tree = ast.parse(routes_py.read_text("utf-8"))
        served: set[str] = set()
        for node in tree.body:      # the module's action table, whatever it is called
            if isinstance(node, ast.Assign) and {t.id for t in node.targets if isinstance(t, ast.Name)} & {"ACTIONS", "VERBS"}:
                served |= {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
        for action in _action_literals(tree):
            assert set(action) <= ACTION_KEYS, f"{name}: an action carries {sorted(set(action) - ACTION_KEYS)}"
            verb = action["verb"]
            if "href" in action or not isinstance(verb, ast.Constant):
                continue
            assert verb.value in served, f"{name}: item offers {verb.value!r}, which is no action it serves"


def test_tasks_never_reach_interactive_claude():
    for tasks_py in (ROOT / "app" / "modules").glob("*/tasks.py"):
        names = {n.attr for n in ast.walk(ast.parse(tasks_py.read_text("utf-8"))) if isinstance(n, ast.Attribute)}
        names |= {n.id for n in ast.walk(ast.parse(tasks_py.read_text("utf-8"))) if isinstance(n, ast.Name)}
        assert not (names & FORBIDDEN_IN_TASKS), f"{tasks_py} reaches an interactive Claude entry point"
    assert not hasattr(JobContext, "session_turn") and not hasattr(JobContext, "oneshot")


def test_read_builtins_exclude_writers():
    assert not {"Write", "Edit", "Bash", "NotebookEdit", "MultiEdit"} & set(READ_BUILTINS)


def test_docs_tools_confined(store, config):
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
    tools.register(read, full, store, config)
    assert set(read.tools) == set(full.tools) == {"docs_list", "docs_read", "feedback_list"}
    paths = {d["path"] for d in read.tools["docs_list"]()}
    assert "docs/app/CLAUDE.md" in paths and all(p.startswith("docs/") and p.endswith(".md") for p in paths)
    assert read.tools["docs_read"]("docs/app/CLAUDE.md")["text"].startswith("# App")
    for bad in ("config.toml", "../app/config.py", "docs/design/support.js", "docs/../app/claude.py"):
        assert "error" in read.tools["docs_read"](bad), bad
    assert read.tools["feedback_list"]() == []


def test_tables_are_named_after_their_module():
    """Every table a schema creates carries its owner's prefix (app_ for the platform) and every index and trigger its
    table's name, so a name says where a table lives and the Database page groups by module. A table that changes its
    name is a line in app/migrate.py RENAMES, and no schema creates a name listed there."""
    import sqlite3

    from app.migrate import RENAMES

    schemas = [("app", ROOT / "app" / "schema.sql"), *sorted((p.parent.name, p) for p in (ROOT / "app" / "modules").glob("*/schema.sql"))]
    for module, path in schemas:
        conn = sqlite3.connect(":memory:")
        conn.executescript(path.read_text("utf-8"))
        for kind, name, table in conn.execute("SELECT type, name, tbl_name FROM sqlite_master WHERE sql IS NOT NULL").fetchall():
            if kind == "table":
                assert name.startswith(f"{module}_"), f"{path.parent.name}/schema.sql: table {name} lacks the {module}_ prefix"
                assert name not in RENAMES, f"{path.parent.name}/schema.sql creates {name}, an old name in app/migrate.py RENAMES"
            else:
                assert name.startswith(f"{table}_"), f"{path.parent.name}/schema.sql: {kind} {name} is not named after {table}"
        conn.close()


def test_build_makes_icon_and_exe(tmp_path: Path):
    """The window icon derives from the logo and the launcher compiles under it, with only what Windows ships."""
    from app import build

    ico, exe = tmp_path / "otto.ico", tmp_path / "Otto.exe"
    build.icon(ROOT / "otto.png", ico)
    build.exe(ico, exe)
    assert ico.read_bytes()[:6] == bytes([0, 0, 1, 0, 4, 0]) and exe.stat().st_size > 0   # reserved, type icon, four frames
