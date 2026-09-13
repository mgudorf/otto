"""Web Search module: the topic tools, decisions from Home end to end, and the capped, idempotent nightly run."""

import json
from pathlib import Path

import pytest

from app.daemon import build
from app.modules.web_search import tasks, tools
from app.runner import Skipped
from tests.conftest import run
from tests.test_app import client_for


class FakeServer:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


def _seed_finding(store, i: int, ts: str) -> int:
    cur = store.execute(
        "INSERT INTO web_search_findings(topic_id, kind, title, url, summary, found_at) VALUES (1, 'work', ?, ?, 'why', ?)",
        (f"finding {i}", f"https://x.example/{i}", ts),
    )
    return cur.lastrowid


def test_decisions_and_topic_tools(config):
    src = (Path(tasks.__file__).parent / "routes.py").read_text("utf-8")
    assert "claude" not in src

    async def main():
        app = build(config)
        await app.state.runner.start()
        store = app.state.store
        async with client_for(app) as c:
            shell = (await c.get("/api/shell")).json()
            ws = next(m for m in shell["modules"] if m["name"] == "web_search")
            assert ws["page"] is False and ws["agent"] is None and ws["hue"] == "#d9915b" and ws["tasks"] == 1
            # topics are the Chat agent's tools; the page and its routes are gone
            read, full = FakeServer(), FakeServer()
            tools.register(read, full, store, config)
            assert set(read.tools) == {"search_findings", "search_topics"}
            assert set(full.tools) == {"search_findings", "search_topics", "search_topic_add", "search_topic_remove"}
            tid = full.tools["search_topic_add"]("work", "time series foundation models")["id"]
            assert "error" in full.tools["search_topic_add"]("work", "time series foundation models")
            assert "error" in full.tools["search_topic_add"]("other", "x") and "error" in full.tools["search_topic_add"]("work", "  ")
            assert [t["id"] for t in read.tools["search_topics"]()] == [tid]
            for gone in ("/api/web_search/left", "/api/web_search/blank"):
                assert (await c.get(gone)).status_code == 404
            assert (await c.post("/api/web_search/action/topic_add", json={"kind": "work", "text": "y"})).status_code == 404
            from app.store import now_iso

            f1, f2 = _seed_finding(store, 1, now_iso()), _seed_finding(store, 2, now_iso())
            item = (await c.get(f"/api/web_search/item/{f1}")).json()
            assert [a["verb"] for a in item["actions"]] == ["agree", "disagree", "link"] and item["actions"][-1]["href"] == "https://x.example/1"
            r = await c.post("/api/web_search/action/agree", json={"id": f1})
            assert r.json() == {"id": f1, "status": "agreed"}
            assert (await c.post("/api/web_search/action/disagree", json={"id": f1})).status_code == 409
            row = store.one("SELECT status, decided_at FROM web_search_findings WHERE id = ?", (f1,))
            assert row["status"] == "agreed" and row["decided_at"]
            assert [a["verb"] for a in (await c.get(f"/api/web_search/item/{f1}")).json()["actions"]] == ["link"]
            assert [f["id"] for f in read.tools["search_findings"]("finding 2")] == [f2]
            assert [f["id"] for f in read.tools["search_findings"]("", status="agreed")] == [f1]
            # Home still carries the module without a page: the Review group and the number, neither able to navigate
            home = (await c.get("/api/home/left")).json()
            review = next(g for g in home["groups"] if g["module"] == "web_search" and g["label"] == "Review")
            assert review["count"] == 1 and review["page"] is False and [r["id"] for r in review["rows"]] == [f2]
            assert {g["module"]: g["count"] for g in home["groups"]}["web_search"] == 2
            numbers = (await c.get("/api/home/numbers")).json()
            n = next(n for n in numbers if n["module"] == "web_search")
            assert n["value"] == 1 and n["label"] == "to review" and n["page"] is False
            from app.modules.web_search.routes import queue

            assert [r["id"] for r in queue(store)] == [f2]
            # Turned down: off Home's Today as well as the queue, still in the table so the nightly run never brings it back
            assert (await c.post("/api/web_search/action/disagree", json={"id": f2})).json()["status"] == "disagreed"
            home = (await c.get("/api/home/left")).json()
            assert {g["module"]: g["count"] for g in home["groups"]}["web_search"] == 1
            assert [r["id"] for g in home["groups"] if g["module"] == "web_search" for r in g["rows"]] == [f1]
            assert [f["id"] for f in read.tools["search_findings"]("", status="disagreed")] == [f2]
            assert full.tools["search_topic_remove"](tid) == {"id": tid} and "error" in full.tools["search_topic_remove"](tid)
            assert read.tools["search_topics"]() == []
            ev = (await c.get("/api/events?module=web_search")).json()
            assert [e["verb"] for e in ev["events"]][:4] == ["topic removed", "disagreed", "agreed", "topic added"]
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


class FakeCtx:
    def __init__(self, store, config, reply: str | None = None):
        self.store, self.config, self.reply = store, config, reply
        self.prompts: list[str] = []
        self.events: list[tuple[str, str]] = []

    def commit(self, cursor=None):
        from contextlib import contextmanager

        @contextmanager
        def _tx():
            with self.store.tx() as conn:
                yield conn
                if cursor:
                    conn.execute("INSERT INTO app_cursors(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", cursor)

        return _tx()

    def event(self, verb, text, ref=None):
        self.events.append((verb, text))

    async def run_task(self, prompt, tools=()):
        self.prompts.append(prompt)
        assert tools == ()
        if self.reply is None:
            raise AssertionError("run_task must not be called")
        return self.reply


@pytest.fixture
def ws_store(store):
    from app.modules import Registry

    reg = Registry()
    reg.load()
    store.migrate(reg.get("web_search").schema)
    return store


def test_nightly_skips_without_topics(ws_store, config):
    ctx = FakeCtx(ws_store, config)
    assert isinstance(run(tasks.nightly(ctx)), Skipped) and ctx.prompts == []


def test_nightly_inserts_and_is_idempotent(ws_store, config):
    assert config.web_search.max_findings == 3
    ts = "2026-09-07T00:00:00+00:00"
    ws_store.execute("INSERT INTO web_search_topics(kind, text, created_at) VALUES ('money', 'grid storage legislation', ?)", (ts,))
    ws_store.execute("INSERT INTO web_search_topics(kind, text, created_at) VALUES ('learn', 'causal inference', ?)", (ts,))
    items = [{"topic_id": 1 + i % 2, "title": f"page {i}", "url": f"https://x.example/{i}", "summary": "matters"} for i in range(4)]
    items.insert(1, dict(items[0]))                                   # duplicate url
    items.append({"topic_id": 9, "title": "unknown topic", "url": "https://x.example/9", "summary": ""})
    items.append({"topic_id": 1, "title": "", "url": "https://x.example/blank", "summary": ""})
    ctx = FakeCtx(ws_store, config, "```json\n" + json.dumps(items) + "\n```")
    assert run(tasks.nightly(ctx)) == "3 new finding(s) from 7 proposed"
    assert "grid storage legislation" in ctx.prompts[0] and "up to 3" in ctx.prompts[0]
    stored = ws_store.query("SELECT topic_id, kind, url, status FROM web_search_findings ORDER BY id")
    assert [r["url"] for r in stored] == ["https://x.example/0", "https://x.example/1", "https://x.example/2"]
    assert [r["kind"] for r in stored] == ["money", "learn", "money"] and stored[0]["status"] == "open"
    assert ws_store.cursor("web_search.nightly") is not None
    assert [e[0] for e in ctx.events] == ["found"] * 3
    again = FakeCtx(ws_store, config, json.dumps(items))
    assert run(tasks.nightly(again)) == "1 new finding(s) from 7 proposed"
    assert "https://x.example/0" in again.prompts[0]
    assert ws_store.scalar("SELECT COUNT(*) FROM web_search_findings") == 4
