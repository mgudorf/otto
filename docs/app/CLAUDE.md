# App

## Summary

Dashboard wherein each module has a "left/middle/right" structure. The left hand side is almost always an index of information which can be selected; files, emails, tables/schema, etc.
The middle is the main interaction/use of the module, which displays the main outputs or selections. The right hand side is always an agentic window, typically used for module specific agents actions. Multiple conversations should be spawnable/selectable via tabs; whenever a session closes, the agent should 1. tag the conversation with high level metadata identifiers and then persist in a place reachable by Graph module 

### What runs today

Otto is a Python 3.14 daemon plus a disposable browser window. The daemon keeps every module's state current on a schedule; the window renders that state and holds none of it. Each module pane holds any number of open sessions, one tab each; closing a tab tags its session and ends it. Chat keeps as many conversations as the owner starts, each tagged after its first turn and never closed. Each module is described in `docs/<module>/CLAUDE.md`; this file, `docs/app/CLAUDE.md`, is the platform's. Open findings live in each doc's `## Patches` section.

| Piece | What it is |
|---|---|
| Daemon | FastAPI + uvicorn on `127.0.0.1:8765`, started detached under `pythonw`, logging to `data/daemon.log` (rotated at 1 MB, three kept); loopback only, no authentication |
| Window | Google Chrome in app mode on its own profile in `app/.chrome-profile/`, first-run, default-browser and sync prompts off; its title bar and taskbar button show the Otto icon, which Chrome takes from the shell's favicon `app/static/otto.ico`. The app never touches Microsoft Edge |
| Store | one SQLite file `data/otto.db` in WAL mode, platform and module tables together, every table named `<module>_<name>` (`app_` for the platform), timestamps as UTC ISO strings. At boot, before any schema runs, `app/migrate.py` renames an older database's tables to the current names: a backup into `data/backups/` first, then one transaction, refused when a new name already holds a table with rows. After the schemas, `MODULE_RENAMES` rewrites the rows that still name a module by an old name, behind its own backup (`tests/test_migrate.py`) |
| LLM | the Claude Code CLI (2.1.263) headless under the owner's claude.ai Max login; no API key exists anywhere in the app |
| Frontend | static ES modules and one stylesheet, no framework: `core.js` renders every page from its config, `styles.css` is the approved design and `fonts.css` declares the vendored PP Formula, PT Serif and Geist Mono cuts. marked, KaTeX and highlight.js are vendored for markdown, LaTeX and code; no build step, no Node, nothing fetched from the network at runtime |
| Modules built | Home, Chat, Email, Education, Second Brain, Science, Newsfeed, Finance, Graph, Database have pages; System and Feedback have none. The rail shows only modules whose package exists and that declare a page |

Run: `Otto.exe` at the repo root, tracked in git, is how Otto is opened: it runs `.venv/Scripts/python.exe -m app` from its own directory with no console, which checks the port and code revision, starts or restarts the daemon, then opens the window; a failed launch's output shows in a box. A pinned `Otto.exe` and the open window are two taskbar buttons, since the window carries Chrome's app identity. `python -m app setup` registers the Windows Task Scheduler entry `Otto` that starts the daemon at logon. `python -m app build` derives `app/static/otto.ico` from `otto.png` and recompiles `Otto.exe`; both are committed, so it runs only after the logo or the launcher source changes. `python -m app status` prints health. `python -m app.modules.email.gmail consent` runs the Gmail OAuth flow once and writes the token file. Tests: `.venv/Scripts/python.exe -m pytest -q`, offline; the CLI is mocked at `app.claude.spawn` and a real invocation raises; no Jupyter kernel is started.

```
app/__main__.py   launcher: open | setup | build | status | daemon
app/build.py      otto.png -> app/static/otto.ico (the window's icon) -> Otto.exe (the launcher under it): PowerShell with System.Drawing scales the logo, the .NET Framework C# compiler builds the exe
app/daemon.py     app factory, lifespan, detached start, port wait, restart
app/api.py        platform routes: health, restart, shell, tasks, jobs, events, settings, data, sessions; event_stream for any broadcast key
app/config.py     config.toml -> typed Config; every key required, missing keys fail at boot
app/store.py      SQLite connection, settings, cursors, events, backup;  app/schema.sql: platform tables (app_*)
app/migrate.py    RENAMES, every name a table has had, and the boot step that renames an older database's tables, backup first
app/scheduler.py  manifests -> tasks rows; submits due tasks; nightly window
app/runner.py     one queue, per-resource locks, worker count = cap, job rows and logs
app/revision.py   sha256 of app/** and config.toml, served by /health
app/claude.py     CLI spawn, event stream, read-only allowlist, nightly budget
app/modules/      registry, agent_base.md, one package per module (contract under Daemon)
app/static/       index.html, styles.css, fonts.css, otto.ico, app.js, core.js, chat.js, point.js, api.js, md.js, pages/<name>.js, vendor/
data/             otto.db, daemon.log and its rotations, secrets/, workspace/ (Science's root: chat/<id>/ and the owner's notebooks, scripts and folders), backups/, exports/; .gitignore covers data/*.log and data/*.log.*, the db, secrets, workspace, backups and exports
.claude/          skills/ (feature-flow, feedback-queue, sync-architecture, data-migration): the repo's own workflows
otto.png          the logo, the one source of otto.ico and of Otto.exe's icon
Otto.exe          tracked, rebuilt by python -m app build; runs .venv/Scripts/python.exe -m app from its own directory with no console
```

## Daemon

The daemon, stated as requirements

The server is a long-running local process; the window is a disposable client. It starts at logon, binds a fixed loopback port, and keeps running whether or not any window is open. Closing the UI never stops work.

One instance, self-restarting on code change. The launcher checks the port before starting anything. The daemon records the code revision it started from; a launch against a newer revision restarts it. That is the only restart path, and there is no manual "kill the stale server" step.

The daemon owns the clock. A scheduler inside the process submits declared tasks on fixed intervals. Modules declare their schedules in a manifest; the shell decides when they run. The user never presses a button whose only purpose is to make the system run.

Scheduled and user-triggered work share one job runner. Same queue, same per-resource locks, same concurrency cap, same logs. A background sync and a user action on the same mailbox serialize instead of colliding.

Every scheduled task is visible in one place. A single table lists each task with its interval, last run, next run, last result, and an enable toggle. Nothing can run on a schedule without appearing there, so there are no zombie tasks.

Job records are durable. Job state and logs persist to a small SQLite file, so a restart loses nothing and an overnight failure is readable the next morning.

Long-lived resources live in the daemon, never in a page. OAuth tokens and their refresh, sync cursors, and any kernel or subprocess handle belong to the process. The browser holds no credentials.

Tasks are idempotent and kill-safe. Every task must be safe to run twice and safe to die mid-run: write results in one transaction, advance cursors only after the write commits, and never leave a half-state the next run cannot recover from.

The agent runs on a schedule and only reads. LLM work (annotating, summarizing, pre-generating) runs as scheduled tasks and produces state the user finds on arrival. Any write to an external system, and any deletion, is a synchronous user action from the UI. Enforce this with a read-only client handed to scheduled tasks and a writing client available only to user-action routes, checked by a test.

Failure is local. A task that raises marks its own row failed and logs the exception; it never takes the scheduler, another module, or the server down. A module that fails to load is skipped with an error, not fatal.

The UI is a view of daemon state. Pages render from the store and poll or subscribe for changes; they never compute or hold state the daemon does not have. A page opened days later shows the current state immediately, because the daemon kept it current.

### Mechanisms

| Requirement | Mechanism | Test |
|---|---|---|
| Long-running, at logon, fixed port | `python -m app setup` registers a logon task running `pythonw -m app.daemon` with the repo as working directory, no time limit, restart on failure; `[server]` in `config.toml` | — |
| One instance, restart on code change | `/health` returns `rev`, a sha256 of `app/**` and `config.toml`. The launcher compares it with the working tree; on mismatch it posts `/admin/restart`: the daemon drains running jobs up to `drain_seconds`, spawns a detached replacement, exits; the replacement waits for the port to free. Direct starts wait the same way and give up if the port stays busy | `test_revision_changes_with_content` |
| Daemon owns the clock | `Scheduler.sync_tasks` turns manifest schedules into `app_tasks` rows and deletes rows no manifest declares; `tick` every `tick_seconds` submits enabled tasks whose `next_run` passed. LLM tasks become due only inside `[nightly] window` and are re-armed for the next window start; only one goes per `stagger_minutes`, the rest stay due for a later tick, so two nightly runs never overlap | `test_sync_creates_rows_and_removes_orphans`, `test_tick_submits_due_and_advances`, `test_window_logic`, `test_nightly_runs_are_staggered` |
| One job runner | `Runner`: one queue, `max_concurrent` workers, one lock per `resource`, an `app_jobs` row per job (`scheduled`, `action`, `session`) with `app_job_logs`. Routes run user actions through `run_action` and await the result, or `submit` and return the job id when the page streams the outcome. Rows left `queued` or `running` by a crash are marked failed at start | `test_same_resource_serializes_and_different_overlap`, `test_cap_holds` |
| Every scheduled task visible | `app_tasks(name, module, interval_seconds, resource, llm, enabled, last_run, next_run, last_status, last_result)`; Activity renders it with the toggle (`POST /api/tasks/{name}`), and shows `module off` where the module's own switch holds it | `test_disabled_and_missing_module` |
| The owner decides what runs | `modules.<name>.scheduled`, one switch per module on Settings, held by `Scheduler.runs`: every task of a module switched off stays due and goes the tick after it is switched back on. Seeded true once at boot; nothing but the owner ever writes it | `test_module_switch_holds_every_task` |
| Durable job records | SQLite WAL; jobs, logs, events, sessions survive restarts; nothing is replayed | `test_skipped_and_logs_and_commit` |
| Resources in the daemon | tokens under `data/secrets/`, cursors in `app_cursors`, Claude runs as child processes of the daemon, Jupyter kernels as child processes held in Science's module state and shut down at lifespan exit; the page holds nothing | `test_science_reap` |
| Idempotent, kill-safe tasks | a task's only write path is `ctx.commit(cursor=...)`: results and the new cursor in one transaction | `test_skipped_and_logs_and_commit` |
| Scheduled agent only reads | `ctx.run_task` is the only Claude entry point a task can reach: read server, read-only built-ins, budget. `session_turn` and `oneshot` are reachable from routes only. Science's `reap` names neither `execute` nor `write`; its `due` task runs the files the owner scheduled on the page, on purpose | `test_tasks_never_reach_interactive_claude`, `test_read_builtins_exclude_writers`, `test_science_reap_never_executes_or_writes` |
| Failure is local, and says why | the runner catches per job: a `BudgetExceeded` from `run_task` records the job `skipped` with the reason, whichever task raised it; any other exception fails the job: the `app_jobs` row is failed with the full traceback in `error`, the `app_events` row reads `<task>: <exception type and message folded to one line>`, and a scheduled task's `last_result` holds the last 500 characters of the traceback, so a multi-line message keeps its reason. The registry records a module that fails to import or whose `setup` raises in `app_module_errors`, and the rail shows it disabled with the error | `test_failure_is_local`, `test_budget_refusal_is_skipped`, `test_registry_skips_broken_module` |
| UI is a view | pages fetch `/api/...` on the refresh interval and after every action; the loading line reflects in-flight fetches; the session pane and a running notebook cell subscribe to server-sent events. Static files go out with `Cache-Control: no-cache`, so the browser revalidates every module against its etag, and the shell reloads the window once when `/api/shell` reports a `rev` other than the one it loaded under | `test_second_brain_end_to_end`, `test_science_run_streams_and_saves` |

### Config

`config.toml` holds boot values; changing one means relaunching. Live settings are seeded from `[ui]` into the `app_settings` table on first start (`INSERT OR IGNORE`, so a new key reaches an old database on the next boot) and edited on the Settings page afterwards (`PUT /api/settings`, keys `ui.*`, `modules.<name>.enabled`, `modules.<name>.scheduled`, `modules.<name>.model` and `modules.<name>.effort`; a value outside its range is a 400: refresh 5 to 3600 s, rows per page 10 to 200, model and effort `default` or one of `claude.models` / `claude.efforts`). `enabled` and `scheduled` are seeded true; `model` and `effort` are absent until the owner picks one, which reads as `default`.

| Section | Keys |
|---|---|
| server | host, port |
| scheduler | tick_seconds, max_concurrent, drain_seconds |
| claude | binary, model (`default` keeps the CLI's own choice; a module's own pick overrides it), models and efforts (what a module may pick on its page, besides `default`), sessions_kept_days |
| data | db, workspace (working directory of every Claude run; file tools are confined to it) |
| nightly | window (local time), max_sessions per day (at least one per nightly LLM task), max_turns and max_minutes per run, stagger_minutes between one nightly run and the next |
| chat | upload_max_mb (an attachment past it is a 413), replay_chars (tail of the stored transcript replayed when the CLI has lost a conversation) |
| second_brain | suggest_lookback_days, suggest_max |
| science | python (the interpreter every kernel and script runs on), root (the workspace itself: the tree LEFT shows, created at boot), idle_minutes, tool_output_chars |
| education | per_night, start_difficulty, flow_low, flow_high |
| database | max_rows, max_seconds |
| email | client_file, token_file, backfill_days, triage_batch |
| newsfeed | items_per_run (entries a search may add per run when the agent set no cap on it) |
| feedback | max_turns |
| ui | start_page, refresh_seconds, time_format (`24h` or `12h`), page_size |

### Claude

Every run is one CLI process with the prompt on stdin and `--output-format stream-json --verbose`, launched with `--setting-sources ""`, `--restricted`, `--strict-mcp-config`, `--permission-prompts none`, `--tools` with the read built-ins `Read,Grep,Glob,WebSearch,WebFetch` (a session turn adds the module agent's `builtins`: `Write` and `Edit` for Chat and Science, confined to the workspace by `--restricted`), `--allowedTools` for those plus the module's MCP tools, `--system-prompt`, then `--model` and `--effort` when the module's own settings (or, for the model, `claude.model`) say something other than `default`. The environment is scrubbed of every `ANTHROPIC_*`, `CLAUDECODE*` and `CLAUDE_CODE_*` variable. Stdout is read in 64 KiB chunks and split on newlines by the daemon itself, so one message carrying a whole file as a tool result never truncates the run. Any run past `max_minutes` is killed. Verified on this machine: the CLI answers with no API key set, WebSearch works headless under these flags, and the owner's global CLAUDE.md does not reach these runs.

| Path | Who | MCP server | Extra flags |
|---|---|---|---|
| `run_task` | scheduled tasks via `ctx.run_task` | `otto-read` at `/mcp/read`: read tools only | `--max-turns <nightly.max_turns> --no-session-persistence`; raises `BudgetExceeded` outside the window or past `max_sessions` |
| `session_turn` | session routes | `otto` at `/mcp/full`: read and write tools | `--session-id` on the first turn, `--resume` after, `--include-partial-messages` always; `--tools` is the read set plus the agent's `builtins` |
| `oneshot` | session tagging, Feedback filing, Education's `Generate` | `otto-read` | `--no-session-persistence`, the caller's `--max-turns` (2 by default, `feedback.max_turns` for a filing) and only the tools the caller names; not counted against the budget |

System prompt: `app/modules/agent_base.md` (shared rules) + the module's `agent.md` + a Current state block from the module's `context(store, registry)` hook, rendered fresh every turn.

Budget: when a task run starts, `app_llm_runs` rows of the local day with `budgeted = 1` and status `running`, `done` or `failed` are counted against `max_sessions`; the run then writes its own `running` row before the CLI spawns and updates it to `done` or `failed` after, so concurrent runs see each other; a refusal writes a `skipped` row and the runner records the job `skipped`. Activity shows runs used, the window, and whether it is open now.

Sessions: `app_sessions(id, module, opened_at, closed_at, title, tags, cli_started)` and `app_session_turns(role user|model|tool|system, text, tool, status)`. Four helpers in `api.py` are the only paths:

| Helper | What it does |
|---|---|
| `new_session(store, module)` | opens one |
| `pane_turn(st, mod, text, prompt)` | a module route's turn of the pane (Education's answer): the module's newest open tab, or a new one when none is open, gets `text` shown as the owner's turn and `prompt` sent to the CLI |
| `start_turn(st, mod, sid, started, text, prompt, key, replay, on_done)` | stores the owner's words (`text`), marks the session busy (a count of queued and running turns per session id; `idle` goes out at zero) and queues a `session` job on resource `session:<sid>` with `prompt` for the CLI, so one session's turns serialize and different sessions run concurrently |
| `tag_session(st, mod, sid, key, close)` | queues a `oneshot` whose `{"title", "tags"}` is written to the row (fallback: first user line, no tags), sets `closed_at` only when `close` is true, then event `closed` or `tagged` and a `tagged` broadcast; Graph reads `app_sessions.tags` |

| Route | What it does |
|---|---|
| `GET /api/session/<module>` | the module's open sessions, oldest first, each labelled with its title once tagged, until then its first user line |
| `GET /api/session/<module>/<id>` | one session with its turns and busy state |
| `POST /api/session/<module>/send` | `{text, id?}`: no `id` opens a new session; an unknown or closed one is a 404. `/clear` with an `id` tags and closes that one; any other message starting with `/` goes to the CLI unchanged, so Claude Code commands and skills work from the pane |
| `GET /api/session/<module>/<id>/events` | the stream on key `<module>:<id>`: `user`, `model`, `delta` (text as it is written, never stored; the panes ignore it), `tool`, `tool_result`, `result`, `error`, `idle`, `tagged` |

Chat keeps many sessions on its own page, streams on `chat:<id>`, and tags after the first completed turn without closing. A first turn that fails retires its session row so the next turn starts clean. A resumed turn the CLI answers with `error_during_execution`, no turns and stderr `No conversation found with session ID` (`ClaudeError.lost_transcript`) is re-sent under the same id as a new session, with the caller's `replay` preamble when one was given, after a `system` turn `resumed from Otto's record`.

MCP servers are `mcp` 2.2.0 `MCPServer` instances mounted stateless with JSON responses; module `tools.py` files register read tools on both servers and write tools on `otto` only.

### Module contract

A module is a package `app/modules/<name>/` plus `app/static/pages/<name>.js`. The registry imports every package; one that raises is recorded in `app_module_errors` and skipped.

| File | Obligation |
|---|---|
| `__init__.py` | `MANIFEST = Manifest(name, title, hue, icon (SVG inner markup, 20x20), order, schedules=(Schedule(task, every "60s\|15m\|24h", resource, llm),), agent=Agent(placeholder, skills, read_tools, write_tools, builtins), page=True)`; `builtins` are CLI tools beyond the read set, given to session turns only. A module with `page=False` (System, Feedback) is still listed by `/api/shell` with `page: false` so its hue and icon resolve, read by Home's hooks, and keeps its `runs`, `model` and `effort` on Settings > Modules, since it has no page to hold them. Optionally `setup(config)`, called once at build after every schema is applied (a raise records the module in `app_module_errors` and drops it), and `async shutdown()`, awaited at lifespan exit after the drain, for a module holding process resources |
| `schema.sql` | the module's tables, every one named `<module>_<name>` and every index and trigger after its table (`test_tables_are_named_after_their_module`), applied at boot (optional; `Store.migrate` only creates, so a column added to or renamed on an existing table is the module's `setup` to do, a table that changes its name is a line in `app/migrate.py` `RENAMES`, and a module that changes its name a line in `MODULE_RENAMES`) |
| `tasks.py` | `async def <task>(ctx)` per schedule; `ctx.store` (read), `ctx.commit(cursor=...)` (the only write), `ctx.log`, `ctx.event`, `ctx.run_task(prompt, tools)`; return a string, or `Skipped("why")`; a `BudgetExceeded` out of `run_task` needs no catch, the runner records it as skipped |
| `routes.py` | `router = APIRouter(prefix="/api/<name>")` with `GET left`, `GET item/{id}`, `POST action/{verb}` (through `runner.run_action`), plus hooks `numbers(store) -> {value, label}`, `today(store) -> rows`, `queue(store) -> rows` (everything still waiting on the owner; Home lists every one), `item(store, id)`, `context(store, registry) -> str`. Route handlers must not share a hook's name. Each action `item` offers is `{verb, label, primary?, confirm?, href?, removes?}`: without an `href` the verb must be a key of the module's own action table, since Home posts it verbatim with `{id}`, and `removes: true` says the row leaves the list, which is how a page and Home know to close the inspector standing on it. `tests/test_platform.py::test_item_verbs_are_routes_the_module_serves` walks every module's action literals against its table |
| `tools.py` | `register(read, full, store, config)`: read tools on both servers, write tools on `full` |
| `agent.md` | the agent's job in the owner's terms |
| `pages/<name>.js` | one default-exported config — `load()`, `cols`, `colsSplit`, `chips`, `seg`, `filter`, `groups`, `cells`, `rowClass`, and optionally `tools`, `summary`, `above`, `alt`, `detail` — which `core.js` renders. The shell owns the rail, the header, the search bar, the keyboard, the drawer and the list and detail frame; a page owns what is in a row and in the pane. See `## UI` |

Wire shape for LEFT: `{groups: [{label, count, rows: [ROW]}], meta?, more?}`, where a ROW is `{id, module, title, when, tags, fixed, …extras}` and the extras are exactly the fields that module's `cells()` and `detail()` read. `when` is the owner's wall clock, so the page groups by their day and prints their time; the client decides whether a row shows a date, a time or nothing. `rows(store, limit)` returns the same ROWs for the cross-module routes. External systems follow one pattern: tasks get a read client, action routes get a write client, and a test proves the split.

**Dismissed and deleted rows leave every list.** A row the owner dismisses (a Newsfeed entry, a Second Brain suggestion) or deletes (an Education question) is gone from the module's LEFT, from `today`, from `queue` and from the agent's `context`, and its item offers no verb but a link. The row stays in its table, which is what stops a scout or generator producing it a second time: each of those prompts lists what is already recorded and says a dismissed one shows what to stop bringing. `done` on a row is for a state the owner reached, not one they refused: a completed Second Brain task and an ended Finance entry stay listed, struck through.

### Platform tables

`app_tasks`, `app_jobs`, `app_job_logs`, `app_settings` (JSON values), `app_cursors`, `app_events(ts, module, verb, text, job_id, ref)`, `app_sessions`, `app_session_turns`, `app_module_errors`, `app_llm_runs(ts, module, task, job_id, status running|done|failed|skipped, minutes, session_id, budgeted)`. The prefix is the module's name, `app` for the platform; the Database page groups tables by it, and `app/migrate.py` `RENAMES` carries every name a table has had, `MODULE_RENAMES` every name a module has had.

### Dependencies

| Item | Version / location |
|---|---|
| Python | 3.14.7, `.venv` from the user-wide install at `C:\Users\gudo\AppData\Local\Python\pythoncore-3.14-64\python.exe`, which is also `science.python` |
| fastapi, uvicorn, mcp, httpx, pytest, jupyter_client, nbformat, python-multipart | 0.141.1, 0.52.4, 2.2.0, 0.28.1, 9.1.1, 8.10.0, 5.11.1, 0.0.32 (`requirements.txt`) |
| ipykernel | 7.3.0 in the user-wide Python; the kernel process Science launches |
| Claude Code CLI | 2.1.263 at `C:\Users\gudo\.local\bin\claude.exe`, claude.ai login, subscription max |
| Google Chrome | found through the `App Paths\chrome.exe` registry key |
| Windows PowerShell 5.1 with System.Drawing, .NET Framework C# compiler | ship with Windows; `python -m app build` scales the logo and compiles `Otto.exe` with them (`%SystemRoot%\Microsoft.NET\Framework64\v4.0.30319\csc.exe`) |
| SQLite with FTS5 and JSON | 3.50.4, stdlib |
| Vendored frontend | `app/static/vendor/`: marked.esm.js 18.0.12, katex/ 0.18.7 (module, stylesheet, 20 woff2 fonts), highlight/ 11.11.1 (core and the python grammar, ES builds), and under `fonts/` the 16 PP Formula cuts, the 4 PT Serif cuts and Geist Mono 400/500, all pinned by `SHA256SUMS`. preact.mjs, htm.mjs, Inter and JetBrains Mono are left from the shell this replaced and nothing imports them |
| Google OAuth client and token | `data/secrets/google_client.json` (web client, redirect `http://localhost:8756/m/email/api/oauth/callback`), `data/secrets/token.json`, scope `gmail.modify`, refreshed in place |

Not used: Node, APScheduler, pywebview, PyInstaller, `claude-agent-sdk`, nbclient, an Anthropic API key, paid search APIs, a graph database, Microsoft Edge.

## Modules

One doc per module, `docs/<module>/CLAUDE.md`: the owner's requirements, `## Built` and `## Patches`. The platform (`app/`) is this file. Rail order in brackets; a module without a page has no rail entry.

| Module | Doc |
|---|---|
| Home [0] | `docs/home/CLAUDE.md` |
| Chat [1] | `docs/chat/CLAUDE.md` |
| Email [1] | `docs/email/CLAUDE.md` |
| Education [2] | `docs/education/CLAUDE.md` |
| Second Brain [3] | `docs/second_brain/CLAUDE.md` |
| Science [4] | `docs/science/CLAUDE.md` |
| Finance [5] | `docs/finance/CLAUDE.md` |
| Newsfeed [6] | `docs/newsfeed/CLAUDE.md` |
| Graph [7] | `docs/graph/CLAUDE.md` |
| Database [8] | `docs/database/CLAUDE.md` |
| System [99, no page] | `docs/system/CLAUDE.md` |
| Feedback [99, no page] | `docs/feedback/CLAUDE.md` |

## UI

The window is the shell the owner approved as `docs/design/otto-next.html`, built into the app: one dense list per module with a detail pane beside it, tags on every row and cross-module tag pages, a search bar whose tokens narrow every list, a command palette that also holds the agent's skills, the agent as a collapsible drawer, a point-at-anything mode, and Graph as a map of every tag whose selection is those search tokens. It is plain ES modules and one stylesheet: no framework, no build step, nothing fetched from the network at runtime.

### Frame contract

`.app` is one CSS grid. Nothing floats over the page.

| Region | Spec |
|---|---|
| Grid | `var(--navw) minmax(0,1fr) var(--chatw)` under a `var(--toph)` header row: rail 248px (56px collapsed with `[`), main, drawer 400px (`]` closes it). The drawer is a grid column at every window width, never a sheet over the page; when the window narrows the page's plates ask for less and, if it is still squeezed, main scrolls sideways rather than hide under it |
| Grips | the gutter left of the drawer and left of the detail pane drag, with nothing drawn for them, and write `--chatw` / `--listw` to `localStorage`. The drawer is capped so main keeps room for its plates: 840px split (660 at ≤1280), 520 unsplit; the cap is re-applied on load, on resize and on every render |
| Header | the brand, then the page's title left of the search bar and the page's own controls right of it (so a page's summary is the first row of main and its plates start level with the drawer's), then the daemon's pulse and six icon buttons: rail, point, palette, keys, theme, drawer |
| Search bar | tokens then a bare input, with the Quick access bookmark at its end. A token is a tag, a module, an `is:` filter or free text; `Ctrl+Space` focuses it, `Ctrl+Shift+Space` clears it, `↑ ↓ ↵` take a suggestion. Tokens narrow every list, including Home in both its modes, and the tag tokens are Graph's selection |
| Rail | module entries in manifest order, a thin rule, then Quick access, and Activity and Settings at the foot. No headings, no counts. A Quick access entry that is one tag's page is marked `#`, the rest `»` |
| Main | the page's summary, then `.content`: the list, and the detail pane beside it when an item is open (`.content.split`) |
| Drawer | the open module's agent: rounded tabs on a shaded strip, one per open session, sized to the title up to 180px and cut off flat, with a `+` tab; the transcript; a composer that is a plain box like the search bar, with what is being discussed as a token inside it and the send arrow at its edge |

| Token | Value |
|---|---|
| Themes | Rainbow and Dark, both dark, toggled in the header and kept in `otto-next-theme`. `--m` is the open module's hue; Rainbow mixes it into every surface, Dark leaves them neutral. There is no light theme |
| Colour | the module's hue on a card's left border and on a primary button (`--accent`, the hue mixed toward the ink so it is never white on dark); `--danger` tints a destructive button. Nothing else carries colour. A hovered card deepens its own tint and leaves its neighbours theirs |
| Type | PP Formula for the chrome (module names, rail, header, palette, dates and numbers), PT Serif for what is read (item titles, prose, chat, descriptors, tags, key caps, the search bar, an Education question body), Geist Mono for code. `fonts.css` declares all 22 vendored cuts with the `ascent-override` / `descent-override` that centre text on its capitals, so a glyph sits level with the icon beside it |
| Rows | `--rowh` 42px; a row's columns come from its page's `cols`, and from `colsSplit` while the detail pane is open. Five tags show on a row, then `+N` |
| Dates | `MM-DD-YYYY`, bare: a date carries no word before it, and a stamp shows the time only for something that arrived today |
| Focus | a lift off the page, not a ring, except on buttons |

### Pages

`app/static/pages/<name>.js` default-exports one config; `core.js` renders every page from it and never imports a page (`app.js` hands them over with `registerPages`).

| Field | What it is |
|---|---|
| `load()` | the page's only fetch, run on open, on every refresh and after every action; returns data and renders nothing |
| `cols`, `colsSplit` | the row's grid template, closed and split |
| `chips`, `seg` | the segment controls; one chip draws none |
| `filter`, `groups` | narrowing by chip, then the cards to draw |
| `cells`, `rowClass` | the row's contents and its state |
| `tools`, `summary`, `above`, `alt` | the header's controls, the first row of main, an editor or capture box over the list, the alternate view under `seg` |
| `detail` | the pane beside the list. Its buttons are built from the item's own `actions` (`verb`, `label`, `primary`, `confirm`, `removes`, `href`), so a page offers exactly what its module allows; a verb carrying `confirm` or `removes` is a red button and asks in a popover first |

### Tags, and what is one system

`app_tags(module, item_id, tag)` holds the owner's tags on any module's row; Second Brain keeps `second_brain_tags`, which its own tools read and write, and `app.store.tags_for` reads both, so a tag means the same thing everywhere. `GET /api/tags` lists them with their counts, `POST /api/tags/add` and `/remove` write them, and `GET /api/items?tags=a,b` returns the rows of every module carrying all of them, which is what a tag page, Home's Recent and the Graph pane show. Every tagged row reaches the graph: `app_tags` is one of its sources beside Second Brain's items and the tagged sessions. A row also carries `fixed` tags — what it is, by kind, topic or the search that found it — which look the same and cannot be edited.

### Keyboard

`?` opens the one list of keys; no control anywhere else names its own. `← →` walk the rail, the list, the open page, the chat tabs and the composer; `↑ ↓ ↵` act inside one. A plain letter fires only without a modifier, so `Ctrl+C` still copies. `j k` step rows, `x` selects one, `t` tags it, `a` asks about it, `c` opens a chat and `C` reopens the last closed one, `o` is point mode, `Alt+←` and `Alt+→` walk history, `Esc` always leaves.

### History and refresh

Every page change and every opened item is a history entry (`pushState`), so the mouse's back and forward buttons walk pages. Pages fetch on `ui.refresh_seconds` and after every action; the header's pulse reads `/health` and `/api/tasks` and says when the daemon last synced and what is running, and nothing when it reports nothing. Static files go out `Cache-Control: no-cache`, and the window reloads itself once when `/api/shell` returns a `rev` other than the one it booted under.

### Point mode

`o`, or the crosshair in the header, aims at anything: a row, a paragraph, a notebook cell, a rail entry, a Home number, the search bar, the drawer. Clicking opens a popover naming exactly what was pointed at — down to which paragraph — with four actions: Ask (the reference becomes the drawer's token), Summarize and tag (a real turn of that module's agent), Capture (a Second Brain item carrying the tags over), and Feedback (filed through the Feedback module against that reference, which is what `/feedback-queue` later prints). `Esc` leaves.

### Files

| File | What it is |
|---|---|
| `index.html` | the skeleton: header, rail, main, drawer, and the popovers, palette, key list and toast |
| `styles.css` | the design, ported from the preview; later rules override earlier ones, so changes are appended |
| `fonts.css` | the generated `@font-face` block for the cuts vendored under `vendor/fonts` |
| `core.js` | state, DOM helpers, the chrome, the search bar, Quick access, history, the keyboard, the tag popover, the palette, the key list, and the generic list and detail renderer |
| `app.js` | registers the twelve pages, the drawer and point mode, then boots |
| `chat.js` | the drawer: tabs, transcript, composer, streaming. It owns what is inside the plate; core owns the plate |
| `point.js` | aiming and the point popover |
| `pages/*.js` | one per module |
| `api.js`, `md.js` | the fetch wrappers with the in-flight count behind the loading line, and markdown with KaTeX |

### Activity and Settings

Activity is the daemon's own log: events by day, a chip per module and one for failures, the task table with its toggles, and the nightly window and how much of its run budget is used; a failed job opens its error in the pane. Settings is a grid of tiles — Otto first (general, data, app), then every module, each tile carrying its hue as a deeper tint — and a pane: for a module, its agent's model and effort and the switches that hold its page and its tasks; for Otto, the general, data and app settings and the backup, export and vacuum controls. Feedback has its own tile listing what is pending and what was cleared.

### Departures from the design preview

- The preview's header pulse reads `synced 14:20, 1 job running` as a fixed string; here it is the daemon's own last sync and running-job count, and it is empty when there is nothing to report.
- Point mode's entry toast is gone: it was a hint, and it named a key outside the `?` overlay.
- The preview's sample tags are single words; real tags are phrases, so a tag that cannot fit its row ends cleanly instead of being sliced, and a row drops its inline tags while the detail pane is open, where the open item's own tag line shows them in full.
- Settings' module pane is a list of rows, not the preview's model-and-effort table: the daemon keeps one model and one effort per module, and a table with a column head over a single row was two pieces of chrome (UI tenets 1 and 2). What the preview offered and the daemon does not keep is a patch below.
- Each module's own departures are the `Departures` row of its doc's `## Built` table.

## Patches

### Reopening a chat inside the tagging window finds it still open

- Kind: defect
- Where: `app/api.py` (`session_send` `/clear`, `session_reopen`), `app/static/chat.js` (`closeChat`, `reopenChat`)
- Found: 2026-09-20, building the agent drawer
- Status: open

What happens: closing a tab posts `/clear`, which returns as soon as the tagging one-shot is submitted; the row is closed only when that run finishes, seconds later. The drawer removes the tab at once. Pressing `C` inside that window reopens a session that was never closed: the route answers 200, the tab comes back, and then the tagger's close lands and the tab disappears again on the next sync.

Expected: reopening always returns a tab that stays, whether or not the tagger has finished.

Fix: either the drawer holds the reopen until the close settles (it already knows the session is being tagged, since `tagged` arrives on the stream), or the platform can cancel a queued close so a reopen inside the window supersedes it. The second is the smaller surface and keeps the drawer free of daemon timing.

### Home's counts strip has room for eight, and the owner has nine modules that count

- Kind: defect
- Where: `app/static/styles.css` (`.page-tools .stat-strip`, the `max-width: 1560px` rule), `app/modules/home/routes.py` `numbers_route`
- Found: 2026-09-20, measuring the header while porting the shell
- Status: open, needs a decision

What happens: nine modules report a number (Chat, Email, Education, Second Brain, Science, Finance, Newsfeed, Graph, Database). Eight are enabled today and, since the strip was tightened, all eight fit at 1600px with about 16px to spare. A ninth needs roughly 61px more than the header has. Between 1561 and 1575px the strip also borrows up to 14px of the header's right gutter, leaving as little as 2px before the first icon button; below 1560px the strip hides itself, as designed.

Expected: every count Home shows keeps its word at every width the strip is shown at, because a number without its word means nothing (UI tenet 2).

Fix: the owner's call, because the only ways out cut something the tenets protect. Either Home shows a chosen subset of counts and the rest live on their own pages, or the strip hides itself at a wider breakpoint than 1560px, or it wraps to a second header row. Nothing here should shorten a label or drop the icon.

### Feedback and System ship no mark, so their Settings tiles carry none

- Kind: gap
- Where: `app/modules/feedback/__init__.py` and `app/modules/system/__init__.py` (`MANIFEST.icon`), drawn by `app/static/pages/settings.js` (`tileGrid`)
- Found: 2026-09-20, fixing the ported Settings page
- Status: open, needs a decision

What happens: both manifests set `icon=""`. The Settings grid is the only place a page-less module is drawn, and a tile's mark is a tinted square with the module's glyph inside it, so an empty icon painted a filled box with nothing in it. The page now draws no mark when the manifest has none, which leaves those two tiles as the only ones without one.

Expected: every tile carries a mark, as every tile in the preview does.

Fix: one line in each manifest. The glyph is the owner's call: `docs/design/` is the source for a module's mark and neither module appears there. The page draws whatever the manifest gives it.

### The Otto pane has no Theme control

- Kind: gap
- Where: `app/static/core.js` (`dark`, `setTheme`, both private to the file), `app/static/pages/settings.js` (`ottoPane`)
- Found: 2026-09-20, fixing the ported Settings page
- Status: open, needs a decision

What happens: the preview's General section offered Rainbow and Dark as a segment; the ported pane has no such row. The header's theme button still switches the theme, so nothing is unreachable. The page cannot rebuild the row on its own: core keeps the theme's reader and writer to itself, and a page that read `document.documentElement.dataset.theme` and wrote the `otto-next-theme` key would be a second way of doing what core already does.

Expected: either the pane offers the theme the way the approved preview does, or the header's button is its one home and the pane is right to leave it out.

Fix: if the row comes back, core exports the pair and the pane draws the segment with them, a line each. The owner decides, because a control that is already a symbol in the header may not want a second home.

### Point mode files feedback against a Settings tile as if it were an item

- Kind: bug
- Where: `app/static/point.js` (`refOf`, `findItem`, `feedbackBox`), `app/static/core.js` (`loadItem`, the `local` row)
- Found: 2026-09-20, fixing the ported Settings page
- Status: open

What happens: a page may hand core a row that is the whole item (`local: true`), and Settings uses one per tile, so `S.item` holds a tile. Aiming point mode at the open pane takes that tile for a daemon row and posts `item: {module: "settings", id: "email"}` to `/api/feedback/action/add`; the filing agent is then told an item was selected that no module can resolve. Activity's and Graph's local rows stand for real records, so only Settings is affected.

Expected: pointing at the Settings pane files against the page, the way pointing at the toolbar or the rail does.

Fix: mark the row, not the page. A local row that stands for no record carries a flag, and `refOf` skips such a row so it falls through to the `kind: 'ui'` branch. Both files are the shell's; the row already travels through `loadItem` untouched.

### The Settings pane reaches four of Otto's settings and not the rest

- Kind: gap
- Where: `app/api.py` (`/api/shell`, `PUT /api/settings`), `app/static/pages/settings.js` (`ottoPane`, `modulePane`)
- Found: 2026-09-20, fixing the ported Settings page
- Status: open, needs a decision

What happens: `PUT /api/settings` accepts four live keys, the start page, the refresh seconds, the time format and the rows per page, plus each module's shown, runs, model and effort. The preview's pane also offered the scheduler's tick and concurrency, the nightly turn and minute caps, the agent drawer's opening state, launch at logon, app window or browser tab, a model and effort for each scheduled task and each skill, and every module's own `config.toml` knobs. None of those is a live setting: they are boot values, and `/api/shell` carries no `[module]` sections, so the pane shows nothing for them.

Expected: the settings the preview showed are either editable here or are boot values the pane is right to leave in `config.toml`.

Fix: the owner picks which ones become live. Each then needs a key `PUT /api/settings` accepts, a field on `/api/shell` and a row in the pane. A per-task or per-skill pick needs more than that: `Claude._choice` reads `modules.<name>.model|effort` only, so the runner has to look for the narrower key first.

