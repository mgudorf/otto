"""MCP tools for the Memory agent. Read tools go on both servers; write tools on the full server only."""

from __future__ import annotations

import json

from app.modules.memory.routes import KINDS, _fts, _tags
from app.store import Store, now_iso


def register(read, full, store: Store, config) -> None:
    def memory_search(query: str, kind: str | None = None, limit: int = 20) -> list[dict]:
        """Full-text search over memories. kind narrows to note, link, quote, fact or task. Newest first."""
        where, params = [], []
        if query.strip():
            where.append("id IN (SELECT rowid FROM memory_fts WHERE memory_fts MATCH ?)")
            params.append(_fts(query))
        if kind:
            where.append("kind = ?")
            params.append(kind)
        sql_where = ("WHERE " + " AND ".join(where)) if where else ""
        rows = store.query(f"SELECT id, kind, text, created_at, done_at FROM memory_items {sql_where} ORDER BY created_at DESC LIMIT ?", (*params, max(1, min(limit, 100))))
        return [{**r, "tags": _tags(store, r["id"])} for r in rows]

    def memory_get(id: int) -> dict:
        """One memory by id, with its tags."""
        r = store.one("SELECT id, kind, text, created_at, updated_at, done_at FROM memory_items WHERE id = ?", (id,))
        if r is None:
            return {"error": f"no memory {id}"}
        return {**r, "tags": _tags(store, r["id"])}

    def memory_tags() -> list[dict]:
        """Every tag in use with its count."""
        return store.query("SELECT tag, COUNT(*) AS count FROM memory_tags GROUP BY tag ORDER BY count DESC, tag")

    def memory_suggestions(status: str = "open") -> list[dict]:
        """Action items already suggested (open, accepted or dismissed). Check before suggesting anything."""
        return store.query("SELECT id, text, status, created_at FROM memory_suggestions WHERE status = ? ORDER BY created_at DESC", (status,))

    def memory_add(kind: str, text: str, tags: list[str] | None = None) -> dict:
        """Capture a memory with the owner's exact words. kind: note, link, quote, fact or task."""
        if kind not in KINDS:
            return {"error": f"kind must be one of {', '.join(KINDS)}"}
        if not text.strip():
            return {"error": "empty text"}
        ts = now_iso()
        with store.tx() as conn:
            cur = conn.execute("INSERT INTO memory_items(kind, text, created_at, updated_at) VALUES (?, ?, ?, ?)", (kind, text.strip(), ts, ts))
            for t in tags or []:
                if t.strip():
                    conn.execute("INSERT OR IGNORE INTO memory_tags(memory_id, tag) VALUES (?, ?)", (cur.lastrowid, t.strip()))
        store.event("memory", "captured", f"{kind} (agent): {text.strip()[:120]}", ref=str(cur.lastrowid))
        return {"id": cur.lastrowid}

    def memory_tag(id: int, tags: list[str]) -> dict:
        """Add tags to a memory."""
        if store.one("SELECT id FROM memory_items WHERE id = ?", (id,)) is None:
            return {"error": f"no memory {id}"}
        clean = [t.strip() for t in tags if t.strip()]
        with store.tx() as conn:
            for t in clean:
                conn.execute("INSERT OR IGNORE INTO memory_tags(memory_id, tag) VALUES (?, ?)", (id, t))
        store.event("memory", "tagged", f"{', '.join(clean)} (agent) on memory {id}", ref=str(id))
        return {"id": id, "tags": _tags(store, id)}

    def memory_suggest(text: str, memory_ids: list[int] | None = None) -> dict:
        """Record an action item you are suggesting, so it is never suggested twice."""
        with store.tx() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO memory_suggestions(text, memory_ids, created_at) VALUES (?, ?, ?)",
                (text.strip(), json.dumps(memory_ids or []), now_iso()),
            )
        return {"id": cur.lastrowid, "new": cur.rowcount == 1}

    for server in (read, full):
        server.tool()(memory_search)
        server.tool()(memory_get)
        server.tool()(memory_tags)
        server.tool()(memory_suggestions)
    full.tool()(memory_add)
    full.tool()(memory_tag)
    full.tool()(memory_suggest)
