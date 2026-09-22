"""Graph: a view over the tags written elsewhere. Reads only; curation goes through the agent's tools.

A tag is not an item, so nothing here lists rows: the brain is drawn from /api/graph."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.store import Store, parse, tag_key, tags_for

router = APIRouter(prefix="/api/graph")

NODE_COLUMNS = "tag, count, items, sessions, last_seen"


def _when(ts: str) -> str:
    """A ROW's `when` on the owner's wall clock, like every other module's; the table stores UTC."""
    return parse(ts).astimezone().strftime("%Y-%m-%dT%H:%M") if ts else ""


def _row(r: dict) -> dict:
    return {"id": r["tag"], "module": "graph", "text": r["tag"], "stamp": _when(r["last_seen"]), "count": r["count"]}


def _item(r: dict, tags: list[str]) -> dict:
    """A tag as a ROW: the node is named by its tag, so the title says it once and no identity tag repeats it."""
    return {"id": r["tag"], "module": "graph", "title": r["tag"], "when": _when(r["last_seen"]), "fixed": [],
            "tags": tags, "count": r["count"], "items": r["items"], "sessions": r["sessions"]}


def _match(query: str) -> tuple[str, tuple]:
    if not query.strip():
        return "", ()
    needle = query.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return "WHERE tag LIKE ? ESCAPE '\\'", (f"%{needle}%",)


def _page(store: Store, query: str, page: int) -> tuple[list[dict], int, int]:
    """Nodes matching the substring, largest first, up to ui.page_size * (page + 1)."""
    size = int(store.setting("ui.page_size"))
    limit = size * (page + 1)
    where, params = _match(query)
    total = store.scalar(f"SELECT COUNT(*) FROM graph_nodes {where}", params)
    rows = store.query(f"SELECT {NODE_COLUMNS} FROM graph_nodes {where} ORDER BY count DESC, tag LIMIT ?", (*params, limit))
    return rows, total, limit


@router.get("/left")
def left(request: Request, query: str = "", page: int = 0) -> dict:
    rows, total, limit = _page(request.app.state.store, query, page)
    return {
        "groups": [{"label": "tags", "count": total, "rows": [_row(r) for r in rows]}],
        "more": total > limit,
    }


@router.get("/graph")
def graph(request: Request, query: str = "") -> dict:
    """Every node the query matches and the edges between them: the map is a map of every tag."""
    store: Store = request.app.state.store
    where, params = _match(query)
    found = store.query(f"SELECT {NODE_COLUMNS} FROM graph_nodes {where} ORDER BY count DESC, tag", params)
    tags = {r["tag"] for r in found}
    edges = [e for e in store.query("SELECT a, b, kind, weight FROM graph_edges") if e["a"] in tags and e["b"] in tags]
    owned = tags_for(store, "graph", sorted(tags))
    return {
        "nodes": [{**r, "last_seen": _when(r["last_seen"]), "tags": owned[r["tag"]]} for r in found],
        "edges": edges,
        "built_at": store.cursor("graph.rebuild"),
        "totals": {"nodes": store.scalar("SELECT COUNT(*) FROM graph_nodes"), "edges": store.scalar("SELECT COUNT(*) FROM graph_edges")},
    }


@router.get("/item/{tag}")
def item_route(request: Request, tag: str) -> dict:
    row = item(request.app.state.store, tag)
    if row is None:
        raise HTTPException(404, "no such tag")
    return row


# ---- shell hooks ---------------------------------------------------------------------------
def item(store: Store, tag: str) -> dict | None:
    r = store.one(f"SELECT {NODE_COLUMNS} FROM graph_nodes WHERE tag = ?", (tag_key(tag),))
    return _item(r, tags_for(store, "graph", [r["tag"]])[r["tag"]]) if r else None


def numbers(store: Store) -> dict:
    return {"value": store.scalar("SELECT COUNT(*) FROM graph_nodes"), "label": "nodes"}


def context(store: Store, registry) -> str:
    nodes = store.scalar("SELECT COUNT(*) FROM graph_nodes")
    edges = store.scalar("SELECT COUNT(*) FROM graph_edges")
    top = store.query(f"SELECT tag, count FROM graph_nodes ORDER BY count DESC, tag LIMIT 10")
    merges = store.query("SELECT alias, target FROM graph_merges ORDER BY alias")
    pruned = store.query("SELECT tag FROM graph_pruned ORDER BY tag")
    links = store.scalar("SELECT COUNT(*) FROM graph_links")
    return "\n".join([
        f"{nodes} nodes, {edges} edges; last built {store.cursor('graph.rebuild') or 'never'}",
        "Largest (tag: items): " + (", ".join(f"{r['tag']}: {r['count']}" for r in top) or "none"),
        "Merged: " + (", ".join(f"{r['alias']} -> {r['target']}" for r in merges) or "none"),
        "Pruned: " + (", ".join(r["tag"] for r in pruned) or "none"),
        f"Curated links: {links}",
    ])
