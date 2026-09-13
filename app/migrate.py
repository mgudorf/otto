"""An older database brought to the current table names before the schemas run.

Every table is named after the module that owns it: app_ for the platform, <module>_ for a module. RENAMES is every
name a table has had, old -> current; renaming a table is one more line here, and the schemas keep only the new name.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path

from app.store import Store

RENAMES = {
    # 2026-09-13: the platform tables took the app_ prefix
    "tasks": "app_tasks",
    "jobs": "app_jobs",
    "job_logs": "app_job_logs",
    "settings": "app_settings",
    "cursors": "app_cursors",
    "events": "app_events",
    "sessions": "app_sessions",
    "session_turns": "app_session_turns",
    "module_errors": "app_module_errors",
    "llm_runs": "app_llm_runs",
    # 2026-09-13: module tables that lacked their module's prefix
    "topics": "education_topics",
    "questions": "education_questions",
    "question_parts": "education_question_parts",
    "memories": "memory_items",
    "memories_fts": "memory_fts",
    "feedback": "feedback_items",
    "db_queries": "database_queries",
    "search_topics": "web_search_topics",
    "search_findings": "web_search_findings",
}


def pending(conn: sqlite3.Connection) -> dict[str, str]:
    """The renames this database still needs: every old name it holds a table under."""
    have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    return {old: new for old, new in RENAMES.items() if old in have}


def _exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone() is not None


def rename_tables(store: Store, backup_dir: Path) -> list[str]:
    """Rename what the database still holds under an old name, in one transaction, after a backup into backup_dir.

    Indexes and triggers on a renamed table are dropped for the schemas to recreate under their new names. An FTS5
    table is dropped rather than renamed, and so is one whose content table moves, because a rename leaves its
    content= option pointing at the old name; the schemas create both again, empty, and rebuild_fts refills them.
    Returns those FTS tables. A new name already taken by a table with rows is a conflict left to the owner; one
    taken by an empty table (a schema that ran before this did) is dropped first. Nothing here changes a row.
    """
    with store.raw() as conn:
        todo = pending(conn)
        if not todo:
            return []
        store.backup(backup_dir / f"otto-{datetime.now():%Y%m%d-%H%M%S}-pre-rename.db")
        broken_before = len(conn.execute("PRAGMA foreign_key_check").fetchall())
        conn.execute("PRAGMA foreign_keys=OFF")
        try:
            conn.execute("BEGIN")
            try:
                # A rename re-parses every trigger, so nothing may dangle: the triggers and indexes of a moving table
                # go first, then every FTS table that goes, with any trigger that names it; the schemas recreate them all.
                for old in todo:
                    for kind, name in _objects_on(conn, old):
                        conn.execute(f'DROP {kind} "{name}"')
                rebuild = []
                for name in _fts_to_drop(conn, todo):
                    for (trigger,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger' AND sql LIKE ?", (f"%{name}%",)).fetchall():
                        conn.execute(f'DROP TRIGGER "{trigger}"')
                    conn.execute(f'DROP TABLE "{name}"')
                    rebuild.append(todo.get(name, name))
                for old, new in todo.items():
                    if not _exists(conn, old):
                        continue    # an FTS table dropped above
                    if _exists(conn, new):
                        if conn.execute(f'SELECT COUNT(*) FROM "{new}"').fetchone()[0]:
                            raise RuntimeError(f"cannot rename {old} to {new}: both exist and {new} has rows")
                        conn.execute(f'DROP TABLE "{new}"')
                    conn.execute(f'ALTER TABLE "{old}" RENAME TO "{new}"')
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")
        finally:
            conn.execute("PRAGMA foreign_keys=ON")
        broken = conn.execute("PRAGMA foreign_key_check").fetchall()
        if len(broken) > broken_before:
            raise RuntimeError(f"tables reference missing rows after the rename: {broken[:5]}")
        return rebuild


def _objects_on(conn: sqlite3.Connection, table: str) -> list[tuple[str, str]]:
    """(type, name) of every index and trigger on the table that a schema created; auto-indexes have no sql and follow the table."""
    return conn.execute(
        "SELECT type, name FROM sqlite_master WHERE type IN ('index', 'trigger') AND tbl_name = ? AND sql IS NOT NULL", (table,)
    ).fetchall()


def _fts_to_drop(conn: sqlite3.Connection, todo: dict[str, str]) -> list[str]:
    """Every FTS5 table that is renamed itself or whose content table is."""
    out = []
    for name, sql in conn.execute("SELECT name, sql FROM sqlite_master WHERE type = 'table' AND sql LIKE 'CREATE VIRTUAL TABLE%'").fetchall():
        m = re.search(r"content\s*=\s*['\"]?(\w+)", sql)
        if name in todo or (m and m.group(1) in todo):
            out.append(name)
    return out


def rebuild_fts(store: Store, names: list[str]) -> None:
    """Refill the FTS5 tables the schemas created empty, from their content tables."""
    for name in names:
        store.execute(f'INSERT INTO "{name}"("{name}") VALUES (\'rebuild\')')
