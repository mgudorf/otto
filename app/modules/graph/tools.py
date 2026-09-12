"""MCP tools for the Graph architect. Read tools on both servers; curation writes on the full server only.

Every write changes an overlay table and rebuilds the graph in the same transaction. Memories and sessions are never written.
"""

from __future__ import annotations

from app.modules.graph import build
from app.modules.graph.build import key
from app.modules.graph.routes import NODE_COLUMNS
from app.store import Store, now_iso


def register(read, full, store: Store, config) -> None:
    def _node(tag: str) -> bool:
        return store.one("SELECT tag FROM graph_nodes WHERE tag = ?", (tag,)) is not None

    def _rebuild_with(verb: str, text: str, change) -> dict:
        with store.tx() as conn:
            err = change(conn)
            if err:
                return {"error": err}
            nodes, edges = build.rebuild(conn)
        store.event("graph", verb, f"(agent) {text}")
        return {"ok": True, "nodes": nodes, "edges": edges}

    def graph_nodes(query: str = "", limit: int = 50) -> list[dict]:
        """Tags in the graph whose name contains query, largest first: tag, count (items), memories, sessions, last_seen."""
        needle = query.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return store.query(
            f"SELECT {NODE_COLUMNS} FROM graph_nodes WHERE tag LIKE ? ESCAPE '\\' ORDER BY count DESC, tag LIMIT ?",
            (f"%{needle}%", max(1, min(limit, 500))),
        )

    def graph_neighbors(tag: str) -> list[dict]:
        """Edges touching a tag: neighbor, kind (cooccur = share items, weight = how many; link = curated), note."""
        k = key(tag)
        if not _node(k):
            return [{"error": f"no node {k!r}"}]
        rows = store.query("SELECT a, b, kind, weight, note FROM graph_edges WHERE a = ? OR b = ? ORDER BY weight DESC, a, b", (k, k))
        return [{"neighbor": r["b"] if r["a"] == k else r["a"], "kind": r["kind"], "weight": r["weight"], "note": r["note"]} for r in rows]

    def graph_items(tag: str, limit: int = 20) -> dict:
        """The memories and tagged sessions carrying a tag (merged aliases included), newest first."""
        k = key(tag)
        if not _node(k):
            return {"error": f"no node {k!r}"}
        hits = [(src, item) for src, item, t, _ in build.sources(store) if t == k]
        mem_ids = sorted({int(i) for s, i in hits if s == "memory"})
        sess_ids = sorted({i for s, i in hits if s == "session"})
        lim = max(1, min(limit, 200))
        memories = store.query(
            f"SELECT id, kind, text, created_at FROM memories WHERE id IN ({','.join('?' * len(mem_ids))}) ORDER BY created_at DESC LIMIT ?",
            (*mem_ids, lim),
        ) if mem_ids else []
        sessions = store.query(
            f"SELECT id, module, title, closed_at FROM sessions WHERE id IN ({','.join('?' * len(sess_ids))}) ORDER BY closed_at DESC LIMIT ?",
            (*sess_ids, lim),
        ) if sess_ids else []
        return {"tag": k, "memories": memories, "sessions": sessions}

    def graph_link(a: str, b: str, note: str = "") -> dict:
        """Add a curated link between two nodes. Both must exist in the graph."""
        a, b = sorted((key(a), key(b)))
        if a == b:
            return {"error": "a and b are the same tag"}
        for t in (a, b):
            if not _node(t):
                return {"error": f"no node {t!r}"}

        def change(conn):
            conn.execute("INSERT OR REPLACE INTO graph_links(a, b, note, ts) VALUES (?, ?, ?, ?)", (a, b, note.strip() or None, now_iso()))

        return _rebuild_with("linked", f"{a} — {b}", change)

    def graph_unlink(a: str, b: str) -> dict:
        """Remove a curated link. Co-occurrence edges cannot be removed; prune or merge a tag instead."""
        a, b = sorted((key(a), key(b)))

        def change(conn):
            if conn.execute("DELETE FROM graph_links WHERE a = ? AND b = ?", (a, b)).rowcount == 0:
                return f"no curated link {a!r} — {b!r}"

        return _rebuild_with("unlinked", f"{a} — {b}", change)

    def graph_merge(alias: str, into: str) -> dict:
        """Fold one tag into another: items tagged `alias` count for `into` from now on. Both must exist in the sources."""
        alias, into = key(alias), key(into)
        if alias == into:
            return {"error": "alias and into are the same tag"}
        known = build.raw_tags(store)
        for t in (alias, into):
            if t not in known:
                return {"error": f"no tag {t!r} in the sources"}

        def change(conn):
            target = conn.execute("SELECT target FROM graph_merges WHERE alias = ?", (into,)).fetchone()
            final = target[0] if target else into
            if final == alias:
                return f"{into!r} is already merged into {alias!r}"
            conn.execute("UPDATE graph_merges SET target = ? WHERE target = ?", (final, alias))
            conn.execute("INSERT OR REPLACE INTO graph_merges(alias, target, ts) VALUES (?, ?, ?)", (alias, final, now_iso()))

        return _rebuild_with("merged", f"{alias} -> {into}", change)

    def graph_prune(tag: str) -> dict:
        """Hide a tag from the graph. The items keep their tag; only the node disappears. graph_restore undoes it."""
        k = key(tag)
        if k not in build.raw_tags(store):
            return {"error": f"no tag {k!r} in the sources"}

        def change(conn):
            conn.execute("INSERT OR IGNORE INTO graph_pruned(tag, ts) VALUES (?, ?)", (k, now_iso()))

        return _rebuild_with("pruned", k, change)

    def graph_restore(tag: str) -> dict:
        """Undo a merge or prune of a tag so it is a node of its own again."""
        k = key(tag)

        def change(conn):
            n = conn.execute("DELETE FROM graph_merges WHERE alias = ?", (k,)).rowcount
            n += conn.execute("DELETE FROM graph_pruned WHERE tag = ?", (k,)).rowcount
            if n == 0:
                return f"{k!r} is neither merged nor pruned"

        return _rebuild_with("restored", k, change)

    for server in (read, full):
        server.tool()(graph_nodes)
        server.tool()(graph_neighbors)
        server.tool()(graph_items)
    full.tool()(graph_link)
    full.tool()(graph_unlink)
    full.tool()(graph_merge)
    full.tool()(graph_prune)
    full.tool()(graph_restore)
