"""Finance: a hand-kept ledger of accounts, recurring payments, holdings and budgets. Every write is a user action through the runner."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from fastapi import APIRouter, Body, HTTPException, Request

from app.modules import int_id
from app.store import Store, iso, now_iso, parse, tags_for

router = APIRouter(prefix="/api/finance")

KINDS = ("account", "recurring", "holding", "budget")
CADENCES = ("monthly", "yearly", "weekly")
LABELS = dict(zip(KINDS, ("Accounts", "Recurring", "Holdings", "Budgets")))
SUFFIX = {"monthly": "/mo", "yearly": "/yr", "weekly": "/wk"}
PER_MONTH = {"monthly": Decimal(1), "yearly": Decimal(1) / 12, "weekly": Decimal(52) / 12}
PERIOD_MONTHS = {"monthly": 1, "yearly": 12}
HISTORY = 12                                   # the amounts one open entry carries; finance_amounts keeps every one
RESOURCE = "finance"
FACET = "finance"
TYPE = "ledger"


def to_cents(value) -> int:
    try:
        d = Decimal(str(value).replace(",", "").strip())
    except InvalidOperation:
        raise HTTPException(400, "amount must be a number")
    return int((d * 100).to_integral_value(ROUND_HALF_UP))


def fmt(cents: int) -> str:
    return f"{Decimal(cents) / 100:,.2f}"


def money(cents: int) -> str:
    """What the feed and the page show: the amount with its currency sign."""
    return f"${fmt(cents)}"


def day(ts: str) -> str:
    """A history stamp the way the owner reads dates: month first."""
    return parse(ts).astimezone().strftime("%m-%d-%Y")


def _when(ts: str) -> str:
    """A stored moment on the owner's own clock, so the feed orders it against every other module's rows."""
    return parse(ts).astimezone().strftime("%Y-%m-%dT%H:%M")


def to_date(value) -> str | None:
    """An anchor date as YYYY-MM-DD, or None for blank. Anything else is a 400."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise HTTPException(400, "due date must be YYYY-MM-DD")


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


def _verbs(r: dict) -> list[list[str]]:
    """What the facet allows on the entry: only a recurring payment has a date, and an ended one cannot end twice."""
    out = [["update", "Update amount"]]
    if r["kind"] == "recurring":
        out.append(["due", "Set date"])
    if not r["ended_at"]:
        out.append(["end", "End"])
    out.append(["forget", "Forget"])
    return out


def _row(r: dict, today: date, tags: list[str]) -> dict:
    """One ROW: the kind is a plain tag, the amount reads as money, the date is the next occurrence.
    The note travels with the row so typing a word from it finds the entry."""
    return {
        "id": r["id"],
        "module": "finance",
        "title": r["name"],
        "when": _when(r["updated_at"]),
        "fixed": [FACET],
        "tags": [r["kind"], *(t for t in tags if t != r["kind"])],
        "type": TYPE,
        "verbs": _verbs(r),
        "snip": r["cadence"],
        "amount": money(r["amount"]),
        "due": next_due(r, today),
        "dim": bool(r["ended_at"]),
        "note": r["note"],
    }


def _rows(store: Store, entries: list[dict], today: date) -> list[dict]:
    tags = tags_for(store, "finance", [r["id"] for r in entries])
    return [_row(r, today, tags[r["id"]]) for r in entries]


def _group_by_kind(store: Store, entries: list[dict], today: date) -> list[dict]:
    """Recurring reads as what is due soonest; undated entries follow, ended ones stay last everywhere."""
    by_kind: dict[str, list[dict]] = {k: [] for k in KINDS}
    for r in entries:
        by_kind[r["kind"]].append(r)
    by_kind["recurring"].sort(key=lambda r: (bool(r["ended_at"]), next_due(r, today) or "9999", r["name"]))
    groups = {k: {"label": LABELS[k], "count": len(v), "rows": _rows(store, v, today)} for k, v in by_kind.items()}
    return [g for g in groups.values() if g["rows"]]


def _like(term: str) -> str:
    """A typed word as a needle: % , _ and the escape itself stand for themselves."""
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _search(query: str) -> tuple[list[str], list[str]]:
    """One LIKE per word over name and note, all words required."""
    where, params = [], []
    for term in query.split():
        where.append("(name LIKE ? ESCAPE '\\' OR COALESCE(note, '') LIKE ? ESCAPE '\\')")
        params += [_like(term)] * 2
    return where, params


def _get(store: Store, entry_id: int) -> dict:
    row = store.one("SELECT * FROM finance_entries WHERE id = ?", (entry_id,))
    if row is None:
        raise HTTPException(404, "no such entry")
    return row


def _active(store: Store) -> list[dict]:
    return store.query("SELECT * FROM finance_entries WHERE ended_at IS NULL ORDER BY name")


def totals(store: Store) -> dict:
    active = _active(store)
    return {
        "accounts": sum(r["amount"] for r in active if r["kind"] == "account"),
        "holdings": sum(r["amount"] for r in active if r["kind"] == "holding"),
        "monthly_recurring": sum(monthly(r) for r in active if r["kind"] == "recurring"),
        "monthly_budget": sum(monthly(r) for r in active if r["kind"] == "budget"),
    }


@router.get("/left")
def left(request: Request, query: str = "") -> dict:
    """Every entry the typed words reach, grouped by kind. The ledger is small, so nothing is ever held back."""
    store: Store = request.app.state.store
    where, params = _search(query)
    sql_where = ("WHERE " + " AND ".join(where)) if where else ""
    entries = store.query(f"SELECT * FROM finance_entries {sql_where} ORDER BY ended_at IS NOT NULL, name", tuple(params))
    return {"groups": _group_by_kind(store, entries, date.today()), "more": False}


@router.get("/blank")
def blank(request: Request) -> dict:
    """What the page needs beyond its rows: the four totals, the choices the capture form offers, and the
    word each kind goes by, so the chips and the group headers read what this module calls them."""
    store: Store = request.app.state.store
    return {"kinds": list(KINDS), "labels": dict(LABELS), "cadences": list(CADENCES), "totals": totals(store)}


@router.get("/item/{entry_id}")
def item_route(request: Request, entry_id: int) -> dict:
    return item(request.app.state.store, str(entry_id))


def item(store: Store, entry_id: str) -> dict:
    """The ROW plus what only the open entry needs: the anchor date the Set date box edits, its recent amounts."""
    r = _get(store, int(entry_id))
    history = store.query(
        "SELECT ts, amount FROM finance_amounts WHERE entry_id = ? ORDER BY ts DESC LIMIT ?", (r["id"], HISTORY)
    )
    kv = ([["Cadence", r["cadence"]]] if r["cadence"] else []) + ([["Note", r["note"]]] if r["note"] else [])
    row = _rows(store, [r], date.today())[0]
    return {**row, "due_on": r["due_on"], "kv": kv, "hist": [[day(h["ts"]), money(h["amount"])] for h in history]}


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
    entries = store.query("SELECT * FROM finance_entries WHERE updated_at >= ? ORDER BY updated_at DESC", (start,))
    return _rows(store, entries, date.today())


def rows(store: Store, limit: int = 200) -> list[dict]:
    """Every entry, most recently touched first: what the tag page, Home's Recent and the Graph read."""
    entries = store.query("SELECT * FROM finance_entries ORDER BY updated_at DESC, id DESC LIMIT ?", (max(1, limit),))
    return _rows(store, entries, date.today())


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
