# Database

1. Module which interfaces with underlying DBs to allow for manual querying/editing of data to give visibility
2. Agent is natural language interface for creating queries
3. Agent has in depth knowledge of database schema. 

## Built

| Piece | Current state |
|---|---|
| Table | `database_queries(name unique, sql)`: the queries the owner or the agent kept |
| Execution | `query.py` splits the text on the semicolons `sqlite3.complete_statement` calls statement ends and runs the statements in order; nothing parses SQL. `read` drives the `mode=ro` connection under `store.ro_lock`, so a write fails inside SQLite; `execute` drives the read-write connection under `store.raw()`, so writes and DDL land and there is no undo. Statements commit one by one, so a script that must be all-or-nothing spells out its own `BEGIN` and `COMMIT`. Both return `{columns, rows, total, truncated, changed, ddl, statements, ms}` from the last statement that returned rows, at most `max_rows` of them, blobs as `<N bytes>`; one progress handler covers the whole script and interrupts it past `max_seconds`, leaving what already committed. An error comes back as text naming the statement that broke, not a failed job. `explain` prefixes `EXPLAIN QUERY PLAN` to the first statement, which prepares it and never runs it |
| Routes | `left` (`{modules, saved}`: every user table under the module whose `schema.sql` creates it, read off a scratch connection each schema runs on, so nothing parses SQL; `app` first, then rail order, `other` last for a table no schema owns; each module with its row total and its tables with their counts, shadow tables of virtual tables and `sqlite_*` hidden; then the saved queries with their sql), `blank` (store file name, size with the WAL, tables), `table/{name}` (one table: module, rows, columns with type, notnull, default and pk, indexes, triggers, the CREATE statement; 404 for a hidden or unknown name), `action/{run\|explain\|save\|delete}` on resource `db`, shared with backup and vacuum. `run` goes to `execute` and writes a `wrote` event when rows changed or the schema moved |
| Hooks | `numbers` (store size), `context` (every table under its module with its columns and row count, the saved query names) |
| Tools | read: `db_schema` (every table with its module, columns, indexes, triggers, CREATE statement and row count), `db_query(sql, limit)` (limit clamped to `max_rows`, on the `mode=ro` connection), `db_explain`; write: `db_save_query` only, on the full server. `query.execute` has no tool: the agent drafts a statement and saves it, the owner runs it from the editor |
| Page | LEFT: `modules`, one row per module in its hue with its row total; a click opens its tables (the name without the module prefix, the full name on hover) with their counts, and a table click loads the newest `ui.page_size` rows as a select into the editor and shows the table's schema in MIDDLE (columns with type and constraints, indexes, triggers, the CREATE statement) until a statement runs; then `saved`. MIDDLE: the SQL editor (Ctrl+Enter runs), `Run` / `Explain` / `Save` (a name prompt) and `Delete` on a loaded saved query, the schema or the result grid with paging, and the timing line. `Run` sends the text straight to SQLite with no confirmation step; the line reports rows written, and a result that changed anything reloads the rail so the counts move |
| Departures | `Export` is not built; grid columns come from the query rather than the artboard's fixed five; `Save` and a `prev` link are added for saved queries and paging; the artboard lists tables flat, LEFT groups them by module and MIDDLE shows a picked table's schema before any query runs |

## Patches

### The Database page writes without a confirm, a backup or an export

- Kind: gap
- Where: Database requirement 1 (manual querying/editing of data); `app/modules/database/routes.py`, `app/modules/database/query.py`, `app/static/pages/database.js`
- Found: 2026-09-10, sync-architecture
- Status: open, owner

What happens: the editor could not write at all; every statement ran on the `mode=ro` connection, so an `UPDATE` came back as the SQLite error text. On 2026-09-12 the owner asked for any statement to run, and `action/run` moved to `query.execute` on the read-write connection. What the plan wrapped around that write is still missing: `Run` fires straight into SQLite with no confirm, no backup is taken first, and the store's only undo is whatever sits in `data/backups/` from the last manual `Back up now`. A mistyped `delete from second_brain_items` is gone. There is still no table export.

Expected: the decisions the owner recorded on 2026-09-08. Writes are SQL typed by the owner or drafted by the agent and run only by the owner; agents stay read-only until evals exist. One confirm and an automatic backup stand in front of every write: `action/run` keeps running on the read-only connection and answers `{needs_confirm: true}` when SQLite refuses a write, the page asks `This statement writes. Back up and run?`, and `action/write` on resource `db` takes `store.backup` into `data/backups/` and then runs the statement in one transaction, returning `{changes, ms, backup}`. `GET export/{table}` sends the whole picked table as CSV named `<table>-<stamp>.csv`, behind an `Export` button that is inactive until a table is picked. The agent gets no new tool: asked to change data it drafts the statement, saves it with `db_save_query` and tells the owner to run it. Events `wrote` and `exported`; no new knob or table. The recorded decision allowed one statement per run; the editor now runs a whole script, statement by statement, with the owner's own `BEGIN`/`COMMIT` as the only rollback.

Fix: the owner's call. Either the confirm and pre-write backup go back in front of `action/run`, or running unguarded is recorded here as the decision. The CSV export is untouched either way.
