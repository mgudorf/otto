"""Graph module: rebuild from the tag sources, curation overlays, the write split, and the routes.

Graph and System are the two modules here that list no rows of their own, so the one page and the one agent are
proved against them: what carries no facet stays off the feed, and what has no page still reaches Otto.
"""

import json

from app.api import _otto
from app.config import ROOT
from app.daemon import build as build_app
from app.modules.graph import build, tasks, tools
from app.store import add_tags, now_iso
from tests.conftest import run
from tests.test_app import client_for, settle

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


def test_app_tags_reach_the_graph(store):
    """A tag the owner writes on an email is a node like any other, and co-occurs with the rest of that row's tags."""
    seed(store)
    add_tags(store, "email", "18f2a", ["Ledger", "tax"])
    with store.tx() as conn:
        assert build.rebuild(conn) == (5, 4)
    n = nodes(store)
    assert (n["tax"]["count"], n["tax"]["items"], n["tax"]["sessions"]) == (3, 1, 2)
    assert (n["ledger"]["count"], n["ledger"]["items"]) == (2, 2)
    assert edges(store)[("ledger", "tax", "cooccur")] == 1


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
            assert (await c.get("/api/graph/item/python")).json()["count"] == 2
            shell = (await c.get("/api/shell")).json()
            g = next(m for m in shell["modules"] if m["name"] == "graph")
            assert g["hue"] == "#C1BE75" and g["facet"] is None   # a tag is not an item: the graph draws the brain and lists nothing
            assert all(n["module"] != "graph" for n in (await c.get("/api/home/numbers")).json())
            assert all(r["module"] != "graph" for r in (await c.get("/api/feed?mode=recent")).json()["items"])
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_system_lists_its_routines(config):
    """Every scheduled task is a routine on the feed: what it runs, when it last ran, and the switches it offers."""

    async def main():
        app = build_app(config)
        await app.state.runner.start()
        app.state.scheduler.sync_tasks()   # the rows the daemon writes at boot, which this module lists
        store = app.state.store
        async with client_for(app) as c:
            mine = lambda d: [r for r in d["items"] if r["module"] == "system"]
            listed = mine((await c.get("/api/feed?mode=recent")).json())
            assert {r["id"] for r in listed} >= {"graph.rebuild", "science.reap"}
            assert all(r["fixed"] == ["routine"] and r["type"] == "routine" and r["tags"] == [] for r in listed)
            row = next(r for r in listed if r["id"] == "graph.rebuild")
            assert (row["title"], row["snip"], row["right"]) == ("graph.rebuild", "every 15 m", "every 15 m")
            assert row["when"] is None and row["late"] is False and row["paused"] is False
            assert row["kv"] == [["Every", "every 15 m"], ["Last run", "never"], ["Last result", "nothing said"], ["Resource", "graph"]]
            assert row["verbs"] == [["run", "Run now"], ["pause", "Pause"]]
            assert next(r for r in listed if r["id"] == "newsfeed.run")["snip"] == "nightly"   # an LLM task runs in the window, not on its interval
            assert mine((await c.get("/api/feed?mode=priority")).json()) == []

            # only what broke waits on the owner
            store.execute("UPDATE app_tasks SET last_run = ?, last_status = 'failed', last_result = 'boom' WHERE name = ?", (now_iso(), "graph.rebuild"))
            waiting = mine((await c.get("/api/feed?mode=priority")).json())
            assert [r["id"] for r in waiting] == ["graph.rebuild"] and waiting[0]["waits"] == 1
            assert waiting[0]["late"] is True and waiting[0]["right"] == "failed" and ["Last result", "boom"] in waiting[0]["kv"]

            paused = (await c.post("/api/verb", json={"module": "system", "id": "graph.rebuild", "verb": "pause"})).json()
            assert paused == {"ok": True, "said": "disabled graph.rebuild", "removes": False}
            off = next(r for r in mine((await c.get("/api/feed?mode=recent")).json()) if r["id"] == "graph.rebuild")
            assert off["paused"] is True and off["right"] == "failed" and off["verbs"][1] == ["resume", "Resume"]
            assert (await c.post("/api/verb", json={"module": "system", "id": "graph.rebuild", "verb": "resume"})).json()["said"] == "enabled graph.rebuild"

            # Run now hands the task to the runner as the clock would, so the run writes its own result back
            assert (await c.post("/api/verb", json={"module": "system", "id": "graph.rebuild", "verb": "run"})).json()["said"] == "run"
            await settle(app)
            t = store.one("SELECT last_status, last_result FROM app_tasks WHERE name = ?", ("graph.rebuild",))
            assert t["last_status"] == "done" and t["last_result"] == "0 nodes, 0 edges"
            assert (await c.post("/api/verb", json={"module": "system", "id": "nope", "verb": "run"})).status_code == 404
            assert (await c.post("/api/verb", json={"module": "system", "id": "graph.rebuild", "verb": "nonsense"})).status_code == 404
        await app.state.runner.drain(1)
        store.close()

    run(main())


def test_otto_is_every_agent_at_once(config):
    """One agent behind the drawer: its tools, skills and prompt are the union of the enabled modules', and a module
    switched off takes its own out of the union."""

    async def main():
        app = build_app(config)
        await app.state.runner.start()
        async with client_for(app) as c:
            agents = [m for m in app.state.registry.ordered() if m.manifest.agent]
            otto = _otto(app.state)
            assert set(otto.manifest.agent.read_tools) == {t for m in agents for t in m.manifest.agent.read_tools}
            assert set(otto.manifest.agent.write_tools) == {t for m in agents for t in m.manifest.agent.write_tools}
            assert {"graph_nodes", "graph_link"} <= set(otto.manifest.agent.read_tools) | set(otto.manifest.agent.write_tools)
            assert all(m.prompt in otto.prompt for m in agents if m.prompt)

            s = (await c.get("/api/session/otto")).json()
            assert s["sessions"] == [] and s["agent"]["cmd"] == "claude · otto"
            assert s["agent"]["skills"] == list(otto.manifest.agent.skills) and "link" in s["agent"]["skills"]
            assert s["context_label"] == ", ".join(m.manifest.title for m in agents)   # what is open, not a count

            assert (await c.put("/api/settings", json={"modules.newsfeed.enabled": False})).status_code == 200
            assert "newsfeed_search" not in _otto(app.state).manifest.agent.read_tools
            assert "Newsfeed" not in (await c.get("/api/session/otto")).json()["context_label"]
            assert (await c.get("/api/session/system")).status_code == 404   # no agent of its own, and none is invented
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())
