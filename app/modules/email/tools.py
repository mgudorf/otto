"""MCP tools for the Email agent. Reads on both servers; email_flag, a note in Otto's own table, on the full server only.

Nothing here can change Gmail.
"""

from __future__ import annotations

import json

from app.modules.email.routes import CHIPS, HAS, PRIORITIES, _where, body_of
from app.store import Store, now_iso


def register(read, full, store: Store, config) -> None:
    def email_search(query: str = "", chip: str = "All", limit: int = 20) -> list[dict]:
        """Search the inbox mirror by sender, address, subject or snippet. Newest first."""
        where, params = _where(query, chip if chip in CHIPS else "All")
        rows = store.query(
            f"SELECT m.id, m.from_name, m.from_addr, m.subject, m.snippet, m.internal_date, m.labels FROM email_messages m {where} "
            "ORDER BY m.internal_date DESC LIMIT ?",
            (*params, max(1, min(limit, 100))),
        )
        return [{**r, "labels": json.loads(r["labels"])} for r in rows]

    async def email_get(id: str) -> dict:
        """One message with its full text and attachment names, fetched from Gmail on first use and cached. Attachments are never fetched."""
        r = store.one(
            "SELECT id, thread_id, from_name, from_addr, to_addr, subject, snippet, internal_date, labels FROM email_messages WHERE id = ?", (id,)
        )
        if r is None:
            return {"error": f"no message {id}"}
        out = {**r, "labels": json.loads(r["labels"])}
        try:
            b = await body_of(store, config, id)
        except Exception as e:
            return {**out, "body_text": r["snippet"], "attachments": [], "error": f"body unavailable: {e!r}"[:200]}
        return {**out, "body_text": b["text"], "attachments": b["attachments"]}

    def email_triage(priority: str = "high") -> list[dict]:
        """Inbox messages the triage marked with this priority (high, normal or low), newest first, with the reason."""
        if priority not in PRIORITIES:
            return [{"error": f"priority must be one of {', '.join(PRIORITIES)}"}]
        return store.query(
            f"SELECT m.id, m.from_name, m.subject, m.internal_date, t.priority, t.reason, t.source FROM email_triage t "
            f"JOIN email_messages m ON m.id = t.message_id WHERE t.priority = ? AND {HAS} ORDER BY m.internal_date DESC LIMIT 50",
            (priority, "INBOX"),
        )

    def email_flag(id: str, priority: str, reason: str) -> dict:
        """Record a priority (high, normal or low) and a one-line reason for a message. This is Otto's note; Gmail is untouched."""
        if priority not in PRIORITIES:
            return {"error": f"priority must be one of {', '.join(PRIORITIES)}"}
        r = store.one("SELECT subject FROM email_messages WHERE id = ?", (id,))
        if r is None:
            return {"error": f"no message {id}"}
        with store.tx() as conn:
            conn.execute(
                "INSERT INTO email_triage(message_id, priority, reason, ts, source) VALUES (?, ?, ?, ?, 'session') "
                "ON CONFLICT(message_id) DO UPDATE SET priority = excluded.priority, reason = excluded.reason, ts = excluded.ts, source = excluded.source",
                (id, priority, reason.strip()[:300], now_iso()),
            )
        store.event("email", "flagged", f"{priority} (agent): {r['subject'][:100]}", ref=id)
        return {"id": id, "priority": priority}

    # Built from CHIPS, so the description the agent reads cannot drift from the chips the route serves.
    email_search.__doc__ += f" chip narrows to {', '.join(CHIPS[:-1])} or {CHIPS[-1]}."

    for server in (read, full):
        server.tool()(email_search)
        server.tool()(email_get)
        server.tool()(email_triage)
    full.tool()(email_flag)
