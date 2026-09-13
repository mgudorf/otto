from app.modules import Agent, Manifest, Schedule

MANIFEST = Manifest(
    name="email",
    title="Email",
    hue="#cf7b7b",
    icon='<rect x="3" y="5" width="14" height="10" rx="2"></rect><path d="M3 7l7 5 7-5"></path>',
    order=1,
    schedules=(
        Schedule(task="sync", every="5m", resource="gmail"),
        Schedule(task="triage", every="24h", resource="email", llm=True),
    ),
    agent=Agent(
        placeholder="Ask about the inbox…",
        skills=("triage", "summarize", "flag"),
        read_tools=("email_search", "email_get", "email_triage"),
        write_tools=("email_flag",),
    ),
)


def setup(config) -> None:
    """Hooks are handed only the store, and the consent warning needs the token path and the window."""
    from app.modules.email import routes

    routes.CONFIG = config
