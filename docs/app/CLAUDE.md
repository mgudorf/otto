# App

## Summary

Dashboard wherein each module has a "left/middle/right" structure. The left hand side is almost always an index of information which can be selected; files, emails, tables/schema, etc.
The middle is the main interaction/use of the module, which displays the main outputs or selections. The right hand side is always an agentic window, typically used for module specific agents actions. Multiple conversations should be spawnable/selectable via tabs; whenever a session closes, the agent should 1. tag the conversation with high level metadata identifiers and then persist in a place reachable by Graph module 

### What runs today

Otto is a Python 3.14 daemon plus a disposable browser window. The daemon keeps every module's state current on a schedule; the window renders that state and holds none of it. Each module pane holds any number of open sessions, one tab each; closing a tab tags its session and ends it. Chat keeps as many conversations as the owner starts, each tagged after its first turn and never closed. Each module is described in `docs/<module>/CLAUDE.md`; this file, `docs/app/CLAUDE.md`, is the platform's. Open findings live in each doc's `## Patches` section.

| Piece | What it is |
|---|---|
| Daemon | FastAPI + uvicorn on `127.0.0.1:8765`, started detached under `pythonw`, logging to `data/daemon.log` (rotated at 1 MB, three kept); loopback only, no authentication |
| Window | Google Chrome in app mode on its own profile in `app/.chrome-profile/`, first-run, default-browser and sync prompts off. The app never touches Microsoft Edge |
| Store | one SQLite file `data/otto.db` in WAL mode, platform and module tables together, every table named `<module>_<name>` (`app_` for the platform), timestamps as UTC ISO strings. `app/migrate.py` brings an older database to the current names at boot, before any schema runs: a backup into `data/backups/` first, then one transaction that drops the indexes and triggers of each moving table (the schemas recreate them under their new names), drops an FTS5 table that moves or whose content table moves (a rename leaves its `content=` behind; the schemas recreate it and it is rebuilt), and renames; a new name already held by a table with rows is refused (`tests/test_migrate.py`) |
| LLM | the Claude Code CLI (2.1.263) headless under the owner's claude.ai Max login; no API key exists anywhere in the app |
| Frontend | static ES modules, Preact + htm vendored, marked + KaTeX vendored for markdown and LaTeX in MIDDLE and in the session pane, inline styles ported from the artboard; no build step, no Node |
| Modules built | Home, Chat, Email, Education, Memory, Science, Finance, Business, Graph, Database have pages; System, Feedback and Search have none. The rail shows only modules whose package exists and that declare a page |

Run: `python -m app` checks the port and code revision, starts or restarts the daemon, then opens the window. `python -m app setup` registers the Windows Task Scheduler entry `Otto` that starts the daemon at logon. `python -m app status` prints health. `python -m app.modules.email.gmail consent` runs the Gmail OAuth flow once and writes the token file. Tests: `.venv/Scripts/python.exe -m pytest -q`, offline; the CLI is mocked at `app.claude.spawn` and a real invocation raises; no Jupyter kernel is started.

```
app/__main__.py   launcher: open | setup | status | daemon
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
app/static/       index.html, shell.js, session.js, rows.js, api.js, feedback.js, md.js, pages/<name>.js, vendor/
data/             otto.db, daemon.log and its rotations, secrets/, workspace/ (Science's root: business/, chat/<id>/ and the owner's notebooks, scripts and folders), backups/, exports/; .gitignore covers data/*.log and data/*.log.*, the db, secrets, workspace, backups and exports
.claude/          skills/ (feature-flow, feedback-queue, sync-architecture): the repo's own workflows
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
| UI is a view | pages fetch `/api/...` on the refresh interval and after every action; the loading line reflects in-flight fetches; the session pane and a running notebook cell subscribe to server-sent events. Static files go out with `Cache-Control: no-cache`, so the browser revalidates every module against its etag, and the shell reloads the window once when `/api/shell` reports a `rev` other than the one it loaded under | `test_memory_end_to_end`, `test_science_run_streams_and_saves` |

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
| business | leads_per_run |
| memory | suggest_lookback_days, suggest_max |
| science | python (the interpreter every kernel and script runs on), root (the workspace itself: the tree LEFT shows, created at boot), idle_minutes, tool_output_chars |
| education | per_night, start_difficulty, flow_low, flow_high |
| database | max_rows, max_seconds |
| email | client_file, token_file, backfill_days, triage_batch |
| web_search | max_findings |
| social | cities (the towns the scout covers), radius_miles, horizon_days, events_per_run |
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

Sessions: `app_sessions(id, module, opened_at, closed_at, title, tags, cli_started)` and `app_session_turns(role user|model|tool|system, text, tool, status)`. Four helpers in `api.py` are the only paths. `new_session(store, module)` opens one. `pane_turn(st, mod, text, prompt)` is a module route's turn of the pane (Education's answer): the module's newest open tab, or a new one when none is open, gets `text` shown as the owner's turn and `prompt` sent to the CLI. `start_turn(st, mod, sid, started, text, prompt, key, replay, on_done)` stores the owner's words, marks the session busy (busy is per session id) and queues a job of kind `session` on resource `session:<sid>`, so one session's turns serialize and different sessions run concurrently; `text` is stored, `prompt` is what the CLI gets. `tag_session(st, mod, sid, key, close)` queues a `oneshot` whose `{"title", "tags"}` is written to the row (fallback: first user line, no tags) with `closed_at` set only when `close` is true, then event `closed` or `tagged` and a `tagged` broadcast; Graph reads `app_sessions.tags`. The module panes keep any number of open sessions per module: `GET /api/session/<module>` lists them oldest first with a label (the title once tagged, until then the first user line), `GET /api/session/<module>/<id>` gives one with its turns and busy state, `POST /api/session/<module>/send` takes `{text, id?}` (no `id` opens a new session; an unknown or closed one is a 404), each streams on key `<module>:<id>` over `GET /api/session/<module>/<id>/events`, and `/clear` with an `id` tags and closes that one. Chat keeps many on its own page, streams on `chat:<id>`, and tags after the first completed turn without closing. Events: `user`, `model`, `delta` (text as it is written, never stored; the panes ignore it), `tool`, `tool_result`, `result`, `error`, `idle`, `tagged`. A first turn that fails retires its session row so the next turn starts clean. A resumed turn the CLI answers with `error_during_execution`, no turns and stderr `No conversation found with session ID` (`ClaudeError.lost_transcript`) is re-sent under the same id as a new session with the caller's `replay` preamble when one was given, after a `system` turn `resumed from Otto's record`. Any other message starting with `/` is passed to the CLI unchanged, so Claude Code commands and skills work from the pane.

MCP servers are `mcp` 2.2.0 `MCPServer` instances mounted stateless with JSON responses; module `tools.py` files register read tools on both servers and write tools on `otto` only.

### Module contract

A module is a package `app/modules/<name>/` plus `app/static/pages/<name>.js`. The registry imports every package; one that raises is recorded in `app_module_errors` and skipped.

| File | Obligation |
|---|---|
| `__init__.py` | `MANIFEST = Manifest(name, title, hue, icon (SVG inner markup, 20x20), order, schedules=(Schedule(task, every "60s\|15m\|24h", resource, llm),), agent=Agent(placeholder, skills, read_tools, write_tools, builtins), page=True)`; `builtins` are CLI tools beyond the read set, given to session turns only. A module with `page=False` (System, Feedback, Search) is still listed by `/api/shell` with `page: false` so its hue and icon resolve, read by Home's hooks, and keeps its `runs`, `model` and `effort` on Settings > Modules, since it has no page to hold them. Optionally `setup(config)`, called once at build after every schema is applied (a raise records the module in `app_module_errors` and drops it), and `async shutdown()`, awaited at lifespan exit after the drain, for a module holding process resources |
| `schema.sql` | the module's tables, every one named `<module>_<name>` and every index and trigger after its table (`test_tables_are_named_after_their_module`), applied at boot (optional; `Store.migrate` only creates, so a column added to an existing table is the module's `setup` to add, and a table that changes its name is a line in `app/migrate.py` `RENAMES`) |
| `tasks.py` | `async def <task>(ctx)` per schedule; `ctx.store` (read), `ctx.commit(cursor=...)` (the only write), `ctx.log`, `ctx.event`, `ctx.run_task(prompt, tools)`; return a string, or `Skipped("why")`; a `BudgetExceeded` out of `run_task` needs no catch, the runner records it as skipped |
| `routes.py` | `router = APIRouter(prefix="/api/<name>")` with `GET left`, `GET item/{id}`, `POST action/{verb}` (through `runner.run_action`), plus hooks `numbers(store) -> {value, label}`, `today(store) -> rows`, `queue(store) -> rows` (everything still waiting on the owner; Home lists every one), `item(store, id)`, `context(store, registry) -> str`. Route handlers must not share a hook's name. Each action `item` offers is `{verb, label, primary?, confirm?, href?, removes?}`: without an `href` the verb must be a key of the module's own action table, since Home posts it verbatim with `{id}`, and `removes: true` says the row leaves the list, which is how a page and Home know to close the inspector standing on it. `tests/test_platform.py::test_item_verbs_are_routes_the_module_serves` walks every module's action literals against its table |
| `tools.py` | `register(read, full, store, config)`: read tools on both servers, write tools on `full` |
| `agent.md` | the agent's job in the owner's terms |
| `pages/<name>.js` | `load(app)`, `meta(app)`, `Left({app, data, mod, fmt})`, `Middle({app, data, mod, fmt})` and optionally `Right(...)`, which replaces the session pane, returning Preact nodes; the shell owns rail, header, tracks and the session pane; `md.js` exports `Markdown` for prose with LaTeX |

Wire shape for LEFT: `{groups: [{label, count, rows: [{id, module, text, stamp, leading?: {kind|dot|ext|pct}, done?, mono?}]}], chips?, chip?, showing?, more?}`. External systems follow one pattern: tasks get a read client, action routes get a write client, and a test proves the split.

**Dismissed and deleted rows leave every list.** A row the owner dismisses (a Social event, a Business lead, a Search finding, a Memory suggestion) or deletes (an Education question) is gone from the module's LEFT, from `today`, from `queue` and from the agent's `context`, and its item offers no verb but a link. The row stays in its table, which is what stops a scout or generator producing it a second time: each of those prompts lists what is already recorded and says a dismissed one shows what to stop bringing. `done` on a row is for a state the owner reached, not one they refused: a completed Memory task and an ended Finance entry stay listed, struck through.

### Platform tables

`app_tasks`, `app_jobs`, `app_job_logs`, `app_settings` (JSON values), `app_cursors`, `app_events(ts, module, verb, text, job_id, ref)`, `app_sessions`, `app_session_turns`, `app_module_errors`, `app_llm_runs(ts, module, task, job_id, status running|done|failed|skipped, minutes, session_id, budgeted)`. The prefix is the module's name, `app` for the platform; the Database page groups tables by it, and `app/migrate.py` `RENAMES` carries every name a table has had.

### Dependencies

| Item | Version / location |
|---|---|
| Python | 3.14.7, `.venv` from the user-wide install at `C:\Users\gudo\AppData\Local\Python\pythoncore-3.14-64\python.exe`, which is also `science.python` |
| fastapi, uvicorn, mcp, httpx, pytest, jupyter_client, nbformat, python-multipart | 0.141.1, 0.52.4, 2.2.0, 0.28.1, 9.1.1, 8.10.0, 5.11.1, 0.0.32 (`requirements.txt`) |
| ipykernel | 7.3.0 in the user-wide Python; the kernel process Science launches |
| Claude Code CLI | 2.1.263 at `C:\Users\gudo\.local\bin\claude.exe`, claude.ai login, subscription max |
| Google Chrome | found through the `App Paths\chrome.exe` registry key |
| SQLite with FTS5 and JSON | 3.50.4, stdlib |
| Vendored frontend | `app/static/vendor/`: preact.mjs, htm.mjs, marked.esm.js 18.0.12, katex/ 0.18.7 (module, stylesheet, 20 woff2 fonts), highlight/ 11.11.1 (core and the python grammar, ES builds), Inter 400/500/600, JetBrains Mono 400/500, pinned by `SHA256SUMS` |
| Google OAuth client and token | `data/secrets/google_client.json` (web client, redirect `http://localhost:8756/m/email/api/oauth/callback`), `data/secrets/token.json`, scope `gmail.modify`, refreshed in place |

Not used: Node, APScheduler, pywebview, `claude-agent-sdk`, nbclient, an Anthropic API key, paid search APIs, a graph database, Microsoft Edge.

## Modules

One doc per module, `docs/<module>/CLAUDE.md`: the owner's requirements, `## Built` and `## Patches`. The platform (`app/`) is this file. Rail order in brackets; a module without a page has no rail entry.

| Module | Doc |
|---|---|
| Home [0] | `docs/home/CLAUDE.md` |
| Chat [1] | `docs/chat/CLAUDE.md` |
| Email [1] | `docs/email/CLAUDE.md` |
| Education [2] | `docs/education/CLAUDE.md` |
| Memory [3] | `docs/memory/CLAUDE.md` |
| Science [4] | `docs/science/CLAUDE.md` |
| Finance [5] | `docs/finance/CLAUDE.md` |
| Business [6] | `docs/business/CLAUDE.md` |
| Graph [7] | `docs/graph/CLAUDE.md` |
| Database [8] | `docs/database/CLAUDE.md` |
| Search [9, no page] | `docs/web_search/CLAUDE.md` |
| Social [10] | `docs/social/CLAUDE.md` |
| System [99, no page] | `docs/system/CLAUDE.md` |
| Feedback [99, no page] | `docs/feedback/CLAUDE.md` |

## UI

Follows style of, but not limited to, the Claude Design project `9459ddf2-3c53-45d8-9252-7a17bd027bf4` (`Personal Dashboard App.dc.html`). The artboard and its runtime are imported to `docs/design/`; open the html in a browser to run it.

### Frame contract

Every page uses three fixed tracks. Selection swaps what renders inside MIDDLE and never moves a track.

| Region | Spec |
|---|---|
| Rail | 56px wide, 32px icon buttons (20px SVG, stroke 1.5), 6px gap, 14px top padding; active background `#23262c`; Activity and Settings pinned at the foot |
| Header | 48px, padding `14px 32px 0`, 20px/600 title, mono 13px meta in `#5f636c`; at the right edge, on a module page, `settings` (the module's `runs` toggle when it has tasks, `model` and `effort` selects, in a 280px panel) beside `feedback` |
| Loading line | 1px, margin `0 32px`; a 30% `#8b8f98` bar animates `translateX(-100% to 340%)` over 1.2s while a fetch is in flight |
| Tracks | `2fr 5fr 2fr` with a `5%` column gap, padding `19px 24px 24px`: LEFT · gap · MIDDLE · gap · RIGHT are 20 · 5 · 50 · 5 · 20 of the frame's width at every window size, so a wider window widens all three and opens no ground between them; opacity fades out and in over 120ms on page switch |
| LEFT | panel `#1a1c21`, radius 6, padding `12px 8px 24px`: search (36px, `#23262c`, 1px focus ring in the hue), chips, groups of one-line rows with a stamp |
| MIDDLE | ground, padding `8px 16px 40px`, content fills the track: the module's blank state or the item inspector, prose included (the inspector, Activity's detail, Education's question, Email's reader and Chat's conversation run the track's full width); Home's number grid holds 640px, Finance's totals strip 720px and each Settings section 560px |
| RIGHT | panel, padding `16px 12px 12px`: the session pane, identical on every page |

| Token | Value |
|---|---|
| Ground / panel / raised | `#101114` / `#1a1c21` / `#23262c` (selection, inputs, user bubbles) |
| Text / muted / dim | `#e6e7ea` / `#8b8f98` / `#5f636c` |
| Hairline / row hover / table row hover | `rgba(230,231,234,.08)` / `#202329` / `#16181c` |
| Hues and rail order | home `#e6e7ea` 0, chat `#d9915b` 1 (not in the artboard; speech-bubble icon; ties with email and sorts first), email `#cf7b7b` 1, education `#7a9fd6` 2, memory `#d1a36a` 3, science `#6fb3b8` 4, finance `#7fb894` 5 (the artboard's Money hue and banknote icon), business `#c98ba8` 6 (not in the artboard; briefcase icon), graph `#b3b06a` 7, database `#a68bd0` 8, social `#8f95d6` 10 (not in the artboard; two-figures icon); web_search `#d9915b` 9 (magnifier icon) and System and Feedback `#8b8f98` 99 have no rail entry, and Search's hue colours its Home rows |
| Type | Inter 15px/1.4 body, 13px meta, 20px/600 title; JetBrains Mono 13px stamps and code, 28px/500 numbers; vendored with `system-ui` / `ui-monospace` fallbacks |
| Rows | 36px list rows, 32px compact rows, 28px group headers, padding `0 12px`, gap 12px, radius 6; leading slot is a kind label (40px, hue), a 6px dot, an extension, or a 40px progress bar; `mono` rows set the text in JetBrains Mono |
| Chips / buttons | padding `3px 9px` / `5px 10px`, radius 6, 13px; active or primary is hue background with `#101114` text; inactive or secondary is `#8b8f98` text with a 1px inset ring on hover |
| Toggle | 28x16 track, 12px knob; on `#e6e7ea` / `#101114`, off `rgba(230,231,234,.14)` / `#8b8f98` |
| Stamps | same day shows the time (`ui.time_format`), otherwise `05 Sep`; group labels are `05 Sep` |
| Markdown | `md.js`: marked with `breaks` and `gfm`, math lifted out first and rendered by KaTeX (`$…$` inline, `$$…$$` display), the `.md` rules and the KaTeX stylesheet added to the document once |
| Composer | `rows.js` `TextArea`, every composer and capture box: three lines when empty, grows with its text (`field-sizing: content`) to half the viewport, then scrolls; raised surface, 15px/1.5, focus ring in the hue; a capture box sits on the panel surface, the Database editor in mono |

Session pane: header is a 6px hue dot plus `claude · <module>`; a tab strip, one mono tab per open session (its label, ellipsized at 140px, `…` appended while another tab's turn runs; the active tab raised), `+` for a blank `new` tab whose first send opens the session, and `×` at the right edge to close the active tab (sends `/clear`: the tagger names it, the tab disappears once `tagged` arrives and a blank tab opens); skill chips; user turns are raised bubbles aligned right at max 85% width, model turns markdown with LaTeX through `md.js`, tool calls one mono line `▸ tool` with the status at the right edge; the composer with the context label and a send button; Enter sends, Shift+Enter breaks a line. The newest open tab is shown on arrival, and the strip re-lists on every shell refresh (the `tick` prop), so a turn a page action started lands in view: a blank tab follows it, another tab shows `…` on it.

Item inspector: 16px hue glyph, kind and time in mono, `×` to clear, the body as markdown through `md.js`, then a primary action in the hue, secondary actions, and `Send to session` right-aligned, which prefills the composer with the item's reference. Email's reader keeps the glyph, time, `×` and `Send to session` and carries no actions; those sit in its LEFT bar.

### Activity and Settings

Activity: LEFT is the `events` log by day with a chip per module; MIDDLE blank state is the task table with its toggles, the nightly budget line (runs used, window, the stagger gap), and the last fifty jobs; selecting an event shows its text and its job's result as markdown, then the error and log. Settings: General (start page among the modules with a page, refresh, time format, rows per page), Modules (every module, page or not: `shown` in the rail for a module with a page, kept here because a hidden module's page cannot be reached to show it again; `runs`, `model` and `effort` read `on its page` for a module with a page and are editable here for one without; a failed module shows its error), Claude (binary, model, the models and efforts a module may pick, agents dir, workspace, sessions kept, background jobs; read-only), Data (database path and size, last backup and last export, `Back up now` through the SQLite backup API into `data/backups/`, `Export`: every table as JSON rows in one file under `data/exports/`, `Vacuum`).

### Departures from the artboard

- Activity's MIDDLE blank state is the task table, required by the Daemon section.
- Finance and Business are separate modules; the artboard had one `Money` entry.
- The rail shows only built modules with a page.
- The header carries `settings` and `feedback` controls the artboard does not have; module settings live there instead of on the Settings page.
- Each module's own departures are the `Departures` row of its doc's `## Built` table.

## Patches

### The module contract does not state the table naming rule

- Kind: gap
- Where: `app/modules/__init__.py` module docstring, its `schema.sql` line; the rule it omits is enforced by `tests/test_platform.py::test_tables_are_named_after_their_module` and stated in the module contract above
- Found: 2026-09-16, sync-architecture
- Status: open

What happens: the docstring every module author reads describes `schema.sql` as "its own tables (optional)" and says nothing about the `<module>_<name>` prefix the 2026-09-13 rename made mandatory. A new module whose schema names a table `items` reads as correct against the contract and fails the suite.

Expected: the contract states the naming rule where it names `schema.sql`, so the docstring and the test say the same thing.

Fix: one line in `app/modules/__init__.py`, `schema.sql    its own tables, every one named <module>_<table> (optional)`. That edit is sitting uncommitted in `main`'s working tree; committing it closes this entry.

### Busy state drops early when two turns are queued on one session

- Kind: bug
- Where: `app/api.py` `start_turn` (`st.session_busy` is a set; the `finally` discards the id when the first turn ends while a second waits on the `session:<sid>` lock); reached by `app/modules/education/routes.py` `answer`, which queues a turn without checking busy
- Found: 2026-09-13, the education quiz work
- Status: open

What happens: two answers submitted in quick succession queue two turns on the same session. The runner serializes them on `session:<sid>`, but `session_busy` holds one entry per session id, so the first turn's `finally` discards it and publishes `idle` while the second is still queued. The pane drops `thinking…` and the send route accepts a third message early; the second turn then streams its `model` event with the pane idle. Nothing is lost, the indicator is wrong for the length of one turn.

Expected: the pane reads busy until the last queued turn of that session has ended.

Fix: count turns per session id (a `Counter`, decremented in `finally`, idle published at zero), or have `start_turn` refuse a second turn while one is queued and let Education's answer route report that the tutor is still busy.

### Daemon does not start at logon on this machine

- Kind: gap
- Where: Daemon requirement "It starts at logon"; `app/__main__.py` `setup`
- Found: 2026-09-07, sync-architecture
- Status: open, owner action

What happens: `python -m app setup` registers the Task Scheduler entry `Otto`, but it has not been run; the daemon starts only when `python -m app` is run. The 2026-09-13 patch session could not run it: registering a scheduled task is outside what an agent session may do on this machine.

Expected: the daemon is running after every logon.

Fix: run `python -m app setup` once from the repo root, then confirm with `Get-ScheduledTask -TaskName Otto`.
