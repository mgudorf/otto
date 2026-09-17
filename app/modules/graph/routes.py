"""Graph: a view over the tags written elsewhere. Reads only; curation goes through the agent's tools."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.store import Store

router = APIRouter(prefix="/api/graph")

NODE_COLUMNS = "tag, count, items, sessions, last_seen"


def _row(r: dict) -> dict:
    return {"id": r["tag"], "module": "graph", "text": r["tag"], "stamp": r["last_seen"], "leading": {"dot": None}, "count": r["count"]}


def _page(store: Store, query: str, page: int) -> tuple[list[dict], int, int]:
    """Nodes matching the substring, largest first, up to ui.page_size * (page + 1)."""
    size = int(store.setting("ui.page_size"))
    limit = size * (page + 1)
    where, params = "", ()
    if query.strip():
        needle = query.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        where, params = "WHERE tag LIKE ? ESCAPE '\\'", (f"%{needle}%",)
    total = store.scalar(f"SELECT COUNT(*) FROM graph_nodes {where}", params)
    rows = store.query(f"SELECT {NODE_COLUMNS} FROM graph_nodes {where} ORDER BY count DESC, tag LIMIT ?", (*params, limit))
    return rows, total, limit


@router.get("/left")
def left(request: Request, query: str = "", page: int = 0) -> dict:
    rows, total, limit = _page(request.app.state.store, query, page)
    return {
        "groups": [{"label": "tags", "count": total, "rows": [_row(r) for r in rows]}],
        "showing": f"{min(limit, total)} / {total}",
        "more": total > limit,
    }


@router.get("/graph")
def graph(request: Request, query: str = "", page: int = 0) -> dict:
    store: Store = request.app.state.store
    rows, _, _ = _page(store, query, page)
    tags = {r["tag"] for r in rows}
    edges = [e for e in store.query("SELECT a, b, kind, weight FROM graph_edges") if e["a"] in tags and e["b"] in tags]
    return {
        "nodes": rows,
        "edges": edges,
        "built_at": store.cursor("graph.rebuild"),
        "totals": {"nodes": store.scalar("SELECT COUNT(*) FROM graph_nodes"), "edges": store.scalar("SELECT COUNT(*) FROM graph_edges")},
    }


# ---- shell hooks ---------------------------------------------------------------------------
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
