"""Feedback: add a note from any page, file it through the agent, list the record."""

from __future__ import annotations

import json

from fastapi import APIRouter, Body, HTTPException, Request

from app.config import ROOT
from app.modules.feedback.queue import open_counts
from app.store import Store, now_iso

router = APIRouter(prefix="/api/feedback")

KINDS = ("bug", "defect", "gap", "roadmap")
RESOURCE = "feedback"
ITEM_TEXT_CHARS = 300
RECENT = 5


def _get(store: Store, fid: int) -> dict:
    row = store.one("SELECT * FROM feedback WHERE id = ?", (fid,))
    if row is None:
        raise HTTPException(404, "no such feedback")
    return row


def _prompt(row: dict) -> str:
    where = f'from the "{row["page"]}" page'
    if row["item_module"]:
        where += f", while item {row['item_module']} {row['item_id']} was selected"
    lines = [f"Feedback #{row['id']}, recorded {row['created_at']} {where}."]
    if row["item_text"]:
        lines += ["", "Selected item text:", "```", row["item_text"], "```"]
    lines += [
        "", "The owner's words:", "```", row["text"], "```", "",
        "File this note. Reply with only a JSON object: "
        '{"kind": "bug" | "defect" | "gap" | "roadmap", "title": "<at most 10 words>", '
        '"summary": "<one sentence, at most 140 characters>", "tags": [<2 to 5 lowercase identifiers>], '
        '"ref": "<existing docs/ path this belongs in, or null>", "draft": "<markdown body for that file>"}',
    ]
    return "\n".join(lines)


def _json_object(raw: str) -> dict:
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < 0:
        raise ValueError(f"no JSON object in reply: {raw[:200]!r}")
    data = json.loads(raw[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("reply is not an object")
    return data


def _filer(st, fid: int):
    store: Store = st.store
    mod = st.registry.modules["feedback"]

    async def file(ctx):
        row = _get(store, fid)
        try:
            raw = await st.claude.oneshot(ctx, mod, _prompt(row), tools=mod.manifest.agent.read_tools, max_turns=st.config.feedback.max_turns)
            data = _json_object(raw)
            kind = data.get("kind")
            if kind not in KINDS:
                raise ValueError(f"kind must be one of {', '.join(KINDS)}, got {kind!r}")
            title, summary, draft = (str(data.get(k) or "").strip() for k in ("title", "summary", "draft"))
            if not (title and summary and draft):
                raise ValueError("title, summary and draft are required")
            tags = [str(t)[:40] for t in data.get("tags") or []][:8]
            ref = str(data["ref"]).strip() if data.get("ref") else None
        except Exception as e:
            with ctx.commit() as conn:
                conn.execute("UPDATE feedback SET status = 'failed', error = ?, job_id = ? WHERE id = ?", (f"{e!r}"[:500], ctx.job.id, fid))
            raise
        with ctx.commit() as conn:
            conn.execute(
                "UPDATE feedback SET status = 'filed', kind = ?, title = ?, summary = ?, tags = ?, ref = ?, draft = ?, filed_at = ?, job_id = ?, error = NULL WHERE id = ?",
                (kind, title[:120], summary[:200], json.dumps(tags), ref, draft, now_iso(), ctx.job.id, fid),
            )
        store.event(row["page"], "filed", f"{kind}: {title}"[:200], ctx.job.id, str(fid))
        return f"{kind}: {title}"

    return file


def _submit(st, fid: int) -> None:
    st.runner.submit("feedback.file", "feedback", RESOURCE, "action", _filer(st, fid))


@router.post("/action/{verb}")
async def action(request: Request, verb: str, body: dict = Body(default={})) -> dict:
    st = request.app.state
    store: Store = st.store
    if verb == "add":
        page = (body.get("page") or "").strip()
        text = (body.get("text") or "").strip()
        if not page or not text:
            raise HTTPException(400, "page and text are required")
        item = body.get("item") or {}
        with store.tx() as conn:
            cur = conn.execute(
                "INSERT INTO feedback(created_at, page, item_module, item_id, item_text, text) VALUES (?, ?, ?, ?, ?, ?)",
                (now_iso(), page, item.get("module"), None if item.get("id") is None else str(item["id"]), (item.get("text") or "")[:ITEM_TEXT_CHARS] or None, text),
            )
        fid = cur.lastrowid
        store.event(page, "feedback", text[:200], None, str(fid))
        _submit(st, fid)
        return {"id": fid}
    if verb == "retry":
        row = _get(store, int(body.get("id", 0)))
        if row["status"] != "failed":
            raise HTTPException(409, f"feedback is {row['status']}, not failed")
        store.execute("UPDATE feedback SET status = 'queued', error = NULL WHERE id = ?", (row["id"],))
        _submit(st, row["id"])
        return {"id": row["id"]}
    raise HTTPException(404, f"unknown action {verb}")


@router.get("/recent")
def recent(request: Request, page: str) -> dict:
    """One page's own notes. The panel is per page, so a note filed on Home is never another module's business."""
    store: Store = request.app.state.store
    rows = store.query(
        "SELECT id, created_at, page, status, kind, summary, error FROM feedback WHERE page = ? ORDER BY id DESC LIMIT ?",
        (page, RECENT),
    )
    return {"page": page, "rows": rows}


@router.get("/list")
def list_route(request: Request, status: str = "", limit: int = 100) -> list[dict]:
    store: Store = request.app.state.store
    where, params = ("WHERE status = ?", [status]) if status else ("", [])
    rows = store.query(f"SELECT * FROM feedback {where} ORDER BY id DESC LIMIT ?", (*params, max(1, min(limit, 1000))))
    for r in rows:
        r["tags"] = json.loads(r["tags"]) if r["tags"] else []
    return rows


# ---- shell hooks ---------------------------------------------------------------------------
def context(store: Store, registry) -> str:
    built = ", ".join(m.name for m in registry.ordered()) or "none"
    patches = ", ".join(f"{doc} {n}" for doc, n in open_counts(ROOT).items()) or "none"
    return "\n".join([f"Built modules: {built}", f"Open patches by doc: {patches}"])
