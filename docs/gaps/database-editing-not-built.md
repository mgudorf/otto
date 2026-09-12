# The Database page writes without a confirm, a backup or an export

- Where: Database requirement 1 (manual querying/editing of data); `app/modules/database/routes.py`, `app/modules/database/query.py`, `app/static/pages/database.js`
- Found: 2026-09-10, sync-architecture
- Status: open, owner

What happens: the editor could not write at all; every statement ran on the `mode=ro` connection, so an `UPDATE` came back as the SQLite error text. On 2026-09-12 the owner asked for any statement to run, and `action/run` moved to `query.execute` on the read-write connection. What the plan wrapped around that write is still missing: `Run` fires straight into SQLite with no confirm, no backup is taken first, and the store's only undo is whatever sits in `data/backups/` from the last manual `Back up now`. A mistyped `delete from memories` is gone. There is still no table export.

Expected: `docs/roadmap/database/PLAN.md` decisions 1-3 put one confirm and an automatic backup in front of every write, and decisions 6-7 export a picked table as CSV. Decision 5 allowed one statement per run; the editor now runs a whole script, statement by statement, with the owner's own `BEGIN`/`COMMIT` as the only rollback.

Fix: the owner's call. Either the confirm and pre-write backup go back in front of `action/run`, or the plan is replaced by one written from the current `ARCHITECTURE.md` that records running unguarded as the decision. The CSV export is untouched either way and still belongs to that plan.
