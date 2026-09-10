"""Science: list files, show a notebook, run cells on its kernel. Runs are jobs; their outputs stream over server-sent events."""

from __future__ import annotations

from datetime import datetime

import nbformat
from fastapi import APIRouter, Body, HTTPException, Request

from app.api import event_stream
from app.modules.science import notebook, state
from app.store import Store, iso, now_iso, parse

router = APIRouter(prefix="/api/science")

HUE = "#6fb3b8"
KEY = "science"          # broadcast key for the events stream
RESOURCE = "science"     # jobs that touch the root, not one kernel


def _root():
    return state.config.root


def _row(f: dict) -> dict:
    live = state.kernels.get(_root() / f["id"]) is not None
    return {"id": f["id"], "module": "science", "text": f["name"], "stamp": f["mtime"], "leading": {"dot": HUE if live else None}, "mono": True}


def _day(ts: str) -> str:
    return parse(ts).astimezone().strftime("%d %b")


@router.get("/left")
def left(request: Request) -> dict:
    files = notebook.scan(_root())
    groups: list[dict] = []
    for f in files:
        label = _day(f["mtime"])
        if not groups or groups[-1]["label"] != label:
            groups.append({"label": label, "count": 0, "rows": []})
        groups[-1]["rows"].append(_row(f))
        groups[-1]["count"] += 1
    return {"groups": groups, "showing": f"{len(files)} files"}


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
    if verb not in KERNEL_ACTIONS and verb not in EDIT_ACTIONS:
        raise HTTPException(404, f"unknown action {verb}")
    file_id = str(body.get("id", ""))
    path = notebook.resolve(_root(), file_id)
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
    index = int(body.get("index", -1))
    path = notebook.resolve(_root(), file_id)
    if path.suffix != ".ipynb":
        raise HTTPException(400, "only notebooks run")
    nb = notebook.read(path)
    if not 0 <= index < len(nb.cells) or nb.cells[index].cell_type != "code":
        raise HTTPException(400, "not a code cell")
    cell_id = nb.cells[index].get("id")
    source = notebook.join(nb.cells[index].source)

    def publish(ev: dict) -> None:
        st.broadcast.publish(KEY, {"path": file_id, "cell": cell_id, "index": index, "ts": now_iso(), **ev})

    async def job(ctx):
        publish({"event": "started"})
        try:
            count, outputs = await state.kernels.execute(path, cell_id, source, lambda o: publish({"event": "output", "output": notebook.shape_output(o)}))
        except Exception as e:
            publish({"event": "error", "text": str(e)})
            raise
        nb = notebook.read(path)
        cell = next((c for c in nb.cells if c.get("id") == cell_id and c.cell_type == "code"), None)   # by id: the owner may have moved it meanwhile
        if cell is not None:
            cell.outputs = [nbformat.from_dict(o) for o in outputs]
            cell.execution_count = count
            notebook.write(path, nb)
        publish({"event": "done", "execution_count": count})
        ctx.event("ran", f"{path.name} [{count}]", ref=file_id)
        return f"{path.name} cell {index}: {len(outputs)} output(s)"

    row = st.runner.submit("science.run", "science", f"kernel:{file_id}", "action", job)
    return {"job": row.id}


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
    """Replace the cell list. A cell naming an existing id of the same type keeps its outputs; anything else is new."""
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
    for c in have.values():
        st.store.event("science", "deleted", f"{path.name} cell: {notebook.join(c.source)[:80]}", ref=file_id)
    return {"id": file_id, "cells": len(cells)}


def _insert_cell(st, path, file_id, body) -> dict:
    nb = notebook.read(path)
    after = int(body.get("after", len(nb.cells) - 1))
    kind = body.get("type", "code")
    if kind not in notebook.TYPES:
        raise HTTPException(400, f"no cell type {kind}")
    index = max(0, min(after + 1, len(nb.cells)))
    nb.cells.insert(index, notebook.new_cell(kind))
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
    name = str(body.get("name", "")).strip()
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(400, "give the notebook a plain file name")
    if not name.endswith(".ipynb"):
        name += ".ipynb"
    path = _root() / name
    if path.exists():
        raise HTTPException(409, "that file exists")

    async def run(ctx):
        notebook.new(path)
        ctx.event("created", path.name, ref=name)
        return {"id": name}

    return await st.runner.run_action("science.new", "science", RESOURCE, run)


# ---- shell hooks ---------------------------------------------------------------------------
def item(store: Store, file_id: str) -> dict:
    path = notebook.resolve(_root(), file_id)
    st = path.stat()
    base = {"id": file_id, "module": "science", "text": path.name, "kind": path.suffix[1:], "created_at": notebook.mtime_iso(st.st_mtime), "actions": []}
    if path.suffix == ".py":
        return {**base, "kernel": None, "cells": [], "source": path.read_text("utf-8", "replace")}
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
    lines.append("Most recently modified:")
    lines += [f"  {f['id']} ({f['mtime']})" for f in files[:5]] or ["  none"]
    return "\n".join(lines)
