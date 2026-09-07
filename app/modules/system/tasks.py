from app.runner import Skipped
from app.store import days_ago_iso


async def heartbeat(ctx) -> str:
    """Proof that the clock runs; Activity shows its last run and next run."""
    return "alive"


async def prune_sessions(ctx) -> str:
    """Drop closed sessions (and their turns) older than claude.sessions_kept_days."""
    cutoff = days_ago_iso(ctx.config.claude.sessions_kept_days)
    with ctx.commit() as conn:
        n = conn.execute("DELETE FROM sessions WHERE closed_at IS NOT NULL AND closed_at < ?", (cutoff,)).rowcount
    return Skipped("nothing to prune") if n == 0 else f"pruned {n}"
