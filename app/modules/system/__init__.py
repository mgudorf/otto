"""Platform tasks. No page, no agent; appears only in Activity."""

from app.modules import Manifest, Schedule

MANIFEST = Manifest(
    name="system",
    title="System",
    hue="#8b8f98",
    icon="",
    order=99,
    page=False,
    schedules=(
        Schedule(task="heartbeat", every="60s"),
        Schedule(task="prune_sessions", every="24h", resource="sessions"),
    ),
)
