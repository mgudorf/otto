# Memory v0 Plan

Status: planning, 2026-09-07.

Memory is where the owner dumps notes, links, quotes, facts and tasks in their own words, finds them again, and gets a nightly nudge when the pile clearly calls for an action. Without it the other modules have no owner-written record to tag, and Graph has nothing to read.

Version 0 is the proving build already on `main` plus what the Memory requirements and the artboard still leave unmet. Nothing outside those two sources is in scope.

## Sources

| Source | Governs |
|---|---|
| `docs/ARCHITECTURE.md` Memory | requirements 1 to 3 and the Built table |
| `docs/ARCHITECTURE.md` Daemon requirements and mechanisms | read-only scheduled agent, kill-safe tasks, one write path |
| `docs/ARCHITECTURE.md` Module contract, Config, Claude | file obligations, where knobs live, the two MCP servers |
| `docs/ARCHITECTURE.md` UI frame contract | hue `#d1a36a`, rail order 3, rows, chips, inspector |
| `docs/design/Personal Dashboard App.dc.html` line 26 | rail icon (rect plus three lines) |
| same, lines 105 to 118 (`isMem`) | LEFT: chips All / Notes / Links / Quotes, rows by day, kind leading slot, `N / total` and `more` |
| same, lines 213 to 222 (`showItem`) | inspector: glyph, kind and time, body, primary `Open`, actions `Link` / `Forget`, `Send to session` |
| same, lines 352, 380, 414, 474 | agent chips recall / tag / link / summarize, placeholder `Ask memory…`, row kinds note / link / quote / fact / task, header meta `48,212` |
| `app/modules/memory/*`, `app/static/pages/memory.js`, `app/config.py`, `config.toml`, `tests/test_app.py` | the proving build |
| `docs/bugs/budget-refusal-marks-job-failed.md` | how Activity shows `memory.suggest` outside the window; fixed in the runner, outside this plan |
| `docs/gaps/logon-task-not-registered.md` | why `memory.suggest` has never run on this machine |

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | The proving build is phase 0 of v0; nothing is rebuilt | It meets requirements 1 to 3 and every line of the module contract, with an end-to-end test on `main` |
| 2 | Kinds stay note, link, quote, fact, task; chips show all five | The artboard's rows carry all five kinds but its chips list four; a kind with no chip cannot be browsed |
| 3 | The suggest task's knobs move to `config.toml` `[memory]`: `suggest_lookback_days`, `suggest_max` | Hard-coded parameters are not allowed; the task reads them once per nightly run, so boot values suffice and a missing key fails at boot |
| 4 | The suggest prompt lists every prior suggestion, any status, with no cap | Requirement 3 says a suggestion is made once, ever; the current last-50 cap lets an old one come back |
| 5 | `Done` is the primary action on an open task; `Open` only on links | Requirement 1 calls Memory a to-do list, which needs completion; `Open` means nothing for a note |
| 6 | Agent chips are recall, tag, add, suggest | Chips are display-only and name what the agent can do; `summarize` contradicts requirement 3 (literal, never reworded) and `link` has no meaning yet (pending 2) |
| 7 | The artboard's `Link` action is not built in v0 | The artboard gives it a label and nothing else; building it means inventing what it links |

Rejected: rebuilding Memory from scratch; a journal kind; a Settings-page section for the memory knobs; a memory-to-memory link table; a vector index for search (FTS5 is in the stdlib and answers the requirement).

## Layout

Changed:

- `app/config.py`: `Memory(suggest_lookback_days, suggest_max)` dataclass on `Config`, required like every other section.
- `config.toml`: `[memory]` with both keys.
- `app/modules/memory/tasks.py`: reads `ctx.config.memory`; the prior-suggestions query loses its `LIMIT`.
- `tests/test_memory.py`: new, see Tests.

Unchanged, listed because the contract below describes them: `app/modules/memory/{__init__.py, schema.sql, routes.py, tools.py, agent.md}`, `app/static/pages/memory.js`.

## Contract

| Field | Value |
|---|---|
| Manifest | name `memory`, title `Memory`, hue `#d1a36a`, icon from artboard line 26, order 3 |
| Schedule | `suggest`, every 24h, resource `memory`, llm true (nightly window and budget apply) |
| Agent | placeholder `Ask memory…`; chips recall, tag, add, suggest |

Routes, all under `/api/memory`:

| Route | Wire shape |
|---|---|
| `GET left?query&chip&page` | `{groups: [{label "05 Sep", count, rows: [{id, module, text, stamp, leading: {kind}, done}]}], chips, chip, showing "40 / 318", more}` |
| `GET blank` | `{kinds, counts: {kind: n}, suggestions: [{id, text, memory_ids, created_at, status}]}` |
| `GET item/{id}` | `{id, kind, text, created_at, updated_at, done_at, module, tags, actions: [{verb, label, primary?, href?, confirm?}]}` |
| `POST action/capture` | body `{kind, text, tags}` → `{id}` |
| `POST action/forget` | body `{id}` → `{id}` |
| `POST action/tag`, `untag` | body `{id, tags}` / `{id, tag}` → `{id, tags}` |
| `POST action/done` | body `{id}` → `{id}` |
| `POST action/suggestion` | body `{id, status accepted or dismissed}` → `{id, status}` |

Every action runs through `runner.run_action` on resource `memory` and writes an `events` row.

| Tools | Names |
|---|---|
| read (both servers) | `memory_search(query, kind?, limit)`, `memory_get(id)`, `memory_tags()`, `memory_suggestions(status)` |
| write (`otto` only) | `memory_add(kind, text, tags?)`, `memory_tag(id, tags)`, `memory_suggest(text, memory_ids?)` |

Hooks: `numbers` is the memory count labelled `memories` (also the session context label); `today` is the local day's captures; `item` as above; `context` is counts by kind, the last ten memories, and open suggestions.

Agent: the Memory agent recalls with the read tools and quotes the owner literally. It groups related memories by id on request without rewording them, adds or tags only when asked, and may propose one action item when the memories clearly call for it, checking `memory_suggestions` first and recording the proposal with `memory_suggest` so it is never made twice.

Departures from the artboard:

- Chips add Facts and Tasks (decision 2).
- Inspector: `Done` primary on open tasks, `Open` only on links, no `Link` (decisions 5 and 7).
- Agent chips replace `link` and `summarize` with `add` and `suggest` (decision 6).
- MIDDLE blank state (capture box, open suggestions) is not in the artboard; carried over from the platform plan.
- Session header reads `claude · memory`, a platform-wide choice.

## Data

| Table | Columns |
|---|---|
| `memories` | id, kind (checked against the five kinds), text, created_at, updated_at, done_at |
| `memory_tags` | memory_id (cascades on delete), tag; primary key on both |
| `memory_suggestions` | id, text unique, memory_ids (JSON list), created_at, status open / accepted / dismissed |
| `memories_fts` | FTS5 over `text`, content table `memories`, kept by insert / delete / update triggers |

Cursor: `memory.suggest`, set to the run time inside the same transaction as the inserted suggestions.

External clients: none. Memory's only external system is Claude. The scheduled `suggest` task reaches it through `ctx.run_task` on the read server with `memory_search` and `memory_get`; session routes reach the full server, which alone carries `memory_add`, `memory_tag` and `memory_suggest`. The split is proven by `test_memory_tool_split` below plus the platform's `test_tasks_never_reach_interactive_claude`.

## Phases

| Phase | Builds | Usable result |
|---|---|---|
| 0 | proving build | built; see ARCHITECTURE.md |
| 1 | `[memory]` config section, task reads it, uncapped prior-suggestion list, `tests/test_memory.py` | The owner changes lookback or the suggestion cap in `config.toml` and relaunches; the suite proves the task, the task-only actions and the tool split offline |

## Tests

`tests/test_memory.py`, offline; `app.claude.spawn` raises under the autouse fixture and `ctx.run_task` is replaced per test.

- `suggest`: a canned JSON reply (bare and fenced) inserts rows once and advances the cursor in the same transaction; the same reply on a second run inserts nothing; no memories in the lookback returns `Skipped`; the prompt carries a dismissed suggestion.
- `done` and `suggestion` actions through the app: `done_at` set, row `done` in `left`, status changes, unknown id is 404.
- `test_memory_tool_split`: `register` against two recording fakes; the read server's tool names equal the manifest's `read_tools`, the full server's equal read plus write, and the two manifest tuples do not overlap.

## Manifest

Present:

| Item | Version / location | Needed for |
|---|---|---|
| Python | 3.14.7, `.venv/Scripts/python.exe` | everything |
| fastapi, uvicorn, mcp, httpx, pytest | 0.141.1, 0.52.4, 2.2.0, 0.28.1, 9.1.1 installed | routes, MCP servers, tests |
| SQLite with FTS5 | 3.50.4; virtual table created this session | store, search |
| Claude Code CLI | 2.1.263 at `C:\Users\gudo\.local\bin\claude.exe` | `suggest` task and sessions |
| Test suite | 16 passed in 1.75s this session | baseline |
| `data/otto.db` | 1 note, 1 tag, 0 suggestions; `memory.suggest` never run | phase 1 starts from a clean history |

Missing: none.

Needs you:

| Item | How |
|---|---|
| Daemon at logon, so `memory.suggest` runs inside `02:00-05:00` | `python -m app setup` from the repo root (docs/gaps/logon-task-not-registered.md) |

Verify:

| Check | Command |
|---|---|
| Suite green after phase 1 | `.venv/Scripts/python.exe -m pytest -q` |
| `suggest` ran on the first night | `.venv/Scripts/python.exe -c "import sqlite3; print(sqlite3.connect('data/otto.db').execute('select last_run, last_status, last_result from tasks where name = ?', ('memory.suggest',)).fetchone())"` |

## Worktree

```
git worktree add ../otto-memory -b memory
```

Work there. When `memory` is merged to `main`, run `/sync-architecture`.

## Pending decisions

1. Scope: v0 is the proving build plus phase 1. Name anything else v0 must hold, or confirm.
2. The artboard's `Link` action and `link` chip: what does a memory link to (another memory, a Graph node, an external item)? Until answered it stays out.
3. Journaling (requirement 1): is the day-grouped stream of notes the journal, or is a journal a distinct thing with its own shape?
