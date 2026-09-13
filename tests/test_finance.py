"""Finance through the real app: the ledger end to end, the due dates, and proof the agent only reads."""

import sqlite3
from datetime import date, timedelta

from app.daemon import build
from app.modules.finance import MANIFEST, setup
from app.modules.finance.routes import day_label, next_due
from tests.conftest import run
from tests.test_app import client_for


def test_finance_end_to_end(config):
    async def main():
        app = build(config)
        await app.state.runner.start()
        async with client_for(app) as c:
            shell = (await c.get("/api/shell")).json()
            fin = next(m for m in shell["modules"] if m["name"] == "finance")
            assert fin["order"] == 5 and fin["agent"]["placeholder"] == "Ask about money…"
            cap = lambda body: c.post("/api/finance/action/capture", json=body)
            r = await cap({"kind": "account", "name": "Checking", "amount": "1,250.50"})
            assert r.status_code == 200, r.text
            acct = r.json()["id"]
            assert (await cap({"kind": "recurring", "name": "Domain", "amount": 120, "cadence": "yearly"})).status_code == 200
            assert (await cap({"kind": "holding", "name": "VTI", "amount": "3000", "note": "12 shares"})).status_code == 200
            assert (await cap({"kind": "budget", "name": "Food", "amount": "400", "cadence": "monthly"})).status_code == 200
            assert (await cap({"kind": "recurring", "name": "Bad", "amount": "ten", "cadence": "monthly"})).status_code == 400
            assert (await cap({"kind": "recurring", "name": "NoCadence", "amount": "1"})).status_code == 400
            left = (await c.get("/api/finance/left")).json()
            assert [g["label"] for g in left["groups"]] == ["Accounts", "Recurring", "Holdings", "Budgets"]
            assert left["groups"][0]["rows"][0]["stampText"] == "1,250.50"
            assert left["groups"][1]["rows"][0]["stampText"] == "120.00 /yr"
            left = (await c.get("/api/finance/left?chip=Holdings&query=shares")).json()
            assert [g["label"] for g in left["groups"]] == ["Holdings"] and left["groups"][0]["rows"][0]["text"] == "VTI"
            blank = (await c.get("/api/finance/blank")).json()
            assert blank["totals"] == {"accounts": 125050, "holdings": 300000, "monthly_recurring": 1000, "monthly_budget": 40000}
            assert (await c.post("/api/finance/action/update", json={"id": acct, "amount": "1300"})).json()["amount"] == 130000
            item = (await c.get(f"/api/finance/item/{acct}")).json()
            assert [h["amount"] for h in item["history"]] == [130000, 125050] and item["text"] == "Checking\n1,300.00"
            assert [a["verb"] for a in item["actions"]] == ["update", "end", "forget"]
            assert (await c.post("/api/finance/action/end", json={"id": acct})).status_code == 200
            left = (await c.get("/api/finance/left?chip=Accounts")).json()
            assert left["groups"][0]["rows"][0]["done"] is True and left["groups"][0]["rows"][0]["leading"] == {"dot": "transparent"}
            assert (await c.get("/api/finance/blank")).json()["totals"]["accounts"] == 0
            numbers = (await c.get("/api/home/numbers")).json()
            fin_n = next(n for n in numbers if n["module"] == "finance")
            assert fin_n["value"] == 3 and fin_n["label"] == "records"
            home = (await c.get("/api/home/left")).json()
            assert next(g for g in home["groups"] if g["module"] == "finance")["count"] == 4
            assert (await c.post("/api/finance/action/forget", json={"id": acct})).status_code == 200
            assert (await c.get(f"/api/finance/item/{acct}")).status_code == 404
            assert app.state.store.scalar("SELECT COUNT(*) FROM finance_amounts WHERE entry_id = ?", (acct,)) == 0
            ev = (await c.get("/api/events?module=finance")).json()
            assert [e["verb"] for e in ev["events"]][:4] == ["forgot", "ended", "updated", "captured"]
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
            assert item["due_on"] == today.isoformat() and item["next_due"] == today.isoformat()
            assert f"next {day_label(today.isoformat())}" in item["text"]
            assert [a["verb"] for a in item["actions"]] == ["update", "due", "end", "forget"]
            assert "due" not in [a["verb"] for a in (await c.get(f"/api/finance/item/{acct}")).json()["actions"]]
            assert (await c.get(f"/api/finance/item/{acct}")).json()["next_due"] is None   # a date is ignored off a recurring entry

            rows = next(g for g in (await c.get("/api/finance/left")).json()["groups"] if g["label"] == "Recurring")["rows"]
            assert [r["text"] for r in rows] == ["Rent", "Gym", "Domain"]   # soonest first, undated last; by name it would be Domain, Gym, Rent
            assert rows[0]["stampText"] == f"1,800.00 /mo · {day_label(today.isoformat())}"
            assert rows[2]["stampText"] == "120.00 /yr"

            assert (await c.post("/api/finance/action/due", json={"id": acct, "due_on": today.isoformat()})).status_code == 400
            assert (await c.post("/api/finance/action/due", json={"id": domain, "due_on": "nope"})).status_code == 400
            dated = (await c.post("/api/finance/action/due", json={"id": domain, "due_on": later.isoformat()})).json()
            assert dated["next_due"] == later.isoformat()
            assert len((await c.get(f"/api/finance/item/{domain}")).json()["history"]) == 1   # the opening amount only: a date is not an amount
            assert (await c.post("/api/finance/action/due", json={"id": domain, "due_on": ""})).json()["next_due"] is None
            assert (await c.get(f"/api/finance/item/{domain}")).json()["due_on"] is None

            assert (await c.post("/api/finance/action/end", json={"id": rent})).status_code == 200
            assert (await c.get(f"/api/finance/item/{rent}")).json()["next_due"] is None   # an ended payment is not due again
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
