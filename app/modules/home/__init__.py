from app.modules import Agent, Manifest

MANIFEST = Manifest(
    name="home",
    title="Home",
    hue="#ECEEF2",
    icon='<path d="M10 3 17 10 10 17 3 10Z"></path>',
    order=0,
    agent=Agent(
        placeholder="Ask about today…",
        skills=("today", "where-to-look"),
    ),
)
