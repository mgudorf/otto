"""Finance: a hand-kept ledger of accounts, recurring payments, holdings and budgets. Every write is a user action through the runner."""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from fastapi import APIRouter, Body, HTTPException, Request

from app.modules.finance import MANIFEST
from app.store import Store, iso, now_iso

router = APIRouter(prefix="/api/finance")

KINDS = ("account", "recurring", "holding", "budget")
CADENCES = ("monthly", "yearly", "weekly")
CHIPS = {"All": None, "Accounts": "account", "Recurring": "recurring", "Holdings": "holding", "Budgets": "budget"}
LABELS = dict(zip(KINDS, ("Accounts", "Recurring", "Holdings", "Budgets")))
SUFFIX = {"monthly": "/mo", "yearly": "/yr", "weekly": "/wk"}
PER_MONTH = {"monthly": Decimal(1), "yearly": Decimal(1) / 12, "weekly": Decimal(52) / 12}
RESOURCE = "finance"
HUE = MANIFEST.hue


def to_cents(value) -> int:
    try:
        d = Decimal(str(value).replace(",", "").strip())
    except InvalidOperation:
        raise HTTPException(400, "amount must be a number")
    return int((d * 100).to_integral_value(ROUND_HALF_UP))


def fmt(cents: int) -> str:
    return f"{Decimal(cents) / 100:,.2f}"


def amount_text(r: dict) -> str:
    return fmt(r["amount"]) + (f" {SUFFIX[r['cadence']]}" if r["cadence"] else "")


def monthly(r: dict) -> int:
    """A recurring or budget amount normalized to one month, in cents."""
    return int((Decimal(r["amount"]) * PER_MONTH[r["cadence"]]).to_integral_value(ROUND_HALF_UP))


def _row(r: dict) -> dict:
    return {
        "id": r["id"],
        "module": "finance",
        "text": r["name"],
        "stamp": r["updated_at"],
        "stampText": amount_text(r),
        "leading": {"dot": "transparent" if r["ended_at"] else HUE},
        "done": bool(r["ended_at"]),
    }


def _group_by_kind(rows: list[dict]) -> list[dict]:
    groups = {k: {"label": LABELS[k], "count": 0, "rows": []} for k in KINDS}
    for r in rows:
        groups[r["kind"]]["rows"].append(_row(r))
        groups[r["kind"]]["count"] += 1
    return [g for g in groups.values() if g["rows"]]


def _search(query: str) -> tuple[list[str], list[str]]:
    """One LIKE per word over name and note, all words required."""
    where, params = [], []
    for term in query.split():
        where.append("(name LIKE ? OR COALESCE(note, '') LIKE ?)")
        params += [f"%{term}%", f"%{term}%"]
    return where, params


def _get(store: Store, entry_id: int) -> dict:
    row = store.one("SELECT * FROM finance_entries WHERE id = ?", (entry_id,))
    if row is None:
        raise HTTPException(404, "no such entry")
    return row


def _active(store: Store) -> list[dict]:
    return store.query("SELECT * FROM finance_entries WHERE ended_at IS NULL ORDER BY name")


def totals(store: Store) -> dict:
    rows = _active(store)
    return {
        "accounts": sum(r["amount"] for r in rows if r["kind"] == "account"),
        "holdings": sum(r["amount"] for r in rows if r["kind"] == "holding"),
        "monthly_recurring": sum(monthly(r) for r in rows if r["kind"] == "recurring"),
        "monthly_budget": sum(monthly(r) for r in rows if r["kind"] == "budget"),
    }


@router.get("/left")
def left(request: Request, query: str = "", chip: str = "All") -> dict:
    store: Store = request.app.state.store
    kind = CHIPS.get(chip)
    where, params = _search(query)
    if kind:
        where.append("kind = ?")
        params.append(kind)
    sql_where = ("WHERE " + " AND ".join(where)) if where else ""
    rows = store.query(f"SELECT * FROM finance_entries {sql_where} ORDER BY ended_at IS NOT NULL, name", tuple(params))
    return {"groups": _group_by_kind(rows), "chips": list(CHIPS), "chip": chip if chip in CHIPS else "All"}


@router.get("/blank")
def blank(request: Request) -> dict:
    store: Store = request.app.state.store
    counts = {r["kind"]: r["n"] for r in store.query("SELECT kind, COUNT(*) AS n FROM finance_entries WHERE ended_at IS NULL GROUP BY kind")}
    return {"kinds": list(KINDS), "cadences": list(CADENCES), "counts": counts, "totals": totals(store)}


@router.get("/item/{entry_id}")
def item_route(request: Request, entry_id: int) -> dict:
    return item(request.app.state.store, str(entry_id))


def item(store: Store, entry_id: str) -> dict:
    r = _get(store, int(entry_id))
    history = store.query("SELECT ts, amount FROM finance_amounts WHERE entry_id = ? ORDER BY ts DESC", (r["id"],))
    actions = [{"verb": "update", "label": "Update", "primary": True}]
    if not r["ended_at"]:
        actions.append({"verb": "end", "label": "End"})
    actions.append({"verb": "forget", "label": "Forget", "confirm": "Forget this entry and its history?"})
    text = "\n".join(p for p in (r["name"], amount_text(r), r["note"]) if p)
    return {**r, "module": "finance", "text": text, "history": history, "actions": actions}


@router.post("/action/{verb}")
async def action(request: Request, verb: str, body: dict = Body(default={})) -> dict:
    st = request.app.state
    store: Store = st.store
    fn = ACTIONS.get(verb)
    if fn is None:
        raise HTTPException(404, f"unknown action {verb}")
    fields = CHECKS[verb](store, body)   # 400 and 404 happen here, before the job is queued

    async def run(ctx):
        return fn(fields, ctx)

    return await st.runner.run_action(f"finance.{verb}", "finance", RESOURCE, run)


def _check_capture(store: Store, body: dict) -> dict:
    kind = body.get("kind", "account")
    name = (body.get("name") or "").strip()
    cadence = body.get("cadence") if kind in ("recurring", "budget") else None
    if kind not in KINDS:
        raise HTTPException(400, "bad kind")
    if not name:
        raise HTTPException(400, "empty name")
    if kind in ("recurring", "budget") and cadence not in CADENCES:
        raise HTTPException(400, "cadence must be monthly, yearly or weekly")
    return {"kind": kind, "name": name, "cadence": cadence, "note": (body.get("note") or "").strip() or None, "amount": to_cents(body.get("amount", ""))}


def _check_update(store: Store, body: dict) -> dict:
    r = _get(store, int(body["id"]))
    note = r["note"] if "note" not in body else ((body.get("note") or "").strip() or None)
    return {"row": r, "amount": to_cents(body.get("amount", "")), "note": note}


def _check_id(store: Store, body: dict) -> dict:
    return {"row": _get(store, int(body["id"]))}


def _capture(f: dict, ctx) -> dict:
    ts = now_iso()
    with ctx.commit() as conn:
        cur = conn.execute(
            "INSERT INTO finance_entries(kind, name, amount, cadence, note, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (f["kind"], f["name"], f["amount"], f["cadence"], f["note"], ts, ts),
        )
        conn.execute("INSERT INTO finance_amounts(entry_id, ts, amount) VALUES (?, ?, ?)", (cur.lastrowid, ts, f["amount"]))
    ctx.event("captured", f"{f['kind']}: {f['name']} {fmt(f['amount'])}", ref=str(cur.lastrowid))
    return {"id": cur.lastrowid}


def _update(f: dict, ctx) -> dict:
    r, amount = f["row"], f["amount"]
    ts = now_iso()
    with ctx.commit() as conn:
        conn.execute("UPDATE finance_entries SET amount = ?, note = ?, updated_at = ? WHERE id = ?", (amount, f["note"], ts, r["id"]))
        conn.execute("INSERT INTO finance_amounts(entry_id, ts, amount) VALUES (?, ?, ?)", (r["id"], ts, amount))
    ctx.event("updated", f"{r['name']}: {fmt(r['amount'])} -> {fmt(amount)}", ref=str(r["id"]))
    return {"id": r["id"], "amount": amount}


def _end(f: dict, ctx) -> dict:
    r = f["row"]
    ts = now_iso()
    with ctx.commit() as conn:
        conn.execute("UPDATE finance_entries SET ended_at = ?, updated_at = ? WHERE id = ?", (ts, ts, r["id"]))
    ctx.event("ended", f"{r['kind']}: {r['name']}", ref=str(r["id"]))
    return {"id": r["id"]}


def _forget(f: dict, ctx) -> dict:
    r = f["row"]
    with ctx.commit() as conn:
        conn.execute("DELETE FROM finance_entries WHERE id = ?", (r["id"],))
    ctx.event("forgot", f"{r['kind']}: {r['name']}", ref=str(r["id"]))
    return {"id": r["id"]}


CHECKS = {"capture": _check_capture, "update": _check_update, "end": _check_id, "forget": _check_id}
ACTIONS = {"capture": _capture, "update": _update, "end": _end, "forget": _forget}


# ---- shell hooks ---------------------------------------------------------------------------
def numbers(store: Store) -> dict:
    return {"value": store.scalar("SELECT COUNT(*) FROM finance_entries WHERE ended_at IS NULL"), "label": "records"}


def today(store: Store) -> list[dict]:
    start = iso(datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0))
    rows = store.query("SELECT * FROM finance_entries WHERE updated_at >= ? ORDER BY updated_at DESC", (start,))
    return [_row(r) for r in rows]


def context(store: Store, registry) -> str:
    t = totals(store)
    lines = [
        f"Totals: accounts {fmt(t['accounts'])}; holdings {fmt(t['holdings'])}; "
        f"recurring {fmt(t['monthly_recurring'])} /mo; budgets {fmt(t['monthly_budget'])} /mo",
        "Active entries (id kind name amount cadence):",
    ]
    active = _active(store)
    lines += [f"  {r['id']} {r['kind']} {r['name']}: {amount_text(r)}" + (f" ({r['note']})" if r["note"] else "") for r in active] or ["  none"]
    ended = store.query("SELECT name FROM finance_entries WHERE ended_at IS NOT NULL ORDER BY name")
    if ended:
        lines.append("Ended: " + ", ".join(r["name"] for r in ended))
    return "\n".join(lines)
