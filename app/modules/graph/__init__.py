from __future__ import annotations

import sqlite3

from app.modules import Agent, Manifest, Schedule

MANIFEST = Manifest(
    name="graph",
    title="Graph",
    hue="#C1BE75",
    icon='<circle cx="5" cy="6" r="2"></circle><circle cx="15" cy="5" r="2"></circle><circle cx="10" cy="15" r="2"></circle><circle cx="16" cy="13" r="1.5"></circle><path d="M7 6.5l6-1M6 7.5l3 6M11.5 14l3-1"></path>',
    order=7,
    schedules=(Schedule(task="rebuild", every="15m", resource="graph"),),
    agent=Agent(
        placeholder="Curate the graph…",
        skills=("neighbors", "link", "merge", "prune"),
        read_tools=("graph_nodes", "graph_neighbors", "graph_items"),
        write_tools=("graph_link", "graph_unlink", "graph_merge", "graph_prune", "graph_restore"),
    ),
)


def setup(config) -> None:
    """Called once by daemon.build after the schemas: graph_nodes counted a tag's Second Brain items as `memories`
    before 2026-09-17; the column is renamed in place and the next rebuild fills it."""
    conn = sqlite3.connect(config.data.db, timeout=5)
    try:
        if "memories" in {r[1] for r in conn.execute("PRAGMA table_info(graph_nodes)")}:
            conn.execute("ALTER TABLE graph_nodes RENAME COLUMN memories TO items")
        conn.commit()
    finally:
        conn.close()
