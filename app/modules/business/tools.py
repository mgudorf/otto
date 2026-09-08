"""MCP tools for the Business agent. Read tools go on both servers; write tools on the full server only."""

from __future__ import annotations

from app.modules.business.routes import KINDS, _search
from app.store import Store, now_iso

COLUMNS = "id, kind, text, ref, why, status, created_at, updated_at"


def register(read, full, store: Store) -> None:
    def business_search(query: str, kind: str | None = None, limit: int = 20) -> list[dict]:
        """Search plans, people, events, documents and leads by words in their text or link. kind narrows. Newest first."""
        where, params = _search(query)
        if kind:
            where.append("kind = ?")
            params.append(kind)
        sql_where = ("WHERE " + " AND ".join(where)) if where else ""
        return store.query(f"SELECT {COLUMNS} FROM business_items {sql_where} ORDER BY created_at DESC LIMIT ?", (*params, max(1, min(limit, 100))))

    def business_get(id: int) -> dict:
        """One item by id. A document's ref is a path you can Read."""
        r = store.one(f"SELECT {COLUMNS} FROM business_items WHERE id = ?", (id,))
        return r if r else {"error": f"no item {id}"}

    def business_leads(status: str = "open") -> list[dict]:
        """Leads by status: open, accepted or dismissed. Check before proposing a lead; a url is recorded once."""
        return store.query(f"SELECT {COLUMNS} FROM business_items WHERE kind = 'lead' AND status = ? ORDER BY created_at DESC", (status,))

    def business_add(kind: str, text: str, ref: str | None = None) -> dict:
        """Capture a plan, person or event with the owner's exact words. ref is an optional link."""
        if kind not in KINDS:
            return {"error": f"kind must be one of {', '.join(KINDS)}"}
        if not text.strip():
            return {"error": "empty text"}
        ts = now_iso()
        with store.tx() as conn:
            cur = conn.execute(
                "INSERT INTO business_items(kind, text, ref, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (kind, text.strip(), (ref or "").strip() or None, ts, ts),
            )
        store.event("business", "captured", f"{kind} (agent): {text.strip()[:120]}", ref=str(cur.lastrowid))
        return {"id": cur.lastrowid}

    def business_lead(text: str, ref: str, why: str) -> dict:
        """Record a lead you found (an opening, call, event or news item) so it is queued for the owner and never repeated."""
        if not text.strip() or not ref.strip():
            return {"error": "text and ref are required"}
        ts = now_iso()
        with store.tx() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO business_items(kind, text, ref, why, created_at, updated_at) VALUES ('lead', ?, ?, ?, ?, ?)",
                (text.strip(), ref.strip(), why.strip() or None, ts, ts),
            )
        new = cur.rowcount == 1
        if new:
            store.event("business", "found", f"(agent) {text.strip()[:120]}", ref=str(cur.lastrowid))
        return {"id": cur.lastrowid if new else None, "new": new}

    for server in (read, full):
        server.tool()(business_search)
        server.tool()(business_get)
        server.tool()(business_leads)
    full.tool()(business_add)
    full.tool()(business_lead)
