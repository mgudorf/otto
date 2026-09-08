# Database v1 Plan

Status: planning, 2026-09-08. Decisions A, B and C were answered by the owner on 2026-09-08; nothing is open.

Version 1 adds what version 0 deliberately refused: running a write statement from the editor after a confirm and a backup, and taking a whole table out as a CSV file. The agent stays read-only: it drafts a write statement in the owner's words and saves it, and the owner runs it. Without this the page can only look; every correction still has to be made in the module that owns the row, or not at all.

Prerequisite: the `database` branch (version 0) merged to `main`. This plan changes files that branch creates.

## Sources

| Source | Governs |
|---|---|
| Owner's answers, 2026-09-08 | A: writes are SQL typed by the owner or drafted by the agent, executed only by the owner. B: export a table as CSV. C: agents are read-only until evals exist |
| `docs/roadmap/database/PLAN.md` | version 0: `Store.read_only()`, `query.py`, `db_queries`, `db_save_query`, the page, the two decisions it deferred here |
| `docs/ARCHITECTURE.md` > Database | "manual querying/editing of data", the half version 0 left unmet |
| `docs/ARCHITECTURE.md` > Daemon ("any write to an external system, and any deletion, is a synchronous user action from the UI"), Mechanisms, Module contract | writes are user actions through `run_action`, results in one transaction |
| `docs/design/Personal Dashboard App.dc.html` lines 266-279, 356 | the `Export` button beside `Run` and `Explain`; the picked table (`st.table`); no confirm and no edit affordance drawn |
| `app/runner.py`, `app/store.py` (`backup`, `tx`), `app/api.py` (`data.backup` on resource `db`) | the write path, the backup primitive, the resource writes serialize on |
| `docs/gaps/settings-export-not-built.md` | stays open: B defines Export on the Database page only, not on Settings |

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | The daemon classifies a statement, not the page. `action/run` keeps running everything on the read-only connection; when SQLite answers `attempt to write a readonly database` the route returns `{needs_confirm: true}` instead of `{error}` | No SQL parsing anywhere; SQLite decides what is a write, and a refused statement has no side effects |
| 2 | The page then shows one confirm, `This statement writes. Back up and run?`, and posts the same SQL to `action/write` | One extra click for every write, none for reads; the artboard's editor stays the only input |
| 3 | `action/write` is a user action on resource `db`: `store.backup` into `data/backups/`, then the statement inside one `ctx.commit()` transaction on the store's write connection | Daemon contract; the backup is the store's only undo; a failing statement rolls back whole; writes serialize with backup, vacuum and version 0 reads |
| 4 | A write returns `{changes, ms, backup}` from the cursor's `rowcount` (0 for statements without one, such as DDL), never rows | The owner sees exactly how many rows moved and which file restores them |
| 5 | Any single statement the owner confirms runs, including DDL | "Editing of data" with SQL is the requirement; the backup covers the mistake; `sqlite3` already refuses more than one statement per call |
| 6 | Export is `GET /api/database/export/{table}`: the whole table, every column, as CSV with a header row, built on the read-only connection, sent as an attachment named `<table>-<YYYYMMDD-HHMMSS>.csv` | B: a table, not a result. `max_rows` does not apply; export means all of it |
| 7 | The `Export` button acts on the table picked in LEFT and is inactive until one is picked | The artboard tracks the picked table; export of a result was not asked for |
| 8 | The agent gets no new tool. `agent.md` changes one rule: asked to change data, it drafts the statement, saves it with `db_save_query`, and tells the owner to run it from `saved` | C: agents are read-only until evals exist; A: the owner executes |
| 9 | Events: `wrote` with `changes` and the statement's first 120 characters; `exported` with the file name | Activity shows every write and every export |
| 10 | No new knob and no new table. Writes and exports are recorded by `jobs` and `events` already | Nothing to tune; a history table would duplicate what exists |

Rejected: detecting writes in the page (parsing); per-row editing in the grid (A chose SQL); a `db_write` tool (C); exporting the current result (B chose the table); an edit-mode toggle in `settings`; streaming the CSV row by row while holding the store lock.

## Layout

| File | Change |
|---|---|
| `app/modules/database/query.py` | `run` returns `{needs_confirm: true}` on the read-only refusal; `write(conn, sql) -> {changes, ms}`; `csv_of(conn, table) -> str` using the stdlib `csv` module |
| `app/modules/database/routes.py` | `action/write`; `GET export/{table}`, name checked against `tables(conn)` and quoted as an identifier, 404 otherwise |
| `app/modules/database/agent.md` | the rule in decision 8 |
| `app/static/pages/database.js` | confirm on `needs_confirm`; write result line `3 rows changed · otto-20260908-101500.db`; `Export` button beside `Explain`, opening the export URL for the picked table |
| `tests/test_database.py` | the tests below |

## Contract

Manifest unchanged. Routes, prefix `/api/database`:

| Route | Wire shape |
|---|---|
| `POST action/run` `{sql}` | as version 0, plus `{needs_confirm: true}` when the read-only connection refuses a write |
| `POST action/write` `{sql}` | `{changes, ms, backup}` or `{error}`; the backup is taken before the statement, so `backup` is present either way |
| `GET export/{table}` | `text/csv`, `Content-Disposition: attachment; filename="<table>-<stamp>.csv"`; 404 for a name not in the table list |

Hooks unchanged. MCP tools unchanged: read `db_schema`, `db_query`, `db_explain`; write `db_save_query` only, still on `otto` alone.

Agent's job, changed sentence: asked to change data, it writes the statement, saves it with `db_save_query` under a name that says what it does, and answers with the statement and "run it from saved". It never runs a write, and `db_query` still cannot.

Page: `Run` on a write statement opens the confirm of decision 2; `Cancel` leaves the editor as it was. After a confirmed write the result line shows changes and the backup file, and LEFT refreshes so counts are current. `Export` sits beside `Explain`, muted until a table is picked in LEFT, then opens `export/<table>` in the window, which Chrome saves as a download.

Departures from the artboard: the confirm dialog is not drawn there. `Export` acts on the picked table, not on the result under it.

## Data

No new tables. Cursors: none.

| Path | Client | Writes |
|---|---|---|
| version 0 paths, `action/run`, `export/{table}` | `store.read_only()` | none possible |
| `action/write` | `store.backup`, then `ctx.commit()` on the store's write connection | whatever the owner confirmed |
| `db_save_query` (server `otto` only) | `store.tx()` | `db_queries` only |

Proof of the split: `action/write` is the only path in the module that reaches the write connection with owner SQL; the read server's tools and the `otto` server's tools are the version 0 sets exactly, so the agent has no write beyond `db_queries`; the recorded `backup` file exists before any change is visible.

## Phases

| Phase | Builds | Usable result |
|---|---|---|
| 1 | `needs_confirm` in `run`, `write`, `action/write`, the confirm and result line in the page, the `agent.md` rule | Type or ask for an `UPDATE`, confirm it, see the rows changed and the backup file; the agent drafts writes into `saved` and never runs them |
| 2 | `csv_of`, `export/{table}`, the `Export` button | Pick a table, press `Export`, get `<table>-<stamp>.csv` |

## Tests

- `test_write_confirms_backs_up_and_commits`: capture a memory; `action/run` with an `UPDATE` returns `needs_confirm`; `action/write` returns `changes == 1` and a `backup` path that exists under `data/backups/`; the row is changed; a write with a syntax error returns `{error}` and the row is unchanged.
- `test_export_csv`: `export/memories` returns `text/csv` with the header and one data row; `export/nope` and `export/"memories"` return 404.
- `test_agent_stays_read_only`: the `otto` server's tools named `db_*` are exactly `db_schema`, `db_query`, `db_explain`, `db_save_query`; the read server's exclude `db_save_query`; `db_query` with an `UPDATE` returns `{error}`.
- `spawn` stays mocked by `conftest.py`; no LLM test.

## Manifest

Present:

| Item | Version / location | Needed for |
|---|---|---|
| Python, SQLite, fastapi, mcp, pytest, httpx | as recorded in `docs/roadmap/database/PLAN.md`, verified 2026-09-07 | everything |
| `csv` | stdlib | decision 6 |
| `store.backup`, `data/backups/` | `app/store.py`, `app/api.py` | decision 3 |

Missing:

| Item | Needed for | How |
|---|---|---|
| Version 0 merged to `main` | every file this plan edits | merge the `database` branch, run `/sync-architecture` |

Needs you: nothing.

Verify:

| Check | Command |
|---|---|
| Version 0 is on `main` | `git log --oneline main -- app/modules/database` shows commits |
| Suite green before branching | `.venv/Scripts/python.exe -m pytest -q` |
| A download lands from the app window | after phase 2, `python -m app`, pick `memories`, press `Export`, check the Downloads folder |

## Worktree

After version 0 is merged:

```
git worktree add ../otto-database-v1 -b database-v1
```

Work in `../otto-database-v1`. When `database-v1` is merged to `main`, run `/sync-architecture`.

## Pending decisions

None. A, B and C were answered on 2026-09-08 and are recorded under Sources.
