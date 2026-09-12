# A cell merge writes `deleted` events for text that survived

- Where: `app/modules/science/routes.py` `set_cells` (one `deleted` event per id absent from the new list)
- Found: 2026-09-12, sync-architecture
- Status: open

What happens: `set_cells` treats every id that vanished as a deletion. `Shift+M` on two cells sends a list in which both old ids are gone and one new cell holds the joined source, so Activity shows two `deleted <source>` events though nothing was lost. A split keeps the id on the tail and writes none, so the log is inconsistent between the two.

Expected: the event log records a deletion only when source left the notebook.

Fix: have the page send the merge as `{id: <first id>, ...}` so one cell keeps its identity and only the consumed one is reported, or compare sources rather than ids when deciding what to log.
