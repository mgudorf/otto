"""Housekeeping: shut down kernels nobody has used for science.idle_minutes. Never touches a file in root."""

from __future__ import annotations

from app.modules.science import state
from app.runner import Skipped


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
