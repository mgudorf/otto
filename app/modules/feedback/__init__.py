"""Feedback: the owner records a change from any page; a standalone agent classifies and files it as a row."""

from app.modules import Agent, Manifest

MANIFEST = Manifest(
    name="feedback",
    title="Feedback",
    hue="#8b8f98",
    icon="",
    order=99,
    page=False,
    agent=Agent(
        placeholder="",
        read_tools=("docs_list", "docs_read", "feedback_list"),
    ),
)
