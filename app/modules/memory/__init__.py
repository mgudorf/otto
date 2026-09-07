from app.modules import Agent, Manifest, Schedule

MANIFEST = Manifest(
    name="memory",
    title="Memory",
    hue="#d1a36a",
    icon='<rect x="4" y="3" width="12" height="14" rx="2"></rect><path d="M7 8h6M7 11h6M7 14h4"></path>',
    order=3,
    schedules=(Schedule(task="suggest", every="24h", resource="memory", llm=True),),
    agent=Agent(
        placeholder="Ask memory…",
        skills=("recall", "tag", "add", "suggest"),
        read_tools=("memory_search", "memory_get", "memory_tags", "memory_suggestions"),
        write_tools=("memory_add", "memory_tag", "memory_suggest"),
    ),
)
