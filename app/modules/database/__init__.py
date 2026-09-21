from app.modules import Agent, Manifest

MANIFEST = Manifest(
    name="database",
    title="Database",
    hue="#B39BDB",
    icon='<rect x="3" y="4" width="14" height="12" rx="2"></rect><path d="M3 10h14"></path>',
    order=8,
    facet="database",
    agent=Agent(
        placeholder="Describe a query…",
        skills=("nl-to-sql", "explain-plan", "schema"),
        read_tools=("db_schema", "db_query", "db_explain"),
        write_tools=("db_save_query",),
    ),
)
