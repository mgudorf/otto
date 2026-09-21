"""Routes through the real app: second_brain end to end on the one page, the feed, the one verb route, the one
agent, System's routines, and sessions with a fake CLI."""

import json
from pathlib import Path

import httpx

from app.config import ROOT
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


def row(module: str, facet: str, rid, title: str, when: str | None, **extra) -> dict:
    """One ROW as a module hands it over: the facet is its only fixed tag, the kind is its type."""
    return {"id": rid, "module": module, "title": title, "when": when, "fixed": [facet],
            "tags": list(extra.pop("tags", ())), "type": "note", "verbs": [["dismiss", "Dismiss"]], **extra}


def facet_module(name: str, facet: str | None, pending: list[dict], listed: list[dict]) -> Module:
    """A faceted module with both row hooks, as Newsfeed has: a queue that waits on the owner and the rows it lists."""
    return Module(
        manifest=Manifest(name=name, title=name.title(), hue="#d9915b", icon="", order=9, facet=facet),
        path=Path(__file__).parent,
        tasks={},
        router=None,
        schema=None,
        numbers=None,
        today=lambda store: list(listed),
        queue=lambda store: list(pending),
        item=None,
        context=None,
        register_tools=None,
        prompt=None,
        rows=lambda store, limit: list(listed)[:limit],
    )


def test_second_brain_end_to_end(config):
    async def main():
        app = build(config)
        await app.state.runner.start()
        async with client_for(app) as c:
            shell = (await c.get("/api/shell")).json()
            facets = {m["name"]: m["facet"] for m in shell["modules"]}
            assert facets["second_brain"] == "entry" and facets["home"] is None and shell["budget"]["max"] == config.nightly.max_sessions
            r = await c.post("/api/second_brain/action/capture", json={"kind": "note", "text": "buy sqlite book", "tags": ["reading"]})
            assert r.status_code == 200, r.text
            mid = r.json()["id"]
            link = (await c.post("/api/second_brain/action/capture", json={"kind": "link", "text": "https://example.com the site"})).json()["id"]
            # the feed is every module's rows: newest first, the facet the only fixed tag, the kind the type
            mine = [r for r in (await c.get("/api/feed?mode=recent")).json()["items"] if r["module"] == "second_brain"]
            assert [r["id"] for r in mine] == [link, mid]
            note = mine[1]
            assert note["fixed"] == ["entry"] and note["type"] == "note" and note["tags"] == ["note", "reading"]
            assert note["verbs"] == [["forget", "Forget"]] and note.get("waits") is None
            # the search bar narrows by typed text and by tag, over the same one list
            assert [r["id"] for r in (await c.get("/api/feed?mode=recent&q=SQLite")).json()["items"]] == [mid]
            assert [r["id"] for r in (await c.get("/api/feed?mode=recent&tags=reading")).json()["items"]] == [mid]
            assert (await c.get("/api/feed?mode=sideways")).status_code == 400
            item = (await c.get(f"/api/second_brain/item/{mid}")).json()
            assert item["tags"] == ["note", "reading"] and item["verbs"] == [["forget", "Forget"]]
            assert (await c.post("/api/second_brain/action/tag", json={"id": mid, "tags": ["books"]})).json()["tags"] == ["books", "reading"]
            numbers = (await c.get("/api/home/numbers")).json()
            second = next(n for n in numbers if n["module"] == "second_brain")
            assert second["value"] == 2 and second["facet"] == "entry"
            # one front door for every verb: the module runs it and says what happened
            said = (await c.post("/api/verb", json={"module": "second_brain", "id": mid, "verb": "forget"})).json()
            assert said == {"ok": True, "said": "forgot note: buy sqlite book", "removes": True}
            assert (await c.get(f"/api/second_brain/item/{mid}")).status_code == 404
            assert (await c.post("/api/verb", json={"module": "second_brain", "id": link, "verb": "vanish"})).status_code == 404
            ev = (await c.get("/api/events?module=second_brain")).json()
            assert [e["verb"] for e in ev["events"]][:2] == ["forgot", "tagged"]
            s = (await c.put("/api/settings", json={"ui.page_size": 20})).json()
            assert s["ui.page_size"] == 20
            assert (await c.put("/api/settings", json={"ui.page_size": 5})).status_code == 400
            assert (await c.put("/api/settings", json={"ui.start_page": "home"})).status_code == 400   # retired with the per-module pages
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
            assert (await c.get("/core.js")).headers["cache-control"] == "no-cache"
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


def test_otto_is_the_one_agent(config):
    """One drawer, not a pane per module: its tools, skills and prompt are the union of every enabled module's, its
    tabs are its own, and a module that brings no agent is still a 404."""
    calls = []

    async def main():
        app = build(config, spawn_fn=fake_spawn([INIT, TEXT, RESULT], calls))
        await app.state.runner.start()
        async with client_for(app) as c:
            pane = (await c.get("/api/session/otto")).json()
            assert pane["sessions"] == []
            assert {"Entry", "Email", "Database"} <= set(pane["context_label"].split(", "))
            assert {"recall", "triage", "nl-to-sql"} <= set(pane["agent"]["skills"])
            sid = (await c.post("/api/session/otto/send", json={"text": "what is waiting?"})).json()["session"]
            await settle(app)
            args = calls[0]["args"]
            allowed = set(args[args.index("--allowedTools") + 1].split(","))
            assert {"mcp__otto__second_brain_add", "mcp__otto__email_search", "mcp__otto__db_query"} <= allowed
            system = args[args.index("--system-prompt") + 1]
            assert "You are the Otto agent" in system and "# Current state" in system
            for name in ("second_brain", "email", "science"):
                assert (ROOT / "app" / "modules" / name / "agent.md").read_text("utf-8").splitlines()[0] in system
            assert [(t["id"], t["busy"]) for t in (await c.get("/api/session/otto")).json()["sessions"]] == [(sid, False)]
            assert app.state.store.scalar("SELECT module FROM app_sessions WHERE id = ?", (sid,)) == "otto"
            assert (await c.get("/api/session/system")).status_code == 404
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_session_rename_outranks_the_tagger(config):
    """F2 names a tab: the name comes back on the next read, and the tagger keeps it on the way out."""

    async def main():
        app = build(config, spawn_fn=fake_spawn([INIT, TEXT, RESULT]))
        await app.state.runner.start()
        async with client_for(app) as c:
            sid = (await c.post("/api/session/second_brain/send", json={"text": "anything about x?"})).json()["session"]
            await settle(app)
            r = await c.post(f"/api/session/second_brain/{sid}/title", json={"title": "the x thread"})
            assert r.status_code == 200, r.text
            assert r.json() == {"module": "second_brain", "id": sid, "title": "the x thread"}
            assert [t["label"] for t in (await c.get("/api/session/second_brain")).json()["sessions"]] == ["the x thread"]
            assert (await c.post(f"/api/session/second_brain/{sid}/title", json={"title": "  "})).status_code == 400
            assert (await c.post("/api/session/second_brain/nope/title", json={"title": "y"})).status_code == 404
            app.state.claude.spawn = fake_spawn([CLOSE])
            await c.post("/api/session/second_brain/send", json={"text": "/clear", "id": sid})
            await settle(app)
            row = app.state.store.one("SELECT * FROM app_sessions WHERE id = ?", (sid,))
            assert row["title"] == "the x thread" and json.loads(row["tags"]) == ["second_brain", "search"]
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_session_reopen_keeps_its_tags(config):
    """A closed tab opens again with its transcript, its tagged title and its tags, and the tagger does not run twice."""

    async def main():
        app = build(config, spawn_fn=fake_spawn([INIT, TEXT, RESULT]))
        await app.state.runner.start()
        async with client_for(app) as c:
            sid = (await c.post("/api/session/second_brain/send", json={"text": "anything about x?"})).json()["session"]
            await settle(app)
            app.state.claude.spawn = fake_spawn([CLOSE])
            await c.post("/api/session/second_brain/send", json={"text": "/clear", "id": sid})
            await settle(app)
            assert (await c.get("/api/session/second_brain")).json()["sessions"] == []
            r = await c.post(f"/api/session/second_brain/{sid}/reopen")
            assert r.status_code == 200, r.text
            back = r.json()
            assert back["session"]["closed_at"] is None and json.loads(back["session"]["tags"]) == ["second_brain", "search"]
            assert [t["role"] for t in back["turns"]] == ["user", "model"] and back["busy"] is False
            assert [(t["id"], t["label"]) for t in (await c.get("/api/session/second_brain")).json()["sessions"]] == [(sid, "Search for x")]
            assert (await c.post("/api/session/second_brain/nope/reopen")).status_code == 404
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


def test_feed_is_every_module_in_two_modes(config):
    """Priority is every queue, least patient first and re-ranked where it lands; Recent is every module's rows,
    newest first with the undated behind them. A module the owner turned off, and one with no facet, list nothing."""
    pending = [row("queued", "queued", 7, "a finding worth reading", "2026-09-08T09:00", waits=5),
               row("queued", "queued", 8, "another finding", "2026-09-08T08:00", waits=2)]
    listed = [row("queued", "queued", 9, "found this morning", "2026-09-08T07:00", tags=["science"]),
              row("queued", "queued", 10, "no moment of its own", None)]

    async def main():
        app = build(config)
        await app.state.runner.start()
        st = app.state
        st.registry.modules["queued"] = facet_module("queued", "queued", pending, listed)
        st.store.set_setting("modules.queued.enabled", True)
        home = st.registry.get("home")
        async with client_for(app) as c:
            await c.post("/api/second_brain/action/capture", json={"kind": "note", "text": "a note from today"})

            waiting = (await c.get("/api/feed?mode=priority")).json()["items"]
            assert [(r["id"], r["waits"]) for r in waiting] == [(8, 1), (7, 2)]
            assert waiting[0]["fixed"] == ["queued"] and waiting[0]["verbs"] == [["dismiss", "Dismiss"]]

            recent = (await c.get("/api/feed?mode=recent")).json()["items"]
            assert [r["id"] for r in recent if r["module"] == "queued"] == [9, 10]
            assert any(r["module"] == "second_brain" and r["fixed"] == ["entry"] for r in recent)
            assert [r["id"] for r in (await c.get("/api/feed?mode=recent&q=MORNING")).json()["items"]] == [9]
            assert [r["id"] for r in (await c.get("/api/feed?mode=recent&tags=science")).json()["items"]] == [9]
            assert [r["id"] for r in (await c.get("/api/feed?mode=recent&tags=queued")).json()["items"]] == [9, 10]

            text = home.context(st.store, st.registry)
            assert "Review: 2 waiting" in text
            assert "  - (queued 7) a finding worth reading" in text and "  - (queued 8) another finding" in text

            pending.clear()
            assert [r for r in (await c.get("/api/feed?mode=priority")).json()["items"] if r["module"] == "queued"] == []
            assert "Review: nothing waiting" in home.context(st.store, st.registry)

            pending.append(row("queued", "queued", 7, "back again", "2026-09-08T09:00", waits=1))
            st.store.set_setting("modules.queued.enabled", False)
            for mode in ("priority", "recent"):
                assert all(r["module"] != "queued" for r in (await c.get(f"/api/feed?mode={mode}")).json()["items"])
            assert "(queued " not in home.context(st.store, st.registry)

            # a module with no facet is backend only: it queues nothing and lists nothing
            quiet = facet_module("quiet", None, [row("quiet", "quiet", 11, "backend only", "2026-09-08T06:00")], [])
            st.registry.modules["quiet"] = quiet
            st.store.set_setting("modules.quiet.enabled", True)
            for mode in ("priority", "recent"):
                assert all(r["module"] != "quiet" for r in (await c.get(f"/api/feed?mode={mode}")).json()["items"])
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_system_lists_its_routines(config):
    """Every scheduled task is a row under the routine facet; one whose last run failed waits in Priority, and its
    verbs run through the one verb route."""

    async def main():
        app = build(config)
        await app.state.runner.start()
        st = app.state
        st.scheduler.sync_tasks()
        async with client_for(app) as c:
            mine = [r for r in (await c.get("/api/feed?mode=recent")).json()["items"] if r["module"] == "system"]
            beat = next(r for r in mine if r["id"] == "system.heartbeat")
            assert beat["fixed"] == ["routine"] and beat["type"] == "routine" and beat["title"] == "system.heartbeat"
            assert beat["when"] is None and beat["snip"] == "every 1 m" and beat["right"] == "every 1 m"
            assert beat["late"] is False and beat["paused"] is False
            assert beat["verbs"] == [["run", "Run now"], ["pause", "Pause"]]
            assert ["Every", "every 1 m"] in beat["kv"] and ["Last run", "never"] in beat["kv"]

            assert [r for r in (await c.get("/api/feed?mode=priority")).json()["items"] if r["module"] == "system"] == []
            st.store.execute("UPDATE app_tasks SET last_status = 'failed', last_run = ? WHERE name = 'system.heartbeat'", (now_iso(),))
            broken = [r for r in (await c.get("/api/feed?mode=priority")).json()["items"] if r["module"] == "system"]
            assert [(r["id"], r["waits"], r["right"], r["late"]) for r in broken] == [("system.heartbeat", 1, "failed", True)]

            said = (await c.post("/api/verb", json={"module": "system", "id": "system.heartbeat", "verb": "pause"})).json()
            assert said == {"ok": True, "said": "disabled system.heartbeat", "removes": False}
            assert st.store.scalar("SELECT enabled FROM app_tasks WHERE name = 'system.heartbeat'") == 0
            paused = next(r for r in (await c.get("/api/feed?mode=recent")).json()["items"] if r["id"] == "system.heartbeat")
            assert paused["paused"] is True and paused["verbs"] == [["run", "Run now"], ["resume", "Resume"]]
            assert (await c.post("/api/verb", json={"module": "system", "id": "system.heartbeat", "verb": "resume"})).status_code == 200
            assert st.store.scalar("SELECT enabled FROM app_tasks WHERE name = 'system.heartbeat'") == 1

            assert (await c.post("/api/verb", json={"module": "system", "id": "nope", "verb": "pause"})).status_code == 404
            assert (await c.post("/api/verb", json={"module": "system", "id": "system.heartbeat", "verb": "vanish"})).status_code == 404
            assert (await c.post("/api/verb", json={"module": "nope", "id": "x", "verb": "pause"})).status_code == 404
            assert (await c.post("/api/verb", json={"module": "home", "id": "x", "verb": "pause"})).status_code == 404   # home takes no verbs
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
            assert next(m for m in shell["modules"] if m["name"] == "feedback")["facet"] is None   # listed for hue and icon, it lists no rows
            assert (await c.post("/api/feedback/action/add", json={"page": "second_brain", "text": "  "})).status_code == 400
            r = await c.post("/api/feedback/action/add", json={"page": "second_brain", "text": "forget should also clear the inspector", "item": {"module": "second_brain", "id": 7, "text": "buy sqlite book"}})
            assert r.status_code == 200, r.text
            fid = r.json()["id"]
            await settle(app)
            assert (await c.get("/api/feedback/recent")).status_code == 422                    # the panel is per module; there is no module-less list
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
            r = await c.post("/api/feedback/action/add", json={"page": "otto", "text": "show job durations"})
            bad = r.json()["id"]
            await settle(app)
            recent = (await c.get("/api/feedback/recent?page=otto")).json()
            assert recent["rows"][0]["status"] == "failed" and "JSON" in recent["rows"][0]["error"]
            assert [r["id"] for r in (await c.get("/api/feedback/recent?page=second_brain")).json()["rows"]] == [fid]   # never another module's notes
            assert (await c.post("/api/feedback/action/retry", json={"id": fid})).status_code == 409
            app.state.claude.spawn = spying([FILED])
            assert (await c.post("/api/feedback/action/retry", json={"id": bad})).status_code == 200
            await settle(app)
            assert (await c.get("/api/feedback/recent?page=otto")).json()["rows"][0]["status"] == "filed"
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
