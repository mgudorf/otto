"""Business: plans, people, events, indexed documents and scouted leads. Every write is a user action through the runner."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Request

from app.store import Store, iso, now_iso, parse

router = APIRouter(prefix="/api/business")

KINDS = ("plan", "person", "event")            # what the owner captures; documents and leads arrive by task
CHIPS = {"All": None, "Plans": "plan", "People": "person", "Events": "event", "Documents": "document", "Leads": "lead"}
RESOURCE = "business"


def _row(r: dict) -> dict:
    leading = {"ext": Path(r["ref"]).suffix.lstrip(".")[:4] or "file"} if r["kind"] == "document" else {"kind": r["kind"]}
    return {
        "id": r["id"],
        "module": "business",
        "text": r["text"],
        "stamp": r["created_at"],
        "leading": leading,
        "done": r["kind"] == "lead" and r["status"] == "dismissed",
    }


def _day_label(ts: str) -> str:
    return parse(ts).astimezone().strftime("%d %b")


def _group_by_day(rows: list[dict]) -> list[dict]:
    groups: list[dict] = []
    for r in rows:
        label = _day_label(r["created_at"])
        if not groups or groups[-1]["label"] != label:
            groups.append({"label": label, "count": 0, "rows": []})
        groups[-1]["rows"].append(_row(r))
        groups[-1]["count"] += 1
    return groups


def _search(query: str) -> tuple[list[str], list[str]]:
    """One LIKE per word over text and ref, all words required."""
    where, params = [], []
    for term in query.split():
        where.append("(text LIKE ? OR ref LIKE ?)")
        params += [f"%{term}%", f"%{term}%"]
    return where, params


def _get(store: Store, item_id: int) -> dict:
    row = store.one("SELECT * FROM business_items WHERE id = ?", (item_id,))
    if row is None:
        raise HTTPException(404, "no such item")
    return row


@router.get("/left")
def left(request: Request, query: str = "", chip: str = "All", page: int = 0) -> dict:
    store: Store = request.app.state.store
    size = int(store.setting("ui.page_size"))
    limit = size * (page + 1)
    kind = CHIPS.get(chip)
    where, params = _search(query)
    if kind:
        where.append("kind = ?")
        params.append(kind)
    sql_where = ("WHERE " + " AND ".join(where)) if where else ""
    total = store.scalar(f"SELECT COUNT(*) FROM business_items {sql_where}", tuple(params))
    rows = store.query(f"SELECT * FROM business_items {sql_where} ORDER BY created_at DESC LIMIT ?", (*params, limit))
    return {
        "groups": _group_by_day(rows),
        "chips": list(CHIPS),
        "chip": chip if chip in CHIPS else "All",
        "showing": f"{min(limit, total)} / {total}",
        "more": total > limit,
    }


@router.get("/blank")
def blank(request: Request) -> dict:
    store: Store = request.app.state.store
    counts = {r["kind"]: r["n"] for r in store.query("SELECT kind, COUNT(*) AS n FROM business_items GROUP BY kind")}
    leads = store.query("SELECT id, text, ref, why, created_at FROM business_items WHERE kind = 'lead' AND status = 'open' ORDER BY created_at DESC")
    return {"kinds": list(KINDS), "counts": counts, "leads": leads}


@router.get("/item/{item_id}")
def item_route(request: Request, item_id: int) -> dict:
    return item(request.app.state.store, str(item_id))


def item(store: Store, item_id: str) -> dict:
    r = _get(store, int(item_id))
    actions = []
    if r["kind"] == "document":
        actions.append({"verb": "open", "label": "Open", "primary": True})
    elif r["kind"] == "lead":
        if r["status"] == "open":
            actions.append({"verb": "accept", "label": "Accept", "primary": True})
            actions.append({"verb": "dismiss", "label": "Dismiss"})
        actions.append({"verb": "link", "label": "Open", "href": r["ref"]})
    else:
        if r["ref"]:
            actions.append({"verb": "link", "label": "Open", "href": r["ref"]})
        actions.append({"verb": "forget", "label": "Forget", "confirm": "Forget this item?"})
    return {**r, "module": "business", "actions": actions}


@router.post("/action/{verb}")
async def action(request: Request, verb: str, body: dict = Body(default={})) -> dict:
    st = request.app.state
    store: Store = st.store
    fn = ACTIONS.get(verb)
    if fn is None:
        raise HTTPException(404, f"unknown action {verb}")
    _validate(store, verb, body)

    async def run(ctx):
        return fn(store, body, ctx)

    return await st.runner.run_action(f"business.{verb}", "business", RESOURCE, run)


def _validate(store: Store, verb: str, body: dict) -> None:
    """Reject bad input before the job is queued, so the client sees a 400 rather than a failed job."""
    if verb == "capture":
        if body.get("kind", "plan") not in KINDS:
            raise HTTPException(400, "bad kind")
        if not (body.get("text") or "").strip():
            raise HTTPException(400, "empty text")
        return
    r = _get(store, int(body.get("id", 0)))
    if verb == "forget" and r["kind"] == "document":
        raise HTTPException(400, "delete the file instead; the folder is re-indexed")
    if verb == "lead" and (r["kind"] != "lead" or body.get("status") not in ("accepted", "dismissed")):
        raise HTTPException(400, "a lead and a status of accepted or dismissed are required")
    if verb == "open" and (r["kind"] != "document" or not r["ref"] or not Path(r["ref"]).is_file()):
        raise HTTPException(400, "not a document on disk")


def _capture(store: Store, body: dict, ctx) -> dict:
    kind = body.get("kind", "plan")
    text = body["text"].strip()
    ref = (body.get("ref") or "").strip() or None
    ts = now_iso()
    with ctx.commit() as conn:
        cur = conn.execute(
            "INSERT INTO business_items(kind, text, ref, created_at, updated_at) VALUES (?, ?, ?, ?, ?)", (kind, text, ref, ts, ts)
        )
    ctx.event("captured", f"{kind}: {text[:120]}", ref=str(cur.lastrowid))
    return {"id": cur.lastrowid}


def _forget(store: Store, body: dict, ctx) -> dict:
    r = _get(store, int(body["id"]))
    with ctx.commit() as conn:
        conn.execute("DELETE FROM business_items WHERE id = ?", (r["id"],))
    ctx.event("forgot", f"{r['kind']}: {r['text'][:120]}", ref=str(r["id"]))
    return {"id": r["id"]}


def _lead(store: Store, body: dict, ctx) -> dict:
    status = body["status"]
    r = _get(store, int(body["id"]))
    with ctx.commit() as conn:
        conn.execute("UPDATE business_items SET status = ?, updated_at = ? WHERE id = ?", (status, now_iso(), r["id"]))
    ctx.event(status, r["text"][:120], ref=str(r["id"]))
    return {"id": r["id"], "status": status}


def _open(store: Store, body: dict, ctx) -> dict:
    r = _get(store, int(body["id"]))
    os.startfile(r["ref"])
    ctx.event("opened", r["text"][:120], ref=str(r["id"]))
    return {"id": r["id"]}


ACTIONS = {"capture": _capture, "forget": _forget, "lead": _lead, "open": _open}


# ---- shell hooks ---------------------------------------------------------------------------
def numbers(store: Store) -> dict:
    return {"value": store.scalar("SELECT COUNT(*) FROM business_items WHERE kind = 'lead' AND status = 'open'"), "label": "leads"}


def today(store: Store) -> list[dict]:
    start = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = store.query("SELECT * FROM business_items WHERE created_at >= ? ORDER BY created_at DESC", (iso(start),))
    return [_row(r) for r in rows]


def context(store: Store, registry) -> str:
    counts = store.query("SELECT kind, COUNT(*) AS n FROM business_items GROUP BY kind ORDER BY kind")
    plans = store.query("SELECT id, text FROM business_items WHERE kind = 'plan' ORDER BY created_at")
    leads = store.query("SELECT id, text, ref FROM business_items WHERE kind = 'lead' AND status = 'open' ORDER BY created_at DESC")
    docs = store.query("SELECT id, text, ref FROM business_items WHERE kind = 'document' ORDER BY text")
    lines = ["Counts: " + (", ".join(f"{c['n']} {c['kind']}" for c in counts) or "none")]
    lines.append("Plans (id, text):")
    lines += [f"  {p['id']}: {p['text'][:500]}" for p in plans] or ["  none"]
    if leads:
        lines.append("Open leads: " + "; ".join(f"#{l['id']} {l['text'][:100]} <{l['ref']}>" for l in leads))
    if docs:
        lines.append("Documents (readable with Read): " + "; ".join(f"#{d['id']} {d['ref']}" for d in docs))
    return "\n".join(lines)
