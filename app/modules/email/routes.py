"""Email: the Gmail mirror. Reads come from the store; every Gmail write is a user action through the runner."""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Body, HTTPException, Request

from app.modules.email import MANIFEST
from app.modules.email.gmail import read_client, write_client
from app.store import Store, iso, parse

router = APIRouter(prefix="/api/email")

RESOURCE = "gmail"
CHIPS = ("All", "Unread", "Flagged", "Priority")
CHIP_LABELS = {"All": (), "Unread": ("UNREAD",), "Flagged": ("STARRED",)}
PRIORITIES = ("high", "normal", "low")
HAS = "EXISTS (SELECT 1 FROM json_each(m.labels) WHERE value = ?)"
HIGH = "m.id IN (SELECT message_id FROM email_triage WHERE priority = 'high')"
# verb -> (labels added, labels removed, event verb)
VERBS = {
    "archive": ((), ("INBOX",), "archived"),
    "trash": (("TRASH",), ("INBOX",), "trashed"),
    "read": ((), ("UNREAD",), "marked read"),
    "unread": (("UNREAD",), (), "marked unread"),
    "star": (("STARRED",), (), "starred"),
    "unstar": ((), ("STARRED",), "unstarred"),
}


def _fts(query: str) -> str:
    return " ".join('"' + t.replace('"', '""') + '"' for t in query.split())


def _where(query: str, chip: str) -> tuple[str, list]:
    """Inbox messages narrowed by chip and search; shared by LEFT, bulk actions and the search tool."""
    where, params = [HAS], ["INBOX"]
    for label in CHIP_LABELS.get(chip, ()):
        where.append(HAS)
        params.append(label)
    if chip == "Priority":
        where.append(HIGH)
    if query.strip():
        where.append("m.n IN (SELECT rowid FROM email_fts WHERE email_fts MATCH ?)")
        params.append(_fts(query))
    return "WHERE " + " AND ".join(where), params


def _labels(r: dict) -> list[str]:
    return json.loads(r["labels"])


def _row(r: dict) -> dict:
    return {
        "id": r["id"],
        "module": "email",
        "text": f"{r['from_name'] or r['from_addr']}: {r['subject']}",
        "stamp": r["internal_date"],
        "leading": {"dot": MANIFEST.hue if "UNREAD" in _labels(r) else "transparent"},
    }


def _group_by_day(rows: list[dict]) -> list[dict]:
    groups: list[dict] = []
    for r in rows:
        label = parse(r["internal_date"]).astimezone().strftime("%d %b")
        if not groups or groups[-1]["label"] != label:
            groups.append({"label": label, "count": 0, "rows": []})
        groups[-1]["rows"].append(_row(r))
        groups[-1]["count"] += 1
    return groups


def _count(store: Store, *labels: str) -> int:
    return store.scalar(f"SELECT COUNT(*) FROM email_messages m WHERE {' AND '.join([HAS] * len(labels))}", labels)


def _get(store: Store, message_id: str) -> dict:
    row = store.one("SELECT * FROM email_messages WHERE id = ?", (message_id,))
    if row is None:
        raise HTTPException(404, "no such message")
    return row


@router.get("/left")
def left(request: Request, query: str = "", chip: str = "All", page: int = 0) -> dict:
    store: Store = request.app.state.store
    size = int(store.setting("ui.page_size"))
    limit = size * (page + 1)
    chip = chip if chip in CHIPS else "All"
    where, params = _where(query, chip)
    total = store.scalar(f"SELECT COUNT(*) FROM email_messages m {where}", tuple(params))
    rows = store.query(f"SELECT m.* FROM email_messages m {where} ORDER BY m.internal_date DESC LIMIT ?", (*params, limit))
    return {
        "groups": _group_by_day(rows),
        "chips": list(CHIPS),
        "chip": chip,
        "showing": f"{min(limit, total):,} / {total:,}",
        "more": total > limit,
        "total": total,
    }


@router.get("/blank")
def blank(request: Request) -> dict:
    store: Store = request.app.state.store
    return {
        "inbox": _count(store, "INBOX"),
        "unread": _count(store, "INBOX", "UNREAD"),
        "flagged": _count(store, "INBOX", "STARRED"),
        "priority": store.scalar(f"SELECT COUNT(*) FROM email_messages m WHERE {HAS} AND {HIGH}", ("INBOX",)),
        "last_sync": store.scalar("SELECT last_run FROM tasks WHERE name = 'email.sync'"),
    }


@router.get("/item/{message_id}")
async def item_route(request: Request, message_id: str) -> dict:
    st = request.app.state
    _get(st.store, message_id)
    try:
        await body_of(st.store, st.config, message_id)
    except Exception as e:  # the snippet stands in and the fetch is retried on the next open
        st.store.event("email", "failed", f"body of {message_id}: {e!r}"[:200], ref=message_id)
    return item(st.store, message_id)


async def body_of(store: Store, config, message_id: str) -> dict:
    """The message's email_bodies row, fetched through the read client on first use. Shared with email_get."""
    row = store.one("SELECT text, html, attachments FROM email_bodies WHERE message_id = ?", (message_id,))
    if row is None:
        gm = read_client(config)
        try:
            b = await gm.body(message_id)
        finally:
            await gm.aclose()
        row = {"text": b["text"], "html": b["html"], "attachments": json.dumps(b["attachments"])}
        store.execute(
            "INSERT OR REPLACE INTO email_bodies(message_id, text, html, attachments) VALUES (?, ?, ?, ?)",
            (message_id, row["text"], row["html"], row["attachments"]),
        )
    return {**row, "attachments": json.loads(row["attachments"])}


def item(store: Store, message_id: str) -> dict:
    r = _get(store, message_id)
    labels = _labels(r)
    unread, starred, in_inbox = "UNREAD" in labels, "STARRED" in labels, "INBOX" in labels
    actions = []
    if in_inbox:
        actions.append({"verb": "archive", "label": "Archive", "primary": True})
        actions.append({"verb": "trash", "label": "Trash", "confirm": "Trash this message?"})
    actions.append({"verb": "read", "label": "Mark read"} if unread else {"verb": "unread", "label": "Mark unread"})
    actions.append({"verb": "unstar", "label": "Unstar"} if starred else {"verb": "star", "label": "Star"})
    actions.append({"verb": "open", "label": "Open in Gmail", "href": f"https://mail.google.com/mail/u/0/#all/{message_id}"})
    b = store.one("SELECT text, html, attachments FROM email_bodies WHERE message_id = ?", (message_id,))
    body = b["text"] if b else r["snippet"]
    tri = store.one("SELECT priority, reason FROM email_triage WHERE message_id = ?", (message_id,))
    return {
        "id": r["id"], "module": "email", "kind": "email",
        "subject": r["subject"], "from_name": r["from_name"], "from_addr": r["from_addr"], "to_addr": r["to_addr"],
        "created_at": r["internal_date"], "text": f"{r['subject']}\n\n{body}",
        "body": body, "html": b["html"] if b else None, "attachments": json.loads(b["attachments"]) if b else [],
        "unread": unread, "starred": starred, "in_inbox": in_inbox,
        "priority": tri["priority"] if tri else None, "reason": tri["reason"] if tri else None,
        "actions": actions,
    }


def _resolve(store: Store, body: dict) -> tuple[list[str], str]:
    """The ids an action applies to, and how to describe them in the event."""
    if body.get("ids"):
        ids = [str(i) for i in body["ids"]]
        if len(ids) == 1:
            return ids, _get(store, ids[0])["subject"][:120]
        return ids, f"{len(ids)} messages"
    f = body.get("filter")
    if f is None:
        return [], ""
    query, chip = str(f.get("query", "")), str(f.get("chip", "All"))
    where, params = _where(query, chip)
    ids = [r["id"] for r in store.query(f"SELECT m.id FROM email_messages m {where}", tuple(params))]
    return ids, f"{len(ids)} messages matching '{query}' · {chip}" if query.strip() else f"{len(ids)} messages · {chip}"


@router.post("/action/{verb}")
async def action(request: Request, verb: str, body: dict = Body(default={})) -> dict:
    st = request.app.state
    if verb not in VERBS:
        raise HTTPException(404, f"unknown action {verb}")
    ids, what = _resolve(st.store, body)
    if not ids:
        raise HTTPException(400, "nothing selected")
    add, remove, past = VERBS[verb]

    async def run(ctx):
        gm = write_client(ctx.config)
        try:
            await gm.modify(ids, add, remove)
        finally:
            await gm.aclose()
        with ctx.commit() as conn:
            for mid in ids:
                row = conn.execute("SELECT labels FROM email_messages WHERE id = ?", (mid,)).fetchone()
                if row is None:
                    continue
                have = json.loads(row["labels"])
                labels = [l for l in have if l not in remove] + [l for l in add if l not in have]
                conn.execute("UPDATE email_messages SET labels = ? WHERE id = ?", (json.dumps(labels), mid))
        ctx.event(past, what, ref=ids[0] if len(ids) == 1 else None)
        return {"count": len(ids)}

    return await st.runner.run_action(f"email.{verb}", "email", RESOURCE, run)


# ---- shell hooks ---------------------------------------------------------------------------
def numbers(store: Store) -> dict:
    return {"value": _count(store, "INBOX", "UNREAD"), "label": "unread"}


def today(store: Store) -> list[dict]:
    start = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = store.query(
        f"SELECT m.* FROM email_messages m WHERE {HAS} AND m.internal_date >= ? ORDER BY m.internal_date DESC", ("INBOX", iso(start))
    )
    return [_row(r) for r in rows]


def context(store: Store, registry) -> str:
    b = {"inbox": _count(store, "INBOX"), "unread": _count(store, "INBOX", "UNREAD"), "flagged": _count(store, "INBOX", "STARRED")}
    last = store.scalar("SELECT last_run FROM tasks WHERE name = 'email.sync'")
    newest = store.query(f"SELECT m.id, m.from_name, m.subject FROM email_messages m WHERE {HAS} ORDER BY m.internal_date DESC LIMIT 10", ("INBOX",))
    high = store.query(
        f"SELECT m.id, m.subject, t.reason FROM email_messages m JOIN email_triage t ON t.message_id = m.id "
        f"WHERE {HAS} AND t.priority = 'high' ORDER BY m.internal_date DESC LIMIT 10", ("INBOX",)
    )
    lines = [f"Inbox: {b['inbox']} messages, {b['unread']} unread, {b['flagged']} starred. Last sync: {last or 'never'}."]
    lines.append("Newest in inbox (id, from, subject):")
    lines += [f"  {r['id']} {r['from_name']}: {r['subject'][:120]}" for r in newest] or ["  none"]
    if high:
        lines.append("Flagged high (id, subject, reason):")
        lines += [f"  {r['id']} {r['subject'][:80]}: {r['reason'][:120]}" for r in high]
    return "\n".join(lines)
