# `email_search` tells the agent three chips when four exist

- Where: `app/modules/email/tools.py` `email_search` docstring; `app/modules/email/agent.md` line 3; `app/modules/email/routes.py` `CHIPS`
- Found: 2026-09-12, sync-architecture
- Status: open

What happens: the tool's description, which is what the agent reads when choosing arguments, says the chip narrows to `All`, `Unread` or `Flagged`. The route accepts `Priority` as well and the agent's instructions tell it to use that chip. An agent that follows the tool description never asks for the priority view it is told to triage from.

Expected: the tool description names the four chips the route serves.

Fix: add `Priority` to the docstring, or build the docstring from `CHIPS` so the two cannot drift.
