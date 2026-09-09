"""Education: questions on the owner's topics, answered and graded on the page; the tutor discusses and revises."""

from __future__ import annotations

import sqlite3

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

# v1 columns on the tables v0 created. schema.sql only creates tables, so a database that already has them is
# brought up here; a fresh one has every column from schema.sql and this finds nothing to add.
COLUMNS = {
    "questions": {"topic_tag": "TEXT"},
    "question_parts": {
        "rubric": "TEXT",
        "answer": "TEXT",
        "answered_at": "TEXT",
        "verdict": "TEXT CHECK (verdict IN ('correct', 'partial', 'incorrect'))",
    },
}


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
