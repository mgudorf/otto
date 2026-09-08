# Database Plan

Status: planning, 2026-09-07.

Version 0 lets the owner look at every table in Otto's own store, type a query, run it, read the rows, keep the queries worth keeping, and ask the agent to write or explain a query in plain words. Without it the only view of the data is whatever each module chooses to show; nothing can be checked, counted or cross-referenced by hand.

## Sources

| Source | Governs |
|---|---|
| `docs/ARCHITECTURE.md` > Database | the three goals: manual querying, agent writes queries, agent knows the schema |
| `docs/ARCHITECTURE.md` > Daemon, Mechanisms, Claude, Module contract, Config, Platform tables | runner, read/write split, tool servers, hooks, knobs |
| `docs/ARCHITECTURE.md` > UI, Frame contract | hue `#a68bd0`, rail order 8, tokens, row and button specs |
| `docs/design/Personal Dashboard App.dc.html` lines 30, 160-172, 266-279, 356, 400, 414 | rail icon, LEFT (tables with counts, saved queries with stamps), MIDDLE (editor, Run, Explain, Export, result line, grid, paging), agent skills and placeholder, header meta |
| `app/store.py`, `app/config.py`, `config.toml` | where the read-only connection and the `[database]` knobs land |
| `app/runner.py`, `app/api.py` (`data.backup`, `data.vacuum` on resource `db`) | how a run becomes a job and what it serializes with |
| `app/modules/__init__.py`, `app/modules/memory/*`, `app/static/pages/memory.js`, `app/static/shell.js`, `app/static/rows.js` | the contract as built, the page pattern, the shell's page table |
| `tests/conftest.py`, `tests/test_app.py`, `tests/test_platform.py` | fixtures, end-to-end pattern, the existing split tests |

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | Version 0 is read-only. Every statement the page or the agent runs goes through a second SQLite connection opened with `mode=ro` | SQLite refuses the write itself, so no SQL parsing and nothing to bypass. `PRAGMA query_only` alone can be switched off by the very statement being run; a `mode=ro` connection cannot |
| 2 | The read-only connection is `Store.read_only()` in `app/store.py`: opened once, own lock, `busy_timeout` 5000, a progress handler that interrupts a statement past `[database] max_seconds` | Resources live in the daemon; routes and MCP tools share one connection; a runaway query stops on its own |
| 3 | Run and Explain are user actions through `runner.run_action` on resource `db`, with the SQLite call in `asyncio.to_thread` | Serializes with backup and vacuum on the same resource, gets a job row, keeps the event loop free |
| 4 | A run returns the whole result up to `[database] max_rows` with a `truncated` flag; the page shows `ui.page_size` rows at a time and pages in the browser | No rewrapping of the owner's SQL to count or offset; matches the artboard's `1-40 / 412 · next` |
| 5 | SQL errors and interruptions come back as `{error}` with status done, never raised | A typo must not write a failed job and a failed event to Activity |
| 6 | Saved queries live in `db_queries`; the agent proposes a query by saving it with `db_save_query`, the only write tool | One mechanism puts a query in front of the owner: it appears under `saved`, one click loads the editor |
| 7 | LEFT lists tables from `sqlite_master` minus `sqlite_%` and the shadow tables of virtual tables, with `COUNT(*)` per table on each load | The artboard shows user tables with counts; 18 tables count in milliseconds |
| 8 | Picking a table loads `select * from <table> order by rowid desc limit <ui.page_size>;` into the editor and does not run it | Artboard behaviour; the owner edits before running |
| 9 | No schedules, no `today` or `item` hooks, no item route | Nothing needs keeping current; the artboard's Database page has no inspector, selection fills the editor |
| 10 | Knobs: `config.toml [database] max_rows`, `max_seconds`; `ui.page_size` reused for paging and the table template | Both bound daemon work, so they are boot values; no new live setting |

Rejected: classifying statements by parsing SQL; `set_authorizer` (more code, same guarantee as `mode=ro`); wrapping the SQL in `SELECT COUNT(*) FROM (...)` for totals; editing rows or running write statements (pending decision 1); Export (pending decision 2).

## Layout

| File | Change |
|---|---|
| `app/store.py` | `Store.read_only()` returning the `mode=ro` connection; `Store.close()` closes it too |
| `app/config.py`, `config.toml` | `Database(max_rows, max_seconds)` dataclass and `[database]` section |
| `app/modules/database/__init__.py` | `MANIFEST` |
| `app/modules/database/schema.sql` | `db_queries` |
| `app/modules/database/query.py` | `run(conn, sql, max_rows, max_seconds)` returning `{columns, rows, total, truncated, ms}` or `{error}`; `explain(...)`; `tables(conn)`; shared by routes and tools |
| `app/modules/database/routes.py` | `left`, `blank`, `action/{run,explain,save,delete}`, hooks `numbers`, `context` |
| `app/modules/database/tools.py` | `db_schema`, `db_query`, `db_explain` on both servers; `db_save_query` on `otto` only |
| `app/modules/database/agent.md` | the agent's job |
| `app/static/pages/database.js` | `load`, `meta`, `Left`, `Middle` |
| `app/static/shell.js` | add `database` to `PAGES` |
| `tests/test_database.py` | the tests below |

## Contract

| Field | Value |
|---|---|
| name, title | `database`, `Database` |
| hue, order | `#a68bd0`, 8 |
| icon | `<rect x="3" y="4" width="14" height="12" rx="2"></rect><path d="M3 10h14"></path>` (artboard line 30) |
| schedules | none |
| agent | placeholder `Describe a query…`; skills `nl-to-sql`, `explain-plan`, `schema`; read tools `db_schema`, `db_query`, `db_explain`; write tools `db_save_query` |

Routes, prefix `/api/database`:

| Route | Wire shape |
|---|---|
| `GET left` | `{groups: [{label: "tables", count, rows: [{id: "table:<name>", module, text: <name>, stampText: <row count>}]}, {label: "saved", count, rows: [{id: "query:<id>", module, text: <name>, stamp: updated_at, sql}]}]}` |
| `GET blank` | `{db: "otto.db", size_bytes, tables}` for the header meta `otto.db · 4.1 MB` and the result-line default |
| `POST action/run` `{sql}` | `{columns, rows, total, truncated, ms}` or `{error}` |
| `POST action/explain` `{sql}` | `{lines: [detail, ...], ms}` or `{error}` |
| `POST action/save` `{name, sql}` | `{id}`; upserts on name; event `saved` |
| `POST action/delete` `{id}` | `{id}`; event `deleted` |

Hooks: `numbers` returns `{value: "<size, e.g. 4.1 MB>", label: "database"}` (the artboard's Home tile shows the size, and Home renders string values as given); `context` returns the table list with columns and row counts and the saved query names, so the agent knows the schema on every turn. `today` and `item` are absent (decision 9).

MCP tools: `db_schema()` gives every table's `CREATE` statement and row count; `db_query(sql, limit)` runs read-only through the same `run`, `limit` capped at `max_rows`; `db_explain(sql)`; `db_save_query(name, sql)` upserts into `db_queries`.

Agent's job: turn the owner's words into one SQLite query against the schema it is given, run it read-only to check it answers the question, show the SQL and the answer, and save it with `db_save_query` when the owner wants to keep it or asked for a query rather than an answer. Explain plans on request. Never claims a save happened unless the tool returned an id. Never runs anything but read statements, and says so if asked to change data.

Page: LEFT is the two groups in mono rows as the artboard draws them, no search or chips (the artboard has none on this page); picking a table fills the editor (decision 8), picking a saved query loads its SQL. MIDDLE is the editor, `Run` in the hue, `Explain`, the result line (`412 rows · 3 ms`, `412 of 1000+ rows` when truncated, or the error in red), the grid with the columns the query produced, and `1-40 / 412` with `prev` and `next`. A `Save` secondary button asks for a name. Ctrl+Enter runs.

Departures from the artboard: `Export` is not built (pending decision 2). The grid's columns come from the query rather than the artboard's fixed five. A `Save` button and a `prev` link are added because saved queries and paging need them. Result rows are rendered as text, not the artboard's placeholder bars.

## Data

`schema.sql`:

| Table | Columns |
|---|---|
| `db_queries` | `id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, sql TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL` |

Cursors: none.

| Path | Client | Writes |
|---|---|---|
| `action/run`, `action/explain`, `db_query`, `db_explain`, `db_schema`, `left` counts | `store.read_only()` | none possible |
| `action/save`, `action/delete` | `ctx.commit()` on the store's write connection | `db_queries` only |
| `db_save_query` (server `otto` only) | `store.tx()` | `db_queries` only |

Proof of the split: an `INSERT` sent to `action/run` comes back as `{error: "attempt to write a readonly database"}` and the target table's count is unchanged; the read server's tool names include `db_query` and exclude `db_save_query`; `store.read_only().execute("INSERT ...")` raises `sqlite3.OperationalError`.

## Phases

| Phase | Builds | Usable result |
|---|---|---|
| 1 | `Store.read_only()`, `[database]` config, manifest, `query.py` run, `left`, `blank`, `action/run`, `numbers`, the page with tables, editor, Run, result grid and paging, shell registration | Open Database, pick a table, edit the SQL, run it, page through the rows; the Home tile shows the store size |
| 2 | `db_queries`, `action/save`, `action/delete`, `action/explain`, the `saved` group, Save and Explain buttons | Keep queries by name, reload them with one click, read the query plan |
| 3 | `tools.py`, `agent.md`, `context` hook | Describe a query in words; the agent writes it, checks it, answers, and saves it to the `saved` list; ask it to explain a plan |

## Tests

- `test_read_only_refuses_writes`: `store.read_only()` runs a `SELECT`, raises on `INSERT`, and interrupts a recursive CTE past `max_seconds` (config replaced with a small value).
- `test_database_run_explain_save`: through `build(config)`: capture a memory, run `select * from memories`, assert columns and one row; run an `INSERT`, assert `{error}` and the count is still one; run a query over a `max_rows` of 2, assert `truncated`; explain returns lines; save, `left` shows it under `saved` with its `sql`; delete removes it.
- `test_database_tools_split`: `db_save_query` is registered on `otto` only; the three read tools are on both.
- No new LLM test: `spawn` stays mocked by `conftest.py`; the agent's session path is already covered by `test_session_turn_and_clear`.

## Manifest

Present:

| Item | Version / location | Needed for |
|---|---|---|
| Python | 3.14.7, `.venv/Scripts/python.exe` | everything |
| SQLite | 3.50.4 via stdlib `sqlite3`; `mode=ro` URI refuses writes, `set_progress_handler` interrupts, `EXPLAIN QUERY PLAN` and `PRAGMA table_info` answer (all run this session) | decisions 1, 2, 8 |
| fastapi, mcp, pytest, httpx | 0.141.1, 2.2.0, 9.1.1, 0.28.1 installed | routes, tool servers, tests |
| `data/otto.db` | 225 KB plus a 4.1 MB WAL, 18 tables including FTS shadow tables | the data the page shows |
| Artboard hue, icon, LEFT and MIDDLE shapes | `docs/design/Personal Dashboard App.dc.html` | contract |
| Preact, htm | `app/static/vendor/` | the page |

Missing: none. No new package.

Needs you: nothing to install or authorize; only the pending decisions below.

Verify:

| Check | Command |
|---|---|
| Suite green on `main` before branching | `.venv/Scripts/python.exe -m pytest -q` |
| Page renders in Chrome after phase 1 | `python -m app`, open Database from the rail |

## Worktree

```
git worktree add ../otto-database -b database
```

Work in `../otto-database`. When `database` is merged to `main`, run `/sync-architecture`.

## Pending decisions

1. Editing. Version 0 refuses every write. For version 1, should a write statement typed in the editor run after a confirm, or should editing be per row in the grid?
2. Export. Build it as a CSV download of the current result, or drop the button from this page as the Settings gap did?
