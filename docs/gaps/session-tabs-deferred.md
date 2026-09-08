# One session per module; tabs not built

- Where: Summary requirement "Multiple conversations should be spawnable/selectable via tabs"; `app/api.py` sessions, `app/static/session.js`
- Found: 2026-09-07, sync-architecture
- Status: deferred by the owner

What happens: one open session per module; `/clear` closes it, tags it and starts a fresh one. Closed sessions keep their title, tags and turns.

Expected: several open sessions per module, selectable by tab.

Fix: `sessions` already allows several open rows per module; add a tab strip to the pane header, a session id on the send and events routes, and per-session busy state.
