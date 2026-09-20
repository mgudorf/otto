"""Feedback: the owner records a change from any page; a standalone agent classifies and files it as a row."""

from __future__ import annotations

import sqlite3

from app.modules import Agent, Manifest
from app.modules.feedback.queue import add_cleared_at

MANIFEST = Manifest(
    name="feedback",
    title="Feedback",
    hue="#A6ACB8",
    icon="",
    order=99,
    page=False,
    agent=Agent(
        placeholder="",
        read_tools=("docs_list", "docs_read", "feedback_list"),
    ),
)


def setup(config) -> None:
    """Called once by daemon.build after the schemas: `cleared_at` on a feedback table that predates it, and a note whose
    filing job died with the last daemon reads `failed` so the panel offers `retry` instead of `filing…` forever."""
    conn = sqlite3.connect(config.data.db, timeout=5)
    try:
        add_cleared_at(conn)
        conn.execute("UPDATE feedback_items SET status = 'failed', error = 'daemon restarted' WHERE status = 'queued'")
        conn.commit()
    finally:
        conn.close()
