"""Running a file: one cell on its kernel, a notebook top to bottom, or a script as a subprocess of science.python.
Routes and the `due` task share these; a route passes `publish` so an open page sees the run live. Schedule arithmetic lives here too.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable

import nbformat

from app.modules import UNITS
from app.modules.science import notebook, state
from app.store import iso, now, now_iso, parse

Publish = Callable[[dict], None] | None
CHUNK = 4096
SCRIPT = "script"   # the `cell` every script event carries


def _pub(publish: Publish, ev: dict) -> None:
    if publish:
        publish(ev)


async def run_cell(path: Path, cell_id: str, source: str, publish: Publish = None) -> tuple[int | None, list[dict]]:
    """Execute `source` for `cell_id` on the notebook's kernel and write the outputs to that cell by id (the owner may have moved it meanwhile)."""
    _pub(publish, {"cell": cell_id, "event": "started"})
    try:
        count, outputs = await state.kernels.execute(path, cell_id, source, lambda o: _pub(publish, {"cell": cell_id, "event": "output", "output": notebook.shape_output(o)}))
    except Exception as e:
        _pub(publish, {"cell": cell_id, "event": "error", "text": str(e)})
        raise
    nb = notebook.read(path)
    cell = next((c for c in nb.cells if c.get("id") == cell_id and c.cell_type == "code"), None)
    if cell is not None:
        cell.outputs = [nbformat.from_dict(o) for o in outputs]
        cell.execution_count = count
        notebook.write(path, nb)
    _pub(publish, {"cell": cell_id, "event": "done", "execution_count": count})
    return count, outputs


async def run_notebook(path: Path, publish: Publish = None) -> str:
    """Every code cell in order, stopping at the first error."""
    nb = notebook.read(path)
    ran = 0
    for c in list(nb.cells):
        if c.cell_type != "code":
            continue
        count, outputs = await run_cell(path, c.get("id"), notebook.join(c.source), publish)
        ran += 1
        err = next((o for o in outputs if o.get("output_type") == "error"), None)
        if err is not None:
            raise RuntimeError(f"cell [{count}] raised {err.get('ename')}: {err.get('evalue')}")
    return f"{ran} cell(s) ran"


async def run_script(store, path: Path, file_id: str, publish: Publish = None) -> str:
    """`science.python -u <file>` in the file's directory, stdout and stderr merged, streamed as it comes and kept whole in science_script_runs."""
    if file_id in state.scripts:
        raise RuntimeError("already running")
    run_id = store.execute("INSERT INTO science_script_runs(path, started_at, status) VALUES (?, ?, 'running')", (file_id, now_iso())).lastrowid
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    proc = await asyncio.create_subprocess_exec(
        state.config.python, "-u", str(path), cwd=str(path.parent),
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, creationflags=flags,
    )
    state.scripts[file_id] = proc
    _pub(publish, {"cell": SCRIPT, "event": "started"})
    chunks: list[str] = []
    try:
        while chunk := await proc.stdout.read(CHUNK):
            text = chunk.decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n")   # a Windows pipe carries CRLF
            chunks.append(text)
            _pub(publish, {"cell": SCRIPT, "event": "output", "output": {"kind": "stream", "name": "stdout", "text": text}})
        code = await proc.wait()
    finally:
        state.scripts.pop(file_id, None)
    status = "done" if code == 0 else "failed"
    store.execute(
        "UPDATE science_script_runs SET finished_at = ?, status = ?, exit_code = ?, output = ? WHERE id = ?",
        (now_iso(), status, code, "".join(chunks), run_id),
    )
    if code != 0:
        _pub(publish, {"cell": SCRIPT, "event": "error", "text": f"exit {code}"})
        raise RuntimeError(f"exit {code}")
    _pub(publish, {"cell": SCRIPT, "event": "done"})
    return f"exit 0, {sum(t.count(chr(10)) for t in chunks)} line(s)"


async def run_file(store, path: Path, file_id: str, publish: Publish = None) -> str:
    if path.suffix == ".py":
        return await run_script(store, path, file_id, publish)
    return await run_notebook(path, publish)


# ---- schedules -----------------------------------------------------------------------------
def every_seconds(every: str) -> int:
    """The manifest's grammar: `30m`, `6h`, `1d`."""
    try:
        n, unit = int(every[:-1]), every[-1]
    except (ValueError, IndexError):
        n, unit = 0, ""
    if n <= 0 or unit not in UNITS:
        raise ValueError("every must be like 30m, 6h or 1d")
    return n * UNITS[unit]


def first_run(seconds: int, at: str | None) -> str:
    """`at` HH:MM anchors the first run to the next such local time; otherwise one interval from now."""
    if not at:
        return iso(now() + timedelta(seconds=seconds))
    try:
        t = datetime.strptime(at, "%H:%M").time()
    except ValueError:
        raise ValueError("at must be HH:MM")
    local = datetime.now().astimezone()
    cand = local.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
    if cand <= local:
        cand += timedelta(days=1)
    return iso(cand.astimezone(UTC))


def next_run(planned: str, seconds: int) -> str:
    """From the planned time, not the actual one, so a daily run keeps its clock time; slots already past are skipped."""
    t = parse(planned) + timedelta(seconds=seconds)
    while t <= now():
        t += timedelta(seconds=seconds)
    return iso(t)
