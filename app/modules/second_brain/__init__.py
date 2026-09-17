from __future__ import annotations

import sqlite3

from app.modules import Agent, Manifest, Schedule

MANIFEST = Manifest(
    name="second_brain",
    title="Second Brain",
    hue="#d1a36a",
    icon='<rect x="4" y="3" width="12" height="14" rx="2"></rect><path d="M7 8h6M7 11h6M7 14h4"></path>',
    order=3,
    schedules=(Schedule(task="suggest", every="24h", resource="second_brain", llm=True),),
    agent=Agent(
        placeholder="Ask your second brain…",
        skills=("recall", "tag", "add", "suggest"),
        read_tools=("second_brain_search", "second_brain_get", "second_brain_tags", "second_brain_suggestions"),
        write_tools=("second_brain_add", "second_brain_tag", "second_brain_suggest"),
    ),
)

# (table, old, new): columns a database from before 2026-09-17 names after the module's old name, memory.
RENAMED_COLUMNS = (("second_brain_tags", "memory_id", "item_id"), ("second_brain_suggestions", "memory_ids", "item_ids"))


def setup(config) -> None:
    """Called once by daemon.build after the schemas: rename in place the columns that still carry the old name."""
    conn = sqlite3.connect(config.data.db, timeout=5)
    try:
        for table, old, new in RENAMED_COLUMNS:
            if old in {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}:
                conn.execute(f"ALTER TABLE {table} RENAME COLUMN {old} TO {new}")
        conn.commit()
    finally:
        conn.close()
