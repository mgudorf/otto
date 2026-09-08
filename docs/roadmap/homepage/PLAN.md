# Homepage v0 Plan

Status: planning, 2026-09-07.

Each night Otto searches the web for things that matter to the owner, and each morning Home lists what it found so the owner can agree or disagree with one click. Without it, Home only mirrors the other modules and the owner has to go looking for news, research and legislation by hand.

## Sources

| Source | Governs |
|---|---|
| `docs/ARCHITECTURE.md` › Home page, Nightly Process | Requirement: nightly capped search, results queued on Home, a record per agree / disagree |
| `docs/ARCHITECTURE.md` › Daemon, Mechanisms, Claude, Config, Module contract | Scheduled work reads through `ctx.run_task`; the one write path `ctx.commit`; `[nightly]` budget; every knob in `config.toml` |
| `docs/ARCHITECTURE.md` › UI frame contract | Home hue `#e6e7ea`, order 0, LEFT groups, item inspector, rows, buttons |
| `docs/design/Personal Dashboard App.dc.html` lines 49–75, 201–210 | Home LEFT (a group per module with a count and `+N`), MIDDLE blank (number grid with a module icon per number) |
| `app/modules/home/{__init__.py, routes.py, agent.md}`, `app/static/pages/home.js` | What Home does today: numbers, today rows, tool-less agent |
| `app/modules/memory/{tasks.py, tools.py, routes.py}` | The built pattern for an LLM task, a cursor, and action routes |
| `app/claude.py`, `app/runner.py`, `app/config.py`, `app/scheduler.py` | `run_task` flags and budget, `JobContext`, typed config, nightly window |
| `docs/gaps/nightly-search-not-built.md` | The gap this item closes |
| `docs/bugs/budget-refusal-marks-job-failed.md` | Known: a budget refusal shows as a failed job; not fixed here |

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | The search lives in the `home` module (`app/modules/home/tasks.py`), not a separate module | ARCHITECTURE files the Nightly Process under Home; the queue and its number are Home's, and one module means one resource lock and one rail entry |
| 2 | One scheduled task `home.search`, every 24h, resource `home`, `llm=True` | The scheduler already confines LLM tasks to `[nightly] window` and `max_sessions`; nothing new caps anything |
| 3 | Search uses the CLI's built-in `WebSearch` / `WebFetch` inside `run_task`; no MCP tools, no search API | Both are already in `READ_BUILTINS`; verified today that a headless run performs a search under the Max login with extra usage disabled, so no other charge is possible |
| 4 | Topics and the nightly result cap are boot values: `[home] topics`, `[home] results_per_night` in `config.toml` | The owner's interests are a knob, never a literal in a prompt; the Settings page edits `ui.*` only, and a relaunch to change interests is acceptable at v0 |
| 5 | A finding is one row in `findings`; agree / disagree writes `decision` and `decided_at` on that row and an `events` row | "Creates a record once agreed/disagreed with" is satisfied by the decided row itself; no second table, no copy into Memory |
| 6 | `url` is unique; the prompt lists pending and decided URLs and titles so a night never repeats one | Idempotent and kill-safe: a re-run inserts nothing new; the owner never reviews the same page twice |
| 7 | Decided findings feed the next prompt as feedback (last thirty titles with their decision) | Makes the click do work: the search leans toward what the owner agreed with, away from what they disagreed with |
| 8 | Queue in LEFT as the first group `Review`, all pending rows, newest first; decided rows leave the queue; the item inspector carries `Open`, `Agree`, `Disagree` | The queue is bounded by `results_per_night` × days unreviewed, so no paging; the inspector is the shell's existing selection surface |
| 9 | Home reports its own number, `to review`, first in the grid | The grid is the blank state the owner lands on; the queue size is the one Home number that changes daily |
| 10 | The Home agent stays tool-less; pending findings are added to its Current state block | The agent already answers from that block; a tool would add a server registration for what a paragraph of context gives |

Rejected: deriving topics from Memory contents (nothing to derive from yet, and non-repeatable); a separate `web_search` module (splits one requirement across two rail entries); live-edited topics in the `settings` table (needs a Settings section that does not exist); an Agree that also writes a Memory (two records for one click); follow-up scheduling (a later item, see Pending decisions).

## Layout

| File | Change |
|---|---|
| `config.toml` | add `[home] topics = [...]`, `results_per_night = <int>` |
| `app/config.py` | `Home(topics: tuple[str, ...], results_per_night: int)` on `Config`; required like every section |
| `app/modules/home/__init__.py` | add `schedules=(Schedule(task="search", every="24h", resource="home", llm=True),)` |
| `app/modules/home/schema.sql` | new: `findings` |
| `app/modules/home/tasks.py` | new: `async def search(ctx)` |
| `app/modules/home/routes.py` | `left` gains the `Review` group; new `item/{id}`, `action/{agree, disagree}`; hooks `numbers`, `item`; `context` gains pending findings; `numbers_route` includes Home first |
| `app/modules/home/agent.md` | one paragraph on the review queue |
| `app/static/pages/home.js` | render the `Review` group; clear selection after `agree` / `disagree` |
| `tests/test_app.py` | `test_home_search_task`, `test_home_review_end_to_end` |
| `docs/gaps/nightly-search-not-built.md` | delete when merged (`/sync-architecture` records the rest) |

## Contract

| Field | Value |
|---|---|
| Manifest | `name="home"`, `title="Home"`, `hue="#e6e7ea"`, icon unchanged (artboard diamond), `order=0`, `page=True` |
| Schedule | `home.search`, every `24h`, resource `home`, `llm=True`; due only inside `[nightly] window`, one run per night, counted against `max_sessions` |
| Agent | `placeholder="Ask about today…"`, skills `today`, `where-to-look`; no tools |

Routes (all under `/api/home`):

| Route | Wire shape |
|---|---|
| `GET left` | `{groups: [{module:"home", label:"Review", hue, icon, count, rows:[{id, module:"home", text: title, stamp: found_at, leading:{dot: hue}}], more: 0}, ...per-module groups as today]}`; the `Review` group is present only when something is pending |
| `GET numbers` | `[{module:"home", hue, icon, value: pending count, label:"to review"}, ...per-module numbers as today]` |
| `GET item/{id}` | `{id, module:"home", kind: topic, created_at: found_at, text: "<title>\n\n<summary>\n<url>", url, decision, actions:[{verb:"open", label:"Open", href}, {verb:"agree", label:"Agree", primary:true}, {verb:"disagree", label:"Disagree"}]}`; a decided finding returns no `agree` / `disagree` actions |
| `POST action/agree`, `POST action/disagree` | body `{id}` → `{id, decision}` through `runner.run_action("home.<verb>", "home", "home", fn)`; 404 unknown id, 409 already decided |

Hooks: `numbers(store)` → `{value: pending, label: "to review"}`; `item(store, id)` as above; `context(store, registry)` → the existing per-module lines plus `Review: N pending` and one line per pending finding `(id) title — url`; no `today` hook (Home does not list itself).

Agent's job: see the day at a glance from the Current state block, including what the nightly search queued; say which finding is worth opening and why, in the owner's terms; never claim to agree or disagree on the owner's behalf, since it has no tool to do so.

Departures from the artboard: the `Review` group and its rows are not in the artboard; they reuse the artboard's module-group header, 36px rows with a 6px dot, and the inspector's primary / secondary buttons. Home's own `to review` number is added to the grid, which the artboard shows only for other modules.

## Data

`app/modules/home/schema.sql`:

| Table | Columns |
|---|---|
| `findings` | `id INTEGER PK`, `found_at TEXT NOT NULL`, `topic TEXT NOT NULL`, `title TEXT NOT NULL`, `url TEXT NOT NULL UNIQUE`, `summary TEXT NOT NULL`, `decision TEXT CHECK (decision IN ('agree','disagree'))`, `decided_at TEXT`, `job_id INTEGER`; index on `(decision, found_at)` |

| Cursor | Value |
|---|---|
| `home.search` | `now_iso()` of the last committed search; written in the same transaction as the inserts |

`search(ctx)`: `Skipped("no topics")` when `config.home.topics` is empty. Prompt: the topics, `results_per_night` as the ceiling, every pending URL and the last thirty decided titles with their decision as "never repeat / lean toward / lean away", and the reply format `[{"topic", "title", "url", "summary"}]` (summary: two sentences, why it matters to the owner). `ctx.run_task(prompt)` with no MCP tools; `WebSearch` and `WebFetch` are the built-ins. Parse the JSON array (same tolerant parser as Memory), then one `ctx.commit(cursor=("home.search", now_iso()))` with `INSERT OR IGNORE` per item. Return `"N new finding(s) from M proposed"`.

| Client | Who receives it | Test |
|---|---|---|
| Read: the CLI on the `otto-read` server with `--no-session-persistence` and the nightly turn cap | `home.search` through `ctx.run_task` only | `test_home_search_task` asserts the spawned args name `otto-read` and carry `--no-session-persistence`; `test_tasks_never_reach_interactive_claude` already proves a task context cannot reach `session_turn` |
| Write: `ctx.commit` on `findings` | `search` (inserts) and `action/agree`, `action/disagree` (decisions) through `run_action` | `test_home_review_end_to_end` decides through the route; no other code path sets `decision` |

There is no external write client: nothing in this item writes outside `otto.db`.

## Phases

| Phase | Builds | Usable result |
|---|---|---|
| 1 | `[home]` config, `findings`, `home.search`, `Review` group in LEFT, `item` with `Open` / `Agree` / `Disagree`, action routes, events, tests | The morning after the first nightly window, Home lists what was found; the owner opens, agrees or disagrees, and the row leaves the queue; Activity shows the run and each decision |
| 2 | `to review` number first in the grid, pending findings in the agent's Current state block, decided titles as feedback in the prompt | The grid shows the queue size on arrival; the Home agent can say what is waiting and which finding is worth opening; the next night's search leans on the owner's decisions |

## Tests

- `test_home_search_task`: fake spawn returning a `result` line with a two-element JSON array; run the task through the runner; two `findings` rows, cursor `home.search` set, args contain `otto-read` and `--no-session-persistence`; run again with the same reply: zero new rows; with `topics=()`: job status `skipped`.
- `test_home_review_end_to_end`: insert two findings; `GET /api/home/left` first group is `Review` with count 2 and `numbers[0]` is `to review` 2; `GET item/{id}` carries `open`, `agree`, `disagree`; `POST action/agree` sets the decision, writes an `agreed` event, and the row leaves `left`; a second `agree` returns 409; `context` names the remaining pending finding.
- The suite stays offline: `app.claude.spawn` is replaced by `conftest.no_real_claude` and the fake.

## Manifest

Present

| Item | Version / location | Needed for |
|---|---|---|
| Python | 3.14.7, `.venv/Scripts/python.exe` | everything |
| fastapi, uvicorn, mcp, httpx, pytest | 0.141.1, 0.52.4, 2.2.0, 0.28.1, 9.1.1 installed in `.venv` (`pip list`, today) | routes, runner, tests |
| SQLite | 3.50.4 via `sqlite3` | `findings` |
| Claude Code CLI | 2.1.263 at `C:/Users/gudo/.local/bin/claude.exe`, claude.ai Max login | `home.search` |
| Headless WebSearch | verified today from `data/workspace`: `claude -p --restricted --tools WebSearch --allowedTools WebSearch --permission-prompts none --max-turns 4 --no-session-persistence` returned a searched result, `webSearchRequests: 1`, `fast_mode_disabled_reason: extra_usage_disabled` (no paid extra usage possible) | decision 3 |

Missing

| Package | Version | Needed for | Install target |
|---|---|---|---|
| none | | | |

Needs you

| Item | How |
|---|---|
| `[home] topics` | The list of interests the search should cover, in your words, one string each (sectors, legislation areas, research fields, learning topics); it goes into `config.toml` and nothing runs without it |
| `[home] results_per_night` | One integer; ARCHITECTURE's example is 3 |

Verify

| Check | Command |
|---|---|
| Task row exists and is armed for the window after the first launch | `.venv/Scripts/python.exe -c "import sqlite3; print(sqlite3.connect('data/otto.db').execute(\"SELECT name, next_run, enabled FROM tasks WHERE name='home.search'\").fetchall())"` |
| First night produced rows | `.venv/Scripts/python.exe -c "import sqlite3; print(sqlite3.connect('data/otto.db').execute('SELECT found_at, topic, title FROM findings ORDER BY id DESC LIMIT 5').fetchall())"` |
| Budget line on Activity counts the run | open Activity after the window; `runs used` includes `home.search` |

## Worktree

```
git worktree add ../otto-homepage -b homepage
```

Work in `../otto-homepage`. When `homepage` is merged to `main`, run `/sync-architecture`.

## Pending decisions

1. Topics: what goes in `[home] topics`? Phase 1 cannot run without the list.
2. Follow-ups (Nightly Process bullets 1 and 2, "schedule them for the future") are left out of v0. Confirm they are a later item, or name them for v0 and this plan grows a `follow_up_on` date on `findings` and a due-follow-ups block in the prompt.
