# Architecture

## Summary

Dashboard wherein each module has a "left/middle/right" structure. The left hand side is almost always an index of information which can be selected; files, emails, tables/schema, etc.
The middle is the main interaction/use of the module, which displays the main outputs or selections. The right hand side is always an agentic window, typically used for module specific agents actions. Multiple conversations should be spawnable/selectable via tabs; whenever a session closes, the agent should 1. tag the conversation with high level metadata identifiers and then persist in a place reachable by Graph module 

### What runs today

Otto is a Python 3.14 daemon plus a disposable browser window. The daemon keeps every module's state current on a schedule; the window renders that state and holds none of it. One session per module is open at a time; `/clear` closes it, tags it, and starts a fresh one. Known findings live one file each in `docs/bugs/` (code does the wrong thing), `docs/defects/` (built as designed, but wrong for the owner) and `docs/gaps/` (requirement or artboard element not met yet).

| Piece | What it is |
|---|---|
| Daemon | FastAPI + uvicorn on `127.0.0.1:8765`, started detached under `pythonw`, logging to `data/daemon.log`; loopback only, no authentication |
| Window | Google Chrome in app mode on its own profile in `app/.chrome-profile/`, first-run, default-browser and sync prompts off. The app never touches Microsoft Edge |
| Store | one SQLite file `data/otto.db` in WAL mode, platform and module tables together, timestamps as UTC ISO strings |
| LLM | the Claude Code CLI (2.1.263) headless under the owner's claude.ai Max login; no API key exists anywhere in the app |
| Frontend | static ES modules, Preact + htm vendored, inline styles ported from the artboard; no build step, no Node |
| Modules built | Home, Email, Education, Memory, Finance, Business, Graph, Database have pages; System and Feedback have none. The rail shows only modules whose package exists |

Run: `python -m app` checks the port and code revision, starts or restarts the daemon, then opens the window. `python -m app setup` registers the Windows Task Scheduler entry `Otto` that starts the daemon at logon. `python -m app status` prints health. `python -m app.modules.email.gmail consent` runs the Gmail OAuth flow once and writes the token file. Tests: `.venv/Scripts/python.exe -m pytest -q`, offline; the CLI is mocked at `app.claude.spawn` and a real invocation raises.

```
app/__main__.py   launcher: open | setup | status | daemon
app/daemon.py     app factory, lifespan, detached start, port wait, restart
app/api.py        platform routes: health, restart, shell, tasks, jobs, events, settings, data, sessions
app/config.py     config.toml -> typed Config; every key required, missing keys fail at boot
app/store.py      SQLite connection, settings, cursors, events, backup;  app/schema.sql: platform tables
app/scheduler.py  manifests -> tasks rows; submits due tasks; nightly window
app/runner.py     one queue, per-resource locks, worker count = cap, job rows and logs
app/revision.py   sha256 of app/** and config.toml, served by /health
app/claude.py     CLI spawn, event stream, read-only allowlist, nightly budget
app/modules/      registry, agent_base.md, one package per module (contract under Daemon)
app/static/       index.html, shell.js, session.js, rows.js, api.js, feedback.js, pages/<name>.js, vendor/
data/             otto.db, daemon.log, secrets/, workspace/, backups/ (all gitignored)
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
| Daemon owns the clock | `Scheduler.sync_tasks` turns manifest schedules into `tasks` rows and deletes rows no manifest declares; `tick` every `tick_seconds` submits enabled tasks whose `next_run` passed. LLM tasks become due only inside `[nightly] window` and are re-armed for the next window start | `test_sync_creates_rows_and_removes_orphans`, `test_tick_submits_due_and_advances`, `test_window_logic` |
| One job runner | `Runner`: one queue, `max_concurrent` workers, one lock per `resource`, a `jobs` row per job (`scheduled`, `action`, `session`) with `job_logs`. Routes run user actions through `run_action` and await the result. Rows left `queued` or `running` by a crash are marked failed at start | `test_same_resource_serializes_and_different_overlap`, `test_cap_holds` |
| Every scheduled task visible | `tasks(name, module, interval_seconds, resource, llm, enabled, last_run, next_run, last_status, last_result)`; Activity renders it with the toggle (`POST /api/tasks/{name}`) | `test_disabled_and_missing_module` |
| Durable job records | SQLite WAL; jobs, logs, events, sessions survive restarts; nothing is replayed | `test_skipped_and_logs_and_commit` |
| Resources in the daemon | tokens under `data/secrets/`, cursors in `cursors`, Claude runs as child processes of the daemon; the page holds nothing | — |
| Idempotent, kill-safe tasks | a task's only write path is `ctx.commit(cursor=...)`: results and the new cursor in one transaction | `test_skipped_and_logs_and_commit` |
| Scheduled agent only reads | `ctx.run_task` is the only Claude entry point a task can reach: read server, read-only built-ins, budget. `session_turn` and `oneshot` are reachable from routes only | `test_tasks_never_reach_interactive_claude`, `test_read_builtins_exclude_writers` |
| Failure is local | the runner catches per job (row failed, traceback in `error`, an `events` row); the registry records a broken module in `module_errors` and the rail shows it disabled with the error | `test_failure_is_local`, `test_registry_skips_broken_module` |
| UI is a view | pages fetch `/api/...` on the refresh interval and after every action; the loading line reflects in-flight fetches; the session pane subscribes to server-sent events | `test_memory_end_to_end` |

### Config

`config.toml` holds boot values; changing one means relaunching. Live settings are seeded from `[ui]` into the `settings` table on first start and edited on the Settings page afterwards (`PUT /api/settings`, keys `ui.*` and `modules.<name>.enabled`).

| Section | Keys |
|---|---|
| server | host, port |
| scheduler | tick_seconds, max_concurrent, drain_seconds |
| claude | binary, model (`default` keeps the CLI's own choice), sessions_kept_days |
| data | db, workspace (working directory of every Claude run; file tools are confined to it) |
| nightly | window (local time), max_sessions per day, max_turns and max_minutes per run |
| business | leads_per_run |
| memory | suggest_lookback_days, suggest_max |
| education | queue_size, start_difficulty, flow_low, flow_high |
| database | max_rows, max_seconds |
| email | client_file, token_file, backfill_days, triage_batch |
| feedback | max_turns |
| ui | start_page, refresh_seconds, time_format (`24h` or `12h`), page_size, side_max, middle_max |

### Claude

Every run is one CLI process with the prompt on stdin and `--output-format stream-json --verbose`, launched with `--setting-sources ""`, `--restricted`, `--strict-mcp-config`, `--permission-prompts none`, `--tools Read,Grep,Glob,WebSearch,WebFetch`, `--allowedTools` for those plus the module's MCP tools, and `--system-prompt`. The environment is scrubbed of every `ANTHROPIC_*`, `CLAUDECODE*` and `CLAUDE_CODE_*` variable. Any run past `max_minutes` is killed. Verified on this machine: the CLI answers with no API key set, and the owner's global CLAUDE.md does not reach these runs.

| Path | Who | MCP server | Extra flags |
|---|---|---|---|
| `run_task` | scheduled tasks via `ctx.run_task` | `otto-read` at `/mcp/read`: read tools only | `--max-turns <nightly.max_turns> --no-session-persistence`; raises `BudgetExceeded` outside the window or past `max_sessions` |
| `session_turn` | session routes | `otto` at `/mcp/full`: read and write tools | `--session-id` on the first turn, `--resume` after |
| `oneshot` | session close, Feedback filing | `otto-read` | `--no-session-persistence`, the caller's `--max-turns` (2 for a close, `feedback.max_turns` for a filing) and only the tools the caller names; not counted against the budget |

System prompt: `app/modules/agent_base.md` (shared rules) + the module's `agent.md` + a Current state block from the module's `context(store, registry)` hook, rendered fresh every turn.

Budget: `llm_runs` rows with `budgeted = 1` are counted per local day against `max_sessions`; Activity shows runs used, the window, and whether it is open now.

Sessions: `sessions(id, module, opened_at, closed_at, title, tags, cli_started)` and `session_turns(role user|model|tool|system, text, tool, status)`. A turn is a job of kind `session` on resource `session:<module>`, so turns serialize per module; its events (`user`, `model`, `tool`, `tool_result`, `result`, `error`, `idle`) stream over `GET /api/session/<module>/events`. `/clear` enqueues a close job: `oneshot` returns `{"title", "tags"}` written to the row (fallback: first user line, no tags), plus a `closed` event; Graph reads `sessions.tags`. A first turn that fails retires its session row so the next turn starts clean. Any other message starting with `/` is passed to the CLI unchanged, so Claude Code commands and skills work from the pane.

MCP servers are `mcp` 2.2.0 `MCPServer` instances mounted stateless with JSON responses; module `tools.py` files register read tools on both servers and write tools on `otto` only.

### Module contract

A module is a package `app/modules/<name>/` plus `app/static/pages/<name>.js`. The registry imports every package; one that raises is recorded in `module_errors` and skipped.

| File | Obligation |
|---|---|
| `__init__.py` | `MANIFEST = Manifest(name, title, hue, icon (SVG inner markup, 20x20), order, schedules=(Schedule(task, every "60s\|15m\|24h", resource, llm),), agent=Agent(placeholder, skills, read_tools, write_tools), page=True)` |
| `schema.sql` | the module's tables, applied at boot |
| `tasks.py` | `async def <task>(ctx)` per schedule; `ctx.store` (read), `ctx.commit(cursor=...)` (the only write), `ctx.log`, `ctx.event`, `ctx.run_task(prompt, tools)`; return a string, or `Skipped("why")` |
| `routes.py` | `router = APIRouter(prefix="/api/<name>")` with `GET left`, `GET item/{id}`, `POST action/{verb}` (through `runner.run_action`), plus hooks `numbers(store) -> {value, label}`, `today(store) -> rows`, `queue(store) -> rows` (everything still waiting on the owner; Home lists every one), `item(store, id)`, `context(store, registry) -> str`. Route handlers must not share a hook's name |
| `tools.py` | `register(read, full, store, config)`: read tools on both servers, write tools on `full` |
| `agent.md` | the agent's job in the owner's terms |
| `pages/<name>.js` | `load(app)`, `meta(app)`, `Left({app, data, mod, fmt})`, `Middle({app, data, mod, fmt})` returning Preact nodes; the shell owns rail, header, tracks and the session pane |

Wire shape for LEFT: `{groups: [{label, count, rows: [{id, module, text, stamp, leading?: {kind|dot|ext|pct}, done?}]}], chips?, chip?, showing?, more?}`. External systems follow one pattern: tasks get a read client, action routes get a write client, and a test proves the split.

### Platform tables

`tasks`, `jobs`, `job_logs`, `settings` (JSON values), `cursors`, `events(ts, module, verb, text, job_id, ref)`, `sessions`, `session_turns`, `module_errors`, `llm_runs(ts, module, task, job_id, status, minutes, session_id, budgeted)`.

### Dependencies

| Item | Version / location |
|---|---|
| Python | 3.14.7, `.venv` from the user-wide install at `C:\Users\gudo\AppData\Local\Python\pythoncore-3.14-64\python.exe` |
| fastapi, uvicorn, mcp, httpx, pytest | 0.141.1, 0.52.4, 2.2.0, 0.28.1, 9.1.1 (`requirements.txt`) |
| Claude Code CLI | 2.1.263 at `C:\Users\gudo\.local\bin\claude.exe`, claude.ai login, subscription max |
| Google Chrome | found through the `App Paths\chrome.exe` registry key |
| SQLite with FTS5 | 3.50.4, stdlib |
| Vendored frontend | `app/static/vendor/`: preact.mjs, htm.mjs, Inter 400/500/600, JetBrains Mono 400/500, pinned by `SHA256SUMS` |
| Google OAuth client and token | `data/secrets/google_client.json` (web client, redirect `http://localhost:8756/m/email/api/oauth/callback`), `data/secrets/token.json`, scope `gmail.modify`, refreshed in place |

Not used: Node, APScheduler, pywebview, `claude-agent-sdk`, an Anthropic API key, paid search APIs, a graph database, Microsoft Edge.

## High level module Functionality

### Home page

1. Shows very high summaries
2. Shows any web search items found via nightly search which are immediately relevant; adds to a queue and creates a record once agreed/disagreed with; i.e. nightly search could return 3 results; at the end of the week there are 21 items to review. 

Built: `GET /api/home/numbers` (one number per enabled module with a `numbers` hook) and `GET /api/home/left`, which puts a `Review` group per module with a `queue` hook first, every waiting row and no cut, then each module's `today` rows, five per module with a `+N` link into the module. Groups are keyed `label:module`, so one module can yield both. MIDDLE blank state is the number grid; selecting a row opens the owning module's item inspector and posts its verbs. The Home agent has no tools; its Current state block carries the same numbers, today rows and `Review: N waiting` lines.

#### Nightly Process

Web search to gather data on anything that could potentially help me in my life; obvious ones; items displayed on homepage.

1. Previously scheduled follow ups
2. Investment news/sector news/legislation etc. Should track potential follow-ups and schedule them for the future. 
3. New techniques/algorithms/research relevant to my research, career, etc. 
4. Topics of learning/question sources 

MUST BE CAPPED TO SOME REASONABLE DEGREE; I am using usage associated with CLAUDE MAX account, but do not want to incur any other api charges, nor do I want to use all of my weekly tokens in 2 days. 

The `[nightly]` budget caps every scheduled LLM run.

### E-mail

1. Uses gmail OAuth
2. Search bar/full ability to interact with inbox (Google chrome behaves very strangely when trying to do bulk deletes; I would like to resolve by explicitly using API here)
3. Agent only performs triage&sorting, prioritization and flagging of relevant items
4. Agent does NOT have the ability to write nor delete on its own. This needs to be a HARD CONSTRAINT determined by tooling or gmail api implementation. 

Built:

| Piece | Current state |
|---|---|
| Tables | `email_messages(id Gmail id, thread_id, from_name, from_addr, subject, snippet, internal_date, labels JSON, body_text)`, `email_triage(message_id, priority high\|normal\|low, reason, source)`, `email_fts` (FTS5, trigger-maintained) |
| Routes | `left` (query, chips All/Unread/Flagged/Priority, page), `blank` (mailbox counts), `item/{id}` (fetches and stores the body on first open), `action/{archive\|trash\|read\|unread\|star\|unstar}` on one id or on every message matching the current query and chip |
| Hooks | `numbers` (unread), `today` (inbox mail of the local day), `item`, `context` (counts, last sync, ten newest, high-priority with reasons) |
| Tools | read: `email_search`, `email_get`, `email_triage`; write: `email_flag`, which writes Otto's triage row. No tool reaches Gmail |
| Schedules | `email.sync` every 5m on resource `gmail`: first a `backfill_days` backfill committed in pages of 100 under a resumable cursor, then Gmail history from `email.history`. `email.triage` every 24h inside the nightly window prioritizes `triage_batch` untriaged inbox messages |
| Gmail | `GmailRead` for tasks and body fetches; `GmailWrite` adds `batchModify` and is reachable only from action routes. A quota refusal pauses every call in flight together and retries |
| Page | LEFT: search, chips, rows by day as `sender: subject`; MIDDLE blank: counts and the bulk bar over the current filter; MIDDLE selected: sender, body, priority and reason, `Archive`, `Trash`, read/unread, star/unstar, `Open in Gmail` |
| Departures | `Priority` chip added; no `Reply` (no compose) and no `Snooze` (no API); the blank state is unspecified in the artboard |

### Education

1. Aimed towards teaching concepts and high level understanding; minimal algebra/derivations as it is hard to type by hand.
2. Has a corpus of topics/questions manageable via database. 
3. Progress tracker
4. Aims for "flow state"; balance of difficulty and understanding determined by score range. 
5. Agent grades answers, makes notes of past performance, uses as context when creating future questions, takes into account feedback.
6. Must provide clearly worded questions, must introduce any equations as part of premise/prompt
7. Questions should be 3-5 parts each; every part should be intimately related with the original question
8. "Grading" should allow for back and forth communication; i.e. answer given -> LLM response
   
#### Education Constraints

1. Breadth over depth; do not repeat the same questions over and over again, even if I get them wrong. 
2. Topics covered should include
   1. Probability and statistics
   2. Agentic AI
   3. Deep learning
   4. Machine Learning
   5. Natural Language Model/Processing
   6. Reinforcement Learning
   7. Modern time series forecasting and foundational models
   8. Causal Inference
   9. Mathematics
   10. Optimization and decision science
   11. Physics
   12. Supply chain optimization
   13. Robotics
   14. Quantitative finance
3. On demand: pursued when there is time, with an anticipation of 3 questions per day. Nothing is scheduled to a date.
4. Progress and score are tracked by domain, one per topic above.
5. New tech (pick a new technology, see if I can understand how it works): a separate roadmap item, `docs/roadmap/new-tech/`.

Built:

| Piece | Current state |
|---|---|
| Tables | `topics(name, description, difficulty 1-5, retired_at)`, `questions(topic_id, title, premise, difficulty, source nightly\|session, started_at, graded_at, skipped_at, score)`, `question_parts(question_id, n, text, score 0-100, note)`, `education_feedback` (the owner's words, unchanged) |
| Routes | `left` (the due queue, then history by day, search, page), `blank` (progress per topic, add-topic box), `item/{id}`, `action/{start\|skip\|add_topic\|retire_topic}` |
| Hooks | `numbers` (due), `today` (the due queue), `item`, `context` (per topic: difficulty, graded/asked, average, recent scores; the started question with every part and its grade; recent feedback verbatim) |
| Tools | read: `education_topics`, `education_questions`, `education_question`, `education_feedback`; write: `education_add_topic`, `education_add_question`, `education_grade`, `education_record_feedback` |
| Schedule | `education.generate` every 24h inside the nightly window: tops the open queue up to `queue_size`, one question for each topic that has waited longest, rejecting a repeated title or a malformed part list |
| Flow | a new topic starts at `start_difficulty`; a completed question averaging below `flow_low` drops its topic one step, above `flow_high` raises it, floor 1 and ceiling 5 |
| Page | LEFT: search, the `due` group, then history by day with the score as a progress bar; MIDDLE blank: a row per topic with difficulty, graded/asked, average and recent scores, plus the add-topic box; MIDDLE selected: premise, numbered parts with score and note, the owner's feedback lines, `Start` or `Skip` |
| Departures | `Reschedule` dropped (nothing is scheduled to a date); LEFT leads with `due` instead of grouping everything by date; the blank state is unspecified in the artboard |

### Memory

1. General note taking/to-do list/journaling module
2. Typically a dumping ground for random ideas/notes I have
3. Agent aimed at consolidating/collecting thoughts, must be very literal and not reword items/add to them. Can suggest action items based on current state/discoveries, never makes suggestion more than onces. 

Built:

| Piece | Current state |
|---|---|
| Tables | `memories(kind note\|link\|quote\|fact\|task, text, created_at, updated_at, done_at)`, `memory_tags`, `memory_suggestions(text unique, memory_ids, status open\|accepted\|dismissed)`, `memories_fts` (FTS5, trigger-maintained) |
| Routes | `left` (query, chip All/Notes/Links/Quotes/Facts/Tasks, page), `blank` (kinds, counts, open suggestions), `item/{id}`, `action/{capture\|forget\|tag\|untag\|done\|suggestion}` |
| Hooks | `numbers` (total), `today` (captures of the local day), `item`, `context` (counts, last ten, open suggestions) |
| Tools | read: `memory_search`, `memory_get`, `memory_tags`, `memory_suggestions`; write: `memory_add`, `memory_tag`, `memory_suggest` (records a suggestion so it is never repeated) |
| Schedule | `memory.suggest`, every 24h inside the nightly window, resource `memory`: proposes up to three action items from the last seven days as JSON, inserted with `INSERT OR IGNORE`, cursor `memory.suggest` |
| Page | LEFT: search, kind chips, rows by day with the kind as leading slot; MIDDLE blank: capture box (kind chips, textarea, tags, `Save`, Ctrl+Enter) and open suggestions with `Accept` / `Dismiss`; MIDDLE selected: inspector with tags (add on Enter, click to remove), `Open` for links, `Done` for tasks, `Forget` |

### Science

1. Interface for scientific experiments via .py or .ipynb; 
2. Uses user-wide python C:\Users\gudo\AppData\Local\Python\pythoncore-3.14-64\python.exe
3. Agent is able to help read/debug notebooks, look at outputs/clean up files, etc; essentially a personalized jupyter + agent interface because I don't like how VSCode handles kernels.  

### Finance

1. General place for me to organize important information regarding anything money related; budget/recurring subscriptions/payments, stock/investment info (not direct link to account, just a proxy with manual inputs)
2. Agent should be able to be asked general questions regarding finances; i.e. natural language queries. 

Built:

| Piece | Current state |
|---|---|
| Tables | `finance_entries(kind account\|recurring\|holding\|budget, name, amount in cents, cadence monthly\|yearly\|weekly, note, ended_at)`, `finance_amounts` (every value the entry has held) |
| Routes | `left` (query, chips All/Accounts/Recurring/Holdings/Budgets), `blank` (totals, kinds, cadences, counts), `item/{id}` with the amount history, `action/{capture\|update\|end\|forget}`, each validated before the job is queued |
| Hooks | `numbers` (active records), `today` (entries touched in the local day), `item`, `context` (the four totals and every active entry) |
| Tools | read only: `finance_list`, `finance_get`, `finance_totals`. The manifest declares no write tools |
| Totals | recurring and budget amounts normalize to a month as yearly / 12 and weekly x 52 / 12; accounts and holdings sum as entered |
| Page | LEFT: search, kind chips, one group per kind with the amount in the stamp slot and a dot for active; MIDDLE blank: the totals and the capture form; MIDDLE selected: the entry, its amount history, `Update`, `End`, `Forget` |
| Departures | the artboard's Money page was a document list, now Business: chips are the four kinds, rows group by kind rather than day, item actions are `Update` / `End` / `Forget` |

### Business

1. Houses business plans/networking (people, events, etc.)/documents
2. Finds/Tracks items immediately relevant to current pursuits, recommendations based on career improvement, business plans, job openings that are realistic, automated; 

Built:

| Piece | Current state |
|---|---|
| Table | `business_items(kind plan\|person\|event\|document\|lead, text, ref, why, status open\|accepted\|dismissed)`, unique on `(kind, ref)`; `ref` is a URL for a lead and an absolute path for a document |
| Routes | `left` (query, chips per kind), `blank` (counts and the open leads), `item/{id}`, `action/{capture\|forget\|lead\|open}` |
| Hooks | `numbers` (open leads), `today` (items created in the local day), `item`, `context` (counts, every plan verbatim, open leads, document paths) |
| Tools | read: `business_search`, `business_get`, `business_leads`; write: `business_add`, `business_lead` |
| Schedules | `business.index_documents` every 15m mirrors the files in `data/workspace/business/` as `document` rows and drops rows whose file is gone. `business.scout` every 24h inside the nightly window searches the web against the owner's plans and queues up to `leads_per_run` new leads, never repeating a url |
| Page | LEFT: search, chips, rows by day with the file extension as the leading slot for documents; MIDDLE blank: the capture box and the lead queue; MIDDLE selected: the item, its reason and url, `Accept` / `Dismiss` for a lead, `Open` for a document |
| Departures | chips are the five kinds rather than the artboard's `Accounts, Plans, Documents` (accounts are Finance); `Summarize` and `Share` dropped; the blank state is unspecified in the artboard |

### Database

1. Module which interfaces with underlying DBs to allow for manual querying/editing of data to give visibility
2. Agent is natural language interface for creating queries
3. Agent has in depth knowledge of database schema. 

Built:

| Piece | Current state |
|---|---|
| Table | `db_queries(name unique, sql)`: the queries the owner or the agent kept |
| Reads | every statement runs on a second SQLite connection opened `mode=ro`, so a write fails inside SQLite and nothing parses SQL. At most `max_rows` rows come back and a statement past `max_seconds` is interrupted; an error comes back as text, not a failed job |
| Routes | `left` (user tables with row counts, shadow tables of virtual tables hidden, then the saved queries), `blank` (store path and size), `action/{run\|explain\|save\|delete}` |
| Hooks | `numbers` (store size), `context` (every table with its columns and row count) |
| Tools | read: `db_schema`, `db_query`, `db_explain`; write: `db_save_query`, which only adds a row to `db_queries` |
| Page | LEFT: tables with counts, then `saved`; MIDDLE: the SQL editor, `Run` / `Explain` / `Save`, the result grid with paging and the timing line |
| Departures | `Export` is not built; grid columns come from the query rather than the artboard's fixed five; `Save` and a `prev` link are added for saved queries and paging |

### Graph

1. A knowledge graph which picks up any items which were explicitly tagged via the other modules; entirely a read-only/view-only insight layered on top of data generated elsewhere.    
2. Agent serves as natural language interface for graph data. 
3. Agent has ability to query, clean/consolidate/delete nodes/edges from the graph; i.e. it is the graph architect  

Built:

| Piece | Current state |
|---|---|
| Sources | every tag on a memory and on a closed session, lowercased and stripped, so `GRADient` and `gradient` are one node. Graph never writes those tables |
| Tables | `graph_nodes(tag, count, memories, sessions, last_seen)` and `graph_edges(a, b, kind cooccur\|link, weight)`, both replaced whole on each rebuild; the curation overlays `graph_merges`, `graph_pruned` and `graph_links` survive it |
| Routes | `left` (tags by count, search, page), `graph` (the visible nodes, the edges among them, build time and totals) |
| Hooks | `numbers` (nodes), `context` (totals, the ten largest tags, merges, prunes, curated link count) |
| Tools | read: `graph_nodes`, `graph_neighbors`, `graph_items`; write: `graph_link`, `graph_unlink`, `graph_merge`, `graph_prune`, `graph_restore`, each rebuilding afterwards |
| Schedule | `graph.rebuild` every 15m, plain SQL and no LLM: tags on the same item become a `cooccur` edge weighted by shared items, a curated link an edge of weight 1 |
| Page | LEFT: search and tags by count; MIDDLE: a ring of nodes with their edges, selecting a tag lights its neighbours |
| Departures | `extract-entities` chip dropped and `neighbors` added; ring radius comes from a hash of the tag so a node stays put when the list reorders; counts are live |

### System (no page)

`system.heartbeat` every 60 s proves the clock runs; `system.prune_sessions` every 24 h deletes closed sessions older than `sessions_kept_days`.

### Feedback (no page)

A `feedback` control in the header of every page records a change the owner wants, together with the selected item when there is one. `POST /api/feedback/action/add` writes the row and queues a filing job on resource `feedback`; `retry` requeues a failed one. The filing job is a `oneshot` run with `feedback.max_turns` and the read tools `docs_list`, `docs_read` (markdown under `docs/` only) and `feedback_list`. The agent replies with one JSON object and the route writes it to the row: `kind` (bug, defect, gap or roadmap), `title`, `summary`, `tags`, `ref` (the existing `docs/` file it belongs in) and `draft` (the body ready for that file, with the owner's words quoted). A reply that is not that object marks the row `failed` with the error. `GET /api/feedback/recent` feeds the panel and `GET /api/feedback/list` gives every field to any agent. Nothing touches the repo; the row is the record.

### Activity and Settings (shell pages)

Activity: LEFT is the `events` log by day with a chip per module; MIDDLE blank state is the task table with its toggles, the nightly budget line, and the last fifty jobs; selecting an event shows its job's result, error and log. Settings: General (start page, refresh, time format, rows per page), Modules (a toggle per module; a failed module shows its error), Claude (binary, model, agents dir, workspace, sessions kept, background jobs; read-only), Data (database path and size, last backup, `Back up now` through the SQLite backup API into `data/backups/`, `Vacuum`).

## UI

Follows style of, but not limited to, the Claude Design project `9459ddf2-3c53-45d8-9252-7a17bd027bf4` (`Personal Dashboard App.dc.html`). The artboard and its runtime are imported to `docs/design/`; open the html in a browser to run it.

### Frame contract

Every page uses three fixed tracks. Selection swaps what renders inside MIDDLE and never moves a track.

| Region | Spec |
|---|---|
| Rail | 56px wide, 32px icon buttons (20px SVG, stroke 1.5), 6px gap, 14px top padding; active background `#23262c`; Activity and Settings pinned at the foot |
| Header | 48px, padding `14px 32px 0`, 20px/600 title, mono 13px meta in `#5f636c` |
| Loading line | 1px, margin `0 32px`; a 30% `#8b8f98` bar animates `translateX(-100% to 340%)` over 1.2s while a fetch is in flight |
| Tracks | `clamp(220px,22.8%,ui.side_max) minmax(300px,1fr) clamp(220px,22.8%,ui.side_max)`, gap `0 24px`, padding `19px 24px 24px`; opacity fades out and in over 120ms on page switch. 22.8% is the artboard's 4/17 side share, so the tracks match it until the ceiling bites (~1950px wide); past that the sides hold and MIDDLE takes the surplus |
| LEFT | panel `#1a1c21`, radius 6, padding `12px 8px 24px`: search (36px, `#23262c`, 1px focus ring in the hue), chips, groups of one-line rows with a stamp |
| MIDDLE | ground, padding `8px 16px 40px`, content `min(100%, ui.middle_max)` centred: the module's blank state or the item inspector. Prose (the inspector, Activity's detail) holds a `72ch` measure inside that |
| RIGHT | panel, padding `16px 12px 12px`: the session pane, identical on every page |

| Token | Value |
|---|---|
| Ground / panel / raised | `#101114` / `#1a1c21` / `#23262c` (selection, inputs, user bubbles) |
| Text / muted / dim | `#e6e7ea` / `#8b8f98` / `#5f636c` |
| Hairline / row hover / table row hover | `rgba(230,231,234,.08)` / `#202329` / `#16181c` |
| Hues and rail order | home `#e6e7ea` 0, email `#cf7b7b` 1, education `#7a9fd6` 2, memory `#d1a36a` 3, science `#6fb3b8` 4, finance `#7fb894` 5 (the artboard's Money hue and banknote icon), business `#c98ba8` 6 (not in the artboard; briefcase icon), graph `#b3b06a` 7, database `#a68bd0` 8 |
| Type | Inter 15px/1.4 body, 13px meta, 20px/600 title; JetBrains Mono 13px stamps and code, 28px/500 numbers; vendored with `system-ui` / `ui-monospace` fallbacks |
| Rows | 36px list rows, 32px compact rows, 28px group headers, padding `0 12px`, gap 12px, radius 6; leading slot is a kind label (40px, hue), a 6px dot, an extension, or a 40px progress bar |
| Chips / buttons | padding `3px 9px` / `5px 10px`, radius 6, 13px; active or primary is hue background with `#101114` text; inactive or secondary is `#8b8f98` text with a 1px inset ring on hover |
| Toggle | 28x16 track, 12px knob; on `#e6e7ea` / `#101114`, off `rgba(230,231,234,.14)` / `#8b8f98` |
| Stamps | same day shows the time (`ui.time_format`), otherwise `05 Sep`; group labels are `05 Sep` |

Session pane: header is a 6px hue dot plus `claude · <module>`; skill chips; user turns are raised bubbles aligned right at max 85% width, model turns plain text at line-height 1.6, tool calls one mono line `▸ tool · status`; a 3-row composer with the context label, `new` (sends `/clear`) and a send button; Enter sends, Shift+Enter breaks a line.

Item inspector: 16px hue glyph, kind and time in mono, `×` to clear, the body, then a primary action in the hue, secondary actions, and `Send to session` right-aligned, which prefills the composer with the item's reference.

### Departures from the artboard

- One session per module, no tab strip.
- Memory's blank state (capture box) is not in the artboard, which left it unspecified.
- Activity's MIDDLE blank state is the task table, required by the Daemon section.
- Settings, Data: `Export` is not built.
- Finance and Business are separate modules; the artboard had one `Money` entry.
- The rail shows only built modules.
- The `feedback` control in the header and its panel are not in the artboard; they reuse the header meta style, the panel surfaces, the composer textarea and compact rows.
