"""Database: every table under the module that owns it, any SQL against the store, the queries worth keeping.

`run` reads; SQLite's own refusal on the read-only connection is what tells the page a statement writes,
and `write` is the confirmed path, a backup then one transaction."""

from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, Body, HTTPException, Request, Response

from app.modules.database import query
from app.store import Store, now_iso, parse, tags_for

router = APIRouter(prefix="/api/database")

RESOURCE = "db"  # shared with data.backup and data.vacuum, so they never overlap a query
REFUSED = "readonly"  # what SQLite says when a statement tries to write on the mode=ro connection
QUERY = "query:"      # a saved query's id, so tables and saved queries share one list
FACET = "database"    # the module's immutable tag, the only one its rows carry


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
    return store.query("SELECT * FROM database_queries ORDER BY updated_at DESC")


def _modules(tables: list[dict], registry) -> list[dict]:
    """The tables grouped under their modules: `app` first, then rail order, then any module no manifest lists, `other` last."""
    by: dict[str, list[dict]] = {}
    for t in tables:
        by.setdefault(t["module"], []).append(t)
    order = ["app", *(m.name for m in registry.ordered()), *sorted(by), "other"]
    out, seen = [], set()
    for name in order:
        if name in by and name not in seen:
            seen.add(name)
            out.append({"name": name, "rows": sum(t["rows"] for t in by[name]), "tables": by[name]})
    return out


@router.get("/left")
def left(request: Request) -> dict:
    st = request.app.state
    return {
        "modules": _modules(query.tables(st.store), st.registry),
        "saved": [{"id": q["id"], "name": q["name"], "sql": q["sql"], "updated_at": q["updated_at"]} for q in _saved(st.store)],
    }


@router.get("/blank")
def blank(request: Request) -> dict:
    store: Store = request.app.state.store
    return {"db": store.path.name, "size_bytes": _size_bytes(store), "tables": len(query.tables(store))}


@router.get("/table/{name}")
def table(request: Request, name: str) -> dict:
    """One table's schema: module, rows, columns with their types and constraints, indexes, triggers, the CREATE statement."""
    t = query.table(request.app.state.store, name)
    if t is None:
        raise HTTPException(404, "no such table")
    return t


@router.get("/export/{name}")
def export(request: Request, name: str) -> Response:
    """The whole table as CSV, named after the table and the moment it left."""
    st = request.app.state
    t = query.table(st.store, name)
    if t is None:
        raise HTTPException(404, "no such table")
    body = query.csv_text(st.store, name)
    st.store.event("database", "exported", f"{name}: {t['rows']:,} rows")
    filename = f"{name}-{datetime.now():%Y%m%d-%H%M%S}.csv"
    return Response(body, media_type="text/csv", headers={"content-disposition": f'attachment; filename="{filename}"'})


@router.get("/item/{item_id}")
def item_route(request: Request, item_id: str) -> dict:
    return item(request.app.state.store, item_id)


@router.post("/action/{verb}")
async def action(request: Request, verb: str, body: dict = Body(default={})) -> dict:
    """Each action validates in the request and returns the job to run; bad input is a 400, never a failed job."""
    st = request.app.state
    make = ACTIONS.get(verb)
    if make is None:
        raise HTTPException(404, f"unknown action {verb}")
    return await st.runner.run_action(f"database.{verb}", "database", RESOURCE, make(st, body))


def _run(st, body: dict):
    """The read path. A statement SQLite refuses on the read-only connection comes back as a question."""
    d, sql = st.config.database, body.get("sql") or ""

    async def job(ctx):
        r = await asyncio.to_thread(query.read, st.store, sql, d.max_rows, d.max_seconds)
        return {"needs_confirm": True} if REFUSED in (r.get("error") or "") else r

    return job


def _write(st, body: dict):
    """The confirmed path: a backup of the store, then the script in one transaction."""
    d, sql = st.config.database, body.get("sql") or ""
    if not query.statements(sql):
        raise HTTPException(400, "sql is required")
    dest = st.config.data.db.parent / "backups" / f"otto-{datetime.now():%Y%m%d-%H%M%S}-pre-write.db"

    async def job(ctx):
        await asyncio.to_thread(st.store.backup, dest)
        r = await asyncio.to_thread(query.write, st.store, sql, d.max_seconds)
        if "error" not in r:
            ctx.event("wrote", f"{r['changes']:,} rows: {' '.join(sql.split())[:120]}")
        return {**r, "backup": dest.name}

    return job


def _explain(st, body: dict):
    d, sql = st.config.database, body.get("sql") or ""

    async def job(ctx):
        return await asyncio.to_thread(query.explain, st.store, sql, d.max_rows, d.max_seconds)

    return job


def save_query(conn, name: str, sql: str) -> int:
    ts = now_iso()
    conn.execute(
        "INSERT INTO database_queries(name, sql, created_at, updated_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(name) DO UPDATE SET sql = excluded.sql, updated_at = excluded.updated_at",
        (name, sql, ts, ts),
    )
    return conn.execute("SELECT id FROM database_queries WHERE name = ?", (name,)).fetchone()[0]


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


def _ref(value) -> int:
    """A saved query's id, whether it arrives bare or as the `query:<id>` the page lists it under."""
    s = str(value or "")
    s = s[len(QUERY):] if s.startswith(QUERY) else s
    return int(s) if s.isdigit() else 0


def _delete(st, body: dict):
    row = st.store.one("SELECT id, name FROM database_queries WHERE id = ?", (_ref(body.get("id")),))
    if row is None:
        raise HTTPException(404, "no such saved query")

    async def job(ctx):
        with ctx.commit() as conn:
            conn.execute("DELETE FROM database_queries WHERE id = ?", (row["id"],))
        ctx.event("deleted", row["name"], ref=str(row["id"]))
        return {"id": row["id"]}

    return job


ACTIONS = {"run": _run, "write": _write, "explain": _explain, "save": _save, "delete": _delete}


# ---- shell hooks ---------------------------------------------------------------------------
def _when(ts: str) -> str:
    """A stored moment on the owner's own clock, so the feed orders it against every other module's rows."""
    return parse(ts).astimezone().strftime("%Y-%m-%dT%H:%M")


def _comment(c: dict) -> str:
    """What a column promises: its key, whether it may be empty, what it holds when nothing is given."""
    parts = ["primary key"] if c["pk"] else (["not null"] if c["notnull"] else [])
    if c["default"] is not None:
        parts.append(f"default {c['default']}")
    return ", ".join(parts)


def _table_row(t: dict) -> dict:
    """One described table as a ROW. A table is the store's own shape rather than something the owner wrote, so it
    takes no tag of its own and carries no moment: undated, it sorts behind everything in Recent."""
    return {"id": t["name"], "module": "database", "title": t["name"], "when": None, "fixed": [FACET],
            "tags": ["table"], "taggable": False, "type": "table", "right": f"{t['rows']:,} rows",
            "cols": [[c["name"], c["type"], _comment(c)] for c in t["columns"]],
            "href": "/api/database/export/" + t["name"],   # the url Export needs; a [verb, label] pair carries none
            "verbs": [["query", "Query"], ["export", "Export"]]}


def _query_row(store: Store, q: dict) -> dict:
    """One saved query as a ROW, stamped with the moment it was last kept."""
    row_id = f"{QUERY}{q['id']}"
    return {"id": row_id, "module": "database", "title": q["name"], "when": _when(q["updated_at"]),
            "fixed": [FACET], "tags": sorted({"query", *tags_for(store, "database", [row_id])[row_id]}),
            "type": "query", "snip": "saved", "sql": q["sql"],
            "verbs": [["delete", "Delete"]]}   # Load waits on the query console returning to the page


def rows(store: Store, limit: int = 200) -> list[dict]:
    """The saved queries newest first, then every table the store holds."""
    return [*(_query_row(store, q) for q in _saved(store)), *(_table_row(t) for t in query.schema(store))][:limit]


def item(store: Store, item_id: str) -> dict:
    """A table with its columns, or a saved query with its text."""
    if item_id.startswith(QUERY):
        ref = item_id[len(QUERY):]
        q = store.one("SELECT * FROM database_queries WHERE id = ?", (int(ref),)) if ref.isdigit() else None
        if q is None:
            raise HTTPException(404, "no such saved query")
        return _query_row(store, q)
    t = query.table(store, item_id)
    if t is None:
        raise HTTPException(404, "no such table")
    return _table_row(t)


def numbers(store: Store) -> dict:
    return {"value": _human(_size_bytes(store)), "label": "database"}


def context(store: Store, registry) -> str:
    lines = [f"Store: {store.path.name}, {_human(_size_bytes(store))}. Tables by module (name, rows, columns):"]
    for m in _modules(query.schema(store), registry):
        lines.append(f"{m['name']}:")
        lines += [f"  {t['name']} ({t['rows']:,}): {', '.join(c['name'] for c in t['columns'])}" for t in m["tables"]]
    saved = _saved(store)
    lines.append("Saved queries: " + (", ".join(q["name"] for q in saved) if saved else "none"))
    return "\n".join(lines)
