"""Social module: interests and the yes/no on an event end to end, and the capped, dated, idempotent scout."""

import json
from datetime import datetime, timedelta

import pytest

from app.daemon import build
from app.modules.social import routes, tasks
from tests.conftest import run
from tests.test_app import client_for


def _day(offset: int) -> str:
    return (datetime.now().astimezone() + timedelta(days=offset)).strftime("%Y-%m-%d")


def test_social_end_to_end(config):
    async def main():
        app = build(config)
        await app.state.runner.start()
        async with client_for(app) as c:
            shell = (await c.get("/api/shell")).json()
            soc = next(m for m in shell["modules"] if m["name"] == "social")
            assert soc["hue"] == "#8f95d6" and soc["agent"]["skills"] == ["upcoming", "add", "scout", "plan"]
            r = await c.post("/api/social/action/capture", json={"text": "meet people building things", "ref": ""})
            assert r.status_code == 200, r.text
            iid = r.json()["id"]
            assert (await c.post("/api/social/action/capture", json={"text": "  "})).status_code == 400

            store = app.state.store
            store.execute(
                "INSERT INTO social_items(kind, text, ref, why, category, city, venue, starts_at, created_at, updated_at)"
                " VALUES ('event', ?, ?, ?, 'game', 'Woodstock, GA', 'The Hall', ?, ?, ?)",
                ("Board game night", "https://e.example/1", "you asked for game nights", f"{_day(3)}T19:00", "2026-09-13T00:00:00+00:00", "2026-09-13T00:00:00+00:00"),
            )
            eid = store.scalar("SELECT id FROM social_items WHERE kind = 'event'")

            left = (await c.get("/api/social/left")).json()          # no chip: Upcoming, events only
            assert left["chip"] == "Upcoming" and [r["id"] for g in left["groups"] for r in g["rows"]] == [eid]
            assert left["groups"][0]["rows"][0]["stampText"] == "19:00"
            assert left["groups"][0]["rows"][0]["leading"] == {"kind": "game"}
            assert (await c.get("/api/social/left?chip=All")).json()["chip"] == "Upcoming"   # shell's reset falls back
            ints = (await c.get("/api/social/left?chip=Interests")).json()
            assert [r["id"] for g in ints["groups"] for r in g["rows"]] == [iid]
            assert (await c.get("/api/social/left?query=woodstock")).json()["showing"] == "1 / 1"

            blank = (await c.get("/api/social/blank")).json()
            assert blank["counts"] == {"game": 1} and blank["interests"] == 1 and len(blank["events"]) == 1
            assert blank["cities"][0] == "Woodstock, GA"

            item = (await c.get(f"/api/social/item/{eid}")).json()
            assert [a["verb"] for a in item["actions"]] == ["going", "dismiss", "link"]
            assert [a["verb"] for a in (await c.get(f"/api/social/item/{iid}")).json()["actions"]] == ["forget"]

            numbers = (await c.get("/api/home/numbers")).json()
            assert next(n for n in numbers if n["module"] == "social")["value"] == 1
            home = (await c.get("/api/home/left")).json()
            assert any(g["module"] == "social" for g in home["groups"])

            # every verb the item offers is a real route taking {id}, which is what Home posts
            assert (await c.post("/api/social/action/going", json={"id": eid})).json()["status"] == "going"
            assert (await c.get(f"/api/social/item/{eid}")).json()["status"] == "going"
            assert [a["verb"] for a in (await c.get(f"/api/social/item/{eid}")).json()["actions"]] == ["dismiss", "link"]
            assert (await c.get("/api/social/left?chip=Going")).json()["showing"] == "1 / 1"
            assert (await c.post("/api/social/action/forget", json={"id": eid})).status_code == 400
            assert (await c.post("/api/social/action/going", json={"id": iid})).status_code == 400
            assert (await c.post("/api/social/action/forget", json={"id": iid})).status_code == 200
            assert (await c.get(f"/api/social/item/{iid}")).status_code == 404

            ev = (await c.get("/api/events?module=social")).json()
            assert [e["verb"] for e in ev["events"]][:3] == ["forgot", "going", "captured"]
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_home_posts_only_verbs_social_serves(config):
    """The Home inspector posts `/api/<module>/action/<verb>` with {id}; every social verb must be one of ACTIONS."""
    async def main():
        app = build(config)
        store = app.state.store
        ts = "2026-09-13T00:00:00+00:00"
        store.execute(
            "INSERT INTO social_items(kind, text, ref, category, starts_at, created_at, updated_at)"
            " VALUES ('event', 'x', 'https://e.example/9', 'film', ?, ?, ?)", (f"{_day(2)}T00:00", ts, ts),
        )
        store.execute("INSERT INTO social_items(kind, text, created_at, updated_at) VALUES ('interest', 'y', ?, ?)", (ts, ts))
        for row in store.query("SELECT id FROM social_items"):
            for a in routes.item(store, str(row["id"]))["actions"]:
                assert a["verb"] == "link" or a["verb"] in routes.ACTIONS, a
        store.close()

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
                    conn.execute("INSERT INTO cursors(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", cursor)

        return _tx()

    def event(self, verb, text, ref=None):
        self.events.append((verb, text))

    async def run_task(self, prompt, tools=()):
        self.prompts.append(prompt)
        assert tools == ("social_search",)
        return self.reply


@pytest.fixture
def soc_store(store):
    from app.modules import Registry

    reg = Registry()
    reg.load()
    store.migrate(reg.get("social").schema)
    return store


def test_scout_runs_without_interests_and_is_capped(soc_store, config):
    assert config.social.events_per_run == 5 and len(config.social.cities) == 5
    events = [
        {"text": f"event {i}", "url": f"https://e.example/{i}", "category": "music", "city": "Roswell, GA",
         "venue": "Green", "date": _day(i + 1), "time": "18:30", "why": "fits"}
        for i in range(6)
    ]
    events.append({**events[0]})                                                  # same url and date
    events.append({**events[1], "date": _day(400)})                               # past the horizon
    events.append({**events[2], "category": "drinking"})                          # not a category
    events.append({**events[3], "date": "soon"})                                  # unusable date
    ctx = FakeCtx(soc_store, config, "```json\n" + json.dumps(events) + "\n```")
    assert run(tasks.scout(ctx)) == "5 new event(s) from 10 proposed"
    assert "Woodstock, GA" in ctx.prompts[0] and "nothing recorded yet" in ctx.prompts[0]
    assert "bar crawls" in ctx.prompts[0]
    stored = soc_store.query("SELECT ref, starts_at, category, status FROM social_items ORDER BY id")
    assert [r["ref"] for r in stored] == [f"https://e.example/{i}" for i in range(5)]
    assert stored[0]["starts_at"] == f"{_day(1)}T18:30" and stored[0]["status"] == "open"
    assert soc_store.cursor("social.scout") is not None
    assert [e[0] for e in ctx.events] == ["found"] * 5

    again = FakeCtx(soc_store, config, json.dumps(events))
    assert run(tasks.scout(again)) == "1 new event(s) from 10 proposed"            # only event 5 is new
    assert "https://e.example/0" in again.prompts[0]
    assert soc_store.scalar("SELECT COUNT(*) FROM social_items") == 6


def test_scout_steers_on_interests_and_keeps_a_series(soc_store, config):
    ts = "2026-09-13T00:00:00+00:00"
    soc_store.execute("INSERT INTO social_items(kind, text, created_at, updated_at) VALUES ('interest', 'pottery classes', ?, ?)", (ts, ts))
    same = {"text": "Trivia", "url": "https://e.example/trivia", "category": "game", "city": "Canton, GA", "venue": "Cafe", "time": "19:00", "why": "weekly"}
    reply = json.dumps([{**same, "date": _day(2)}, {**same, "date": _day(9)}])
    ctx = FakeCtx(soc_store, config, reply)
    assert run(tasks.scout(ctx)) == "2 new event(s) from 2 proposed"               # one url, two dates, both kept
    assert "pottery classes" in ctx.prompts[0]
    assert soc_store.scalar("SELECT COUNT(*) FROM social_items WHERE kind = 'event'") == 2


def test_starts_at_rejects_what_it_cannot_place():
    first = datetime(2026, 9, 13)
    last = first + timedelta(days=30)
    assert tasks._starts_at("2026-09-20", "19:00", first, last) == "2026-09-20T19:00"
    assert tasks._starts_at("2026-09-20", "", first, last) == "2026-09-20T00:00"
    assert tasks._starts_at("2026-09-12", "19:00", first, last) is None            # before today
    assert tasks._starts_at("2026-11-01", "", first, last) is None                 # past the horizon
    assert tasks._starts_at("next friday", "", first, last) is None


def test_row_clock_follows_the_time_format():
    r = {"id": 1, "kind": "event", "text": "x", "category": "film", "status": "open",
         "created_at": "2026-09-13T00:00:00+00:00", "starts_at": "2026-09-20T19:00"}
    assert routes._row(r, "24h")["stampText"] == "19:00"
    assert routes._row(r, "12h")["stampText"] == "7:00 PM"
    assert routes._row({**r, "starts_at": "2026-09-20T00:00"}, "24h")["stampText"] == "all day"
    assert "stampText" not in routes._row({**r, "kind": "interest", "category": None, "starts_at": None}, "24h")
