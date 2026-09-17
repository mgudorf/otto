"""Newsfeed: searches the agent writes, run on the owner's nights; every entry a run returns waits for a yes or no."""

from app.modules import Agent, Manifest, Schedule

MANIFEST = Manifest(
    name="newsfeed",
    title="Newsfeed",
    hue="#c98ba8",
    icon='<path d="M4 12a4 4 0 0 1 4 4"></path><path d="M4 8a8 8 0 0 1 8 8"></path><path d="M4 4a12 12 0 0 1 12 12"></path><circle cx="4.5" cy="15.5" r="1"></circle>',
    order=6,
    schedules=(Schedule(task="run", every="24h", resource="newsfeed", llm=True),),
    agent=Agent(
        placeholder="Ask the feed…",
        skills=("recall", "searches", "add", "tag"),
        read_tools=("newsfeed_search", "newsfeed_get", "newsfeed_searches"),
        write_tools=("newsfeed_search_add", "newsfeed_tag"),
    ),
)
