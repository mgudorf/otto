"""Newsfeed: entries and searches end to end, the agent's creation tools, the capped, dated, idempotent nightly run with
follow-ups, and the one-time conversion of the Business, Social and Search rows."""

import json
import sqlite3
from datetime import date, timedelta

import pytest

from app.daemon import build
from app.modules.newsfeed import migrate, tasks, tools
from app.runner import Skipped
from tests.conftest import run
from tests.test_app import client_for

TS = "2026-09-07T00:00:00+00:00"


def _day(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


def _search(store, name="jobs", tags=("work",), every_days=1, cap=3, next_run=None) -> int:
    cur = store.execute(
        "INSERT INTO newsfeed_searches(name, prompt, every_days, cap, created_at, next_run) VALUES (?, ?, ?, ?, ?, ?)",
        (name, f"find {name}", every_days, cap, TS, next_run or _day(0)),
    )
    for t in tags:
        store.execute("INSERT INTO newsfeed_tags(kind, ref, tag) VALUES ('search', ?, ?)", (cur.lastrowid, t))
    return cur.lastrowid


def _entry(store, sid, text, url, status="open", starts_at=None, follow_up_at=None, found_at=TS) -> int:
    cur = store.execute(
        "INSERT INTO newsfeed_items(search_id, text, url, starts_at, follow_up_at, found_at, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (sid, text, url, starts_at, follow_up_at, found_at, status),
    )
    return cur.lastrowid


def test_newsfeed_end_to_end(config):
    async def main():
        app = build(config)
        await app.state.runner.start()
        store = app.state.store
        async with client_for(app) as c:
            shell = (await c.get("/api/shell")).json()
            feed = next(m for m in shell["modules"] if m["name"] == "newsfeed")
            assert feed["hue"] == "#D79EBB" and feed["agent"]["skills"] == ["recall", "searches", "add", "tag"]
            assert {m["name"] for m in shell["modules"]}.isdisjoint({"business", "social", "web_search"})
            assert (await c.get("/api/newsfeed/blank")).json()["searches"] == []

            sid = _search(store)
            a = _entry(store, sid, "Acme is hiring", "https://acme.example/jobs", found_at="2026-09-08T09:00:00+00:00")
            b = _entry(store, sid, "Board game night", "https://e.example/1", starts_at=f"{_day(3)}T19:00")
            store.execute("INSERT INTO newsfeed_tags(kind, ref, tag) VALUES ('item', ?, 'game')", (b,))

            left = (await c.get("/api/newsfeed/left")).json()
            assert left["chip"] == "All" and left["chips"] == ["All", "Open", "Accepted"]
            assert [r["id"] for g in left["groups"] for r in g["rows"]] == [a, b]
            rows = {r["id"]: r for g in left["groups"] for r in g["rows"]}
            assert rows[a]["title"] == "Acme is hiring" and rows[a]["status"] == "open" and "happens" not in rows[a]
            assert rows[a]["search"] == "jobs" and len(rows[a]["when"]) == 16                    # the day found, in the owner's clock
            assert rows[b]["happens"] == f"{_day(3)}T19:00" and rows[b]["fixed"] == ["game"] and rows[b]["tags"] == []
            assert (await c.post("/api/tags/add", json={"module": "newsfeed", "id": a, "tags": ["Remote"]})).json()["tags"] == ["remote"]
            assert [r["id"] for r in (await c.get("/api/items?tags=remote")).json()["items"]] == [a]   # the owner's tags, through the rows hook
            assert (await c.get("/api/newsfeed/left?query=game")).json()["groups"] != []      # a tag is searchable
            assert (await c.get("/api/newsfeed/left?query=acme")).json()["groups"] != []
            assert (await c.get("/api/newsfeed/left?query=%25")).json()["groups"] == []   # a wildcard is a letter like any other
            assert (await c.get("/api/newsfeed/left?limit=1")).json()["more"] is True     # a list cut short says so
            assert (await c.get("/api/newsfeed/left?chip=Accepted")).json()["groups"] == []

            item = (await c.get(f"/api/newsfeed/item/{a}")).json()
            assert item["kind"] == "entry" and item["search"] == "jobs" and [x["verb"] for x in item["actions"]] == ["accept", "dismiss", "link"]
            blank = (await c.get("/api/newsfeed/blank")).json()
            assert blank["open"] == 2 and blank["searches"][0]["id"] == f"s{sid}" and blank["searches"][0]["open"] == 2 and blank["searches"][0]["tags"] == ["work"]
            home = (await c.get("/api/home/left")).json()
            review = next(g for g in home["groups"] if g["label"] == "Review")
            assert review["module"] == "newsfeed" and [r["id"] for r in review["rows"]] == [a, b]   # newest found first
            assert next(n for n in (await c.get("/api/home/numbers")).json() if n["module"] == "newsfeed")["value"] == 2

            # Tags on an entry and on a search, through the same two verbs; a search's id is s<id>.
            assert (await c.post("/api/newsfeed/action/tag", json={"id": a, "tags": ["Remote", "ai"]})).json()["tags"] == ["ai", "remote"]
            assert (await c.post("/api/newsfeed/action/untag", json={"id": a, "tag": "remote"})).json()["tags"] == ["ai"]
            assert (await c.post("/api/newsfeed/action/tag", json={"id": f"s{sid}", "tags": ["career"]})).json()["tags"] == ["career", "work"]
            assert (await c.post("/api/newsfeed/action/tag", json={"id": "abc", "tags": ["x"]})).status_code == 400
            assert (await c.post("/api/newsfeed/action/accept", json={})).status_code == 400
            assert (await c.post("/api/newsfeed/action/accept", json={"id": f"s{sid}"})).status_code == 400

            assert (await c.post("/api/newsfeed/action/accept", json={"id": a})).json()["status"] == "accepted"
            assert (await c.post("/api/newsfeed/action/dismiss", json={"id": a})).status_code == 409
            assert [x["verb"] for x in (await c.get(f"/api/newsfeed/item/{a}")).json()["actions"]] == ["link"]
            assert (await c.post("/api/newsfeed/action/dismiss", json={"id": b})).json()["status"] == "dismissed"
            # Dismissed: off every chip and off Home; still in the table so no run proposes it again.
            assert [r["id"] for g in (await c.get("/api/newsfeed/left")).json()["groups"] for r in g["rows"]] == [a]
            assert all(g["label"] != "Review" for g in (await c.get("/api/home/left")).json()["groups"])
            assert store.scalar("SELECT COUNT(*) FROM newsfeed_items") == 2

            # Killing a search keeps its entries, now without a search.
            s = (await c.get(f"/api/newsfeed/item/s{sid}")).json()
            assert s["kind"] == "search" and s["entries"] == 2 and s["actions"][0]["verb"] == "kill" and s["actions"][0]["removes"]
            assert (await c.post("/api/newsfeed/action/kill", json={"id": a})).status_code == 400
            assert (await c.post("/api/newsfeed/action/kill", json={"id": f"s{sid}"})).json() == {"id": f"s{sid}"}
            assert (await c.get(f"/api/newsfeed/item/s{sid}")).status_code == 404
            assert (await c.get(f"/api/newsfeed/item/{a}")).json()["search"] is None
            assert store.scalar("SELECT COUNT(*) FROM newsfeed_tags WHERE kind = 'search'") == 0
            ev = (await c.get("/api/events?module=newsfeed")).json()
            assert [e["verb"] for e in ev["events"]][:4] == ["killed", "dismissed", "accepted", "tagged"]
        await app.state.runner.drain(1)
        store.close()

    run(main())


class FakeServer:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


@pytest.fixture
def feed_store(store):
    from app.modules import Registry

    reg = Registry()
    reg.load()
    store.migrate(reg.get("newsfeed").schema)
    return store


def test_agent_creates_searches_and_tags(feed_store, config):
    read, full = FakeServer(), FakeServer()
    tools.register(read, full, feed_store, config)
    assert set(read.tools) == {"newsfeed_search", "newsfeed_get", "newsfeed_searches"}
    assert set(full.tools) == set(read.tools) | {"newsfeed_search_add", "newsfeed_tag"}
    made = full.tools["newsfeed_search_add"]("jobs", "remote data science roles", tags=["Work", "work", "ai"])
    assert made["id"] == "s1" and made["cap"] == config.newsfeed.items_per_run and made["every_days"] == 1 and made["tags"] == ["ai", "work"]
    assert "error" in full.tools["newsfeed_search_add"]("jobs", "again")
    assert "error" in full.tools["newsfeed_search_add"]("", "x")
    weekly = full.tools["newsfeed_search_add"]("grants", "open grant calls", every_days=7, cap=2)
    assert weekly["every_days"] == 7 and weekly["cap"] == 2
    listed = read.tools["newsfeed_searches"]()
    assert [s["name"] for s in listed] == ["jobs", "grants"] and listed[0]["next_run"] == _day(0)
    eid = _entry(feed_store, 1, "Acme is hiring", "https://acme.example/jobs")
    assert full.tools["newsfeed_tag"](str(eid), ["Remote"])["tags"] == ["remote"]
    assert full.tools["newsfeed_tag"]("s1", ["career"])["tags"] == ["ai", "career", "work"]
    assert "error" in full.tools["newsfeed_tag"]("s9", ["x"]) and "error" in full.tools["newsfeed_tag"]("nope", ["x"])
    assert read.tools["newsfeed_get"]("s1")["tags"] == ["ai", "career", "work"] and read.tools["newsfeed_get"](str(eid))["tags"] == ["remote"]
    assert [r["id"] for r in read.tools["newsfeed_search"]("remote")] == [eid]
    assert read.tools["newsfeed_search"]("nothing") == []


class FakeCtx:
    def __init__(self, store, config, replies=()):
        self.store, self.config = store, config
        self.replies = list(replies)
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
        if not self.replies:
            raise AssertionError("run_task must not be called")
        return self.replies.pop(0)


def test_run_skips_without_due_searches(feed_store, config):
    assert str(run(tasks.run(FakeCtx(feed_store, config)))) == "no searches"
    _search(feed_store, next_run=_day(1))
    r = run(tasks.run(FakeCtx(feed_store, config)))
    assert isinstance(r, Skipped) and str(r) == "nothing due"


def test_run_inserts_capped_dated_tagged_and_idempotent(feed_store, config):
    sid = _search(feed_store, "events", tags=("social",), cap=3)
    later = _search(feed_store, "later", next_run=_day(2))
    items = [
        {"text": f"thing {i}", "url": f"https://x.example/{i}", "summary": "matters", "date": _day(i + 1), "time": "19:00" if i else "", "tags": ["Art", "woodstock"]}
        for i in range(4)
    ]
    items.insert(1, dict(items[0]))                                    # duplicate url
    items.append({"text": "no url", "url": ""})
    items.append({"text": "bad date", "url": "https://x.example/bad", "date": "soon", "follow_up": _day(9), "tags": "notalist"})
    ctx = FakeCtx(feed_store, config, ["```json\n" + json.dumps(items) + "\n```"])
    assert run(tasks.run(ctx)) == "events: 3 new"
    assert len(ctx.prompts) == 1 and "find events" in ctx.prompts[0] and "up to 3" in ctx.prompts[0] and f"Today is {_day(0)}" in ctx.prompts[0]
    stored = feed_store.query("SELECT id, search_id, url, starts_at, status FROM newsfeed_items ORDER BY id")
    assert [r["url"] for r in stored] == ["https://x.example/0", "https://x.example/1", "https://x.example/2"]
    assert stored[0]["starts_at"] == _day(1) and stored[1]["starts_at"] == f"{_day(2)}T19:00" and stored[0]["status"] == "open"
    assert all(r["search_id"] == sid for r in stored)
    assert [r["tag"] for r in feed_store.query("SELECT tag FROM newsfeed_tags WHERE kind = 'item' AND ref = ? ORDER BY tag", (stored[0]["id"],))] == ["art", "social", "woodstock"]
    s = feed_store.one("SELECT next_run, last_run, last_result FROM newsfeed_searches WHERE id = ?", (sid,))
    assert s["next_run"] == _day(1) and s["last_run"] and s["last_result"] == "3 new from 7 proposed"
    assert feed_store.one("SELECT last_run FROM newsfeed_searches WHERE id = ?", (later,))["last_run"] is None
    assert feed_store.cursor("newsfeed.run") is not None and [e[0] for e in ctx.events] == ["found"] * 3

    # The next night: the search is not due; force it and the same reply adds only what is new, the seen list naming the rest.
    feed_store.execute("UPDATE newsfeed_searches SET next_run = ? WHERE id = ?", (_day(0), sid))
    again = FakeCtx(feed_store, config, [json.dumps(items)])
    assert run(tasks.run(again)) == "events: 2 new"                   # the fourth and the undated one, past the cap the first night
    assert "https://x.example/0" in again.prompts[0] and feed_store.scalar("SELECT COUNT(*) FROM newsfeed_items") == 5
    row = feed_store.one("SELECT starts_at, follow_up_at FROM newsfeed_items WHERE url = 'https://x.example/bad'")
    assert row["starts_at"] is None and row["follow_up_at"] == _day(9)

    # A reply with no array is that search's last_result; the run goes on and the search stays due for tomorrow's attempt.
    feed_store.execute("UPDATE newsfeed_searches SET next_run = ? WHERE id = ?", (_day(0), sid))
    bad = FakeCtx(feed_store, config, ["I could not find anything."])
    assert run(tasks.run(bad)) == "events: bad reply"
    assert feed_store.one("SELECT last_result, next_run FROM newsfeed_searches WHERE id = ?", (sid,))["last_result"].startswith("bad reply")
    assert feed_store.one("SELECT next_run FROM newsfeed_searches WHERE id = ?", (sid,))["next_run"] == _day(0)


def test_run_follows_up_on_accepted_entries(feed_store, config):
    sid = _search(feed_store, "grants", tags=("money",))
    due = _entry(feed_store, sid, "Grant call opens", "https://g.example/call", status="accepted", follow_up_at=_day(-1))
    _entry(feed_store, sid, "Not yet", "https://g.example/later", status="accepted", follow_up_at=_day(5))
    _entry(feed_store, sid, "Never asked", "https://g.example/open", status="open", follow_up_at=_day(-3))
    reply = [{"text": "Grant call closed, awards in October", "url": "https://g.example/awards", "summary": "changed", "follows": due, "tags": ["grant"]},
             {"text": "Unrelated", "url": "https://g.example/x", "follows": 999}]
    ctx = FakeCtx(feed_store, config, [json.dumps(reply)])
    assert run(tasks.run(ctx)) == "grants: 2 new"
    p = ctx.prompts[0]
    assert "follow-up day has come" in p and f"({due}, {_day(-1)}) https://g.example/call" in p and "g.example/later" in p and "g.example/open" in p
    assert p.count("g.example/later") == 1 and p.count("g.example/call") == 2      # listed as seen and as due; the others as seen only
    new = feed_store.one("SELECT follows, search_id FROM newsfeed_items WHERE url = 'https://g.example/awards'")
    assert new["follows"] == due and new["search_id"] == sid
    assert feed_store.one("SELECT follows FROM newsfeed_items WHERE url = 'https://g.example/x'")["follows"] is None
    assert feed_store.one("SELECT follow_up_at FROM newsfeed_items WHERE id = ?", (due,))["follow_up_at"] is None      # consumed
    assert feed_store.one("SELECT follow_up_at FROM newsfeed_items WHERE url = 'https://g.example/later'")["follow_up_at"] == _day(5)


# The three retired modules' tables as their schemas created them, with rows.
OLD = """
CREATE TABLE business_items (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, text TEXT NOT NULL, ref TEXT, why TEXT, status TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
INSERT INTO business_items VALUES (5, 'plan', 'startups in Atlanta', NULL, NULL, 'open', '2026-09-09T05:38:43+00:00', '2026-09-09T05:38:43+00:00');
INSERT INTO business_items VALUES (6, 'plan', 'remote data science jobs', NULL, NULL, 'open', '2026-09-09T05:38:44+00:00', '2026-09-09T05:38:44+00:00');
INSERT INTO business_items VALUES (8, 'lead', 'COLLIDE conference', 'https://b.example/collide', 'an Atlanta AI conference', 'open', '2026-09-09T06:01:04+00:00', '2026-09-09T06:01:04+00:00');
INSERT INTO business_items VALUES (11, 'lead', 'Venture Atlanta', 'https://b.example/venture', 'pitch competition', 'dismissed', '2026-09-10T06:00:57+00:00', '2026-09-11T00:00:00+00:00');
INSERT INTO business_items VALUES (12, 'person', 'Sam at Acme', NULL, NULL, 'open', '2026-09-10T06:00:57+00:00', '2026-09-10T06:00:57+00:00');
CREATE TABLE social_items (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, text TEXT NOT NULL, ref TEXT, why TEXT, category TEXT, city TEXT, venue TEXT, starts_at TEXT, status TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
INSERT INTO social_items VALUES (4, 'event', 'Textile exhibition', 'https://s.example/knots', 'new exhibition', 'art', 'Woodstock', 'Woodstock Arts', '2026-09-18T00:00', 'going', '2026-09-13T14:24:16+00:00', '2026-09-14T00:00:00+00:00');
INSERT INTO social_items VALUES (11, 'event', 'Roswell Arts Festival', 'https://s.example/roswell', 'free outdoor show', 'art', 'Roswell, GA', 'City Hall', '2026-09-19T10:00', 'open', '2026-09-14T06:46:49+00:00', '2026-09-14T06:46:49+00:00');
INSERT INTO social_items VALUES (12, 'interest', 'meet people building things', NULL, NULL, NULL, NULL, NULL, NULL, 'open', '2026-09-14T06:46:49+00:00', '2026-09-14T06:46:49+00:00');
CREATE TABLE web_search_topics (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, text TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);
CREATE TABLE web_search_findings (id INTEGER PRIMARY KEY, topic_id INTEGER, kind TEXT NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL UNIQUE, summary TEXT NOT NULL, found_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open', decided_at TEXT);
INSERT INTO web_search_topics VALUES (1, 'learn', 'causal inference', '2026-09-01T00:00:00+00:00');
INSERT INTO web_search_findings VALUES (1, 1, 'learn', 'A causal primer', 'https://w.example/causal', 'two sentences', '2026-09-02T00:00:00+00:00', 'agreed', '2026-09-03T00:00:00+00:00');
"""


def test_migrate_converts_the_retired_modules(store):
    conn = sqlite3.connect(store.path)
    conn.executescript(OLD)
    conn.close()
    assert migrate.convert(store) == {"searches": 3, "entries": 5}
    names = store.query("SELECT id, name, cap, every_days, next_run, prompt FROM newsfeed_searches ORDER BY id")
    assert [s["name"] for s in names] == ["business", "social", "causal inference"] and [s["cap"] for s in names] == [3, 5, 3]
    assert all(s["every_days"] == 1 and s["next_run"] == _day(0) for s in names)
    assert names[0]["prompt"].endswith("- startups in Atlanta\n- remote data science jobs") and "Woodstock, GA" in names[1]["prompt"] and "causal inference" in names[2]["prompt"]
    tags = lambda kind, ref: [r["tag"] for r in store.query("SELECT tag FROM newsfeed_tags WHERE kind = ? AND ref = ? ORDER BY tag", (kind, ref))]
    assert tags("search", names[0]["id"]) == ["business"] and tags("search", names[2]["id"]) == ["learn"]
    items = {r["url"]: r for r in store.query("SELECT * FROM newsfeed_items")}
    assert set(items) == {"https://b.example/collide", "https://b.example/venture", "https://s.example/knots", "https://s.example/roswell", "https://w.example/causal"}
    assert items["https://b.example/venture"]["status"] == "dismissed" and items["https://b.example/venture"]["decided_at"] == "2026-09-11T00:00:00+00:00"
    assert items["https://b.example/collide"]["summary"] == "an Atlanta AI conference" and items["https://b.example/collide"]["decided_at"] is None
    assert items["https://s.example/knots"]["status"] == "accepted" and items["https://s.example/knots"]["starts_at"] == "2026-09-18"
    assert items["https://s.example/roswell"]["starts_at"] == "2026-09-19T10:00" and tags("item", items["https://s.example/roswell"]["id"]) == ["art", "roswell", "social"]
    assert items["https://w.example/causal"]["status"] == "accepted" and items["https://w.example/causal"]["search_id"] == names[2]["id"]
    assert store.scalar("SELECT COUNT(*) FROM business_items") == 5                      # the old tables are left alone
    assert migrate.convert(store) == {"searches": 0, "entries": 0}                        # and a second run adds nothing
    assert store.scalar("SELECT COUNT(*) FROM newsfeed_items") == 5
