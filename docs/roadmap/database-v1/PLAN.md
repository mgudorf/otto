# Database v1 Plan

Status: planning, 2026-09-08. **BLOCKED: three owner decisions are unanswered (see Missing, and Pending decisions). Nothing marked OPEN below can be built until they are.**

Version 1 adds what version 0 deliberately refused: changing data from the Database page, and taking a query result out of Otto as a file. Without it the page can only look; every correction still has to be made in the module that owns the row, or not at all.

Prerequisite: the `database` branch (version 0) merged to `main`. This plan changes files that branch creates.

## Missing

Every row here must be answered before the worktree is created. Each is repeated as a pending decision at the end.

| # | What is missing | Why it blocks | Sections affected |
|---|---|---|---|
| A | **How editing works**: (a) a write statement typed in the editor, run after a confirm; (b) per-row editing in the result grid; (c) both | The route set, the page, the tests and the schema differ entirely between (a) and (b) | Decisions, Layout, Contract, Data, Phases, Tests |
| B | **What Export produces**: (a) CSV of the current result; (b) a copy of `otto.db`; (c) JSON of the current result | Defines the route, the file name, and whether it re-runs the query | Contract, Layout, Phases |
| C | **Whether the agent may write data** at all, or only the owner through the page | Decides whether a write tool exists on the `otto` server and what `agent.md` must say. ARCHITECTURE's Database section is silent; Email's "agent never writes" is a stated hard constraint there, not here | Contract, Data, Tests |

## Sources

| Source | Governs |
|---|---|
| `docs/roadmap/database/PLAN.md` | version 0: the read-only connection, `query.py`, routes, page, and the two decisions it deferred here |
| `docs/ARCHITECTURE.md` > Database | "manual querying/editing of data" is the requirement version 0 left half met |
| `docs/ARCHITECTURE.md` > Daemon ("any write to an external system, and any deletion, is a synchronous user action from the UI"), Mechanisms, Module contract | writes are user actions through `run_action`; results in one transaction |
| `docs/design/Personal Dashboard App.dc.html` lines 266-279 | the `Export` button; the artboard shows no edit affordance, no confirm, no editable cells |
| `docs/gaps/settings-export-not-built.md` | the same undefined Export on Settings; whatever B decides should settle both |
| `app/runner.py`, `app/store.py` (`backup`), `app/api.py` (`data.backup` on resource `db`) | the write path, the backup primitive, the resource writes serialize on |

## Decisions

Firm, independent of A, B and C:

| # | Decision | Why |
|---|---|---|
| 1 | Every write is a user action through `runner.run_action` on resource `db`, executed on the store's write connection inside one `ctx.commit()` transaction | The Daemon contract; a failing statement rolls back whole; writes serialize with backup, vacuum and version 0 reads |
| 2 | A write returns `{changes, ms}` from `conn.total_changes` and never rows | The owner sees exactly how many rows moved |
| 3 | Every write action takes a backup into `data/backups/` first, through the existing `store.backup`, in the same job | The only undo the store has; cheap at the current size; makes a wrong `UPDATE` recoverable |
| 4 | Writes are never scheduled and never reachable from `ctx.run_task` | Daemon contract; no `tasks.py` for this module |
| 5 | After any write the page refreshes LEFT so table counts and the Home tile are current | The UI is a view of daemon state |

**OPEN**, resolved by the pending decisions:

| # | Decision | Depends on |
|---|---|---|
| 6 | Route set for editing: `action/write {sql}` for (a); `action/row_update {table, rowid, values}`, `action/row_delete {table, rowid}`, `action/row_insert {table, values}` for (b) | A |
| 7 | Whether (a) requires the page to detect a write statement before Run and show the confirm, or the daemon answers `{needs_confirm: true}` first and the page re-posts with `confirm: true` | A |
| 8 | Export route: `GET /api/database/export?query_id=` re-running a saved query to CSV, or `GET /api/database/export` streaming a `store.backup` copy, or JSON | B |
| 9 | Whether a `db_write` tool exists on the `otto` server, and the sentence in `agent.md` that permits or forbids changing data | C |

Rejected: silent writes without a backup; a separate "edit mode" toggle in `settings` (a knob that only exists to make the page allow what the daemon already allows).

## Layout

| File | Change | Depends on |
|---|---|---|
| `app/modules/database/routes.py` | the write action(s) and the export route | A, B |
| `app/modules/database/query.py` | `write(conn, sql)` for (a), or `row_*` helpers that build the statement from `{table, rowid, values}` with `PRAGMA table_info` for (b) | A |
| `app/modules/database/tools.py`, `agent.md` | `db_write` on `otto` only, or nothing | C |
| `app/static/pages/database.js` | confirm dialog on Run for (a); editable cells, a delete control and an insert row for (b); the Export button | A, B |
| `tests/test_database.py` | the tests below | A, B, C |

No change to `config.toml`, `app/store.py` or `app/schema.sql` is known yet. Decision 3 needs no knob: backups already go to `data/backups/`.

## Contract

Manifest unchanged from version 0. New routes, prefix `/api/database`:

| Route | Wire shape | Depends on |
|---|---|---|
| `POST action/write` `{sql, confirm}` | `{changes, ms, backup}` or `{error}` | A = (a) or (c) |
| `POST action/row_update` `{table, rowid, values}` | `{changes, backup}` | A = (b) or (c) |
| `POST action/row_delete` `{table, rowid}` | `{changes, backup}` | A = (b) or (c) |
| `POST action/row_insert` `{table, values}` | `{rowid, backup}` | A = (b) or (c) |
| `GET export` | a file; name, format and whether a query re-runs are **OPEN** | B |

Hooks unchanged. Events: `wrote` with the statement's first 120 characters and `changes`, `exported` with the file name.

MCP tools: **OPEN** (C). If permitted: `db_write(sql)` on `otto` only, same backup-first job as the route, and `agent.md` gains "change data only when the owner asked for exactly that change and repeats the statement back before running it". If forbidden: no new tool, and `agent.md` keeps version 0's "says so if asked to change data".

Departures from the artboard: the artboard has no edit affordance, so whichever of (a) or (b) is chosen is invented here and must be named in the final plan. `Export` exists on the artboard with no defined target; B defines it.

## Data

No new tables are known. **OPEN**: (b) needs none; (a) needs none; a per-write audit row (`db_writes(ts, sql, changes, backup)`) would only be added if the owner wants a history beyond `events` and `jobs`, which already record every write.

| Path | Client | Writes |
|---|---|---|
| version 0 paths | `store.read_only()` | none possible |
| every write action above | `ctx.commit()` on the store's write connection, after `store.backup` | any table, that is the point |
| `db_write` if C permits | `store.tx()` after `store.backup` | any table |

Proof of the split: the write actions and `db_write` are the only code paths that touch the store's write connection from this module; `test_tasks_never_reach_interactive_claude` already fails if a `tasks.py` appears that reaches them; the new test asserts `db_write` is absent from the read server.

## Phases

| Phase | Builds | Usable result | Depends on |
|---|---|---|---|
| 1 | backup-first write path in `query.py` and the route(s) of decision 6, the confirm or the editable grid, LEFT refresh | Change a row from the Database page and see the count and the backup | A |
| 2 | Export route and button | Take a result (or the store) out as a file | B |
| 3 | `db_write` and the `agent.md` rule, or a one-line note that the agent stays read-only | Ask the agent to make a change, or be told it cannot | C |

## Tests

- `test_write_backs_up_and_commits`: a write returns `changes`, a new file exists in `data/backups/`, and the row is changed; a failing statement leaves the table untouched and still returns `{error}`.
- `test_write_is_user_action_only`: the write path is reachable only through `run_action`; no `tasks.py` exists for the module; `db_write` (if C permits) is absent from the read server.
- `test_export`: **OPEN** until B; asserts the route returns the chosen format for a known result.
- `spawn` stays mocked by `conftest.py`.

## Manifest

Present:

| Item | Version / location | Needed for |
|---|---|---|
| Python, SQLite, fastapi, mcp, pytest, httpx | as recorded in `docs/roadmap/database/PLAN.md`, verified 2026-09-07 | everything |
| `store.backup`, `data/backups/` | `app/store.py`, `app/api.py` | decision 3 |

Missing:

| Item | Needed for | How |
|---|---|---|
| Version 0 merged to `main` | every file this plan edits | merge the `database` branch, run `/sync-architecture` |

Needs you:

| Item | How |
|---|---|
| Decisions A, B, C | answer the pending decisions; then this plan is rewritten with the OPEN rows resolved and the worktree is created |

Verify:

| Check | Command |
|---|---|
| Version 0 is on `main` | `git log --oneline main -- app/modules/database` shows commits |
| Suite green before branching | `.venv/Scripts/python.exe -m pytest -q` |

## Worktree

Only after A, B and C are answered and version 0 is merged:

```
git worktree add ../otto-database-v1 -b database-v1
```

Work in `../otto-database-v1`. When `database-v1` is merged to `main`, run `/sync-architecture`.

## Pending decisions

1. **A, editing.** Which of: (a) a write statement typed in the editor, run after a confirm; (b) per-row editing in the result grid; (c) both?
2. **B, Export.** Which of: (a) CSV of the current result; (b) a copy of `otto.db`; (c) JSON of the current result? The answer also settles `docs/gaps/settings-export-not-built.md`.
3. **C, agent writes.** May the Database agent change data through a `db_write` tool, or does it stay read-only with writes only from the page?
