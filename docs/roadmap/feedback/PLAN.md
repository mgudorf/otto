# Feedback Plan

Status: planning, 2026-09-08.

A `feedback` control in the header of every page lets the owner record a change they want the moment they notice it, without leaving the window. A standalone Feedback agent reads each note, decides whether it is a bug, a defect, a gap or a roadmap request, and files it as a row: the owner's words verbatim, a one-line digest, tags, the existing doc it relates to, and a drafted item in the shape the `docs/` folders use. Nothing touches the repo; the Database module later triages and exports rows in bulk. Without it every idea means opening VS Code, and most ideas are lost before that happens.

## Sources

| Source | Governs |
|---|---|
| The request (this session) | A control on every page; a standalone agent classifies and files each note; every note recorded and compacted for later LLM insight; the owner chose a table over files under `docs/`, `max_turns` 12 |
| `docs/ARCHITECTURE.md` › Daemon requirements, Mechanisms, Claude, Module contract | Writes happen only from user actions; the CLI's built-in file tools are confined to `data/workspace`; `oneshot` is the user-triggered, unbudgeted run |
| `docs/ARCHITECTURE.md` › UI frame contract, Activity | Header spec, tokens, rows, buttons; Activity lists `events` by module |
| `docs/design/Personal Dashboard App.dc.html` lines 37–41, 311–333 | Header markup; the session composer the panel borrows from |
| `.claude/skills/sync-architecture/SKILL.md` step 4 | The taxonomy and file shape the agent drafts: bug, defect, gap; roadmap for the rest |
| `app/claude.py`, `app/runner.py`, `app/api.py`, `app/daemon.py` | `_args`, `oneshot`, `submit` without await (`/clear` precedent), tool registration |
| `app/modules/memory/{tools.py, routes.py, agent.md}`, `app/modules/system/__init__.py` | The built pattern for tools, action routes, and a `page=False` module |
| `app/static/shell.js`, `session.js`, `rows.js`, `api.js` | The header, the composer pattern, compact rows, `post` |
| `docs/roadmap/education/PLAN.md` line 112 | Names a module table `feedback`; one SQLite namespace |
| `tests/test_app.py`, `tests/conftest.py`, `tests/test_platform.py` | Fake CLI stream, route tests through `build(config)` |

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | Feedback is a module `app/modules/feedback/` with `page=False`: manifest, `schema.sql`, `routes.py`, `tools.py`, `agent.md`; no rail entry, no page, no schedule | The module contract gives an agent its prompt, tools and Current state; `page=False` keeps it off the rail (System precedent). The control lives in the shell because it must be on every page |
| 2 | The agent writes nothing itself. Its final reply is JSON `{kind, title, summary, tags, ref, draft}` and the job writes the row | No write tool means no path to confine; the row is the item. The owner exports rows to `docs/` later through the Database module |
| 3 | Read tools `docs_list()` (every `.md` under `docs/`) and `docs_read(path)` (any `docs/**/*.md`, resolved inside `docs/`), plus `feedback_list` | Classification needs `ARCHITECTURE.md`, the existing findings and plans, and earlier notes; the CLI's file tools cannot leave `data/workspace` |
| 4 | A note is a user action: `POST /api/feedback/action/add` inserts the row `queued` and submits a job (`feedback.file`, resource `feedback`, kind `action`, not awaited) that runs the agent; the route returns at once | The runner's resource lock files notes in order; the window never waits on a Claude run |
| 5 | The run is `oneshot`, extended with `tools` and `max_turns`; read server, `--no-session-persistence`, `llm_runs` row with `budgeted = 0`; cap `[feedback] max_turns = 12` | The existing user-triggered, unbudgeted entry point already fits; one knob in `config.toml` |
| 6 | Row fields from the reply: `kind` in bug, defect, gap, roadmap; `title`; `summary` (one sentence); `tags` (JSON, 2 to 5); `ref` (the existing `docs/` file it relates to, or null); `draft` (the markdown body in the finding shape, or a roadmap Feedback entry) | The verbatim words are the record; summary and tags are the compact form; the draft makes export a copy |
| 7 | Every note keeps `page`, the selected item (module, id, first 300 characters) and the owner's words unchanged; a bad reply sets `failed` with the error and `retry` resubmits | Nothing is lost; the failure is visible and recoverable in place |
| 8 | The header control is mono 13px `feedback`, or `feedback · N` with N queued or failed; the panel under the header's right edge holds a 3-row textarea, a context line, `Send`, and the last five notes as compact rows: `kind · summary`, `filing…`, or `failed · retry` | Tracks never move; the rows are the confirmation loop |
| 9 | Table `feedback` in the module's `schema.sql`; Education's planned table becomes `education_feedback` when built | One SQLite namespace |

Rejected: `docs_write` into the working tree (uncommitted files in whichever checkout the daemon runs from; the owner chose the table); a Claude Code skill draining a queue; `--add-dir app/` for code reads (unverified under `--restricted`; the docs suffice to classify); a separate `agent_run` entry point (two parameters on `oneshot` do the same).

## Layout

| File | Change |
|---|---|
| `config.toml`, `app/config.py` | `[feedback] max_turns = 12`; `Feedback(max_turns)` on `Config` |
| `app/claude.py` | `oneshot(ctx, mod, prompt, tools=(), max_turns=2)` |
| `app/modules/feedback/__init__.py` | `MANIFEST(name="feedback", title="Feedback", hue="#8b8f98", icon="", order=99, page=False, agent=Agent(placeholder="", read_tools=("docs_list", "docs_read", "feedback_list")))` |
| `app/modules/feedback/schema.sql` | `feedback` |
| `app/modules/feedback/routes.py` | `GET recent`, `GET list`, `POST action/{add, retry}`; hook `context` |
| `app/modules/feedback/tools.py` | `docs_list`, `docs_read`, `feedback_list` on both servers |
| `app/modules/feedback/agent.md` | the agent's job |
| `app/static/feedback.js` | new: `Feedback` component (control, panel, recent rows) |
| `app/static/shell.js` | fetch `/api/feedback/recent` in `refresh`; mount `Feedback` at the end of the header |
| `tests/test_app.py`, `tests/test_platform.py` | `test_feedback_end_to_end`, `test_docs_tools_confined` |

## Contract

Manifest: as above. `page=False` keeps the module out of `/api/shell`; its router and tools load like any module's. No schedules, no write tools.

| Route | Wire shape |
|---|---|
| `POST /api/feedback/action/add` | body `{page, text, item?: {module, id, text}}` → `{id}`; 400 empty text; inserts `queued`, writes `events(module=page, verb="feedback", text=<words>, ref=<id>)`, submits `feedback.file` |
| `POST /api/feedback/action/retry` | body `{id}` → `{id}`; 404 unknown; 409 unless `failed`; resets to `queued` and resubmits |
| `GET /api/feedback/recent` | `{rows: [{id, created_at, page, status, kind, summary, error}]}`, last five |
| `GET /api/feedback/list?status=&limit=` | full rows, newest first; the record for triage and export |

`feedback.file` job: prompt = the note (`#id`, page, item module and id with its text, the owner's words in a fenced block) and the reply format; `raw = await ctx.claude.oneshot(ctx, mod, prompt, tools, config.feedback.max_turns)`; parse the JSON object (tolerant, as Memory's parser); require `kind` in the four kinds and non-empty `title`, `summary`, `draft`; `ctx.commit()` sets `status='filed'` with the fields, `filed_at`, `job_id`; any failure sets `status='failed', error`, and the runner's `failed` event shows it in Activity. Returns `"<kind>: <title>"`.

| Tool | Server | Does |
|---|---|---|
| `docs_list()` | both | `[{path, bytes, modified}]` for every `.md` under `docs/` |
| `docs_read(path)` | both | the text; refuses anything that does not resolve inside `docs/` or is not `.md` |
| `feedback_list(status=None, limit=50)` | both | rows `{id, created_at, page, item_module, item_id, text, status, kind, title, summary, tags, ref}` |

Agent (`agent.md`): files one note at a time. First `docs_list`, then read what is relevant: `ARCHITECTURE.md` to know whether the page is built and what it promises, and any finding or plan that covers the same thing. Choose one kind by the sync taxonomy: `bug` when the code does something it was not meant to do; `defect` when it works as built but is wrong for the owner; `gap` when a stated requirement or artboard element is unmet; `roadmap` for anything new. `ref` names the existing file the note belongs in, or null. `draft` is the body ready for that file: for findings `# <Title>`, `- Where:`, `- Found: <date>, feedback #<id>`, `- Status: open`, then `What happens:`, `Expected:`, `Fix:`; for roadmap a `## Feedback` entry with id, date, page, item, verbatim words and what it asks for. The owner's words appear verbatim and are never reworded. Reply with only the JSON object.

`context(store, registry)`: the built modules by name, the roadmap slugs on disk, and counts of files per finding folder.

`Feedback({page, hue, sel, item, recent, onSent})` in `feedback.js`: control span, mono 13px, `#8b8f98`, ring hover, label always `feedback`. Panel: top 44px, right 32px, width 360px, padding 12px, `#1a1c21`, ring `inset 0 0 0 1px rgba(230,231,234,.08)`, radius 6; textarea 3 rows on `#23262c`, placeholder `What should change here?`; context line `memory · item 12` or `memory`; `Send` primary in `hue`; then the recent rows at 28px in mono: `filing…` for `queued`, `<kind> · <summary>` for `filed`, `failed · <error>` with a `retry` span for `failed`. Enter sends, Shift+Enter breaks a line, Esc closes keeping the draft. Send posts `{page, text, item: sel ? {module, id, text: item.text.slice(0, 300)} : undefined}` and calls `onSent`.

Departures from the artboard: the header control and the panel are not in the artboard; they reuse the header's mono meta style, the panel and raised surfaces, the composer textarea, compact rows and the primary button. Events for `activity` and `settings` carry that page as `module` and show under Activity's `All` chip.

## Data

`app/modules/feedback/schema.sql`:

| Table | Columns |
|---|---|
| `feedback` | `id INTEGER PK`, `created_at TEXT NOT NULL`, `page TEXT NOT NULL`, `item_module TEXT`, `item_id TEXT`, `item_text TEXT`, `text TEXT NOT NULL`, `status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','filed','failed'))`, `kind TEXT CHECK (kind IN ('bug','defect','gap','roadmap'))`, `title TEXT`, `summary TEXT`, `tags TEXT` (JSON), `ref TEXT`, `draft TEXT`, `filed_at TEXT`, `job_id INTEGER`, `error TEXT`; index on `(status, created_at)` |

Cursors: none. Scheduled tasks: none. External systems: none.

| Client | Who receives it | Test |
|---|---|---|
| Read: `docs_list`, `docs_read`, `feedback_list` on both servers; the CLI on `otto-read` through `oneshot` | the Feedback agent, per note | `test_docs_tools_confined`; `test_feedback_end_to_end` asserts the spawned args name `otto-read`, `--no-session-persistence` and `--max-turns 12` |
| Write: `ctx.commit` on `feedback` | `action/add`, `action/retry` and the `feedback.file` job, all through the runner | `test_feedback_end_to_end`; no `tasks.py` exists, so `test_tasks_never_reach_interactive_claude` stays green |

## Phases

| Phase | Builds | Usable result |
|---|---|---|
| 1 | Config knob, `oneshot` parameters, the module (table, routes, tools, agent.md), `feedback.js`, header mount, tests | On any page the owner clicks `feedback`, types the change, presses Enter; seconds later the panel row reads `bug · <summary>`; Activity shows the run; a failed run shows `retry` |
| 2 | `feedback_list` tool and `GET /api/feedback/list` with every field | Every note, verbatim, compacted and drafted, is readable by any agent and by the Database module for triage and export |

## Tests

- `test_docs_tools_confined` (`tests/test_platform.py`): register the tools on two `MCPServer`s with a `Store`; `docs_list()` includes `docs/ARCHITECTURE.md`; `docs_read("docs/ARCHITECTURE.md")` returns its text; `docs_read("config.toml")`, `docs_read("../app/config.py")` and `docs_read("docs/design/support.js")` return `{"error"}`.
- `test_feedback_end_to_end` (`tests/test_app.py`): fake spawn whose result line is a JSON object with `kind: "bug"`; `POST action/add` with `page: "memory"` and an item → `{id}`; after `settle`, `GET recent` shows `filed`, `kind == "bug"`; the `llm_runs` row has `budgeted == 0`; the spawn args contain `otto-read`, `--no-session-persistence` and `--max-turns 12`; a second note whose fake reply is not JSON ends `failed`; `POST action/retry` requeues it; empty text → 400; `GET /api/events?module=memory` first verb is `feedback`; `GET list` returns the verbatim text.
- Offline: `conftest.no_real_claude` plus the fake.

## Manifest

Present

| Item | Version / location | Needed for |
|---|---|---|
| Python | 3.14.7, `.venv/Scripts/python.exe` | everything |
| fastapi, uvicorn, mcp, httpx, pytest | 0.141.1, 0.52.4, 2.2.0, 0.28.1, 9.1.1 in `.venv` (`pip list`, today) | routes, tools, tests |
| SQLite | 3.50.4 via `sqlite3` | `feedback` |
| Claude Code CLI | 2.1.263 at `C:/Users/gudo/.local/bin/claude.exe`, claude.ai Max login | `oneshot` |
| Daemon | running, rev `872953658f4c`, `/health` on `127.0.0.1:8765` answered today | manual verify |
| Test suite | 19 passed today (`pytest -q`) | baseline |

Missing

| Package | Version | Needed for | Install target |
|---|---|---|---|
| none | | | |

Needs you

| Item | How |
|---|---|
| none | |

Verify

| Check | Command |
|---|---|
| A note was filed with a draft | `curl -s "http://127.0.0.1:8765/api/feedback/list?limit=5"` |
| The run was unbudgeted | `.venv/Scripts/python.exe -c "import sqlite3; print(sqlite3.connect('data/otto.db').execute(\"SELECT module, task, status, budgeted FROM llm_runs WHERE module='feedback' ORDER BY id DESC LIMIT 3\").fetchall())"` |
| Nothing in the repo changed | `git status --short` after a note is empty |

## Worktree

```
git worktree add ../otto-feedback -b feedback
```

Work in `../otto-feedback`. When `feedback` is merged to `main`, run `/sync-architecture`.

## Pending decisions

None.
