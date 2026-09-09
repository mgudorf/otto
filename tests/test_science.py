"""Science through the real app: the listing, a notebook's cells, a faked kernel run, and the reaper. No real kernel."""

from __future__ import annotations

import ast
import dataclasses
import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import nbformat
import pytest
from fastapi import HTTPException

from app.config import ROOT
from app.daemon import build
from app.modules.science import notebook, state, tasks
from app.modules.science.kernels import Kernel
from app.store import now
from tests.conftest import run
from tests.test_app import client_for, settle


@pytest.fixture
def sci(config, tmp_path: Path):
    root = tmp_path / "science"
    root.mkdir()
    nb = nbformat.v4.new_notebook()
    nb.cells = [nbformat.v4.new_code_cell("print(1)"), nbformat.v4.new_markdown_cell("# notes")]
    nbformat.write(nb, str(root / "analysis.ipynb"))
    (root / "etl.py").write_text("x = 1\n", "utf-8")
    (tmp_path / "secret.txt").write_text("no", "utf-8")
    return dataclasses.replace(config, science=dataclasses.replace(config.science, root=root))


def test_science_lists_and_reads(sci):
    async def main():
        app = build(sci)
        await app.state.runner.start()
        async with client_for(app) as c:
            left = (await c.get("/api/science/left")).json()
            rows = [r for g in left["groups"] for r in g["rows"]]
            assert {r["text"] for r in rows} == {"analysis.ipynb", "etl.py"} and left["showing"] == "2 files"
            assert all(r["leading"]["dot"] is None for r in rows)
            item = (await c.get("/api/science/item/analysis.ipynb")).json()
            assert item["kind"] == "ipynb" and item["kernel"] is None
            assert [x["type"] for x in item["cells"]] == ["code", "markdown"] and item["cells"][0]["source"] == "print(1)"
            py = (await c.get("/api/science/item/etl.py")).json()
            assert py["kind"] == "py" and py["source"] == "x = 1\n"
            assert (await c.get("/api/science/item/missing.ipynb")).status_code == 404
            assert (await c.get("/api/science/blank")).json() == {"kernels": 0, "files": 2}
            numbers = (await c.get("/api/home/numbers")).json()
            assert any(n["module"] == "science" and n["label"] == "kernels" and n["value"] == 0 for n in numbers)
            home = (await c.get("/api/home/left")).json()
            assert next(g for g in home["groups"] if g["module"] == "science")["count"] == 2
        with pytest.raises(HTTPException):
            notebook.resolve(sci.science.root, "../secret.txt")
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_science_run_streams_and_saves(sci, monkeypatch):
    async def main():
        app = build(sci)
        await app.state.runner.start()
        outs = [
            {"output_type": "stream", "name": "stdout", "text": "1\n"},
            {"output_type": "execute_result", "data": {"text/plain": "2"}, "metadata": {}, "execution_count": 3},
        ]

        async def fake_execute(path, index, source, on_output=None):
            assert source == "print(1)" and index == 0
            for o in outs:
                on_output(o)
            return 3, outs

        monkeypatch.setattr(state.kernels, "execute", fake_execute)
        q = app.state.broadcast.subscribe("science")
        async with client_for(app) as c:
            r = await c.post("/api/science/action/run", json={"id": "analysis.ipynb", "index": 0})
            assert r.status_code == 200 and "job" in r.json(), r.text
            await settle(app)
            events = []
            while not q.empty():
                events.append(q.get_nowait())
            assert [e["event"] for e in events] == ["started", "output", "output", "done"]
            assert events[1]["output"] == {"kind": "stream", "name": "stdout", "text": "1\n"} and events[3]["execution_count"] == 3
            cell = (await c.get("/api/science/item/analysis.ipynb")).json()["cells"][0]
            assert cell["execution_count"] == 3 and [o["kind"] for o in cell["outputs"]] == ["stream", "text"]
            nb = nbformat.read(str(sci.science.root / "analysis.ipynb"), as_version=4)
            assert nb.cells[0].execution_count == 3 and len(nb.cells[0].outputs) == 2
            assert not list(sci.science.root.glob("*.tmp"))
            job = (await c.get("/api/jobs")).json()[0]
            assert job["task"] == "science.run" and job["resource"] == "kernel:analysis.ipynb" and job["status"] == "done"
            assert (await c.post("/api/science/action/run", json={"id": "analysis.ipynb", "index": 1})).status_code == 400
            assert (await c.post("/api/science/action/restart", json={"id": "analysis.ipynb"})).status_code == 409
            assert (await c.get("/api/events?module=science")).json()["events"][0]["verb"] == "ran"
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_science_edits_write_valid_notebooks(sci):
    async def main():
        app = build(sci)
        await app.state.runner.start()
        root = sci.science.root
        async with client_for(app) as c:
            post = lambda verb, body: c.post(f"/api/science/action/{verb}", json=body)
            assert (await post("set_cell", {"id": "analysis.ipynb", "index": 0, "source": "print(2)"})).status_code == 200
            assert (await post("insert_cell", {"id": "analysis.ipynb", "after": 0, "type": "markdown"})).json()["index"] == 1
            assert (await post("insert_cell", {"id": "analysis.ipynb"})).json()["index"] == 3
            cells = (await c.get("/api/science/item/analysis.ipynb")).json()["cells"]
            assert [(x["type"], x["source"]) for x in cells] == [("code", "print(2)"), ("markdown", ""), ("markdown", "# notes"), ("code", "")]
            assert (await post("delete_cell", {"id": "analysis.ipynb", "index": 1})).status_code == 200
            assert (await post("set_cell", {"id": "analysis.ipynb", "index": 9, "source": "x"})).status_code == 400
            assert (await post("set_cell", {"id": "etl.py", "index": 0, "source": "x"})).status_code == 400
            assert (await post("new", {"name": "fresh"})).json() == {"id": "fresh.ipynb"}
            assert (await post("new", {"name": "fresh"})).status_code == 409
            assert (await post("new", {"name": "../fresh"})).status_code == 400
            assert (await post("new", {"name": ""})).status_code == 400
            left = (await c.get("/api/science/left")).json()
            assert {r["text"] for g in left["groups"] for r in g["rows"]} == {"analysis.ipynb", "etl.py", "fresh.ipynb"}
            assert [e["verb"] for e in (await c.get("/api/events?module=science")).json()["events"]] == ["created", "deleted"]
        for name in ("analysis.ipynb", "fresh.ipynb"):
            nb = nbformat.read(str(root / name), as_version=4)
            nbformat.validate(nb)
        assert len(nbformat.read(str(root / "analysis.ipynb"), as_version=4).cells) == 3
        assert nbformat.read(str(root / "fresh.ipynb"), as_version=4).metadata["kernelspec"]["name"] == "python3"
        assert not list(root.glob("*.tmp"))
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_science_read_tools_never_write(sci, monkeypatch):
    async def main():
        app = build(sci)
        read_names = {t.name for t in await app.state.mcp_read.list_tools()}
        full_names = {t.name for t in await app.state.mcp_full.list_tools()}
        agent = app.state.registry.get("science").manifest.agent
        assert {n for n in read_names if n.startswith("science_")} == set(agent.read_tools)
        assert set(agent.write_tools) <= full_names and not set(agent.write_tools) & read_names
        assert set(agent.read_tools) <= full_names

        async def fake_execute(path, index, source, on_output=None):
            assert source == "print(1)"
            return 7, [{"output_type": "stream", "name": "stdout", "text": "y" * (sci.science.tool_output_chars + 50)}]

        monkeypatch.setattr(state.kernels, "execute", fake_execute)
        full = app.state.mcp_full
        run = _data(await full.call_tool("science_run", {"id": "analysis.ipynb", "index": 0}))
        assert run["execution_count"] == 7 and run["outputs"][0]["text"].endswith("[50 more chars]")
        assert _data(await full.call_tool("science_cell", {"id": "analysis.ipynb", "index": 0}))["outputs"][0]["text"] == "y" * (sci.science.tool_output_chars + 50)
        assert _data(await full.call_tool("science_set_cell", {"id": "analysis.ipynb", "index": 1, "source": "# renamed"})) == {"id": "analysis.ipynb", "index": 1}
        nb = _data(await app.state.mcp_read.call_tool("science_notebook", {"id": "analysis.ipynb"}))
        assert nb["cells"][0]["execution_count"] == 7 and nb["cells"][1]["source"] == "# renamed"
        assert "error" in _data(await full.call_tool("science_run", {"id": "etl.py", "index": 0}))
        files = [json.loads(c.text) for c in (await app.state.mcp_read.call_tool("science_files", {})).content]
        assert {f["id"] for f in files} == {"analysis.ipynb", "etl.py"} and all(f["kernel"] is None for f in files)
        assert [e["verb"] for e in app.state.store.query("SELECT verb FROM events WHERE module = 'science' ORDER BY id")] == ["ran", "edited"]
        app.state.store.close()

    run(main())


def _data(result):
    """The payload of an MCPServer.call_tool result: structured when the server built one, else the JSON text block."""
    structured = getattr(result, "structured_content", None)
    return structured if structured is not None else json.loads(result.content[0].text)


def test_science_reap(sci):
    async def main():
        app = build(sci)
        limit = sci.science.idle_minutes

        def kernel(name, minutes, running=None):
            return Kernel(path=Path(name), manager=None, client=None, started_at="", last_activity=now() - timedelta(minutes=minutes), running=running)

        stale = kernel("a.ipynb", limit + 1)
        busy = kernel("b.ipynb", limit * 10, running={"index": 0, "outputs": []})
        fresh = kernel("c.ipynb", 0)
        state.kernels._k = {str(k.path): k for k in (stale, busy, fresh)}
        gone = []

        async def fake_shutdown(path):
            gone.append(path)
            return state.kernels._k.pop(str(path), None) is not None

        state.kernels.shutdown = fake_shutdown
        events = []
        ctx = SimpleNamespace(config=sci, event=lambda *a, **k: events.append(a))
        assert (await tasks.reap(ctx)).startswith("shut down 1")
        assert gone == [Path("a.ipynb")] and events[0][0] == "shut down"
        assert await tasks.reap(ctx) == "no idle kernels"
        app.state.store.close()

    run(main())


def test_science_tasks_never_execute_or_write():
    src = (ROOT / "app" / "modules" / "science" / "tasks.py").read_text("utf-8")
    tree = ast.parse(src)
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not names & {"execute", "write", "start", "restart"}
