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
| Frontend | static ES modules, Preact + htm vendored, marked + KaTeX vendored for markdown and LaTeX in MIDDLE and in the session pane, inline styles ported from the artboard; no build step, no Node |
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
app/static/       index.html, otto.ico, shell.js, session.js, rows.js, api.js, feedback.js, module_settings.js, md.js, pages/<name>.js, vendor/
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
| `pages/<name>.js` | `load(app)`, `Left({app, data, mod, fmt})`, `Middle({app, data, mod, fmt})` and optionally `Right(...)`, which replaces the session pane, returning Preact nodes; the shell owns rail, header, tracks and the session pane; `md.js` exports `Markdown` for prose with LaTeX; `rows.js` exports the tokens, `Row`, `GroupHeader`, `Plus`, `Enter`, `DateInput` and the date helpers every page draws with |

Wire shape for LEFT: `{groups: [{label, count, rows: [{id, module, text, stamp, stampText?, leading?: {pct|task}, done?, unread?, live?}]}], chips?, chip?, more?}`. `stamp` orders a row and is never drawn (the day label above already says the day); `stampText` is drawn at the row's right edge when the row carries one (an amount, an event day); `unread: false` dims a row the owner has dealt with, `done` strikes it through, `live` sets it in the hue; a group whose `label` is `""` has no header. External systems follow one pattern: tasks get a read client, action routes get a write client, and a test proves the split.

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
| Vendored frontend | `app/static/vendor/`: preact.mjs, htm.mjs, marked.esm.js 18.0.12, katex/ 0.18.7 (module, stylesheet, 20 woff2 fonts), highlight/ 11.11.1 (core and the python grammar, ES builds), Inter 400/500/600, JetBrains Mono 400/500, pinned by `SHA256SUMS` |
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

Follows style of, but not limited to, the Claude Design project `9459ddf2-3c53-45d8-9252-7a17bd027bf4` (`Personal Dashboard App.dc.html`). The artboard and its runtime are imported to `docs/design/`; open the html in a browser to run it.

### Frame contract

Every page uses three fixed tracks. Selection swaps what renders inside MIDDLE and never moves a track.

| Region | Spec |
|---|---|
| Rail | 56px wide, 32px icon buttons (20px SVG, stroke 1.5), 6px gap, 14px top padding; active background `#23262c`; Activity and Settings pinned at the foot |
| Header | 48px, padding `14px 32px 0`, the 20px/600 title and nothing else; at the right edge two 28px icon controls: on a module page a sliders icon opens the module's settings (the `runs` toggle when it has tasks, `model` and `effort` selects, in a 280px panel), and a speech-bubble icon opens feedback on every page |
| Loading line | 1px, margin `0 32px`; a 30% `#8b8f98` bar animates `translateX(-100% to 340%)` over 1.2s while a fetch is in flight |
| Tracks | `2fr 5fr 2fr` with a `5%` column gap, padding `19px 24px 24px`: LEFT · gap · MIDDLE · gap · RIGHT are 20 · 5 · 50 · 5 · 20 of the frame's width at every window size, so a wider window widens all three and opens no ground between them; opacity fades out and in over 120ms on page switch |
| LEFT | panel `#1a1c21`, radius 6, padding `12px 8px 24px`: search (36px, `#23262c`, 1px focus ring in the hue) with `+` beside it where the page creates something, chips, groups of boxed one-line rows under an `MM-DD-YYYY` day label, `more` under a cut list; no counts anywhere |
| MIDDLE | ground, padding `8px 16px 40px`, content fills the track: the module's blank state or the item inspector, prose included (the inspector, Activity's detail, Education's question, Email's reader and Chat's conversation run the track's full width); Home's number grid holds 640px, Finance's totals strip 720px and each Settings section 560px |
| RIGHT | panel, padding `16px 12px 12px`: the session pane, identical on every page |

| Token | Value |
|---|---|
| Ground / panel / box / raised | `#101114` / `#1a1c21` / `#1e2126` (a row on its panel) / `#23262c` (selection, inputs, user bubbles) |
| Text / muted / dim | `#e6e7ea` / `#8b8f98` / `#5f636c` |
| Hairline / row hover / table row hover | `rgba(230,231,234,.08)` / `#202329` / `#16181c` |
| Hues and rail order | home `#e6e7ea` 0, chat `#d9915b` 1 (not in the artboard; speech-bubble icon; ties with email and sorts first), email `#cf7b7b` 1, education `#7a9fd6` 2, second_brain `#d1a36a` 3, science `#6fb3b8` 4, finance `#7fb894` 5 (the artboard's Money hue and banknote icon), newsfeed `#c98ba8` 6 (not in the artboard; feed-arcs icon), graph `#b3b06a` 7, database `#a68bd0` 8; System and Feedback `#8b8f98` 99 have no rail entry |
| Type | Inter everywhere: 15px/1.4 body, 13px meta, 20px/600 title, 28px/500 numbers with tabular figures; JetBrains Mono 13px for code alone (notebook cells, scripts, the SQL editor, markdown code); vendored with `system-ui` / `ui-monospace` fallbacks |
| Rows | 36px list rows, 32px compact rows, 28px group headers, padding `0 12px`, gap 12px, radius 6, 4px between rows. Every row is a box: `#1e2126` with a hairline ring, weight 500 while `unread`; transparent and `#8b8f98` once read or done (Gmail's convention, no dots); raised with a 2px hue bar at its left edge when selected; `#252830` on hover. The leading slot is a 40px progress bar or a 10px task square; nothing on a row repeats the day label above it |
| Chips / buttons | padding `3px 9px` / `5px 10px`, radius 6, 13px; active or primary is hue background with `#101114` text; inactive or secondary is `#8b8f98` text with a 1px inset ring on hover. `+` in a 28px ring is the one control for anything new (a conversation, a topic, an entry, a file or folder, a cell, a session tab), raised while the new thing is the one open; `↵` in a ring sends every composer and capture box |
| Toggle | 28x16 track, 12px knob; on `#e6e7ea` / `#101114`, off `rgba(230,231,234,.14)` / `#8b8f98` |
| Dates | `MM-DD-YYYY` everywhere (`09-12-1990` is September 12th): group labels, the inspector's line, tables and schedules; a stamp shows the time (`ui.time_format`) on the same day, else the date. A typed date is `DateInput`: digits only, the dashes placed as they come, the unfilled part of `MM-DD-YYYY` shown dim, sent as `YYYY-MM-DD` once complete |
| Markdown | `md.js`: marked with `breaks` and `gfm`, math lifted out first and rendered by KaTeX (`$…$` inline, `$$…$$` display), the `.md` rules and the KaTeX stylesheet added to the document once |
| Composer | `rows.js` `TextArea`, every composer and capture box: three lines when empty, no placeholder, grows with its text (`field-sizing: content`) to half the viewport, then scrolls; raised surface, 15px/1.5, focus ring in the hue; a capture box sits on the panel surface, the Database editor in mono. Enter sends and Shift+Enter breaks a line everywhere but the SQL editor (Ctrl+Enter) and the notebook cells (JupyterLab's keys) |

Session pane: a blank pane shows nothing but its controls. A tab strip, one tab per open session (its label, ellipsized at 140px, `…` appended while another tab's turn runs; the active tab raised), `+` for a blank tab whose first send opens the session (raised while the blank tab is the one open), and `×` at the right edge to close the active tab (sends `/clear`: the tagger names it, the tab disappears once `tagged` arrives and a blank tab opens); user turns are raised bubbles aligned right at max 85% width, model turns markdown with LaTeX through `md.js`, tool calls one 13px line `▸ tool` with the status at the right edge; the box with no placeholder, then `/` (a menu of the agent's skills; a pick puts `/name ` in the box), a pulsing hue dot while a turn runs, and `↵`; Enter sends, Shift+Enter breaks a line. The newest open tab is shown on arrival, and the strip re-lists on every shell refresh (the `tick` prop), so a turn a page action started lands in view: a blank tab follows it, another tab shows `…` on it.

Item inspector: 16px hue glyph, the item's `MM-DD-YYYY HH:MM` dim, `×` to clear, the body as markdown through `md.js`, then a primary action in the hue, secondary actions, and `Send to session` right-aligned, which prefills the composer with the item's reference; no kind is written. Email's reader keeps the glyph, time, `×` and `Send to session` and carries no actions; those sit in its LEFT bar.

### Activity and Settings

Activity: LEFT is the `events` log by day with a chip per module, each row boxed with the clock, the verb in its module's hue (red when failed) and the text, `more` under the cut; MIDDLE blank state is the task table with its toggles, one line `nightly used / max · window · every N min` (`· open` inside the window), and the last fifty jobs; selecting an event shows its module, verb and time, its text and its job's result as markdown, then the error and log. Settings: LEFT four boxed rows; General (start page among the modules with a page, refresh, time format, rows per page), Modules (every module, page or not, its title in its hue: `shown` in the rail for a module with a page, kept here because a hidden module's page cannot be reached to show it again; `runs`, `model` and `effort` read `on its page` for a module with a page and are editable here for one without; a failed module shows its error), Claude (binary, model, the models and efforts a module may pick, agents dir, workspace, sessions kept, background jobs; read-only), Data (database path and size, last backup and last export, `Back up now` through the SQLite backup API into `data/backups/`, `Export`: every table as JSON rows in one file under `data/exports/`, `Vacuum`).

### Departures from the artboard

- Activity's MIDDLE blank state is the task table, required by the Daemon section.
- Finance is the artboard's `Money` entry; the web scouting that sat in Business and Social is Newsfeed's, a module the artboard does not have.
- The rail shows only built modules with a page.
- The header carries settings and feedback icons the artboard does not have; module settings live there instead of on the Settings page.
- Each module's own departures are the `Departures` row of its doc's `## Built` table.

## Patches

### Activity lists system twice among its chips
- Kind: bug
- Where: `app/static/pages/activity.js` `load`
- Found: 2026-09-18, the UI review
- Status: open

What happens: the chip strip is built as `All`, every module the shell lists, then `system` appended; the shell now lists System as a module, so `system` appears twice and the strip wraps to a fifth line.

Expected: one `system` chip.

Fix: drop the appended `system` in `load`; the shell's module list already carries it.
### Visual system reads as generated
- Kind: roadmap
- Where: `app/static/index.html`, `app/static/rows.js` (`T`, `rowStyle`, `Row`, `Chips`, `Button`, `Plus`, `Enter`), `app/static/shell.js` (rail, header, tracks), `app/static/session.js`, `app/static/pages/settings.js` (the native select), `docs/design/Personal Dashboard App.dc.html`
- Found: 2026-09-18, the owner's request (the UI review)
- Status: open

What happens: every surface is one of four greys a few percent apart with no edge or light direction; every row is a 6px-radius box with a hairline ring on a panel of the same shape, as are chips, buttons, inputs and tabs; the dim grey `#5f636c` carries every date, stamp, group label, empty state and blank-state line at 2.8:1 against the panel; the type scale is 13/15/20 in Inter at default tracking; `+ × ↵ ▸ /` are typed characters beside drawn icons and Settings uses a native select; the rail stacks eight pastel hues; MIDDLE is one dim line on Email, Second Brain, Science, Chat and Settings and RIGHT an empty plate until a tab opens, while LEFT truncates titles to fit a full date. The owner reads this as flat and generated.

Expected: a sleek, dense instrument: matte plates under one light, white readings, module hues as small marks only, readable greys, one type scale with a display size for numbers and titles, drawn icons, no dead track.

Fix: in `T` and `index.html`: ground `#0f1013`, plate `#16171c` with `inset 0 1px 0 rgba(255,255,255,.05)` and a `0 0 0 1px rgba(0,0,0,.35)` outline, field `#1e2026` (inputs get an inset shadow), text `#f2f3f5` / `#a3a7b0` / `#7a7f89`, radius 10 plates, 8 rail and fields, 6 controls, 4 tags; rows flat 30px on the plate (hover field, selected field with the 2px hue bar, no ring, a hairline only between groups, the stamp in a fixed right column); type IBM Plex Sans 14/1.45 body, 12.5 meta, 12 labels, 22/600 title at -0.01em, 38/500 numbers at -0.025em tabular, IBM Plex Mono for code and tool lines (vendored; keeping Inter with the same scale is the owner's alternative); rail icons in the tertiary grey with the hue on the active and hovered one only; `+ × ↵ ▸ /` drawn as 20-grid SVG at stroke 1.6 and the select replaced by chips; column gap 2.5% with the width to LEFT; RIGHT collapsed to a 44px strip until a tab is open; each module's blank MIDDLE a panel of its state (content per module is the owner's call); the artboard restyled in the same change. Owner decisions before the change: typeface, the RIGHT collapse, the track split, each blank state's content. A mock of Home in this system was rendered on 2026-09-18 for the review.

On 2026-09-18 the owner widened this to a full overhaul on branch `alternate-ui`: the LEFT lists read as clunky and slow to parse, tags should carry organization, search and referencing, and the agent pane should collapse. A clickable preview of that shell, built outside the app with invented data, is `docs/design/otto-next.html` (open it in a browser): one dense table per module with a detail pane beside it, tags on every row with cross-module tag pages, a search bar that takes `#tag`, `@module` and `is:` tokens, a command palette that also holds the agent's skills, keyboard rows, the agent as a collapsible drawer, a point-at-anything mode (aim at a row, a paragraph, a cell or a control, or highlight text, then Ask, Summarize and tag, Capture or Feedback), neutral tags, and Graph as a map of all tags whose selection is an intersection (a click picks a tag, Ctrl+click adds one, Ctrl+Shift+click removes one, and the set is the search bar's tag tokens) with related items previewed in place. Every page change is a browser history entry, so the mouse back and forward buttons walk pages. No control explains itself: no placeholders, no key labels beside buttons, a symbol alone where it depicts the function. A state change is a bordered button and a destructive one is tinted red; Quick access is a snapshot of the page and the search bar's tokens, added from the bookmark at the end of the bar or from the palette under a name of the owner's choosing and removed from the rail; an entry that is one tag's page is marked # and the rest », and there is no separate pinned list. The rail has no headings: modules, a thin rule, then quick access; module counts appear only in Home's header strip, not in the rail or a page title. Home toggles between Priority, what waits, and Recent, the five newest items per module with nothing filtered out, and the search bar's tokens apply to both. The drawer and the detail pane resize by dragging the gutter beside them, with nothing drawn for it, and the widths persist. The header holds the page: its title sits left of the search bar and its controls right of it, so a page's summary is the first row of the main column and the plates start level with the drawer; Home's counts sit in the header as icon and number, so its cards start there too. PT Serif carries the reading text (item titles, prose, chat, descriptors, tags, key caps, the search bar) and PP Formula the chrome (module names, the rail, dates and numbers, the palette, the header). A date stands alone, tags carry no label, and a plain-letter shortcut fires only without a modifier so Ctrl+C copies. Settings is a grid of tiles, Otto (general, data, app) then every module, and a pane that picks model and effort for the agent, each scheduled task and each skill, with the module's own knobs from `config.toml` beneath. Nothing in `app/static` changes until the owner picks a direction from it.
