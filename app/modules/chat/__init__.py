"""Chat: the owner's general conversations with Claude, kept forever. Web search on demand, files in and out, the nightly search's topics."""

from app.modules import Agent, Manifest

MANIFEST = Manifest(
    name="chat",
    title="Chat",
    hue="#d9915b",
    icon='<path d="M4 4h12v9H9l-4 3v-3H4Z"></path>',
    order=1,   # ties with Email; the registry loads packages alphabetically and sorts stably, so Chat sits first after Home
    agent=Agent(
        placeholder="Ask anything…",
        skills=("web", "files", "topics"),
        builtins=("Write", "Edit"),
        read_tools=("search_findings", "search_topics"),
        write_tools=("search_topic_add", "search_topic_remove"),
    ),
)
