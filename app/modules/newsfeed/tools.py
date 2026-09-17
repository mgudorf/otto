"""MCP tools for the Newsfeed agent. Read tools go on both servers; creating a search and tagging are on the full server only."""

from __future__ import annotations

from app.modules.newsfeed.routes import SEARCH, _ref, _search, searches, tags_of
from app.modules.newsfeed.tasks import clean_tags, local_today
from app.store import Store, now_iso

COLUMNS = "id, search_id, text, url, summary, starts_at, follow_up_at, follows, found_at, status, decided_at"


def register(read, full, store: Store, config) -> None:
    def newsfeed_search(query: str = "", status: str | None = None, limit: int = 20) -> list[dict]:
        """Entries by words in their text, url, summary or tags. status narrows to open, accepted or dismissed. Newest first."""
        where, params = _search(query)
        if status:
            where.append("status = ?")
            params.append(status)
        sql_where = ("WHERE " + " AND ".join(where)) if where else ""
        rows = store.query(f"SELECT {COLUMNS} FROM newsfeed_items {sql_where} ORDER BY found_at DESC, id DESC LIMIT ?", (*params, max(1, min(limit, 100))))
        return [{**r, "tags": tags_of(store, "item", r["id"])} for r in rows]

    def newsfeed_get(id: str) -> dict:
        """One entry by its integer id, or one search by its id in the form s12, with its tags."""
        try:
            kind, ref = _ref(id)
        except Exception:
            return {"error": f"bad id {id!r}: an entry is an integer, a search is s<integer>"}
        table = "newsfeed_searches" if kind == "search" else "newsfeed_items"
        r = store.one(f"SELECT * FROM {table} WHERE id = ?", (ref,))
        if r is None:
            return {"error": f"no {kind} {id}"}
        return {**r, "id": f"{SEARCH}{ref}" if kind == "search" else ref, "tags": tags_of(store, kind, ref)}

    def newsfeed_searches() -> list[dict]:
        """Every search the nightly run covers: id (s12), name, prompt, every_days, cap, next_run, last_run, last_result, tags, open entries."""
        return searches(store)

    def newsfeed_search_add(name: str, prompt: str, tags: list[str] | None = None, every_days: int = 1, cap: int | None = None) -> dict:
        """Create a search in the owner's words. name is a short unique label; prompt says what to look for, where and what to skip;
        every_days is how often it runs (1 = every night); cap is the entries one run may add (the [newsfeed] default when omitted).
        Its entries inherit its tags."""
        name, prompt = name.strip(), prompt.strip()
        if not name or not prompt:
            return {"error": "name and prompt are required"}
        if store.one("SELECT id FROM newsfeed_searches WHERE name = ?", (name,)):
            return {"error": f"a search named {name!r} exists"}
        every_days = max(1, int(every_days))
        cap = max(1, int(cap)) if cap else config.newsfeed.items_per_run
        with store.tx() as conn:
            cur = conn.execute(
                "INSERT INTO newsfeed_searches(name, prompt, every_days, cap, created_at, next_run) VALUES (?, ?, ?, ?, ?, ?)",
                (name, prompt, every_days, cap, now_iso(), local_today()),
            )
            for t in clean_tags(tags):
                conn.execute("INSERT OR IGNORE INTO newsfeed_tags(kind, ref, tag) VALUES ('search', ?, ?)", (cur.lastrowid, t))
        store.event("newsfeed", "search added", f"(agent) {name}: {prompt[:100]}", ref=f"{SEARCH}{cur.lastrowid}")
        return {"id": f"{SEARCH}{cur.lastrowid}", "name": name, "every_days": every_days, "cap": cap, "tags": tags_of(store, "search", cur.lastrowid)}

    def newsfeed_tag(id: str, tags: list[str]) -> dict:
        """Add tags to an entry (integer id) or a search (s12). Lowercase words; existing tags stay."""
        try:
            kind, ref = _ref(id)
        except Exception:
            return {"error": f"bad id {id!r}: an entry is an integer, a search is s<integer>"}
        table = "newsfeed_searches" if kind == "search" else "newsfeed_items"
        r = store.one(f"SELECT * FROM {table} WHERE id = ?", (ref,))
        if r is None:
            return {"error": f"no {kind} {id}"}
        clean = clean_tags(tags)
        if not clean:
            return {"error": "no tags"}
        with store.tx() as conn:
            for t in clean:
                conn.execute("INSERT OR IGNORE INTO newsfeed_tags(kind, ref, tag) VALUES (?, ?, ?)", (kind, ref, t))
        store.event("newsfeed", "tagged", f"(agent) {', '.join(clean)} on {r.get('name') or r['text'][:80]}", ref=str(id))
        return {"id": id, "tags": tags_of(store, kind, ref)}

    for server in (read, full):
        server.tool()(newsfeed_search)
        server.tool()(newsfeed_get)
        server.tool()(newsfeed_searches)
    full.tool()(newsfeed_search_add)
    full.tool()(newsfeed_tag)
