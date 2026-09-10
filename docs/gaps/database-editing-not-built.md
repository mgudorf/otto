# The Database page cannot edit data

- Where: Database requirement 1 (manual querying/editing of data); `app/modules/database/routes.py`, `app/modules/database/query.py`
- Found: 2026-09-10, sync-architecture
- Status: open, roadmap

What happens: every statement runs on the `mode=ro` connection, so an `UPDATE` typed in the editor comes back as the SQLite error text. There is no confirm, no write path and no table export; a wrong row can only be corrected from the module that owns it.

Expected: a write statement the owner confirms runs after a backup and reports the rows changed; a picked table exports as CSV.

Fix: `docs/roadmap/database/PLAN.md`, decided on 2026-09-08 and not started (the `database` worktree holds no unmerged commits).
