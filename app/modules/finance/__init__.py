import sqlite3

from app.modules import Agent, Manifest

MANIFEST = Manifest(
    name="finance",
    title="Finance",
    hue="#7fb894",
    icon='<rect x="2" y="5" width="16" height="10" rx="1.5"></rect><circle cx="10" cy="10" r="2.5"></circle><path d="M5 8.5v3M15 8.5v3"></path>',
    order=5,
    schedules=(),
    agent=Agent(
        placeholder="Ask about money…",
        skills=("totals", "monthly", "history"),
        read_tools=("finance_list", "finance_get", "finance_totals"),
        write_tools=(),
    ),
)

# v1 column on the table v0 created. schema.sql only creates tables, so a database that already has
# finance_entries is brought up here; a fresh one has the column and this finds nothing to add.
COLUMNS = {"finance_entries": {"due_on": "TEXT"}}


def setup(config) -> None:
    """Called once by daemon.build after the schemas: add the columns a v0 database lacks."""
    conn = sqlite3.connect(config.data.db, timeout=5)
    try:
        for table, columns in COLUMNS.items():
            have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            for name, ddl in columns.items():
                if name not in have:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
        conn.commit()
    finally:
        conn.close()
