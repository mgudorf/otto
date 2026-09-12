"""Web Search: the nightly run over the owner's topics. No page: its findings wait on Home, its topics are the Chat agent's tools."""

from app.modules import Manifest, Schedule

MANIFEST = Manifest(
    name="web_search",
    title="Search",
    hue="#d9915b",
    icon='<circle cx="9" cy="9" r="5.5"></circle><path d="M13 13l4 4"></path>',
    order=9,
    schedules=(Schedule(task="nightly", every="24h", resource="web_search", llm=True),),
    page=False,
)
