"""Read-only execution against Otto's own store. Every call here uses the mode=ro connection,
so a write fails inside SQLite; nothing parses SQL. Shared by the routes and the MCP tools."""

from __future__ import annotations

import sqlite3
import time

from app.store import Store

PROGRESS_EVERY = 1000  # VM instructions between deadline checks


def _cell(v):
    return f"<{len(v)} bytes>" if isinstance(v, bytes) else v


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


def run(store: Store, sql: str, max_rows: int, max_seconds: float) -> dict:
    """One statement, read-only, at most max_rows rows, interrupted past max_seconds.
    Errors come back as {"error"}; they are the owner's typos, not failures."""
    sql = sql.strip()
    if not sql:
        return {"error": "empty statement"}
    conn = store.read_only()
    deadline = time.monotonic() + max_seconds
    with store.ro_lock:
        conn.set_progress_handler(lambda: time.monotonic() > deadline, PROGRESS_EVERY)
        t0 = time.perf_counter()
        try:
            cur = conn.execute(sql)
            fetched = cur.fetchmany(max_rows + 1)
            columns = [d[0] for d in cur.description] if cur.description else []
        except (sqlite3.Error, sqlite3.Warning) as e:
            msg = str(e)
            return {"error": f"interrupted after {max_seconds:g}s" if msg == "interrupted" else msg}
        finally:
            conn.set_progress_handler(None, 0)
        ms = round((time.perf_counter() - t0) * 1000, 1)
    rows = [[_cell(v) for v in r] for r in fetched[:max_rows]]
    return {"columns": columns, "rows": rows, "total": len(rows), "truncated": len(fetched) > max_rows, "ms": ms}


def explain(store: Store, sql: str, max_rows: int, max_seconds: float) -> dict:
    sql = sql.strip().rstrip(";")
    if not sql:
        return {"error": "empty statement"}
    r = run(store, f"EXPLAIN QUERY PLAN {sql}", max_rows, max_seconds)
    if "error" in r:
        return r
    return {"lines": [row[3] for row in r["rows"]], "ms": r["ms"]}
