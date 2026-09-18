"""Finance: a hand-kept ledger of accounts, recurring payments, holdings and budgets. Every write is a user action through the runner."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from fastapi import APIRouter, Body, HTTPException, Request

from app.modules import int_id
from app.store import Store, iso, now_iso

router = APIRouter(prefix="/api/finance")

KINDS = ("account", "recurring", "holding", "budget")
CADENCES = ("monthly", "yearly", "weekly")
CHIPS = {"All": None, "Accounts": "account", "Recurring": "recurring", "Holdings": "holding", "Budgets": "budget"}
LABELS = dict(zip(KINDS, ("Accounts", "Recurring", "Holdings", "Budgets")))
SUFFIX = {"monthly": "/mo", "yearly": "/yr", "weekly": "/wk"}
PER_MONTH = {"monthly": Decimal(1), "yearly": Decimal(1) / 12, "weekly": Decimal(52) / 12}
PERIOD_MONTHS = {"monthly": 1, "yearly": 12}
RESOURCE = "finance"


def to_cents(value) -> int:
    try:
        d = Decimal(str(value).replace(",", "").strip())
    except InvalidOperation:
        raise HTTPException(400, "amount must be a number")
    return int((d * 100).to_integral_value(ROUND_HALF_UP))


def fmt(cents: int) -> str:
    return f"{Decimal(cents) / 100:,.2f}"


def to_date(value) -> str | None:
    """An anchor date as YYYY-MM-DD, or None for blank. Anything else is a 400."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise HTTPException(400, "due date must be YYYY-MM-DD")


def day_label(iso_date: str) -> str:
    """10-05-2026, the date format the rest of the UI uses."""
    return date.fromisoformat(iso_date).strftime("%m-%d-%Y")


def amount_text(r: dict) -> str:
    return fmt(r["amount"]) + (f" {SUFFIX[r['cadence']]}" if r["cadence"] else "")


def monthly(r: dict) -> int:
    """A recurring or budget amount normalized to one month, in cents."""
    return int((Decimal(r["amount"]) * PER_MONTH[r["cadence"]]).to_integral_value(ROUND_HALF_UP))


def _month_step(anchor: date, months: int) -> date:
    """The anchor's day that many months on, clamped to the target month's last day."""
    year, month = anchor.year + (anchor.month - 1 + months) // 12, (anchor.month - 1 + months) % 12 + 1
    return date(year, month, min(anchor.day, monthrange(year, month)[1]))


def next_due(r: dict, today: date) -> str | None:
    """The first occurrence on or after today. Every step is measured from the anchor, so a short month
    clamps once instead of shifting the entry for good."""
    anchor, cadence = r["due_on"], r["cadence"]
    if not anchor or not cadence or r["ended_at"]:
        return None
    a = date.fromisoformat(anchor)
    if cadence == "weekly":
        return (a + timedelta(weeks=max(0, -((a - today).days // 7)))).isoformat()
    step = PERIOD_MONTHS[cadence]
    months = (today.year - a.year) * 12 + today.month - a.month
    periods = max(0, -(-months // step))       # whole periods from the anchor to today's month
    d = _month_step(a, periods * step)
    return (d if d >= today else _month_step(a, (periods + 1) * step)).isoformat()


def _row(r: dict, today: date) -> dict:
    """Row.stampText wins over Row.stamp, so the next occurrence rides with the amount in that one slot."""
    nxt = next_due(r, today)
    return {
        "id": r["id"],
        "module": "finance",
        "text": r["name"],
        "stamp": r["updated_at"],
        "stampText": amount_text(r) + (f" · {day_label(nxt)}" if nxt else ""),
        "done": bool(r["ended_at"]),
    }


def _group_by_kind(rows: list[dict], today: date) -> list[dict]:
    """Recurring reads as what is due soonest; undated entries follow, ended ones stay last everywhere."""
    by_kind: dict[str, list[dict]] = {k: [] for k in KINDS}
    for r in rows:
        by_kind[r["kind"]].append(r)
    by_kind["recurring"].sort(key=lambda r: (bool(r["ended_at"]), next_due(r, today) or "9999", r["name"]))
    groups = {k: {"label": LABELS[k], "count": len(v), "rows": [_row(r, today) for r in v]} for k, v in by_kind.items()}
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
    return {"groups": _group_by_kind(rows, date.today()), "chips": list(CHIPS), "chip": chip if chip in CHIPS else "All"}


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
    nxt = next_due(r, date.today())
    actions = [{"verb": "update", "label": "Update", "primary": True}]
    if r["kind"] == "recurring":
        actions.append({"verb": "due", "label": "Set date"})
    if not r["ended_at"]:
        actions.append({"verb": "end", "label": "End"})
    actions.append({"verb": "forget", "label": "Forget", "confirm": "Forget this entry and its history?", "removes": True})
    text = "\n".join(p for p in (r["name"], amount_text(r), f"next {day_label(nxt)}" if nxt else None, r["note"]) if p)
    return {**r, "module": "finance", "text": text, "next_due": nxt, "history": history, "actions": actions}


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
    return {
        "kind": kind, "name": name, "cadence": cadence, "amount": to_cents(body.get("amount", "")),
        "note": (body.get("note") or "").strip() or None,
        "due_on": to_date(body.get("due_on")) if kind == "recurring" else None,
    }


def _check_update(store: Store, body: dict) -> dict:
    r = _get(store, int_id(body))
    note = r["note"] if "note" not in body else ((body.get("note") or "").strip() or None)
    return {"row": r, "amount": to_cents(body.get("amount", "")), "note": note}


def _check_id(store: Store, body: dict) -> dict:
    return {"row": _get(store, int_id(body))}


def _check_due(store: Store, body: dict) -> dict:
    r = _get(store, int_id(body))
    if r["kind"] != "recurring":
        raise HTTPException(400, "only a recurring payment has a due date")
    return {"row": r, "due_on": to_date(body.get("due_on"))}


def _capture(f: dict, ctx) -> dict:
    ts = now_iso()
    with ctx.commit() as conn:
        cur = conn.execute(
            "INSERT INTO finance_entries(kind, name, amount, cadence, note, due_on, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (f["kind"], f["name"], f["amount"], f["cadence"], f["note"], f["due_on"], ts, ts),
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


def _due(f: dict, ctx) -> dict:
    """The anchor only. No amount is changing, so finance_amounts is left alone."""
    r, due_on = f["row"], f["due_on"]
    ts = now_iso()
    with ctx.commit() as conn:
        conn.execute("UPDATE finance_entries SET due_on = ?, updated_at = ? WHERE id = ?", (due_on, ts, r["id"]))
    ctx.event("dated", f"{r['name']}: " + (f"due {due_on}" if due_on else "date cleared"), ref=str(r["id"]))
    return {"id": r["id"], "due_on": due_on, "next_due": next_due({**r, "due_on": due_on}, date.today())}


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


CHECKS = {"capture": _check_capture, "update": _check_update, "due": _check_due, "end": _check_id, "forget": _check_id}
ACTIONS = {"capture": _capture, "update": _update, "due": _due, "end": _end, "forget": _forget}


# ---- shell hooks ---------------------------------------------------------------------------
def numbers(store: Store) -> dict:
    return {"value": store.scalar("SELECT COUNT(*) FROM finance_entries WHERE ended_at IS NULL"), "label": "records"}


def today(store: Store) -> list[dict]:
    start = iso(datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0))
    rows = store.query("SELECT * FROM finance_entries WHERE updated_at >= ? ORDER BY updated_at DESC", (start,))
    return [_row(r, date.today()) for r in rows]


def _context_line(r: dict, today: date) -> str:
    nxt = next_due(r, today)
    return (
        f"  {r['id']} {r['kind']} {r['name']}: {amount_text(r)}"
        + (f" next {nxt}" if nxt else "")
        + (f" ({r['note']})" if r["note"] else "")
    )


def context(store: Store, registry) -> str:
    t = totals(store)
    lines = [
        f"Totals: accounts {fmt(t['accounts'])}; holdings {fmt(t['holdings'])}; "
        f"recurring {fmt(t['monthly_recurring'])} /mo; budgets {fmt(t['monthly_budget'])} /mo",
        "Active entries (id kind name amount cadence, next due where the owner gave a date):",
    ]
    today = date.today()
    lines += [_context_line(r, today) for r in _active(store)] or ["  none"]
    ended = store.query("SELECT name FROM finance_entries WHERE ended_at IS NOT NULL ORDER BY name")
    if ended:
        lines.append("Ended: " + ", ".join(r["name"] for r in ended))
    return "\n".join(lines)
