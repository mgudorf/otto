# Feedback Plan

Status: planning, 2026-09-08.

A `feedback` control in the header of every page lets the owner record a change they want the moment they notice it, without leaving the window. A standalone Feedback agent reads each note, decides whether it is a bug, a defect, a gap or a roadmap request, and writes that file under `docs/`; the note itself is kept verbatim with a one-line digest and tags so later passes can mine it for rules. Without it every idea means opening VS Code, and most ideas are lost before that happens.

## Sources

| Source | Governs |
|---|---|
| The request (this session) | A control on every page; a standalone agent classifies and writes the item; writes are markdown only, under `docs/` only; every note recorded and compacted for later LLM insight |
| `docs/ARCHITECTURE.md` › Daemon requirements, Mechanisms, Claude, Module contract | Writes happen only from user actions; scheduled runs read; the CLI's built-in tools are `Read, Grep, Glob, WebSearch, WebFetch` confined to `data/workspace`; write MCP tools live on the `otto` server only |
| `docs/ARCHITECTURE.md` › UI frame contract, Activity | Header spec, tokens, rows, buttons; Activity lists `events` by module |
| `docs/design/Personal Dashboard App.dc.html` lines 37–41, 311–333 | Header markup; the session composer the panel borrows from |
| `.claude/skills/sync-architecture/SKILL.md` step 4 | The finding taxonomy and file shape the agent writes: `docs/bugs/`, `docs/defects/`, `docs/gaps/` |
| `.claude/skills/create-roadmap-item/SKILL.md` step 1 | One plan per slug; an existing `PLAN.md` is updated, never duplicated |
| `app/claude.py`, `app/runner.py`, `app/api.py`, `app/daemon.py` | `_args`, `oneshot` (user-triggered, unbudgeted), `submit` without await (`/clear` precedent), tool registration |
| `app/modules/memory/{tools.py, routes.py, agent.md}`, `app/modules/system/__init__.py` | The built pattern for write tools, action routes, and a `page=False` module |
| `app/static/shell.js`, `session.js`, `rows.js`, `api.js`, `pages/activity.js` | The header, the composer pattern, compact rows, `post` |
| `docs/roadmap/education/PLAN.md` line 112 | Names a module table `feedback`; one SQLite namespace |
| `tests/test_app.py`, `tests/conftest.py`, `tests/test_platform.py` | Fake CLI stream, route tests through `build(config)`, the tool-split guard |

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | Feedback is a module `app/modules/feedback/` with `page=False`: manifest, `schema.sql`, `routes.py`, `tools.py`, `agent.md`; no rail entry, no page, no schedule | The module contract already gives an agent its prompt, tools and Current state; `page=False` keeps it off the rail (System precedent). The control lives in the shell because it must be on every page |
| 2 | The agent may write only through `docs_write(kind, slug, text)`, a tool on the `otto` server whose path is derived: `bug → docs/bugs/<slug>.md`, `defect → docs/defects/<slug>.md`, `gap → docs/gaps/<slug>.md`, `roadmap → docs/roadmap/<slug>/PLAN.md`; `slug` must match `^[a-z0-9][a-z0-9-]{1,60}$` | Markdown only and `docs/` only by construction, not by prompt: the CLI never gets its Write tool, and no free path exists. Memory's `memory_add` proves write tools reach the agent today |
| 3 | Read tools `docs_list()` (every `.md` under `docs/`, with size and mtime) and `docs_read(path)` (any `docs/**/*.md`, resolved inside `docs/`) | Classification needs `ARCHITECTURE.md` and the existing findings and plans; updating beats duplicating. The CLI's file tools cannot leave `data/workspace` |
| 4 | A note is a user action: `POST /api/feedback/action/add` inserts the row `queued` and submits a job (`feedback.file`, resource `feedback`, kind `action`, not awaited) that runs the agent; the route returns at once | Writes to `docs/` are user-triggered, never scheduled; the runner's resource lock files notes in order; the window never waits on a Claude run |
| 5 | New Claude entry point `agent_run(ctx, mod, prompt)`: `otto` server, the module's read and write tools, `--max-turns [feedback] max_turns`, `--no-session-persistence`, `llm_runs` row with `budgeted = 0` | Neither `run_task` (read server, nightly budget) nor `session_turn` (a persistent session) fits a one-shot user-triggered run that writes. Unbudgeted like session-close tagging |
| 6 | The agent's final reply is JSON `{kind, path, summary, tags}`; the job verifies `path` exists under `docs/`, then sets the row `filed` with those fields; a bad reply or a missing file sets `failed` with the error | The row is the record; the file is the item. Verifying the file makes "filed" mean the file exists |
| 7 | Every note keeps `page`, the selected item (module, id, first 300 characters), the owner's words unchanged, plus the agent's `summary` (one sentence, at most 140 characters) and `tags` (JSON, 2 to 5) | The verbatim words are the record; summary and tags are the compact form later LLM passes read through `feedback_list` or `GET /api/feedback` |
| 8 | Roadmap kind: an existing `PLAN.md` gains one entry under `## Feedback` (id, date, page, item, verbatim words, what it asks for); no plan → `PLAN.md` with `Status: requested, <date>.` and that section only | create-roadmap-item updates an existing plan and expands a requested one; the agent cannot check dependencies on the machine, so it records the request, not a full plan |
| 9 | The header control is mono 13px `feedback`, or `feedback · N` with N queued or failed; the panel under the header's right edge holds a 3-row textarea, a context line, `Send`, and the last five notes as compact rows: `kind · summary · path`, `filing…`, or `failed · retry` | Tracks never move; the rows are the confirmation loop: send, see how it was filed seconds later, without opening Activity |
| 10 | Files land in the working tree uncommitted; the owner commits from the next Claude Code session | Git is outside `docs/`; the daemon never runs git |
| 11 | The platform stays untouched except `config.py` (`[feedback] max_turns`) and `claude.py` (`agent_run`); Education's planned table becomes `education_feedback` when built | One knob, in `config.toml`; one SQLite namespace |

Rejected: a Claude Code skill draining a queue (the owner asked for the agent to file each note itself); `--add-dir app/` so the agent reads code (unverified under `--restricted`; classification needs the docs, which the tools give); an in-app git commit (invasive, collides with worktrees); a `docs/feedback/LOG.md` digest file (the table with `summary` and `tags` is the compact record and is reachable by tool and route); a free-path `docs_write(path)` with validation (a derived path has no edge cases).

## Layout

| File | Change |
|---|---|
| `config.toml`, `app/config.py` | `[feedback] max_turns = <int>`; `Feedback(max_turns)` on `Config` |
| `app/claude.py` | `agent_run(ctx, mod, prompt) -> str` |
| `app/modules/feedback/__init__.py` | `MANIFEST(name="feedback", title="Feedback", hue="#8b8f98", icon="", order=99, page=False, agent=Agent(placeholder="", read_tools=("docs_list","docs_read","feedback_list"), write_tools=("docs_write",)))` |
| `app/modules/feedback/schema.sql` | `feedback` |
| `app/modules/feedback/routes.py` | `GET recent`, `GET list`, `POST action/{add, retry}`; hooks `context` |
| `app/modules/feedback/tools.py` | `docs_list`, `docs_read`, `feedback_list` on both servers; `docs_write` on `otto` only |
| `app/modules/feedback/agent.md` | the agent's job |
| `app/static/feedback.js` | new: `Feedback` component (control, panel, recent rows) |
| `app/static/shell.js` | fetch `/api/feedback/recent` in `refresh`; mount `Feedback` at the end of the header |
| `tests/test_app.py`, `tests/test_platform.py` | `test_feedback_end_to_end`, `test_docs_write_confined`, extend `test_read_builtins_exclude_writers` |

## Contract

Manifest: as above. `page=False` keeps the module out of `/api/shell`; its router and tools load like any module's. No schedules.

| Route | Wire shape |
|---|---|
| `POST /api/feedback/action/add` | body `{page, text, item?: {module, id, text}}` → `{id}`; 400 empty text; inserts `queued`, writes `events(module=page, verb="feedback", text=<words>, ref=<id>)`, submits `feedback.file` |
| `POST /api/feedback/action/retry` | body `{id}` → `{id}`; 404 unknown; 409 unless `failed`; resets to `queued` and resubmits |
| `GET /api/feedback/recent` | `{pending: <queued + failed>, rows: [{id, created_at, page, status, kind, path, summary, error}]}`, last five |
| `GET /api/feedback/list?status=&limit=` | full rows, newest first; the compact record for later passes |

`feedback.file` job: prompt = the note (`#id`, page, item module and id with its text, the owner's words in a fenced block) and the reply format; `raw = await ctx.claude.agent_run(ctx, mod, prompt)`; parse the JSON object (tolerant, as Memory's parser); require `kind` in the four kinds, `path` inside `docs/` and existing, `summary` non-empty; `ctx.commit()` sets `status='filed', kind, path, summary, tags, filed_at, job_id`; any failure sets `status='failed', error`, and the runner's `failed` event shows it in Activity. Returns `"<kind> → <path>"`.

Tools (`tools.py`):

| Tool | Server | Does |
|---|---|---|
| `docs_list()` | both | `[{path, bytes, modified}]` for every `.md` under `config.root / "docs"` |
| `docs_read(path)` | both | the text; refuses anything that does not resolve inside `docs/` or is not `.md` |
| `feedback_list(status=None, limit=50)` | both | rows `{id, created_at, page, item_module, item_id, text, status, kind, path, summary, tags}` |
| `docs_write(kind, slug, text)` | `otto` only | derives the path per decision 2, validates `slug`, creates `docs/roadmap/<slug>/` when needed, writes the file, returns `{path, bytes}` |

Agent (`agent.md`): the Feedback agent files one note at a time. First `docs_list`, then read what is relevant: `ARCHITECTURE.md` to know whether the page is built and what it promises, and any existing finding or plan that covers the same thing. Choose one kind by the sync taxonomy: `bug` when the code does something it was not meant to do; `defect` when it works as built but is wrong for the owner; `gap` when a stated requirement or artboard element is unmet; `roadmap` for anything new. Update an existing file rather than write a second one. A finding file is `# <Title>`, `- Where:`, `- Found: <date>, feedback #<id>`, `- Status: open`, then `What happens:`, `Expected:`, `Fix:`; the owner's words appear verbatim in `What happens` or `Expected`. A roadmap entry follows decision 8. Never reword the owner's words. Reply with only `{"kind", "path", "summary", "tags"}`.

`context(store, registry)`: the built modules by name, the roadmap slugs on disk, and counts of files per finding folder.

`Feedback({page, hue, sel, item, recent, onSent})` in `feedback.js`: control span, mono 13px, `#8b8f98`, ring hover, label from `recent.pending`. Panel: top 44px, right 32px, width 360px, padding 12px, `#1a1c21`, ring `inset 0 0 0 1px rgba(230,231,234,.08)`, radius 6; textarea 3 rows on `#23262c`, placeholder `What should change here?`; context line `memory · item 12` or `memory`; `Send` primary in `hue`; then the recent rows at 28px in mono: `filing…` for `queued`, `<kind> · <summary>` with the path as title for `filed`, `failed · <error>` with a `retry` span for `failed`. Enter sends, Shift+Enter breaks a line, Esc closes keeping the draft. Send posts `{page, text, item: sel ? {module, id, text: item.text.slice(0, 300)} : undefined}` and calls `onSent`.

Departures from the artboard: the header control and the panel are not in the artboard; they reuse the header's mono meta style, the panel and raised surfaces, the composer textarea, compact rows and the primary button. Events for `activity` and `settings` carry that page as `module` and show under Activity's `All` chip.

## Data

`app/modules/feedback/schema.sql`:

| Table | Columns |
|---|---|
| `feedback` | `id INTEGER PK`, `created_at TEXT NOT NULL`, `page TEXT NOT NULL`, `item_module TEXT`, `item_id TEXT`, `item_text TEXT`, `text TEXT NOT NULL`, `status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','filed','failed'))`, `kind TEXT CHECK (kind IN ('bug','defect','gap','roadmap'))`, `path TEXT`, `summary TEXT`, `tags TEXT` (JSON), `filed_at TEXT`, `job_id INTEGER`, `error TEXT`; index on `(status, created_at)` |

Cursors: none. Scheduled tasks: none.

| Client | Who receives it | Test |
|---|---|---|
| Read: `docs_list`, `docs_read`, `feedback_list` on `otto-read` and `otto` | any agent | `test_read_builtins_exclude_writers` extended: `read.list_tools()` names no `docs_write` |
| Write: `docs_write` on `otto` only, reached through `agent_run` from the `feedback.file` action job | the Feedback agent, per note | `test_docs_write_confined`; `test_feedback_end_to_end` asserts the spawned args name the `otto` server and `--no-session-persistence`; `test_tasks_never_reach_interactive_claude` stays green because the module has no `tasks.py` |

## Phases

| Phase | Builds | Usable result |
|---|---|---|
| 1 | Config knob, `agent_run`, the module (table, routes, tools, agent.md), `feedback.js`, header mount, tests | On any page the owner clicks `feedback`, types the change, presses Enter; seconds later the panel row reads `bug · <summary>` and the file exists under `docs/`; Activity shows the run; a failed run shows `retry` |
| 2 | `feedback_list` tool and `GET /api/feedback/list` with `summary` and `tags` on every row | Every note, verbatim and compacted, is readable by any agent and by `curl` for later insight and rule passes |

## Tests

- `test_docs_write_confined` (`tests/test_platform.py`): register the tools on two `MCPServer`s with a `Store` and a temp root; `docs_write("bug", "x-y", "# X")` writes `docs/bugs/x-y.md`; `docs_write("roadmap", "new-thing", …)` creates `docs/roadmap/new-thing/PLAN.md`; slugs `../x`, `a/b`, `A`, `x.md` and kind `note` return `{"error"}` and write nothing; `docs_read("../config.toml")` and `docs_read("docs/x.txt")` refuse.
- `test_feedback_end_to_end` (`tests/test_app.py`): fake spawn whose result line is `{"kind":"bug","path":"docs/bugs/x.md","summary":"…","tags":["memory"]}`, and the test writes that file into the temp root first; `POST action/add` with `page: "memory"` and an item → `{id}`; after `settle`, `GET recent` shows `filed`, `kind == "bug"`, `pending == 0`; the `llm_runs` row has `budgeted == 0`; the spawn args contain `"otto"` server config and `--no-session-persistence`; a second note whose fake reply names a missing path ends `failed` with `pending == 1`; `POST action/retry` requeues it; empty text → 400; `GET /api/events?module=memory` first verb is `feedback`.
- Offline: `conftest.no_real_claude` plus the fake; `docs_write` in tests targets the temp root, never the repo.

## Manifest

Present

| Item | Version / location | Needed for |
|---|---|---|
| Python | 3.14.7, `.venv/Scripts/python.exe` | everything |
| fastapi, uvicorn, mcp, httpx, pytest | 0.141.1, 0.52.4, 2.2.0, 0.28.1, 9.1.1 in `.venv` (`pip list`, today) | routes, tools, tests |
| SQLite | 3.50.4 via `sqlite3` | `feedback` |
| Claude Code CLI | 2.1.263 at `C:/Users/gudo/.local/bin/claude.exe`, claude.ai Max login | `agent_run` |
| Write MCP tools reach a user-triggered run | `memory_add` on the `otto` server is exercised by `test_session_turn_and_clear` today; `_args` never enables the CLI's Write tool | decision 2 |
| Daemon | running, rev `872953658f4c`, `/health` on `127.0.0.1:8765` answered today | manual verify |
| Test suite | 19 passed today (`pytest -q`) | baseline |

Missing

| Package | Version | Needed for | Install target |
|---|---|---|---|
| none | | | |

Needs you

| Item | How |
|---|---|
| `[feedback] max_turns` | one integer for `config.toml`; a run lists docs, reads two or three files and writes one, so 12 is the proposal |

Verify

| Check | Command |
|---|---|
| A note was filed and the file exists | `curl -s "http://127.0.0.1:8765/api/feedback/list?limit=5"` then `ls` the `path` it names |
| The run was unbudgeted | `.venv/Scripts/python.exe -c "import sqlite3; print(sqlite3.connect('data/otto.db').execute(\"SELECT module, task, status, budgeted FROM llm_runs WHERE module='feedback' ORDER BY id DESC LIMIT 3\").fetchall())"` |
| Nothing outside `docs/` changed | `git status --short` after a note shows only `docs/` paths |

## Worktree

```
git worktree add ../otto-feedback -b feedback
```

Work in `../otto-feedback`. When `feedback` is merged to `main`, run `/sync-architecture`.

## Pending decisions

1. `[feedback] max_turns`: 12, or another cap?
2. Files are written uncommitted into the working tree of whichever checkout the daemon runs from (decision 10). Confirm, or name a commit step you want the daemon to own.
