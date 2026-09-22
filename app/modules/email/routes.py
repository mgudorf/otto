"""Email: the Gmail mirror. Reads come from the store; every Gmail write is a user action through the runner."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from html import escape

from fastapi import APIRouter, Body, HTTPException, Request

from app.modules.email.gmail import consent_expires, read_client, write_client
from app.store import Store, iso, now, parse, tags_for

router = APIRouter(prefix="/api/email")

RESOURCE = "gmail"
FACET = "email"
GMAIL = "https://mail.google.com/mail/u/0/#all/"
CHIPS = ("All", "Unread", "Flagged", "Priority")
CHIP_LABELS = {"All": (), "Unread": ("UNREAD",), "Flagged": ("STARRED",)}
CONFIG = None   # set by setup(); the queue hook is handed only the store
PRIORITIES = ("high", "normal", "low")
ROWS = 200      # the newest messages a list holds, the cap the platform's own row hooks use
HAS = "EXISTS (SELECT 1 FROM json_each(m.labels) WHERE value = ?)"
HIGH = "m.id IN (SELECT message_id FROM email_triage WHERE priority = 'high')"
# A row carries its triage and its attachment names, so the list needs no second query and the reader no second fetch.
SELECT = ("SELECT m.*, t.priority, b.attachments FROM email_messages m "
          "LEFT JOIN email_triage t ON t.message_id = m.id "
          "LEFT JOIN email_bodies b ON b.message_id = m.id")
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


def _local(ts: str) -> str:
    """Local wall time: the page reads a row's day and clock straight off the string."""
    return parse(ts).astimezone().isoformat(timespec="minutes")


def _verbs(labels: list[str]) -> list[list[str]]:
    """Archive first, then the two toggles and Gmail; the one that cannot be undone sits last."""
    inbox = "INBOX" in labels
    verbs = [["archive", "Archive"]] if inbox else []
    verbs.append(["read", "Mark read"] if "UNREAD" in labels else ["unread", "Mark unread"])
    verbs.append(["unstar", "Unstar"] if "STARRED" in labels else ["star", "Star"])
    verbs.append(["open", "Open in Gmail"])
    if inbox:
        verbs.append(["trash", "Trash"])
    return verbs


def _row(r: dict, tags: list[str]) -> dict:
    """One ROW. The sender is the clause after the subject, the Gmail snippet the gist under it."""
    labels = _labels(r)
    unread = "UNREAD" in labels
    return {
        "id": r["id"],
        "module": "email",
        "title": r["subject"],
        "snip": r["from_name"] or r["from_addr"],
        "summary": r["snippet"],
        "when": _local(r["internal_date"]),
        "fixed": [FACET],
        "tags": tags,
        "type": "email",
        "unread": unread,
        "dim": not unread,
        "starred": "STARRED" in labels,
        "href": f"{GMAIL}{r['id']}",                # the url Open needs; a [verb, label] pair carries none
        "verbs": _verbs(labels),
    }


def _rows(store: Store, records: list[dict]) -> list[dict]:
    tags = tags_for(store, "email", [r["id"] for r in records])
    return [_row(r, tags[r["id"]]) for r in records]


def _group_by_day(listed: list[dict]) -> list[dict]:
    groups: list[dict] = []
    for r in listed:
        y, m, d = r["when"][:10].split("-")
        label = f"{m}-{d}-{y}"
        if not groups or groups[-1]["label"] != label:
            groups.append({"label": label, "count": 0, "rows": []})
        groups[-1]["rows"].append(r)
        groups[-1]["count"] += 1
    return groups


def _count(store: Store, *labels: str) -> int:
    return store.scalar(f"SELECT COUNT(*) FROM email_messages m WHERE {' AND '.join([HAS] * len(labels))}", labels)


def _get(store: Store, message_id: str) -> dict:
    row = store.one(f"{SELECT} WHERE m.id = ?", (message_id,))
    if row is None:
        raise HTTPException(404, "no such message")
    return row


@router.get("/left")
def left(request: Request, query: str = "", chip: str = "All", limit: int = ROWS) -> dict:
    """The chip and the typed words narrow the whole mailbox, never a page of it; `more` says rows were held back."""
    store: Store = request.app.state.store
    chip = chip if chip in CHIPS else "All"
    where, params = _where(query, chip)
    total = store.scalar(f"SELECT COUNT(*) FROM email_messages m {where}", tuple(params))
    out = rows(store, limit, chip, query)
    return {
        "groups": _group_by_day(out),
        "more": total > len(out),
        "read_on_open": bool(CONFIG.email.read_on_open) if CONFIG else False,
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


def _html(b: dict | None, snippet: str) -> str:
    """What the reader renders: the sanitized html the message carried, else its text as paragraphs."""
    if b and b["html"]:
        return b["html"]
    text = (b["text"] if b else "") or snippet
    return "".join(f"<p>{escape(p.strip())}</p>" for p in re.split(r"\n\s*\n", text) if p.strip())


def item(store: Store, message_id: str) -> dict:
    """The ROW plus what only the reader needs: who it is from, what triage made of it, and the body."""
    r = _get(store, message_id)
    row = _row(r, tags_for(store, "email", [message_id])[message_id])
    tri = store.one("SELECT priority, reason FROM email_triage WHERE message_id = ?", (message_id,))
    attached = json.loads(r["attachments"] or "[]")
    kv = [["From", f"{r['from_name']} <{r['from_addr']}>" if r["from_name"] else r["from_addr"]]]
    if tri:
        kv.append(["Priority", f"{tri['priority']}, {tri['reason']}" if tri["reason"] else tri["priority"]])
    if attached:
        kv.append(["Attached", ", ".join(attached)])
    b = store.one("SELECT text, html FROM email_bodies WHERE message_id = ?", (message_id,))
    return {**row, "kv": kv, "body": _html(b, r["snippet"])}


def _resolve(store: Store, body: dict) -> tuple[list[str], str]:
    """The ids an action applies to, and how to describe them in the event."""
    if body.get("ids") or body.get("id"):
        ids = [str(i) for i in body["ids"]] if body.get("ids") else [str(body["id"])]
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


@router.post("/action/sync")
async def sync_now(request: Request) -> dict:
    """The scheduler's own task, on the scheduler's own lock: a manual sync and a due one can never overlap."""
    from app.modules.email import tasks  # deferred: tasks.py imports this module

    st = request.app.state
    result = await st.runner.run_action("email.sync", "email", RESOURCE, tasks.sync)
    return {"result": str(result)}


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


def rows(store: Store, limit: int = ROWS, chip: str = "All", query: str = "") -> list[dict]:
    """The inbox as ROWs, newest first. The page's list, the cross-module lists and Home's Recent share it."""
    where, params = _where(query, chip if chip in CHIPS else "All")
    records = store.query(f"{SELECT} {where} ORDER BY m.internal_date DESC LIMIT ?", (*params, max(1, limit)))
    return _rows(store, records)


def today(store: Store) -> list[dict]:
    start = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    records = store.query(
        f"{SELECT} WHERE {HAS} AND m.internal_date >= ? ORDER BY m.internal_date DESC", ("INBOX", iso(start))
    )
    return _rows(store, records)


def queue(store: Store) -> list[dict]:
    """Re-consent is the owner's to run and nothing else can do it, so it waits on them like any other queue row."""
    if CONFIG is None:
        return []
    due = consent_expires(CONFIG.email.token_file)
    if due is None or due - timedelta(days=CONFIG.email.consent_warn_days) > now():
        return []
    gone = due <= now()
    when = _local(iso(due))
    return [{
        "id": "consent",
        "module": "email",
        "title": "Gmail consent has expired; run: python -m app.modules.email.gmail consent" if gone
                 else "Gmail consent expires soon; run: python -m app.modules.email.gmail consent",
        "when": when,
        "fixed": [FACET],
        "tags": [],
        "type": "decision",        # no message stands behind it, so nothing tags it and no verb runs on it
        "taggable": False,
        "due": when[:10],
        "verbs": [],
    }]


def context(store: Store, registry) -> str:
    b = {"inbox": _count(store, "INBOX"), "unread": _count(store, "INBOX", "UNREAD"), "flagged": _count(store, "INBOX", "STARRED")}
    last = store.cursor("email.synced_at")
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
