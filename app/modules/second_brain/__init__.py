from __future__ import annotations

import sqlite3

from app.modules import Agent, Manifest, Schedule

MANIFEST = Manifest(
    name="second_brain",
    title="Entry",
    hue="#DDB06F",
    icon='<path d="M10 4C8.6 2.6 5.4 3.2 5.6 5.8C2.8 6.4 2.6 10.2 4.6 11.2C3.4 13.6 6.2 15.8 8.2 14.6C8.8 15.6 9.4 16.2 10 16.2C10.6 16.2 11.2 15.6 11.8 14.6C13.8 15.8 16.6 13.6 15.4 11.2C17.4 10.2 17.2 6.4 14.4 5.8C14.6 3.2 11.4 2.6 10 4Z"></path><path d="M10 4v12.2"></path>',
    order=3,
    facet="entry",
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
