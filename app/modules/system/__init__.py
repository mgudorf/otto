"""Platform tasks. Every scheduled task is a routine in the feed; no agent of its own."""

from app.modules import Manifest, Schedule

MANIFEST = Manifest(
    name="system",
    title="System",
    hue="#A6ACB8",
    icon='<circle cx="10" cy="10" r="7"></circle><path d="M10 6v4l3 2"></path>',
    order=99,
    facet="routine",
    schedules=(
        Schedule(task="heartbeat", every="60s"),
        Schedule(task="prune_sessions", every="24h", resource="sessions"),
    ),
)
