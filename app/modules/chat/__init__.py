"""Chat: the owner's general conversations with Claude, kept forever. Web search on demand, files in and out."""

from app.modules import Agent, Manifest

MANIFEST = Manifest(
    name="chat",
    title="Chat",
    hue="#E0A06E",
    icon='<path d="M4 4h12v9H9l-4 3v-3H4Z"></path>',
    order=1,   # ties with Email; the registry loads packages alphabetically and sorts stably, so Chat's group comes first
    facet="chats",
    agent=Agent(
        placeholder="Ask anything…",
        skills=("web", "files"),
        builtins=("Write", "Edit"),
    ),
)
