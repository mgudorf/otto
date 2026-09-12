"""Execution against Otto's own store. `read` uses the mode=ro connection, so SQLite itself refuses
a write; `execute` uses the read-write one, where anything SQLite accepts runs. Nothing parses SQL.
Shared by the routes and the MCP tools."""

from __future__ import annotations

import sqlite3
import time

from app.store import Store

PROGRESS_EVERY = 1000  # VM instructions between deadline checks


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


def tables(store: Store) -> list[dict]:
    """User tables with row counts: no sqlite_* internals, no shadow tables of virtual tables."""
    conn = store.read_only()
    with store.ro_lock:
        names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        virtual = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND sql LIKE 'CREATE VIRTUAL TABLE%'")]
        shown = [n for n in names if not any(n != v and n.startswith(v + "_") for v in virtual)]
        return [{"name": n, "rows": conn.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0]} for n in shown]


def schema(store: Store) -> list[dict]:
    """Every shown table with its CREATE statement, columns and row count."""
    conn = store.read_only()
    out = []
    for t in tables(store):
        with store.ro_lock:
            sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = ?", (t["name"],)).fetchone()[0]
            cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{t["name"]}")')]
        out.append({**t, "columns": cols, "sql": sql})
    return out


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
    """Read-only: a write fails inside SQLite, never here."""
    stmts = statements(sql)
    if not stmts:
        return {"error": "empty statement"}
    with store.ro_lock:
        return _drive(store.read_only(), stmts, max_rows, max_seconds)


def execute(store: Store, sql: str, max_rows: int, max_seconds: float) -> dict:
    """Selects, writes and DDL alike, at most max_rows rows back, interrupted past max_seconds.
    Statements commit one by one, so a script that must be all-or-nothing writes its own BEGIN and
    COMMIT. Errors come back as {"error"}; they are the owner's typos, not failures."""
    stmts = statements(sql)
    if not stmts:
        return {"error": "empty statement"}
    with store.raw() as conn:
        return _drive(conn, stmts, max_rows, max_seconds)


def explain(store: Store, sql: str, max_rows: int, max_seconds: float) -> dict:
    """The plan for the first statement. EXPLAIN QUERY PLAN prepares it and never runs it."""
    stmts = statements(sql)
    if not stmts:
        return {"error": "empty statement"}
    r = execute(store, f"EXPLAIN QUERY PLAN {stmts[0].rstrip(';')}", max_rows, max_seconds)
    if "error" in r:
        return r
    return {"lines": [row[3] for row in r["rows"]], "ms": r["ms"]}
