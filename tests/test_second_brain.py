"""Second Brain module: the suggest task offline, the task-only actions, and the read / write tool split."""

import dataclasses

from app.config import ROOT, SecondBrain
from app.daemon import build
from app.modules.second_brain import MANIFEST
from app.modules.second_brain.tasks import suggest
from app.modules.second_brain.tools import register
from app.runner import JobFailed, Runner
from app.store import now_iso
from tests.conftest import run
from tests.test_app import client_for

SECOND_BRAIN_SCHEMA = (ROOT / "app" / "modules" / "second_brain" / "schema.sql").read_text("utf-8")


class FakeClaude:
    """Stands in for app.claude: returns canned replies and keeps every prompt."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    async def run_task(self, ctx, prompt, tools=()):
        self.prompts.append(prompt)
        return self.replies.pop(0)


def capture(store, kind, text):
    ts = now_iso()
    return store.execute("INSERT INTO second_brain_items(kind, text, created_at, updated_at) VALUES (?, ?, ?, ?)", (kind, text, ts, ts)).lastrowid


async def run_suggest(store, config, claude):
    r = Runner(store, config, registry=None, claude=claude, max_concurrent=1)
    await r.start()
    job = r.submit("second_brain.suggest", "second_brain", "second_brain", "scheduled", suggest)
    try:
        return await job.done
    finally:
        await r.drain(1)


def test_suggest_inserts_once_and_reads_config(store, config):
    store.migrate(SECOND_BRAIN_SCHEMA)
    config = dataclasses.replace(config, second_brain=SecondBrain(suggest_lookback_days=7, suggest_max=1))
    m1 = capture(store, "task", "renew passport")
    capture(store, "note", "passport expires in march")
    reply = '```json\n[{"text": "Book a passport appointment", "item_ids": [%d]}, {"text": "Second one", "item_ids": []}]\n```' % m1
    claude = FakeClaude([reply, reply])

    assert run(run_suggest(store, config, claude)) == "1 new suggestion(s) from 1 proposed"
    rows = store.query("SELECT * FROM second_brain_suggestions")
    assert len(rows) == 1 and rows[0]["item_ids"] == f"[{m1}]" and rows[0]["status"] == "open"
    assert store.cursor("second_brain.suggest") is not None
    assert f"last {config.second_brain.suggest_lookback_days} days" in claude.prompts[0] and "at most 1" in claude.prompts[0]

    store.execute("UPDATE second_brain_suggestions SET status = 'dismissed'")
    assert run(run_suggest(store, config, claude)) == "0 new suggestion(s) from 1 proposed"
    assert store.scalar("SELECT COUNT(*) FROM second_brain_suggestions") == 1
    assert "- Book a passport appointment" in claude.prompts[1], "dismissed suggestions stay in the never-repeat list"
    assert store.one("SELECT status FROM app_jobs ORDER BY id DESC LIMIT 1")["status"] == "done"


def test_suggest_skips_without_recent_items(store, config):
    store.migrate(SECOND_BRAIN_SCHEMA)
    claude = FakeClaude([])
    run(run_suggest(store, config, claude))
    assert claude.prompts == []
    job = store.one("SELECT * FROM app_jobs")
    assert job["status"] == "skipped" and "no items" in job["result"]


def test_done_and_suggestion_actions(config):
    async def main():
        app = build(config)
        await app.state.runner.start()
        store = app.state.store
        async with client_for(app) as c:
            mid = (await c.post("/api/second_brain/action/capture", json={"kind": "task", "text": "call the bank"})).json()["id"]
            item = (await c.get(f"/api/second_brain/item/{mid}")).json()
            assert item["actions"][0] == {"verb": "done", "label": "Done", "primary": True}
            assert (await c.post("/api/second_brain/action/done", json={"id": mid})).json() == {"id": mid}
            item = (await c.get(f"/api/second_brain/item/{mid}")).json()
            assert item["done_at"] and item["actions"][0]["verb"] == "forget"
            left = (await c.get("/api/second_brain/left?chip=Tasks")).json()
            assert left["groups"][0]["rows"][0]["done"] is True

            # A suggestion carries its own row id, "s<n>", so it never collides with an item of the same number.
            sid = store.execute(
                "INSERT INTO second_brain_suggestions(text, item_ids, created_at) VALUES (?, ?, ?)", ("call them today", f"[{mid}]", now_iso())
            ).lastrowid
            row = f"s{sid}"
            assert (await c.get("/api/second_brain/blank")).json()["suggestions"][0]["id"] == row
            assert [r["id"] for g in (await c.get("/api/home/left")).json()["groups"] if g["label"] == "Review" for r in g["rows"]] == [row]
            sug = (await c.get(f"/api/second_brain/item/{row}")).json()
            assert sug["kind"] == "suggestion" and [a["verb"] for a in sug["actions"]] == ["accept", "dismiss"]
            assert all(a["removes"] for a in sug["actions"])
            r = await c.post("/api/second_brain/action/accept", json={"id": row})
            assert r.json() == {"id": row, "status": "accepted"}
            assert (await c.get("/api/second_brain/blank")).json()["suggestions"] == []
            assert [a["verb"] for a in (await c.get(f"/api/second_brain/item/{row}")).json()["actions"]] == []
            assert all(g["label"] != "Review" for g in (await c.get("/api/home/left")).json()["groups"])
            assert (await c.post("/api/second_brain/action/dismiss", json={"id": mid})).status_code == 404     # an item is not a suggestion
            assert (await c.get("/api/second_brain/item/nope")).status_code == 404
            verbs = [e["verb"] for e in (await c.get("/api/events?module=second_brain")).json()["events"]]
            assert verbs[:2] == ["accepted", "completed"]
            missing = await c.post("/api/second_brain/action/done", json={"id": mid + 999})
            assert missing.status_code == 404, missing.text
        await app.state.runner.drain(1)
        store.close()

    run(main())


class RecordingServer:
    def __init__(self):
        self.names = set()

    def tool(self):
        def deco(fn):
            self.names.add(fn.__name__)
            return fn

        return deco


def test_second_brain_tool_split(store, config):
    store.migrate(SECOND_BRAIN_SCHEMA)
    read, full = RecordingServer(), RecordingServer()
    register(read, full, store, config)
    agent = MANIFEST.agent
    assert read.names == set(agent.read_tools)
    assert full.names == set(agent.read_tools) | set(agent.write_tools)
    assert not set(agent.read_tools) & set(agent.write_tools)
