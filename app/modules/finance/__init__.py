from app.modules import Agent, Manifest

MANIFEST = Manifest(
    name="finance",
    title="Finance",
    hue="#7fb894",
    icon='<rect x="2" y="5" width="16" height="10" rx="1.5"></rect><circle cx="10" cy="10" r="2.5"></circle><path d="M5 8.5v3M15 8.5v3"></path>',
    order=5,
    schedules=(),
    agent=Agent(
        placeholder="Ask about money…",
        skills=("totals", "monthly", "history"),
        read_tools=("finance_list", "finance_get", "finance_totals"),
        write_tools=(),
    ),
)
