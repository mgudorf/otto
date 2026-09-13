"""MCP tools for the Social agent. Read tools go on both servers; write tools on the full server only."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.modules.social.routes import CATEGORIES, _search, today_stamp
from app.modules.social.tasks import _starts_at
from app.store import Store, now_iso

COLUMNS = "id, kind, text, ref, why, category, city, venue, starts_at, status, created_at, updated_at"


def register(read, full, store: Store, config) -> None:
    def social_search(query: str, category: str | None = None, limit: int = 20) -> list[dict]:
        """Search interests and events by words in their text, link, venue, city or category. Newest first."""
        where, params = _search(query)
        if category:
            where.append("category = :category")
            params["category"] = category
        sql_where = ("WHERE " + " AND ".join(where)) if where else ""
        params["limit"] = max(1, min(limit, 100))
        return store.query(f"SELECT {COLUMNS} FROM social_items {sql_where} ORDER BY created_at DESC LIMIT :limit", params)

    def social_get(id: int) -> dict:
        """One interest or event by id."""
        r = store.one(f"SELECT {COLUMNS} FROM social_items WHERE id = ?", (id,))
        return r if r else {"error": f"no item {id}"}

    def social_upcoming(days: int = 14, status: str | None = None) -> list[dict]:
        """Events starting between today and `days` ahead, soonest first. status narrows to open, going or dismissed."""
        last = (datetime.now().astimezone() + timedelta(days=max(1, days))).strftime("%Y-%m-%dT23:59")
        where = "kind = 'event' AND starts_at >= :today AND starts_at <= :last"
        params = {"today": today_stamp(), "last": last}
        if status:
            where += " AND status = :status"
            params["status"] = status
        return store.query(f"SELECT {COLUMNS} FROM social_items WHERE {where} ORDER BY starts_at ASC, id ASC", params)

    def social_interest(text: str, ref: str | None = None) -> dict:
        """Record what the owner says they want to do or meet, in their exact words. It steers the nightly scout."""
        if not text.strip():
            return {"error": "empty text"}
        ts = now_iso()
        with store.tx() as conn:
            cur = conn.execute(
                "INSERT INTO social_items(kind, text, ref, created_at, updated_at) VALUES ('interest', ?, ?, ?, ?)",
                (text.strip(), (ref or "").strip() or None, ts, ts),
            )
        store.event("social", "captured", f"interest (agent): {text.strip()[:120]}", ref=str(cur.lastrowid))
        return {"id": cur.lastrowid}

    def social_event(text: str, url: str, category: str, date: str, city: str = "", venue: str = "", time: str = "", why: str = "") -> dict:
        """Record an event you found so it queues for the owner and is never proposed twice. date is YYYY-MM-DD, time HH:MM or empty."""
        if not text.strip() or not url.strip():
            return {"error": "text and url are required"}
        if category not in CATEGORIES:
            return {"error": f"category must be one of {', '.join(CATEGORIES)}"}
        now = datetime.now().astimezone().replace(tzinfo=None)
        first = now.replace(hour=0, minute=0, second=0, microsecond=0)
        last = first + timedelta(days=config.social.horizon_days)
        starts_at = _starts_at(date, time, first, last)
        if starts_at is None:
            return {"error": f"date must be YYYY-MM-DD between {first:%Y-%m-%d} and {last:%Y-%m-%d}"}
        ts = now_iso()
        with store.tx() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO social_items(kind, text, ref, why, category, city, venue, starts_at, created_at, updated_at)"
                " VALUES ('event', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (text.strip(), url.strip(), why.strip() or None, category, city.strip() or None, venue.strip() or None, starts_at, ts, ts),
            )
        new = cur.rowcount == 1
        if new:
            store.event("social", "found", f"(agent) {text.strip()[:120]}", ref=str(cur.lastrowid))
        return {"id": cur.lastrowid if new else None, "new": new}

    for server in (read, full):
        server.tool()(social_search)
        server.tool()(social_get)
        server.tool()(social_upcoming)
    full.tool()(social_interest)
    full.tool()(social_event)
