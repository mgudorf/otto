"""MCP tools for the Science agent. Read tools go on both servers; run and set_cell on the full server only."""

from __future__ import annotations

import nbformat
from fastapi import HTTPException

from app.modules.science import notebook, state
from app.store import Store


def register(read, full, store: Store, config) -> None:
    def cap(text: str) -> str:
        n = config.science.tool_output_chars
        return text if len(text) <= n else text[:n] + f"… [{len(text) - n} more chars]"

    def shaped(o: dict, full_text: bool) -> dict:
        s = notebook.shape_output(o)
        if s["kind"] == "image":
            return {"kind": "image", "note": f"png, {len(s['png']) * 3 // 4} bytes; open the notebook to see it"}
        for key in ("text", "html", "traceback"):
            if key in s and not full_text:
                s[key] = cap(s[key])
        return s

    def path_of(file_id: str):
        try:
            return notebook.resolve(state.config.root, file_id)
        except HTTPException:
            return None

    def science_files() -> list[dict]:
        """Every notebook and script under the science root, newest modification first, with its kernel state if one is live."""
        out = []
        for f in notebook.scan(state.config.root):
            k = state.kernels.get(state.config.root / f["id"])
            out.append({"id": f["id"], "ext": f["ext"], "modified": f["mtime"], "kernel": k.state if k else None})
        return out

    def science_notebook(id: str) -> dict:
        """A notebook's cells (index, type, source, execution_count, outputs capped) or a script's source. id is from science_files."""
        path = path_of(id)
        if path is None:
            return {"error": f"no file {id}"}
        if path.suffix == ".py":
            return {"id": id, "kind": "py", "source": cap(path.read_text("utf-8", "replace"))}
        nb = notebook.read(path)
        k = state.kernels.get(path)
        cells = []
        for i, c in enumerate(nb.cells):
            cell = {"index": i, "type": c.cell_type, "source": notebook.join(c.source), "execution_count": c.get("execution_count")}
            if c.cell_type == "code":
                cell["outputs"] = [shaped(o, False) for o in (c.get("outputs") or [])]
            cells.append(cell)
        return {"id": id, "kind": "ipynb", "kernel": k.state if k else None, "cells": cells}

    def science_cell(id: str, index: int) -> dict:
        """One cell in full: its source and outputs without the cap (images stay described, not embedded)."""
        path = path_of(id)
        if path is None or path.suffix != ".ipynb":
            return {"error": f"no notebook {id}"}
        nb = notebook.read(path)
        if not 0 <= index < len(nb.cells):
            return {"error": f"no cell {index}"}
        c = nb.cells[index]
        return {
            "id": id, "index": index, "type": c.cell_type, "source": notebook.join(c.source), "execution_count": c.get("execution_count"),
            "outputs": [shaped(o, True) for o in (c.get("outputs") or [])] if c.cell_type == "code" else [],
        }

    def science_kernels() -> list[dict]:
        """Live kernels: which notebook, idle or busy, runs so far, minutes idle."""
        return [{"id": k.path.name, "path": str(k.path), "state": k.state, "runs": k.executions, "idle_minutes": round(k.idle_minutes(), 1)} for k in state.kernels.alive()]

    async def science_run(id: str, index: int) -> dict:
        """Run one code cell on the notebook's kernel (started if needed) and return its outputs. Only when the owner asked for that cell."""
        path = path_of(id)
        if path is None or path.suffix != ".ipynb":
            return {"error": f"no notebook {id}"}
        nb = notebook.read(path)
        if not 0 <= index < len(nb.cells) or nb.cells[index].cell_type != "code":
            return {"error": f"cell {index} is not a code cell"}
        cell_id = nb.cells[index].get("id")
        count, outputs = await state.kernels.execute(path, cell_id, notebook.join(nb.cells[index].source))
        nb = notebook.read(path)
        cell = next((c for c in nb.cells if c.get("id") == cell_id and c.cell_type == "code"), None)   # by id: the owner may have moved it meanwhile
        if cell is not None:
            cell.outputs = [nbformat.from_dict(o) for o in outputs]
            cell.execution_count = count
            notebook.write(path, nb)
        store.event("science", "ran", f"{path.name} [{count}] (agent)", ref=id)
        return {"id": id, "index": index, "execution_count": count, "outputs": [shaped(o, False) for o in outputs]}

    def science_set_cell(id: str, index: int, source: str) -> dict:
        """Replace one cell's source with the text the owner asked for. Outputs stay until the cell runs again."""
        path = path_of(id)
        if path is None or path.suffix != ".ipynb":
            return {"error": f"no notebook {id}"}
        nb = notebook.read(path)
        if not 0 <= index < len(nb.cells):
            return {"error": f"no cell {index}"}
        nb.cells[index].source = source
        notebook.write(path, nb)
        store.event("science", "edited", f"{path.name} cell {index} (agent)", ref=id)
        return {"id": id, "index": index}

    for server in (read, full):
        server.tool()(science_files)
        server.tool()(science_notebook)
        server.tool()(science_cell)
        server.tool()(science_kernels)
    full.tool()(science_run)
    full.tool()(science_set_cell)
