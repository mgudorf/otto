"""Scheduled rebuild of the graph from the tag sources. Plain SQL, no LLM."""

from __future__ import annotations

from app.modules.graph import build
from app.store import now_iso


async def rebuild(ctx) -> str:
    with ctx.commit(cursor=("graph.rebuild", now_iso())) as conn:
        nodes, edges = build.rebuild(conn)
    return f"{nodes} nodes, {edges} edges"
