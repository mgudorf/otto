# Database

1. Module which interfaces with underlying DBs to allow for manual querying/editing of data to give visibility
2. Agent is natural language interface for creating queries
3. Agent has in depth knowledge of database schema.

## Built

| Piece | Current state |
|---|---|
| Facet | `database`, hue `#B39BDB`. Every row carries it as its one `fixed` tag |
| Table | `database_queries(name unique, sql)`: the queries the owner kept, from the editor or by telling the agent to |
| Rows | Two types. A saved query is type `query`: `id` `query:<id>`, `title` its name, `when` the moment it was last kept, `tags` `query` plus the owner's from `app_tags`, `snip` `saved`, and `sql` its text. A table is type `table`: `id` and `title` its name, `when` null so it sorts behind everything in Recent, `tags` `table`, `taggable: false` because a table is the store's own shape rather than something the owner wrote, `right` its row count, and `cols` of name, type and what the column promises. The saved queries come first, then every table |
| Page | The summary under an open row is the schema: a table's columns, each with its type and what it promises, or a saved query's SQL, drawn from the feed row itself. The page is the query editor, `app/static/sql.js`: a textarea seeded with `SELECT * FROM "<table>"` for a table or the saved SQL for a query, then Run, Explain and Save, then the result. Run posts `action/run`; a `needs_confirm` answer asks in a popover and then posts `action/write`, after which the feed reloads. A result is a grid of the columns and rows under a line of the row count, `truncated` when the cap cut it, and the time; a write answers with the rows changed and the backup's name; a plan is its lines; an error is its text. Save on a table asks for a name in a popover; Save on a saved query replaces its SQL under its own name. `Ctrl+↵` in the textarea runs. The draft, the last result and the caret are kept per item in the module, so a redraw never loses them |
| Verbs | a saved query offers `delete` Delete, which is destructive, so the browser asks first and drops the row; a table offers `export` Export, which the browser opens against `export/{name}`. Opening a row is both the query and the load: the page is the editor |
| Execution | `query.py` splits the text on the semicolons `sqlite3.complete_statement` calls statement ends and runs the statements in order; nothing parses SQL. `read` drives the `mode=ro` connection under `store.ro_lock`, so a write fails inside SQLite, and the read transaction sqlite3 opened for the attempt is rolled back so the connection is not pinned to a stale snapshot. `write` drives the read-write connection inside one `BEGIN`, so a script lands whole or rolls back, and reports `{changes, ms}` without fetching rows. `execute` is the bare read-write drive both sit on, returning `{columns, rows, total, truncated, changed, ddl, statements, ms}` from the last statement that returned rows, at most `max_rows` of them, blobs as `<N bytes>`; one progress handler covers the whole script and interrupts it past `max_seconds`. An error comes back as text naming the statement that broke, not a failed job. `explain` prefixes `EXPLAIN QUERY PLAN` to the first statement, which prepares it and never runs it. `csv_text` writes one table out as CSV, its column names first |
| Routes | `blank` (store file name, size with the WAL, tables), `table/{name}` (one table: module, rows, columns with type, notnull, default and pk, indexes, triggers, the CREATE statement; 404 for a hidden or unknown name), `export/{name}` (the whole table as CSV named `<table>-<stamp>.csv`, an `exported` event, 404 for a hidden or unknown name), `item/{id}`, `action/{run\|write\|explain\|save\|delete}` on resource `db`, shared with backup and vacuum. `run` goes to `read` and answers `{needs_confirm: true}` when SQLite refuses the statement; `write` backs the store up to `data/backups/otto-<stamp>-pre-write.db`, runs the script in one transaction and returns `{changes, ms, backup}` with a `wrote` event; `save` takes `{name, sql}` and answers the id; `delete` takes the id bare or as the `query:<id>` the rows carry. `run`, `write`, `explain` and `save` are what the editor posts |
| Hooks | `numbers` (store size), `rows`, `item`, `context` (every table under its module with its columns and row count, the saved query names). No `today` and no `queue`: nothing here waits on the owner |
| Tools | read: `db_schema` (every table with its module, columns, indexes, triggers, CREATE statement and row count), `db_query(sql, limit)` (limit clamped to `max_rows`, on the `mode=ro` connection), `db_explain`; write: `db_save_query` only, on the full server. Neither `query.write` nor `query.execute` has a tool: a statement that changes data or schema reaches the store only from the editor |
| Agent | `agent.md`: one statement from the owner's words, checked with `db_query` and shown with its answer; a save only when the owner says to save or keep a query, never to hand a statement over; a change to data or schema is written and shown in a code block for the owner to run from the editor, neither saved nor claimed applied |

## Patches

### Routes and a query mode nothing reaches

- Kind: defect
- Where: `app/modules/database/routes.py` (`blank`, `table/{name}`, the per-module `rows` total in `_modules`), `app/modules/database/query.py` (`execute`, the `ddl` and `statements` fields of `_drive`'s answer), `database_queries.created_at`, `tests/test_database.py` (`test_execute_writes`, the `blank` and `table` calls)
- Found: 09-22-2026, the stale-code audit
- Status: open

What happens: the editor runs SQL through `read`, `write` and `explain`, and nothing requests `blank` or `table/{name}`. `execute`, the read-write drive that once ran and wrote together, is left with one caller, `explain`, which hands it a single `EXPLAIN QUERY PLAN` that the read-only connection runs as well; its write, DDL and commit-by-statement behaviour, and the `ddl` and `statements` it reports, reach only `test_execute_writes`. `_modules` sums rows per module for a list that went with the page, and a saved query's `created_at` is written and never read. The Execution and Routes rows above still describe `execute`, `blank` and `table/{name}`.

Expected: one read path, one write path, and the routes the page calls.

Fix: `explain` runs through `read`; `execute`, its two fields, the two routes, the sum and their tests go.

### A write whose script has its own BEGIN always fails

- Kind: bug
- Where: `app/modules/database/query.py` (`write`, `statements`)
- Found: 09-22-2026, the stale-code audit
- Status: open

What happens: `write` opens a transaction and then runs the owner's statements one by one, `BEGIN` and `COMMIT` among them, so a script that brackets itself stops at "cannot start a transaction within a transaction" and rolls back. The docstring says the script lands whole "whatever the owner's own BEGIN said", and `execute`'s advised writing `BEGIN` and `COMMIT`.

Expected: a script with its own `BEGIN` and `COMMIT` runs as one transaction, like any other.

Fix: `write` drops a leading `BEGIN` and a trailing `COMMIT` or `END` before driving the rest inside its own transaction.

### The store's size reads MB from 1 GB up to 1 TB

- Kind: bug
- Where: `app/modules/database/routes.py` (`_human`)
- Found: 09-22-2026, the stale-code audit
- Status: open

What happens: after the loop has divided three times the number is in gigabytes, and the last line calls it GB only from 1024 up, so a 2.5 GB store reads "2.5 MB". The label reaches the agent through `numbers`. The store is far below 1 GB, so nothing shows it yet.

Expected: the unit matches the number.

Fix: the last line labels the number GB.

### A saved query's row carries the caption "saved"

- Kind: defect
- Where: `app/modules/database/routes.py` (`_query_row`)
- Found: 09-22-2026, the stale-code audit
- Status: open

What happens: every saved query shows " · saved" after its name, a caption its type and its place in the feed already say, against UI 1 of the repo's CLAUDE.md.

Expected: the name alone.

Fix: drop the `snip`, and the Rows row above says so.
