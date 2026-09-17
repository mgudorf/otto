"""Routes through the real app: second_brain module end to end, and sessions with a fake CLI."""

import json
from pathlib import Path

import httpx

from app.daemon import build
from app.modules import Manifest, Module
from app.store import now_iso
from tests.conftest import fake_spawn, run

INIT = json.dumps({"type": "system", "subtype": "init", "session_id": "s1", "tools": ["mcp__otto__second_brain_search"]})
TOOL = json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "mcp__otto__second_brain_search", "input": {"query": "x"}}]}})
TOOL_OK = json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "[]"}]}})
TEXT = json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Nothing about that yet."}]}})
RESULT = json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "Nothing about that yet.", "session_id": "s1"})
CLOSE = json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": '{"title": "Search for x", "tags": ["second_brain", "search"]}', "session_id": "s2"})


def client_for(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def settle(app):
    """Wait until the runner has no queued or running work."""
    import asyncio

    for _ in range(200):
        await asyncio.sleep(0.01)
        if not app.state.runner.running and app.state.runner._queue.empty():
            return


def queue_module(pending: list[dict], todays: list[dict]) -> Module:
    """A page module with both hooks, as Newsfeed has: a queue and today's rows."""
    return Module(
        manifest=Manifest(name="queued", title="Queued", hue="#d9915b", icon="", order=9),
        path=Path(__file__).parent,
        tasks={},
        router=None,
        schema=None,
        numbers=None,
        today=lambda store: list(todays),
        queue=lambda store: list(pending),
        item=None,
        context=None,
        register_tools=None,
        prompt=None,
    )


def test_second_brain_end_to_end(config):
    async def main():
        app = build(config)
        await app.state.runner.start()
        async with client_for(app) as c:
            shell = (await c.get("/api/shell")).json()
            assert {m["name"] for m in shell["modules"]} >= {"home", "second_brain"} and shell["budget"]["max"] == config.nightly.max_sessions
            r = await c.post("/api/second_brain/action/capture", json={"kind": "note", "text": "buy sqlite book", "tags": ["reading"]})
            assert r.status_code == 200, r.text
            mid = r.json()["id"]
            await c.post("/api/second_brain/action/capture", json={"kind": "link", "text": "https://example.com the site"})
            left = (await c.get("/api/second_brain/left?query=sqlite")).json()
            assert left["groups"][0]["rows"][0]["id"] == mid and left["showing"] == "1 / 1"
            left = (await c.get("/api/second_brain/left?chip=Links")).json()
            assert left["groups"][0]["rows"][0]["leading"]["kind"] == "link"
            item = (await c.get(f"/api/second_brain/item/{mid}")).json()
            assert item["tags"] == ["reading"] and item["actions"][-1]["verb"] == "forget"
            assert (await c.post("/api/second_brain/action/tag", json={"id": mid, "tags": ["books"]})).json()["tags"] == ["books", "reading"]
            home = (await c.get("/api/home/left")).json()
            assert next(g for g in home["groups"] if g["module"] == "second_brain")["count"] == 2
            numbers = (await c.get("/api/home/numbers")).json()
            assert next(n for n in numbers if n["module"] == "second_brain")["value"] == 2
            assert (await c.post("/api/second_brain/action/forget", json={"id": mid})).status_code == 200
            assert (await c.get(f"/api/second_brain/item/{mid}")).status_code == 404
            ev = (await c.get("/api/events?module=second_brain")).json()
            assert [e["verb"] for e in ev["events"]][:2] == ["forgot", "tagged"]
            s = (await c.put("/api/settings", json={"ui.page_size": 20})).json()
            assert s["ui.page_size"] == 20
            assert (await c.put("/api/settings", json={"ui.page_size": 5})).status_code == 400
            # a module's own model and effort: one of the configured choices or default
            assert (await c.put("/api/settings", json={"modules.second_brain.model": "gpt"})).status_code == 400
            assert (await c.put("/api/settings", json={"modules.second_brain.effort": "extreme"})).status_code == 400
            f = (await c.put("/api/settings", json={"modules.second_brain.model": config.claude.models[0], "modules.second_brain.effort": "low"})).json()
            assert f["modules.second_brain.model"] == config.claude.models[0] and f["modules.second_brain.effort"] == "low"
            mem = next(m for m in (await c.get("/api/shell")).json()["modules"] if m["name"] == "second_brain")
            assert mem["model"] == config.claude.models[0] and mem["effort"] == "low"
            assert shell["claude"]["models"] == list(config.claude.models) and shell["claude"]["efforts"] == list(config.claude.efforts)
            # an export is every table as JSON rows
            r = (await c.post("/api/data/export")).json()
            dump = json.loads(Path(r["path"]).read_text("utf-8"))
            assert dump["app_settings"] and "second_brain_items" in dump and (await c.get("/api/data")).json()["exports"] == 1
            # every static file revalidates, so a restarted daemon never serves stale modules
            assert (await c.get("/shell.js")).headers["cache-control"] == "no-cache"
            # a run counts against the nightly budget from the moment it starts, so concurrent runs see each other
            app.state.store.execute("INSERT INTO app_llm_runs(ts, module, task, status, budgeted) VALUES (?, 'second_brain', 'second_brain.suggest', 'running', 1)", (now_iso(),))
            assert (await c.get("/api/shell")).json()["budget"]["used"] == 1
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_session_turn_and_clear(config):
    calls = []

    async def main():
        app = build(config, spawn_fn=fake_spawn([INIT, TOOL, TOOL_OK, TEXT, RESULT], calls))
        await app.state.runner.start()
        async with client_for(app) as c:
            app.state.store.set_setting("modules.second_brain.model", "sonnet")
            app.state.store.set_setting("modules.second_brain.effort", "low")
            r = await c.post("/api/session/second_brain/send", json={"text": "anything about x?"})
            assert r.status_code == 200, r.text
            sid = r.json()["session"]
            await settle(app)
            tabs = (await c.get("/api/session/second_brain")).json()
            assert [(t["id"], t["label"], t["busy"]) for t in tabs["sessions"]] == [(sid, "anything about x?", False)]
            s = (await c.get(f"/api/session/second_brain/{sid}")).json()
            roles = [(t["role"], t.get("tool"), t.get("status")) for t in s["turns"]]
            assert roles == [("user", None, None), ("tool", "second_brain_search", "done"), ("model", None, None)]
            assert s["session"]["cli_started"] == 1 and s["busy"] is False
            args = calls[0]["args"]
            assert "--session-id" in args and "--restricted" in args and "--permission-prompts" in args and "--include-partial-messages" in args
            assert args[args.index("--model") + 1] == "sonnet" and args[args.index("--effort") + 1] == "low"   # the module's own picks
            assert "--tools" in args and "Write" not in args[args.index("--tools") + 1]
            assert "mcp__otto__second_brain_add" in args[args.index("--allowedTools") + 1]
            assert not any(k.startswith("ANTHROPIC_") or k.startswith("CLAUDECODE") for k in calls[0]["env"])
            # second turn on the same tab resumes; a turn without an id opens a second tab
            await c.post("/api/session/second_brain/send", json={"text": "and y?", "id": sid})
            await settle(app)
            assert "--resume" in calls[1]["args"]
            sid2 = (await c.post("/api/session/second_brain/send", json={"text": "another thread"})).json()["session"]
            await settle(app)
            assert sid2 != sid and "--session-id" in calls[2]["args"]
            assert [t["id"] for t in (await c.get("/api/session/second_brain")).json()["sessions"]] == [sid, sid2]
            assert (await c.get("/api/session/second_brain/nope")).status_code == 404
            # /clear closes one tab with title and tags from the one-shot tagger; the other stays open
            app.state.claude.spawn = fake_spawn([CLOSE], calls)
            r = await c.post("/api/session/second_brain/send", json={"text": "/clear", "id": sid})
            assert r.json() == {"cleared": True}
            await settle(app)
            row = app.state.store.one("SELECT * FROM app_sessions WHERE id = ?", (sid,))
            assert row["closed_at"] and row["title"] == "Search for x" and json.loads(row["tags"]) == ["second_brain", "search"]
            assert calls[3]["args"][calls[3]["args"].index("--max-turns") + 1] == "2"
            assert [t["id"] for t in (await c.get("/api/session/second_brain")).json()["sessions"]] == [sid2]
            assert (await c.post("/api/session/second_brain/send", json={"text": "/clear"})).json() == {"cleared": False}
            assert (await c.post("/api/session/second_brain/send", json={"text": "/clear", "id": sid})).status_code == 404
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_failed_first_turn_retires_session(config):
    async def main():
        bad = json.dumps({"type": "result", "subtype": "error_during_execution", "is_error": True, "result": "boom", "session_id": "s1"})
        app = build(config, spawn_fn=fake_spawn([bad]))
        await app.state.runner.start()
        async with client_for(app) as c:
            await c.post("/api/session/second_brain/send", json={"text": "hi"})
            await settle(app)
            assert (await c.get("/api/session/second_brain")).json()["sessions"] == []
            rows = app.state.store.query("SELECT * FROM app_sessions")
            assert rows[0]["closed_at"] and rows[0]["title"] == "(failed to start)"
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_huge_stream_line_survives(config):
    """One stream-json message can carry a whole file as a tool result; it must not truncate the run."""

    async def main():
        big = json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "y" * 400_000}]}})
        app = build(config, spawn_fn=fake_spawn([INIT, TOOL, big, TEXT, RESULT]))
        await app.state.runner.start()
        async with client_for(app) as c:
            sid = (await c.post("/api/session/second_brain/send", json={"text": "read the big one"})).json()["session"]
            await settle(app)
            s = (await c.get(f"/api/session/second_brain/{sid}")).json()
            assert [t["role"] for t in s["turns"]] == ["user", "tool", "model"]
            assert s["turns"][1]["status"] == "done" and s["busy"] is False
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_home_review_group(config):
    """A module with a queue hook leads Home with every waiting row; empty or disabled, it shows nothing."""
    pending = [
        {"id": 7, "module": "queued", "text": "a finding worth reading", "stamp": "2026-09-08T09:00:00+00:00"},
        {"id": 8, "module": "queued", "text": "another finding", "stamp": "2026-09-08T08:00:00+00:00"},
    ]
    todays = [{"id": 9, "module": "queued", "text": "found this morning", "stamp": "2026-09-08T07:00:00+00:00"}]

    async def main():
        app = build(config)
        await app.state.runner.start()
        st = app.state
        st.registry.modules["queued"] = queue_module(pending, todays)
        st.store.set_setting("modules.queued.enabled", True)
        home = st.registry.get("home")
        async with client_for(app) as c:
            await c.post("/api/second_brain/action/capture", json={"kind": "note", "text": "a note from today"})

            groups = (await c.get("/api/home/left")).json()["groups"]
            assert groups[0]["module"] == "queued" and groups[0]["label"] == "Review"
            assert groups[0]["count"] == 2 and groups[0]["more"] == 0
            assert [r["id"] for r in groups[0]["rows"]] == [7, 8]
            assert [g["module"] for g in groups if g["label"] == "Review"] == ["queued"]
            assert any(g["module"] == "second_brain" and g["label"] == "Second Brain" for g in groups)
            # one module, two groups: the page keys them label:module, so the keys stay distinct
            mine = [(g["label"], g["module"]) for g in groups if g["module"] == "queued"]
            assert mine == [("Review", "queued"), ("Queued", "queued")]
            assert len({f"{label}:{mod}" for label, mod in mine}) == 2
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
            assert "(queued " not in home.context(st.store, st.registry)
            # a module without a page still queues for the owner; its header cannot navigate
            quiet = queue_module(pending, [])
            quiet.manifest = Manifest(name="quiet", title="Quiet", hue="#d9915b", icon="", order=9, page=False)
            st.registry.modules["quiet"] = quiet
            groups = (await c.get("/api/home/left")).json()["groups"]
            assert groups[0]["module"] == "quiet" and groups[0]["label"] == "Review" and groups[0]["page"] is False
            assert next(g for g in groups if g["module"] == "second_brain")["page"] is True
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


FILED = json.dumps({"type": "result", "subtype": "success", "is_error": False, "session_id": "s3", "result": json.dumps({
    "kind": "bug", "title": "Forget leaves the inspector open", "summary": "Forgetting an item should clear the inspector.",
    "tags": ["second_brain", "bug", "inspector"], "ref": None, "draft": "# Forget leaves the inspector open\n\n- Where: second_brain item\n",
})})
NOT_JSON = json.dumps({"type": "result", "subtype": "success", "is_error": False, "session_id": "s4", "result": "I could not classify this."})


def test_feedback_end_to_end(config):
    calls, procs = [], []

    def spying(lines):
        inner = fake_spawn(lines, calls)

        async def spawn(args, cwd, env):
            proc = await inner(args, cwd, env)
            procs.append(proc)
            return proc

        return spawn

    async def main():
        app = build(config, spawn_fn=spying([FILED]))
        await app.state.runner.start()
        async with client_for(app) as c:
            shell = (await c.get("/api/shell")).json()
            assert next(m for m in shell["modules"] if m["name"] == "feedback")["page"] is False   # listed for hue and icon, kept off the rail
            assert (await c.post("/api/feedback/action/add", json={"page": "second_brain", "text": "  "})).status_code == 400
            r = await c.post("/api/feedback/action/add", json={"page": "second_brain", "text": "forget should also clear the inspector", "item": {"module": "second_brain", "id": 7, "text": "buy sqlite book"}})
            assert r.status_code == 200, r.text
            fid = r.json()["id"]
            await settle(app)
            assert (await c.get("/api/feedback/recent")).status_code == 422                    # the panel is per page; there is no page-less list
            recent = (await c.get("/api/feedback/recent?page=second_brain")).json()
            assert recent["page"] == "second_brain" and recent["rows"][0]["status"] == "filed" and recent["rows"][0]["kind"] == "bug"
            row = (await c.get("/api/feedback/list")).json()[0]
            assert row["id"] == fid and row["text"] == "forget should also clear the inspector" and row["item_id"] == "7" and row["tags"] == ["second_brain", "bug", "inspector"]
            assert row["draft"].startswith("# Forget") and row["ref"] is None and row["job_id"]
            args = calls[0]["args"]
            assert "otto-read" in args[args.index("--mcp-config") + 1] and "--no-session-persistence" in args
            assert args[args.index("--max-turns") + 1] == str(config.feedback.max_turns)
            assert "mcp__otto-read__docs_read" in args[args.index("--allowedTools") + 1]
            prompt = procs[0].stdin.data.decode("utf-8")
            assert f"Feedback #{fid}" in prompt and "buy sqlite book" in prompt
            assert app.state.store.one("SELECT budgeted FROM app_llm_runs WHERE module = 'feedback'")["budgeted"] == 0
            ev = (await c.get("/api/events?module=second_brain")).json()["events"]
            assert [e["verb"] for e in ev][:2] == ["filed", "feedback"]
            # a reply that is not JSON fails the note; retry requeues it
            app.state.claude.spawn = spying([NOT_JSON])
            r = await c.post("/api/feedback/action/add", json={"page": "activity", "text": "show job durations"})
            bad = r.json()["id"]
            await settle(app)
            recent = (await c.get("/api/feedback/recent?page=activity")).json()
            assert recent["rows"][0]["status"] == "failed" and "JSON" in recent["rows"][0]["error"]
            assert [r["id"] for r in (await c.get("/api/feedback/recent?page=second_brain")).json()["rows"]] == [fid]   # never another page's notes
            assert (await c.post("/api/feedback/action/retry", json={"id": fid})).status_code == 409
            app.state.claude.spawn = spying([FILED])
            assert (await c.post("/api/feedback/action/retry", json={"id": bad})).status_code == 200
            await settle(app)
            assert (await c.get("/api/feedback/recent?page=activity")).json()["rows"][0]["status"] == "filed"
            # a note sent during a drain is refused before any row exists
            app.state.runner.draining = True
            assert (await c.post("/api/feedback/action/add", json={"page": "second_brain", "text": "late"})).status_code == 503
            assert app.state.store.scalar("SELECT COUNT(*) FROM feedback_items") == 2
        await app.state.runner.drain(1)
        app.state.store.close()
        # a note whose filing job died with the last daemon reads failed at the next boot, so retry is offered
        app = build(config)
        st = app.state
        st.store.execute("INSERT INTO feedback_items(created_at, page, text) VALUES ('2026-09-13T00:00:00+00:00', 'second_brain', 'orphan')")
        st.store.close()
        app = build(config)
        row = app.state.store.one("SELECT status, error FROM feedback_items WHERE text = 'orphan'")
        assert row == {"status": "failed", "error": "daemon restarted"}
        app.state.store.close()

    run(main())
