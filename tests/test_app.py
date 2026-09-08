"""Routes through the real app: memory module end to end, and sessions with a fake CLI."""

import json
from pathlib import Path

import httpx

from app.daemon import build
from app.modules import Manifest, Module
from tests.conftest import fake_spawn, run

INIT = json.dumps({"type": "system", "subtype": "init", "session_id": "s1", "tools": ["mcp__otto__memory_search"]})
TOOL = json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "mcp__otto__memory_search", "input": {"query": "x"}}]}})
TOOL_OK = json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "[]"}]}})
TEXT = json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Nothing about that yet."}]}})
RESULT = json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "Nothing about that yet.", "session_id": "s1"})
CLOSE = json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": '{"title": "Search for x", "tags": ["memory", "search"]}', "session_id": "s2"})


def client_for(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def settle(app):
    """Wait until the runner has no queued or running work."""
    import asyncio

    for _ in range(200):
        await asyncio.sleep(0.01)
        if not app.state.runner.running and app.state.runner._queue.empty():
            return


def queue_module(pending: list[dict]) -> Module:
    """A page module whose only hook is queue(store); stands in for web_search."""
    return Module(
        manifest=Manifest(name="queued", title="Queued", hue="#d9915b", icon="", order=9),
        path=Path(__file__).parent,
        tasks={},
        router=None,
        schema=None,
        numbers=None,
        today=None,
        queue=lambda store: list(pending),
        item=None,
        context=None,
        register_tools=None,
        prompt=None,
    )


def test_memory_end_to_end(config):
    async def main():
        app = build(config)
        await app.state.runner.start()
        async with client_for(app) as c:
            shell = (await c.get("/api/shell")).json()
            assert {m["name"] for m in shell["modules"]} >= {"home", "memory"} and shell["budget"]["max"] == config.nightly.max_sessions
            r = await c.post("/api/memory/action/capture", json={"kind": "note", "text": "buy sqlite book", "tags": ["reading"]})
            assert r.status_code == 200, r.text
            mid = r.json()["id"]
            await c.post("/api/memory/action/capture", json={"kind": "link", "text": "https://example.com the site"})
            left = (await c.get("/api/memory/left?query=sqlite")).json()
            assert left["groups"][0]["rows"][0]["id"] == mid and left["showing"] == "1 / 1"
            left = (await c.get("/api/memory/left?chip=Links")).json()
            assert left["groups"][0]["rows"][0]["leading"]["kind"] == "link"
            item = (await c.get(f"/api/memory/item/{mid}")).json()
            assert item["tags"] == ["reading"] and item["actions"][-1]["verb"] == "forget"
            assert (await c.post("/api/memory/action/tag", json={"id": mid, "tags": ["books"]})).json()["tags"] == ["books", "reading"]
            home = (await c.get("/api/home/left")).json()
            assert next(g for g in home["groups"] if g["module"] == "memory")["count"] == 2
            numbers = (await c.get("/api/home/numbers")).json()
            assert next(n for n in numbers if n["module"] == "memory")["value"] == 2
            assert (await c.post("/api/memory/action/forget", json={"id": mid})).status_code == 200
            assert (await c.get(f"/api/memory/item/{mid}")).status_code == 404
            ev = (await c.get("/api/events?module=memory")).json()
            assert [e["verb"] for e in ev["events"]][:2] == ["forgot", "tagged"]
            s = (await c.put("/api/settings", json={"ui.page_size": 20})).json()
            assert s["ui.page_size"] == 20
            assert (await c.put("/api/settings", json={"ui.page_size": 5})).status_code == 400
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_session_turn_and_clear(config):
    calls = []

    async def main():
        app = build(config, spawn_fn=fake_spawn([INIT, TOOL, TOOL_OK, TEXT, RESULT], calls))
        await app.state.runner.start()
        async with client_for(app) as c:
            r = await c.post("/api/session/memory/send", json={"text": "anything about x?"})
            assert r.status_code == 200, r.text
            await settle(app)
            s = (await c.get("/api/session/memory")).json()
            roles = [(t["role"], t.get("tool"), t.get("status")) for t in s["turns"]]
            assert roles == [("user", None, None), ("tool", "memory_search", "done"), ("model", None, None)]
            assert s["session"]["cli_started"] == 1 and s["busy"] is False
            args = calls[0]["args"]
            assert "--session-id" in args and "--restricted" in args and "--permission-prompts" in args
            assert "--tools" in args and "Write" not in args[args.index("--tools") + 1]
            assert "mcp__otto__memory_add" in args[args.index("--allowedTools") + 1]
            assert not any(k.startswith("ANTHROPIC_") or k.startswith("CLAUDECODE") for k in calls[0]["env"])
            # second turn resumes
            await c.post("/api/session/memory/send", json={"text": "and y?"})
            await settle(app)
            assert "--resume" in calls[1]["args"]
            # /clear closes with title and tags from the one-shot tagger
            app.state.claude.spawn = fake_spawn([CLOSE], calls)
            r = await c.post("/api/session/memory/send", json={"text": "/clear"})
            assert r.json() == {"cleared": True}
            await settle(app)
            row = app.state.store.one("SELECT * FROM sessions")
            assert row["closed_at"] and row["title"] == "Search for x" and json.loads(row["tags"]) == ["memory", "search"]
            assert calls[2]["args"][calls[2]["args"].index("--max-turns") + 1] == "2"
            assert (await c.get("/api/session/memory")).json()["session"] is None
            assert (await c.post("/api/session/memory/send", json={"text": "/clear"})).json() == {"cleared": False}
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_failed_first_turn_retires_session(config):
    async def main():
        bad = json.dumps({"type": "result", "subtype": "error_during_execution", "is_error": True, "result": "boom", "session_id": "s1"})
        app = build(config, spawn_fn=fake_spawn([bad]))
        await app.state.runner.start()
        async with client_for(app) as c:
            await c.post("/api/session/memory/send", json={"text": "hi"})
            await settle(app)
            s = (await c.get("/api/session/memory")).json()
            assert s["session"] is None
            rows = app.state.store.query("SELECT * FROM sessions")
            assert rows[0]["closed_at"] and rows[0]["title"] == "(failed to start)"
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_home_review_group(config):
    """A module with a queue hook leads Home with every waiting row; empty or disabled, it shows nothing."""
    pending = [
        {"id": 7, "module": "queued", "text": "a finding worth reading", "stamp": "2026-09-08T09:00:00+00:00"},
        {"id": 8, "module": "queued", "text": "another finding", "stamp": "2026-09-08T08:00:00+00:00"},
    ]

    async def main():
        app = build(config)
        await app.state.runner.start()
        st = app.state
        st.registry.modules["queued"] = queue_module(pending)
        st.store.set_setting("modules.queued.enabled", True)
        home = st.registry.get("home")
        async with client_for(app) as c:
            await c.post("/api/memory/action/capture", json={"kind": "note", "text": "a note from today"})

            groups = (await c.get("/api/home/left")).json()["groups"]
            assert groups[0]["module"] == "queued" and groups[0]["label"] == "Review"
            assert groups[0]["count"] == 2 and groups[0]["more"] == 0
            assert [r["id"] for r in groups[0]["rows"]] == [7, 8]
            assert [g["module"] for g in groups if g["label"] == "Review"] == ["queued"]
            assert any(g["module"] == "memory" and g["label"] == "Memory" for g in groups)
            text = home.context(st.store, st.registry)
            assert "Review: 2 waiting" in text
            assert "  - (queued 7) a finding worth reading" in text and "  - (queued 8) another finding" in text

            pending.clear()
            groups = (await c.get("/api/home/left")).json()["groups"]
            assert all(g["label"] != "Review" for g in groups)
            assert "Review: nothing waiting" in home.context(st.store, st.registry)

            pending.extend([{"id": 7, "module": "queued", "text": "back again", "stamp": "2026-09-08T09:00:00+00:00"}])
            st.store.set_setting("modules.queued.enabled", False)
            groups = (await c.get("/api/home/left")).json()["groups"]
            assert all(g["label"] != "Review" for g in groups)
            assert "Review" not in home.context(st.store, st.registry)
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())
