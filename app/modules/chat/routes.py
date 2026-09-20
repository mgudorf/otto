"""Chat: every conversation the owner has with Claude, kept until the owner deletes it.

A conversation is a `sessions` row with module `chat` and a folder under the workspace for its files. Turns go through the
platform's `start_turn`; the first completed turn queues the tagger for a title. Every write is a user action through the runner.
"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Body, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app.api import event_stream, start_turn, tag_session, turns
from app.store import Store, iso, now_iso, parse, tag_key, tags_for

router = APIRouter(prefix="/api/chat")

MODULE = "chat"
NEW_TITLE = "(new)"
DELETE = {"verb": "delete", "label": "Delete", "confirm": "Delete this conversation?", "removes": True}
LAST_TS = "COALESCE((SELECT MAX(ts) FROM app_session_turns t WHERE t.session_id = s.id), s.opened_at) AS last_ts"


def _key(sid: str) -> str:
    return f"chat:{sid}"


def _when(ts: str) -> str:
    """A ROW's `when`: the owner's wall clock, so the page groups by their day and shows their time."""
    return parse(ts).astimezone().strftime("%Y-%m-%dT%H:%M")


def _day_label(when: str) -> str:
    return f"{when[5:7]}-{when[8:10]}-{when[:4]}"


def _folder(config, sid: str) -> Path:
    return config.data.workspace / MODULE / sid


def _get(store: Store, sid: str) -> dict:
    row = store.one("SELECT * FROM app_sessions WHERE id = ? AND module = ?", (sid, MODULE))
    if row is None:
        raise HTTPException(404, "no such conversation")
    return row


def _create(store: Store) -> dict:
    sid = str(uuid.uuid4())
    store.execute("INSERT INTO app_sessions(id, module, opened_at) VALUES (?, ?, ?)", (sid, MODULE, now_iso()))
    return _get(store, sid)


def _title(store: Store, row: dict) -> str:
    """The tagger's title once it has run; until then the owner's first line."""
    if row["title"]:
        return row["title"]
    first = store.scalar("SELECT text FROM app_session_turns WHERE session_id = ? AND role = 'user' ORDER BY id LIMIT 1", (row["id"],))
    return (first or NEW_TITLE).splitlines()[0][:80]


def _tags(store: Store, rows: list[dict]) -> dict:
    """Each conversation's tags: the ones the tagger gave the session, then any the owner added on top."""
    owner = tags_for(store, MODULE, [r["id"] for r in rows])
    out = {}
    for r in rows:
        tags: list[str] = []
        for t in [*json.loads(r["tags"] or "[]"), *owner[r["id"]]]:
            t = tag_key(t)
            if t and t not in tags:
                tags.append(t)
        out[r["id"]] = tags
    return out


def _rows(store: Store, rows: list[dict]) -> list[dict]:
    """The ROW every list speaks: the title it shows, the day it last moved, its tags. Needs `last_ts` on each row."""
    tags = _tags(store, rows)
    return [
        {"id": r["id"], "module": MODULE, "title": _title(store, r), "when": _when(r["last_ts"]), "tags": tags[r["id"]], "fixed": []}
        for r in rows
    ]


def _files(folder: Path) -> list[dict]:
    if not folder.is_dir():
        return []
    out = []
    for p in folder.iterdir():
        if p.is_file():
            s = p.stat()
            out.append({"name": p.name, "bytes": s.st_size, "modified": iso(datetime.fromtimestamp(s.st_mtime, UTC))})
    return sorted(out, key=lambda f: f["modified"], reverse=True)


def _search(query: str) -> tuple[list[str], list[str]]:
    """One LIKE per word over the title and every turn's text, all words required."""
    where, params = [], []
    for term in query.split():
        where.append("(COALESCE(s.title, '') LIKE ? OR EXISTS (SELECT 1 FROM app_session_turns u WHERE u.session_id = s.id AND u.text LIKE ?))")
        params += [f"%{term}%", f"%{term}%"]
    return where, params


def _replay(store: Store, sid: str, chars: int) -> str:
    """Otto's record of the conversation, cut to its tail, for a CLI that has lost the transcript."""
    lines = [f"{t['role']}: {t['text']}" for t in turns(store, sid) if t["role"] in ("user", "model") and t["text"]]
    tail = "\n".join(lines)[-chars:]
    return f"Earlier in this conversation, from Otto's record (the CLI's own transcript is gone):\n{tail}\n\nThe owner continues:\n\n"


def _unique(path: Path) -> Path:
    n = 2
    out = path
    while out.exists():
        out = path.with_name(f"{path.stem} ({n}){path.suffix}")
        n += 1
    return out


# ---- routes --------------------------------------------------------------------------------
@router.get("/left")
def left(request: Request, query: str = "", page: int = 0) -> dict:
    store: Store = request.app.state.store
    size = int(store.setting("ui.page_size"))
    limit = size * (page + 1)
    where, params = _search(query)
    sql_where = "WHERE s.module = ?" + "".join(f" AND {w}" for w in where)
    params = [MODULE, *params]
    total = store.scalar(f"SELECT COUNT(*) FROM app_sessions s {sql_where}", tuple(params))
    found = store.query(
        f"""SELECT s.id, s.title, s.tags, s.opened_at, {LAST_TS},
                   COALESCE((SELECT MAX(id) FROM app_session_turns t WHERE t.session_id = s.id), 0) AS last_turn
              FROM app_sessions s {sql_where} ORDER BY last_ts DESC, last_turn DESC, s.rowid DESC LIMIT ?""",
        (*params, limit),
    )
    groups: list[dict] = []
    for r in _rows(store, found):
        label = _day_label(r["when"])
        if not groups or groups[-1]["label"] != label:
            groups.append({"label": label, "count": 0, "rows": []})
        groups[-1]["rows"].append(r)
        groups[-1]["count"] += 1
    # Every conversation offers the same one verb, so the list says it once: a button on a row asks what the pane's asks.
    return {"groups": groups, "more": total > limit, "actions": [DELETE]}


@router.get("/item/{sid}")
def item_route(request: Request, sid: str) -> dict:
    st = request.app.state
    row = _get(st.store, sid)
    last = st.store.scalar("SELECT MAX(ts) FROM app_session_turns WHERE session_id = ?", (sid,)) or row["opened_at"]
    [out] = _rows(st.store, [{**row, "last_ts": last}])
    return {
        **out, "busy": sid in st.session_busy, "turns": turns(st.store, sid),
        "files": _files(_folder(st.config, sid)), "actions": [DELETE],
    }


@router.post("/new")
def new(request: Request) -> dict:
    """An empty conversation, so files can be attached before the first message."""
    st = request.app.state
    row = _create(st.store)
    _folder(st.config, row["id"]).mkdir(parents=True, exist_ok=True)
    return {"id": row["id"]}


@router.post("/send")
async def send(request: Request, body: dict = Body(...)) -> dict:
    st = request.app.state
    store: Store = st.store
    mod = st.registry.get(MODULE)
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "empty message")
    row = _get(store, str(body["id"])) if body.get("id") else _create(store)
    sid = row["id"]
    if sid in st.session_busy:
        raise HTTPException(409, "a turn is still running")
    folder = _folder(st.config, sid)
    folder.mkdir(parents=True, exist_ok=True)
    attached = []
    for name in body.get("files") or []:
        p = folder / Path(str(name)).name
        if not p.is_file():
            raise HTTPException(400, f"no attachment named {name}")
        attached.append(p)
    trailer = f"(Conversation folder: {folder}. Save any file you create there."
    if attached:
        trailer += " Attached, read them with the Read tool: " + "; ".join(str(p) for p in attached)
    prompt = f"{text}\n\n{trailer})"
    started = bool(row["cli_started"])
    replay = _replay(store, sid, st.config.chat.replay_chars) if started else None
    on_done = (lambda: tag_session(st, mod, sid, _key(sid), close=False)) if row["title"] is None else None
    job = start_turn(st, mod, sid, started, text, prompt, _key(sid), replay=replay, on_done=on_done)
    return {"id": sid, "queued": job.id}


@router.post("/action/{verb}")
async def action(request: Request, verb: str, body: dict = Body(default={})) -> dict:
    run = ACTIONS.get(verb)
    if run is None:
        raise HTTPException(404, f"unknown action {verb}")
    return await run(request, body)


async def _delete(request: Request, body: dict) -> dict:
    """The conversation, its turns and its folder; the only removal Chat has."""
    st = request.app.state
    row = _get(st.store, str(body.get("id", "")))
    sid = row["id"]
    if sid in st.session_busy:
        raise HTTPException(409, "a turn is still running")
    title = _title(st.store, row)

    async def run(ctx):
        with ctx.commit() as conn:
            conn.execute("DELETE FROM app_sessions WHERE id = ?", (sid,))   # turns go with it (ON DELETE CASCADE)
        shutil.rmtree(_folder(st.config, sid), ignore_errors=True)
        ctx.event("deleted", title[:120], ref=sid)
        return {"id": sid}

    return await st.runner.run_action("chat.delete", MODULE, f"session:{sid}", run)


ACTIONS = {"delete": _delete}


@router.post("/upload/{sid}")
async def upload(request: Request, sid: str, file: UploadFile = File(...)) -> dict:
    st = request.app.state
    _get(st.store, sid)
    name = file.filename or ""
    if not name or name in (".", "..") or Path(name).name != name:
        raise HTTPException(400, "give the file a plain name")
    data = await file.read()
    if len(data) > st.config.chat.upload_max_mb * 1024 * 1024:
        raise HTTPException(413, f"larger than {st.config.chat.upload_max_mb} MB")
    folder = _folder(st.config, sid)

    async def run(ctx):
        folder.mkdir(parents=True, exist_ok=True)
        dest = _unique(folder / name)
        dest.write_bytes(data)
        ctx.event("attached", dest.name, ref=sid)
        return {"name": dest.name, "bytes": len(data)}

    return await st.runner.run_action("chat.upload", MODULE, f"session:{sid}", run)


@router.get("/files/{sid}")
def files(request: Request, sid: str) -> list[dict]:
    st = request.app.state
    _get(st.store, sid)
    return _files(_folder(st.config, sid))


@router.get("/file/{sid}/{name}")
def file(request: Request, sid: str, name: str):
    st = request.app.state
    _get(st.store, sid)
    p = _folder(st.config, sid) / name
    if Path(name).name != name or not p.is_file():
        raise HTTPException(404, "no such file")
    return FileResponse(p)


@router.get("/events/{sid}")
async def events(request: Request, sid: str):
    _get(request.app.state.store, sid)
    return event_stream(request, _key(sid))


# ---- shell hooks ---------------------------------------------------------------------------
def rows(store: Store, limit: int = 200) -> list[dict]:
    """Every conversation as a ROW, the one that moved last first."""
    found = store.query(
        f"SELECT s.id, s.title, s.tags, s.opened_at, {LAST_TS} FROM app_sessions s WHERE s.module = ?"
        " ORDER BY last_ts DESC, s.rowid DESC LIMIT ?",
        (MODULE, limit),
    )
    return _rows(store, found)


def numbers(store: Store) -> dict:
    return {"value": store.scalar("SELECT COUNT(*) FROM app_sessions WHERE module = ?", (MODULE,)), "label": "conversations"}


def context(store: Store, registry) -> str:
    n = store.scalar("SELECT COUNT(*) FROM app_sessions WHERE module = ?", (MODULE,))
    recent = store.query("SELECT id, title FROM app_sessions WHERE module = ? ORDER BY opened_at DESC LIMIT 5", (MODULE,))
    lines = [f"Conversations: {n}", "Most recent:"]
    lines += [f"  {_title(store, r)}" for r in recent] or ["  none"]
    lines.append("Each conversation has its own folder under the workspace; the owner's messages name it.")
    return "\n".join(lines)
