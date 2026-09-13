"""The one rebuild: tag sources -> graph_nodes and graph_edges, with the curation overlays applied.

`conn` is anything with `.execute(sql, params)`: the Store for reads, the transaction connection for writes.
"""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations

SOURCES = """
SELECT 'memory' AS src, m.id AS item, t.tag AS tag, m.created_at AS ts
  FROM memory_tags t JOIN memory_items m ON m.id = t.memory_id
UNION ALL
SELECT 'session', s.id, j.value, COALESCE(s.closed_at, s.opened_at)
  FROM app_sessions s, json_each(s.tags) j
 WHERE s.tags IS NOT NULL
"""
# Every tagged session counts, open or closed: the module panes are tagged when they close, a Chat conversation after its first turn.


def key(tag: str) -> str:
    """Tags are case-insensitive: `GRADient descent` and `gradient DESCENT` are one node."""
    return str(tag).strip().lower()


def raw_tags(conn) -> set[str]:
    """Every normalised tag present in the sources, before merges and prunes."""
    return {key(row[2]) for row in conn.execute(SOURCES) if key(row[2])}


def sources(conn) -> list[tuple[str, str, str, str]]:
    """(src, item, tag, ts) rows: tags normalised, aliases folded, pruned tags dropped."""
    merges = dict(conn.execute("SELECT alias, target FROM graph_merges").fetchall())
    pruned = {r[0] for r in conn.execute("SELECT tag FROM graph_pruned").fetchall()}
    out = []
    for src, item, tag, ts in conn.execute(SOURCES):
        k = key(tag)
        k = merges.get(k, k)
        if k and k not in pruned:
            out.append((src, str(item), k, ts or ""))
    return out


def rebuild(conn) -> tuple[int, int]:
    """Replace graph_nodes and graph_edges from the sources. Returns (nodes, edges)."""
    nodes: dict[str, dict] = {}
    per_item: dict[tuple[str, str], set[str]] = defaultdict(set)
    for src, item, tag, ts in sources(conn):
        n = nodes.setdefault(tag, {"items": set(), "memories": 0, "sessions": 0, "last_seen": ""})
        if (src, item) not in n["items"]:
            n["items"].add((src, item))
            n["memories" if src == "memory" else "sessions"] += 1
        n["last_seen"] = max(n["last_seen"], ts)
        per_item[(src, item)].add(tag)
    cooccur: dict[tuple[str, str], int] = defaultdict(int)
    for tags in per_item.values():
        for a, b in combinations(sorted(tags), 2):
            cooccur[(a, b)] += 1
    merges = dict(conn.execute("SELECT alias, target FROM graph_merges").fetchall())
    links = []
    for a, b, note in conn.execute("SELECT a, b, note FROM graph_links").fetchall():
        a, b = sorted((merges.get(a, a), merges.get(b, b)))
        if a != b and a in nodes and b in nodes:
            links.append((a, b, note))

    conn.execute("DELETE FROM graph_nodes")
    conn.execute("DELETE FROM graph_edges")
    for tag, n in nodes.items():
        conn.execute(
            "INSERT INTO graph_nodes(tag, count, memories, sessions, last_seen) VALUES (?, ?, ?, ?, ?)",
            (tag, len(n["items"]), n["memories"], n["sessions"], n["last_seen"]),
        )
    for (a, b), w in cooccur.items():
        conn.execute("INSERT INTO graph_edges(a, b, kind, weight) VALUES (?, ?, 'cooccur', ?)", (a, b, w))
    for a, b, note in links:
        conn.execute("INSERT OR IGNORE INTO graph_edges(a, b, kind, weight, note) VALUES (?, ?, 'link', 1, ?)", (a, b, note))
    return len(nodes), len(cooccur) + len(links)
