# Education v0 Plan

Status: planning, 2026-09-08.

Education keeps a queue of conceptual questions on the owner's topics, grades the owner's answers in a back-and-forth with a tutor, and tunes difficulty per topic to keep the owner in flow. It is worked on demand, when the owner has time, with about three questions waiting each day. Without it the owner has no place where questions are waiting and no record, topic by topic, of what they understand.

## Sources

| Source | Governs |
|---|---|
| `docs/ARCHITECTURE.md` Education, Education Constraints | what the module must do, the fourteen topics, the on-demand rule, progress by domain |
| `docs/ARCHITECTURE.md` Daemon requirements and Mechanisms | scheduled work reads, user actions write; kill-safe tasks; nightly budget |
| `docs/ARCHITECTURE.md` Claude, Module contract, Config, UI frame contract | run paths, manifest and file obligations, knobs, tokens, hue `#7a9fd6`, rail order 2 |
| `docs/design/Personal Dashboard App.dc.html` rail entry, `eduGroups`, `selInfo` for `ed`, `AGENTS.edu`, home `edu` tile | icon, LEFT rows with a 40px progress bar and date groups, inspector with a primary `Start` and secondary actions (see departures), tutor chips and placeholder, home number `due` |
| `app/modules/__init__.py`, `app/daemon.py`, `app/runner.py`, `app/claude.py`, `app/scheduler.py`, `app/config.py` | registry, tool registration, job context, `run_task`, nightly window, typed config |
| `app/modules/memory/*`, `app/static/pages/memory.js` | the reference implementation of the contract; `_json_array` and the suggest task are the nightly pattern |
| `app/static/shell.js`, `rows.js`, `session.js`, `app/api.py` | page map, `Row` leading slots, `Inspector`, `sendToSession`, session context block |
| `docs/bugs/budget-refusal-marks-job-failed.md`, `docs/gaps/logon-task-not-registered.md` | how the nightly task must handle a refusal; why it may never fire on this machine today |
| `tests/*` | fixtures (`fake_spawn`, `config`), the AST guard over every `tasks.py`, hook signature rule |

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | Grading happens in the tutor session, not in a form | Requirement 8 wants back-and-forth after each answer; the session pane already streams turns and carries write tools. A form would need an LLM call from a route, which the Claude contract does not offer |
| 2 | `Start` marks one question started; the tutor learns it from the Current state block | `context(store, registry)` cannot see the page selection, so the started question must live in the store. Starting another question un-starts the previous one, so there is never more than one |
| 3 | Each part is graded separately with `education_grade(question_id, part, score, note)`; the question is graded when its last part is | A part can be re-graded during the back-and-forth, an interrupted session loses nothing, and the LEFT bar can show progress inside a question |
| 4 | Difficulty is an integer 1 to 5 stored per topic; when a question completes, a score above `flow_high` raises it one step, below `flow_low` lowers it one step | Requirement 4 in its literal form, parameter-free beyond the band, deterministic Python, visible in the progress table |
| 5 | Nightly `generate` tops the due queue up to `queue_size`, one question per topic, topics ordered by least recently asked, skipping when the queue is full | Breadth over depth (constraint 1); a bounded backlog; no budget spent while the owner is away |
| 6 | The prompt lists every prior title on the topic as "never repeat these or close variants" | Constraint 1: a question is asked once, even when answered badly. Skipped questions count as asked |
| 7 | The tutor can write a question on demand with `education_add_question`, which starts it immediately | Day one has no nightly output yet; "quiz me on X now" is the natural tutor request. Same insert as the nightly path, `source = session` |
| 8 | Owner feedback is stored verbatim in its own table, separate from the tutor's notes | Requirement 5 and agent_base: the owner's words are quoted literally; the generator reads both |
| 9 | Education's tools take their knobs through `register(read, full, store, config=None)`, loading `config.toml` when the daemon passes nothing | `education_grade` needs the flow band and `education_add_topic` needs `start_difficulty`. The database worktree already changes the shared seam to pass config while finance, graph and web_search add three-argument registers, so touching the seam here would collide at merge; the optional argument works on both sides of that change |
| 10 | Knobs in `config.toml` under `[education]`: `queue_size`, `start_difficulty`, `flow_low`, `flow_high` | Boot values like `[nightly]`; nothing hidden in code. `queue_size` is 3: the owner expects about three questions a day |
| 11 | LEFT search uses `LIKE` over title and premise, no FTS table | A few questions a day; triggers and a virtual table buy nothing here |
| 12 | Questions are worked on demand from the queue; nothing is scheduled to a date | The owner pursues Education when there is time. The nightly run keeps three waiting and the tutor writes more on request, so a free day is never short of questions and there is no calendar state to maintain |
| 13 | The task catches `BudgetExceeded` and returns `Skipped` | The per-task fix named in `docs/bugs/budget-refusal-marks-job-failed.md`; a refusal must not read as a failure in Activity |
| 14 | A topic is one of the owner's domains; progress is tracked per topic: difficulty, graded/asked, average, the last five scores, last asked. Each question keeps its score and per-part notes | Requirement 3 at the level the owner thinks in; per-question history keeps the finer grain without a second table |

Rejected: grading through a MIDDLE answer form with a one-shot LLM call; whole-question grading with one score list; a per-topic rolling average with a window knob; FTS5 for search; changing the shared registration seam in this branch; seeding topics in code.

## Layout

| File | Change |
|---|---|
| `app/modules/education/__init__.py` | `MANIFEST` |
| `app/modules/education/schema.sql` | `topics`, `questions`, `question_parts`, `feedback` |
| `app/modules/education/tasks.py` | `generate(ctx)` |
| `app/modules/education/routes.py` | `left`, `blank`, `item/{id}`, `action/{start\|skip\|add_topic\|retire_topic}`, hooks `numbers`, `today`, `item`, `context` |
| `app/modules/education/tools.py` | `validate_question`, `insert_question`, `add_question`, `grade` as plain functions; `register(read, full, store, config=None)` wraps them and the read tools |
| `app/modules/education/agent.md` | the tutor's job |
| `app/static/pages/education.js` | `load`, `meta`, `Left`, `Middle` |
| `app/static/shell.js` | import `pages/education.js`, add it to `PAGES` |
| `app/config.py` | `Education` dataclass, `education` field on `Config`, one line in `load` |
| `config.toml` | `[education]` section |
| `tests/test_app.py` | the memory test finds its Home group and number by module name; Education now precedes Memory |
| `tests/test_education.py` | the three tests below |

## Contract

Manifest: `name="education"`, `title="Education"`, `hue="#7a9fd6"`, icon copied from the artboard rail entry (`M2 8l8-4 8 4-8 4-8-4Z`, `M6 10v4c0 1.2 2 2 4 2s4-.8 4-2v-4`, `M18 8v5`), `order=2`. Agent: placeholder `Ask the tutor…`, skills `question-gen`, `quiz`, `explain`, `plan` (the artboard's), read tools and write tools as below. Header meta: `<n> due`.

| Schedule | every | resource | llm |
|---|---|---|---|
| `education.generate` | 24h | `education` | yes: runs inside the nightly window, one budgeted run |

| Route | Wire shape |
|---|---|
| `GET /api/education/left?query=&page=` | `{groups, showing, more}`. First group `due`: open questions, started first then oldest first, `leading: {pct: graded parts / parts}`, stamp `created_at`. Then one group per day of `graded_at` or `skipped_at`, newest first, `leading: {pct: score}`, skipped rows `done: true`; `ui.page_size` pages the history. `query` filters title and premise |
| `GET /api/education/blank` | `{due, topics: [{id, name, description, difficulty, asked, graded, average, recent, last_asked}]}`, active topics only; `recent` is the last five scores, newest first |
| `GET /api/education/item/{id}` | `{id, module, kind: "<topic> · d<difficulty>", title, text: premise, created_at, status, score, parts: [{n, text, score, note}], feedback: [text], actions}`. Actions: open `Start` (primary) and `Skip`; started `Skip`; graded or skipped none |
| `POST /api/education/action/start` `{id}` | sets `started_at`, clears it on any other open question; event `started` |
| `POST /api/education/action/skip` `{id}` | sets `skipped_at`; event `skipped` |
| `POST /api/education/action/add_topic` `{name, description?}` | inserts at `start_difficulty`; the description is optional, one line on what the owner wants from the topic; event `added topic` |
| `POST /api/education/action/retire_topic` `{id}` | sets `retired_at`; its open questions stay answerable; event `retired topic` |

Every action runs through `runner.run_action("education.<verb>", "education", "education", fn)`.

| Tool | Server | Does |
|---|---|---|
| `education_topics()` | read | active topics with difficulty, asked, graded, average and the last five scores |
| `education_questions(topic_id=None, status=None, limit=50)` | read | titles, difficulty, score, dates; the no-repeat check |
| `education_question(id)` | read | one question with parts, scores, notes and feedback |
| `education_feedback(topic_id=None)` | read | the owner's feedback lines, verbatim |
| `education_add_topic(name, description=None)` | full | inserts at `start_difficulty` |
| `education_add_question(topic_id, title, premise, parts, difficulty)` | full | 3 to 5 parts or an error; unique title per topic; `source = session`; starts it |
| `education_grade(question_id, part, score, note)` | full | scores one part 0 to 100 with a note; re-grading overwrites; on the last part sets `score` (mean) and `graded_at`, then moves the topic's difficulty by the flow rule once |
| `education_record_feedback(text, topic_id=None, question_id=None)` | full | stores the owner's words unchanged |

Hooks: `numbers` is the open count labelled `due`; `today` is the due queue as LEFT rows (Home shows five and `+N`); `item` as above; `context` renders the active topics with difficulty, average and last five scores, the started question in full with any part scores, the due count, the last five graded titles with scores, and the latest feedback lines.

The tutor teaches concepts in plain language, never asks for algebra or derivations, and introduces every equation inside the premise. It grades the started question one part at a time, saying which part it is grading, and records each part with `education_grade` as soon as it has a score, revising on a good rebuttal. It writes the owner's feedback with `education_record_feedback` verbatim. On request it writes a question with `education_add_question` after checking `education_questions` for repeats: 3 to 5 parts, each intimately tied to the premise, at the topic's current difficulty. It adds topics with `education_add_topic` when asked and prefers breadth across topics over depth in one.

Page: LEFT is the search, then the groups above, then `showing` and `more`. MIDDLE selected is the `Inspector` with the premise as body, the numbered parts with score and note once graded, feedback lines, and the actions; `Start` also focuses the composer with `Q<id> part 1: `. MIDDLE blank is the progress table (name, `d<difficulty>`, graded/asked, average, last five scores, last asked, a retire control) and an add-topic box (name, optional one-line description, `Save`).

Departures from the artboard:

- The artboard's `Reschedule` action is dropped: questions are answered on demand, when the owner has time; nothing is scheduled to a date.
- LEFT's first group is `due`, then history by day; the artboard groups everything by date range.
- MIDDLE blank state (progress table and add-topic box) is not in the artboard, which left it unspecified.
- The artboard's Database mock names `courses` and `lessons`; this module's nouns are topics and questions, per the requirements.

## Data

| Table | Columns |
|---|---|
| `topics` | `id, name UNIQUE, description (nullable), difficulty CHECK 1..5, created_at, retired_at` |
| `questions` | `id, topic_id → topics, title, premise, difficulty CHECK 1..5, source CHECK nightly\|session, created_at, started_at, graded_at, skipped_at, score, UNIQUE(topic_id, title)`; index on `created_at` |
| `question_parts` | `question_id → questions ON DELETE CASCADE, n, text, score CHECK 0..100, note, graded_at, PRIMARY KEY(question_id, n)` |
| `feedback` | `id, ts, topic_id, question_id, text` |

Status is derived: open when `graded_at` and `skipped_at` are null, started when also `started_at` is set. Last asked per topic is `MAX(questions.created_at)`; a topic's average and last five scores come from its graded questions.

A topic is one of the owner's domains. The first fourteen, entered once through the page or the tutor after phase 1 lands, never seeded in code:

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

New tech (pick a new technology, see if the owner can understand how it works) is not a topic here; it is its own future item, `docs/roadmap/new-tech/`.

| Cursor | Value |
|---|---|
| `education.generate` | timestamp of the last successful insert, written in the same `ctx.commit` as the questions |

| Path | Client | Writes |
|---|---|---|
| `generate` (scheduled) | `ctx.store` reads; `ctx.run_task` reaches Claude on the read server with `education_questions`, `education_question`; `ctx.commit` is its only write | its own `questions` and `question_parts` rows plus the cursor, one transaction |
| tutor session | full server: the four read tools and the four write tools | grades, feedback, session questions, topics |
| page actions | `run_action` on resource `education` | start, skip, topic add and retire |

No external system is touched. The split is proved by `test_education_tool_split`: `asyncio.run(read.list_tools())` names no `education_add_*`, `education_grade` or `education_record_feedback`, and the full server names all eight; the existing AST guard `test_tasks_never_reach_interactive_claude` covers `tasks.py`.

## Phases

| Phase | Builds | Usable result |
|---|---|---|
| 1 | schema, manifest, `[education]` config and dataclass, routes and hooks, tools, `agent.md`, page, `shell.js` entry, `test_education_end_to_end`, `test_education_tool_split` | The owner enters the fourteen topics, asks the tutor for a question, answers it in the pane part by part, watches the score bar in LEFT and the topic's difficulty and recent scores move, and sees `N due` on Home |
| 2 | `tasks.py generate`: queue top-up, topic rotation, no-repeat list, JSON parse, `BudgetExceeded` to `Skipped`, cursor; `test_generate_task` | Three questions wait each morning; Activity shows the run and its result |

## Tests

- `test_education_end_to_end` (`build(config)` + `httpx.ASGITransport`): add a topic, `add_question` with four parts, `left` shows it under `due` with `pct 0`, `start` sets it, `grade` four parts, the row moves to today's group with `pct` equal to the mean, `numbers` drops to zero, `blank` shows the topic as `1/1` graded with the score first in `recent`, the topic's difficulty rises when the score is above `flow_high`, `skip` works, a two-part question is refused.
- `test_generate_task`: `fake_spawn` returning a result whose text is a JSON array of one question; `budget` monkeypatched to in-window with nothing used; the task inserts the question and the cursor; a full queue returns `Skipped`; a `BudgetExceeded` from a patched `run_task` also ends as `skipped`, not `failed`.
- `test_education_tool_split`: as in Data.
- Existing guards apply unchanged: `test_registry_loads_real_modules` (no import error, hooks without `request`), `test_tasks_never_reach_interactive_claude`, and the conftest fixture that makes a real CLI spawn raise.

## Manifest

Present:

| Item | Version / location | Needed for |
|---|---|---|
| Python | 3.14.7, `.venv/Scripts/python.exe` | everything |
| fastapi, uvicorn, mcp, httpx, pytest | 0.141.1, 0.52.4, 2.2.0, 0.28.1, 9.1.1 installed | routes, tool servers, tests |
| SQLite | 3.50.4 via stdlib | tables; FTS5 available, unused |
| Claude Code CLI | 2.1.263 at `C:/Users/gudo/.local/bin/claude.exe`, claude.ai login | tutor session, nightly generate |
| `MCPServer.list_tools()` | returns tool objects with `.name`, checked 2026-09-07 | the split test |
| Test suite | 16 passed 2026-09-07 | baseline |

Missing: nothing; the item adds no package.

Needs you:

| Item | How |
|---|---|
| Topics | Once phase 1 lands, enter the fourteen listed under Data on the page or by telling the tutor |
| Daemon at night | `python -m app setup` once, then `Get-ScheduledTask -TaskName Otto`; without it the daemon is not running in the 02:00-05:00 window and `generate` never fires (`docs/gaps/logon-task-not-registered.md`) |

Verify:

| Check | Command |
|---|---|
| A scheduled LLM run completes on this machine; `llm_runs` was empty on 2026-09-07 | after the first window: `.venv/Scripts/python.exe -c "import sqlite3; print(sqlite3.connect('data/otto.db').execute('select ts, module, task, status from llm_runs').fetchall())"` |
| `generate` finishes inside `nightly.max_turns` with two read tools | `.venv/Scripts/python.exe -c "import sqlite3; print(sqlite3.connect('data/otto.db').execute(\"select status, result, error from jobs where task = 'education.generate' order by id desc limit 3\").fetchall())"` |
| A refusal reads as `skipped` in Activity | same query on a night `max_sessions` is exhausted |

## Worktree

```
git worktree add ../otto-education -b education
```

Work there; when the branch is merged to `main`, run `/sync-architecture`.

## Pending decisions

1. `[education]` values: `queue_size = 3` follows from three questions a day. Confirm `start_difficulty = 3`, `flow_low = 60`, `flow_high = 85`, or change them.
