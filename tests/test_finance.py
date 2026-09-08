"""Finance through the real app: the ledger end to end, and proof the agent only reads."""

from app.daemon import build
from app.modules.finance import MANIFEST
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


def test_finance_agent_reads_only(config):
    assert MANIFEST.schedules == () and MANIFEST.agent.write_tools == ()

    async def main():
        app = build(config)
        read = {t.name for t in await app.state.mcp_read.list_tools() if t.name.startswith("finance_")}
        full = {t.name for t in await app.state.mcp_full.list_tools() if t.name.startswith("finance_")}
        assert read == full == set(MANIFEST.agent.read_tools)
        app.state.store.close()

    run(main())
