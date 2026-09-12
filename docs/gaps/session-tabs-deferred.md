# One session per module; tabs not built

- Where: Summary requirement "Multiple conversations should be spawnable/selectable via tabs"; `app/api.py` sessions, `app/static/session.js`
- Found: 2026-09-07, sync-architecture
- Status: deferred by the owner

What happens: one open session per module pane; `/clear` closes it, tags it and starts a fresh one. Closed sessions keep their title, tags and turns. Chat (merged 2026-09-12) keeps many conversations on its own page through the same `start_turn` seam with busy state per session id, so the platform now supports several open sessions per module; the panes still show one.

Expected: several open sessions per module, selectable by tab.

Fix: `sessions` already allows several open rows per module; add a tab strip to the pane header, a session id on the send and events routes, and per-session busy state.
