# Feedback Plan

Status: planning, 2026-09-08.

A `feedback` control in the header of every page lets the owner record a change they want the moment they notice it, without leaving the window. The daemon queues each note with what the owner was looking at; one Claude Code command later turns the queue into roadmap items. Without it every idea means opening VS Code and writing the plan by hand, and most ideas are lost before that happens.

## Sources

| Source | Governs |
|---|---|
| The request (this session) | A control on every module page; feedback queued, processed later into roadmap items; the owner is the only user and developer |
| `docs/ARCHITECTURE.md` › Daemon requirements and Mechanisms | User actions are jobs through `run_action`; the UI holds no state; failure is local |
| `docs/ARCHITECTURE.md` › Claude | In-app runs are `--restricted`, read-only built-ins, confined to `data/workspace`: they cannot write `docs/` |
| `docs/ARCHITECTURE.md` › UI frame contract, Activity | Header spec (48px, mono 13px meta), tokens, buttons; Activity lists `events` by module |
| `docs/design/Personal Dashboard App.dc.html` lines 37–41, 311–333 | Header markup; the session composer (textarea, mono action row) the panel borrows from |
| `app/api.py`, `app/schema.sql`, `app/runner.py`, `app/store.py` | Platform routes, tables, `run_action`, `events` |
| `app/static/shell.js`, `app/static/session.js`, `app/static/rows.js`, `app/static/api.js` | The header, the composer pattern, `Button`, `mono13`, `post` |
| `app/static/pages/activity.js` | Where queued feedback becomes visible with no new page |
| `.claude/skills/create-roadmap-item/{SKILL.md, reference.md}` | The step the processing skill delegates to; its one-plan-per-item rule |
| `docs/roadmap/education/PLAN.md` line 112 | Names a module table `feedback`; one SQLite namespace |
| `tests/test_app.py`, `tests/conftest.py` | Route test pattern through `build(config)` |

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | Feedback is a platform feature: `app/schema.sql`, `app/api.py`, `app/static/feedback.js`, mounted by `shell.js`; not a module | It must exist on every page, Activity and Settings included, and the shell owns the header. No rail entry, no agent, no schedule, no manifest |
| 2 | The control is the last element of the header, right-aligned: mono 13px `feedback`, or `feedback · N` while N notes are queued. Clicking it opens a panel under the header's right edge; nothing else moves | Frame contract: selection never moves a track; the header is the one region shared by every page. The count tells the owner when to drain the queue without opening anything |
| 3 | The panel is a 3-row textarea on the raised surface, a mono context line, and `Send` in the page hue. Enter sends, Shift+Enter breaks a line, Esc closes | Identical to the session composer the owner already uses; nothing new to learn |
| 4 | Every submission records the page, the selected item (module, id, first 300 characters of its text) when one is selected, and the typed words unchanged | The processing step needs what the owner was looking at; the owner types only the change. The owner's words are the owner's (agent_base) |
| 5 | Submission is `runner.run_action("feedback.add", <page>, "feedback", fn)`: one `feedback` row, one `events` row (module = page, verb `feedback`, text = the words) | Every write is a job with a row in Activity; the event puts the queue in Activity under the page's chip, so no Feedback page is needed |
| 6 | The queue is drained by a Claude Code skill `/process-feedback`, not by the in-app agent | In-app Claude cannot write `docs/`. A roadmap item is `/create-roadmap-item`: it reads ARCHITECTURE, the artboard and the code and checks dependencies on this machine, which is the owner's Claude Code session. The owner's VS Code time becomes one command per batch |
| 7 | The skill reads and marks the queue through the daemon (`GET /api/feedback?status=queued`, `POST /api/feedback/{id}`), using `[server]` from `config.toml`; never through the database file | One owner of `otto.db`; marking is a job like every other write; the URL is a knob that already exists |
| 8 | Page to plan: a module page goes to the existing plan whose title names that module (`home` → `docs/roadmap/homepage/`), else to `docs/roadmap/<page>/`; `activity`, `settings` and the frame go to `docs/roadmap/app/`. An existing plan is updated, otherwise `/create-roadmap-item` writes it | create-roadmap-item's rule: never two plans for one item. `docs/roadmap/app/` is the platform's folder |
| 9 | `status` is `queued` or `processed`, set once. No withdraw, no edit in the app | Exactly what was asked: record, queue, process. A bad note is dropped by the owner while reviewing the skill's reply |
| 10 | The platform table is `feedback`; when Education is built its table is `education_feedback` | One SQLite namespace; the platform's tables carry no prefix (`tasks`, `jobs`, `events`) |
| 11 | No `config.toml` key and no `settings` key | The item has no parameter: panel size and item-text length are frame constants like every other measurement in the shell; the daemon URL is `[server]` |

Rejected: a `oneshot` transcription at submit (a Claude run per note adds seconds to a capture meant to take one, and the row already carries the context); `feedback_add` / `feedback_list` MCP tools on every module's agent (touches every manifest for a second way to do one thing); a Feedback rail page (Activity already lists the queue; a page needs LEFT, MIDDLE and an agent); filing feedback as Memory tasks (mixes the owner's life with the app's backlog); the skill opening `data/otto.db` directly.

## Layout

| File | Change |
|---|---|
| `app/schema.sql` | add `feedback` |
| `app/api.py` | `feedback_queued` in `GET /api/shell`; new `POST /api/feedback`, `GET /api/feedback`, `POST /api/feedback/{id}` |
| `app/static/feedback.js` | new: `Feedback` component (header control and panel) |
| `app/static/shell.js` | mount `Feedback` at the end of the header with `page`, `hue`, `sel`, `item`, `queued`, `onSent` |
| `tests/test_app.py` | `test_feedback_queue` |
| `.claude/skills/process-feedback/SKILL.md` | new: drains the queue into roadmap plans |

## Contract

Shell: `GET /api/shell` gains `feedback_queued: <count of status = queued>`; the control renders from it and the header refreshes on the existing interval and after every send.

| Route | Wire shape |
|---|---|
| `POST /api/feedback` | body `{page, text, item?: {module, id, text}}` → `{id}`; 400 on empty text; `run_action("feedback.add", page, "feedback", fn)`; writes the row and `events(module=page, verb="feedback", text=<words>, job_id, ref=<id>)` |
| `GET /api/feedback?status=queued` | `[{id, created_at, page, item_module, item_id, item_text, text, status, processed_at, ref}]`, oldest first; `status` defaults to `queued` |
| `POST /api/feedback/{id}` | body `{status: "processed", ref}` → the row; 404 unknown id; 409 already processed; 400 any other status; `run_action("feedback.mark", <row.page>, "feedback", fn)`; writes `events(module=page, verb="processed", text=<ref>)` |

`Feedback({page, hue, sel, item, queued, onSent})` in `feedback.js`: the control is a mono 13px span in `#8b8f98` with the ring hover, `feedback` or `feedback · N`. Open state is a panel positioned under the header's right edge (top 44px, right 32px, width 360px, padding 12px, `#1a1c21`, ring `inset 0 0 0 1px rgba(230,231,234,.08)`, radius 6) holding the textarea (3 rows, `#23262c`, placeholder `What should change here?`), a mono line `memory · item 12` or `memory`, and `Send` primary in `hue`. Send posts `{page, text, item: sel ? {module, id, text: item.text.slice(0, 300)} : undefined}`, clears the draft, closes, calls `onSent` (the shell's `refresh`). Esc closes with the draft kept. Errors render in `#cf7b7b` inside the panel.

Events for the `activity` and `settings` pages carry that page name as `module`; Activity's chips list modules only, so those rows show under `All`.

`/process-feedback` (skill, runs in Claude Code on a clean `main`):

1. Read `[server]` from `config.toml`; `GET /api/feedback?status=queued`. Daemon unreachable: stop and say `run python -m app`.
2. Empty queue: say so and stop.
3. Group rows by page and map each page to its plan folder (decision 8). Per folder: the plan exists → update it under create-roadmap-item's rules, adding what the rows ask for and one `Feedback` line per row (`id`, date, page, item, the owner's words verbatim); no plan → `/create-roadmap-item <slug>` with the rows as the request.
4. Commit on `main`: `Process feedback: <ids>`.
5. `POST /api/feedback/{id}` `{status: "processed", ref: "docs/roadmap/<slug>/PLAN.md"}` per row, after the commit succeeds.
6. Reply with one table, `id | page | words | ref`, and any question a plan raised.

Departures from the artboard: the header carries a control the artboard lacks, and the panel is not in the artboard. Both reuse the header's mono meta style, the panel and raised surfaces, the session composer's textarea and the primary button.

## Data

`app/schema.sql`:

| Table | Columns |
|---|---|
| `feedback` | `id INTEGER PK`, `created_at TEXT NOT NULL`, `page TEXT NOT NULL`, `item_module TEXT`, `item_id TEXT`, `item_text TEXT`, `text TEXT NOT NULL`, `status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','processed'))`, `processed_at TEXT`, `ref TEXT`; index on `(status, created_at)` |

Cursors: none. Scheduled tasks: none. External clients: none; nothing writes outside `otto.db` and `docs/`.

| Client | Who receives it | Test |
|---|---|---|
| Write: `ctx.commit` on `feedback` and `events` | `POST /api/feedback` and `POST /api/feedback/{id}` through `run_action` | `test_feedback_queue` proves both routes are jobs (a `jobs` row per call) and that no other path sets `status`; `test_tasks_never_reach_interactive_claude` is unaffected because no task exists |

## Phases

| Phase | Builds | Usable result |
|---|---|---|
| 1 | `feedback` table, the three routes, `feedback_queued` in the shell, `feedback.js`, header mount, test | On any page the owner clicks `feedback`, types the change, presses Enter; the count in the header rises, Activity lists the note under the page's chip with what was selected |
| 2 | `.claude/skills/process-feedback/SKILL.md` | One command in Claude Code turns every queued note into a roadmap plan (new or updated), commits, marks the rows processed; the header count returns to zero |

## Tests

- `test_feedback_queue` (`tests/test_app.py`, through `build(config)`): `POST /api/feedback` with `page: "memory"`, an item and text → 200 with `id`; empty text → 400; `GET /api/shell` has `feedback_queued == 1`; `GET /api/feedback` returns the row with the text unchanged and `item_text` kept; `GET /api/events?module=memory` first verb is `feedback`; `POST /api/feedback/{id}` `{status: "processed", ref: "docs/roadmap/memory/PLAN.md"}` → `status == "processed"` and a `processed` event; a second mark → 409; `{status: "queued"}` → 400; `GET /api/jobs` shows `feedback.add` and `feedback.mark` as `action` jobs.
- No Claude touchpoint exists in this item; the suite stays offline under `conftest.no_real_claude`.

## Manifest

Present

| Item | Version / location | Needed for |
|---|---|---|
| Python | 3.14.7, `.venv/Scripts/python.exe` | everything |
| fastapi, uvicorn, mcp, httpx, pytest | 0.141.1, 0.52.4, 2.2.0, 0.28.1, 9.1.1 in `.venv` (`pip list`, today) | routes, runner, tests |
| SQLite | 3.50.4 via `sqlite3` | `feedback` |
| Daemon | running, rev `872953658f4c`, `/health` on `127.0.0.1:8765` answered today | the skill's queue read and mark |
| Test suite | 19 passed today (`pytest -q`) | baseline |
| Claude Code CLI | 2.1.263 at `C:/Users/gudo/.local/bin/claude.exe` | `/process-feedback` runs inside it |
| `.claude/skills/create-roadmap-item/` | present | step 3 of the skill |

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
| Queue holds what was typed, verbatim | `curl -s "http://127.0.0.1:8765/api/feedback?status=queued"` |
| Header count matches the queue | `curl -s http://127.0.0.1:8765/api/shell` shows `feedback_queued` equal to the row count above |
| Marking is a job | `.venv/Scripts/python.exe -c "import sqlite3; print(sqlite3.connect('data/otto.db').execute(\"SELECT task, kind, status FROM jobs WHERE task LIKE 'feedback.%' ORDER BY id DESC LIMIT 5\").fetchall())"` |

## Worktree

```
git worktree add ../otto-feedback -b feedback
```

Work in `../otto-feedback`. When `feedback` is merged to `main`, run `/sync-architecture`.

## Pending decisions

1. Decision 6: the transcription into a roadmap item runs in your Claude Code session via `/process-feedback`, not inside the app's agent, because in-app Claude cannot write `docs/`. Confirm, or name what the in-app agent should do at submit time instead.
2. A note that reports a bug in built code: filed as a roadmap item as you said, or as a `docs/bugs/` file per the sync taxonomy? The plan assumes a roadmap item for every note.
