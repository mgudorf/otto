"""Database: look at every table, run read-only SQL, keep the queries worth keeping."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Body, HTTPException, Request

from app.modules.database import query
from app.store import Store, now_iso

router = APIRouter(prefix="/api/database")

RESOURCE = "db"  # shared with data.backup and data.vacuum, so they never overlap a query


def _size_bytes(store: Store) -> int:
    db = store.path
    return sum(p.stat().st_size for p in (db, db.with_name(db.name + "-wal")) if p.exists())


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} GB" if n >= 1024 else f"{n:.1f} MB"


def _saved(store: Store) -> list[dict]:
    return store.query("SELECT * FROM db_queries ORDER BY updated_at DESC")


@router.get("/left")
def left(request: Request) -> dict:
    store: Store = request.app.state.store
    tables = query.tables(store)
    saved = _saved(store)
    return {"groups": [
        {"label": "tables", "count": len(tables),
         "rows": [{"id": f"table:{t['name']}", "module": "database", "text": t["name"], "stampText": f"{t['rows']:,}"} for t in tables]},
        {"label": "saved", "count": len(saved),
         "rows": [{"id": f"query:{q['id']}", "module": "database", "text": q["name"], "stamp": q["updated_at"], "sql": q["sql"], "query_id": q["id"]} for q in saved]},
    ]}


@router.get("/blank")
def blank(request: Request) -> dict:
    store: Store = request.app.state.store
    return {"db": store.path.name, "size_bytes": _size_bytes(store), "tables": len(query.tables(store))}


@router.post("/action/{verb}")
async def action(request: Request, verb: str, body: dict = Body(default={})) -> dict:
    """Each action validates in the request and returns the job to run; bad input is a 400, never a failed job."""
    st = request.app.state
    make = ACTIONS.get(verb)
    if make is None:
        raise HTTPException(404, f"unknown action {verb}")
    return await st.runner.run_action(f"database.{verb}", "database", RESOURCE, make(st, body))


def _run(st, body: dict):
    d, sql = st.config.database, body.get("sql") or ""

    async def job(ctx):
        return await asyncio.to_thread(query.run, st.store, sql, d.max_rows, d.max_seconds)

    return job


def _explain(st, body: dict):
    d, sql = st.config.database, body.get("sql") or ""

    async def job(ctx):
        return await asyncio.to_thread(query.explain, st.store, sql, d.max_rows, d.max_seconds)

    return job


def save_query(conn, name: str, sql: str) -> int:
    ts = now_iso()
    conn.execute(
        "INSERT INTO db_queries(name, sql, created_at, updated_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(name) DO UPDATE SET sql = excluded.sql, updated_at = excluded.updated_at",
        (name, sql, ts, ts),
    )
    return conn.execute("SELECT id FROM db_queries WHERE name = ?", (name,)).fetchone()[0]


def _save(st, body: dict):
    name, sql = (body.get("name") or "").strip(), (body.get("sql") or "").strip()
    if not name or not sql:
        raise HTTPException(400, "name and sql are required")

    async def job(ctx):
        with ctx.commit() as conn:
            qid = save_query(conn, name, sql)
        ctx.event("saved", f"{name}: {sql[:120]}", ref=str(qid))
        return {"id": qid}

    return job


def _delete(st, body: dict):
    row = st.store.one("SELECT id, name FROM db_queries WHERE id = ?", (int(body.get("id") or 0),))
    if row is None:
        raise HTTPException(404, "no such saved query")

    async def job(ctx):
        with ctx.commit() as conn:
            conn.execute("DELETE FROM db_queries WHERE id = ?", (row["id"],))
        ctx.event("deleted", row["name"], ref=str(row["id"]))
        return {"id": row["id"]}

    return job


ACTIONS = {"run": _run, "explain": _explain, "save": _save, "delete": _delete}


# ---- shell hooks ---------------------------------------------------------------------------
def numbers(store: Store) -> dict:
    return {"value": _human(_size_bytes(store)), "label": "database"}


def context(store: Store, registry) -> str:
    lines = [f"Store: {store.path.name}, {_human(_size_bytes(store))}. Tables (name, rows, columns):"]
    lines += [f"  {t['name']} ({t['rows']:,}): {', '.join(t['columns'])}" for t in query.schema(store)]
    saved = _saved(store)
    lines.append("Saved queries: " + (", ".join(q["name"] for q in saved) if saved else "none"))
    return "\n".join(lines)
