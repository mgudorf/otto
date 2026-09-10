"""Files under science.root: the listing, reading and atomic writing of notebooks, and the wire shape of cells."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path

import nbformat
from fastapi import HTTPException

EXTS = (".ipynb", ".py")
SKIP = {".ipynb_checkpoints", "__pycache__"}
ANSI = re.compile(r"\x1b\[[0-9;]*m")
TYPES = ("code", "markdown", "raw")


def mtime_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds")


def scan(root: Path) -> list[dict]:
    """Every notebook and script under root, newest modification first."""
    out = []
    if not root.is_dir():
        return out
    for p in root.rglob("*"):
        if p.suffix not in EXTS or not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in SKIP or part.startswith(".") for part in rel.parts):
            continue
        st = p.stat()
        out.append({"id": rel.as_posix(), "name": p.name, "ext": p.suffix[1:], "mtime": mtime_iso(st.st_mtime), "size": st.st_size})
    out.sort(key=lambda f: f["mtime"], reverse=True)
    return out


def resolve(root: Path, file_id: str) -> Path:
    """A file id is a posix path relative to root; anything escaping root or missing is a 404."""
    p = (root / file_id).resolve()
    try:
        p.relative_to(root.resolve())
    except ValueError:
        raise HTTPException(404, "no such file")
    if not p.is_file() or p.suffix not in EXTS:
        raise HTTPException(404, "no such file")
    return p


def read(path: Path):
    """Every cell comes back with an id. A file older than nbformat 4.5 has none, so it gets positional ones that the next write keeps."""
    nb = nbformat.read(str(path), as_version=4)
    if nb.nbformat_minor < 5:
        for i, c in enumerate(nb.cells):
            c.setdefault("id", f"c{i}")
        nb.nbformat_minor = 5
    return nb


def write(path: Path, nb) -> None:
    """Write beside the file, then replace: a reader never sees a half-written notebook."""
    tmp = path.with_name(path.name + ".tmp")
    nbformat.write(nb, str(tmp))
    os.replace(tmp, path)


def new(path: Path) -> None:
    """A notebook with one empty code cell, marked for the python3 kernel like any Jupyter-made file."""
    nb = nbformat.v4.new_notebook()
    nb.cells.append(new_cell("code"))
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3 (ipykernel)", "language": "python"}
    write(path, nb)


def new_cell(kind: str, source: str = ""):
    make = {"code": nbformat.v4.new_code_cell, "markdown": nbformat.v4.new_markdown_cell, "raw": nbformat.v4.new_raw_cell}
    return make[kind](source)


def join(v) -> str:
    return "".join(v) if isinstance(v, list) else (v or "")


def shape_output(o: dict) -> dict:
    t = o.get("output_type")
    if t == "stream":
        return {"kind": "stream", "name": o.get("name", "stdout"), "text": join(o.get("text"))}
    if t == "error":
        return {"kind": "error", "ename": o.get("ename", ""), "evalue": o.get("evalue", ""), "traceback": ANSI.sub("", "\n".join(o.get("traceback", [])))}
    data = o.get("data", {})
    if "image/png" in data:
        return {"kind": "image", "png": join(data["image/png"]).replace("\n", "")}
    if "text/html" in data:
        return {"kind": "html", "html": join(data["text/html"])}
    if "text/plain" in data:
        return {"kind": "text", "text": join(data["text/plain"])}
    return {"kind": "text", "text": ", ".join(data) if data else ""}


def cells(nb, running: dict | None = None) -> list[dict]:
    """Cells for the wire. While a cell runs, its in-flight outputs replace the saved ones."""
    out = []
    for i, c in enumerate(nb.cells):
        live = running if running and running.get("cell") == c.get("id") else None
        outputs = live["outputs"] if live else (c.get("outputs") or [])
        out.append({
            "id": c.get("id"),
            "index": i,
            "type": c.cell_type,
            "source": join(c.source),
            "execution_count": c.get("execution_count"),
            "running": live is not None,
            "outputs": [shape_output(o) for o in outputs] if c.cell_type == "code" else [],
        })
    return out
