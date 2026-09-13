"""Scheduled work: mirror Gmail into email_messages, and triage the inbox overnight.

Only the read client is reachable from here; triage writes Otto's own table, never Gmail.
"""

from __future__ import annotations

import asyncio
import json

from app.modules.email.gmail import GmailError, read_client
from app.modules.email.routes import HAS, PRIORITIES
from app.runner import Skipped
from app.store import now, now_iso

FETCH_CONCURRENCY = 10   # metadata requests in flight; the client pauses them all when Gmail refuses on quota
PAGE = 100               # messages fetched and committed together during a backfill; a kill loses at most one page
CURSOR = "email.history"
SYNCED = "email.synced_at"   # moved by every successful sync, scheduled or manual, so the page can say when
BACKFILL = "email.backfill"   # "<historyId>|<started>" while a backfill is in progress; resumed by the next run

UPSERT = """INSERT INTO email_messages(id, thread_id, from_name, from_addr, to_addr, subject, snippet, internal_date, labels, synced_at)
VALUES (:id, :thread_id, :from_name, :from_addr, :to_addr, :subject, :snippet, :internal_date, :labels, :synced_at)
ON CONFLICT(id) DO UPDATE SET labels = excluded.labels, snippet = excluded.snippet, synced_at = excluded.synced_at"""


def _stamp_synced(conn) -> None:
    """In the same transaction as the results, so the page never reports a sync that did not commit."""
    conn.execute(
        "INSERT INTO cursors(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (SYNCED, now_iso()),
    )


async def _fetch(gm, ids: list[str]) -> tuple[list[dict], list[str]]:
    """Metadata for each id; ids Gmail no longer has come back as gone."""
    sem = asyncio.Semaphore(FETCH_CONCURRENCY)
    rows, gone = [], []

    async def one(mid: str) -> None:
        async with sem:
            try:
                rows.append(await gm.metadata(mid))
            except GmailError as e:
                if e.status != 404:
                    raise
                gone.append(mid)

    await asyncio.gather(*(one(m) for m in ids))
    return rows, gone


async def sync(ctx) -> str:
    gm = read_client(ctx.config)
    try:
        cursor = ctx.cursor(CURSOR)
        if cursor:
            try:
                return await _incremental(ctx, gm, cursor)
            except GmailError as e:
                if e.status != 404:
                    raise
                ctx.log("history id expired; backfilling")
        return await _backfill(ctx, gm)
    finally:
        await gm.aclose()


def _stamp() -> str:
    """Microsecond UTC stamp: lets a resumed backfill tell its own pages from older rows within the same second."""
    return now().isoformat(timespec="microseconds")


async def _backfill(ctx, gm) -> str:
    pending = ctx.cursor(BACKFILL)
    if pending:
        history_id, started = pending.split("|", 1)
        ctx.log(f"resuming the backfill started {started}")
    else:
        history_id, started = str((await gm.profile())["historyId"]), _stamp()  # taken first: history covers everything after
        with ctx.commit(cursor=(BACKFILL, f"{history_id}|{started}")):
            pass
    days = ctx.config.email.backfill_days
    ids = await gm.list_ids(f"newer_than:{days}d")
    have = {r["id"] for r in ctx.store.query("SELECT id FROM email_messages WHERE synced_at >= ?", (started,))}
    todo = [i for i in ids if i not in have]
    fetched = 0
    for i in range(0, len(todo), PAGE):
        rows, _ = await _fetch(gm, todo[i:i + PAGE])
        with ctx.commit() as conn:
            conn.executemany(UPSERT, [{**r, "synced_at": _stamp()} for r in rows])
        fetched += len(rows)
        ctx.log(f"backfill {fetched}/{len(todo)}")
    with ctx.commit(cursor=(CURSOR, history_id)) as conn:
        conn.execute("DELETE FROM cursors WHERE key = ?", (BACKFILL,))
        _stamp_synced(conn)
    return f"backfilled {fetched} messages from the last {days} days ({len(have)} already mirrored)"


async def _incremental(ctx, gm, cursor: str) -> str:
    data = await gm.history(cursor)
    touched, deleted = set(), set()
    for rec in data["history"]:
        for m in rec.get("messagesDeleted", []):
            deleted.add(m["message"]["id"])
        for key in ("messagesAdded", "labelsAdded", "labelsRemoved"):
            for m in rec.get(key, []):
                touched.add(m["message"]["id"])
    rows, gone = await _fetch(gm, sorted(touched - deleted))
    deleted |= set(gone)
    ts = now_iso()
    with ctx.commit(cursor=(CURSOR, data["historyId"])) as conn:
        conn.executemany(UPSERT, [{**r, "synced_at": ts} for r in rows])
        conn.executemany("DELETE FROM email_messages WHERE id = ?", [(i,) for i in sorted(deleted)])
        _stamp_synced(conn)
    if not rows and not deleted:
        return "no changes"
    return f"{len(rows)} updated, {len(deleted)} removed"


# ---- triage ----------------------------------------------------------------------------------
def _json_array(raw: str) -> list:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("["):]
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < 0:
        raise ValueError(f"no JSON array in reply: {raw[:200]!r}")
    return json.loads(text[start:end + 1])


async def triage(ctx) -> str:
    batch = ctx.config.email.triage_batch
    rows = ctx.store.query(
        f"SELECT m.id, m.from_name, m.from_addr, m.subject, m.snippet FROM email_messages m WHERE {HAS} "
        "AND m.id NOT IN (SELECT message_id FROM email_triage) ORDER BY m.internal_date DESC LIMIT ?",
        ("INBOX", batch),
    )
    if not rows:
        return Skipped("nothing untriaged in the inbox")
    prompt = "\n".join([
        "Triage these inbox messages for the owner, given as (id, from, subject) snippet:",
        *[f"- ({r['id']}, {r['from_name']} <{r['from_addr']}>, {r['subject'][:120]}) {r['snippet'][:200]}" for r in rows],
        "",
        "Reply with only a JSON array, one element per message: {\"id\": the id, \"priority\": \"high\" | \"normal\" | \"low\", \"reason\": one short sentence}.",
        "high: needs the owner's action or reply soon. normal: worth reading. low: promotions, notifications, newsletters.",
    ])
    raw = await ctx.run_task(prompt, tools=("email_search", "email_get"))
    ids = {r["id"] for r in rows}
    ts = now_iso()
    done = high = 0
    with ctx.commit(cursor=("email.triage", ts)) as conn:
        for it in _json_array(raw):
            mid, priority = str(it.get("id", "")), str(it.get("priority", "")).lower()
            if mid not in ids or priority not in PRIORITIES:
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO email_triage(message_id, priority, reason, ts, source) VALUES (?, ?, ?, ?, 'scheduled')",
                (mid, priority, str(it.get("reason", "")).strip()[:300], ts),
            )
            done += cur.rowcount
            high += cur.rowcount if priority == "high" else 0
    return f"{done} triaged, {high} high"
