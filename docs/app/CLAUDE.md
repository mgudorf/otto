# App

## Summary

One page. A brain of dots on the left carries search and navigation, the middle is one feed of every module's rows grouped by facet, the right is the open item in the shape its type names, and the far right is one agent drawer with a tab per conversation. Nine immutable tags — the facets — are the modules that list rows, and picking one anywhere picks it everywhere. Any number of conversations are open at once, one tab each; ending one has the agent name it, tag it and keep it, and it comes back as a row under the chats facet, where Graph reads its tags.

### What runs today

Otto is a Python 3.14 daemon plus a disposable browser window. The daemon keeps every module's state current on a schedule; the window renders that state and holds none of it. One agent holds every enabled module's tools and prompts. Each module is described in `docs/<module>/CLAUDE.md`; this file, `docs/app/CLAUDE.md`, is the platform's. Open findings live in each doc's `## Patches` section.

| Piece | What it is |
|---|---|
| Daemon | FastAPI + uvicorn on `127.0.0.1:8765`, started detached under `pythonw`, logging to `data/daemon.log` (rotated at 1 MB, three kept); loopback only, no authentication |
| Window | Google Chrome in app mode on its own profile in `app/.chrome-profile/`, first-run, default-browser and sync prompts off; its title bar and taskbar button show the Otto icon, which Chrome takes from the shell's favicon `app/static/otto.ico`. The app never touches Microsoft Edge |
| Store | one SQLite file `data/otto.db` in WAL mode, platform and module tables together, every table named `<module>_<name>` (`app_` for the platform), timestamps as UTC ISO strings. At boot, before any schema runs, `app/migrate.py` renames an older database's tables to the current names: a backup into `data/backups/` first, then one transaction, refused when a new name already holds a table with rows. After the schemas, `MODULE_RENAMES` rewrites the rows that still name a module by an old name, behind its own backup (`tests/test_migrate.py`) |
| LLM | the Claude Code CLI (2.1.263) headless under the owner's claude.ai Max login; no API key exists anywhere in the app |
| Frontend | static ES modules and one stylesheet, no framework: `core.js` holds the state and renders the feed and the open item, `brain.js` the brain, `drawer.js` the agent, `shell.js` the frame and the keyboard; `styles.css` is the approved design and `fonts.css` declares the vendored PT Serif and Geist Mono cuts. marked, KaTeX and highlight.js are vendored for markdown, LaTeX and code; no build step, no Node, nothing fetched from the network at runtime |
| Modules built | nine carry a facet and list rows: Entry, Chat, Email, Education, Science, Finance, Newsfeed, Database and System. Home serves the feed, Graph keeps the tag graph its agent's tools work on, Feedback takes what point mode files; those three carry no facet, so they list nothing and hold no lobe |

Run: `Otto.exe` at the repo root, tracked in git, is how Otto is opened: it runs `.venv/Scripts/python.exe -m app` from its own directory with no console, which checks the port and code revision, starts or restarts the daemon, then opens the window; a failed launch's output shows in a box. A pinned `Otto.exe` and the open window are two taskbar buttons, since the window carries Chrome's app identity. `python -m app setup` registers the Windows Task Scheduler entry `Otto` that starts the daemon at logon. `python -m app build` derives `app/static/otto.ico` from `otto.png` and recompiles `Otto.exe`; both are committed, so it runs only after the logo or the launcher source changes. `python -m app status` prints health. `python -m app.modules.email.gmail consent` runs the Gmail OAuth flow once and writes the token file. Tests: `.venv/Scripts/python.exe -m pytest -q`, offline; the CLI is mocked at `app.claude.spawn` and a real invocation raises; no Jupyter kernel is started.

```
app/__main__.py   launcher: open | setup | build | status | daemon
app/build.py      otto.png -> app/static/otto.ico (the window's icon) -> Otto.exe (the launcher under it): PowerShell with System.Drawing scales the logo, the .NET Framework C# compiler builds the exe
app/daemon.py     app factory, lifespan, detached start, port wait, restart
app/api.py        platform routes: health, restart, shell, tags, items, verb, tasks, jobs, events, settings, data, sessions; event_stream for any broadcast key
app/config.py     config.toml -> typed Config; every key required, missing keys fail at boot
app/store.py      SQLite connection, settings, cursors, events, backup;  app/schema.sql: platform tables (app_*)
app/migrate.py    RENAMES, every name a table has had, and the boot step that renames an older database's tables, backup first
app/scheduler.py  manifests -> tasks rows; submits due tasks; nightly window
app/runner.py     one queue, per-resource locks, worker count = cap, job rows and logs
app/revision.py   sha256 of app/** and config.toml, served by /health
app/claude.py     CLI spawn, event stream, read-only allowlist, nightly budget
app/modules/      registry, agent_base.md, one package per module (contract under Daemon)
app/static/       index.html, styles.css, fonts.css, otto.ico, app.js, core.js, shell.js, brain.js, drawer.js, point.js, api.js, md.js, vendor/
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

Every scheduled task is visible in one place. A single list shows each task with its interval, last run, last result and whether it is paused. Nothing can run on a schedule without appearing there, so there are no zombie tasks.

Job records are durable. Job state and logs persist to a small SQLite file, so a restart loses nothing and an overnight failure is readable the next morning.

Long-lived resources live in the daemon, never in a page. OAuth tokens and their refresh, sync cursors, and any kernel or subprocess handle belong to the process. The browser holds no credentials.

Tasks are idempotent and kill-safe. Every task must be safe to run twice and safe to die mid-run: write results in one transaction, advance cursors only after the write commits, and never leave a half-state the next run cannot recover from.

The agent runs on a schedule and only reads. LLM work (annotating, summarizing, pre-generating) runs as scheduled tasks and produces state the user finds on arrival. Any write to an external system, and any deletion, is a synchronous user action from the UI. Enforce this with a read-only client handed to scheduled tasks and a writing client available only to user-action routes, checked by a test.

Failure is local. A task that raises marks its own row failed and logs the exception; it never takes the scheduler, another module, or the server down. A module that fails to load is skipped with an error, not fatal.

The UI is a view of daemon state. The page renders from the store and polls or subscribes for changes; it never computes or holds state the daemon does not have. A window opened days later shows the current state immediately, because the daemon kept it current.

### Mechanisms

| Requirement | Mechanism | Test |
|---|---|---|
| Long-running, at logon, fixed port | `python -m app setup` registers a logon task running `pythonw -m app.daemon` with the repo as working directory, no time limit, restart on failure; `[server]` in `config.toml` | — |
| One instance, restart on code change | `/health` returns `rev`, a sha256 of `app/**` and `config.toml`. The launcher compares it with the working tree; on mismatch it posts `/admin/restart`: the daemon drains running jobs up to `drain_seconds`, spawns a detached replacement, exits; the replacement waits for the port to free. Direct starts wait the same way and give up if the port stays busy | `test_revision_changes_with_content` |
| Daemon owns the clock | `Scheduler.sync_tasks` turns manifest schedules into `app_tasks` rows and deletes rows no manifest declares; `tick` every `tick_seconds` submits enabled tasks whose `next_run` passed. LLM tasks become due only inside `[nightly] window` and are re-armed for the next window start; only one goes per `stagger_minutes`, the rest stay due for a later tick, so two nightly runs never overlap | `test_sync_creates_rows_and_removes_orphans`, `test_tick_submits_due_and_advances`, `test_window_logic`, `test_nightly_runs_are_staggered` |
| One job runner | `Runner`: one queue, `max_concurrent` workers, one lock per `resource`, an `app_jobs` row per job (`scheduled`, `action`, `session`) with `app_job_logs`. Routes run user actions through `run_action` and await the result, or `submit` and return the job id when the outcome arrives later. Rows left `queued` or `running` by a crash are marked failed at start | `test_same_resource_serializes_and_different_overlap`, `test_cap_holds` |
| Every scheduled task visible | `app_tasks(name, module, interval_seconds, resource, llm, enabled, last_run, next_run, last_status, last_result)`; System turns each row into a routine row of the feed, carrying its cadence, last run and last result, with `Run now` and `Pause` or `Resume` as its verbs; one whose last run failed waits in Priority. A task of a module switched off stays listed and says so | `test_system_lists_its_routines`, `test_disabled_and_missing_module` |
| The owner decides what runs | `modules.<name>.scheduled`, one switch per module through `PUT /api/settings`, held by `Scheduler.runs`: every task of a module switched off stays due and goes the tick after it is switched back on. Seeded true once at boot; nothing but the owner ever writes it | `test_module_switch_holds_every_task` |
| Durable job records | SQLite WAL; jobs, logs, events, sessions survive restarts; nothing is replayed | `test_skipped_and_logs_and_commit` |
| Resources in the daemon | tokens under `data/secrets/`, cursors in `app_cursors`, Claude runs as child processes of the daemon, Jupyter kernels as child processes held in Science's module state and shut down at lifespan exit; the page holds nothing | `test_science_reap` |
| Idempotent, kill-safe tasks | a task's only write path is `ctx.commit(cursor=...)`: results and the new cursor in one transaction | `test_skipped_and_logs_and_commit` |
| Scheduled agent only reads | `ctx.run_task` is the only Claude entry point a task can reach: read server, read-only built-ins, budget. `session_turn` and `oneshot` are reachable from routes only. Science's `reap` names neither `execute` nor `write`; its `due` task runs the files the owner scheduled, on purpose | `test_tasks_never_reach_interactive_claude`, `test_read_builtins_exclude_writers`, `test_science_reap_never_executes_or_writes` |
| Failure is local, and says why | the runner catches per job: a `BudgetExceeded` from `run_task` records the job `skipped` with the reason, whichever task raised it; any other exception fails the job: the `app_jobs` row is failed with the full traceback in `error`, the `app_events` row reads `<task>: <exception type and message folded to one line>`, and a scheduled task's `last_result` holds the last 500 characters of the traceback, so a multi-line message keeps its reason. The registry records a module that fails to import or whose `setup` raises in `app_module_errors`, and `/api/shell` reports it disabled with the error | `test_failure_is_local`, `test_budget_refusal_is_skipped`, `test_registry_skips_broken_module` |
| UI is a view | the page fetches `/api/feed` once per mode on `ui.refresh_seconds` and after every verb, and a refresh waits while anything is being typed into; the drawer subscribes to its session's event stream. Static files go out with `Cache-Control: no-cache`, so the browser revalidates every file against its etag | `test_feed_is_every_module_in_two_modes`, `test_second_brain_end_to_end` |

### Config

`config.toml` holds boot values; changing one means relaunching. Live settings are seeded from `[ui]` into the `app_settings` table on first start (`INSERT OR IGNORE`, so a new key reaches an old database on the next boot) and changed afterwards through `PUT /api/settings` (keys `ui.*`, `modules.<name>.enabled`, `modules.<name>.scheduled`, `modules.<name>.model` and `modules.<name>.effort`; a value outside its range is a 400: refresh 5 to 3600 s, rows per page 10 to 200, model and effort `default` or one of `claude.models` / `claude.efforts`). `enabled` and `scheduled` are seeded true, `enabled` for every module carrying a facet; `model` and `effort` are absent until the owner picks one, which reads as `default`. Nothing in the page writes a setting today — the patch below carries what that costs.

| Section | Keys |
|---|---|
| server | host, port |
| scheduler | tick_seconds, max_concurrent, drain_seconds |
| claude | binary, model (`default` keeps the CLI's own choice; a module's own pick overrides it), models and efforts (what a module may pick, besides `default`), sessions_kept_days |
| data | db, workspace (working directory of every Claude run; file tools are confined to it) |
| nightly | window (local time), max_sessions per day (at least one per nightly LLM task), max_turns and max_minutes per run, stagger_minutes between one nightly run and the next |
| chat | upload_max_mb (an attachment past it is a 413), replay_chars (tail of the stored transcript replayed when the CLI has lost a conversation) |
| second_brain | suggest_lookback_days, suggest_max |
| science | python (the interpreter every kernel and script runs on), root (the workspace itself, created at boot), idle_minutes, tool_output_chars |
| education | per_night, start_difficulty, flow_low, flow_high |
| database | max_rows, max_seconds |
| email | client_file, token_file, backfill_days, triage_batch, read_on_open, consent_warn_days |
| newsfeed | items_per_run (entries a search may add per run when the agent set no cap on it) |
| feedback | max_turns |
| ui | refresh_seconds, time_format (`24h` or `12h`), page_size |

### Claude

Every run is one CLI process with the prompt on stdin and `--output-format stream-json --verbose`, launched with `--setting-sources ""`, `--restricted`, `--strict-mcp-config`, `--permission-prompts none`, `--tools` with the read built-ins `Read,Grep,Glob,WebSearch,WebFetch` (a session turn adds the agent's `builtins`, and Otto's are every enabled module's, so `Write` and `Edit` ride every turn, confined to the workspace by `--restricted`), `--allowedTools` for those plus the module's MCP tools, `--system-prompt`, then `--model` and `--effort` when the module's own settings (or, for the model, `claude.model`) say something other than `default`. The environment is scrubbed of every `ANTHROPIC_*`, `CLAUDECODE*` and `CLAUDE_CODE_*` variable. Stdout is read in 64 KiB chunks and split on newlines by the daemon itself, so one message carrying a whole file as a tool result never truncates the run. Any run past `max_minutes` is killed. Verified on this machine: the CLI answers with no API key set, WebSearch works headless under these flags, and the owner's global CLAUDE.md does not reach these runs.

| Path | Who | MCP server | Extra flags |
|---|---|---|---|
| `run_task` | scheduled tasks via `ctx.run_task` | `otto-read` at `/mcp/read`: read tools only | `--max-turns <nightly.max_turns> --no-session-persistence`; raises `BudgetExceeded` outside the window or past `max_sessions` |
| `session_turn` | session routes | `otto` at `/mcp/full`: read and write tools | `--session-id` on the first turn, `--resume` after, `--include-partial-messages` always; `--tools` is the read set plus the agent's `builtins` |
| `oneshot` | session tagging, Feedback filing, Education's `Generate` | `otto-read` | `--no-session-persistence`, the caller's `--max-turns` (2 by default, `feedback.max_turns` for a filing) and only the tools the caller names; not counted against the budget |

System prompt: `app/modules/agent_base.md` (shared rules) + the module's `agent.md` + a Current state block from the module's `context(store, registry)` hook, rendered fresh every turn.

`otto` is the drawer's agent and no package: `app/api.py` builds a `Module` for it whose tools are the union of every enabled module's `read_tools`, `write_tools` and `builtins`, whose prompt is every enabled module's `agent.md` in manifest order, and whose Current state is Home's `context` hook, so one turn can reach any module. Its `context_label` names the modules it can see (`test_otto_is_the_one_agent`). The per-module session routes still answer; the page calls only `otto`'s.

Budget: when a task run starts, `app_llm_runs` rows of the local day with `budgeted = 1` and status `running`, `done` or `failed` are counted against `max_sessions`; the run then writes its own `running` row before the CLI spawns and updates it to `done` or `failed` after, so concurrent runs see each other; a refusal writes a `skipped` row and the runner records the job `skipped`.

Sessions: `app_sessions(id, module, opened_at, closed_at, title, tags, cli_started)` and `app_session_turns(role user|model|tool|system, text, tool, status)`. Four helpers in `api.py` are the only paths:

| Helper | What it does |
|---|---|
| `new_session(store, module)` | opens one |
| `pane_turn(st, mod, text, prompt)` | a module route's turn of the drawer: the module's newest open session, or a new one when none is open, gets `text` shown as the owner's turn and `prompt` sent to the CLI |
| `start_turn(st, mod, sid, started, text, prompt, key, replay, on_done)` | stores the owner's words (`text`), marks the session busy (a count of queued and running turns per session id; `idle` goes out at zero) and queues a `session` job on resource `session:<sid>` with `prompt` for the CLI, so one session's turns serialize and different sessions run concurrently |
| `tag_session(st, mod, sid, key, close)` | queues a `oneshot` whose `{"title", "tags"}` is written to the row (fallback: first user line, no tags), sets `closed_at` only when `close` is true, then event `closed` or `tagged` and a `tagged` broadcast; Graph reads `app_sessions.tags` |

| Route | What it does |
|---|---|
| `GET /api/session/<module>` | the module's open sessions, oldest first, each labelled with its title once tagged, until then its first user line |
| `GET /api/session/<module>/<id>` | one session with its turns and busy state |
| `POST /api/session/<module>/send` | `{text, id?}`: no `id` opens a new session; an unknown or closed one is a 404. `/clear` with an `id` tags and closes that one; any other message starting with `/` goes to the CLI unchanged, so Claude Code commands and skills work from the drawer |
| `POST /api/session/<module>/<id>/title` | renames the tab, and the name outranks the tagger's |
| `POST /api/session/<module>/<id>/reopen` | a closed session opens again, keeping its turns and its tags |
| `GET /api/session/<module>/<id>/events` | the stream on key `<module>:<id>`: `user`, `model`, `delta` (text as it is written, never stored; the drawer ignores it), `tool`, `tool_result`, `result`, `error`, `idle`, `tagged` |

Chat's rows are every conversation, whichever agent held it, so a session opened under `otto` and closed becomes a chats row. A first turn that fails retires its session row so the next turn starts clean. A resumed turn the CLI answers with `error_during_execution`, no turns and stderr `No conversation found with session ID` (`ClaudeError.lost_transcript`) is re-sent under the same id as a new session, with the caller's `replay` preamble when one was given, after a `system` turn `resumed from Otto's record`.

MCP servers are `mcp` 2.2.0 `MCPServer` instances mounted stateless with JSON responses; module `tools.py` files register read tools on both servers and write tools on `otto` only.

### Module contract

A module is a package `app/modules/<name>/`. The registry imports every package; one that raises is recorded in `app_module_errors` and skipped. No module owns a page.

| File | Obligation |
|---|---|
| `__init__.py` | `MANIFEST = Manifest(name, title, hue, icon (SVG inner markup, 20x20), order, schedules=(Schedule(task, every "60s\|15m\|24h", resource, llm),), agent=Agent(placeholder, skills, read_tools, write_tools, builtins), facet="entry")`. `facet` is the module's immutable tag: the one `fixed` tag every row of it carries, which decides the row's group in the feed, its hue and its mark. A module without one (Home, Graph, Feedback) lists no rows and holds no lobe on the brain, and is still listed by `/api/shell` with `facet: null` so its hue and icon resolve. `builtins` are CLI tools beyond the read set, given to session turns only. Optionally `setup(config)`, called once at build after every schema is applied (a raise records the module in `app_module_errors` and drops it), and `async shutdown()`, awaited at lifespan exit after the drain, for a module holding process resources |
| `schema.sql` | the module's tables, every one named `<module>_<name>` and every index and trigger after its table (`test_tables_are_named_after_their_module`), applied at boot (optional; `Store.migrate` only creates, so a column added to or renamed on an existing table is the module's `setup` to do, a table that changes its name is a line in `app/migrate.py` `RENAMES`, and a module that changes its name a line in `MODULE_RENAMES`) |
| `tasks.py` | `async def <task>(ctx)` per schedule; `ctx.store` (read), `ctx.commit(cursor=...)` (the only write), `ctx.log`, `ctx.event`, `ctx.run_task(prompt, tools)`; return a string, or `Skipped("why")`; a `BudgetExceeded` out of `run_task` needs no catch, the runner records it as skipped |
| `routes.py` | `router = APIRouter(prefix="/api/<name>")` with `GET item/{id}` and `POST action/{verb}` (through `runner.run_action`), plus hooks `rows(store, limit) -> [ROW]`, `queue(store) -> [ROW]` (everything still waiting on the owner, each with `waits`), `item(store, id)`, `numbers(store) -> {value, label}`, `today(store) -> rows`, `context(store, registry) -> str`. Route handlers must not share a hook's name |
| `tools.py` | `register(read, full, store, config)`: read tools on both servers, write tools on `full` |
| `agent.md` | the module's share of the one agent's system prompt, in the owner's terms |

A ROW is what every list speaks:

```
id       unique within the module; may be prefixed ("s12", "query:12") or a path
module   str
title    str
when     ISO-8601 on the owner's wall clock, or None for an undated row
fixed    [facet] — exactly one element, the module's facet, never the item's kind
tags     from app.store.tags_for: the owner's own tags, editable
type     which renderer the page uses: note, task, quote, link, suggestion, email, question, notebook,
         script, ledger, article, table, query, conversation, routine, decision
verbs    [[verb, "Label"], …] what the module allows on this row, in the order the owner should see them
waits    int on a queue row, lower first; None elsewhere
…extras  per type: snip, unread, dim, done, starred, late, due, right, amount, pct, summary, related, taggable
```

A kind worth filtering on is a plain tag, not `fixed`: Entry adds `task`, `note`, `link` and `quote` to `tags`. Every verb must be a key of the module's own action table, since the browser posts it through `POST /api/verb` with `{module, id}` and nothing else; six verbs — `edit`, `answer`, `explain`, `update`, `due`, `query` — run in the browser and are never sent. `test_row_verbs_are_routes_the_module_serves` walks every module's verb literals against its table and holds the set that reaches no route. A verb named `trash`, `dismiss`, `forget`, `delete`, `archive`, `later` or `end` removes the row: the browser asks first and drops the row when the daemon answers.

External systems follow one pattern: tasks get a read client, action routes get a write client, and a test proves the split.

**Dismissed and deleted rows leave every list.** A row the owner dismisses (a Newsfeed entry, an Entry suggestion) or deletes (an Education question) is gone from `rows`, from `today`, from `queue` and from the agent's `context`, and its item offers no verb but a link. The row stays in its table, which is what stops a scout or generator producing it a second time: each of those prompts lists what is already recorded and says a dismissed one shows what to stop bringing. `done` on a row is for a state the owner reached, not one they refused: a completed Entry task and an ended Finance entry stay listed, struck through.

### Platform tables

`app_tasks`, `app_jobs`, `app_job_logs`, `app_settings` (JSON values), `app_cursors`, `app_events(ts, module, verb, text, job_id, ref)`, `app_sessions`, `app_session_turns`, `app_module_errors`, `app_llm_runs(ts, module, task, job_id, status running|done|failed|skipped, minutes, session_id, budgeted)`. The prefix is the module's name, `app` for the platform; Database's table rows group by it, and `app/migrate.py` `RENAMES` carries every name a table has had, `MODULE_RENAMES` every name a module has had.

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
| Vendored frontend | `app/static/vendor/`: marked.esm.js 18.0.12, katex/ 0.18.7 (module, stylesheet, 20 woff2 fonts), highlight/ 11.11.1 (core and the python grammar, ES builds), and under `fonts/` the 4 PT Serif cuts and Geist Mono 400/500, all pinned by `SHA256SUMS` |
| Google OAuth client and token | `data/secrets/google_client.json` (web client, redirect `http://localhost:8756/m/email/api/oauth/callback`), `data/secrets/token.json`, scope `gmail.modify`, refreshed in place |

Not used: Node, APScheduler, pywebview, PyInstaller, `claude-agent-sdk`, nbclient, an Anthropic API key, paid search APIs, a graph database, Microsoft Edge.

## Modules

One doc per module, `docs/<module>/CLAUDE.md`: the owner's requirements, `## Built` and `## Patches`. The platform (`app/`) is this file. The facet is the module's immutable tag and its group in the feed; a module without one lists no rows.

| Module | Facet | Doc |
|---|---|---|
| Entry | `entry` | `docs/second_brain/CLAUDE.md` |
| Chat | `chats` | `docs/chat/CLAUDE.md` |
| Email | `email` | `docs/email/CLAUDE.md` |
| Education | `education` | `docs/education/CLAUDE.md` |
| Science | `science` | `docs/science/CLAUDE.md` |
| Finance | `finance` | `docs/finance/CLAUDE.md` |
| Newsfeed | `newsfeed` | `docs/newsfeed/CLAUDE.md` |
| Database | `database` | `docs/database/CLAUDE.md` |
| System | `routine` | `docs/system/CLAUDE.md` |
| Home | — | `docs/home/CLAUDE.md` |
| Graph | — | `docs/graph/CLAUDE.md` |
| Feedback | — | `docs/feedback/CLAUDE.md` |

## UI

The window is one page: the brain, the feed, the open item and the agent drawer under one header. There is no rail, no per-module page and no per-module agent. Plain ES modules and one stylesheet: no framework, no build step, nothing fetched from the network at runtime.

### Frame contract

`.app` is one CSS grid: a `var(--toph)` header row over four columns — panel, main, page, chat. Nothing floats over them but the popovers, the palette, the key list and the toast.

| Region | Spec |
|---|---|
| Columns | shares, not pixels: `S.layout.feed` is the feed's percentage of the width, `S.layout.drawer` the drawer's, and the big panel takes the rest. `applyLayout` writes them to `grid-template-columns`; `otto-layout` in `localStorage` keeps them |
| Panel | the brain, while `data-view="brain"` |
| Main | the feed, always |
| Page | the open item, while `data-view="inspect"` |
| Chat | the one agent drawer, while `data-chat="open"` |
| Modes | the brain and the page are the same share on opposite sides of the feed and never show together; `[` swaps them and `]` closes the drawer. Opening or closing an item never swaps them |
| Grips | one gutter per movable edge, with nothing drawn for it: right of the brain, left of the page, left of the drawer. Dragging writes the share, releasing saves it |
| Header | the brand, which opens the program menu; the Priority and Recent segment; the search bar; then the pulse and six icon buttons: brain or inspect, point, palette, keys, theme, drawer |
| Search bar | tokens, then a bare input. A token is a tag, a module or an `is:` filter (`unread`, `open`, `done`, `starred`); `#`, `@` and `is:` suggest as they are typed, `↑ ↓ ↵` take a suggestion, Backspace on an empty input drops the last token. The typed text narrows the rows in hand over their title, their snip and their tags |
| Pulse | the dot lights while any request is in flight; the text is the clock time of the last feed fetch |

| Token | Value |
|---|---|
| Themes | Rainbow and Dark, both dark, switched from the header or the program menu and kept in `otto-look`. `--m` is the open item's facet hue; Rainbow mixes it into every surface, Dark holds the tint at nothing. There is no light theme |
| Colour | the facet's hue on a group card's left border and its ground, and on the send button (`--accent`, the hue mixed toward the ink so it is never white on dark); `--danger` carries a destructive button and a late stamp. A hovered row deepens its own ground and leaves its neighbours theirs |
| Type | PT Serif everywhere, chrome and reading text alike, Geist Mono for code and for a notebook, script, table or routine title. `fonts.css` declares all 6 vendored cuts with the `ascent-override` / `descent-override` that centre text on its capitals, so a glyph sits level with the icon beside it |
| Rows | `--rowh` 42px, three columns: the checkbox that picks it, the title with its snip, and the right-hand cell |
| Dates | `MM-DD-YYYY`, bare: a date carries no word before it, and a stamp shows the time only for something that arrived today. `ui.time_format` decides 24-hour or 12-hour |
| Focus | a lift off the page, not a ring, except on buttons |

### The feed

One list of every module's rows, grouped by facet in manifest order; each group is a card carrying the facet's hue and mark. Priority is every module's `queue()`, ranked least patient first; Recent is every module's `rows()`, newest first with undated rows behind them. `p` and `r` choose, and the tokens narrow both. The browser holds one set for both modes: `load()` asks `/api/feed` once per mode and merges them by `module/id`, so switching modes or narrowing costs no round trip.

The right-hand cell is a progress bar for a question, the amount for a ledger entry, a box for a task, otherwise the row's own `right`, its due date, or its stamp. Clicking a row opens it in place: the row stays where it is and a summary slides out under it with its tags, its gist and the rows it relates to, each of which opens from there. `x` or the checkbox picks rows, and `t` tags everything picked at once.

### The open item

The page draws the item in the shape its `type` names, after `GET /api/{module}/item/{id}` has filled the row out with what only the module can answer for.

| type | Module | What the page draws |
|---|---|---|
| `email` | Email | the stamp, the fields, the body |
| `question` | Education | the prompt and each part as a card that folds open, with its score once graded |
| `note` `task` `quote` `link` | Entry | the prose, struck through when done; `e` opens the title for editing |
| `suggestion` | Entry | the prose; it takes none of the owner's tags |
| `notebook` `script` | Science | every cell, its code and its last output, read only; the stamp is the kernel's state and the owner's schedule |
| `ledger` | Finance | the amount, the due date, the fields and the history |
| `article` | Newsfeed | the fields and the body |
| `table` | Database | every column with its type and its comment; the stamp is the row count |
| `query` | Database | the saved SQL |
| `conversation` | Chat | the last four turns |
| `routine` | System | the cadence, the last run, the last result and the resource |
| `decision` | any | the fields, the body and the date |

A verb runs through `POST /api/verb`, which finds the module's own `/action/{verb}` and hands back the sentence the module wrote in Activity; the drawer records it. A destructive verb asks in a popover anchored to what it would remove.

### The drawer

One agent. A tab per open conversation with a `+` at the head, the transcript, and a composer carrying what is being discussed as a token — the open item, or what point mode aimed at. `c` opens a conversation, `C` reopens the newest closed one through Chat's `reopen` verb, `F2` renames a tab, and closing one sends `/clear`, which names it, tags it and keeps it as a chats row. Nothing stateful lives in the DOM across a render: a draft per tab, the caret and which tab is open are module state.

### Tags

`app_tags(module, item_id, tag)` holds the owner's tags on any module's row; Second Brain keeps `second_brain_tags`, which its own tools read and write, and `app.store.tags_for` reads both, so a tag means the same thing everywhere. `GET /api/tags` lists them with their counts, `POST /api/tags/add` and `/remove` write them. A row's `fixed` is its facet and nothing else: it cannot be edited, and a facet's name is refused as a tag to give.

Selection is an intersection, never a path. `S.tokens` is the one set: a tag picked on the brain, typed into the search bar or clicked on a row is the same token, and adding one narrows the feed. One facet at a time — picking a second replaces the first, and the brain zooms into that facet's cluster.

### The brain

A figure of dots turning slowly inside a dotted chamber, one lobe per facet, each dot shaded by the nearest lobe's hue. Every facet has a callout on a ring outside the figure, its leader following its lobe; picking one zooms into that facet's cluster, where its tags are a point cloud and the ten that matter most in the current mode are named. Up to nine plain tags can be pinned (`m`), each taking a numbered callout in the gaps between the facets, its number key toggling it in the search; the pins are kept in `otto-pins`. Tag nodes are placed by the facets their items belong to, so a tag sits near one, between two or among several, and a node's edges to its facets are drawn only while it is picked, pointed at or the open item's. Positions come from hashes, so a tag sits where it sat. The figure holds still when the system asks for reduced motion, and the program menu sets its minutes per turn.

### Keyboard

`?` opens the one list of keys; no control anywhere else names its own. `h` `l` (`←` `→`) step between the brain, the feed, the page and the drawer; `j` `k` (`↓` `↑`) move inside one; `↵` opens what the keyboard stands on, and moving never opens. In the drawer `j` `k` walk the `+`, each tab and then the composer. `1`–`9` toggle the pinned tags. `x` picks a row, `t` tags it, `a` asks about it, `n` starts an entry in the drawer, `e` edits, `Del` deletes, `p` and `r` are the modes, `o` is point mode, `/` or `Ctrl+K` the palette, `Ctrl+Space` the search bar and `Ctrl+Shift+Space` clears it, `Alt+←` and `Alt+→` walk history, `Esc` always leaves one layer.

The palette holds the open item's own verbs first, then the frame's actions, the agent's skills (typing `/` shows only those), the facets, the tags and matching rows.

### History and refresh

The tokens, the open item and the mode are one history entry each (`pushState`), so the mouse's back and forward buttons walk the page's states; `?open=<id>` and `?tag=<tag>` open a link on a row or a tag. The feed refreshes on `ui.refresh_seconds` and after every verb, and a refresh waits while anything is being typed into. Static files go out `Cache-Control: no-cache`.

### Point mode

`o`, or the crosshair in the header, aims at anything: a row, a paragraph, a notebook cell, a lobe, a feed group, the search bar, the tabs, the composer, a turn of the conversation, or a stretch of selected text. Clicking opens a popover naming exactly what was pointed at — down to which paragraph — with four actions: Ask (the reference becomes the drawer's token), Summarize and tag (a real turn of the agent), Capture (an Entry note carrying the tags over), and Feedback (filed through the Feedback module against that reference, which is what `/feedback-queue` later prints). `Esc` leaves.

### Activity and Settings

Neither is a page. The program menu under the brand holds Settings (the shares the feed and the drawer take, and the brain's minutes per turn), Activity (which adds the `routine` token, so the feed shows System's rows), Back up now, Export, the key list, the theme and what revision is running. A task's row carries `Run now` and `Pause` or `Resume`, so the scheduler is steered from the feed.

### Files

| File | What it is |
|---|---|
| `index.html` | the skeleton: the header, the four columns, and the popovers, palette, key list and toast |
| `styles.css` | the design; later rules override earlier ones, so changes are appended |
| `fonts.css` | the `@font-face` block for the cuts vendored under `vendor/fonts` |
| `core.js` | the state, the DOM helpers, the facets and dates, the search bar and its tokens, the feed, the open item and its types, the verbs, the tag and confirm popovers, history, and the frames the other parts fill |
| `shell.js` | the four zones and the keyboard, the palette, the key list, the program menu, the layout popover, the grips, and boot |
| `brain.js` | the figure, the chamber, the callouts, the pins, the cluster zoom and the turn |
| `drawer.js` | the one agent: tabs, transcript, composer, streaming |
| `point.js` | aiming and the point popover |
| `api.js` | the fetch helpers and the in-flight count behind the pulse |
| `md.js` | markdown with KaTeX |
| `app.js` | imports the parts, which register themselves with core, then boots |

### Departures from the design preview

- The preview's header pulse reads `synced 14:20, 1 job running` as a fixed string; here the dot lights while a request is in flight and the text is the clock time of the last feed fetch.
- The brain's tags are the tags the rows in hand carry, not a graph of their own; a tag on nothing the feed is holding has no node.
- Point mode's entry toast is gone: it was a hint, and it named a key outside the `?` overlay.
- A row carries no tags; they show in the summary under it when it is open, where a phrase-long tag has room to end cleanly.
- Each module's own departures are the `Departures` row of its doc's `## Built` table.

## Patches

### Reopening a chat inside the tagging window finds it still open

- Kind: defect
- Where: `app/api.py` (`session_send` `/clear`, `session_reopen`), `app/static/drawer.js` (`closeChat`, `reopenChat`, `openConversation`)
- Found: 2026-09-20, building the agent drawer
- Status: open

What happens: closing a tab posts `/clear`, which returns as soon as the tagging one-shot is submitted; the row is closed only when that run finishes, seconds later. The drawer removes the tab at once. Pressing `C` inside that window reopens a session that was never closed: the route answers 200, the tab comes back, and then the tagger's close lands and the tab disappears again on the next sync.

Expected: reopening always returns a tab that stays, whether or not the tagger has finished.

Fix: either the drawer holds the reopen until the close settles (it already knows the session is being tagged, since `tagged` arrives on the stream), or the platform can cancel a queued close so a reopen inside the window supersedes it. The second is the smaller surface and keeps the drawer free of daemon timing.

### A notebook's cells cannot be edited or run one at a time

- Kind: gap
- Where: `app/static/core.js` (`contentEl`, the `notebook` and `script` cases), `app/modules/science/routes.py` (`EDIT_ACTIONS`, `KERNEL_ACTIONS`, `/api/science/events`)
- Found: 09-21-2026, writing the one page's doc
- Status: open

What happens: the page draws each cell's code and its last output and nothing more. A cell cannot be typed into, added, moved, deleted or run by itself, and a running cell's output never arrives, because the page subscribes to no module stream. A whole file still runs, and the kernel is still steered, through the row's verbs: Run, Interrupt, Restart kernel, Shut down kernel, Schedule. `set_cell`, `set_cells`, `insert_cell` and `delete_cell` are served and unreachable.

Expected: the cells are the editor — command and edit modes, the JupyterLab keys, every change written straight to the file, and a run's output arriving as it is produced.

Fix: the `notebook` and `script` renderers become an editor, with the caret and the unwritten draft in module state, as the drawer's draft is. Two things are missing under them: `POST /api/verb` carries only `{module, id, verb, value}`, so a cell edit needs a richer body or a direct post to `/api/science/action/set_cell`, and the page needs a subscription to Science's event stream so a cell fills while it runs.

### A question is answered in the drawer, not on the part it belongs to

- Kind: gap
- Where: `app/static/core.js` (`contentEl`, the `question` case), `app/modules/education/routes.py` (`POST /action/answer`, `_verbs`)
- Found: 09-21-2026, writing the one page's doc
- Status: open

What happens: the `question` renderer draws the prompt and each part as a card that folds open, and the next ungraded part reads `answer in the drawer`. There is no box on the part and no verb that opens one, so the only way to answer is a typed turn, which Education's own entry says is stored nowhere.

Expected: the answer is typed on the part it belongs to and sent from there, and the grade comes back on that card.

Fix: the `question` renderer grows a box per ungraded part, its half-typed text in module state so a refresh cannot throw it away, posting `{id, n, answer}` to `/api/education/action/answer`, which already briefs the tutor and clears the old grade. The send key belongs in the `?` overlay.

### A saved query shows its SQL and cannot run it

- Kind: gap
- Where: `app/static/core.js` (`contentEl`, the `table` and `query` cases), `app/modules/database/routes.py` (`ACTIONS`)
- Found: 09-21-2026, writing the one page's doc
- Status: open

What happens: a table draws its columns and its row count; a saved query draws its SQL as one read-only block. Neither runs anything. The table's `Query` verb only opens the drawer with `query <table>: ` half-typed, so every read now goes through the agent. `run`, `write`, `explain` and `save` are served and unreachable, so there is no result grid, no plan, and no place for the confirmation a writing statement asks for.

Expected: a query is edited and run where it is shown, its rows drawn under it, `EXPLAIN` available, and a statement that writes confirmed before it goes.

Fix: the `query` renderer becomes an editable block with Run, Explain and Save, drawing `{cols, rows}` as a grid under it; `write` keeps the confirmation the old console asked for. A table's `Query` verb then opens that block seeded with a `SELECT` rather than the drawer.

### The daemon's own state has no home: no Activity, no Settings

- Kind: gap
- Where: `app/static/shell.js` (`openAppMenu`, `openLayoutPop`), `app/api.py` (`/api/events`, `/api/jobs`, `GET` and `PUT /api/settings`)
- Found: 09-21-2026, writing the one page's doc
- Status: open, needs a decision

What happens: System's routine rows carry each task's cadence, last run, last result and its Run, Pause and Resume verbs, and that is all the daemon shows of itself. The events by day, a failed job's error and traceback, the nightly window and how much of its run budget is used are drawn nowhere. `PUT /api/settings` is served and nothing calls it: a module's `enabled` and `scheduled` switches, its model and its effort, `ui.refresh_seconds` and `ui.time_format` can only be changed against the API by hand, and `ui.page_size` is seeded, validated and read by nobody — the feed asks for 200 rows.

Expected: the owner can read the daemon's log and change a live setting from the one page.

Fix: the events are rows and could be a facet of their own, or the program menu could open them as an item; the settings want a pane or an item, one row per key. Which of the two shapes each takes is the owner's call, since both are new surfaces rather than a port of the deleted pages.

### The window keeps running the code it booted with

- Kind: defect
- Where: `app/static/shell.js` (`boot`), `app/api.py` (`/api/shell` `rev`)
- Found: 09-21-2026, writing the one page's doc
- Status: open

What happens: `boot` fetches `/api/shell` once and never looks at `rev` again, and the refresh asks only for `/api/feed`. When the launcher restarts the daemon on a code change, an open window goes on running the JavaScript it loaded, against a daemon that may answer differently. Nothing says the window is stale.

Expected: the window reloads itself once when the daemon reports a revision other than the one it booted under.

Fix: the revision has to reach the refresh — either `load()` re-fetches `/api/shell` and compares, or `/api/feed` carries `rev` beside its items. One reload, once, as the old shell did.

### The facet tag is coloured, and twelve show where the rule says five

- Kind: defect
- Where: `app/static/styles.css` (`.tag.fixed`, `.token.tag.fixed`), `app/static/core.js` (`tagEl`, `revealEl`)
- Found: 09-21-2026, writing the one page's doc
- Status: open, needs a decision

What happens: a facet's tag is drawn in its module's hue — tinted ground, coloured ink, coloured ring, bold — while the owner's own tags are neutral, so the two systems do not look alike and colour lands somewhere other than a card's left border and a primary button. The summary under an open row shows twelve tags before `+N`. Both are version 36 of the preview, ported verbatim.

Expected: UI rules 3 and 4 — tags are neutral and one system, five then `+N`, and colour is the module's hue on a card's left border and on a primary button, nothing else.

Fix: one rule and one number, if the rules win: `.tag.fixed` drops to the neutral ground with its mark carrying the facet, and `revealEl` asks for five. The preview the owner approved does it the other way, so which gives way is theirs to say.

### Nine modules still serve the list the old pages asked for

- Kind: defect
- Where: `GET left` in the `routes.py` of chat, database, education, email, finance, graph, newsfeed, science and second_brain; `app/api.py` (`GET /api/items`)
- Found: 09-21-2026, writing the one page's doc
- Status: open

What happens: each of the nine still builds the grouped, paged list its page used to draw, and `/api/items` still merges every module's rows by tag. The page asks for neither: it asks for `/api/feed` twice and `/api/{module}/item/{id}` when a row opens. The routes are carried, tested and merged for nothing, and a module changing its rows has two shapes to keep in step instead of one.

Expected: the daemon serves what the page asks for.

Fix: delete `left` from the nine and its tests with it, keeping whatever grouping logic `rows` still needs. `/api/items` is the older cross-module route and `/api/feed` supersedes it; it goes the same way unless a tool is found to be reading it.

### The artboard is still the twelve-page app

- Kind: gap
- Where: `docs/design/Personal Dashboard App.dc.html`, `docs/design/support.js`
- Found: 09-21-2026, writing the one page's doc
- Status: open

What happens: `docs/design/` is the stated source for hues, icons and each page's shape, and what it holds is the imported artboard of the rail, twelve pages, a detail pane and a per-module agent. The hues and the marks still match the app; nothing about its shape does.

Expected: the artboard is the app, since the owner reads it as the app and not as an import.

Fix: the approved one-page design replaces the import in `docs/design/`, and the repo's `CLAUDE.md` line describing it as "each page's LEFT and MIDDLE shape" follows it.
