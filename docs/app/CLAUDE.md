# App

## Summary

One page. A brain of dots on the left carries search and navigation, the middle is one feed of every module's rows grouped by facet, the right is the open item in the shape its type names, and the far right is one agent drawer with a tab per conversation. Nine immutable tags — the facets — are the modules that list rows, and picking one anywhere picks it everywhere. Any number of conversations are open at once, one tab each; ending one has the agent name it, tag it and keep it, and it comes back as a row under the chats facet, where Graph reads its tags.

### What runs today

Otto is a Python 3.14 daemon plus a disposable browser window. The daemon keeps every module's state current on a schedule; the window renders that state and holds none of it. One agent holds every enabled module's tools and prompts. Each module is described in `docs/<module>/CLAUDE.md`; this file, `docs/app/CLAUDE.md`, is the platform's. Open findings live in each doc's `## Patches` section.

| Piece | What it is |
|---|---|
| Daemon | FastAPI + uvicorn on `127.0.0.1:8765`, started detached under `pythonw`, logging to `data/daemon.log` (rotated at 1 MB, three kept); loopback only, no authentication |
| Window | Google Chrome in app mode on the owner's own profile: a window of the Chrome they already run, so every link the page opens lands in that browser, signed in, as a new tab. Its title bar and taskbar button show the Otto icon, which Chrome takes from the shell's favicon `app/static/otto.ico`. It is not a process of Otto's, so nothing that ends Otto's processes may match it, or it ends the owner's browser. The app never touches Microsoft Edge |
| Store | one SQLite file `data/otto.db` in WAL mode, platform and module tables together, every table named `<module>_<name>` (`app_` for the platform), timestamps as UTC ISO strings. At boot, before any schema runs, `app/migrate.py` renames an older database's tables to the current names: a backup into `data/backups/` first, then one transaction, refused when a new name already holds a table with rows. After the schemas, `MODULE_RENAMES` rewrites the rows that still name a module by an old name, behind its own backup (`tests/test_migrate.py`) |
| LLM | the Claude Code CLI (2.1.263) headless under the owner's claude.ai Max login; no API key exists anywhere in the app |
| Frontend | static ES modules and one stylesheet, no framework: `core.js` holds the state and renders the feed and the open item, `brain.js` the brain, `drawer.js` the agent, `sql.js` the query editor, `shell.js` the frame and the keyboard; `styles.css` is the approved design and `fonts.css` declares the vendored PT Serif and Geist Mono cuts. marked, KaTeX and highlight.js are vendored for markdown, LaTeX and code; no build step, no Node, nothing fetched from the network at runtime |
| Modules built | nine carry a facet and list rows: Entry, Chat, Email, Education, Science, Finance, Newsfeed, Database and System. Home serves the feed, Graph keeps the tag graph its agent's tools work on, Feedback takes what point mode files; those three carry no facet, so they list nothing and hold no lobe |

Run: `Otto.exe` at the repo root, tracked in git, is how Otto is opened: it runs `.venv/Scripts/python.exe -m app` from its own directory with no console, which checks the port and code revision, starts or restarts the daemon, then opens the window; a failed launch's output shows in a box. A pinned `Otto.exe` and the open window are two taskbar buttons, since the window carries Chrome's app identity. `python -m app setup` registers the Windows Task Scheduler entry `Otto` that starts the daemon at logon. `python -m app build` derives `app/static/otto.ico` from `otto.png` and recompiles `Otto.exe`; both are committed, so it runs only after the logo or the launcher source changes. `python -m app status` prints health. `python -m app.modules.email.gmail consent` runs the Gmail OAuth flow once and writes the token file. Tests: `.venv/Scripts/python.exe -m pytest -q`, offline; the CLI is mocked at `app.claude.spawn` and a real invocation raises; no Jupyter kernel is started.

```
app/__main__.py   launcher: open | setup | build | status | daemon
app/build.py      otto.png -> app/static/otto.ico (the window's icon) -> Otto.exe (the launcher under it): PowerShell with System.Drawing scales the logo, the .NET Framework C# compiler builds the exe
app/daemon.py     app factory, lifespan, detached start, port wait, restart
app/api.py        platform routes: health, restart, shell, tags, verb, tasks, jobs, events, settings, data, sessions; event_stream for any broadcast key
app/config.py     config.toml -> typed Config; every key required, missing keys fail at boot
app/store.py      SQLite connection, settings, cursors, events, backup;  app/schema.sql: platform tables (app_*)
app/migrate.py    RENAMES, every name a table has had, and the boot step that renames an older database's tables, backup first
app/scheduler.py  manifests -> tasks rows; submits due tasks; nightly window
app/runner.py     one queue, per-resource locks, worker count = cap, job rows and logs
app/revision.py   sha256 of app/** and config.toml, served by /health
app/claude.py     CLI spawn, event stream, read-only allowlist, nightly budget
app/modules/      registry, agent_base.md, one package per module (contract under Daemon)
app/static/       index.html, styles.css, fonts.css, otto.ico, app.js, core.js, shell.js, brain.js, drawer.js, point.js, sql.js, api.js, md.js, vendor/
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
| Every scheduled task visible | `app_tasks(name, module, interval_seconds, resource, llm, enabled, last_run, next_run, last_status, last_result)`; System turns each row into a routine row of the feed, carrying its cadence, last run and last result, with `Run now` and `Pause` or `Resume` as its verbs; one whose last run failed waits in Priority. A task switched off stays listed and says paused | `test_system_lists_its_routines`, `test_disabled_and_missing_module` |
| The owner decides what runs | `app_tasks.enabled`, one switch per task, thrown from Settings through `POST /api/tasks/<name>` or by the routine row's Pause and Resume: `tick` skips a task switched off, which keeps its `next_run` and goes the tick after it is switched back on. `sync_tasks` folds the per-module `modules.<name>.scheduled` switch the old Settings threw into its module's tasks, once, and deletes the key; nothing but the owner ever writes a switch | `test_module_switch_becomes_task_switches` |
| Durable job records | SQLite WAL; jobs, logs, events, sessions survive restarts; nothing is replayed | `test_skipped_and_logs_and_commit` |
| Resources in the daemon | tokens under `data/secrets/`, cursors in `app_cursors`, Claude runs as child processes of the daemon, Jupyter kernels as child processes held in Science's module state and shut down at lifespan exit; the page holds nothing | `test_science_reap` |
| Idempotent, kill-safe tasks | a task's only write path is `ctx.commit(cursor=...)`: results and the new cursor in one transaction | `test_skipped_and_logs_and_commit` |
| Scheduled agent only reads | `ctx.run_task` is the only Claude entry point a task can reach: read server, read-only built-ins, budget. `session_turn` and `oneshot` are reachable from routes only. Science's `reap` names neither `execute` nor `write`; its `due` task runs the files the owner scheduled, on purpose | `test_tasks_never_reach_interactive_claude`, `test_read_builtins_exclude_writers`, `test_science_reap_never_executes_or_writes` |
| Failure is local, and says why | the runner catches per job: a `BudgetExceeded` from `run_task` records the job `skipped` with the reason, whichever task raised it; any other exception fails the job: the `app_jobs` row is failed with the full traceback in `error`, the `app_events` row reads `<task>: <exception type and message folded to one line>`, and a scheduled task's `last_result` holds the last 500 characters of the traceback, so a multi-line message keeps its reason. The registry records a module that fails to import or whose `setup` raises in `app_module_errors`, and `/api/shell` reports it disabled with the error | `test_failure_is_local`, `test_budget_refusal_is_skipped`, `test_registry_skips_broken_module` |
| UI is a view | the page fetches `/api/feed` once per mode on `ui.refresh_seconds` and after every verb, and a refresh waits while anything is being typed into; the drawer subscribes to its session's event stream. Static files go out with `Cache-Control: no-cache`, so the browser revalidates every file against its etag | `test_feed_is_every_module_in_two_modes`, `test_second_brain_end_to_end` |

### Config

`config.toml` holds boot values; changing one means relaunching. Live settings are seeded from `[ui]` into the `app_settings` table on first start (`INSERT OR IGNORE`, so a new key reaches an old database on the next boot) and changed afterwards from Settings through `PUT /api/settings` (keys `ui.*`, `modules.<name>.enabled`, and `tasks.<task>.model` and `tasks.<task>.effort`, where the task is the name of the job that makes the run; a value outside its range is a 400: refresh 5 to 3600 s, rows per page 10 to 200, model and effort `default` or one of `claude.models` / `claude.efforts`; any other key, the retired per-module `scheduled`, `model` and `effort` among them, is a 400 too). `enabled` is seeded true for every module carrying a facet; a task's `model` and `effort` are absent until the owner picks one, which reads as `default`.

| Section | Keys |
|---|---|
| server | host, port |
| scheduler | tick_seconds, max_concurrent, drain_seconds |
| claude | binary, model (`default` keeps the CLI's own choice; a task's own pick overrides it), models and efforts (what a task may pick, besides `default`), sessions_kept_days |
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

Every run is one CLI process with the prompt on stdin and `--output-format stream-json --verbose`, launched with `--setting-sources ""`, `--restricted`, `--strict-mcp-config`, `--permission-prompts none`, `--tools` with the read built-ins `Read,Grep,Glob,WebSearch,WebFetch` (a session turn adds the agent's `builtins`, and Otto's are every enabled module's, so `Write` and `Edit` ride every turn, confined to the workspace by `--restricted`), `--allowedTools` for those plus the module's MCP tools, `--system-prompt`, then `--model` and `--effort` when the task's own settings (or, for the model, `claude.model`) say something other than `default`. The task is the job's name: a scheduled task's own (`email.triage`), `<module>.turn` for a session turn (the drawer's is `otto.turn`), `<module>.close` or `<module>.tag` for the tagger, `feedback.file` for a filing. The environment is scrubbed of every `ANTHROPIC_*`, `CLAUDECODE*` and `CLAUDE_CODE_*` variable. Stdout is read in 64 KiB chunks and split on newlines by the daemon itself, so one message carrying a whole file as a tool result never truncates the run. Any run past `max_minutes` is killed. Verified on this machine: the CLI answers with no API key set, WebSearch works headless under these flags, and the owner's global CLAUDE.md does not reach these runs.

| Path | Who | MCP server | Extra flags |
|---|---|---|---|
| `run_task` | scheduled tasks via `ctx.run_task` | `otto-read` at `/mcp/read`: read tools only | `--max-turns <nightly.max_turns> --no-session-persistence`; raises `BudgetExceeded` outside the window or past `max_sessions` |
| `session_turn` | session routes | `otto` at `/mcp/full`: read and write tools | `--session-id` on the first turn, `--resume` after, `--include-partial-messages` always; `--tools` is the read set plus the agent's `builtins` |
| `oneshot` | session tagging, Feedback filing, Education's `Generate` | `otto-read` | `--no-session-persistence`, the caller's `--max-turns` (2 by default, `feedback.max_turns` for a filing) and only the tools the caller names; not counted against the budget |

System prompt: `app/modules/agent_base.md` (shared rules) + the module's `agent.md` + a Current state block from the module's `context(store, registry)` hook, rendered fresh every turn.

`otto` is the drawer's agent and no package: `app/api.py` builds a `Module` for it whose tools are the union of every enabled module's `read_tools`, `write_tools` and `builtins`, whose prompt is every enabled module's `agent.md` in manifest order (each opens with what its module is; `agent_base.md` alone says who the agent is), and whose Current state is Home's `context` hook, so one turn can reach any module. Its `context_label` names the modules it can see (`test_otto_is_the_one_agent`). The per-module session routes still answer; the page calls only `otto`'s.

Budget: when a task run starts, `app_llm_runs` rows of the local day with `budgeted = 1` and status `running`, `done` or `failed` are counted against `max_sessions`; the run then writes its own `running` row before the CLI spawns and updates it to `done` or `failed` after, so concurrent runs see each other; a refusal writes a `skipped` row and the runner records the job `skipped`.

Sessions: `app_sessions(id, module, opened_at, closed_at, title, tags, cli_started)` and `app_session_turns(role user|model|tool|system, text, tool, status)`. Four helpers in `api.py` are the only paths:

| Helper | What it does |
|---|---|
| `new_session(store, module)` | opens one |
| `pane_turn(st, mod, text, prompt)` | a module route's turn of the drawer: the module's newest open session, or a new one when none is open, gets `text` shown as the owner's turn and `prompt` sent to the CLI |
| `start_turn(st, mod, sid, started, text, prompt, key, replay, on_done)` | stores the owner's words (`text`), marks the session busy (a count of queued and running turns per session id; `idle` goes out at zero) and queues a `session` job on resource `session:<sid>` with `prompt` for the CLI, so one session's turns serialize and different sessions run concurrently |
| `tag_session(st, mod, sid, key, close)` | queues a `oneshot` whose `{"title", "tags"}` is written to the row (fallback: first user line, no tags), sets `closed_at` only when `close` is true and the session is still in `st.session_closing` (a reopen since the `/clear` takes it out), then event `closed` or `tagged` and a `tagged` broadcast; Graph reads `app_sessions.tags` |

| Route | What it does |
|---|---|
| `GET /api/session/<module>` | the module's open sessions, oldest first, each labelled with its title once tagged, until then its first user line |
| `GET /api/session/<module>/<id>` | one session with its turns and busy state |
| `POST /api/session/<module>/new` | opens an empty session, so a file can be attached before the first message |
| `POST /api/session/<module>/send` | `{text, id?, files?}`: no `id` opens a new session; an unknown or closed one is a 404. `files` names what Chat's `upload/<id>` put in the session's folder, `data/workspace/chat/<id>/`: the CLI gets the text plus a trailer naming their paths, the transcript the text alone, and a name not in the folder, or files with no `id`, is a 400. `/clear` with an `id` tags and closes that one; anything else is the turn, sent to the CLI as typed |
| `POST /api/session/<module>/<id>/title` | renames the tab, and the name outranks the tagger's |
| `POST /api/session/<module>/<id>/reopen` | a closed session opens again, keeping its turns and its tags. Inside the window between `/clear` and the tagger's write it cancels the close instead, so the tab stays and the session is tagged but never closed; Chat's `reopen` verb does the same |
| `GET /api/session/<module>/<id>/events` | the stream on key `<module>:<id>`: `user`, `model`, `delta` (text as it is written, never stored; the drawer ignores it), `tool`, `tool_result`, `result`, `error`, `idle`, `tagged` |

Chat's rows are every conversation, whichever agent held it, so a session opened under `otto` and closed becomes a chats row. A first turn that fails retires its session row so the next turn starts clean. A resumed turn the CLI answers with `error_during_execution`, no turns and stderr `No conversation found with session ID` (`ClaudeError.lost_transcript`) is re-sent under the same id as a new session, with the caller's `replay` preamble when one was given, after a `system` turn `resumed from Otto's record`.

MCP servers are `mcp` 2.2.0 `MCPServer` instances mounted stateless with JSON responses; module `tools.py` files register read tools on both servers and write tools on `otto` only.

### Module contract

A module is a package `app/modules/<name>/`. The registry imports every package; one that raises is recorded in `app_module_errors` and skipped. No module owns a page.

| File | Obligation |
|---|---|
| `__init__.py` | `MANIFEST = Manifest(name, title, hue, icon (SVG inner markup, 20x20), order, schedules=(Schedule(task, every "60s\|15m\|24h", resource, llm),), agent=Agent(placeholder, read_tools, write_tools, builtins), facet="entry")`. `facet` is the module's immutable tag: the one `fixed` tag every row of it carries, which decides the row's group in the feed, its hue and its mark. A module without one (Home, Graph, Feedback) lists no rows and holds no lobe on the brain, and is still listed by `/api/shell` with `facet: null` so its hue and icon resolve. `builtins` are CLI tools beyond the read set, given to session turns only. Optionally `setup(config)`, called once at build after every schema is applied (a raise records the module in `app_module_errors` and drops it), and `async shutdown()`, awaited at lifespan exit after the drain, for a module holding process resources |
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
when     ISO-8601 on the owner's wall clock: the day it happens or is due when it has one, else when it arrived;
         None for an undated row
fixed    [facet] — exactly one element, the module's facet, never the item's kind
tags     from app.store.tags_for: the owner's own tags, editable
type     which renderer the page uses: note, task, quote, link, suggestion, email, question, notebook,
         script, ledger, article, table, query, conversation, routine, decision
verbs    [[verb, "Label"], …] what the module allows on this row, in the order the owner should see them
waits    int on a queue row, lower first; None elsewhere
…extras  per type: snip, unread, dim, done, starred, late, due, right, amount, pct, summary, related, taggable
```

A kind worth filtering on is a plain tag, not `fixed`: Entry adds `task`, `note`, `link` and `quote` to `tags`. Every verb must be a key of the module's own action table, since the browser posts it through `POST /api/verb` with `{module, id}` and nothing else; eight verbs — `edit`, `answer`, `explain`, `update`, `due`, `open`, `link`, `export` — run in the browser and are never sent. `test_row_verbs_are_routes_the_module_serves` walks every module's verb literals against its table and holds the set that reaches no route. A verb named `trash`, `dismiss`, `forget`, `delete`, `archive`, `later`, `end` or `kill` removes the row: the browser asks first and drops the row when the daemon answers.

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
| Colour | the facet's hue on a group card's left border and its ground, on the facet's own tag chip, and on the send button (`--accent`, the hue mixed toward the ink so it is never white on dark); `--danger` carries a destructive button and a late stamp. A hovered row deepens its own ground and leaves its neighbours theirs |
| Type | PT Serif everywhere, chrome and reading text alike, Geist Mono for code and for a notebook, script, table or routine title. `fonts.css` declares all 6 vendored cuts with the `ascent-override` / `descent-override` that centre text on its capitals, so a glyph sits level with the icon beside it |
| Rows | `--rowh` 42px, three columns: the checkbox that picks it, the title with its snip, and the right-hand cell |
| Dates | `MM-DD-YYYY`, bare: a date carries no word before it, and a stamp shows the time only for something that arrived today. `ui.time_format` decides 24-hour or 12-hour |
| Focus | a lift off the page, not a ring, except on buttons |

### The feed

One list of every module's rows, grouped by facet in manifest order; each group is a card carrying the facet's hue and mark. Priority is every module's `queue()`, ranked least patient first; Recent is every module's `rows()`, latest date first with undated rows behind them. `p` and `r` choose, and the tokens narrow both. The browser holds one set for both modes: `load()` asks `/api/feed` once per mode and merges them by `module/id`, so switching modes or narrowing costs no round trip.

The right-hand cell is a progress bar for a question, the amount for a ledger entry, a box for a task, otherwise the row's own `right`, its due date, or its stamp. Clicking a row opens it in place: the row stays where it is and a summary slides out under it with its tags, its gist, a table's columns or a saved query's SQL, and the rows it relates to, each of which opens from there. `x` or the checkbox picks rows, and `t` tags everything picked at once.

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
| `table` | Database | the query editor seeded with `SELECT * FROM` the table, with Run, Explain and Save; the stamp is the row count. The columns, each with its type and what it promises, are the summary under the row |
| `query` | Database | the query editor holding the saved SQL, which Save keeps under the same name; the SQL is also the summary under the row |
| `conversation` | Chat | the last four turns |
| `routine` | System | the cadence, the last run, the last result and the resource |
| `decision` | any | the fields, the body and the date |

A verb runs through `POST /api/verb`, which finds the module's own `/action/{verb}` and hands back the sentence the module wrote in Activity; the drawer records it. A destructive verb asks in a popover anchored to what it would remove.

### The drawer

One agent. A tab per open conversation with a `+` at the head, the transcript, and a composer carrying what is being discussed as a token — the open item, or what point mode aimed at. `c` opens a conversation, `C` reopens the newest closed one through Chat's `reopen` verb, `F2` renames a tab, and closing one sends `/clear`, which names it, tags it and keeps it as a chats row. Nothing stateful lives in the DOM across a render: a draft per tab, the files attached to it, the caret and which tab is open are module state.

The composer is the text over a bar, after the Claude Code panel in VS Code: attach, a chip with the drawer's model and effort, and send at the far end. Attach opens the file picker, and a file dropped on the composer or pasted into it attaches the same way: it goes straight into the tab's folder through Chat's `upload/<id>`, shows as a token beside the reference, and the next turn names it to the agent. From the `+` tab, attaching first opens an empty tab through `/api/session/otto/new`, which takes the draft with it. The chip reads `default`, a model, or a model and an effort, and opens a popover of both lists, and a pick writes `tasks.otto.turn.model` or `.effort`: the same setting Settings lays out as Otto under Conversation. The clock and the Auto mode of the VS Code panel have no counterpart, since a turn here has no time budget of its own to set and the agent never asks permission.

### Tags

`app_tags(module, item_id, tag)` holds the owner's tags on any module's row; Second Brain keeps `second_brain_tags`, which its own tools read and write, and `app.store.tags_for` reads both, so a tag means the same thing everywhere. `GET /api/tags` lists them with their counts, a tag a Newsfeed run wrote in `newsfeed_tags` counted too, `POST /api/tags/add` and `/remove` write them. A row's `fixed` is its facet and nothing else: it cannot be edited, and a facet's name is refused as a tag to give. Under an open row five tags show, then `+N`; the facet's chip wears its hue and the owner's tags are neutral.

A tag an agent writes is one word. `app.store.word_tags` lowercases, keeps a tag only when it is a single run of letters and digits, and drops repeats. The tools (`newsfeed_search_add`, `newsfeed_tag`, `second_brain_add`, `second_brain_tag`) refuse a list naming the first tag that is not one word, so the agent retries with words; a one-shot (the session tagger, the newsfeed nightly, the feedback filing) drops what fails, since nothing retries it. The owner's own tags through `/api/tags/add` are not held to it.

Selection is an intersection, never a path. `S.tokens` is the one set: a tag picked on the brain, typed into the search bar or clicked on a row is the same token, and adding one narrows the feed. One facet at a time — picking a second replaces the first, and the brain zooms into that facet's cluster.

### The brain

A figure of dots turning slowly inside a dotted chamber, one lobe per facet, each dot shaded by the nearest lobe's hue. Every facet has a callout on a ring outside the figure, its leader following its lobe; picking one zooms into that facet's cluster, where its tags are a point cloud and the ten that matter most in the current mode are named. Up to nine plain tags can be pinned (`m`), each taking a numbered callout in the gaps between the facets, its number key toggling it in the search; the pins are kept in `otto-pins`. Tag nodes are placed by the facets their items belong to, so a tag sits near one, between two or among several, and a node's edges to its facets are drawn only while it is picked, pointed at or the open item's. Positions come from hashes, so a tag sits where it sat. The figure holds still when the system asks for reduced motion, and Settings sets its minutes per turn.

### Keyboard

`?` opens the one list of keys; no control anywhere else names its own. `h` `l` (`←` `→`) step between the brain, the feed, the page and the drawer; `j` `k` (`↓` `↑`) move inside one; `↵` opens what the keyboard stands on, and moving never opens. In the drawer `j` `k` walk the `+`, each tab and then the composer. `1`–`9` toggle the pinned tags. `x` picks a row, `t` tags it, `a` asks about it, `n` starts an entry in the drawer, `e` edits, `Del` deletes, `p` and `r` are the modes, `o` is point mode, `/` or `Ctrl+K` the palette, `Ctrl+Space` the search bar and `Ctrl+Shift+Space` clears it, `Alt+←` and `Alt+→` walk history, `Esc` always leaves one layer, and `Ctrl+↵` in the query editor runs the SQL.

The palette holds the open item's own verbs first, then the frame's actions, the facets, the tags and matching rows.

### History and refresh

The tokens, the open item and the mode are one history entry each (`pushState`), so the mouse's back and forward buttons walk the page's states; `?open=<id>` and `?tag=<tag>` open a link on a row or a tag. The feed refreshes on `ui.refresh_seconds`, read afresh before each wait so a change on Settings holds from the next refresh, and after every verb; a refresh waits while anything is being typed into. `/api/feed` carries the daemon's revision, and a refresh that sees one other than the window booted under reloads the window, so a daemon restarted on new code is never driven by the code before it. Static files go out `Cache-Control: no-cache`.

### Point mode

`o`, or the crosshair in the header, aims at anything: a row, a paragraph, a notebook cell, a lobe, a feed group, the search bar, the tabs, the composer, a turn of the conversation, or a stretch of selected text. Clicking opens a popover naming exactly what was pointed at — down to which paragraph — with four actions: Ask (the reference becomes the drawer's token), Summarize and tag (a real turn of the agent), Capture (an Entry note carrying the tags over), and Feedback (filed through the Feedback module against that reference, which is what `/feedback-queue` later prints). `Esc` leaves.

### Activity and Settings

The program menu under the brand holds Settings, Activity (which adds the `routine` token, so the feed shows System's rows), Back up now, Export, the key list, the theme and what revision is running. A task's row carries `Run now` and `Pause` or `Resume`, so the scheduler is steered from the feed as well.

Settings (`settings.js`) opens from the menu or the palette as a dialog over the page and holds the keyboard until `Esc` or a click outside it. It reads `/api/tasks`, `/api/data` and a fresh `/api/shell`, and every control keeps its own state, so a change never redraws the dialog under the keyboard. The left column is every task by the kind of work it is, each row its title (the job's name on hover), its switch when it has a schedule, and its model and effort when it runs Claude:

| Group | Tasks | Controls |
|---|---|---|
| Conversation | Otto (`otto.turn`, the drawer) | model, effort |
| Filing | Naming conversations (`otto.close`, the tagger when a tab closes), Filing feedback (`feedback.file`) | model, effort |
| Nightly | every `app_tasks` row with `llm`: Question writing, Email triage, Newsfeed searches, Entry suggestions | switch, model, effort |
| Upkeep | every other `app_tasks` row: Email sync, Graph rebuild, Scheduled files, Idle kernel shutdown, Heartbeat, Old conversation cleanup | switch |

A switch is the task's own `app_tasks.enabled`, the one its routine row's Pause and Resume throw; model and effort write `tasks.<job name>.model` and `.effort`, `default` included. A scheduled task missing from the titles in `settings.js` shows its job name. The right column holds Feed, a switch per facet (`modules.<name>.enabled`: its rows reach the feed and its tools reach the agent; the brain is built on the facets once, so the page reloads when the dialog closes after one changed), General (refresh every, 24 h or 12 h), Layout (the cards' and the drawer's shares and the brain's minutes per turn, this browser's own in `otto-layout`, applied as they are typed), Data (the database's path and size, Back up now, Export and Vacuum, each run followed by the date of the last one), and App (the server, the Claude binary, the workspace, `claude.model` when it is not `default`, the nightly window with the day's runs against the budget, and how long closed sessions are kept).

### Files

| File | What it is |
|---|---|
| `index.html` | the skeleton: the header, the four columns, and the popovers, palette, key list, Settings and toast |
| `styles.css` | the design; later rules override earlier ones, so changes are appended |
| `fonts.css` | the `@font-face` block for the cuts vendored under `vendor/fonts` |
| `core.js` | the state, the DOM helpers, the facets and dates, the search bar and its tokens, the feed, the open item and its types, the verbs, the tag and confirm popovers, history, and the frames the other parts fill |
| `shell.js` | the four zones and the keyboard, the palette, the key list, the program menu, the grips, and boot |
| `settings.js` | the Settings dialog, and the setting helpers the drawer's chip shares |
| `brain.js` | the figure, the chamber, the callouts, the pins, the cluster zoom and the turn |
| `drawer.js` | the one agent: tabs, transcript, the composer and its bar, attachments, streaming |
| `point.js` | aiming and the point popover |
| `sql.js` | the query editor: a table or a saved query as SQL that runs on the page, its draft and result kept per item |
| `api.js` | the fetch helpers, a file upload, and the in-flight count behind the pulse |
| `md.js` | markdown with KaTeX |
| `app.js` | imports the parts, which register themselves with core, then boots |

### Departures from the design preview

- The preview's header pulse reads `synced 14:20, 1 job running` as a fixed string; here the dot lights while a request is in flight and the text is the clock time of the last feed fetch.
- The brain's tags are the tags the rows in hand carry, not a graph of their own; a tag on nothing the feed is holding has no node.
- Point mode's entry toast is gone: it was a hint, and it named a key outside the `?` overlay.
- A row carries no tags; they show in the summary under it when it is open, where a phrase-long tag has room to end cleanly.
- Each module's own departures are the `Departures` row of its doc's `## Built` table.

## Patches

### A notebook's cells cannot be edited or run one at a time

- Kind: gap
- Where: `app/static/core.js` (`contentEl`, the `notebook` and `script` cases), `app/modules/science/routes.py` (`EDIT_ACTIONS`, `KERNEL_ACTIONS`, `/api/science/events`, `_run`'s one-cell branch)
- Found: 09-21-2026, writing the one page's doc; widened 09-22-2026, the stale-code audit
- Status: open

What happens: the page draws each cell's code and its last output and nothing more. A cell cannot be typed into, added, moved, deleted or run by itself, and a running cell's output never arrives, because the page subscribes to no module stream. A whole file still runs, and the kernel is still steered, through the row's verbs: Run, Interrupt, Restart kernel, Shut down kernel, Schedule. `set_cell`, `set_cells`, `insert_cell` and `delete_cell` are served and unreachable. So is `_run`'s one-cell branch, which waits on an `index` that `/api/verb` never carries, and `_set_cell` and `_insert_cell` repeat what the `science_set_cell` and `science_insert_cell` tools already do without them.

Expected: the cells are the editor — command and edit modes, the JupyterLab keys, every change written straight to the file, and a run's output arriving as it is produced.

Fix: the `notebook` and `script` renderers become an editor, with the caret and the unwritten draft in module state, as the drawer's draft is. Two things are missing under them: `POST /api/verb` carries only `{module, id, verb, value}`, so a cell edit needs a richer body or a direct post to `/api/science/action/set_cell`, and the page needs a subscription to Science's event stream so a cell fills while it runs.

### A question is answered in the drawer, not on the part it belongs to

- Kind: gap
- Where: `app/static/core.js` (`contentEl`, the `question` case), `app/modules/education/routes.py` (`POST /action/answer`, `_verbs`), `app/api.py` (`pane_turn`)
- Found: 09-21-2026, writing the one page's doc; widened 09-22-2026, the stale-code audit
- Status: open

What happens: the `question` renderer draws the prompt and each part as a card that folds open, and the next ungraded part reads `answer in the drawer`. There is no box on the part and no verb that opens one, so the only way to answer is a typed turn, which Education's own entry says is stored nowhere.

Expected: the answer is typed on the part it belongs to and sent from there, and the grade comes back on that card.

Fix: the `question` renderer grows a box per ungraded part, its half-typed text in module state so a refresh cannot throw it away, posting `{id, n, answer}` to `/api/education/action/answer`, which already briefs the tutor and clears the old grade. The send key belongs in the `?` overlay. The route hands its turn to `pane_turn`, which opens a session under `education`, and the drawer lists only `otto`'s, so the brief and the grade would land in a tab the owner never sees: the turn must go to the drawer's open tab. `pane_turn` has no other caller.

### The daemon's own log has no home

- Kind: gap
- Where: `app/static/shell.js` (`openAppMenu`), `app/api.py` (`/api/events`, `/api/jobs`, `/api/jobs/{job_id}`, none of which has a caller)
- Found: 09-21-2026, writing the one page's doc
- Status: open, needs a decision

What happens: System's routine rows carry each task's cadence, last run, last result and its Run, Pause and Resume verbs, and Settings carries the nightly window and the day's runs; that is all the daemon shows of itself. The events by day and a failed job's error and traceback are drawn nowhere.

Expected: the owner can read the daemon's log from the one page.

Fix: the events are rows and could be a facet of their own, or the program menu could open them as an item, as Settings opens as a dialog. Which shape it takes is the owner's call, since either is a new surface rather than a port of the deleted Activity page.

### Rows per page is kept and read by nobody

- Kind: defect
- Where: `app/api.py` (`UI_KEYS`), `app/daemon.py` (the `ui.page_size` seed), `app/static/core.js` (`load`), `app/modules/home/routes.py` (`FEED_ROWS`)
- Found: 09-21-2026, recovering Settings
- Status: open, needs a decision

What happens: `ui.page_size` is seeded from `[ui]`, validated at 10 to 200 and held at 40 in the live database, and nothing reads it: the feed asks every module for 200 rows in Recent, a number written into both `load` and `FEED_ROWS`. Settings leaves it off rather than show a knob that moves nothing.

Expected: the rows the feed asks for are one setting the owner can see and change, or there is no such setting.

Fix: `load` asks for `ui.page_size` rows per module and Settings shows it under General; the live value of 40 would cut Recent from 200 rows per facet to 40 on the day it lands, and the search bar narrows only the rows in hand, so how many to hold is the owner's call. Otherwise the key leaves `UI_KEYS`, the seed, `[ui]` and `Ui`.

### The repo's CLAUDE.md, README and skills still describe the twelve-page frontend

- Kind: defect
- Where: `CLAUDE.md` (UI 5, Development 3, Layout 3), `README.md` (Open items), `.claude/skills/sync-architecture/SKILL.md` (step 2), `.claude/skills/feature-flow/SKILL.md` (step 6)
- Found: 09-21-2026, recovering Settings; widened 09-22-2026, the stale-code audit
- Status: open

What happens: Development 3 names `app/static/shell.js` "an import and the `PAGES` map" as a shared seam, and Layout 3 lists `pages/<name>.js`, `rows.js`, `session.js`, `feedback.js`, `module_settings.js` and Preact and htm under `vendor/`. None of these exist since the one page: the frontend is `core.js`, `shell.js`, `brain.js`, `drawer.js`, `point.js`, `settings.js`, `api.js` and `md.js`, and `shell.js` has no `PAGES` map. UI 5 and Development 3 still speak of the rail and rail order, and there is no rail. The sync-architecture skill routes a change by `app/static/pages/<name>.js`, and feature-flow's merge step keeps the seams "in rail order". The README's Open items table lists a Database problem (no confirm, no backup, no CSV export) that the query editor has fixed; Database's doc holds no patch behind it.

Expected: the file every change is held to describes the code as it is.

Fix: Layout 3 takes the file list of this doc's Files table, and Development 3 drops `shell.js` from the seams, since no module adds a line to it any more. UI 5 drops the rail, "rail order" becomes manifest order in Development 3 and feature-flow, sync-architecture routes by `app/static/*.js` and this doc's Files table, and the README row goes.

### A tag lives in one of six stores

- Kind: defect
- Where: `app/store.py` (`tags_for`, `add_tags`, `remove_tag`, `all_tags` and their `SECOND_BRAIN` branches), `app/schema.sql` (the `app_tags` comment); `second_brain_tags` in `app/modules/second_brain/tools.py` and `routes.py` (`_tag`, `_untag`); `newsfeed_tags` in `app/modules/newsfeed/routes.py` (`_written`, `_tag`, `_untag`, `tags_of`), `tasks.py` and `tools.py`; `education_questions.tags` in `app/modules/education/routes.py` (`_tags`, `_row_tags`) and `questions.py` (`clean_tags`, `tags_of`); `app_sessions.tags` in `app/api.py` (`tag_session`) and `app/modules/chat/routes.py` (`_tags`); `feedback_items.tags` in `app/modules/feedback/routes.py` and `agent.md`; `app/modules/graph/build.py` (`SOURCES`) and `app/modules/graph/agent.md`
- Found: 09-21-2026, the owner asking for one notion of tag; absorbs Chat's "A conversation's own tags cannot be removed" and Education's "A question's tags live in two places", both 09-20-2026; widened 09-22-2026, the stale-code audit
- Status: open

What happens: the contract says a row's `tags` come from `tags_for`, and five modules keep tags somewhere else: Entry in `second_brain_tags`, Newsfeed in `newsfeed_tags`, Education in a JSON list on the question, the session tagger in a JSON list on the session, Feedback in a JSON list on the filing. Every reader knows a different subset. `tags_for`, `add_tags` and `remove_tag` reach `app_tags` and `second_brain_tags`, the catalog those and `newsfeed_tags`; Graph's rebuild reads the first two and the sessions'; a row shows whatever its module merges. So the × on a tag the session tagger, a nightly run or Education's list gave does nothing and the tag is back on the next refresh, Graph never sees a Newsfeed or Education tag, and the tutor's context lists only Education's own. Each store cleans a tag its own way: `tag_key`, `word_tags`, Education's `clean_tags`, which does not lowercase, and inline strips in the Newsfeed and Entry routes. Feedback's prompt asks for its tags as slots, the page, the kind and the subject, which repeat the filing's own fields, and nothing but `feedback_list` reads them. Three of the module writers have no caller at all: Entry's and Newsfeed's `tag` and `untag` actions and Education's `tags` action, which no row offers and the browser never posts, since its tags go through `/api/tags/add` and `/remove`. They go rather than being rewritten, and with Education's `tags` go `clean_tags` and `TAG_CHARS`.

Expected: one table holds every tag on every row, whoever wrote it. Every writer goes through `add_tags`, an agent's tags through `word_tags` first, and every reader through `tags_for`, so the × works on every tag but a facet, and Graph, the catalog and the brain see one set.

Fix: `app_tags` is the one store. `second_brain_tags`, `newsfeed_tags` (a search keyed `s<id>`) and the Education, session and Feedback lists move into it through the data-migration skill and are dropped, and the `SECOND_BRAIN` branches leave `app/store.py`. The module routes and tools write through `add_tags`, and `SOURCES` becomes `app_tags` alone. Feedback's prompt asks for what the note is about, not for slots.

### A row's kind is drawn as a tag

- Kind: defect
- Where: `app/modules/__init__.py` (the contract line "A kind worth filtering on is a plain tag") and the same line in this doc's module contract; `app/modules/second_brain/routes.py` (`_row`), `app/modules/finance/routes.py` (`_row`), `app/modules/database/routes.py` (`_table_row`, `_query_row`); `app/static/point.js` (`capture`); `docs/design/data.js` (the sample rows' first tags)
- Found: 09-21-2026, the owner asking for one notion of tag
- Status: open, needs a decision

What happens: the contract tells a module to put a kind worth filtering on into `tags`, beside its own line that `tags` are the owner's own and editable. Entry puts the item's kind first (`task`, `note`, `link`, `quote`, `fact`), Finance its kind, Database `table` on a table and `query` on a saved query. They are drawn, narrowed on and placed on the brain as tags nobody gave; the × on one does nothing and it is back on the next refresh, and a Database table carries `table` while refusing any other tag. That is a second class of privileged tag beside the facets, undeclared and looking like the owner's. On Entry and Database it repeats the row's `type`. Point mode's Capture copies a row's tags onto the new note, so a derived tag becomes a stored one there. The artboard's sample rows lead with their type as a tag too.

Expected: a tag is a label someone gave. The facets are the only tags nobody can take off.

Fix: the contract line goes, the three modules stop writing their kind into `tags`, and the artboard's sample rows follow. Where a kind is still wanted as a filter it is one of three things: an immutable tag beside the facets, declared in the manifest and drawn like one; the row's `type`, which the search bar narrows on the way it narrows on `is:`; or an ordinary tag written once at capture, which the owner may take off. The second keeps the immutable set to the facets and stores nothing new, and is the recommendation.

### The window lands in whichever Chrome profile was used last

- Kind: bug
- Where: `app/__main__.py` (`open_window`); `app/config.py` and `config.toml` for the key it needs
- Found: 09-22-2026, checking the real-Chrome change against the owner's Chrome
- Status: open

What happens: `open_window` starts Chrome with `--app` and no profile, and Chrome opens an app window in the profile used last. This Chrome has two profiles, and only `Default` is signed in with the owner's Google account. `Default` was the one used last today, so links land in the owner's Gmail. After a stretch in the other profile, the Otto window and every link it opens land there instead, under another account or none.

Expected: the window, and every link it opens, is always in the profile that holds the owner's account.

Fix: a `[window] profile` key in `config.toml`, `"Default"` on this machine, carried by a `Config` field and passed as `--profile-directory=<profile>` in `open_window`. Chrome then hands the window to the running browser under that profile, whichever profile was used last.

### The first launcher's profile folder is still on disk and still named

- Kind: defect
- Where: `app/revision.py` (`SKIP_DIRS`), `.gitignore` (`app/.browser-profile/`), the folder `app/.browser-profile/` in the primary checkout
- Found: 09-22-2026, deleting `app/.chrome-profile`
- Status: open

What happens: nothing has opened a browser on `app/.browser-profile/` since the window moved to Chrome on 09-07-2026. The folder still sits in the primary checkout at 49 MB, the revision hash still skips it by name, and `.gitignore` still lists it.

Expected: the code names no folder that nothing creates, and the checkout holds no dead browser state.

Fix: delete the folder first, by hand and with the owner's yes, since it is ignored runtime state. Then drop `.browser-profile` from `SKIP_DIRS` and its line from `.gitignore`. The order matters: the hash walks all of `app/`, so with the entry gone and the folder still there, a `.js` or `.html` file written into it would change the revision and restart the daemon.

### A conversation the command-line tool lost cannot be recovered

- Kind: bug
- Where: `app/api.py` (`session_send`, `start_turn`'s `replay` and `on_done`, `REPLAYED`), `app/claude.py` (`LOST_TRANSCRIPT`, `ClaudeError.lost_transcript`), `app/modules/chat/routes.py` (`send`, `_replay`), `[chat] replay_chars`
- Found: 09-22-2026, the stale-code audit
- Status: open

What happens: when the Claude command-line tool no longer holds a conversation it answers "No conversation found", and `start_turn` can then start it again under the same id with Otto's stored transcript in front, but only when its caller passes `replay`. Chat's own `send` is the one caller that does, and nothing calls it; the drawer's `/api/session/otto/send` passes none, so a drawer conversation the tool lost fails on every turn from then on. `on_done`, which Chat's `send` used to name a conversation after its first turn, has no caller either. The Claude section of this doc describes the recovery as if every session had it.

Expected: a conversation Otto kept comes back whether or not the command-line tool kept it.

Fix: `session_send` passes Chat's `_replay` of the stored turns once a session has started; `_replay` and `replay_chars` move with it, and Chat's own `send` goes (Chat's entry "Chat's own conversation routes have no caller"). `on_done` goes unless a title after the first turn is wanted.

### The offline suite reads the owner's Gmail token

- Kind: bug
- Where: `tests/conftest.py` (`config`), `app/modules/email/__init__.py` (`setup`), `app/modules/email/routes.py` (`queue`), `tests/test_app.py::test_feed_is_every_module_in_two_modes`
- Found: 09-22-2026, the stale-code audit
- Status: open

What happens: the `config` fixture replaces only `[data]`, so `email.client_file` and `email.token_file` still name the owner's files under `data/secrets/`. Email's `setup` hands that config to `queue`, which reads the real token's expiry and puts the consent row into Priority for the last two days of each seven-day token. `test_feed_is_every_module_in_two_modes` asserts the whole Priority list and the count of what waits, so in the primary checkout it fails two days in every seven, and it passes in a worktree, which has no `data/secrets`.

Expected: the offline suite reads nothing of the owner's and passes on any day.

Fix: the fixture points both files at paths under `tmp_path`; the consent row gets a test of its own that writes a token with a near expiry.

### Notebook code is inserted into the page as markup

- Kind: bug
- Where: `app/static/core.js` (`contentEl`, the `notebook` and `script` cases), `app/modules/science/routes.py` (`_cells`, `_script_cells`)
- Found: 09-22-2026, the stale-code audit
- Status: open

What happens: Science sends a cell's source and a script's text as they are, and the renderer sets them as HTML (`h('pre', { html: c.code })`), a shape copied from the design preview, whose sample code is already highlighted markup. So `a<b` swallows the rest of the line, `&lt;` shows as `<`, and markup inside a notebook runs in the page: a downloaded notebook carrying `<img onerror=…>` would run script inside the app, where every local route answers without authentication, `/api/database/action/write` included.

Expected: code reads exactly as written and never runs in the page.

Fix: set the code as text (`h('pre', null, c.code)`). The syntax colours the markup assumed were never emitted (see "Frontend code and styles nothing uses").

### A question's Markdown and LaTeX show as source, and its parts by number

- Kind: gap
- Where: `app/static/core.js` (`contentEl`, the `question` case), `app/static/md.js` (`tex`), `app/static/index.html` (the KaTeX stylesheet), `app/modules/education/routes.py` (`detail`)
- Found: 09-22-2026, the stale-code audit
- Status: open

What happens: `detail` sends the definitions, the premise and each part's ask as Markdown with LaTeX, and the renderer sets them as HTML unrendered, so `**bold**` and `$x^2$` show as typed and markup inside a question would run. `tex()` in `md.js` renders exactly this and nothing calls it, so KaTeX, its stylesheet and its twenty fonts load on every page and draw nothing. Each part reads `(1)` and its ask: the letter (`label`) and the `title` that `detail` sends are never read. This misses UI 5 of the repo's CLAUDE.md and Education's question format.

Expected: a question body reads in PT Serif with its LaTeX rendered, and each part leads with its letter and title.

Fix: the `question` case renders each block through `tex()` with raw HTML kept inert (marked passes HTML through), and heads a part with its `label` and `title`. The unused `.qbody` style is the one for the rendered body.

### Editing a title can never be reached, and would not save

- Kind: bug
- Where: `app/static/core.js` (`HERE.edit`, `setEdit`, `commitEdit`, `editorEl`, the `editing` branch of `contentEl`), `app/static/shell.js` (the `e` key), `app/modules/second_brain/routes.py` (`_verbs`, `ACTIONS`)
- Found: 09-22-2026, the stale-code audit
- Status: open

What happens: `e` edits only a row that offers `edit`, and no module offers it, so `e` always answers "Nothing to edit here" and the editor never opens. Were it opened, the edit would still be lost: `commitEdit` hands `edit` to `doVerb`, which finds `edit` among the verbs the browser runs itself and opens the editor again instead of posting, so the new title lives in the browser until the next refresh. This doc's open-item table promises that `e` opens an Entry note, task, quote or link for editing.

Expected: `e` edits an Entry item's text, and the change is kept.

Fix: Entry offers `edit` on its items and serves an `edit` action that takes `value`, and `commitEdit` posts it through `/api/verb` directly rather than through `doVerb`. If editing is not wanted, the path and the table's promise go instead.

### Five modules build a Current state that no agent receives

- Kind: defect
- Where: `context` in `app/modules/chat/routes.py`, `app/modules/database/routes.py`, `app/modules/finance/routes.py`, `app/modules/graph/routes.py` and `app/modules/science/routes.py`; the `agent.md` of database, finance, graph and science; `app/modules/home/routes.py` (`context`); `app/api.py` (`_otto`)
- Found: 09-22-2026, the stale-code audit
- Status: open, needs a decision

What happens: a module's `context` reaches a prompt only through its own nightly Claude run, a one-off run it starts, or a session of its own. Since the per-module panes went, Chat, Database, Finance, Graph and Science have none of the three, and the drawer's Current state is Home's, which gives each faceted module one counter and today's titles (Graph, with no facet, not even that). So the five hooks run for no one, while the Database, Finance, Graph and Science prompts tell the drawer to answer from "the Current state block": the tables with their columns, the ledger, the tag map, the live kernels. The agent never receives any of it.

Expected: what a prompt says the agent can see is what it sees.

Fix: either Home's `context` folds in these modules' own blocks, which lengthens every drawer turn, or the five hooks go with the prompt lines that promise them and the agent reads through its tools. Which is worth the prompt's length is the owner's call.

### Agent prompts send the owner to screens that are gone

- Kind: defect
- Where: the `agent.md` of `app/modules/email/`, `app/modules/finance/`, `app/modules/education/`, `app/modules/science/`, `app/modules/chat/` and `app/modules/newsfeed/`; `app/modules/education/prompts/grade.md`
- Found: 09-22-2026, the stale-code audit
- Status: open

What happens: every enabled module's `agent.md` is part of the drawer's prompt on every turn, and several still describe the per-module pages. Email sends the owner to "the action bar above the Email page's list" with ctrl and shift click. Finance says "the Finance page does that" for adding or changing an entry, which nothing can do. Education has the owner answer "on the page" and press Submit, and read the grade "in the pane". Science tells the owner to refresh the page with Ctrl+Shift+R, and calls deleting cells, files and outputs the owner's action in the page, which offers none. Chat says every message names the conversation's folder, which only Chat's uncalled `send` did, so the agent saves into the workspace root. Newsfeed calls killing a search the owner's call on the page, where no search is listed.

Expected: the prompt describes the app as it is: a row's verbs, the drawer, point mode.

Fix: rewrite those lines against this doc's UI section. Where a promised action has no path at all (a Finance entry, a search's kill, a Science delete), the line says the agent cannot do it, until the entries that add a path land.

### Point mode cannot name a question part or the title

- Kind: bug
- Where: `app/static/point.js` (`POINTABLE`, `refOf`)
- Found: 09-22-2026, the stale-code audit
- Status: open

What happens: point mode names a question part by `.part` and the title by `.dbody h2`, and the one page renders neither: a part is a `.qcard`, and the title sits in `.dhead`, outside `.dbody`. Pointing at a part or the title names the item's body instead, and a heading inside an email or an article is named the title.

Expected: the popover names the part or the title pointed at, as it names a paragraph.

Fix: `.part` becomes `.qcard`, named by its letter, and the title check becomes `.dhead .dtitle`.

### Frontend code and styles nothing uses

- Kind: defect
- Where: `app/static/core.js` (`esc`, `relDay`, `setTokens`, `addItem`, `nextId` and `seq`, `widget`, the `r.url` branch of `doVerb`, `HERE.answer`, `HERE.explain`, the `inflight` import), `app/static/shell.js` (the imports `visible`, `renderTop`, `renderPanel`, `tokenText`), `app/static/point.js` (the imports `currentItem`, `call`, `parts`), `app/static/styles.css` (`.with-tags`, `.tags-inline`, `.dbody.rel`, `.qbody`, `.part`, `.block`, `.k`, `.s`, `.n`, `.cm`), `app/static/vendor/highlight/` and its two lines in `SHA256SUMS`
- Found: 09-22-2026, the stale-code audit
- Status: open

What happens: the one page left these behind. Seven exports of `core.js` have no caller. `doVerb` opens `r.url`, which `/api/verb` never returns. `answer` and `explain` are verbs the browser would run itself, and no module offers either. Eight imports are unused. The styles serve rows that showed their tags inline (in the narrow-window query too), the old Education page's body and parts, a `.block` card, and syntax colours nothing emits. highlight.js and its Python grammar are vendored and pinned, and nothing has imported them since `pages/science.js` went; this doc's Frontend row and Dependencies table and the repo's CLAUDE.md still list them.

Expected: the page carries only what it runs.

Fix: delete them, and highlight.js from the docs. `.qbody` stays if the question entry puts it to use, and KaTeX stays for that entry.

### Platform routes, fields and helpers nothing reaches

- Kind: defect
- Where: `app/api.py` (`GET /api/settings`, `POST /api/session/{module}/{sid}/reopen`, the session routes for any module but `otto`, `_context_label` and `context_label`, `agent.cmd` and `agent.placeholder` in `/api/session/{module}`, `claude.agents_dir`, `claude.background_jobs` and each module's `agent` in `/api/shell`, `later` in `REMOVES`, the `tag_key` import), `app/modules/__init__.py` (`Agent.placeholder`, `Module.item`, `later` and `/api/brain` in the contract docstring), the eleven manifests' `placeholder`, `app/claude.py` (`ClaudeError.subtype` and `num_turns`, the `Any` import), `tests/test_app.py` (the `second_brain` session tests, the `context_label` assertion, the `reopen` lines)
- Found: 09-22-2026, the stale-code audit
- Status: open

What happens: the page reads settings from `/api/shell` and reopens a conversation through Chat's `reopen` verb, so `GET /api/settings` and the platform's `reopen` have no caller. The drawer opens only `otto`'s sessions; every other module's is opened by tests alone, and with them the non-`otto` branches of `_module` and `_context_label`. The page reads none of `context_label`, `agent.cmd`, `agents_dir`, `background_jobs` or `placeholder` (the composer carries no placeholder, per UI 1), yet every manifest with an agent must supply one. The registry loads `Module.item` and nothing calls it; each module's `item` is reached through its own route. `ClaudeError` keeps `subtype` and `num_turns` and nothing reads them. No module offers `later`, and the contract docstring says `/api/brain` draws the tags, a route that was never built (Graph's "The brain does not read the graph" proposes it).

Expected: the platform serves what the page, the launcher, the tools and the clock use.

Fix: delete them, move the session tests onto `otto`, and drop `placeholder` from `Agent` and the manifests. `pane_turn` stays while "A question is answered in the drawer, not on the part it belongs to" may revive `action/answer`.

### Migrations with nothing left to do

- Kind: defect
- Where: `app/migrate.py` (`RENAMES`, `MODULE_RENAMES`, `rename_tables`, `rename_modules`, `rebuild_fts`) and its calls in `app/daemon.py`; `setup` in `app/modules/education/__init__.py`, `app/modules/finance/__init__.py`, `app/modules/graph/__init__.py` and `app/modules/second_brain/__init__.py`; `add_cleared_at` in `app/modules/feedback/queue.py`; Education's fallbacks for old rows (`NO_RUBRIC` and `NO_DEFINITIONS` in `grading.py`, `part_title`'s fallback in `questions.py`, `_defs(None)` in `routes.py`); the `modules.%.scheduled` fold in `app/scheduler.py` (`sync_tasks`); `tests/test_migrate.py`, `test_setup_migrates_v1`, `test_finance_due_column_added`
- Found: 09-22-2026, the stale-code audit, against the live database opened read-only
- Status: open, needs a decision

What happens: the live database holds no table under an old name and no row naming an old module, so `rename_tables` and `rename_modules` return at their first check on every boot, and `RENAMES` still maps `search_topics` and `search_findings` onto `web_search_*`, a module that no longer exists. Every module `setup` that adds or renames columns finds them in place: Education's columns and table rebuilds, Finance's `due_on`, Graph's `memories`, Entry's `memory_id` and `memory_ids`, Feedback's `cleared_at`. No question or part lacks a title, a rubric, definitions or a topic, so Education's fallbacks fire on nothing. The `modules.%.scheduled` fold has one run left, at the next restart, and since the old switch for Entry reads off, that run pauses `second_brain.suggest`.

Expected: code that has done its one job goes; git keeps it.

Fix: first decide whether an old backup must still restore through the renames; this doc's Store row says `RENAMES` carries every name a table has had, which argues for keeping `migrate.py`. The module `setup` steps (Feedback's reset of notes left queued stays), the fallbacks and their tests go either way. The scheduler fold goes after the restart that runs it; switch Entry's suggestions back on in Settings then if they are wanted. Newsfeed's one-time migration has its own entry.

### Deleted modules left tables, settings and folders behind

- Kind: defect
- Where: the live database (the tables `business_items`, `social_items`, `web_search_findings` and `web_search_topics`; the settings `ui.middle_max`, `ui.side_max`, `ui.start_page`, `modules.business.*`, `modules.social.*` and `modules.web_search.*`); the folders `app/modules/business/`, `memory/`, `social/` and `web_search/` in the primary checkout
- Found: 09-22-2026, the stale-code audit, against the live database opened read-only
- Status: open, needs the owner's word

What happens: no schema declares the four tables (20, 20, 0 and 0 rows), nothing reads the settings, and `PUT /api/settings` refuses their keys. Each folder holds only compiled files of a deleted package; the registry passes over it for want of an `__init__.py`.

Expected: nothing on disk or in the store belongs to a module that no longer exists.

Fix: the tables are dropped through the data-migration skill, backup first, only when the owner says so in words, as Newsfeed's migration entry already requires; the settings rows go with them; the folders are deleted by hand with the owner's yes. The events, jobs and runs that name those modules are history and stay.

### Unused packages, merged branches and a merged worktree

- Kind: defect
- Where: `.venv` (`google-api-python-client`, `google-auth-oauthlib` and the eleven packages installed only for them); the local branches merged into `main`; the worktree `../wt-one-page`
- Found: 09-22-2026, the stale-code audit
- Status: open, needs the owner's word

What happens: nothing imports the Google client packages and `requirements.txt` does not list them; they date from an earlier Gmail client, and the thirteen are installed only for one another. Nineteen local branches are fully merged into `main`, and `../wt-one-page` holds one of them, `feat/one-page`, merged and clean, which feature-flow's last step should have removed.

Expected: the environment is what `requirements.txt` says, and a merged branch goes with its worktree.

Fix: with the owner's yes, uninstall the two packages and their orphans, `git worktree remove ../wt-one-page`, and `git branch -d` the merged branches. `feat/automations`, `feat/newsfeed-event-date` and `feat/stop-command` are in flight and stay.

### Comments and docstrings still describe the pages

- Kind: defect
- Where: comments and docstrings in `app/api.py`, `app/runner.py`, `app/claude.py`, `app/config.py`, `config.toml`, `app/static/brain.js`, `app/static/md.js` and every module but System's routes; the tests `test_chat.py`, `test_database.py`, `test_education.py`, `test_email.py`, `test_finance.py`, `test_graph.py`, `test_newsfeed.py` and `test_science.py`; the Built rows of the chat, database, email, feedback, finance, graph, science and second_brain docs
- Found: 09-22-2026, the stale-code audit
- Status: open

What happens: comments across the daemon still speak of a module's page and pane, LEFT and MIDDLE, the file tree, the Activity page, the rail, chips, and a model a module picks on its page. A few say the opposite of the code: `claude.py` counts two ways to reach Claude where there are three; `brain.js` says the figure never stops, though a turn of 0 and reduced motion hold it; `education/tools.py` says the daemon passes no config. Several docs' Built rows still list the routes and panels this audit's other entries name as gone or unreachable.

Expected: a comment says what the code does now.

Fix: each module's cleanup rewrites its own comments and Built rows in the same commit; whatever is left after them goes in one pass.

### The suite reads the live Gmail token

- Kind: bug
- Where: `tests/conftest.py` (`config`), `app/config.py` (`token_file` and `client_file` resolved under the checkout's root), `app/modules/email/routes.py` (`queue`)
- Found: 09-28-2026, merging the dated-rows change
- Status: open

What happens: the `config` fixture moves the database and the workspace into `tmp_path` and leaves `email.token_file` where `config.toml` puts it, under the checkout. In the primary checkout that is the owner's live `data/secrets/token.json`, so once its consent is within `consent_warn_days` of ending, Email's `queue` hands every app-level test a consent row in Priority. Five tests that pin Priority's exact rows and ranks then fail there and only there: `test_feed_is_every_module_in_two_modes`, `test_education_end_to_end`, `test_newsfeed_end_to_end`, `test_newsfeed_feed_and_verbs` and `test_done_and_suggestion_actions`. The same tree passes in a worktree, which has no `data/secrets`. Seen with the consent expired on 09-25-2026.

Expected: the suite runs offline against nothing of the owner's; one tree gives one result in every checkout.

Fix: the `config` fixture points `email.token_file` and `email.client_file` into `tmp_path`, so no test ever sees a live token.
