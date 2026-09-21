# Database

1. Module which interfaces with underlying DBs to allow for manual querying/editing of data to give visibility
2. Agent is natural language interface for creating queries
3. Agent has in depth knowledge of database schema.

## Built

| Piece | Current state |
|---|---|
| Facet | `database`, hue `#B39BDB`. Every row carries it as its one `fixed` tag |
| Table | `database_queries(name unique, sql)`: the queries the owner or the agent kept |
| Rows | Two types. A saved query is type `query`: `id` `query:<id>`, `title` its name, `when` the moment it was last kept, `tags` `query` plus the owner's from `app_tags`, `snip` `saved`, and `sql` its text. A table is type `table`: `id` and `title` its name, `when` null so it sorts behind everything in Recent, `tags` `table`, `taggable: false` because a table is the store's own shape rather than something the owner wrote, `right` its row count, and `cols` of name, type and what the column promises. The saved queries come first, then every table |
| Verbs | a saved query offers `load` Load and `delete` Delete; a table offers `query` Query and `export` Export. `query` never leaves the browser — it opens the drawer with `query <table>: ` for the agent. `delete` is destructive, so the browser asks first and drops the row |
| Execution | `query.py` splits the text on the semicolons `sqlite3.complete_statement` calls statement ends and runs the statements in order; nothing parses SQL. `read` drives the `mode=ro` connection under `store.ro_lock`, so a write fails inside SQLite, and the read transaction sqlite3 opened for the attempt is rolled back so the connection is not pinned to a stale snapshot. `write` drives the read-write connection inside one `BEGIN`, so a script lands whole or rolls back, and reports `{changes, ms}` without fetching rows. `execute` is the bare read-write drive both sit on, returning `{columns, rows, total, truncated, changed, ddl, statements, ms}` from the last statement that returned rows, at most `max_rows` of them, blobs as `<N bytes>`; one progress handler covers the whole script and interrupts it past `max_seconds`. An error comes back as text naming the statement that broke, not a failed job. `explain` prefixes `EXPLAIN QUERY PLAN` to the first statement, which prepares it and never runs it. `csv_text` writes one table out as CSV, its column names first |
| Routes | `left` (`{modules, saved}`: every user table under the module whose `schema.sql` creates it, read off a scratch connection each schema runs on, so nothing parses SQL; `app` first, then the modules in manifest order, `other` last for a table no schema owns; each module with its row total and its tables with their counts, shadow tables of virtual tables and `sqlite_*` hidden; then the saved queries with their sql), `blank` (store file name, size with the WAL, tables), `table/{name}` (one table: module, rows, columns with type, notnull, default and pk, indexes, triggers, the CREATE statement; 404 for a hidden or unknown name), `export/{name}` (the whole table as CSV named `<table>-<stamp>.csv`, an `exported` event, 404 for a hidden or unknown name), `item/{id}`, `action/{run\|write\|explain\|save\|delete}` on resource `db`, shared with backup and vacuum. `run` goes to `read` and answers `{needs_confirm: true}` when SQLite refuses the statement; `write` backs the store up to `data/backups/otto-<stamp>-pre-write.db`, runs the script in one transaction and returns `{changes, ms, backup}` with a `wrote` event; `delete` takes the id bare or as the `query:<id>` the rows carry. `run`, `write` and `explain` have no caller in the browser: SQL reaches the store through the agent's tools |
| Hooks | `numbers` (store size), `rows`, `item`, `context` (every table under its module with its columns and row count, the saved query names). No `today` and no `queue`: nothing here waits on the owner |
| Tools | read: `db_schema` (every table with its module, columns, indexes, triggers, CREATE statement and row count), `db_query(sql, limit)` (limit clamped to `max_rows`, on the `mode=ro` connection), `db_explain`; write: `db_save_query` only, on the full server. Neither `query.write` nor `query.execute` has a tool |

## Patches

### Export and Load go nowhere

- Kind: bug
- Where: `app/modules/database/routes.py` (`_table_row`, `_query_row`, `ACTIONS`), `app/static/core.js` (`HERE`, `doVerb`)
- Found: 09-21-2026, the one-page change
- Status: open

What happens: a table offers `export` and a saved query offers `load`, and neither is an action the module serves nor a verb the browser answers itself. Both post to `POST /api/verb`, reach `action/{verb}` and come back as the toast `unknown action export`. A table can still be exported through `GET /api/database/export/{name}`, which nothing calls; loading a query had a meaning only while there was an editor to load it into.

Expected: a verb on a row does what its label says.

Fix: `export` becomes a download the browser opens against the existing export route, the way a link verb should work. `load` has no destination until there is a console to load into, so it goes until then.
