"""Graph module: rebuild from the tag sources, curation overlays, the write split, and the routes."""

import json

from app.config import ROOT
from app.daemon import build as build_app
from app.modules.graph import build, tasks, tools
from app.store import now_iso
from tests.conftest import run
from tests.test_app import client_for

SECOND_BRAIN_SCHEMA = (ROOT / "app" / "modules" / "second_brain" / "schema.sql").read_text("utf-8")
GRAPH_SCHEMA = (ROOT / "app" / "modules" / "graph" / "schema.sql").read_text("utf-8")
READ_TOOLS = {"graph_nodes", "graph_neighbors", "graph_items"}
WRITE_TOOLS = {"graph_link", "graph_unlink", "graph_merge", "graph_prune", "graph_restore"}


class FakeServer:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


def seed(store):
    """Three items and three sessions: s1 closed and tagged, s2 a live pane (no tags yet), s3 a Chat conversation tagged while open."""
    store.migrate(SECOND_BRAIN_SCHEMA)
    store.migrate(GRAPH_SCHEMA)
    ts = now_iso()
    with store.tx() as conn:
        for i in (1, 2, 3):
            conn.execute("INSERT INTO second_brain_items(id, kind, text, created_at, updated_at) VALUES (?, 'note', ?, ?, ?)", (i, f"m{i}", ts, ts))
        for mid, tag in [(1, "Python"), (1, "sqlite"), (2, "python "), (2, "SQLite"), (3, "ledger")]:
            conn.execute("INSERT INTO second_brain_tags(item_id, tag) VALUES (?, ?)", (mid, tag))
        conn.execute("INSERT INTO app_sessions(id, module, opened_at, closed_at, title, tags) VALUES ('s1', 'second_brain', ?, ?, 'one', ?)", (ts, ts, json.dumps(["SQLITE", "tax"])))
        conn.execute("INSERT INTO app_sessions(id, module, opened_at) VALUES ('s2', 'second_brain', ?)", (ts,))
        conn.execute("INSERT INTO app_sessions(id, module, opened_at, title, tags) VALUES ('s3', 'chat', ?, 'three', ?)", (ts, json.dumps(["tax", "Chat"])))


def nodes(store):
    return {r["tag"]: r for r in store.query("SELECT * FROM graph_nodes")}


def edges(store):
    return {(r["a"], r["b"], r["kind"]): r["weight"] for r in store.query("SELECT * FROM graph_edges")}


def snapshot(store):
    return [store.query(f"SELECT * FROM {t} ORDER BY 1, 2") for t in ("second_brain_items", "second_brain_tags", "app_sessions")]


def test_rebuild_from_sources(store):
    seed(store)
    with store.tx() as conn:
        assert build.rebuild(conn) == (5, 3)
    n = nodes(store)
    assert set(n) == {"python", "sqlite", "ledger", "tax", "chat"}
    assert (n["sqlite"]["count"], n["sqlite"]["items"], n["sqlite"]["sessions"]) == (3, 2, 1)
    assert n["python"]["count"] == 2 and n["tax"]["sessions"] == 2 and n["chat"]["sessions"] == 1
    assert edges(store) == {("python", "sqlite", "cooccur"): 2, ("sqlite", "tax", "cooccur"): 1, ("chat", "tax", "cooccur"): 1}
    before = (nodes(store), edges(store))
    with store.tx() as conn:
        build.rebuild(conn)
    assert (nodes(store), edges(store)) == before


def test_overlays_and_sources_untouched(store, config):
    seed(store)
    read, full = FakeServer(), FakeServer()
    tools.register(read, full, store, config)
    with store.tx() as conn:
        build.rebuild(conn)
    sources_before = snapshot(store)
    t = full.tools
    assert t["graph_merge"]("Ledger", "tax")["ok"]
    n = nodes(store)
    assert "ledger" not in n and n["tax"]["count"] == 3 and n["tax"]["items"] == 1
    assert t["graph_prune"]("python")["ok"]
    assert "python" not in nodes(store) and ("python", "sqlite", "cooccur") not in edges(store)
    assert t["graph_link"]("tax", "sqlite", "same ledger work")["ok"]
    assert edges(store)[("sqlite", "tax", "link")] == 1
    assert t["graph_restore"]("python")["ok"] and nodes(store)["python"]["count"] == 2
    assert "error" in t["graph_restore"]("python")
    assert "error" in t["graph_link"]("nope", "tax")
    assert "error" in t["graph_merge"]("tax", "ledger")  # would make a cycle
    assert t["graph_unlink"]("sqlite", "tax")["ok"] and ("sqlite", "tax", "link") not in edges(store)
    hits = read.tools["graph_items"]("TAX")
    assert [m["id"] for m in hits["items"]] == [3] and [s["id"] for s in hits["sessions"]] == ["s1", "s3"]
    assert {e["neighbor"] for e in read.tools["graph_neighbors"]("sqlite")} == {"python", "tax"}
    assert snapshot(store) == sources_before
    assert [e["verb"] for e in store.query("SELECT verb FROM app_events ORDER BY id")] == ["merged", "pruned", "linked", "restored", "unlinked"]


def test_write_tools_only_on_full(store, config):
    seed(store)
    read, full = FakeServer(), FakeServer()
    tools.register(read, full, store, config)
    assert set(read.tools) == READ_TOOLS
    assert set(full.tools) == READ_TOOLS | WRITE_TOOLS


def test_graph_routes(config):
    async def main():
        app = build_app(config)
        await app.state.runner.start()
        async with client_for(app) as c:
            for tags in (["Python", "sqlite"], ["python"]):
                assert (await c.post("/api/second_brain/action/capture", json={"kind": "note", "text": "x", "tags": tags})).status_code == 200
            assert (await c.get("/api/graph/left")).json()["groups"][0]["count"] == 0
            job = app.state.runner.submit("graph.rebuild", "graph", "graph", "scheduled", tasks.rebuild)
            assert await job.done == "2 nodes, 1 edges"
            left = (await c.get("/api/graph/left")).json()
            assert [r["id"] for r in left["groups"][0]["rows"]] == ["python", "sqlite"] and left["groups"][0]["rows"][0]["count"] == 2
            assert left["more"] is False and "leading" not in left["groups"][0]["rows"][0]
            g = (await c.get("/api/graph/graph?query=sql")).json()
            assert [n["tag"] for n in g["nodes"]] == ["sqlite"] and g["edges"] == [] and g["totals"] == {"nodes": 2, "edges": 1}
            assert g["built_at"] == app.state.store.cursor("graph.rebuild")
            g = (await c.get("/api/graph/graph")).json()
            assert g["edges"] == [{"a": "python", "b": "sqlite", "kind": "cooccur", "weight": 1}]
            numbers = (await c.get("/api/home/numbers")).json()
            assert next(n for n in numbers if n["module"] == "graph")["value"] == 2
            shell = (await c.get("/api/shell")).json()
            assert next(m for m in shell["modules"] if m["name"] == "graph")["hue"] == "#b3b06a"
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())
