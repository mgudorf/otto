"""Read tools for the Feedback agent: the docs folder and the feedback record. No write tools exist."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.config import ROOT
from app.store import Store

DOCS = (ROOT / "docs").resolve()


def _docs_path(path: str):
    p = (ROOT / path).resolve()
    if not p.is_relative_to(DOCS) or p.suffix != ".md":
        return None
    return p


def register(read, full, store: Store) -> None:
    def docs_list() -> list[dict]:
        """Every markdown file under docs/: findings (bugs, defects, gaps), roadmap plans, ARCHITECTURE.md."""
        out = []
        for p in sorted(DOCS.rglob("*.md")):
            st = p.stat()
            out.append({
                "path": p.relative_to(ROOT).as_posix(),
                "bytes": st.st_size,
                "modified": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec="seconds"),
            })
        return out

    def docs_read(path: str) -> dict:
        """The text of one docs/ markdown file, by the path docs_list gave."""
        p = _docs_path(path)
        if p is None:
            return {"error": "only markdown files under docs/ can be read"}
        if not p.exists():
            return {"error": f"no such file {path}"}
        return {"path": p.relative_to(ROOT).as_posix(), "text": p.read_text("utf-8")}

    def feedback_list(status: str | None = None, limit: int = 50) -> list[dict]:
        """Feedback notes already recorded, newest first. status narrows to queued, filed or failed."""
        where, params = ("WHERE status = ?", [status]) if status else ("", [])
        rows = store.query(
            f"SELECT id, created_at, page, item_module, item_id, text, status, kind, title, summary, tags, ref FROM feedback {where} ORDER BY id DESC LIMIT ?",
            (*params, max(1, min(limit, 500))),
        )
        for r in rows:
            r["tags"] = json.loads(r["tags"]) if r["tags"] else []
        return rows

    for server in (read, full):
        server.tool()(docs_list)
        server.tool()(docs_read)
        server.tool()(feedback_list)
