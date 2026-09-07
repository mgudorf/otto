# Otto App Plan

Status: planning, 2026-09-07. Nothing below is installed or built; see [Manifest](#manifest).

## Goal

A local daemon keeps every module's state current on a schedule. A disposable browser window renders that state in the three-track frame from the design. Closing the window never stops work; a window opened days later shows current state immediately.

This plan covers the platform only: daemon, shell, module contract, Claude session pane, Activity, Settings. Each data module gets its own plan under `docs/roadmap/<module>/` and plugs into the contract defined here.

## Sources

| Source | Governs |
|---|---|
| [ARCHITECTURE.md](../../ARCHITECTURE.md) | Daemon requirements (binding), module goals |
| [Personal Dashboard App.dc.html](../../design/Personal%20Dashboard%20App.dc.html) | Frame, surfaces, type, hues, per-module list / inspector / session shapes |
| [support.js](../../design/support.js) | dc-runtime that renders the artboard in a browser; reference only, never shipped |

Design imported 2026-09-07 from Claude Design project `9459ddf2-3c53-45d8-9252-7a17bd027bf4`, file `Personal Dashboard App.dc.html`. The sibling artboard `Personal Dashboard.dc.html` (Home variants 1a to 1e) stays in the project and was not imported.

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | Daemon in Python 3.14: FastAPI + uvicorn, bound to `127.0.0.1` only | One small async process serves the scheduler, JSON routes, static files and event streams; the venv already exists |
| 2 | Window is Microsoft Edge in app mode (`--app=http://127.0.0.1:<port>`) with its own profile in `app/.browser-profile/` | Already installed; the window is a throwaway client; no tray app, no WebView2 wrapper to maintain |
| 3 | Frontend has no build step: static ES modules, Preact + htm vendored as two files, inline style objects | No Node on this machine; the artboard is React-shaped with inline styles and ports 1:1; a module page is one file that can be deleted |
| 4 | One SQLite file `data/otto.db` in WAL mode holds jobs, tasks, settings, sessions and module data | Durable job records are a hard requirement; the path is already gitignored |
| 5 | Scheduler and job runner are hand-rolled on asyncio | The spec is exactly one table, one queue, per-resource locks, one cap; a scheduling library would be a second source of truth for schedules |
| 6 | All LLM work runs the Claude Code CLI headless (`claude -p`) under the existing Max login; no API key exists anywhere in the app | Hard constraint: no API charges. Scheduled runs get a read-only tool allowlist; interactive sessions get the module's tools |
| 7 | Daemon starts at logon through a Windows Task Scheduler task registered once by `python -m app setup` | Survives reboots, restarts on failure, nothing to remember |
| 8 | Boot values live in `config.toml` (committed defaults); live settings live in the `settings` table edited from the Settings page | No hard-coded values, and a restart-requiring value never shares a store with a live one |

Rejected: Vite / React / TypeScript (needs Node and a build), APScheduler, pywebview, an Anthropic API key, paid search APIs, a graph database.

## Layout

```
app/
  __main__.py          python -m app: check port and revision, start daemon if needed, open window; `setup` registers the logon task
  daemon.py            FastAPI app factory; lifespan: store -> registry -> scheduler -> runner
  config.py            loads config.toml into a typed object
  store.py             SQLite connection, migrations, jobs / tasks / settings / sessions tables
  scheduler.py         interval clock; submits due tasks to the runner
  runner.py            one queue, per-resource locks, concurrency cap, job rows and logs
  revision.py          content hash of app/** (excluding .browser-profile); served by /health
  claude.py            spawns the CLI, streams events, enforces the read-only allowlist and the nightly budget
  modules/
    __init__.py        registry: imports each module, records failures, never raises
    <name>/
      __init__.py      MANIFEST (see Module contract)
      tasks.py         scheduled work; receives read-only clients only
      routes.py        /api/<name>/... ; the only place a writing client is available
      agent.md         system prompt for this module's Claude session
  static/
    index.html         shell entry
    shell.js           rail, header, loading line, three tracks, page switching
    session.js         Claude session pane, shared by every module
    rows.js            shared list row with slots (leading, text, stamp)
    api.js             fetch, polling, event-stream helpers
    modules/<name>.js  exports left(state) and middle(state) for that module
    vendor/            preact.mjs, htm.mjs, fonts/ (pinned versions recorded in vendor/VERSIONS)
data/                  runtime state, gitignored: otto.db, secrets/, sessions/, backups/
config.toml
tests/
```

Runtime data never lives in a page. OAuth tokens, sync cursors and kernel handles belong to the daemon process; the browser holds nothing.

## Frame contract

Every module page uses the same three fixed regions. Selection swaps what renders inside MIDDLE and never moves or resizes a track.

| Region | Surface | Content |
|---|---|---|
| Rail | ground | 56px wide, 32px icon buttons (20px stroke-1.5 SVG), 6px gap, 14px top padding; Activity and Settings pinned at the foot; active button background `#23262c` |
| Header | ground | 48px, padding `14px 32px 0`, title 20px/600 plus mono 13px meta in `#5f636c` |
| Loading line | ground | 1px, margin `0 32px`; a 30% wide `#8b8f98` bar animates `translateX(-100% to 340%)` over 1.2s while any fetch is in flight |
| Tracks | | `grid-template-columns: minmax(220px,4fr) minmax(300px,9fr) minmax(220px,4fr)`, gap `0 24px`, padding `19px 24px 24px`; opacity fades to 0 and back over 120ms on page switch |
| LEFT | panel `#1a1c21`, radius 6, padding `12px 8px 24px` | Search input (36px, `#23262c`, focus ring 1px in the module hue), optional chips, groups of one-line rows with a stamp |
| MIDDLE | ground, padding `8px 16px 40px` | Inspector for the selection; blank state is the module's own notion of blank (Home: numbers; Database: empty query box; Science: nothing until a file is picked) |
| RIGHT | panel `#1a1c21`, radius 6, padding `16px 12px 12px` | Claude session; identical shell everywhere, only agent, skills and rules differ |

Tokens, taken from the artboard:

| Token | Value |
|---|---|
| Ground / panel / raised | `#101114` / `#1a1c21` / `#23262c` (raised is used for selection, inputs and user bubbles) |
| Text / muted / dim | `#e6e7ea` / `#8b8f98` / `#5f636c` |
| Hairline / row hover / table row hover | `rgba(230,231,234,.08)` / `#202329` / `#16181c` |
| Hues | home `#e6e7ea`, email `#cf7b7b`, education `#7a9fd6`, memory `#d1a36a`, science `#6fb3b8`, money `#7fb894`, graph `#b3b06a`, database `#a68bd0`, activity and settings `#e6e7ea` |
| Type | Inter 15px / 1.4 body, 13px meta, 20px / 600 title; JetBrains Mono 13px stamps and code, 28px / 500 numbers |
| Rows | 36px list rows, 32px compact rows, 28px group headers, padding `0 12px`, gap 12px, radius 6 |
| Chips | padding `3px 9px`, radius 6, 13px; active is hue background with `#101114` text, inactive is `#8b8f98` text |
| Buttons | padding `5px 10px`, radius 6, 13px; primary is hue background with `#101114` text; secondary is `#8b8f98` text with a 1px inset ring on hover |
| Toggle | 28x16 track, 12px knob; on is `#e6e7ea` track with `#101114` knob, off is `rgba(230,231,234,.14)` track with `#8b8f98` knob |

Fonts are vendored (Inter 400/500/600, JetBrains Mono 400/500) with `system-ui` and `ui-monospace` fallbacks, so the window works offline.

Shapes the artboard fixes per page (copy the SVG icon paths from the artboard verbatim):

- Home: LEFT shows the date, then per module a hue-colored header with a count and a short list with a `+N` link into the module; MIDDLE blank state is the number grid (`repeat(auto-fit, minmax(140px,1fr))`, one number per module, clicking it opens the module).
- Item inspector (Email, Education, Memory, Money): 16px hue glyph, title, `x` to clear; body; then a primary action in the hue, secondary actions, and `Send to session` right-aligned.
- Science: notebook header (glyph, file name, kernel status), cells in a `48px minmax(0,1fr)` grid with code on a panel and outputs as text, table or plot below.
- Graph: meta row, an SVG of edges over positioned node labels; selecting a node highlights its neighbors and dims the rest.
- Database: SQL textarea on a panel, `Run` / `Explain` / `Export`, result meta right-aligned, result table with hairline rows and a pager.
- Activity: LEFT is the event log by day with chips `All` plus one per module, rows `time (44px) - hue dot - verb (64px) - text`; MIDDLE blank state is the scheduled-task table (interval, last run, next run, last result, enable toggle); selecting an event shows its job log.
- Settings: sections General (start page, refresh interval, time format, rows per page), Modules (one toggle per module), Claude (binary, model, agents dir, sessions kept, background jobs), Data (database path, last backup, `Back up now` / `Export` / `Vacuum`).
- Session pane: header is a 6px hue dot plus the agent command in mono; skill chips; transcript where user turns are raised bubbles aligned right at max 85% width, model turns are plain text at line-height 1.6, and tool calls are one mono line `▸ tool · status`; composer is a 3-row textarea with a context label, `new` and a send button below.

One deviation from the artboard, required by ARCHITECTURE: the session pane header carries a tab strip so several conversations can be open per module. The artboard shows one transcript and a `new` button.

## Module contract

A module is one Python package plus one static file. The shell owns everything else.

Python, `app/modules/<name>/__init__.py`:

```python
MANIFEST = Manifest(
    name="email", title="Email", hue="#cf7b7b", order=1, icon="email",
    schedules=[Schedule(task="sync", every="15m", resource="gmail")],
    agent=Agent(prompt="agent.md", read_tools=[...], write_tools=[...],
                placeholder="Ask about the inbox...", skills=[...]),
)
```

| Piece | Obligation |
|---|---|
| `tasks.py` | One async function per declared schedule. Receives a read-only context: store handle, read clients, `claude.run_task`. Results and the new cursor go through `ctx.commit(rows, cursor=...)`, one transaction; there is no separate cursor API, so a task can die anywhere and the next run recovers |
| `routes.py` | `GET /api/<name>/left`, `GET /api/<name>/item/<id>`, `GET /api/<name>/numbers`, `POST /api/<name>/action/<verb>`. Writing clients exist only here. Actions run through the runner so they serialize with scheduled work on the same resource |
| `agent.md` | System prompt for the module's session. Skills and rules are listed in the manifest and shown as chips |
| `static/modules/<name>.js` | `left(state)` and `middle(state)` returning Preact nodes; uses the shared row component; no state of its own beyond selection and chips |

Wire shape for LEFT, shared by every module so the shell can render it:

```
{ groups: [{ label, count, rows: [{ id, text, stamp, leading?: {dot|kind|ext|pct}, hue? }] }],
  chips?: [label], showing?: "40 / 31,904" }
```

Registry rules: a module that fails to import is skipped and recorded in `module_errors`; its rail button still renders, disabled, with the error in its tooltip. Schedules exist only through manifests, so nothing can run on a schedule without appearing in Activity. The rail is generated from the registry in `order`, so adding or splitting a module never touches the shell.

External systems follow one pattern: a module registers a read client (handed to tasks) and a write client (available in routes). For Gmail that is two consents, `gmail.readonly` and `gmail.modify`, so a leaked task client cannot write even by accident.

## Daemon contract

Each requirement in ARCHITECTURE maps to one mechanism and one test.

| Requirement | Mechanism | Test |
|---|---|---|
| Long-running, at logon, fixed loopback port | Task Scheduler task runs `pythonw -m app.daemon` at logon; `server.port` from config; binds `127.0.0.1` only | Health endpoint answers after a simulated restart |
| One instance, restart on code change | Launcher reads `/health` `{rev}`; `rev` is a sha256 over `app/**` contents; mismatch posts `/admin/restart`; the daemon drains running jobs up to `scheduler.drain_seconds`, spawns its replacement, and exits; the replacement retries the bind until the port frees (Windows has no in-place exec) | Editing a file changes `rev`; launcher triggers restart; old PID gone, new PID serving |
| Daemon owns the clock | `scheduler.py` ticks every `scheduler.tick_seconds`, reads `tasks` where `enabled and next_run <= now`, submits, and advances `next_run` | Task with a 1s interval runs at least twice in 3s without user input |
| One job runner | `runner.py`: `asyncio.Queue`, `asyncio.Semaphore(max_concurrent)`, one `asyncio.Lock` per `resource`; every job is a row in `jobs` with `job_logs` | Two jobs on `gmail` serialize; two on different resources overlap; the cap holds |
| Every scheduled task visible in one place | `tasks(name, module, interval, enabled, last_run, next_run, last_result)`; Activity MIDDLE renders it with the enable toggle; only the registry inserts rows | Every manifest schedule appears; toggling off stops submission |
| Job records are durable | SQLite WAL; `jobs` and `job_logs` survive restart; nothing is replayed because tasks are idempotent | Restart mid-queue; the failed row and its log are readable afterwards |
| Long-lived resources live in the daemon | Tokens under `data/secrets/`, cursors in the store, kernel handles in the science module's process table; no cookies, no browser storage | Grep test: `static/` never references a token or secret path |
| Idempotent, kill-safe tasks | `ctx.commit(rows, cursor=...)` is the only write path from a task and is one transaction; results are upserts keyed by source id | Kill a task between fetch and commit; the next run re-fetches from the old cursor without duplicates |
| Scheduled agent only reads | `claude.run_task` passes a read-only tool allowlist and is the only Claude entry point importable from `tasks.py`; `claude.session_turn` is reachable from `routes.py` and `session.js` only | AST scan of every `tasks.py`; allowlist excludes Write, Edit, Bash and every write MCP tool |
| Failure is local | Runner wraps each job; a raise marks that row failed with the traceback and continues; registry wraps imports | A job that raises leaves the scheduler and other modules running |
| UI is a view of daemon state | Pages fetch `/api/...` on the `refresh` setting interval and after each action; the loading line reflects in-flight fetches; nothing is computed client-side beyond layout | Fresh window renders the same data as the store with no daemon call besides reads |

Security posture: the daemon has no authentication and binds loopback only. Any process on this machine can call it. Acceptable for a single-user desktop; document it, do not solve it.

## Claude sessions

- Every session turn is `claude -p --resume <session_id> "<text>"` with the module's `agent.md` appended as system prompt and the module's tool lists applied. A new process per turn keeps the daemon free of long-lived CLI handles and makes a crash recoverable by resuming.
- Output streams as events (`text`, `tool`, `status`) over `GET /api/session/<id>/events`; the pane renders user bubbles, plain model text and `▸ tool · status` lines exactly as the artboard does.
- Sessions persist in `sessions(id, module, opened_at, closed_at, title, tags)` with transcripts in `data/sessions/<id>.jsonl`. Closing a tab enqueues a `close_session` job: one read-only headless call produces a title and tags, written to the row, which Graph reads.
- `Send to session` in the inspector prefixes the composer with the selected item's reference.
- Settings, Claude section: `claude.binary`, `claude.model`, agents dir (`app/modules`, read-only display), `claude.sessions_kept_days`, and the list of tasks that call `run_task`.

## Nightly budget

The nightly search and every other scheduled LLM task share one budget, the `[nightly]` block in `config.toml`. Runs outside the window wait for the next window. The runner refuses to start a run past `max_sessions` and records the refusal as a job result, so Activity shows `budget used today` and the reason a task was skipped. A run past `max_minutes` is killed and marked failed. This is the enforcement of "must be capped".

## Config

`config.toml` at the repo root holds every boot value; the file is the single place to change a knob.

```toml
[server]
host = "127.0.0.1"
port = 8765

[scheduler]
tick_seconds = 5
max_concurrent = 3
drain_seconds = 30

[claude]
binary = "C:/Users/gudo/.local/bin/claude.exe"
model = "default"
sessions_kept_days = 30

[data]
db = "data/otto.db"

[nightly]
window = "02:00-05:00"   # local time
max_sessions = 3         # headless runs per night, all tasks combined
max_turns = 20           # per run
max_minutes = 15         # per run
```

Live settings (start page, refresh interval, time format, rows per page, module toggles) live in the `settings` table and are edited from the Settings page. Defaults come from the artboard's props: start page `home`, page size 40 (10 to 200 in steps of 10), refresh 30s, 24h time.

## Phases

Each phase ends with something usable.

| Phase | Builds | Usable result |
|---|---|---|
| 0 Environment | Everything in the Manifest marked missing; vendored files; the verify commands | `pytest` runs; `claude -p` answers under the Max login with no API key |
| 1 Daemon core | config, store, scheduler, runner, revision, `/health`, `/api/tasks`, `/api/jobs`, `/admin/restart`, launcher, logon task | `python -m app` opens an Edge window on a page served by the daemon; a built-in `heartbeat` task runs every minute and is listed with last / next run; editing a file and relaunching restarts the daemon; closing the window stops nothing |
| 2 Shell | rail, header, loading line, tracks, shared row, Activity page, Settings page, module registry with blank states | Every rail entry renders its designed blank state; task toggles and settings persist across restarts |
| 3 Sessions and Home | `claude.py`, session pane with tabs and streaming, session persistence and tagging, Home numbers and Today lists from registered modules, nightly budget | A conversation with the home agent about today; Home shows one number per registered module |
| 4 Proving module | Memory, the only module with no external credentials: capture, list, inspector, tag, and its session | The module contract is proven end to end before any OAuth work; details in `docs/roadmap/memory/` |
| next | Email, Education, Science, Money, Graph, Database, nightly web search | Each in its own roadmap folder, plugging into the contract above |

## Tests

Kept minimal; every LLM touchpoint is mocked at the `claude.spawn` seam and a real invocation raises under pytest.

- Runner: same-resource serialization, concurrency cap, a raising job marks only its own row.
- Kill safety: a task killed between fetch and commit recovers on the next run without duplicates.
- Revision: content change alters `rev`; launcher requests restart; new process serves.
- Registry: a module whose import raises is skipped and reported; the others load.
- Read-only agent: AST scan of `tasks.py` files; allowlist excludes write tools.

## Manifest

Nothing here is assumed. Status was checked on this machine on 2026-09-07.

Present:

| Item | Version / location | Needed for |
|---|---|---|
| Python (user-wide) | 3.14.7, `C:\Users\gudo\AppData\Local\Python\pythoncore-3.14-64\python.exe` | venv base; Science kernel host |
| `.venv` | Python 3.14.7, pip 26.2.1, no packages | daemon runtime |
| git | 2.55.0 | revision history |
| Claude Code CLI | 2.1.263, `C:\Users\gudo\.local\bin\claude.exe` | every LLM call |
| Microsoft Edge | `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe` | the window |
| Task Scheduler | `schtasks.exe` | logon start |
| SQLite | 3.50.4 via stdlib `sqlite3` | the store |
| PyPI | reachable from the venv | installs below |

Missing, install into `.venv` (versions are the latest seen on PyPI on 2026-09-07):

| Package | Version | Needed for |
|---|---|---|
| fastapi | 0.141.1 | daemon routes and static files |
| uvicorn | 0.52.4 | ASGI server |
| pytest | 9.1.1 | tests |
| httpx | 0.28.1 | route tests and the launcher's health check |
| google-api-python-client | 2.200.0 | Email module (deferred to that module's phase) |
| google-auth-oauthlib | 1.4.1 | Gmail OAuth flow (same) |
| jupyter-client | 8.10.0 | Science module kernels (same) |
| nbformat | 5.11.1 | Science module notebooks (same) |

Missing, install into the user-wide Python: `ipykernel` (Science kernels run there, not in the venv; pin the version when installing).

Missing, vendored files (one-time download, pinned in `app/static/vendor/VERSIONS`):

| File | Source | Needed for |
|---|---|---|
| `preact.mjs`, `htm.mjs` | preact and htm releases | frontend without a build |
| Inter 400 / 500 / 600 woff2 | Inter releases | body type |
| JetBrains Mono 400 / 500 woff2 | JetBrains Mono releases | stamps, code, numbers |

Missing, created by you (not installable):

| Item | Where | Needed for |
|---|---|---|
| Google Cloud project with the Gmail API enabled and an OAuth client of type Desktop; `client_secret.json` | `data/secrets/` | Email module. Two consents: `gmail.readonly` for scheduled tasks, `gmail.modify` for user actions |
| Task Scheduler entry `Otto` | created by `python -m app setup` | logon start |

Verify before Phase 3 (run, do not assume):

| Check | Command |
|---|---|
| Headless CLI works under the Max login with no API key in the environment | `claude -p "say ok" --output-format json` with `ANTHROPIC_API_KEY` unset |
| Tool allowlist and resume flags on this CLI version | `claude --help`; confirm the flags used by `claude.py` |
| Web search is available headless (nightly search depends on it) | a one-line headless prompt that must search |
| `claude-agent-sdk` 0.2.152 (PyPI) is covered by the subscription | only if the CLI path proves insufficient; otherwise not installed |

Not needed: Node.js or npm, APScheduler, an Anthropic API key, pywebview or WebView2, a graph database.

Not covered: LinkedIn message monitoring has no supported API; the Business module plan must decide whether to drop it.

## Pending decisions

1. `roadmap/` at the repo root holds empty per-module folders; this plan lives in `docs/roadmap/`. Pick one location.
2. The artboard has one `Money` module; ARCHITECTURE and the roadmap folders have Finance and Business. The rail is registry-driven, so either works; decide in those module plans.
3. The session tab strip is a deviation from the artboard (see Frame contract).
4. `Personal operating dashboard UI.zip` at the repo root duplicates `docs/design/`.
