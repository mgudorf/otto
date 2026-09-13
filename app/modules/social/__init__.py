from app.modules import Agent, Manifest, Schedule

MANIFEST = Manifest(
    name="social",
    title="Social",
    hue="#8f95d6",
    icon='<circle cx="7.5" cy="7" r="2.6"></circle><path d="M2.5 16.5c0-2.8 2.2-4.5 5-4.5s5 1.7 5 4.5"></path><circle cx="14.5" cy="8.5" r="2"></circle><path d="M13.6 12.6c2.3-.2 3.9 1.3 3.9 3.9"></path>',
    order=10,
    schedules=(Schedule(task="scout", every="24h", resource="social", llm=True),),
    agent=Agent(
        placeholder="Ask social…",
        skills=("upcoming", "add", "scout", "plan"),
        read_tools=("social_search", "social_get", "social_upcoming"),
        write_tools=("social_interest", "social_event"),
    ),
)
