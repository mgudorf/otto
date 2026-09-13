"""Files under science.root: the tree, the flat listing, creation, reading and atomic writing of notebooks, and the wire shape of cells."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path

import nbformat
from fastapi import HTTPException

EXTS = (".ipynb", ".py")
KINDS = ("py", "ipynb", "folder")
SKIP = {".ipynb_checkpoints", "__pycache__"}
ANSI = re.compile(r"\x1b\[[0-9;]*m")
TYPES = ("code", "markdown", "raw")


def mtime_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds")


def _hidden(name: str) -> bool:
    return name.startswith(".") or name in SKIP


def tree(root: Path) -> list[dict]:
    """Every directory and every notebook or script under root as nested nodes, directories first, names in order. Dot and checkpoint directories are skipped."""

    def walk(d: Path, rel: str) -> list[dict]:
        out = []
        try:
            entries = sorted(d.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except OSError:
            return out
        for p in entries:
            if _hidden(p.name):
                continue
            rid = f"{rel}/{p.name}" if rel else p.name
            if p.is_dir():
                out.append({"id": rid, "name": p.name, "kind": "dir", "children": walk(p, rid)})
            elif p.suffix in EXTS and p.is_file():
                st = p.stat()
                out.append({"id": rid, "name": p.name, "kind": p.suffix[1:], "mtime": mtime_iso(st.st_mtime), "size": st.st_size})
        return out

    return walk(root, "") if root.is_dir() else []


def scan(root: Path) -> list[dict]:
    """Every notebook and script under root, flat, newest modification first."""
    out: list[dict] = []

    def flat(nodes: list[dict]) -> None:
        for n in nodes:
            if n["kind"] == "dir":
                flat(n["children"])
            else:
                out.append({"id": n["id"], "name": n["name"], "ext": n["kind"], "mtime": n["mtime"], "size": n["size"]})

    flat(tree(root))
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


def target(root: Path, rel: str, kind: str) -> Path:
    """Where a new folder, script or notebook goes: every part of `rel` plain (no leading dot), the suffix added for a file, 409 if it exists."""
    if kind not in KINDS:
        raise HTTPException(400, f"kind is one of {', '.join(KINDS)}")
    parts = [p.strip() for p in rel.replace("\\", "/").split("/")]
    if not parts or not all(parts) or any(_hidden(p) for p in parts):
        raise HTTPException(400, "give it a plain path under the root")
    path = root / Path(*parts)
    if kind != "folder" and path.suffix != f".{kind}":
        path = path.with_name(f"{path.name}.{kind}")
    if path.exists():
        raise HTTPException(409, "that path exists")
    return path


def create(root: Path, path: Path, kind: str) -> str:
    """Make what `target` chose: a folder, an empty script or a one-cell notebook. Returns the new id."""
    if kind == "folder":
        path.mkdir(parents=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        if kind == "py":
            path.write_text("", "utf-8")
        else:
            new(path)
    return path.relative_to(root).as_posix()


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
