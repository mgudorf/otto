"""Science: the file tree, a notebook or a script, runs on its kernel or as a subprocess, and the owner's schedules. Runs are jobs; their outputs stream over server-sent events."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Body, HTTPException, Request

from app.api import event_stream
from app.modules.science import notebook, runs, state
from app.store import Store, iso, now_iso, parse

router = APIRouter(prefix="/api/science")

KEY = "science"          # broadcast key for the events stream
RESOURCE = "science"     # jobs that touch the root, not one kernel


def _root():
    return state.config.root


def _live(file_id: str) -> bool:
    return file_id in state.scripts or state.kernels.get(_root() / file_id) is not None


def _row(f: dict) -> dict:
    return {"id": f["id"], "module": "science", "text": f["name"], "stamp": f["mtime"], "live": _live(f["id"])}


def _mark(nodes: list[dict]) -> int:
    """Flag the files running now; returns the file count."""
    n = 0
    for node in nodes:
        if node["kind"] == "dir":
            n += _mark(node["children"])
        else:
            n += 1
            node["live"] = _live(node["id"])
    return n


@router.get("/left")
def left(request: Request) -> dict:
    tree = notebook.tree(_root())
    _mark(tree)
    return {"tree": tree}


@router.get("/blank")
def blank(request: Request) -> dict:
    return {"kernels": len(state.kernels.alive()), "files": len(notebook.scan(_root()))}


@router.get("/item/{file_id:path}")
def item_route(request: Request, file_id: str) -> dict:
    return item(request.app.state.store, file_id)


@router.get("/events")
async def events(request: Request):
    return event_stream(request, KEY)


@router.post("/action/{verb}")
async def action(request: Request, verb: str, body: dict = Body(default={})) -> dict:
    st = request.app.state
    if verb == "run":
        return _run(st, body)
    if verb == "new":
        return await _new(st, body)
    if verb not in KERNEL_ACTIONS and verb not in EDIT_ACTIONS and verb not in SCHEDULE_ACTIONS:
        raise HTTPException(404, f"unknown action {verb}")
    file_id = str(body.get("id", ""))
    path = notebook.resolve(_root(), file_id)
    if verb in SCHEDULE_ACTIONS:
        return SCHEDULE_ACTIONS[verb](st, path, file_id, body)
    if verb == "interrupt" and path.suffix == ".py":
        proc = state.scripts.get(file_id)
        if proc is None:
            raise HTTPException(409, "not running")
        proc.kill()
        st.store.event("science", "interrupted", path.name, ref=file_id)
        return {"ok": True}
    if verb in KERNEL_ACTIONS:   # never queued: each must get past a running cell
        if state.kernels.get(path) is None:
            raise HTTPException(409, "no kernel")
        past, fn = KERNEL_ACTIONS[verb]
        await fn(path)
        st.store.event("science", past, path.name, ref=file_id)
        return {"ok": True}
    if path.suffix != ".ipynb":
        raise HTTPException(400, "only notebooks are edited here")
    # Direct, not queued: one read-modify-write with no await inside, so it never lands inside a run's output write.
    return EDIT_ACTIONS[verb](st, path, file_id, body)


def _run(st, body: dict) -> dict:
    file_id = str(body.get("id", ""))
    path = notebook.resolve(_root(), file_id)

    def publish(ev: dict) -> None:
        st.broadcast.publish(KEY, {"path": file_id, "ts": now_iso(), **ev})

    if path.suffix == ".py":
        if file_id in state.scripts:
            raise HTTPException(409, "already running")

        async def script(ctx):
            out = await runs.run_script(st.store, path, file_id, publish)
            ctx.event("ran", f"{path.name}: {out}", ref=file_id)
            return out

        return {"job": _fire(st.runner.submit("science.script", "science", f"script:{file_id}", "action", script))}

    index = int(body.get("index", -1))
    nb = notebook.read(path)
    if not 0 <= index < len(nb.cells) or nb.cells[index].cell_type != "code":
        raise HTTPException(400, "not a code cell")
    cell_id = nb.cells[index].get("id")
    source = notebook.join(nb.cells[index].source)

    async def job(ctx):
        count, outputs = await runs.run_cell(path, cell_id, source, lambda ev: publish({"index": index, **ev}))
        ctx.event("ran", f"{path.name} [{count}]", ref=file_id)
        return f"{path.name} cell {index}: {len(outputs)} output(s)"

    return {"job": _fire(st.runner.submit("science.run", "science", f"kernel:{file_id}", "action", job))}


def _fire(job) -> int:
    """The page follows the run over events, not the job's future; a failure is in the jobs row, so retrieve it here or asyncio logs it as lost."""
    job.done.add_done_callback(lambda f: f.cancelled() or f.exception())
    return job.id


KERNEL_ACTIONS = {
    "interrupt": ("interrupted", lambda path: state.kernels.interrupt(path)),
    "restart": ("restarted", lambda path: state.kernels.restart(path)),
    "shutdown": ("shut down", lambda path: state.kernels.shutdown(path)),
}


# ---- edits: the file on disk is the document; every edit is one atomic write -----------------
def _cell_index(nb, body: dict) -> int:
    index = int(body.get("index", -1))
    if not 0 <= index < len(nb.cells):
        raise HTTPException(400, "no such cell")
    return index


def _set_cell(st, path, file_id, body) -> dict:
    nb = notebook.read(path)
    index = _cell_index(nb, body)
    nb.cells[index].source = str(body.get("source", ""))
    notebook.write(path, nb)
    return {"id": file_id, "index": index}


def _set_cells(st, path, file_id, body) -> dict:
    """Replace the cell list. A cell naming an existing id of the same type keeps its outputs; anything else is new.
    A vanished cell is logged as deleted only when its text left the notebook, so a merge reports nothing."""
    nb = notebook.read(path)
    have = {c.get("id"): c for c in nb.cells}
    cells = []
    for spec in body.get("cells", []):
        kind = spec.get("type", "code")
        if kind not in notebook.TYPES:
            raise HTTPException(400, f"no cell type {kind}")
        source = str(spec.get("source", ""))
        old = have.pop(spec.get("id"), None)
        if old is not None and old.cell_type == kind:
            old.source = source
            cells.append(old)
        else:
            cells.append(notebook.new_cell(kind, source))
    nb.cells = cells
    notebook.write(path, nb)
    kept = "\n".join(notebook.join(c.source) for c in cells)
    for c in have.values():
        text = notebook.join(c.source).strip()
        if text and text not in kept:
            st.store.event("science", "deleted", f"{path.name} cell: {text[:80]}", ref=file_id)
    return {"id": file_id, "cells": len(cells)}


def _insert_cell(st, path, file_id, body) -> dict:
    nb = notebook.read(path)
    after = int(body.get("after", len(nb.cells) - 1))
    kind = body.get("type", "code")
    if kind not in notebook.TYPES:
        raise HTTPException(400, f"no cell type {kind}")
    index = max(0, min(after + 1, len(nb.cells)))
    nb.cells.insert(index, notebook.new_cell(kind, str(body.get("source", ""))))
    notebook.write(path, nb)
    return {"id": file_id, "index": index}


def _delete_cell(st, path, file_id, body) -> dict:
    nb = notebook.read(path)
    index = _cell_index(nb, body)
    gone = nb.cells.pop(index)
    notebook.write(path, nb)
    st.store.event("science", "deleted", f"{path.name} cell {index}: {notebook.join(gone.source)[:80]}", ref=file_id)
    return {"id": file_id, "index": index}


EDIT_ACTIONS = {"set_cell": _set_cell, "set_cells": _set_cells, "insert_cell": _insert_cell, "delete_cell": _delete_cell}


async def _new(st, body: dict) -> dict:
    kind = str(body.get("kind", "ipynb"))
    path = notebook.target(_root(), str(body.get("path", "")), kind)

    async def run(ctx):
        new_id = notebook.create(_root(), path, kind)
        ctx.event("created", new_id, ref=new_id)
        return {"id": new_id, "kind": kind}

    return await st.runner.run_action("science.new", "science", RESOURCE, run)


# ---- schedules: one row per file, read by the `due` task ---------------------------------------
def _schedule(st, path, file_id, body) -> dict:
    every = str(body.get("every", "")).strip()
    at = str(body.get("at") or "").strip() or None
    try:
        seconds = runs.every_seconds(every)
        first = runs.first_run(seconds, at)
    except ValueError as e:
        raise HTTPException(400, str(e))
    st.store.execute(
        """INSERT INTO science_schedules(path, every_seconds, at, next_run) VALUES (?, ?, ?, ?)
           ON CONFLICT(path) DO UPDATE SET every_seconds = excluded.every_seconds, at = excluded.at, next_run = excluded.next_run""",
        (file_id, seconds, at, first),
    )
    st.store.event("science", "scheduled", f"{path.name} every {every}" + (f" at {at}" if at else ""), ref=file_id)
    return {"id": file_id, "next_run": first}


def _unschedule(st, path, file_id, body) -> dict:
    if st.store.execute("DELETE FROM science_schedules WHERE path = ?", (file_id,)).rowcount:
        st.store.event("science", "unscheduled", path.name, ref=file_id)
    return {"id": file_id}


SCHEDULE_ACTIONS = {"schedule": _schedule, "unschedule": _unschedule}


# ---- shell hooks ---------------------------------------------------------------------------
def item(store: Store, file_id: str) -> dict:
    path = notebook.resolve(_root(), file_id)
    st = path.stat()
    base = {
        "id": file_id, "module": "science", "text": path.name, "kind": path.suffix[1:], "created_at": notebook.mtime_iso(st.st_mtime), "actions": [],
        "schedule": store.one("SELECT * FROM science_schedules WHERE path = ?", (file_id,)),
    }
    if path.suffix == ".py":
        last = store.one("SELECT started_at, finished_at, status, exit_code, output FROM science_script_runs WHERE path = ? ORDER BY id DESC LIMIT 1", (file_id,))
        return {**base, "kernel": None, "cells": [], "source": path.read_text("utf-8", "replace"), "running": file_id in state.scripts, "last": last}
    k = state.kernels.get(path)
    nb = notebook.read(path)
    kernel = {"state": k.state, "executions": k.executions, "started_at": k.started_at} if k else None
    return {**base, "kernel": kernel, "cells": notebook.cells(nb, k.running if k else None), "source": None}


def numbers(store: Store) -> dict:
    return {"value": len(state.kernels.alive()), "label": "kernels"}


def today(store: Store) -> list[dict]:
    start = iso(datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0))
    return [_row(f) for f in notebook.scan(_root()) if f["mtime"] >= start]


def context(store: Store, registry) -> str:
    files = notebook.scan(_root())
    lines = [f"Root: {_root()} ({len(files)} files)"]
    alive = state.kernels.alive()
    lines.append("Kernels: " + ("; ".join(f"{k.path.name} {k.state}, idle {k.idle_minutes():.0f} min, {k.executions} runs" for k in alive) or "none"))
    sched = store.query("SELECT path, next_run, last_status FROM science_schedules ORDER BY next_run")
    lines.append("Scheduled: " + ("; ".join(f"{r['path']} next {r['next_run']}, last {r['last_status'] or 'never'}" for r in sched) or "none"))
    lines.append("Most recently modified:")
    lines += [f"  {f['id']} ({f['mtime']})" for f in files[:5]] or ["  none"]
    return "\n".join(lines)
