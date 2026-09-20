"""Science through the real app: the tree, a notebook's cells, a faked kernel run that lands by cell id, whole-list edits, creation,
a script run as a real subprocess of this interpreter, schedules and the due task, and the reaper. No real kernel."""

from __future__ import annotations

import ast
import dataclasses
import json
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import nbformat
import pytest
from fastapi import HTTPException

from app.config import ROOT
from app.daemon import build
from app.modules.science import notebook, routes, runs, state, tasks
from app.modules.science.kernels import Kernel
from app.store import iso, now, now_iso, parse
from tests.conftest import run
from tests.test_app import client_for, settle


@pytest.fixture
def sci(config, tmp_path: Path):
    root = tmp_path / "science"
    (root / "sub").mkdir(parents=True)
    (root / ".hidden").mkdir()
    nb = nbformat.v4.new_notebook()
    nb.cells = [nbformat.v4.new_code_cell("print(1)"), nbformat.v4.new_markdown_cell("# notes")]
    nbformat.write(nb, str(root / "analysis.ipynb"))
    (root / "etl.py").write_text("x = 1\n", "utf-8")
    (root / "sub" / "deep.py").write_text("print('deep')\nraise SystemExit(3)\n", "utf-8")
    (root / ".hidden" / "no.py").write_text("", "utf-8")
    (tmp_path / "secret.txt").write_text("no", "utf-8")
    return dataclasses.replace(config, science=dataclasses.replace(config.science, root=root, python=sys.executable))


def test_science_tree_and_reads(sci):
    async def main():
        app = build(sci)
        await app.state.runner.start()
        async with client_for(app) as c:
            left = (await c.get("/api/science/left")).json()
            assert {g["label"]: sorted(r["id"] for r in g["rows"]) for g in left["groups"]} == {"": ["analysis.ipynb", "etl.py"], "sub/": ["sub/deep.py"]}
            assert left["more"] is False and all(g["count"] == len(g["rows"]) for g in left["groups"])
            row = next(r for g in left["groups"] for r in g["rows"] if r["id"] == "analysis.ipynb")
            assert row["title"] == "analysis.ipynb" and row["kind"] == "ipynb" and row["fixed"] == ["notebook"] and row["tags"] == [] and row["when"]
            assert row["kernel"] is None and row["running"] is False and row["schedule"] is None
            item = (await c.get("/api/science/item/analysis.ipynb")).json()
            assert item["kind"] == "ipynb" and item["kernel"] is None and item["schedule"] is None
            assert [x["type"] for x in item["cells"]] == ["code", "markdown"] and item["cells"][0]["source"] == "print(1)"
            assert all(x["id"] for x in item["cells"])
            py = (await c.get("/api/science/item/sub/deep.py")).json()
            assert py["kind"] == "py" and py["source"].startswith("print('deep')") and py["running"] is False and py["last"] is None
            assert (await c.get("/api/science/item/missing.ipynb")).status_code == 404
            assert (await c.get("/api/science/blank")).json() == {"kernels": 0, "files": 3}
            numbers = (await c.get("/api/home/numbers")).json()
            assert any(n["module"] == "science" and n["label"] == "kernels" and n["value"] == 0 for n in numbers)
            home = (await c.get("/api/home/left")).json()
            assert next(g for g in home["groups"] if g["module"] == "science")["count"] == 3
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
        first = nbformat.read(str(sci.science.root / "analysis.ipynb"), as_version=4).cells[0].id

        async def fake_execute(path, cell, source, on_output=None):
            assert source == "print(1)" and cell == first
            nb = notebook.read(path)   # the owner inserts a cell above while this runs
            nb.cells.insert(0, notebook.new_cell("markdown", "# above"))
            notebook.write(path, nb)
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
            assert all(e["cell"] == first and e["index"] == 0 for e in events)
            cells = (await c.get("/api/science/item/analysis.ipynb")).json()["cells"]
            assert cells[0]["source"] == "# above" and cells[1]["id"] == first
            assert cells[1]["execution_count"] == 3 and [o["kind"] for o in cells[1]["outputs"]] == ["stream", "text"]
            nb = nbformat.read(str(sci.science.root / "analysis.ipynb"), as_version=4)
            assert nb.cells[1].execution_count == 3 and len(nb.cells[1].outputs) == 2
            assert not list(sci.science.root.glob("*.tmp"))
            job = (await c.get("/api/jobs")).json()[0]
            assert job["task"] == "science.run" and job["resource"] == "kernel:analysis.ipynb" and job["status"] == "done"
            assert (await c.post("/api/science/action/run", json={"id": "analysis.ipynb", "index": 2})).status_code == 400
            assert (await c.post("/api/science/action/run", json={"id": "analysis.ipynb"})).status_code == 200   # no cell named: the notebook, top to bottom
            await settle(app)
            assert sum(1 for j in (await c.get("/api/jobs")).json() if j["task"] == "science.run") == 2
            assert (await c.post("/api/science/action/restart", json={"id": "analysis.ipynb"})).status_code == 409
            assert (await c.get("/api/events?module=science")).json()["events"][0]["verb"] == "ran"
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_science_script_runs_as_subprocess(sci):
    async def main():
        app = build(sci)
        await app.state.runner.start()
        q = app.state.broadcast.subscribe("science")
        async with client_for(app) as c:
            assert (await c.post("/api/science/action/interrupt", json={"id": "sub/deep.py"})).status_code == 409
            r = await c.post("/api/science/action/run", json={"id": "sub/deep.py"})
            assert r.status_code == 200 and "job" in r.json(), r.text
            await settle(app)
            events = []
            while not q.empty():
                events.append(q.get_nowait())
            assert [e["event"] for e in events] == ["started", "output", "error"] and all(e["cell"] == "script" and e["path"] == "sub/deep.py" for e in events)
            assert events[1]["output"]["text"] == "deep\n" and events[2]["text"] == "exit 3"
            item = (await c.get("/api/science/item/sub/deep.py")).json()
            assert item["running"] is False and item["last"]["status"] == "failed" and item["last"]["exit_code"] == 3 and item["last"]["output"] == "deep\n"
            job = (await c.get("/api/jobs")).json()[0]
            assert job["task"] == "science.script" and job["resource"] == "script:sub/deep.py" and job["status"] == "failed"
            assert (await c.post("/api/science/action/run", json={"id": "etl.py"})).status_code == 200
            await settle(app)
            last = (await c.get("/api/science/item/etl.py")).json()["last"]
            assert last["status"] == "done" and last["exit_code"] == 0 and last["output"] == ""
            assert [e["verb"] for e in (await c.get("/api/events?module=science")).json()["events"]] == ["ran", "failed"]
        assert state.scripts == {}
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
            assert set(routes.ACTIONS) == {"run", "new"} | set(routes.KERNEL_ACTIONS) | set(routes.EDIT_ACTIONS) | set(routes.SCHEDULE_ACTIONS)
            assert (await post("nonsense", {"id": "analysis.ipynb"})).status_code == 404
            assert (await post("set_cell", {"id": "analysis.ipynb", "index": 0, "source": "print(2)"})).status_code == 200
            assert (await post("insert_cell", {"id": "analysis.ipynb", "after": 0, "type": "markdown"})).json()["index"] == 1
            assert (await post("insert_cell", {"id": "analysis.ipynb"})).json()["index"] == 3
            cells = (await c.get("/api/science/item/analysis.ipynb")).json()["cells"]
            assert [(x["type"], x["source"]) for x in cells] == [("code", "print(2)"), ("markdown", ""), ("markdown", "# notes"), ("code", "")]
            assert (await post("delete_cell", {"id": "analysis.ipynb", "index": 1})).status_code == 200
            assert (await post("set_cell", {"id": "analysis.ipynb", "index": 9, "source": "x"})).status_code == 400
            assert (await post("set_cell", {"id": "etl.py", "index": 0, "source": "x"})).status_code == 400
            assert (await post("new", {"path": "fresh", "kind": "ipynb"})).json() == {"id": "fresh.ipynb", "kind": "ipynb"}
            assert (await post("new", {"path": "fresh", "kind": "ipynb"})).status_code == 409
            assert (await post("new", {"path": "sub/notes", "kind": "py"})).json() == {"id": "sub/notes.py", "kind": "py"}
            assert (await post("new", {"path": "lab/2026", "kind": "folder"})).json() == {"id": "lab/2026", "kind": "folder"}
            assert (await post("new", {"path": "../fresh", "kind": "py"})).status_code == 400
            assert (await post("new", {"path": "", "kind": "py"})).status_code == 400
            assert (await post("new", {"path": "x", "kind": "txt"})).status_code == 400
            left = (await c.get("/api/science/left")).json()
            assert sorted(r["id"] for g in left["groups"] for r in g["rows"]) == ["analysis.ipynb", "etl.py", "fresh.ipynb", "sub/deep.py", "sub/notes.py"]
            assert {g["label"] for g in left["groups"]} == {"", "sub/"}   # an empty folder has no rows, so no group
            assert [e["verb"] for e in (await c.get("/api/events?module=science")).json()["events"]] == ["created", "created", "created", "deleted"]
        for name in ("analysis.ipynb", "fresh.ipynb"):
            nb = nbformat.read(str(root / name), as_version=4)
            nbformat.validate(nb)
        assert len(nbformat.read(str(root / "analysis.ipynb"), as_version=4).cells) == 3
        assert nbformat.read(str(root / "fresh.ipynb"), as_version=4).metadata["kernelspec"]["name"] == "python3"
        assert (root / "sub" / "notes.py").read_text("utf-8") == "" and (root / "lab" / "2026").is_dir()
        assert not list(root.glob("*.tmp"))
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_science_set_cells_keeps_outputs_by_id(sci):
    async def main():
        app = build(sci)
        await app.state.runner.start()
        root = sci.science.root
        nb = nbformat.v4.new_notebook()   # a pre-4.5 file: no cell ids on disk
        nb.cells = [nbformat.v4.new_code_cell("print(1)"), nbformat.v4.new_markdown_cell("# notes")]
        nb.cells[0].outputs = [nbformat.v4.new_output("stream", name="stdout", text="1\n")]
        nb.cells[0].execution_count = 3
        for c in nb.cells:
            del c["id"]
        nb.nbformat_minor = 4
        nbformat.write(nb, str(root / "old.ipynb"))
        async with client_for(app) as c:
            post = lambda cells, id="old.ipynb": c.post("/api/science/action/set_cells", json={"id": id, "cells": cells})
            cells = (await c.get("/api/science/item/old.ipynb")).json()["cells"]
            assert [x["id"] for x in cells] == ["c0", "c1"]
            r = await post([{"type": "markdown", "source": "# top"}, {"id": "c0", "type": "code", "source": "print(2)"}, {"id": "c1", "type": "code", "source": "# notes"}])
            assert r.json() == {"id": "old.ipynb", "cells": 3}, r.text
            cells = (await c.get("/api/science/item/old.ipynb")).json()["cells"]
            assert [(x["type"], x["source"]) for x in cells] == [("markdown", "# top"), ("code", "print(2)"), ("code", "# notes")]
            assert cells[1]["id"] == "c0" and cells[1]["execution_count"] == 3 and [o["text"] for o in cells[1]["outputs"]] == ["1\n"]
            assert cells[2]["id"] != "c1" and cells[2]["execution_count"] is None and cells[2]["outputs"] == []
            assert cells[0]["id"] and cells[0]["outputs"] == []
            # A merge: every old id vanishes but every text survives, so nothing is logged as deleted.
            assert (await post([{"type": "code", "source": "# top\n\nprint(2)\n\n# notes"}])).json()["cells"] == 1
            assert (await c.get("/api/events?module=science")).json()["events"] == []
            merged = (await c.get("/api/science/item/old.ipynb")).json()["cells"][0]["id"]
            assert (await post([{"id": merged, "type": "code", "source": "print(3)"}])).json()["cells"] == 1   # text changed in place: an edit, not a deletion
            assert (await c.get("/api/events?module=science")).json()["events"] == []
            assert (await post([{"type": "code", "source": "x"}])).json()["cells"] == 1   # the merged cell's text is gone
            assert [e["verb"] for e in (await c.get("/api/events?module=science")).json()["events"]] == ["deleted"]
            assert (await post([{"type": "heading", "source": ""}])).status_code == 400
            assert (await post([], id="etl.py")).status_code == 400
        on_disk = nbformat.read(str(root / "old.ipynb"), as_version=4)
        nbformat.validate(on_disk)
        assert on_disk.nbformat_minor == 5 and len(on_disk.cells) == 1 and not list(root.glob("*.tmp"))
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
        assert agent.builtins == ("Write", "Edit")

        async def fake_execute(path, cell, source, on_output=None):
            assert source == "print(1)"
            return 7, [{"output_type": "stream", "name": "stdout", "text": "y" * (sci.science.tool_output_chars + 50)}]

        monkeypatch.setattr(state.kernels, "execute", fake_execute)
        full = app.state.mcp_full
        run = _data(await full.call_tool("science_run", {"id": "analysis.ipynb", "index": 0}))
        assert run["execution_count"] == 7 and run["outputs"][0]["text"].endswith("[50 more chars]")
        assert _data(await full.call_tool("science_cell", {"id": "analysis.ipynb", "index": 0}))["outputs"][0]["text"] == "y" * (sci.science.tool_output_chars + 50)
        assert _data(await full.call_tool("science_set_cell", {"id": "analysis.ipynb", "index": 1, "source": "# renamed"})) == {"id": "analysis.ipynb", "index": 1}
        assert _data(await full.call_tool("science_insert_cell", {"id": "analysis.ipynb", "after": -1, "type": "markdown", "source": "# first"})) == {"id": "analysis.ipynb", "index": 0}
        nb = _data(await app.state.mcp_read.call_tool("science_notebook", {"id": "analysis.ipynb"}))
        assert [c["source"] for c in nb["cells"]] == ["# first", "print(1)", "# renamed"] and nb["cells"][1]["execution_count"] == 7
        script = _data(await full.call_tool("science_run", {"id": "sub/deep.py"}))
        assert script["status"] == "failed" and script["exit_code"] == 3 and script["output"] == "deep\n"
        assert _data(await full.call_tool("science_new", {"path": "lab/run", "kind": "py"})) == {"id": "lab/run.py", "kind": "py"}
        assert "error" in _data(await full.call_tool("science_new", {"path": "lab/run", "kind": "py"}))
        assert "error" in _data(await full.call_tool("science_new", {"path": "../out", "kind": "folder"}))
        files = [json.loads(c.text) for c in (await app.state.mcp_read.call_tool("science_files", {})).content]
        assert {f["id"] for f in files} == {"analysis.ipynb", "etl.py", "sub/deep.py", "lab/run.py"} and all(f["kernel"] is None and f["running"] is False for f in files)
        assert [e["verb"] for e in app.state.store.query("SELECT verb FROM app_events WHERE module = 'science' ORDER BY id")] == ["ran", "edited", "edited", "ran", "created"]
        app.state.store.close()

    run(main())


def _data(result):
    """The payload of an MCPServer.call_tool result: structured when the server built one, else the JSON text block."""
    structured = getattr(result, "structured_content", None)
    return structured if structured is not None else json.loads(result.content[0].text)


def test_science_schedules_and_due(sci, monkeypatch):
    async def main():
        app = build(sci)
        await app.state.runner.start()
        store = app.state.store
        ran = []

        async def fake_execute(path, cell, source, on_output=None):
            ran.append(source)
            return len(ran), [{"output_type": "stream", "name": "stdout", "text": "ok\n"}]

        monkeypatch.setattr(state.kernels, "execute", fake_execute)
        async with client_for(app) as c:
            post = lambda verb, body: c.post(f"/api/science/action/{verb}", json=body)
            assert (await post("schedule", {"id": "analysis.ipynb", "every": "sometimes"})).status_code == 400
            assert (await post("schedule", {"id": "analysis.ipynb", "every": "1d", "at": "25:00"})).status_code == 400
            r = await post("schedule", {"id": "analysis.ipynb", "every": "1d", "at": "06:00"})
            assert r.status_code == 200 and parse(r.json()["next_run"]) > now(), r.text
            assert (await post("schedule", {"id": "etl.py", "every": "30m"})).status_code == 200
            assert (await post("schedule", {"id": "missing.py", "every": "30m"})).status_code == 404
            item = (await c.get("/api/science/item/analysis.ipynb")).json()
            assert item["schedule"] == "every 1 d at 06:00" and parse(item["next_run"]) > now()
            assert (await post("unschedule", {"id": "etl.py"})).status_code == 200
            assert (await c.get("/api/science/item/etl.py")).json()["schedule"] is None
            assert [e["verb"] for e in (await c.get("/api/events?module=science")).json()["events"]] == ["unscheduled", "scheduled", "scheduled"]
            assert (await post("schedule", {"id": "sub/deep.py", "every": "1h"})).status_code == 200

        events = []
        ctx = SimpleNamespace(store=store, config=sci, commit=store.tx, event=lambda *a, **k: events.append(a))
        assert await tasks.due(ctx) == "nothing due"
        past = iso(now() - timedelta(hours=30))
        store.execute("UPDATE science_schedules SET next_run = ?", (past,))
        assert await tasks.due(ctx) == "ran 2 scheduled file(s)"
        rows = {r["path"]: r for r in store.query("SELECT * FROM science_schedules")}
        nb = rows["analysis.ipynb"]
        assert nb["last_status"] == "done" and nb["last_result"] == "1 cell(s) ran" and ran == ["print(1)"]
        assert parse(nb["next_run"]) > now() and parse(nb["next_run"]).hour == parse(past).hour   # the clock time is kept, the missed slot skipped
        assert nbformat.read(str(sci.science.root / "analysis.ipynb"), as_version=4).cells[0].outputs[0]["text"] == "ok\n"
        deep = rows["sub/deep.py"]
        assert deep["last_status"] == "failed" and "exit 3" in deep["last_result"] and parse(deep["next_run"]) > now()
        assert store.one("SELECT output FROM science_script_runs WHERE path = 'sub/deep.py'")["output"] == "deep\n"
        assert [e[0] for e in events] == ["ran", "failed"]
        assert await tasks.due(ctx) == "nothing due"
        text = app.state.registry.get("science").context(store, app.state.registry)
        assert "Scheduled: sub/deep.py next" in text and "analysis.ipynb next" in text and "last done" in text
        await app.state.runner.drain(1)
        store.close()

    run(main())


def test_science_schedule_arithmetic():
    assert runs.every_seconds("30m") == 1800 and runs.every_seconds("2d") == 172800
    for bad in ("", "m", "0h", "5x", "1.5h"):
        with pytest.raises(ValueError):
            runs.every_seconds(bad)
    with pytest.raises(ValueError):
        runs.first_run(60, "6am")
    assert parse(runs.first_run(60, None)) > now()
    assert parse(runs.next_run(iso(now() - timedelta(days=3)), 86400)) > now()
    ahead = iso(now() + timedelta(hours=1))
    assert runs.next_run(ahead, 3600) == iso(parse(ahead) + timedelta(hours=1))


def test_science_reap(sci):
    async def main():
        app = build(sci)
        limit = sci.science.idle_minutes

        def kernel(name, minutes, running=None):
            return Kernel(path=Path(name), manager=None, client=None, started_at="", last_activity=now() - timedelta(minutes=minutes), running=running)

        stale = kernel("a.ipynb", limit + 1)
        busy = kernel("b.ipynb", limit * 10, running={"cell": "c0", "outputs": []})
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


def test_science_reap_never_executes_or_writes():
    """The reaper is housekeeping: it names no run or write. `due` runs files on purpose, so the guard is on `reap` alone."""
    src = (ROOT / "app" / "modules" / "science" / "tasks.py").read_text("utf-8")
    fn = next(n for n in ast.parse(src).body if isinstance(n, ast.AsyncFunctionDef) and n.name == "reap")
    names = {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)} | {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
    assert not names & {"execute", "write", "start", "restart", "run_file", "run_script", "run_cell"}
