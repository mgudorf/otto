"""MCP tools for the Database agent. Reads on both servers; the one write (a saved query) on the full
server only. The agent has no path to owner SQL: it drafts and saves, the owner runs."""

from __future__ import annotations

from app.modules.database import query
from app.modules.database.routes import save_query
from app.store import Store


def register(read, full, store: Store, config) -> None:
    d = config.database

    def db_schema() -> list[dict]:
        """Every table under the module that owns it: row count, columns (name, type, notnull, default, pk), indexes, triggers and the CREATE statement."""
        return query.schema(store)

    def db_query(sql: str, limit: int = 100) -> dict:
        """Run read-only SQL. Returns columns and up to `limit` rows of the last statement; a write fails."""
        return query.read(store, sql, max(1, min(limit, d.max_rows)), d.max_seconds)

    def db_explain(sql: str) -> dict:
        """The query plan (EXPLAIN QUERY PLAN) for one statement."""
        return query.explain(store, sql, d.max_rows, d.max_seconds)

    def db_save_query(name: str, sql: str) -> dict:
        """Save a query under a name so the owner finds it under `saved`; the same name replaces the SQL."""
        name, sql = name.strip(), sql.strip()
        if not name or not sql:
            return {"error": "name and sql are required"}
        with store.tx() as conn:
            qid = save_query(conn, name, sql)
        store.event("database", "saved", f"{name} (agent): {sql[:120]}", ref=str(qid))
        return {"id": qid, "name": name}

    for server in (read, full):
        server.tool()(db_schema)
        server.tool()(db_query)
        server.tool()(db_explain)
    full.tool()(db_save_query)
