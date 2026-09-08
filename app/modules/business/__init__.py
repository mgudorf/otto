from app.modules import Agent, Manifest, Schedule

MANIFEST = Manifest(
    name="business",
    title="Business",
    hue="#c98ba8",
    icon='<rect x="3" y="7" width="14" height="10" rx="2"></rect><path d="M7 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M3 11h14"></path>',
    order=6,
    schedules=(
        Schedule(task="index_documents", every="15m", resource="business"),
        Schedule(task="scout", every="24h", resource="business", llm=True),
    ),
    agent=Agent(
        placeholder="Ask business…",
        skills=("recall", "add", "scout", "summarize"),
        read_tools=("business_search", "business_get", "business_leads"),
        write_tools=("business_add", "business_lead"),
    ),
)
