"""MCP tools over the nightly search. Read tools on both servers; the topic edits on the full server only, for the Chat agent."""

from __future__ import annotations

from app.modules.web_search.routes import KINDS, _search
from app.store import Store, now_iso

COLUMNS = "id, topic_id, kind, title, url, summary, found_at, status, decided_at"


def register(read, full, store: Store, config) -> None:
    def search_findings(query: str = "", status: str | None = None, limit: int = 20) -> list[dict]:
        """Findings by words in their title or summary. status narrows to open, agreed or disagreed. Newest first."""
        where, params = _search(query)
        if status:
            where.append("status = ?")
            params.append(status)
        sql_where = ("WHERE " + " AND ".join(where)) if where else ""
        return store.query(f"SELECT {COLUMNS} FROM web_search_findings {sql_where} ORDER BY found_at DESC LIMIT ?", (*params, max(1, min(limit, 100))))

    def search_topics() -> list[dict]:
        """Every topic the nightly search covers, with its kind: money, work or learn."""
        return store.query("SELECT id, kind, text, created_at FROM web_search_topics ORDER BY kind, created_at")

    def search_topic_add(kind: str, text: str) -> dict:
        """Add a topic for the nightly search, in the owner's words. kind: money (investment, sector, legislation), work (techniques, research, career) or learn (what the owner studies)."""
        if kind not in KINDS:
            return {"error": f"kind must be one of {', '.join(KINDS)}"}
        text = text.strip()
        if not text:
            return {"error": "empty text"}
        if store.one("SELECT id FROM web_search_topics WHERE text = ?", (text,)):
            return {"error": "topic already listed"}
        cur = store.execute("INSERT INTO web_search_topics(kind, text, created_at) VALUES (?, ?, ?)", (kind, text, now_iso()))
        store.event("web_search", "topic added", f"{kind} (agent): {text[:120]}", ref=str(cur.lastrowid))
        return {"id": cur.lastrowid, "kind": kind, "text": text}

    def search_topic_remove(id: int) -> dict:
        """Remove a topic by id. Its findings keep their kind."""
        t = store.one("SELECT * FROM web_search_topics WHERE id = ?", (id,))
        if t is None:
            return {"error": f"no topic {id}"}
        store.execute("DELETE FROM web_search_topics WHERE id = ?", (id,))
        store.event("web_search", "topic removed", f"{t['kind']} (agent): {t['text'][:120]}", ref=str(id))
        return {"id": id}

    for server in (read, full):
        server.tool()(search_findings)
        server.tool()(search_topics)
    full.tool()(search_topic_add)
    full.tool()(search_topic_remove)
