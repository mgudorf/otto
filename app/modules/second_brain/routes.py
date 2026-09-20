"""Second Brain: capture, list, inspect, tag, forget. Every write is a user action through the runner."""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Body, HTTPException, Request

from app.modules import int_id
from app.store import Store, now_iso, parse, tags_for

router = APIRouter(prefix="/api/second_brain")

KINDS = ("note", "link", "quote", "fact", "task")
CHIPS = {"All": None, "Tasks": "task"}   # the kinds stay in the table for the agent; the page names only tasks
SUGGESTION = "s"                                   # a suggestion's row id, "s12"; an item carries the bare integer
RESOURCE = "second_brain"
MODULE = "second_brain"


def _when(ts: str) -> str:
    """A ROW's `when`: the owner's wall clock, so the page groups by their day and shows their time."""
    return parse(ts).astimezone().strftime("%Y-%m-%dT%H:%M")


def _row(r: dict, tags: list[str]) -> dict:
    """One item as a ROW: what it is drives `fixed`, the owner's own tags stay editable."""
    return {
        "id": r["id"], "module": MODULE, "title": r["text"], "when": _when(r["created_at"]),
        "kind": r["kind"], "fixed": [r["kind"]], "tags": tags, "done": bool(r["done_at"]),
    }


def _rows(store: Store, rs: list[dict]) -> list[dict]:
    tags = tags_for(store, MODULE, [r["id"] for r in rs])
    return [_row(r, tags[r["id"]]) for r in rs]


def _day_label(when: str) -> str:
    return f"{when[5:7]}-{when[8:10]}-{when[:4]}"


def _group_by_day(store: Store, rs: list[dict]) -> list[dict]:
    """A listed row carries its verbs, so a button on the row asks what the same button in the pane asks."""
    groups: list[dict] = []
    verbs = {r["id"]: _actions(r) for r in rs}
    for row in _rows(store, rs):
        label = _day_label(row["when"])
        if not groups or groups[-1]["label"] != label:
            groups.append({"label": label, "count": 0, "rows": []})
        groups[-1]["rows"].append({**row, "actions": verbs[row["id"]]})
        groups[-1]["count"] += 1
    return groups


def _fts(query: str) -> str:
    return " ".join('"' + t.replace('"', '""') + '"' for t in query.split())


def _tags(store: Store, item_id: int) -> list[str]:
    return tags_for(store, MODULE, [item_id])[item_id]


def _get(store: Store, item_id: int) -> dict:
    row = store.one("SELECT * FROM second_brain_items WHERE id = ?", (item_id,))
    if row is None:
        raise HTTPException(404, "no such item")
    return row


def _suggestion_id(value) -> int:
    """The integer behind an "s12" row id. Anything else is not a suggestion, so it is a 404 rather than a 500."""
    text = str(value or "")
    if not text.startswith(SUGGESTION) or not text[len(SUGGESTION):].isdigit():
        raise HTTPException(404, "no such suggestion")
    return int(text[len(SUGGESTION):])


def _suggestion_actions(r: dict) -> list[dict]:
    """A suggestion waits on a yes or a no; once it has one it offers nothing. The no is final, so it asks first."""
    if r["status"] != "open":
        return []
    return [{"verb": "accept", "label": "Accept", "primary": True, "removes": True},
            {"verb": "dismiss", "label": "Dismiss", "confirm": "Dismiss this suggestion?", "removes": True}]


def _actions(r: dict) -> list[dict]:
    """The verbs an item offers, and the question the destructive one must ask before it runs."""
    actions = []
    if r["kind"] == "link":
        actions.append({"verb": "open", "label": "Open", "primary": True, "href": r["text"].split()[0]})
    elif r["kind"] == "task":
        actions.append({"verb": "reopen", "label": "Reopen", "primary": True} if r["done_at"] else {"verb": "done", "label": "Done", "primary": True})
    actions.append({"verb": "forget", "label": "Forget", "confirm": "Forget this item?", "removes": True})
    return actions


def _suggestion_row(r: dict) -> dict:
    """A suggestion as a ROW: no row of the owner's stands behind it, so `taggable` false keeps every tagging path off it."""
    return {"id": f"{SUGGESTION}{r['id']}", "module": MODULE, "title": r["text"], "when": _when(r["created_at"]),
            "kind": "suggestion", "fixed": ["suggestion"], "tags": [], "taggable": False, "actions": _suggestion_actions(r)}


@router.get("/left")
def left(request: Request, query: str = "", chip: str = "All", page: int = 0) -> dict:
    store: Store = request.app.state.store
    size = int(store.setting("ui.page_size"))
    limit = size * (page + 1)
    kind = CHIPS.get(chip)
    where, params = [], []
    if kind:
        where.append("m.kind = ?")
        params.append(kind)
    if query.strip():
        where.append("m.id IN (SELECT rowid FROM second_brain_fts WHERE second_brain_fts MATCH ?)")
        params.append(_fts(query))
    sql_where = ("WHERE " + " AND ".join(where)) if where else ""
    total = store.scalar(f"SELECT COUNT(*) FROM second_brain_items m {sql_where}", tuple(params))
    found = store.query(f"SELECT m.* FROM second_brain_items m {sql_where} ORDER BY m.created_at DESC LIMIT ?", (*params, limit))
    return {
        "groups": _group_by_day(store, found),
        "chips": list(CHIPS),
        "chip": chip if chip in CHIPS else "All",
        "more": total > limit,
    }


@router.get("/blank")
def blank(request: Request) -> dict:
    return {"suggestions": queue(request.app.state.store)}


@router.get("/item/{item_id}")
def item_route(request: Request, item_id: str) -> dict:
    return item(request.app.state.store, item_id)


def _suggestion_item(store: Store, sid: int) -> dict:
    r = store.one("SELECT * FROM second_brain_suggestions WHERE id = ?", (sid,))
    if r is None:
        raise HTTPException(404, "no such suggestion")
    return {**_suggestion_row(r), "status": r["status"]}


def item(store: Store, item_id: str) -> dict:
    if not str(item_id).isdigit():
        return _suggestion_item(store, _suggestion_id(item_id))
    r = _get(store, int(item_id))
    return {**_row(r, _tags(store, r["id"])), "actions": _actions(r)}


@router.post("/action/{verb}")
async def action(request: Request, verb: str, body: dict = Body(default={})) -> dict:
    st = request.app.state
    store: Store = st.store
    prepare = ACTIONS.get(verb)
    if prepare is None:
        raise HTTPException(404, f"unknown action {verb}")
    write = prepare(store, body)  # validates here, so a bad request answers 400 / 404 and never becomes a failed job

    async def run(ctx):
        return write(ctx)

    return await st.runner.run_action(f"second_brain.{verb}", "second_brain", RESOURCE, run)


# Each action validates against the store first and returns the write to run inside the job.
def _capture(store: Store, body: dict):
    kind = body.get("kind", "note")
    text = (body.get("text") or "").strip()
    tags = [t.strip() for t in body.get("tags", []) if t.strip()]
    if kind not in KINDS:
        raise HTTPException(400, "bad kind")
    if not text:
        raise HTTPException(400, "empty text")

    def write(ctx) -> dict:
        ts = now_iso()
        with ctx.commit() as conn:
            cur = conn.execute("INSERT INTO second_brain_items(kind, text, created_at, updated_at) VALUES (?, ?, ?, ?)", (kind, text, ts, ts))
            for t in tags:
                conn.execute("INSERT OR IGNORE INTO second_brain_tags(item_id, tag) VALUES (?, ?)", (cur.lastrowid, t))
        ctx.event("captured", f"{kind}: {text[:120]}", ref=str(cur.lastrowid))
        return {"id": cur.lastrowid}

    return write


def _forget(store: Store, body: dict):
    r = _get(store, int_id(body))

    def write(ctx) -> dict:
        with ctx.commit() as conn:
            conn.execute("DELETE FROM second_brain_items WHERE id = ?", (r["id"],))
        ctx.event("forgot", f"{r['kind']}: {r['text'][:120]}", ref=str(r["id"]))
        return {"id": r["id"]}

    return write


def _tag(store: Store, body: dict):
    r = _get(store, int_id(body))
    tags = [t.strip() for t in body.get("tags", []) if t.strip()]

    def write(ctx) -> dict:
        with ctx.commit() as conn:
            for t in tags:
                conn.execute("INSERT OR IGNORE INTO second_brain_tags(item_id, tag) VALUES (?, ?)", (r["id"], t))
            conn.execute("UPDATE second_brain_items SET updated_at = ? WHERE id = ?", (now_iso(), r["id"]))
        ctx.event("tagged", f"{', '.join(tags)} on {r['text'][:80]}", ref=str(r["id"]))
        return {"id": r["id"], "tags": _tags(store, r["id"])}

    return write


def _untag(store: Store, body: dict):
    r = _get(store, int_id(body))

    def write(ctx) -> dict:
        with ctx.commit() as conn:
            conn.execute("DELETE FROM second_brain_tags WHERE item_id = ? AND tag = ?", (r["id"], body.get("tag", "")))
        return {"id": r["id"], "tags": _tags(store, r["id"])}

    return write


def _done(store: Store, body: dict):
    r = _get(store, int_id(body))

    def write(ctx) -> dict:
        with ctx.commit() as conn:
            conn.execute("UPDATE second_brain_items SET done_at = ?, updated_at = ? WHERE id = ?", (now_iso(), now_iso(), r["id"]))
        ctx.event("completed", r["text"][:120], ref=str(r["id"]))
        return {"id": r["id"]}

    return write


def _reopen(store: Store, body: dict):
    r = _get(store, int_id(body))

    def write(ctx) -> dict:
        with ctx.commit() as conn:
            conn.execute("UPDATE second_brain_items SET done_at = NULL, updated_at = ? WHERE id = ?", (now_iso(), r["id"]))
        ctx.event("reopened", r["text"][:120], ref=str(r["id"]))
        return {"id": r["id"]}

    return write


def _decide(status: str):
    """One verb per decision, each taking {id}: what the page posts is what Home posts."""

    def prepare(store: Store, body: dict):
        sid = _suggestion_id(body.get("id"))
        if store.one("SELECT id FROM second_brain_suggestions WHERE id = ?", (sid,)) is None:
            raise HTTPException(404, "no such suggestion")

        def write(ctx) -> dict:
            with ctx.commit() as conn:
                conn.execute("UPDATE second_brain_suggestions SET status = ? WHERE id = ?", (status, sid))
            ctx.event(status, f"suggestion {sid}", ref=str(sid))
            return {"id": f"{SUGGESTION}{sid}", "status": status}

        return write

    return prepare


ACTIONS = {
    "capture": _capture, "forget": _forget, "tag": _tag, "untag": _untag, "done": _done, "reopen": _reopen,
    "accept": _decide("accepted"), "dismiss": _decide("dismissed"),
}


# ---- shell hooks ---------------------------------------------------------------------------
def numbers(store: Store) -> dict:
    return {"value": store.scalar("SELECT COUNT(*) FROM second_brain_items"), "label": "items"}


def queue(store: Store) -> list[dict]:
    """Every suggestion still waiting on a yes or no, newest first; Home lists these under Review."""
    open_rows = store.query("SELECT * FROM second_brain_suggestions WHERE status = 'open' ORDER BY created_at DESC, id DESC")
    return [_suggestion_row(r) for r in open_rows]


def today(store: Store) -> list[dict]:
    start = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    from app.store import iso

    return _rows(store, store.query("SELECT * FROM second_brain_items WHERE created_at >= ? ORDER BY created_at DESC", (iso(start),)))


def rows(store: Store, limit: int = 200) -> list[dict]:
    """Every captured item as a ROW, newest first: what the tag intersection and Home's Recent read."""
    return _rows(store, store.query("SELECT * FROM second_brain_items ORDER BY created_at DESC, id DESC LIMIT ?", (limit,)))


def context(store: Store, registry) -> str:
    counts = store.query("SELECT kind, COUNT(*) AS n FROM second_brain_items GROUP BY kind ORDER BY kind")
    recent = store.query("SELECT id, kind, text, created_at FROM second_brain_items ORDER BY created_at DESC LIMIT 10")
    open_s = queue(store)                                      # the "s12" ids the page and Home open
    lines = ["Counts: " + (", ".join(f"{c['n']} {c['kind']}" for c in counts) or "none")]
    lines.append("Most recent (id, kind, text):")
    lines += [f"  {r['id']} {r['kind']}: {r['text'][:140]}" for r in recent] or ["  none"]
    if open_s:
        lines.append("Open suggestions: " + "; ".join(f"#{s['id']} {s['title'][:100]}" for s in open_s))
    return "\n".join(lines)
