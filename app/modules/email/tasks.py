"""Scheduled work: mirror Gmail into email_messages. Only the read client is reachable from here."""

from __future__ import annotations

import asyncio

from app.modules.email.gmail import GmailError, read_client
from app.store import now_iso

FETCH_CONCURRENCY = 10   # metadata requests in flight; Gmail allows about 50 gets per second per user
CURSOR = "email.history"

UPSERT = """INSERT INTO email_messages(id, thread_id, from_name, from_addr, to_addr, subject, snippet, internal_date, labels, synced_at)
VALUES (:id, :thread_id, :from_name, :from_addr, :to_addr, :subject, :snippet, :internal_date, :labels, :synced_at)
ON CONFLICT(id) DO UPDATE SET labels = excluded.labels, snippet = excluded.snippet, synced_at = excluded.synced_at"""


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


async def _backfill(ctx, gm) -> str:
    history_id = str((await gm.profile())["historyId"])  # taken first, so nothing between list and commit is lost
    days = ctx.config.email.backfill_days
    rows, _ = await _fetch(gm, await gm.list_ids(f"newer_than:{days}d"))
    ts = now_iso()
    with ctx.commit(cursor=(CURSOR, history_id)) as conn:
        conn.executemany(UPSERT, [{**r, "synced_at": ts} for r in rows])
    return f"backfilled {len(rows)} messages from the last {days} days"


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
    if not rows and not deleted:
        return "no changes"
    return f"{len(rows)} updated, {len(deleted)} removed"
