"""Platform routes: health, restart, shell, tasks, jobs, events, settings, data, sessions."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.claude import ClaudeError
from app.store import Store, now_iso

router = APIRouter()


class Broadcast:
    """In-process fan-out of session events to open event streams."""

    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, key: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subs[key].add(q)
        return q

    def unsubscribe(self, key: str, q: asyncio.Queue) -> None:
        self._subs[key].discard(q)

    def publish(self, key: str, event: dict) -> None:
        for q in list(self._subs[key]):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass


# ---- health / admin ------------------------------------------------------------------------
@router.get("/health")
def health(request: Request) -> dict:
    st = request.app.state
    return {
        "rev": st.rev,
        "pid": os.getpid(),
        "started_at": st.started_at,
        "draining": st.runner.draining,
        "running": sorted(st.runner.running),
    }


@router.post("/admin/restart")
async def restart(request: Request) -> dict:
    st = request.app.state
    if not st.runner.draining:
        asyncio.create_task(_restart(request.app))
    return {"restarting": True}


async def _restart(app) -> None:
    st = app.state
    st.store.event("system", "restarting", f"draining up to {st.config.scheduler.drain_seconds:.0f}s")
    await st.runner.drain(st.config.scheduler.drain_seconds)
    from app.daemon import spawn_daemon

    spawn_daemon(st.config)
    if st.server is not None:
        st.server.should_exit = True


# ---- shell -----------------------------------------------------------------------------------
@router.get("/api/shell")
def shell(request: Request) -> dict:
    st = request.app.state
    settings = st.store.all_settings()
    modules = []
    for m in st.registry.ordered():
        if not m.manifest.page:
            continue
        a = m.manifest.agent
        modules.append({
            "name": m.name, "title": m.manifest.title, "hue": m.manifest.hue, "icon": m.manifest.icon,
            "order": m.manifest.order, "enabled": settings.get(f"modules.{m.name}.enabled", True) is not False,
            "agent": {"placeholder": a.placeholder, "skills": list(a.skills)} if a else None, "error": None,
        })
    for name, err in st.registry.errors.items():
        modules.append({
            "name": name, "title": name, "hue": "#5f636c", "icon": "", "order": 98, "enabled": False,
            "agent": None, "error": err.strip().splitlines()[-1][:300],
        })
    c = st.config
    return {
        "rev": st.rev,
        "modules": modules,
        "settings": settings,
        "claude": {
            "binary": c.claude.binary, "model": c.claude.model, "workspace": str(c.data.workspace),
            "agents_dir": str(c.root / "app" / "modules"), "sessions_kept_days": c.claude.sessions_kept_days,
            "background_jobs": [r["name"] for r in st.store.query("SELECT name FROM tasks WHERE llm = 1 ORDER BY name")],
        },
        "budget": st.claude.budget(),
    }


# ---- tasks / jobs / events -----------------------------------------------------------------
@router.get("/api/tasks")
def tasks(request: Request) -> list[dict]:
    return request.app.state.store.query("SELECT * FROM tasks ORDER BY module, name")


@router.post("/api/tasks/{name}")
def task_enable(request: Request, name: str, body: dict = Body(...)) -> dict:
    st = request.app.state
    try:
        st.scheduler.set_enabled(name, bool(body.get("enabled")))
    except KeyError:
        raise HTTPException(404, "no such task")
    st.store.event("system", "enabled" if body.get("enabled") else "disabled", name)
    return st.store.one("SELECT * FROM tasks WHERE name = ?", (name,))


@router.get("/api/jobs")
def jobs(request: Request, limit: int = 100) -> list[dict]:
    return request.app.state.store.query("SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (max(1, min(limit, 1000)),))


@router.get("/api/jobs/{job_id}")
def job(request: Request, job_id: int) -> dict:
    store: Store = request.app.state.store
    row = store.one("SELECT * FROM jobs WHERE id = ?", (job_id,))
    if row is None:
        raise HTTPException(404, "no such job")
    row["logs"] = store.query("SELECT ts, message FROM job_logs WHERE job_id = ? ORDER BY id", (job_id,))
    return row


@router.get("/api/events")
def events(request: Request, module: str = "", limit: int = 200, offset: int = 0) -> dict:
    store: Store = request.app.state.store
    where, params = ("WHERE module = ?", [module]) if module else ("", [])
    total = store.scalar(f"SELECT COUNT(*) FROM events {where}", tuple(params))
    rows = store.query(f"SELECT * FROM events {where} ORDER BY id DESC LIMIT ? OFFSET ?", (*params, max(1, min(limit, 1000)), max(0, offset)))
    return {"events": rows, "total": total}


# ---- settings --------------------------------------------------------------------------------
UI_KEYS = {"ui.start_page": str, "ui.refresh_seconds": int, "ui.time_format": str, "ui.page_size": int}


@router.get("/api/settings")
def settings(request: Request) -> dict:
    return request.app.state.store.all_settings()


@router.put("/api/settings")
def settings_put(request: Request, body: dict = Body(...)) -> dict:
    st = request.app.state
    store: Store = st.store
    for key, value in body.items():
        if key in UI_KEYS:
            value = UI_KEYS[key](value)
            if key == "ui.refresh_seconds" and not 5 <= value <= 3600:
                raise HTTPException(400, "refresh must be 5 to 3600 seconds")
            if key == "ui.page_size" and not 10 <= value <= 200:
                raise HTTPException(400, "rows per page must be 10 to 200")
            if key == "ui.time_format" and value not in ("24h", "12h"):
                raise HTTPException(400, "time format must be 24h or 12h")
            if key == "ui.start_page" and value not in st.registry.modules and value not in ("activity", "settings"):
                raise HTTPException(400, "unknown start page")
        elif key.startswith("modules.") and key.endswith(".enabled"):
            value = bool(value)
        else:
            raise HTTPException(400, f"unknown setting {key}")
        store.set_setting(key, value)
    return store.all_settings()


# ---- data ------------------------------------------------------------------------------------
def _backups_dir(request: Request):
    return request.app.state.config.data.db.parent / "backups"


def _db_size(request: Request) -> int:
    db = request.app.state.config.data.db
    return sum(p.stat().st_size for p in (db, db.with_name(db.name + "-wal")) if p.exists())


@router.get("/api/data")
def data(request: Request) -> dict:
    d = _backups_dir(request)
    backups = sorted(d.glob("otto-*.db")) if d.exists() else []
    last = backups[-1] if backups else None
    return {
        "db": str(request.app.state.config.data.db),
        "size_bytes": _db_size(request),
        "last_backup": datetime.fromtimestamp(last.stat().st_mtime).astimezone().isoformat(timespec="seconds") if last else None,
        "backups": len(backups),
    }


@router.post("/api/data/backup")
async def backup(request: Request) -> dict:
    st = request.app.state
    dest = _backups_dir(request) / f"otto-{datetime.now():%Y%m%d-%H%M%S}.db"

    async def run(ctx):
        st.store.backup(dest)
        ctx.event("backed up", dest.name, ref=str(dest))
        return str(dest)

    await st.runner.run_action("data.backup", "system", "db", run)
    return {"path": str(dest), "size_bytes": dest.stat().st_size}


@router.post("/api/data/vacuum")
async def vacuum(request: Request) -> dict:
    st = request.app.state

    async def run(ctx):
        st.store.vacuum()
        ctx.event("vacuumed", "database")
        return "ok"

    await st.runner.run_action("data.vacuum", "system", "db", run)
    return {"size_bytes": _db_size(request)}


# ---- sessions --------------------------------------------------------------------------------
def _module(request: Request, name: str):
    mod = request.app.state.registry.modules.get(name)
    if mod is None or mod.manifest.agent is None:
        raise HTTPException(404, "no agent for that module")
    return mod


def _session(store: Store, module: str) -> dict | None:
    return store.one("SELECT * FROM sessions WHERE module = ? AND closed_at IS NULL ORDER BY opened_at DESC LIMIT 1", (module,))


def _turns(store: Store, session_id: str) -> list[dict]:
    return store.query("SELECT id, ts, role, text, tool, status FROM session_turns WHERE session_id = ? ORDER BY id", (session_id,))


def _add_turn(store: Store, session_id: str, role: str, text: str | None = None, tool: str | None = None, status: str | None = None) -> int:
    cur = store.execute(
        "INSERT INTO session_turns(session_id, ts, role, text, tool, status) VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, now_iso(), role, text, tool, status),
    )
    return cur.lastrowid


def _context_label(st, mod) -> str:
    n = mod.numbers(st.store) if mod.numbers else None
    if n:
        v = n["value"]
        return f"{v:,} {n['label']}" if isinstance(v, int) else f"{v} {n['label']}"
    return mod.manifest.title.lower()


@router.get("/api/session/{module}")
def session(request: Request, module: str) -> dict:
    st = request.app.state
    mod = _module(request, module)
    sess = _session(st.store, module)
    a = mod.manifest.agent
    return {
        "session": sess,
        "turns": _turns(st.store, sess["id"]) if sess else [],
        "busy": module in st.session_busy,
        "context_label": _context_label(st, mod),
        "agent": {"cmd": f"claude · {module}", "placeholder": a.placeholder, "skills": list(a.skills)},
    }


@router.post("/api/session/{module}/send")
async def session_send(request: Request, module: str, body: dict = Body(...)) -> dict:
    st = request.app.state
    store: Store = st.store
    mod = _module(request, module)
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "empty message")
    if module in st.session_busy:
        raise HTTPException(409, "a turn is still running")

    if text == "/clear":
        sess = _session(store, module)
        if sess is None:
            return {"cleared": False}
        st.runner.submit(f"{module}.close", module, f"session:{module}", "session", _closer(st, mod, sess["id"]), notify=True)
        st.broadcast.publish(module, {"role": "system", "text": "session cleared", "ts": now_iso()})
        return {"cleared": True}

    sess = _session(store, module)
    if sess is None:
        sid = str(uuid.uuid4())
        store.execute("INSERT INTO sessions(id, module, opened_at) VALUES (?, ?, ?)", (sid, module, now_iso()))
        sess = _session(store, module)
    sid, started = sess["id"], bool(sess["cli_started"])
    _add_turn(store, sid, "user", text=text)
    st.broadcast.publish(module, {"role": "user", "text": text, "ts": now_iso()})
    st.session_busy.add(module)

    async def turn(ctx):
        tool_rows: dict[str, int] = {}

        async def on_event(ev: dict) -> None:
            role = ev["role"]
            if role == "model":
                _add_turn(store, sid, "model", text=ev["text"])
            elif role == "tool":
                tool_rows[ev.get("id") or ""] = _add_turn(store, sid, "tool", tool=ev["tool"], status=ev["status"])
            elif role == "tool_result":
                rid = tool_rows.get(ev.get("id") or "")
                if rid:
                    store.execute("UPDATE session_turns SET status = ? WHERE id = ?", (ev["status"], rid))
            elif role == "init":
                ctx.log("tools: " + ", ".join(ev.get("tools", [])))
            st.broadcast.publish(module, {**ev, "ts": now_iso()})

        try:
            await st.claude.session_turn(mod, sid, not started, text, on_event)
            store.execute("UPDATE sessions SET cli_started = 1 WHERE id = ?", (sid,))
            return "ok"
        except ClaudeError as e:
            _add_turn(store, sid, "system", text=f"error: {e}")
            st.broadcast.publish(module, {"role": "error", "text": str(e), "ts": now_iso()})
            if not started:  # the CLI never took this id; retire it so the next turn starts clean
                store.execute("UPDATE sessions SET closed_at = ?, title = ? WHERE id = ?", (now_iso(), "(failed to start)", sid))
            raise
        finally:
            st.session_busy.discard(module)
            st.broadcast.publish(module, {"role": "idle", "ts": now_iso()})

    job = st.runner.submit(f"{module}.turn", module, f"session:{module}", "session", turn)
    return {"queued": job.id, "session": sid}


def _closer(st, mod, sid: str):
    store: Store = st.store

    async def close(ctx):
        turns = _turns(store, sid)
        user_lines = [t["text"] for t in turns if t["role"] == "user" and t["text"]]
        title, tags = (user_lines[0][:80] if user_lines else "(empty)"), []
        if user_lines:
            transcript = "\n".join(f"{t['role']}: {t['text']}" for t in turns if t["role"] in ("user", "model") and t["text"])[:6000]
            prompt = (
                'Below is a conversation. Reply with only JSON of the form {"title": <at most 8 words>, '
                '"tags": [<3 to 6 lowercase topic identifiers>]}.\n\n' + transcript
            )
            try:
                raw = await st.claude.oneshot(ctx, mod, prompt)
                data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
                title = str(data.get("title") or title)[:80]
                tags = [str(t)[:40] for t in data.get("tags", [])][:8]
            except Exception as e:
                ctx.log(f"tagging failed, keeping fallback title: {e!r}")
        with ctx.commit() as conn:
            conn.execute("UPDATE sessions SET closed_at = ?, title = ?, tags = ? WHERE id = ?", (now_iso(), title, json.dumps(tags), sid))
        ctx.event("closed", f"session: {title}" + (f" [{', '.join(tags)}]" if tags else ""), ref=sid)
        return title

    return close


@router.get("/api/session/{module}/events")
async def session_events(request: Request, module: str) -> StreamingResponse:
    st = request.app.state
    _module(request, module)
    q = st.broadcast.subscribe(module)

    async def gen():
        try:
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield f"data: {json.dumps(ev)}\n\n"
        finally:
            st.broadcast.unsubscribe(module, q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
