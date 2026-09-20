"""Execution against Otto's own store. `read` uses the mode=ro connection, so SQLite itself refuses
a write; `write` uses the read-write one and holds the whole script in one transaction, so a script
either lands whole or not at all; `execute` is the bare read-write drive both of those sit on.
Nothing parses SQL. Shared by the routes and the MCP tools."""

from __future__ import annotations

import csv
import io
import sqlite3
import time
from functools import lru_cache
from pathlib import Path

from app.store import Store

PROGRESS_EVERY = 1000  # VM instructions between deadline checks
APP = Path(__file__).resolve().parents[2]


def _cell(v):
    return f"<{len(v)} bytes>" if isinstance(v, bytes) else v


def statements(sql: str) -> list[str]:
    """Split on the semicolons SQLite itself calls a statement end, so quoted ones survive."""
    out, buf = [], ""
    for ch in sql:
        buf += ch
        if ch == ";" and sqlite3.complete_statement(buf):
            out.append(buf)
            buf = ""
    out.append(buf)
    return [s for s in (x.strip() for x in out) if s]


@lru_cache(maxsize=1)
def owners() -> dict[str, str]:
    """Table -> the module whose schema.sql creates it (`app` for app/schema.sql), read off a scratch connection each
    schema runs on, so nothing parses SQL. A table no schema creates is `other`: a dropped module's, or the owner's own."""
    out: dict[str, str] = {}
    schemas = [("app", APP / "schema.sql"), *sorted((p.parent.name, p) for p in (APP / "modules").glob("*/schema.sql"))]
    for module, path in schemas:
        scratch = sqlite3.connect(":memory:")
        scratch.executescript(path.read_text("utf-8"))
        out.update({r[0]: module for r in scratch.execute("SELECT name FROM sqlite_master WHERE type = 'table'")})
        scratch.close()
    return out


def tables(store: Store) -> list[dict]:
    """User tables with their module and row count: no sqlite_* internals, no shadow tables of virtual tables."""
    conn = store.read_only()
    with store.ro_lock:
        names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        virtual = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND sql LIKE 'CREATE VIRTUAL TABLE%'")]
        shown = [n for n in names if not any(n != v and n.startswith(v + "_") for v in virtual)]
        return [{"name": n, "module": owners().get(n, "other"), "rows": conn.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0]} for n in shown]


def _describe(store: Store, t: dict) -> dict:
    """A shown table with its columns (name, type, notnull, default, pk), indexes, triggers and CREATE statement."""
    conn = store.read_only()
    name = t["name"]
    with store.ro_lock:
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone()[0]
        columns = [{"name": r[1], "type": r[2], "notnull": bool(r[3]), "default": r[4], "pk": bool(r[5])} for r in conn.execute(f'PRAGMA table_info("{name}")')]
        indexes = [{"name": r[0], "sql": r[1]} for r in conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'index' AND tbl_name = ? AND sql IS NOT NULL ORDER BY name", (name,))]
        triggers = [{"name": r[0], "sql": r[1]} for r in conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'trigger' AND tbl_name = ? ORDER BY name", (name,))]
    return {**t, "columns": columns, "indexes": indexes, "triggers": triggers, "sql": sql}


def table(store: Store, name: str) -> dict | None:
    """One shown table, described; None for a name that is not one."""
    t = next((t for t in tables(store) if t["name"] == name), None)
    return _describe(store, t) if t else None


def schema(store: Store) -> list[dict]:
    """Every shown table, described."""
    return [_describe(store, t) for t in tables(store)]


def _schema_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA schema_version").fetchone()[0]


def _drive(conn: sqlite3.Connection, stmts: list[str], max_rows: int, max_seconds: float) -> dict:
    """Every statement in order on an already-locked connection, under one deadline for the lot.
    Columns and rows come from the last statement that returned any. `changed` sums the rows each
    statement wrote directly, not what its triggers went on to touch; `ddl` says the schema moved,
    so a DROP that changed no rows still leaves a trace."""
    deadline = time.monotonic() + max_seconds
    conn.set_progress_handler(lambda: time.monotonic() > deadline, PROGRESS_EVERY)
    version = _schema_version(conn)
    columns, rows, truncated, changed, i = [], [], False, 0, 0
    t0 = time.perf_counter()
    try:
        for i, stmt in enumerate(stmts, 1):
            cur = conn.execute(stmt)
            if cur.description is None:
                changed += max(cur.rowcount, 0)
                continue
            fetched = cur.fetchmany(max_rows + 1)
            columns = [d[0] for d in cur.description]
            rows = [[_cell(v) for v in r] for r in fetched[:max_rows]]
            truncated = len(fetched) > max_rows
    except (sqlite3.Error, sqlite3.Warning) as e:
        msg = f"interrupted after {max_seconds:g}s" if str(e) == "interrupted" else str(e)
        return {"error": msg if len(stmts) == 1 else f"statement {i}: {msg}",
                "changed": changed, "ddl": _schema_version(conn) != version}
    finally:
        conn.set_progress_handler(None, 0)
    return {"columns": columns, "rows": rows, "total": len(rows), "truncated": truncated,
            "changed": changed, "ddl": _schema_version(conn) != version,
            "statements": len(stmts), "ms": round((time.perf_counter() - t0) * 1000, 1)}


def read(store: Store, sql: str, max_rows: int, max_seconds: float) -> dict:
    """Read-only: a write fails inside SQLite, never here. A refused write leaves the read transaction
    sqlite3 opened for it, and that would pin this connection to a stale snapshot, so it is rolled back."""
    stmts = statements(sql)
    if not stmts:
        return {"error": "empty statement"}
    with store.ro_lock:
        conn = store.read_only()
        try:
            return _drive(conn, stmts, max_rows, max_seconds)
        finally:
            if conn.in_transaction:
                conn.rollback()


def execute(store: Store, sql: str, max_rows: int, max_seconds: float) -> dict:
    """Selects, writes and DDL alike, at most max_rows rows back, interrupted past max_seconds.
    Statements commit one by one, so a script that must be all-or-nothing writes its own BEGIN and
    COMMIT. Errors come back as {"error"}; they are the owner's typos, not failures."""
    stmts = statements(sql)
    if not stmts:
        return {"error": "empty statement"}
    with store.raw() as conn:
        return _drive(conn, stmts, max_rows, max_seconds)


def write(store: Store, sql: str, max_seconds: float) -> dict:
    """Every statement in one transaction: the script lands whole or not at all, whatever the owner's
    own BEGIN said. Rows are never fetched, so {changes, ms} is all a write reports."""
    stmts = statements(sql)
    if not stmts:
        return {"error": "empty statement"}
    with store.raw() as conn:
        conn.execute("BEGIN")
        r = _drive(conn, stmts, 0, max_seconds)
        if conn.in_transaction:
            conn.execute("ROLLBACK" if "error" in r else "COMMIT")
    out = {"changes": r.get("changed", 0), "ms": r.get("ms", 0.0)}
    return {**out, "error": r["error"]} if "error" in r else out


def csv_text(store: Store, name: str) -> str:
    """One table as CSV, its column names first. The caller checks the name against `tables`."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    with store.ro_lock:
        cur = store.read_only().execute(f'SELECT * FROM "{name}"')
        writer.writerow([d[0] for d in cur.description])
        writer.writerows([_cell(v) for v in row] for row in cur)
    return out.getvalue()


def explain(store: Store, sql: str, max_rows: int, max_seconds: float) -> dict:
    """The plan for the first statement. EXPLAIN QUERY PLAN prepares it and never runs it."""
    stmts = statements(sql)
    if not stmts:
        return {"error": "empty statement"}
    r = execute(store, f"EXPLAIN QUERY PLAN {stmts[0].rstrip(';')}", max_rows, max_seconds)
    if "error" in r:
        return r
    return {"lines": [row[3] for row in r["rows"]], "ms": r["ms"]}
