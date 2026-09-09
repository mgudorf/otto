"""MCP tools for the Search agent. Read tools only; both servers get them."""

from __future__ import annotations

from app.modules.web_search.routes import _search
from app.store import Store

COLUMNS = "id, topic_id, kind, title, url, summary, found_at, status, decided_at"


def register(read, full, store: Store, config) -> None:
    def search_findings(query: str = "", status: str | None = None, limit: int = 20) -> list[dict]:
        """Findings by words in their title or summary. status narrows to open, agreed or disagreed. Newest first."""
        where, params = _search(query)
        if status:
            where.append("status = ?")
            params.append(status)
        sql_where = ("WHERE " + " AND ".join(where)) if where else ""
        return store.query(f"SELECT {COLUMNS} FROM search_findings {sql_where} ORDER BY found_at DESC LIMIT ?", (*params, max(1, min(limit, 100))))

    def search_topics() -> list[dict]:
        """Every topic the nightly search covers, with its kind: money, work or learn."""
        return store.query("SELECT id, kind, text, created_at FROM search_topics ORDER BY kind, created_at")

    for server in (read, full):
        server.tool()(search_findings)
        server.tool()(search_topics)
