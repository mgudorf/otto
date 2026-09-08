"""MCP tools for the Email agent. Reads on both servers. Nothing here can change Gmail."""

from __future__ import annotations

import json

from app.modules.email.gmail import read_client
from app.modules.email.routes import CHIPS, _where
from app.store import Store


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

    for server in (read, full):
        server.tool()(email_search)
        server.tool()(email_get)
