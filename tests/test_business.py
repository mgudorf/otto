"""Business module: catalog end to end, the documents mirror, and the capped, idempotent scout."""

import json

import pytest

from app.daemon import build
from app.modules.business import tasks
from app.runner import Skipped
from tests.conftest import run
from tests.test_app import client_for


def test_business_end_to_end(config):
    async def main():
        app = build(config)
        await app.state.runner.start()
        async with client_for(app) as c:
            shell = (await c.get("/api/shell")).json()
            biz = next(m for m in shell["modules"] if m["name"] == "business")
            assert biz["hue"] == "#c98ba8" and biz["agent"]["skills"] == ["recall", "add", "scout", "summarize"]
            r = await c.post("/api/business/action/capture", json={"kind": "plan", "text": "ship otto by december", "ref": ""})
            assert r.status_code == 200, r.text
            pid = r.json()["id"]
            await c.post("/api/business/action/capture", json={"kind": "person", "text": "Sam, hiring at Acme", "ref": "https://acme.example"})
            assert (await c.post("/api/business/action/capture", json={"kind": "lead", "text": "x"})).status_code == 400
            left = (await c.get("/api/business/left?query=otto")).json()
            assert left["groups"][0]["rows"][0]["id"] == pid and left["showing"] == "1 / 1"
            left = (await c.get("/api/business/left?chip=People")).json()
            assert left["groups"][0]["rows"][0]["leading"]["kind"] == "person"
            item = (await c.get(f"/api/business/item/{pid}")).json()
            assert item["ref"] is None and [a["verb"] for a in item["actions"]] == ["forget"]
            home = (await c.get("/api/home/left")).json()
            assert {g["module"]: g["count"] for g in home["groups"]}["business"] == 2
            numbers = (await c.get("/api/home/numbers")).json()
            assert next(n for n in numbers if n["module"] == "business")["value"] == 0

            # A lead waits under Review however old it is; each verb is a route taking {id}, which is what Home posts.
            store = app.state.store
            store.execute(
                "INSERT INTO business_items(kind, text, ref, why, created_at, updated_at)"
                " VALUES ('lead', 'Acme is hiring', 'https://acme.example/jobs', 'serves the december plan', ?, ?)",
                ("2026-09-01T09:00:00+00:00",) * 2,
            )
            lid = store.scalar("SELECT id FROM business_items WHERE kind = 'lead'")
            review = next(g for g in (await c.get("/api/home/left")).json()["groups"] if g["label"] == "Review")
            assert review["module"] == "business" and [r["id"] for r in review["rows"]] == [lid]
            assert [a["verb"] for a in (await c.get(f"/api/business/item/{lid}")).json()["actions"]] == ["accept", "dismiss", "link"]
            assert (await c.post("/api/business/action/dismiss", json={"id": pid})).status_code == 400   # only a lead is decided
            assert (await c.post("/api/business/action/dismiss", json={"id": lid})).json()["status"] == "dismissed"

            # Dismissed: off every chip and off Home, struck through nowhere, and still in the table for the scout.
            listed = [r["id"] for g in (await c.get("/api/business/left")).json()["groups"] for r in g["rows"]]
            assert lid not in listed and (await c.get("/api/business/left?chip=Leads")).json()["groups"] == []
            assert all(g["label"] != "Review" for g in (await c.get("/api/home/left")).json()["groups"])
            assert store.scalar("SELECT COUNT(*) FROM business_items WHERE kind = 'lead'") == 1
            assert [a["verb"] for a in (await c.get(f"/api/business/item/{lid}")).json()["actions"]] == ["link"]

            assert (await c.post("/api/business/action/forget", json={"id": pid})).status_code == 200
            assert (await c.get(f"/api/business/item/{pid}")).status_code == 404
            ev = (await c.get("/api/events?module=business")).json()
            assert [e["verb"] for e in ev["events"]][:3] == ["forgot", "dismissed", "captured"]
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
                    conn.execute("INSERT INTO cursors(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", cursor)

        return _tx()

    def event(self, verb, text, ref=None):
        self.events.append((verb, text))

    async def run_task(self, prompt, tools=()):
        self.prompts.append(prompt)
        assert tools == ("business_search",)
        return self.reply


@pytest.fixture
def biz_store(store):
    from app.modules import Registry

    reg = Registry()
    reg.load()
    store.migrate(reg.get("business").schema)
    return store


def test_index_documents_mirrors_folder(biz_store, config):
    folder = tasks.documents_folder(config)
    folder.mkdir(parents=True)
    (folder / "deck.pdf").write_bytes(b"x")
    (folder / "notes.md").write_text("y")
    ctx = FakeCtx(biz_store, config)
    assert run(tasks.index_documents(ctx)) == "2 added, 0 removed"
    rows = biz_store.query("SELECT text, ref FROM business_items WHERE kind = 'document' ORDER BY text")
    assert [r["text"] for r in rows] == ["deck.pdf", "notes.md"] and rows[0]["ref"].endswith("deck.pdf")
    assert isinstance(run(tasks.index_documents(ctx)), Skipped)
    (folder / "deck.pdf").unlink()
    assert run(tasks.index_documents(ctx)) == "0 added, 1 removed"
    assert biz_store.scalar("SELECT COUNT(*) FROM business_items WHERE kind = 'document'") == 1
    from app.modules.business.routes import _row

    row = _row(biz_store.one("SELECT * FROM business_items WHERE kind = 'document'"))
    assert row["leading"] == {"ext": "md"} and row["module"] == "business"


def test_scout_inserts_capped_and_idempotent(biz_store, config):
    assert config.business.leads_per_run == 3
    assert isinstance(run(tasks.scout(FakeCtx(biz_store, config))), Skipped)
    ts = "2026-09-07T00:00:00+00:00"
    biz_store.execute("INSERT INTO business_items(kind, text, created_at, updated_at) VALUES ('plan', 'find a research role', ?, ?)", (ts, ts))
    leads = [{"text": f"lead {i}", "url": f"https://x.example/{i}", "why": "fits"} for i in range(4)]
    leads.insert(1, dict(leads[0]))                       # duplicate url
    leads.append({"text": "no url", "url": ""})
    ctx = FakeCtx(biz_store, config, "```json\n" + json.dumps(leads) + "\n```")
    assert run(tasks.scout(ctx)) == "3 new lead(s) from 6 proposed"
    assert "find a research role" in ctx.prompts[0]
    stored = biz_store.query("SELECT text, ref, why, status FROM business_items WHERE kind = 'lead' ORDER BY id")
    assert [r["ref"] for r in stored] == ["https://x.example/0", "https://x.example/1", "https://x.example/2"]
    assert stored[0]["status"] == "open" and stored[0]["why"] == "fits"
    assert biz_store.cursor("business.scout") is not None
    assert [e[0] for e in ctx.events] == ["found"] * 3
    again = FakeCtx(biz_store, config, json.dumps(leads))
    assert run(tasks.scout(again)) == "1 new lead(s) from 6 proposed"
    assert "https://x.example/0" in again.prompts[0]
    assert biz_store.scalar("SELECT COUNT(*) FROM business_items WHERE kind = 'lead'") == 4
