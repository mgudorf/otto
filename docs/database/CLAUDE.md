# Database

1. Module which interfaces with underlying DBs to allow for manual querying/editing of data to give visibility
2. Agent is natural language interface for creating queries
3. Agent has in depth knowledge of database schema.

## Built

| Piece | Current state |
|---|---|
| Table | `database_queries(name unique, sql)`: the queries the owner or the agent kept |
| Execution | `query.py` splits the text on the semicolons `sqlite3.complete_statement` calls statement ends and runs the statements in order; nothing parses SQL. `read` drives the `mode=ro` connection under `store.ro_lock`, so a write fails inside SQLite, and the read transaction sqlite3 opened for the attempt is rolled back so the connection is not pinned to a stale snapshot. `write` drives the read-write connection inside one `BEGIN`, so a script lands whole or rolls back, and reports `{changes, ms}` without fetching rows. `execute` is the bare read-write drive both sit on, returning `{columns, rows, total, truncated, changed, ddl, statements, ms}` from the last statement that returned rows, at most `max_rows` of them, blobs as `<N bytes>`; one progress handler covers the whole script and interrupts it past `max_seconds`. An error comes back as text naming the statement that broke, not a failed job. `explain` prefixes `EXPLAIN QUERY PLAN` to the first statement, which prepares it and never runs it. `csv_text` writes one table out as CSV, its column names first |
| Routes | `left` (`{modules, saved}`: every user table under the module whose `schema.sql` creates it, read off a scratch connection each schema runs on, so nothing parses SQL; `app` first, then rail order, `other` last for a table no schema owns; each module with its row total and its tables with their counts, shadow tables of virtual tables and `sqlite_*` hidden; then the saved queries with their sql), `blank` (store file name, size with the WAL, tables), `table/{name}` (one table: module, rows, columns with type, notnull, default and pk, indexes, triggers, the CREATE statement; 404 for a hidden or unknown name), `export/{name}` (the whole table as CSV named `<table>-<stamp>.csv`, an `exported` event, 404 for a hidden or unknown name), `item/{id}` (a table as a ROW with its columns and an `Export` action, or `query:<id>` with its text and a `Delete` action), `action/{run\|write\|explain\|save\|delete}` on resource `db`, shared with backup and vacuum. `run` goes to `read` and answers `{needs_confirm: true}` when SQLite refuses the statement; `write` backs the store up to `data/backups/otto-<stamp>-pre-write.db`, runs the script in one transaction and returns `{changes, ms, backup}` with a `wrote` event; `delete` takes the id bare or as the `query:<id>` the page lists |
| Hooks | `numbers` (store size), `rows` (the saved queries as ROWs, newest first, each stamped with when it was last kept, which is what Home's Recent and `/api/items` order by; a table has no moment and is marked `taggable: false`, so it is neither one of them nor anything a tag can land on), `item`, `context` (every table under its module with its columns and row count, the saved query names) |
| Tools | read: `db_schema` (every table with its module, columns, indexes, triggers, CREATE statement and row count), `db_query(sql, limit)` (limit clamped to `max_rows`, on the `mode=ro` connection), `db_explain`; write: `db_save_query` only, on the full server. Neither `query.write` nor `query.execute` has a tool: the agent drafts a statement and saves it, the owner runs it from the editor |
| Page | The editor sits above the list: a mono textarea, `Run` (Ctrl+Enter inside the box), `Explain` and `Save`, with what the daemon reports of the last statement at the right of the button row and the result beneath as a grid carrying the query's own columns. The box is one element for the life of the page, so a redraw keeps the caret and the height it was dragged to. The result is one grid whose header and rows are subgrids of it, so a column is as wide as its widest value, at least 96px and with every cell capped at 420px, its header included, so that neither a long value nor a long column name opens the result scrolled sideways; the rows line up under the header, and a result wider than the pane scrolls sideways instead of being cut off at the card's edge. `Run` reads; when SQLite refuses the statement the page drops the last result and asks `This statement writes. Back up and run?`, and answering runs the statement that was asked about, whatever the box holds by then, backing the store up first and naming the backup. `Save` asks for a name and upserts on it. The list is every table, the module that owns it in that module's hue, its name in mono and its row count; a table row takes no tag and offers no checkbox, because a table is the store's own shape rather than an item the owner keeps; under `Saved` come the kept queries, each with `Load`, which puts its text in the editor. Selecting a table opens its columns with their types and constraints and an `Export` that sends the whole table as CSV; selecting a saved query opens its text and `Delete`. `Back up now` sits right of the search bar |
| Departures | The artboard puts a key cap beside `Run`, a line of advice under the buttons and a `Column · Type · Constraints` header over the pane's columns; all three are dropped, the header because a column header is chrome text. Ctrl+Enter is the box's own binding and is listed nowhere: the `?` overlay lists what the frame dispatches, and the frame dispatches a single plain key pressed outside a field. Its `Export CSV` sits in the pane's header, which the shell owns, so it is the pane's primary button, built from what `item` offers. Saved queries are a second group in the list, which the artboard has none of. Result columns come from the query rather than the artboard's fixed five |

## Patches

### Colour on the page outside a card border and a primary button
- Kind: defect
- Where: `app/static/pages/database.js`, the owner cell in `cells` (`color:${hue(i.owner)}`) and the failed statement in `line()` (`color:var(--danger)`); the same two uses live in `app/static/pages/activity.js` and `app/static/pages/finance.js`
- Found: 2026-09-20, the port review of the Database page
- Status: open

What happens: each table row prints the owning module's name in that module's hue, and a statement SQLite refused prints in the danger red. Both come straight from the artboard, which colours a module name and a failure this way on Activity and Finance as well.

Expected: UI tenet 4 puts colour on a card's left border and on a primary button and nowhere else, which would leave the module name in `--ink-2` and the error in the ordinary meta grey.

Fix: one ruling for all three pages, not a change to this one: either the tenet's exception list grows to cover a module name and a failure, or the three pages drop the colour together. Whichever way it goes, the artboard changes with it.

### A tag on a saved query is written and never seen again
- Kind: bug
- Where: `app/modules/database/routes.py` (`_query_row`), `app/static/pages/database.js` (the query rows in `load`)
- Found: 09-20-2026, the recheck of the Database page
- Status: open

What happens: a saved query is a real item, so the shell lets the owner tag one — ctrl-click and `t` reach any row the page draws, and the table rows no longer take one. The tag is written into `app_tags` under `database`, but `_query_row` hands every row an empty `tags` list and never reads them back, so the row shows no tag and the tag's own page does not find the query. The tag exists only in the table.

Expected: a tag put on a saved query shows on its row and finds it on the tag's page, as a tag on any other module's item does.

Fix: `_query_row` takes its tags from `tags_for(store, "database", ids)`, read once for the whole list the way the other modules' `rows` hooks do, and the page's `load` stops handing query rows an empty `tags` of its own.
