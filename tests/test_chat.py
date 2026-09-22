"""Chat module: conversations through the real app with a fake CLI, the title after the first turn, attachments, the replay of a
lost transcript, the one agent every conversation belongs to, and the feed those conversations reach."""

import dataclasses
import json

from app.config import Chat
from app.daemon import build
from app.modules.chat.routes import rows as rows_hook
from app.modules.graph import build as graph_build
from app.modules.newsfeed import tasks as feed_tasks
from app.modules.system.routes import queue as routine_queue, rows as routine_rows
from app.runner import JobFailed
from app.store import now_iso
from tests.conftest import FakeProc, run
from tests.test_app import client_for, settle

INIT = json.dumps({"type": "system", "subtype": "init", "session_id": "c1", "tools": ["Write", "WebSearch"]})
WRITE = json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Write", "input": {"file_path": "notes.md", "content": "x"}}]}})
WRITE_OK = json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "File created"}]}})
DELTA = json.dumps({"type": "stream_event", "event": {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "Saved it "}}})
TEXT = json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Saved it as notes.md."}]}})
RESULT = json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "Saved it as notes.md.", "session_id": "c1", "num_turns": 2})
TAG = json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": '{"title": "Notes about x", "tags": ["notes", "chat"]}', "session_id": "c2"})
LOST = json.dumps({"type": "result", "subtype": "error_during_execution", "is_error": True, "num_turns": 0, "session_id": "c1"})
LOST_ERR = "No conversation found with session ID: c1"
TURN = [INIT, WRITE, WRITE_OK, DELTA, TEXT, RESULT]


def sequence(specs, calls, procs=None):
    """Each spawn takes the next (stdout lines, stderr lines) pair; the last pair repeats."""
    specs = list(specs)

    async def spawn(args, cwd, env):
        lines, err = specs.pop(0) if len(specs) > 1 else specs[0]
        calls.append({"args": args, "cwd": cwd, "env": env})
        proc = FakeProc(list(lines), list(err))
        if procs is not None:
            procs.append(proc)
        return proc

    return spawn


def test_chat_conversation_lifecycle(config):
    calls, procs = [], []

    async def main():
        app = build(config, spawn_fn=sequence([(TURN, ()), ([TAG], ()), (TURN, ())], calls, procs))
        await app.state.runner.start()
        st = app.state
        async with client_for(app) as c:
            shell = (await c.get("/api/shell")).json()
            facets = {m["name"]: m["facet"] for m in shell["modules"]}
            chat = next(m for m in shell["modules"] if m["name"] == "chat")
            assert chat["facet"] == "chats" and chat["agent"]["skills"] == ["web", "files"]
            assert facets["home"] is None and facets["graph"] is None   # a backend module carries no facet and lists no rows
            assert (await c.post("/api/chat/send", json={"text": "  "})).status_code == 400
            r = await c.post("/api/chat/send", json={"text": "save a note about x"})
            assert r.status_code == 200, r.text
            sid = r.json()["id"]
            await settle(app)
            item = (await c.get(f"/api/chat/item/{sid}")).json()
            # the page shows the tail as [role, text]; the whole transcript, tool turns and all, stays on the session route
            assert item["turns"] == [["user", "save a note about x"], ["model", "Saved it as notes.md."]]
            said = (await c.get(f"/api/session/chat/{sid}")).json()["turns"]
            assert [(t["role"], t.get("tool"), t.get("status")) for t in said] == [("user", None, None), ("tool", "Write", "done"), ("model", None, None)]
            assert item["title"] == "Notes about x" and item["tags"] == ["notes", "chat"] and item["busy"] is False
            row = st.store.one("SELECT * FROM app_sessions WHERE id = ?", (sid,))
            assert row["module"] == "chat" and row["cli_started"] == 1 and row["closed_at"] is None
            # the turn: a new CLI session with Write and Edit, no Otto tools, partial messages on
            args = calls[0]["args"]
            assert "--session-id" in args and "--include-partial-messages" in args and "--restricted" in args
            builtins = args[args.index("--tools") + 1].split(",")
            assert {"Read", "WebSearch", "Write", "Edit"} <= set(builtins) and "Bash" not in builtins
            allowed = args[args.index("--allowedTools") + 1]
            assert "mcp__otto__" not in allowed and "Write" in allowed
            folder = config.data.workspace / "chat" / sid
            prompt = procs[0].stdin.data.decode("utf-8")
            assert prompt.startswith("save a note about x") and f"Conversation folder: {folder}" in prompt and folder.is_dir()
            # the tagger: a read-only oneshot after the first turn, no close
            tag_args = calls[1]["args"]
            assert "--no-session-persistence" in tag_args and tag_args[tag_args.index("--max-turns") + 1] == "2"
            assert "Write" not in tag_args[tag_args.index("--tools") + 1] and "--include-partial-messages" not in tag_args
            assert "tagged" in [e["verb"] for e in (await c.get("/api/events?module=chat")).json()["events"]]
            with st.store.tx() as conn:
                graph_build.rebuild(conn)
            assert st.store.one("SELECT sessions FROM graph_nodes WHERE tag = 'notes'")["sessions"] == 1
            # a second turn resumes and queues no second tag job
            await c.post("/api/chat/send", json={"id": sid, "text": "and add a heading"})
            await settle(app)
            assert "--resume" in calls[2]["args"] and st.store.scalar("SELECT COUNT(*) FROM app_jobs WHERE task = 'chat.tag'") == 1
            # every conversation has its own resource; the list orders by last activity and searches the turns
            sid2 = (await c.post("/api/chat/send", json={"text": "something else"})).json()["id"]
            await settle(app)
            resources = {j["resource"] for j in st.store.query("SELECT resource FROM app_jobs WHERE task = 'chat.turn'")}
            assert resources == {f"session:{sid}", f"session:{sid2}"}
            left = (await c.get("/api/chat/left")).json()
            assert left["more"] is False and [r["title"] for r in left["groups"][0]["rows"]] == ["something else", "Notes about x"]
            tagged = left["groups"][0]["rows"][1]
            assert tagged == {
                "id": sid, "module": "chat", "title": "Notes about x", "when": tagged["when"],
                "fixed": ["chats"], "tags": ["notes", "chat"], "type": "conversation",
                "verbs": [["reopen", "Reopen"], ["delete", "Delete"]],
            }
            assert [r["id"] for r in rows_hook(st.store, 10)] == [sid2, sid]   # the ROWs /api/items and the feed read
            assert [r["id"] for r in (await c.get("/api/chat/left?query=heading")).json()["groups"][0]["rows"]] == [sid]
            assert (await c.get("/api/chat/left?query=zzz")).json()["groups"] == []
            n = next(n for n in (await c.get("/api/home/numbers")).json() if n["module"] == "chat")
            assert n["value"] == 2 and n["label"] == "conversations"
            # delete is the only removal: row, turns and folder, and the browser asks for it through the one front door
            assert (await c.post("/api/verb", json={"module": "chat", "id": sid2, "verb": "nope"})).status_code == 404
            assert (await c.post("/api/verb", json={"module": "nope", "id": sid2, "verb": "delete"})).status_code == 404
            r = await c.post("/api/verb", json={"module": "chat", "id": sid2, "verb": "delete"})
            assert r.status_code == 200 and r.json() == {"ok": True, "said": "deleted something else", "removes": True}, r.text
            assert st.store.one("SELECT id FROM app_sessions WHERE id = ?", (sid2,)) is None
            assert st.store.scalar("SELECT COUNT(*) FROM app_session_turns WHERE session_id = ?", (sid2,)) == 0
            assert not (config.data.workspace / "chat" / sid2).exists() and len((await c.get("/api/chat/left")).json()["groups"][0]["rows"]) == 1
            assert (await c.get(f"/api/chat/item/{sid2}")).status_code == 404
            # a scheduled run through the same seam never gets the write built-ins
            st.claude.config = dataclasses.replace(config, nightly=dataclasses.replace(config.nightly, window="00:00-23:59"))
            st.store.execute(
                "INSERT INTO newsfeed_searches(name, prompt, every_days, cap, created_at, next_run) VALUES ('x', 'find x', 1, 3, '2026-09-01T00:00:00+00:00', '2000-01-01')"
            )
            job = st.runner.submit("newsfeed.run", "newsfeed", "newsfeed", "scheduled", feed_tasks.run)
            try:
                await job.done
            except JobFailed:
                pass   # the fake's reply is not a JSON array; the args are what matters
            task_args = calls[-1]["args"]
            assert task_args[task_args.index("--tools") + 1] == "Read,Grep,Glob,WebSearch,WebFetch" and "--include-partial-messages" not in task_args
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_chat_replays_lost_transcript(config):
    small = dataclasses.replace(config, chat=Chat(upload_max_mb=1, replay_chars=40))
    calls, procs = [], []

    async def main():
        app = build(small, spawn_fn=sequence([(TURN, ()), ([TAG], ()), ([LOST], [LOST_ERR]), (TURN, ())], calls, procs))
        await app.state.runner.start()
        st = app.state
        async with client_for(app) as c:
            sid = (await c.post("/api/chat/send", json={"text": "save a note about x"})).json()["id"]
            await settle(app)
            assert (await c.post("/api/chat/send", json={"id": sid, "text": "and now?"})).status_code == 200
            await settle(app)
            turns = (await c.get(f"/api/session/chat/{sid}")).json()["turns"]
            assert [t["role"] for t in turns] == ["user", "tool", "model", "user", "system", "tool", "model"]
            assert turns[4]["text"] == "resumed from Otto's record"
            # the page's excerpt is the tail of what the two of them said; the replay note is bookkeeping and stays out of it
            excerpt = (await c.get(f"/api/chat/item/{sid}")).json()["turns"]
            assert excerpt[-2:] == [["user", "and now?"], ["model", "Saved it as notes.md."]] and all(t[0] in ("user", "model") for t in excerpt)
            assert "--resume" in calls[2]["args"] and "--session-id" in calls[3]["args"]
            prompt = procs[3].stdin.data.decode("utf-8")
            transcript = "user: save a note about x\nmodel: Saved it as notes.md."
            assert prompt.startswith("Earlier in this conversation") and transcript[-40:] in prompt and transcript[:20] not in prompt
            assert prompt.rstrip().endswith(")") and "and now?" in prompt
            row = st.store.one("SELECT cli_started, closed_at FROM app_sessions WHERE id = ?", (sid,))
            assert row["cli_started"] == 1 and row["closed_at"] is None
            assert st.store.scalar("SELECT COUNT(*) FROM app_jobs WHERE task = 'chat.turn' AND status = 'done'") == 2
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_chat_upload_and_files(config):
    small = dataclasses.replace(config, chat=Chat(upload_max_mb=1, replay_chars=1000))
    calls, procs = [], []

    async def main():
        app = build(small, spawn_fn=sequence([(TURN, ())], calls, procs))
        await app.state.runner.start()
        st = app.state
        async with client_for(app) as c:
            sid = (await c.post("/api/chat/new")).json()["id"]
            folder = small.data.workspace / "chat" / sid
            assert folder.is_dir()
            r = await c.post(f"/api/chat/upload/{sid}", files={"file": ("notes.txt", b"hello", "text/plain")})
            assert r.status_code == 200 and r.json() == {"name": "notes.txt", "bytes": 5}
            assert (folder / "notes.txt").read_bytes() == b"hello"
            assert (await c.post(f"/api/chat/upload/{sid}", files={"file": ("notes.txt", b"again", "text/plain")})).json()["name"] == "notes (2).txt"
            assert (await c.post(f"/api/chat/upload/{sid}", files={"file": ("sub/evil.txt", b"x", "text/plain")})).status_code == 400
            assert (await c.post(f"/api/chat/upload/{sid}", files={"file": ("big.bin", b"x" * (1024 * 1024 + 1), "application/octet-stream")})).status_code == 413
            assert (await c.post("/api/chat/upload/nope", files={"file": ("a.txt", b"x", "text/plain")})).status_code == 404
            assert {f["name"] for f in (await c.get(f"/api/chat/files/{sid}")).json()} == {"notes.txt", "notes (2).txt"}
            r = await c.get(f"/api/chat/file/{sid}/notes.txt")
            assert r.status_code == 200 and r.content == b"hello"
            assert (await c.get(f"/api/chat/file/{sid}/missing.txt")).status_code == 404
            assert (await c.post("/api/chat/send", json={"id": sid, "text": "read it", "files": ["missing.txt"]})).status_code == 400
            assert (await c.post("/api/chat/send", json={"id": sid, "text": "read it", "files": ["notes.txt"]})).status_code == 200
            await settle(app)
            prompt = procs[0].stdin.data.decode("utf-8")
            assert "Attached, read them with the Read tool: " + str(folder / "notes.txt") in prompt
            item = (await c.get(f"/api/chat/item/{sid}")).json()
            assert item["title"] == "read it" and {f["name"] for f in item["files"]} == {"notes.txt", "notes (2).txt"}   # the tagger's reply was not JSON: the first line stands
            assert "attached" in [e["verb"] for e in (await c.get("/api/events?module=chat")).json()["events"]]
            assert (await c.get("/api/chat/item/nope")).status_code == 404
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_otto_is_every_agent_at_once(config):
    """The drawer talks to one agent: every enabled module's tools and prompt behind the session module `otto`, and what it
    says lands in the chats facet like any other conversation."""
    calls, procs = [], []

    async def main():
        app = build(config, spawn_fn=sequence([(TURN, ())], calls, procs))
        await app.state.runner.start()
        st = app.state
        async with client_for(app) as c:
            pane = (await c.get("/api/session/otto")).json()
            assert pane["sessions"] == [] and pane["agent"]["cmd"] == "claude · otto"
            assert {"web", "files", "triage", "quiz"} <= set(pane["agent"]["skills"])
            assert "Email" in pane["context_label"] and "Entry" in pane["context_label"]
            r = await c.post("/api/session/otto/send", json={"text": "what waits?"})
            assert r.status_code == 200, r.text
            sid = r.json()["session"]
            await settle(app)
            args = calls[0]["args"]
            allowed = args[args.index("--allowedTools") + 1]
            assert {"mcp__otto__email_search", "mcp__otto__education_grade", "mcp__otto__second_brain_add"} <= set(allowed.split(","))
            prompt = args[args.index("--system-prompt") + 1]
            agents = [m for m in st.registry.ordered() if m.manifest.agent and m.prompt]
            assert len(agents) > 1 and all(m.prompt.strip() in prompt for m in agents)
            # every conversation is a conversation, whichever agent held it
            assert [x["id"] for x in rows_hook(st.store, 10)] == [sid]
            row = (await c.get(f"/api/chat/item/{sid}")).json()
            assert row["fixed"] == ["chats"] and row["title"] == "what waits?" and row["turns"][0] == ["user", "what waits?"]
            assert [x["id"] for x in (await c.get("/api/session/otto")).json()["sessions"]] == [sid]
            assert (await c.get("/api/session/nope")).status_code == 404
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_feed_recent_and_system_routines(config):
    """The feed is the one list: Recent merges every faceted module newest first, undated rows behind them. System's
    scheduled tasks are rows there like any other, run and paused through the same front door."""
    calls, procs = [], []

    async def main():
        app = build(config, spawn_fn=sequence([(TURN, ())], calls, procs))
        await app.state.runner.start()
        st = app.state
        st.scheduler.sync_tasks()       # the clock's own table is what System lists
        async with client_for(app) as c:
            sid = (await c.post("/api/chat/send", json={"text": "save a note about x"})).json()["id"]
            await settle(app)
            items = (await c.get("/api/feed?mode=recent")).json()["items"]
            assert all(len(x["fixed"]) == 1 and x["type"] and x["verbs"] is not None for x in items)
            assert [x["when"] is not None for x in items] == sorted((x["when"] is not None for x in items), reverse=True)
            assert next(x for x in items if x["module"] == "chat")["id"] == sid
            routines = [x for x in items if x["fixed"] == ["routine"]]
            assert {x["id"] for x in routines} == {r["name"] for r in st.store.query("SELECT name FROM app_tasks")}
            hb = next(x for x in routines if x["id"] == "system.heartbeat")
            assert hb == {
                "id": "system.heartbeat", "module": "system", "title": "system.heartbeat", "when": None,
                "fixed": ["routine"], "tags": [], "type": "routine", "snip": "every 1 m", "late": False, "paused": False,
                "right": "every 1 m", "kv": [["Every", "every 1 m"], ["Last run", "never"], ["Last result", "nothing said"]],
                "verbs": [["run", "Run now"], ["pause", "Pause"]],
            }
            prune = next(x for x in routines if x["id"] == "system.prune_sessions")
            assert prune["kv"][-1] == ["Resource", "sessions"] and prune["snip"] == "every 1 d"
            counts = (await c.get("/api/home/numbers")).json()   # the brand menu counts the facets and nothing else
            assert all(n["facet"] for n in counts) and not {"home", "graph", "feedback"} & {n["module"] for n in counts}
            # a tag typed in the search bar and the words typed with it narrow the same list
            assert [x["id"] for x in (await c.get("/api/feed?mode=recent&tags=routine")).json()["items"]] == [x["id"] for x in routines]
            assert (await c.get("/api/feed?mode=recent&tags=chats&q=save a note")).json()["items"][0]["id"] == sid
            assert (await c.get("/api/feed?mode=recent&tags=chats&q=zzz")).json()["items"] == []
            assert (await c.get("/api/feed?mode=sideways")).status_code == 400

            # pause, resume and run: the verbs the routine offers, through the one front door
            assert (await c.post("/api/verb", json={"module": "system", "id": "system.heartbeat", "verb": "pause"})).json() == {
                "ok": True, "said": "disabled system.heartbeat", "removes": False}
            paused = next(x for x in routine_rows(st.store) if x["id"] == "system.heartbeat")
            assert paused["paused"] is True and paused["right"] == "paused" and paused["verbs"][1] == ["resume", "Resume"]
            assert (await c.post("/api/verb", json={"module": "system", "id": "system.heartbeat", "verb": "resume"})).json()["said"] == "enabled system.heartbeat"
            assert (await c.post("/api/verb", json={"module": "system", "id": "nope", "verb": "run"})).status_code == 404
            assert (await c.post("/api/verb", json={"module": "system", "id": "system.heartbeat", "verb": "run"})).json()["said"] == "run"
            await settle(app)
            assert st.store.one("SELECT status FROM app_jobs WHERE task = 'system.heartbeat'")["status"] == "done"

            # only what broke waits on the owner, and Priority ranks it
            assert routine_queue(st.store) == []
            st.store.execute("UPDATE app_tasks SET last_status = 'failed', last_run = ? WHERE name = 'system.prune_sessions'", (now_iso(),))
            [broken] = routine_queue(st.store)
            assert broken["id"] == "system.prune_sessions" and broken["late"] is True and broken["right"] == "failed" and broken["waits"] == 0
            queued = (await c.get("/api/feed?mode=priority")).json()["items"]
            assert [x["id"] for x in queued if x["module"] == "system"] == ["system.prune_sessions"]
            assert all(x["waits"] == rank for rank, x in enumerate(queued, 1))
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())
