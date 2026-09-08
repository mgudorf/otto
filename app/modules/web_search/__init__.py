from app.modules import Agent, Manifest, Schedule

MANIFEST = Manifest(
    name="web_search",
    title="Search",
    hue="#d9915b",
    icon='<circle cx="9" cy="9" r="5.5"></circle><path d="M13 13l4 4"></path>',
    order=9,
    schedules=(Schedule(task="nightly", every="24h", resource="web_search", llm=True),),
    agent=Agent(
        placeholder="Ask about findings…",
        skills=("findings", "topics"),
        read_tools=("search_findings", "search_topics"),
    ),
)
