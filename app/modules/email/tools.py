"""MCP tools for the Email agent. Reads on both servers; email_flag, a note in Otto's own table, on the full server only.

Nothing here can change Gmail.
"""

from __future__ import annotations

import json

from app.modules.email.gmail import read_client
from app.modules.email.routes import CHIPS, HAS, PRIORITIES, _where
from app.store import Store, now_iso


def register(read, full, store: Store, config) -> None:
    def email_search(query: str = "", chip: str = "All", limit: int = 20) -> list[dict]:
        """Search the inbox mirror by sender, address, subject or snippet. chip narrows to All, Unread or Flagged. Newest first."""
        where, params = _where(query, chip if chip in CHIPS else "All")
        rows = store.query(
            f"SELECT m.id, m.from_name, m.from_addr, m.subject, m.snippet, m.internal_date, m.labels FROM email_messages m {where} "
            "ORDER BY m.internal_date DESC LIMIT ?",
            (*params, max(1, min(limit, 100))),
        )
        return [{**r, "labels": json.loads(r["labels"])} for r in rows]

    async def email_get(id: str) -> dict:
        """One message with its full text, fetched from Gmail on first use and cached."""
        r = store.one("SELECT * FROM email_messages WHERE id = ?", (id,))
        if r is None:
            return {"error": f"no message {id}"}
        body = r["body_text"]
        if body is None:
            gm = read_client(config)
            try:
                body = await gm.body(id)
                store.execute("UPDATE email_messages SET body_text = ? WHERE id = ?", (body, id))
            except Exception as e:
                return {**r, "labels": json.loads(r["labels"]), "body_text": r["snippet"], "error": f"body unavailable: {e!r}"[:200]}
            finally:
                await gm.aclose()
        return {**r, "labels": json.loads(r["labels"]), "body_text": body}

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

    for server in (read, full):
        server.tool()(email_search)
        server.tool()(email_get)
        server.tool()(email_triage)
    full.tool()(email_flag)
