"""Finance through the real app: the ledger end to end, its rows on the feed, the due dates, and proof the agent only reads."""

import sqlite3
from datetime import date, timedelta

from app.daemon import build
from app.modules.finance import MANIFEST, setup
from app.modules.finance.routes import next_due
from tests.conftest import run
from tests.test_app import client_for


def test_finance_end_to_end(config):
    async def main():
        app = build(config)
        await app.state.runner.start()
        async with client_for(app) as c:
            shell = (await c.get("/api/shell")).json()
            fin = next(m for m in shell["modules"] if m["name"] == "finance")
            assert fin["order"] == 5 and fin["facet"] == "finance" and fin["agent"]["placeholder"] == "Ask about money…"
            cap = lambda body: c.post("/api/finance/action/capture", json=body)
            r = await cap({"kind": "account", "name": "Checking", "amount": "1,250.50"})
            assert r.status_code == 200, r.text
            acct = r.json()["id"]
            assert (await cap({"kind": "recurring", "name": "Domain", "amount": 120, "cadence": "yearly"})).status_code == 200
            assert (await cap({"kind": "holding", "name": "VTI", "amount": "3000", "note": "12 shares"})).status_code == 200
            assert (await cap({"kind": "budget", "name": "Food", "amount": "400", "cadence": "monthly"})).status_code == 200
            assert (await cap({"kind": "recurring", "name": "Bad", "amount": "ten", "cadence": "monthly"})).status_code == 400
            assert (await cap({"kind": "recurring", "name": "NoCadence", "amount": "1"})).status_code == 400
            ledger = lambda: {r["title"]: r for r in app.state.registry.get("finance").rows(app.state.store, 200)}
            checking = ledger()["Checking"]
            assert (checking["title"], checking["amount"], checking["snip"], checking["dim"]) == ("Checking", "$1,250.50", None, False)
            assert checking["fixed"] == ["finance"] and checking["tags"] == ["account"]   # finance is fixed; the kind narrows as a plain tag, never written into the title
            assert checking["type"] == "ledger" and [v for v, _ in checking["verbs"]] == ["update", "end", "forget"]
            domain = ledger()["Domain"]
            assert (domain["title"], domain["amount"], domain["snip"], domain["due"]) == ("Domain", "$120.00", "yearly", None)
            # the rows hook is what the feed reads: one holding, found by the kind it carries
            assert [(r["title"], r["amount"]) for r in (await c.get("/api/feed?mode=recent&tags=holding")).json()["items"]] == [("VTI", "$3,000.00")]
            blank = (await c.get("/api/finance/blank")).json()
            assert blank["totals"] == {"accounts": 125050, "holdings": 300000, "monthly_recurring": 1000, "monthly_budget": 40000}
            assert (await c.post("/api/finance/action/update", json={"id": acct, "amount": "1300"})).json()["amount"] == 130000
            item = (await c.get(f"/api/finance/item/{acct}")).json()
            assert [amount for _, amount in item["hist"]] == ["$1,300.00", "$1,250.50"]
            assert (item["title"], item["amount"], item["note"]) == ("Checking", "$1,300.00", None)
            assert item["kv"] == [] and [v for v, _ in item["verbs"]] == ["update", "end", "forget"]
            assert (await c.post("/api/finance/action/end", json={"id": acct})).status_code == 200
            ended = ledger()["Checking"]
            assert ended["dim"] is True and ended["title"] == "Checking"
            assert (await c.get("/api/finance/blank")).json()["totals"]["accounts"] == 0
            numbers = (await c.get("/api/home/numbers")).json()
            fin_n = next(n for n in numbers if n["module"] == "finance")
            assert fin_n["value"] == 3 and fin_n["label"] == "records"
            recent = (await c.get("/api/feed?mode=recent")).json()["items"]
            assert len([r for r in recent if r["module"] == "finance"]) == 4   # ended and all: the ledger is small, so nothing is held back
            for bad in ({}, {"id": "abc"}, {"id": None}):   # a malformed id is a 400 naming the field, like every other check
                assert (await c.post("/api/finance/action/forget", json=bad)).status_code == 400
            assert (await c.post("/api/finance/action/forget", json={"id": acct})).status_code == 200
            assert (await c.get(f"/api/finance/item/{acct}")).status_code == 404
            assert app.state.store.scalar("SELECT COUNT(*) FROM finance_amounts WHERE entry_id = ?", (acct,)) == 0
            ev = (await c.get("/api/events?module=finance")).json()
            assert [e["verb"] for e in ev["events"]][:4] == ["forgot", "ended", "updated", "captured"]
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_finance_feed_and_verbs(config):
    """The ledger on the one page: its rows in both feed modes, narrowed by tag and by typed text, and a verb run
    through the single front door rather than the module's own route."""

    async def main():
        app = build(config)
        await app.state.runner.start()
        async with client_for(app) as c:
            cap = lambda body: c.post("/api/finance/action/capture", json=body)
            acct = (await cap({"kind": "account", "name": "Checking", "amount": "10"})).json()["id"]
            assert (await cap({"kind": "holding", "name": "VTI", "amount": "30", "note": "12 shares"})).status_code == 200
            mine = lambda d: [r for r in d["items"] if r["module"] == "finance"]
            recent = mine((await c.get("/api/feed?mode=recent")).json())
            assert [r["title"] for r in recent] == ["VTI", "Checking"]              # most recently touched first
            assert all(r["fixed"] == ["finance"] and r["type"] == "ledger" for r in recent)
            assert all(r.get("waits") is None for r in recent)                     # Recent ranks nothing; only a queue row waits
            assert [r["title"] for r in (await c.get("/api/feed?mode=recent&tags=finance,account")).json()["items"]] == ["Checking"]
            assert [r["title"] for r in (await c.get("/api/feed?mode=recent&q=checking")).json()["items"]] == ["Checking"]
            assert mine((await c.get("/api/feed?mode=priority")).json()) == []      # nothing in the ledger waits on the owner
            assert (await c.get("/api/feed?mode=sideways")).status_code == 400

            # one list holds every module, so a finance row is stamped on the owner's clock like all the rest
            assert (await c.post("/api/second_brain/action/capture", json={"kind": "note", "text": "Groceries"})).status_code == 200
            assert len(recent[0]["when"]) == len("2026-09-21T12:00")
            assert [r["title"] for r in (await c.get("/api/feed?mode=recent")).json()["items"]][0] == "Groceries"

            ran = (await c.post("/api/verb", json={"module": "finance", "id": acct, "verb": "end"})).json()
            assert ran == {"ok": True, "said": "ended account: Checking", "removes": True}
            assert (await c.get(f"/api/finance/item/{acct}")).json()["dim"] is True
            gone = (await c.post("/api/verb", json={"module": "finance", "id": acct, "verb": "forget"})).json()
            assert gone["said"] == "forgot account: Checking" and gone["removes"] is True
            assert (await c.get(f"/api/finance/item/{acct}")).status_code == 404
            assert (await c.post("/api/verb", json={"module": "finance", "id": acct, "verb": "nonsense"})).status_code == 404
            assert (await c.post("/api/verb", json={"module": "nope", "id": "1", "verb": "end"})).status_code == 404
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_finance_next_due_projection():
    """Fixed today, so the clamp cases are exact and nothing depends on the clock."""
    def nxt(anchor, cadence, today, ended=None):
        return next_due({"due_on": anchor, "cadence": cadence, "ended_at": ended}, date.fromisoformat(today))

    assert nxt("2026-01-31", "monthly", "2026-04-05") == "2026-04-30"   # clamps to a 30-day month
    assert nxt("2026-01-31", "monthly", "2026-02-01") == "2026-02-28"   # and to February
    assert nxt("2026-01-31", "monthly", "2026-05-01") == "2026-05-31"   # then back to the 31st, no drift
    assert nxt("2026-01-31", "monthly", "2026-04-30") == "2026-04-30"   # due today counts as next
    assert nxt("2026-09-15", "monthly", "2026-09-16") == "2026-10-15"   # this month's already gone
    assert nxt("2026-12-01", "monthly", "2026-09-12") == "2026-12-01"   # an anchor in the future is the answer
    assert nxt("2026-09-07", "weekly", "2026-09-12") == "2026-09-14"
    assert nxt("2024-02-29", "yearly", "2026-09-12") == "2027-02-28"    # leap day outside a leap year
    assert nxt("2026-01-31", "monthly", "2026-04-05", ended="2026-02-01") is None
    assert nxt(None, "monthly", "2026-04-05") is None


def test_finance_due_dates(config):
    today = date.today()
    later = today + timedelta(days=3)

    async def main():
        app = build(config)
        await app.state.runner.start()
        async with client_for(app) as c:
            cap = lambda body: c.post("/api/finance/action/capture", json=body)
            rent = (await cap({"kind": "recurring", "name": "Rent", "amount": "1800", "cadence": "monthly", "due_on": today.isoformat()})).json()["id"]
            assert (await cap({"kind": "recurring", "name": "Gym", "amount": "40", "cadence": "weekly", "due_on": later.isoformat()})).status_code == 200
            domain = (await cap({"kind": "recurring", "name": "Domain", "amount": "120", "cadence": "yearly"})).json()["id"]
            acct = (await cap({"kind": "account", "name": "Checking", "amount": "10", "due_on": today.isoformat()})).json()["id"]
            assert (await cap({"kind": "recurring", "name": "Bad", "amount": "1", "cadence": "monthly", "due_on": "15 Oct"})).status_code == 400

            item = (await c.get(f"/api/finance/item/{rent}")).json()
            assert item["due_on"] == today.isoformat() and item["due"] == today.isoformat()   # the anchor the box edits, and the occurrence the row shows
            assert [v for v, _ in item["verbs"]] == ["update", "due", "end", "forget"]
            assert "due" not in [v for v, _ in (await c.get(f"/api/finance/item/{acct}")).json()["verbs"]]
            assert (await c.get(f"/api/finance/item/{acct}")).json()["due"] is None   # a date is ignored off a recurring entry

            rows = {r["title"]: r for r in app.state.registry.get("finance").rows(app.state.store, 200) if "recurring" in r["tags"]}
            assert set(rows) == {"Rent", "Gym", "Domain"}
            assert (rows["Rent"]["amount"], rows["Rent"]["snip"], rows["Rent"]["due"]) == ("$1,800.00", "monthly", today.isoformat())
            assert (rows["Domain"]["amount"], rows["Domain"]["snip"], rows["Domain"]["due"]) == ("$120.00", "yearly", None)

            assert (await c.post("/api/finance/action/due", json={"id": acct, "due_on": today.isoformat()})).status_code == 400
            assert (await c.post("/api/finance/action/due", json={"id": domain, "due_on": "nope"})).status_code == 400
            dated = (await c.post("/api/finance/action/due", json={"id": domain, "due_on": later.isoformat()})).json()
            assert dated["next_due"] == later.isoformat()
            assert len((await c.get(f"/api/finance/item/{domain}")).json()["hist"]) == 1   # the opening amount only: a date is not an amount
            assert (await c.post("/api/finance/action/due", json={"id": domain, "due_on": ""})).json()["next_due"] is None
            assert (await c.get(f"/api/finance/item/{domain}")).json()["due_on"] is None

            assert (await c.post("/api/finance/action/end", json={"id": rent})).status_code == 200
            assert (await c.get(f"/api/finance/item/{rent}")).json()["due"] is None   # an ended payment is not due again
            ev = [e["verb"] for e in (await c.get("/api/events?module=finance")).json()["events"]]
            assert ev[:2] == ["ended", "dated"]
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_finance_due_column_added(config):
    """A database built before the column is brought up by setup, and a second boot finds nothing to add."""
    conn = sqlite3.connect(config.data.db)
    conn.execute(
        "CREATE TABLE finance_entries (id INTEGER PRIMARY KEY, kind TEXT, name TEXT, amount INTEGER, "
        "cadence TEXT, note TEXT, created_at TEXT, updated_at TEXT, ended_at TEXT)"
    )
    conn.commit()
    conn.close()
    setup(config)
    setup(config)
    conn = sqlite3.connect(config.data.db)
    columns = [r[1] for r in conn.execute("PRAGMA table_info(finance_entries)")]
    conn.close()
    assert columns.count("due_on") == 1


def test_finance_agent_reads_only(config):
    assert MANIFEST.schedules == () and MANIFEST.agent.write_tools == ()

    async def main():
        app = build(config)
        read = {t.name for t in await app.state.mcp_read.list_tools() if t.name.startswith("finance_")}
        full = {t.name for t in await app.state.mcp_full.list_tools() if t.name.startswith("finance_")}
        assert read == full == set(MANIFEST.agent.read_tools)
        app.state.store.close()

    run(main())
