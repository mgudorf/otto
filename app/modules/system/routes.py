"""System: the daemon's scheduled tasks as routines — what runs, how often, when it last ran and what it said.

Every row is a row of app_tasks; the module stores nothing of its own. `run` hands the task to the runner as the
clock would, so the run writes its own result back; `pause` and `resume` throw the scheduler's switch.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request

from app.store import Store, now, parse

router = APIRouter(prefix="/api/system")

FACET = "routine"                 # the module's immutable tag, the only one a routine carries
ROW_LIMIT = 200
FAILED = "failed"                 # the job status the runner writes onto a task that raised
SIZES = (("d", 86400), ("h", 3600), ("m", 60), ("s", 1))


def _every(seconds: int) -> str:
    unit, size = next((u, s) for u, s in SIZES if seconds >= s and seconds % s == 0)
    return f"every {seconds // size} {unit}"


def _cadence(r: dict) -> str:
    """What the clock promises. An LLM task is due only inside the nightly window, whatever its interval says."""
    return "nightly" if r["llm"] else _every(r["interval_seconds"])


def _when(ts: str | None) -> str | None:
    """The last run on the owner's own clock, so the feed orders it against every other module's rows."""
    return parse(ts).astimezone().strftime("%Y-%m-%dT%H:%M") if ts else None


def _stamp(ts: str | None) -> str:
    return parse(ts).astimezone().strftime("%m-%d-%Y %H:%M") if ts else "never"


def _row(r: dict) -> dict:
    late, paused, cadence = r["last_status"] == FAILED, not r["enabled"], _cadence(r)
    kv = [["Every", cadence], ["Last run", _stamp(r["last_run"])], ["Last result", r["last_result"] or "nothing said"]]
    if r["resource"]:
        kv.append(["Resource", r["resource"]])
    return {
        "id": r["name"], "module": "system", "title": r["name"], "when": _when(r["last_run"]),
        "fixed": [FACET], "tags": [], "type": "routine",
        "snip": cadence, "late": late, "paused": paused,
        "right": "failed" if late else "paused" if paused else cadence,
        "kv": kv,
        "verbs": [["run", "Run now"], ["resume", "Resume"] if paused else ["pause", "Pause"]],
    }


def _task(store: Store, name) -> dict:
    row = store.one("SELECT * FROM app_tasks WHERE name = ?", (str(name or ""),))
    if row is None:
        raise HTTPException(404, "no such task")
    return row


@router.post("/action/{verb}")
async def action(request: Request, verb: str, body: dict = Body(default={})) -> dict:
    st = request.app.state
    act = ACTIONS.get(verb)
    if act is None:
        raise HTTPException(404, f"unknown action {verb}")
    return act(st, _task(st.store, body.get("id")))


def _run(st, t: dict) -> dict:
    """Run it now, as the clock would: the same kind of job, so the runner stamps the task with what it returns.
    Nothing is awaited here — a nightly task can run for minutes, and Activity carries the result."""
    module = st.registry.modules.get(t["module"])
    fn = module.tasks.get(t["name"].split(".", 1)[1]) if module else None
    if fn is None:
        raise HTTPException(409, "module not loaded")
    st.runner.submit(t["name"], t["module"], t["resource"], "scheduled", fn, notify=bool(t["llm"]))
    return {"id": t["name"], "queued": True}


def _switch(enabled: bool):
    def act(st, t: dict) -> dict:
        st.scheduler.set_enabled(t["name"], enabled)
        st.store.event("system", "enabled" if enabled else "disabled", t["name"])
        return {"id": t["name"], "paused": not enabled}

    return act


ACTIONS = {"run": _run, "pause": _switch(False), "resume": _switch(True)}


# ---- shell hooks ---------------------------------------------------------------------------
def rows(store: Store, limit: int = ROW_LIMIT) -> list[dict]:
    """Every scheduled task, the most recently run first; one that has never run sits behind them."""
    return [_row(r) for r in store.query(
        "SELECT * FROM app_tasks ORDER BY last_run IS NULL, last_run DESC, name LIMIT ?", (max(1, min(limit, 1000)),)
    )]


def queue(store: Store) -> list[dict]:
    """Only what broke: a task whose last run failed. `waits` is the days it has stood broken, freshest first."""
    failed = store.query("SELECT * FROM app_tasks WHERE last_status = ? ORDER BY last_run DESC", (FAILED,))
    return [{**_row(r), "waits": (now() - parse(r["last_run"])).days} for r in failed]
