"""Housekeeping and the clock for the owner's scheduled files. `reap` never touches a file; `due` runs what the owner scheduled on the page."""

from __future__ import annotations

from app.modules.science import notebook, runs, state
from app.runner import Skipped, reason
from app.store import now_iso


async def reap(ctx) -> str:
    limit = ctx.config.science.idle_minutes
    stale = [k for k in state.kernels.alive() if k.running is None and k.idle_minutes() >= limit]
    for k in stale:
        idle = k.idle_minutes()
        await state.kernels.shutdown(k.path)
        ctx.event("shut down", f"{k.path.name} idle {idle:.0f} min", ref=k.path.name)
    if not stale:
        return Skipped("no idle kernels")
    return f"shut down {len(stale)} idle kernel(s)"


async def due(ctx) -> str:
    """Every schedule whose time has come: the next slot is booked before the run, so a slow run never repeats."""
    rows = ctx.store.query("SELECT * FROM science_schedules WHERE next_run <= ? ORDER BY next_run", (now_iso(),))
    if not rows:
        return Skipped("nothing due")
    for r in rows:
        with ctx.commit() as conn:
            conn.execute("UPDATE science_schedules SET next_run = ? WHERE path = ?", (runs.next_run(r["next_run"], r["every_seconds"]), r["path"]))
        try:
            result, status = await runs.run_file(ctx.store, notebook.resolve(ctx.config.science.root, r["path"]), r["path"]), "done"
        except Exception as e:
            result, status = reason(e), "failed"
        with ctx.commit() as conn:
            conn.execute("UPDATE science_schedules SET last_run = ?, last_status = ?, last_result = ? WHERE path = ?", (now_iso(), status, result[:500], r["path"]))
        ctx.event("ran" if status == "done" else "failed", f"{r['path']}: {result}"[:200], ref=r["path"])
    return f"ran {len(rows)} scheduled file(s)"
