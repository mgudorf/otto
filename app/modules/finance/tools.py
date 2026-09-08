"""MCP tools for the Finance agent. Read tools only, on both servers; the agent never writes."""

from __future__ import annotations

from app.modules.finance.routes import KINDS, amount_text, monthly, totals
from app.store import Store


def register(read, full, store: Store) -> None:
    def finance_list(kind: str | None = None, include_ended: bool = False) -> list[dict]:
        """The owner's entries. kind narrows to account, recurring, holding or budget. Amounts are cents; text is the display form."""
        where, params = [], []
        if kind:
            if kind not in KINDS:
                return [{"error": f"kind must be one of {', '.join(KINDS)}"}]
            where.append("kind = ?")
            params.append(kind)
        if not include_ended:
            where.append("ended_at IS NULL")
        sql_where = ("WHERE " + " AND ".join(where)) if where else ""
        rows = store.query(f"SELECT * FROM finance_entries {sql_where} ORDER BY kind, name", tuple(params))
        return [{**r, "text": amount_text(r), "monthly": monthly(r) if r["cadence"] else None} for r in rows]

    def finance_get(id: int) -> dict:
        """One entry by id with its amount history, newest first."""
        r = store.one("SELECT * FROM finance_entries WHERE id = ?", (id,))
        if r is None:
            return {"error": f"no entry {id}"}
        history = store.query("SELECT ts, amount FROM finance_amounts WHERE entry_id = ? ORDER BY ts DESC", (id,))
        return {**r, "text": amount_text(r), "history": history}

    def finance_totals() -> dict:
        """Sums over active entries, in cents: accounts, holdings, monthly_recurring, monthly_budget."""
        return totals(store)

    for server in (read, full):
        server.tool()(finance_list)
        server.tool()(finance_get)
        server.tool()(finance_totals)
