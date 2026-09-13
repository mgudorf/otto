"""Education: questions on the owner's topics, answered on the page and graded by the tutor in the session; the owner completes each quiz."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from app.modules import Agent, Manifest, Schedule

MANIFEST = Manifest(
    name="education",
    title="Education",
    hue="#7a9fd6",
    icon='<path d="M2 8l8-4 8 4-8 4-8-4Z"></path><path d="M6 10v4c0 1.2 2 2 4 2s4-.8 4-2v-4"></path><path d="M18 8v5"></path>',
    order=2,
    schedules=(Schedule(task="generate", every="24h", resource="education", llm=True),),
    agent=Agent(
        placeholder="Ask the tutor…",
        skills=("question-gen", "quiz", "explain", "plan"),
        read_tools=("education_topics", "education_questions", "education_question", "education_feedback"),
        write_tools=("education_add_topic", "education_add_question", "education_grade", "education_record_feedback"),
    ),
)

SCHEMA = Path(__file__).parent / "schema.sql"

# Columns added to tables an older database created. schema.sql only creates tables, so a database that already has
# them is brought up here; a fresh one has every column from schema.sql and this finds nothing to add.
COLUMNS = {
    "questions": {"topic_tag": "TEXT", "deleted_at": "TEXT"},                   # v1, v3
    "question_parts": {
        "rubric": "TEXT",                                                       # v1
        "answer": "TEXT",
        "answered_at": "TEXT",
        "verdict": "TEXT CHECK (verdict IN ('correct', 'partial', 'incorrect'))",
        "title": "TEXT",                                                        # v2
    },
}


def _sql(conn: sqlite3.Connection, table: str) -> str:
    return conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()[0]


def _create(table: str, as_name: str) -> str:
    """The table's CREATE from schema.sql, under another name: the rebuilds below never restate the shape."""
    m = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \(.*?\n\);", SCHEMA.read_text("utf-8"), re.S)
    return m.group(0).replace(f"IF NOT EXISTS {table}", as_name, 1)


def setup(config) -> None:
    """Called once by daemon.build after the schemas: add the columns an older database lacks, and rebuild the two
    tables v2 reshaped. The difficulty scale runs 1 to 10 now (a value d on the old 1 to 5 scale becomes 2d-1), a
    skipped question no longer exists (those rows go, with their parts; their feedback keeps its words), and
    graded_at became completed_at. A CHECK cannot be altered in place, so each table is rebuilt the documented way:
    create under a new name, copy, drop, rename, with foreign keys off for the duration."""
    conn = sqlite3.connect(config.data.db, timeout=5, isolation_level=None)
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("BEGIN")
        try:
            for table, columns in COLUMNS.items():
                have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
                for name, ddl in columns.items():
                    if name not in have:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
            if "BETWEEN 1 AND 10" not in _sql(conn, "topics"):
                conn.execute(_create("topics", "topics_v2"))
                conn.execute(
                    "INSERT INTO topics_v2(id, name, description, difficulty, created_at, retired_at) "
                    "SELECT id, name, description, 2 * difficulty - 1, created_at, retired_at FROM topics"
                )
                conn.execute("DROP TABLE topics")
                conn.execute("ALTER TABLE topics_v2 RENAME TO topics")
            if "skipped_at" in _sql(conn, "questions"):
                conn.execute("DELETE FROM question_parts WHERE question_id IN (SELECT id FROM questions WHERE skipped_at IS NOT NULL)")
                conn.execute("UPDATE education_feedback SET question_id = NULL WHERE question_id IN (SELECT id FROM questions WHERE skipped_at IS NOT NULL)")
                conn.execute(_create("questions", "questions_v2"))
                conn.execute(
                    "INSERT INTO questions_v2(id, topic_id, title, topic_tag, premise, difficulty, source, created_at, started_at, completed_at, score) "
                    "SELECT id, topic_id, title, topic_tag, premise, 2 * difficulty - 1, source, created_at, started_at, graded_at, score "
                    "FROM questions WHERE skipped_at IS NULL"
                )
                conn.execute("DROP TABLE questions")
                conn.execute("ALTER TABLE questions_v2 RENAME TO questions")
                conn.execute("CREATE INDEX IF NOT EXISTS questions_created ON questions(created_at)")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
        broken = conn.execute("PRAGMA foreign_key_check").fetchall()
        if broken:
            raise RuntimeError(f"education tables reference missing rows after migration: {broken[:5]}")
    finally:
        conn.close()
