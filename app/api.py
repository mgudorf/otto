"""Platform routes: health, restart, shell, tags, items, tasks, jobs, events, settings, data, sessions."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import uuid
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.claude import ClaudeError
from app.modules import Agent, Manifest, Module
from app.store import Store, add_tags, all_tags, now_iso, remove_tag, tag_key, tags_for

router = APIRouter()

REPLAYED = "resumed from Otto's record"


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
    """Every module: `facet` is the immutable tag its rows carry and the lobe it owns on the brain, None for a backend one."""
    st = request.app.state
    settings = st.store.all_settings()
    modules = []
    for m in st.registry.ordered():
        a = m.manifest.agent
        modules.append({
            "name": m.name, "title": m.manifest.title, "hue": m.manifest.hue, "icon": m.manifest.icon,
            "order": m.manifest.order, "facet": m.manifest.facet, "enabled": settings.get(f"modules.{m.name}.enabled", True) is not False,
            "scheduled": settings.get(f"modules.{m.name}.scheduled", True) is not False, "tasks": len(m.manifest.schedules),
            "model": settings.get(f"modules.{m.name}.model") or "default", "effort": settings.get(f"modules.{m.name}.effort") or "default",
            "agent": {"placeholder": a.placeholder, "skills": list(a.skills)} if a else None, "error": None,
        })
    for name, err in st.registry.errors.items():
        modules.append({
            "name": name, "title": name, "hue": "#5f636c", "icon": "", "order": 98, "facet": None, "enabled": False,
            "scheduled": False, "tasks": 0, "model": "default", "effort": "default", "agent": None, "error": err.strip().splitlines()[-1][:300],
        })
    c = st.config
    return {
        "rev": st.rev,
        "modules": modules,
        "settings": settings,
        "claude": {
            "binary": c.claude.binary, "model": c.claude.model, "models": list(c.claude.models), "efforts": list(c.claude.efforts), "workspace": str(c.data.workspace),
            "agents_dir": str(c.root / "app" / "modules"), "sessions_kept_days": c.claude.sessions_kept_days,
            "background_jobs": [r["name"] for r in st.store.query("SELECT name FROM app_tasks WHERE llm = 1 ORDER BY name")],
        },
        "budget": st.claude.budget(),
    }


# ---- tags and items ---------------------------------------------------------------------------
# One tag set across every module, so picking a tag narrows the whole app rather than one page. A module joins by
# defining rows(store, limit); one that does not is simply absent here.
ROW_LIMIT = 200


def _listing(request: Request) -> list:
    """Every enabled module that can list its rows, in facet order."""
    store: Store = request.app.state.store
    return [m for m in request.app.state.registry.ordered() if m.rows and store.setting(f"modules.{m.name}.enabled") is not False]


@router.get("/api/tags")
def tags(request: Request) -> list[dict]:
    return all_tags(request.app.state.store)


@router.get("/api/items")
def items(request: Request, tags: str = "", limit: int = ROW_LIMIT) -> dict:
    """Rows from every module carrying all the named tags, newest first; with no tags, every module's rows."""
    st = request.app.state
    want = {t for t in (tag_key(t) for t in tags.split(",")) if t}
    cap = max(1, min(limit, 1000))
    out = []
    for m in _listing(request):
        for row in m.rows(st.store, cap):
            carried = {tag_key(t) for t in [*(row.get("fixed") or []), *(row.get("tags") or [])]}
            if want <= carried:
                out.append(row)
    out.sort(key=lambda r: r.get("when") or "", reverse=True)
    return {"items": out}


def _tagged(request: Request, body: dict) -> tuple[str, str]:
    module, item_id = str(body.get("module") or ""), str(body.get("id") or "")
    if module not in request.app.state.registry.modules:
        raise HTTPException(404, "no such module")
    if not item_id:
        raise HTTPException(400, "id required")
    return module, item_id


@router.post("/api/tags/add")
def tags_add(request: Request, body: dict = Body(...)) -> dict:
    module, item_id = _tagged(request, body)
    wanted = body.get("tags") or []
    if not isinstance(wanted, list):
        raise HTTPException(400, "tags must be a list")
    store: Store = request.app.state.store
    try:
        add_tags(store, module, item_id, wanted)
    except sqlite3.IntegrityError:
        raise HTTPException(404, "no such item")
    return {"module": module, "id": item_id, "tags": tags_for(store, module, [item_id])[item_id]}


@router.post("/api/tags/remove")
def tags_remove(request: Request, body: dict = Body(...)) -> dict:
    module, item_id = _tagged(request, body)
    store: Store = request.app.state.store
    remove_tag(store, module, item_id, str(body.get("tag") or ""))
    return {"module": module, "id": item_id, "tags": tags_for(store, module, [item_id])[item_id]}


# ---- verbs ------------------------------------------------------------------------------------
# One front door so the browser has a single call. The modules keep their own action routes; this finds the one the
# named module offers and runs it, and reports what the module itself said about it.
REMOVES = {"trash", "dismiss", "forget", "delete", "archive", "later", "end"}


def _action(request: Request, module: str):
    mod = request.app.state.registry.modules.get(module)
    if mod is None or mod.router is None:
        raise HTTPException(404, "no such module")
    for route in mod.router.routes:
        if route.path == f"/api/{module}/action/{{verb}}":
            return route.endpoint
    raise HTTPException(404, "module takes no verbs")


@router.post("/api/verb")
async def verb(request: Request, body: dict = Body(...)) -> dict:
    """Run one verb on one row. `said` is the sentence the module wrote in Activity, which is what the drawer records."""
    store: Store = request.app.state.store
    module, name = str(body.get("module") or ""), str(body.get("verb") or "")
    endpoint = _action(request, module)
    mark = store.scalar("SELECT COALESCE(MAX(id), 0) FROM app_events")
    await endpoint(request, name, body)
    said = store.one("SELECT verb, text FROM app_events WHERE id > ? AND module = ? ORDER BY id DESC LIMIT 1", (mark, module))
    return {"ok": True, "said": f"{said['verb']} {said['text']}" if said else name, "removes": name in REMOVES}


# ---- tasks / jobs / events -----------------------------------------------------------------
@router.get("/api/tasks")
def tasks(request: Request) -> list[dict]:
    return request.app.state.store.query("SELECT * FROM app_tasks ORDER BY module, name")


@router.post("/api/tasks/{name}")
def task_enable(request: Request, name: str, body: dict = Body(...)) -> dict:
    st = request.app.state
    try:
        st.scheduler.set_enabled(name, bool(body.get("enabled")))
    except KeyError:
        raise HTTPException(404, "no such task")
    st.store.event("system", "enabled" if body.get("enabled") else "disabled", name)
    return st.store.one("SELECT * FROM app_tasks WHERE name = ?", (name,))


@router.get("/api/jobs")
def jobs(request: Request, limit: int = 100) -> list[dict]:
    return request.app.state.store.query("SELECT * FROM app_jobs ORDER BY id DESC LIMIT ?", (max(1, min(limit, 1000)),))


@router.get("/api/jobs/{job_id}")
def job(request: Request, job_id: int) -> dict:
    store: Store = request.app.state.store
    row = store.one("SELECT * FROM app_jobs WHERE id = ?", (job_id,))
    if row is None:
        raise HTTPException(404, "no such job")
    row["logs"] = store.query("SELECT ts, message FROM app_job_logs WHERE job_id = ? ORDER BY id", (job_id,))
    return row


@router.get("/api/events")
def events(request: Request, module: str = "", limit: int = 200, offset: int = 0) -> dict:
    store: Store = request.app.state.store
    where, params = ("WHERE module = ?", [module]) if module else ("", [])
    total = store.scalar(f"SELECT COUNT(*) FROM app_events {where}", tuple(params))
    rows = store.query(f"SELECT * FROM app_events {where} ORDER BY id DESC LIMIT ? OFFSET ?", (*params, max(1, min(limit, 1000)), max(0, offset)))
    return {"events": rows, "total": total}


# ---- settings --------------------------------------------------------------------------------
UI_KEYS = {"ui.refresh_seconds": int, "ui.time_format": str, "ui.page_size": int}


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
        elif key.startswith("modules.") and key.rsplit(".", 1)[-1] in ("enabled", "scheduled"):
            value = bool(value)   # .enabled = its rows reach the feed; .scheduled = its tasks run
        elif key.startswith("modules.") and key.rsplit(".", 1)[-1] in ("model", "effort"):
            choices = st.config.claude.models if key.endswith(".model") else st.config.claude.efforts
            if value not in ("default", *choices):   # .model and .effort go on every CLI run the module makes
                raise HTTPException(400, f"{key.rsplit('.', 1)[-1]} must be default or one of {', '.join(choices)}")
        else:
            raise HTTPException(400, f"unknown setting {key}")
        store.set_setting(key, value)
    return store.all_settings()


# ---- data ------------------------------------------------------------------------------------
def _backups_dir(request: Request):
    return request.app.state.config.data.db.parent / "backups"


def _exports_dir(request: Request):
    return request.app.state.config.data.db.parent / "exports"


def _latest(paths) -> str | None:
    last = paths[-1] if paths else None
    return datetime.fromtimestamp(last.stat().st_mtime).astimezone().isoformat(timespec="seconds") if last else None


def _db_size(request: Request) -> int:
    db = request.app.state.config.data.db
    return sum(p.stat().st_size for p in (db, db.with_name(db.name + "-wal")) if p.exists())


@router.get("/api/data")
def data(request: Request) -> dict:
    d, e = _backups_dir(request), _exports_dir(request)
    backups = sorted(d.glob("otto-*.db")) if d.exists() else []
    exports = sorted(e.glob("otto-*.json")) if e.exists() else []
    return {
        "db": str(request.app.state.config.data.db),
        "size_bytes": _db_size(request),
        "last_backup": _latest(backups),
        "backups": len(backups),
        "last_export": _latest(exports),
        "exports": len(exports),
    }


@router.post("/api/data/export")
async def export(request: Request) -> dict:
    """Every table as JSON rows in one file under data/exports/, so the record can leave SQLite."""
    st = request.app.state
    dest = _exports_dir(request) / f"otto-{datetime.now():%Y%m%d-%H%M%S}.json"

    async def run(ctx):
        store: Store = st.store
        names = [r["name"] for r in store.query("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        dump = {name: store.query(f'SELECT * FROM "{name}"') for name in names}
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(dump, ensure_ascii=False, default=str), "utf-8")
        ctx.event("exported", dest.name, ref=str(dest))
        return str(dest)

    await st.runner.run_action("data.export", "system", "db", run)
    return {"path": str(dest), "size_bytes": dest.stat().st_size}


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
# A session is one CLI conversation, streaming on key `<module>:<id>`. The drawer keeps any number open under the
# name `otto`, one tab each; Chat keeps its own. start_turn and tag_session are the two paths every session goes
# through; a module's routes call them with its own broadcast key. Busy state is per session id.
OTTO = "otto"


def _agents(st) -> list:
    """Every enabled module that brings an agent; together they are Otto."""
    return [m for m in st.registry.ordered() if m.manifest.agent and st.store.setting(f"modules.{m.name}.enabled") is not False]


def _union(agents: list, field: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(v for a in agents for v in getattr(a, field)))


def _otto(st) -> Module:
    """The one agent: every enabled module's tools, skills and prompt behind a single session module."""
    mods = _agents(st)
    a = [m.manifest.agent for m in mods]
    agent = Agent(placeholder="", skills=_union(a, "skills"), read_tools=_union(a, "read_tools"),
                  write_tools=_union(a, "write_tools"), builtins=_union(a, "builtins"))
    home = st.registry.modules.get("home")
    return Module(
        manifest=Manifest(name=OTTO, title="Otto", hue="", icon="", order=0, agent=agent),
        path=st.config.root / "app" / "modules", tasks={}, router=None, schema=None, numbers=None, today=None,
        queue=None, item=None, context=getattr(home, "context", None), register_tools=None,
        prompt="\n\n".join(m.prompt for m in mods if m.prompt),
    )


def _module(request: Request, name: str):
    st = request.app.state
    if name == OTTO:
        return _otto(st)
    mod = st.registry.modules.get(name)
    if mod is None or mod.manifest.agent is None:
        raise HTTPException(404, "no agent for that module")
    return mod


def _open(store: Store, module: str) -> list[dict]:
    return store.query("SELECT * FROM app_sessions WHERE module = ? AND closed_at IS NULL ORDER BY opened_at", (module,))


def _session(store: Store, module: str, sid: str) -> dict:
    row = store.one("SELECT * FROM app_sessions WHERE module = ? AND id = ? AND closed_at IS NULL", (module, sid))
    if row is None:
        raise HTTPException(404, "no open session with that id")
    return row


def _label(store: Store, row: dict) -> str:
    """The tab's name: the tagger's title once it has run, until then the owner's first line."""
    if row["title"]:
        return row["title"]
    first = store.scalar("SELECT text FROM app_session_turns WHERE session_id = ? AND role = 'user' ORDER BY id LIMIT 1", (row["id"],))
    return (first or "new").splitlines()[0][:80]


def _key(module: str, sid: str) -> str:
    return f"{module}:{sid}"


def turns(store: Store, session_id: str) -> list[dict]:
    return store.query("SELECT id, ts, role, text, tool, status FROM app_session_turns WHERE session_id = ? ORDER BY id", (session_id,))


def add_turn(store: Store, session_id: str, role: str, text: str | None = None, tool: str | None = None, status: str | None = None) -> int:
    cur = store.execute(
        "INSERT INTO app_session_turns(session_id, ts, role, text, tool, status) VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, now_iso(), role, text, tool, status),
    )
    return cur.lastrowid


def _context_label(st, mod) -> str:
    """What the prompt carries: for Otto the modules it can see, for one module its own counter."""
    if mod.name == OTTO:
        return ", ".join(m.manifest.title for m in _agents(st))
    n = mod.numbers(st.store) if mod.numbers else None
    if n:
        v = n["value"]
        return f"{v:,} {n['label']}" if isinstance(v, int) else f"{v} {n['label']}"
    return mod.manifest.title.lower()


@router.get("/api/session/{module}")
def session(request: Request, module: str) -> dict:
    """The pane's tabs: every open session of the module, oldest first."""
    st = request.app.state
    mod = _module(request, module)
    a = mod.manifest.agent
    return {
        "sessions": [{"id": r["id"], "label": _label(st.store, r), "opened_at": r["opened_at"], "busy": r["id"] in st.session_busy} for r in _open(st.store, module)],
        "context_label": _context_label(st, mod),
        "agent": {"cmd": f"claude · {module}", "placeholder": a.placeholder, "skills": list(a.skills)},
    }


@router.get("/api/session/{module}/{sid}")
def session_one(request: Request, module: str, sid: str) -> dict:
    st = request.app.state
    _module(request, module)
    sess = _session(st.store, module, sid)
    return {"session": sess, "turns": turns(st.store, sid), "busy": sid in st.session_busy}


@router.post("/api/session/{module}/{sid}/reopen")
def session_reopen(request: Request, module: str, sid: str) -> dict:
    """The inverse of `/clear`: the tab opens again under the title and tags it was closed with."""
    st = request.app.state
    _module(request, module)
    store: Store = st.store
    row = store.one("SELECT * FROM app_sessions WHERE module = ? AND id = ?", (module, sid))
    if row is None:
        raise HTTPException(404, "no session with that id")
    if row["closed_at"]:
        store.execute("UPDATE app_sessions SET closed_at = NULL WHERE id = ?", (sid,))
        store.event(module, "reopened", f"session: {_label(store, row)}", ref=sid)
    return {"session": _session(store, module, sid), "turns": turns(store, sid), "busy": sid in st.session_busy}


@router.post("/api/session/{module}/{sid}/title")
def session_title(request: Request, module: str, sid: str, body: dict = Body(...)) -> dict:
    """The owner's own name for a tab, which the tagger never overwrites."""
    st = request.app.state
    _module(request, module)
    _session(st.store, module, sid)
    title = str(body.get("title") or "").strip()[:80]
    if not title:
        raise HTTPException(400, "title required")
    st.store.execute("UPDATE app_sessions SET title = ? WHERE id = ?", (title, sid))
    return {"module": module, "id": sid, "title": title}


@router.post("/api/session/{module}/send")
async def session_send(request: Request, module: str, body: dict = Body(...)) -> dict:
    """`id` names the tab; without one the turn opens a new session. `/clear` tags and closes the tab it names."""
    st = request.app.state
    store: Store = st.store
    mod = _module(request, module)
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "empty message")
    sid = body.get("id")
    sess = _session(store, module, str(sid)) if sid else None
    if sess is not None and sess["id"] in st.session_busy:
        raise HTTPException(409, "a turn is still running")

    if text == "/clear":
        if sess is None:
            return {"cleared": False}
        tag_session(st, mod, sess["id"], _key(module, sess["id"]), close=True)
        st.broadcast.publish(_key(module, sess["id"]), {"role": "system", "text": "session cleared", "ts": now_iso()})
        return {"cleared": True}

    if sess is None:
        sess = new_session(store, module)
    job = start_turn(st, mod, sess["id"], bool(sess["cli_started"]), text, text, _key(module, sess["id"]))
    return {"queued": job.id, "session": sess["id"]}


def new_session(store: Store, module: str) -> dict:
    sid = str(uuid.uuid4())
    store.execute("INSERT INTO app_sessions(id, module, opened_at) VALUES (?, ?, ?)", (sid, module, now_iso()))
    return _session(store, module, sid)


def pane_turn(st, mod, text: str, prompt: str):
    """A module route's turn of the pane (Education's answer): on the module's newest open tab, or a new one when none is
    open, `text` shown as the owner's turn and `prompt` sent to the CLI. Returns the job and the session row."""
    rows = _open(st.store, mod.name)
    sess = rows[-1] if rows else new_session(st.store, mod.name)
    return start_turn(st, mod, sess["id"], bool(sess["cli_started"]), text, prompt, _key(mod.name, sess["id"])), sess


def start_turn(st, mod, sid: str, started: bool, text: str, prompt: str, key: str, replay: str | None = None, on_done=None):
    """Record the owner's turn and queue the CLI turn on `session:<sid>`; its events stream on `key`.

    `text` is what is stored, `prompt` what the CLI gets. `replay`, on a resumed turn whose transcript the CLI has
    lost, restarts the session under the same id with that preamble in front of the prompt. `on_done` runs after a
    turn that succeeded, inside the job.
    """
    store: Store = st.store
    add_turn(store, sid, "user", text=text)
    st.broadcast.publish(key, {"role": "user", "text": text, "ts": now_iso()})
    st.session_busy[sid] += 1

    async def turn(ctx):
        tool_rows: dict[str, int] = {}

        async def on_event(ev: dict) -> None:
            role = ev["role"]
            if role == "model":
                add_turn(store, sid, "model", text=ev["text"])
            elif role == "tool":
                tool_rows[ev.get("id") or ""] = add_turn(store, sid, "tool", tool=ev["tool"], status=ev["status"])
            elif role == "tool_result":
                rid = tool_rows.get(ev.get("id") or "")
                if rid:
                    store.execute("UPDATE app_session_turns SET status = ? WHERE id = ?", (ev["status"], rid))
            elif role == "init":
                ctx.log("tools: " + ", ".join(ev.get("tools", [])))
            st.broadcast.publish(key, {**ev, "ts": now_iso()})

        try:
            try:
                await st.claude.session_turn(mod, sid, not started, prompt, on_event)
            except ClaudeError as e:
                if not (started and replay is not None and e.lost_transcript):
                    raise
                ctx.log("the CLI has no transcript for this session; replaying Otto's record")
                add_turn(store, sid, "system", text=REPLAYED)
                st.broadcast.publish(key, {"role": "system", "text": REPLAYED, "ts": now_iso()})
                await st.claude.session_turn(mod, sid, True, replay + prompt, on_event)
            store.execute("UPDATE app_sessions SET cli_started = 1 WHERE id = ?", (sid,))
            if on_done is not None:
                on_done()
            return "ok"
        except ClaudeError as e:
            add_turn(store, sid, "system", text=f"error: {e}")
            st.broadcast.publish(key, {"role": "error", "text": str(e), "ts": now_iso()})
            if not started:  # the CLI never took this id; retire it so the next turn starts clean
                store.execute("UPDATE app_sessions SET closed_at = ?, title = ? WHERE id = ?", (now_iso(), "(failed to start)", sid))
            raise
        finally:
            st.session_busy[sid] -= 1
            if st.session_busy[sid] <= 0:      # the last queued turn of this session ended; a second one keeps the pane busy
                del st.session_busy[sid]
                st.broadcast.publish(key, {"role": "idle", "ts": now_iso()})

    return st.runner.submit(f"{mod.name}.turn", mod.name, f"session:{sid}", "session", turn)


def tag_session(st, mod, sid: str, key: str, close: bool):
    """Queue the tagger on `session:<sid>`: a oneshot names a title and tags, unless the owner named it. `close` also ends the session."""
    store: Store = st.store

    async def tag(ctx):
        rows = turns(store, sid)
        user_lines = [t["text"] for t in rows if t["role"] == "user" and t["text"]]
        title, tags = (user_lines[0][:80] if user_lines else "(empty)"), []
        if user_lines:
            transcript = "\n".join(f"{t['role']}: {t['text']}" for t in rows if t["role"] in ("user", "model") and t["text"])[:6000]
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
        title = store.scalar("SELECT title FROM app_sessions WHERE id = ?", (sid,)) or title   # a rename outranks the tagger
        with ctx.commit() as conn:
            if close:
                conn.execute("UPDATE app_sessions SET closed_at = ?, title = ?, tags = ? WHERE id = ?", (now_iso(), title, json.dumps(tags), sid))
            else:
                conn.execute("UPDATE app_sessions SET title = ?, tags = ? WHERE id = ?", (title, json.dumps(tags), sid))
        ctx.event("closed" if close else "tagged", f"session: {title}" + (f" [{', '.join(tags)}]" if tags else ""), ref=sid)
        st.broadcast.publish(key, {"role": "tagged", "title": title, "tags": tags, "ts": now_iso()})
        return title

    return st.runner.submit(f"{mod.name}.{'close' if close else 'tag'}", mod.name, f"session:{sid}", "session", tag, notify=True)


@router.get("/api/session/{module}/{sid}/events")
async def session_events(request: Request, module: str, sid: str) -> StreamingResponse:
    _module(request, module)
    _session(request.app.state.store, module, sid)
    return event_stream(request, _key(module, sid))


def event_stream(request: Request, key: str) -> StreamingResponse:
    """Server-sent events for one broadcast key, until the client disconnects."""
    st = request.app.state
    q = st.broadcast.subscribe(key)

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
            st.broadcast.unsubscribe(key, q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
