# Education Plan

Status: planning, 2026-09-09. Version 1, on the built v0 base (2026-09-08).

Education keeps a queue of questions on the owner's topics and grades the owner's answers. Version 1 brings
back the question and answer format of the owner's previous project (`mylife`): one titled question with a
shared setup written in markdown and LaTeX, three to five lettered parts each with a hidden rubric, an answer
box under every part, and a verdict with an explanation landing right where the answer was typed. The
generator's rules come over with it. The tutor on the right stays the place for conversation. Without it the
middle shows plain-text questions written to a one-line rule, and every answer has to be typed into the chat.

## Sources

| Source | Governs |
|---|---|
| The request (this session) | Bring the middle panel closer to the old module's functionality: question format, answer format, question content (the generator, never the old data); the session pane supersedes every agentic piece of the old project |
| `C:\Users\gudo\Desktop\mylife\modules\education\prompts\generate_question.md` | the question shape, the title and tag specs, the fourteen rules |
| `…\mylife\modules\education\prompts\grade_turn.md` | verdict, score in halves of two, explanation rules |
| `…\mylife\modules\education\engine\generate.py`, `grade.py`, `db.py` | validation, the header-acronym check, the context blocks, what a graded part stores |
| `…\mylife\modules\education\static\module.js`, `module.css` | the question view: chips, setup, part letter, answer box, answer-given block, explanation block, score pill; `renderMD` (marked + KaTeX) |
| `…\mylife\modules\education\backend.py`, `module.json`, `docs\tasks\completed\education\v1_*.md`, `v2-*.md` | what the old module exposed and why the format is what it is; the pieces not ported |
| `docs/ARCHITECTURE.md` Education (1, 6, 7, 8; constraints 1, 3, 4), Daemon, Claude (`oneshot`), Module contract, Config, UI frame contract | requirements, the read/write split, the user-triggered run, tokens, hue `#7a9fd6`, order 2 |
| `docs/design/Personal Dashboard App.dc.html` `eduGroups`, `selInfo`, line 221 | LEFT rows (unchanged), inspector actions and frame |
| `app/modules/education/*`, `app/static/pages/education.js`, `shell.js` (`Inspector`), `rows.js`, `api.js`, `app/claude.py`, `app/runner.py`, `app/daemon.py`, `app/store.py` | the built v0, the run paths, the build order (schemas, then `setup`) |
| `app/modules/feedback/routes.py`, `app/modules/science/__init__.py` | `oneshot` from a route; `setup(config)` on a module package |
| `docs/roadmap/education/PLAN.md` v0 | the decisions that stand (below) |
| `data/otto.db`, read-only today | 14 topics at d3; 3 nightly questions in the v0 shape, none answered; `education.generate` ran 2026-09-09 02:00 local |
| `tests/test_education.py`, `test_app.py`, `test_platform.py`, `conftest.py` | fixtures, the fake CLI, the AST guard over `tasks.py` |

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | The question shape is `mylife`'s: `title` (3 to 8 words, not a question), `topic_tag` (the facet, 2 to 5 words), a setup in markdown with math in LaTeX (`questions.premise` keeps its column), then 3 to 5 parts `(a)`…`(e)`, each one ask with a hidden rubric | The format the owner liked. Requirement 7 fixes the count at 3 to 5 where the old prompt allowed 7; one constant, `PARTS` |
| 2 | One generator, `prompts/generate.md`: the old prompt's altitude paragraph and rules verbatim (define every variable and equation, no unexplained names, cross-field-expert basis, definitions in and explanations out, no leading, one ask per part, self-answer test, conceptual not computational, LaTeX, header acronyms bound in the body), plus Otto's topic context (difficulty 1 to 5, what the owner wants, every title asked, the last grades, the owner's feedback verbatim). It asks for one question per listed topic as a JSON array | The old altitude says what kind of question; the flow difficulty says how deep; they compose. One template, one parser, one validator on every path. An array keeps the nightly run one budgeted session for `queue_size` topics; a page press lists one topic |
| 3 | A `Generate` button on the blank state: `POST action/generate` runs the generator through `oneshot` for the topic that has waited longest, awaited by the route, and the page selects the new question | The old module's one question per press; the only on-demand path through the generator rather than the tutor's hand. `oneshot` from a route is the Feedback precedent; unbudgeted |
| 4 | Grading happens on the page. Submit stores the answer, starts the question, and runs `prompts/grade.md` (the old `grade_turn` reduced to one turn: verdict, score 0 to 2 in halves, explanation) through `oneshot`, awaited; the part then shows the answer, the explanation and a score pill in the verdict's colour | The answer format the owner liked. The exchange that followed in the old project (follow-ups, resolve) is the tutor's job now |
| 5 | One graded answer per part on the page; the conversation about it continues in the session pane, where the tutor revises with `education_grade` | The right pane supersedes the old Socratic loop; the middle holds no exchange state |
| 6 | Scores stay 0 to 100 in the store (the grader's halves times 50, the verdict stored beside it); question score, flow band, LEFT bars and the topic table are unchanged | Every reader keeps working; one conversion at one seam |
| 7 | Rubrics never reach the page; the tutor sees a part's rubric only once that part is graded | Before an answer the rubric is the answer |
| 8 | `questions.topic_tag` and `question_parts.rubric, answer, answered_at, verdict` are added by the module's `setup(config)` when the live table lacks them. No rename anywhere | `Store.migrate` only creates; `schema.sql` cannot add a column to a table that exists. The three v0 questions on disk stay answerable: no tag chip, and the grader is told there is no rubric |
| 9 | Markdown and LaTeX render through vendored `marked` 18.0.12 and KaTeX 0.18.7: `app/static/md.js` exports one `Markdown` component; the KaTeX stylesheet and its woff2 fonts sit under `app/static/vendor/katex/`; `SHA256SUMS` grows | The old project loaded both from a CDN; Otto vendors everything and runs offline |
| 10 | The education page draws its own question view (header line, title, chips, setup, parts, answer blocks, actions) in the inspector's frame conventions; Home keeps the generic inspector with the self-contained `text` | The generic inspector renders pre-wrapped text; this format needs markdown |
| 11 | Verdict colours: correct `#7fb894`, partial `#d1a36a`, incorrect `#cf7b7b`, the palette's green, amber and red | The artboard names no verdict colours; a named departure |
| 12 | The nightly `generate` passes no tools | The prompt carries every title already asked; a tool turn is a wasted turn against `max_turns` |
| 13 | No retry on a rejected generation: the nightly rejects the element, a press answers 502 with the reason. An unbound header acronym is accepted with a warning in the event text and the response | A retry doubles a budgeted session; the old rule stands: a crude check never costs a failed press |
| 14 | `education_add_question` keeps the tutor's hand-written path in the new shape; the difficulty is the topic's | "quiz me on X now" stays a sentence to the tutor; the same validator gates both writers |
| 15 | Actions stay `Start` and `Skip`; a submitted answer starts its question by itself | Home's inspector and the tutor's Current state key on the started question; the old view had no start step |
| 16 | Not ported: assessments, educator rules and their compression, curriculum proposals and coverage, FSRS scheduling and the concept graph, misconceptions, takeaways, per-part feedback chips, delete | The request names three things. Conversation and feedback live in the session pane (`education_record_feedback`); the curriculum is the topics table |

Standing from v0: 2, 3 (a part is graded on its own), 4 (difficulty per topic and the flow band), 5, 6, 8, 9, 10, 11, 12, 13, 14. Superseded: v0 decision 1 (grading in the session) by 4 and 5; v0 decision 7 keeps the tool but in the new shape (14).

Rejected: grading in the tutor session with the page as a mirror (the middle would wait on a tool call it cannot see, and the explanation would show twice); multi-turn grading on the page (the session pane exists for that); CDN scripts; 0 to 2 scores in the store (every reader would change); a `migrate(store)` hook on the module contract (a shared seam every branch conflicts on, for one module's five columns); a per-topic Generate control (the breadth rule picks the topic); a takeaway line (a fourth LLM call for a line the owner did not ask for); keeping the old 3 to 7 parts (requirement 7 says 3 to 5; pending decision 1).

## Layout

| File | Change |
|---|---|
| `app/modules/education/__init__.py` | `setup(config)` adds the five columns when a table lacks them |
| `app/modules/education/schema.sql` | the columns on fresh databases, comments updated |
| `app/modules/education/prompts/generate.md` | the generator, from `generate_question.md` |
| `app/modules/education/prompts/grade.md` | the grader, from `grade_turn.md` |
| `app/modules/education/questions.py` | new: the shared reads (moved from `routes.py`), `render`, `waiting_topics`, `generate_prompt`, `parse_array`, `validate_question`, `unbound_acronyms`, `insert_question`, `add_question` |
| `app/modules/education/grading.py` | new: `grade_prompt`, `parse_grade`, `verdict_for`, `apply_grade`, `grade` (moved from `tools.py`) |
| `app/modules/education/tasks.py` | `generate` renders the generator, passes no tools, validates each element |
| `app/modules/education/routes.py` | `item` in the new shape; `POST action/answer`, `POST action/generate`; `context` in the new shape |
| `app/modules/education/tools.py` | tools only; `education_add_question` new signature; `education_question` adds graded rubrics; `education_questions` adds `topic_tag` |
| `app/modules/education/agent.md` | the tutor's job now |
| `app/static/md.js` | new: `Markdown` (marked + KaTeX), the stylesheet link and the `.md` rules injected once |
| `app/static/vendor/katex/{katex.mjs, katex.min.css, fonts/*.woff2}`, `app/static/vendor/marked.esm.js`, `SHA256SUMS` | the renderers |
| `app/static/pages/education.js` | the question view with answer boxes; `Generate` on the blank state |
| `tests/test_education.py` | rewritten, below |

Untouched: `app/config.py`, `config.toml`, `app/static/shell.js`, `app/modules/__init__.py`, the other modules. No new knob: the format constants (`PARTS`, the halves-to-percent scale, the label letters) are the format, not settings.

## Contract

Manifest, schedule (`education.generate`, 24h, resource `education`, llm), hooks `numbers` and `today`, and the routes `left`, `blank`, `action/{start|skip|add_topic|retire_topic}` are unchanged.

| Route | Wire shape |
|---|---|
| `GET /api/education/item/{id}` | `{id, module, kind: "<topic> · d<difficulty>[ · <score>]", title, topic, topic_id, topic_tag, text, setup, difficulty, source, status, score, created_at, parts: [{n, label, text, answer, answered_at, verdict, score, note, graded_at}], feedback, actions}`. `text` stays self-contained (title, setup, `(a) prompt` lines) for Home and the Feedback control. No rubric |
| `POST /api/education/action/answer` `{id, n, answer}` | `{id, n, verdict, score}`. 400 empty; 404 no question or part; 409 question graded or skipped, or part graded. Writes `answer, answered_at`, sets `started_at` (un-starting any other), then runs `education.grade` on resource `education.llm` and awaits it: `oneshot` with `grade.md`, reply `{verdict, score, explanation}`, `apply_grade` in one commit; the last part completes the question and moves the topic's difficulty once (v0 rule). A failed run answers 502 with the reason; the answer stays, Submit is offered again |
| `POST /api/education/action/generate` `{}` | `{id, warning?}`. 409 no active topic. `education.generate_now` on `education.llm`, awaited: `oneshot` with `generate.md` for the topic that has waited longest, the element validated, inserted with `source = session` (on the owner's demand, as the tutor's are) and not started; event `generated` carrying any acronym warning. 502 with the reason on a rejected reply |

| Tool | Server | Does |
|---|---|---|
| `education_topics()`, `education_feedback(topic_id=None)` | read | unchanged |
| `education_questions(topic_id=None, status=None, limit=50)` | read | unchanged plus `topic_tag` |
| `education_question(id)` | read | the item shape plus `rubric` on graded parts only |
| `education_add_topic`, `education_record_feedback` | full | unchanged |
| `education_add_question(topic_id, title, topic_tag, setup, parts)` | full | `parts` is 3 to 5 of `{prompt, rubric}`; validated as the generator's output is; difficulty from the topic; starts at once |
| `education_grade(question_id, part, score, note)` | full | score 0 to 100, note is the explanation shown under the answer; verdict from the score (100 correct, 0 incorrect, else partial); completion and flow as before |

`context(store, registry)`: the topic table; the due count; the started question in full (title, tag, setup, then each part with its prompt, the answer or "not answered", the verdict, score and explanation once graded, and the rubric once graded); the last five graded; the latest feedback verbatim.

The tutor: the owner answers on the page and each answer is graded there; the tutor discusses a graded part in plain language, revises with `education_grade` when the owner pushes back well, records the owner's words with `education_record_feedback`, writes a question on request in the full shape after checking `education_questions`, adds topics only when asked, and prefers breadth over depth.

Page. LEFT unchanged. MIDDLE selected: the inspector's header line (glyph in the hue, mono `kind · date time`, `×`), the title at 17px/600, two ringed chips (topic, tag), the setup as markdown, then each part: `(a)` in the hue and mono, the prompt as markdown, and under it either a raised 4-row textarea with `Submit` (Ctrl+Enter) showing `grading…` while the run is in flight, or the graded block: the answer in a raised box with a 3px left border in the verdict colour, the score in mono in that colour, then the explanation as markdown on a faint hue ground. A part of a graded or skipped question that was never answered reads `not answered`. The owner's feedback lines, then `Start`/`Skip` from `actions` and `Send to session`, which prefills `Q<id> "<title>": `. MIDDLE blank: `Generate` (primary, `generating…` while it runs) above the v0 topic table and add-topic box.

Departures from the artboard: v0's stand (no `Reschedule`, LEFT leads with `due`, the blank state); the verdict colours; the `Generate` button; markdown in the middle where the artboard's inspector shows plain text.

## Data

| Table | Columns |
|---|---|
| `questions` | v0 plus `topic_tag TEXT` (NULL on v0 rows) |
| `question_parts` | v0 plus `rubric TEXT`, `answer TEXT`, `answered_at TEXT`, `verdict TEXT CHECK (correct\|partial\|incorrect)`; `note` is now the explanation |
| `topics`, `education_feedback` | unchanged |

Migration: `setup(config)` opens `config.data.db`, reads `PRAGMA table_info` for the two tables and issues `ALTER TABLE … ADD COLUMN` for each missing column; a fresh database already has them from `schema.sql`, so it is a no-op there. Runs at every boot, idempotent. The v0 rows on disk keep working: the page omits the missing chip and the grader is told there is no rubric.

| Path | Client | Writes |
|---|---|---|
| `education.generate` (scheduled) | `ctx.run_task`, no tools, budgeted | its questions and parts plus the cursor, one `ctx.commit` |
| `education.generate_now`, `education.grade` (actions on `education.llm`) | `st.claude.oneshot` on `otto-read`, unbudgeted | one question, or one part's grade, in one `ctx.commit` |
| tutor session | full server | topics, session questions, re-grades, feedback |
| page actions on `education` | `run_action` | start, skip, topic add and retire; `answer` writes the answer before its job |

The split is proved by `test_education_tool_split` (unchanged), the AST guard over `tasks.py`, and `test_education_end_to_end` asserting that the grade run's spawn names `otto-read` and `--no-session-persistence`.

## Phases

| Phase | Builds | Usable result |
|---|---|---|
| 1 | columns and `setup`, `generate.md`, `questions.py`, `tasks.py`, `action/generate`, tools, the vendored renderers, `md.js`, the question view with parts read-only | Press `Generate`: a titled question with chips, a setup with rendered LaTeX and lettered parts appears in the middle; the nightly writes the same shape |
| 2 | `grade.md`, `grading.py`, `action/answer`, the answer boxes and graded blocks, `context`, `agent.md` | Answer part (a) on the page and watch the verdict, score and explanation land under it; the LEFT bar and the topic table move; the tutor discusses the graded part and revises the score |

## Tests

- `test_education_end_to_end`: a fake CLI answering in sequence (generate reply, grade replies, one non-JSON reply). Add a topic; `add_question` refuses two parts and a part without a rubric, accepts four; `item` carries labels and no rubric; `action/generate` inserts a question with rubrics and writes the event; `action/answer` grades part (a) to `correct` 100, starts the question, and the tutor's context shows the answer, the explanation and the rubric; a non-JSON reply answers 502 and keeps the answer, the retry grades it; 409 on a graded part, 400 empty, 404 bad part; `grade` completes the question, the topic's difficulty rises, LEFT shows the score, the spawn args of the grade run name `otto-read` and `--no-session-persistence`; search, skip, retire and return as in v0.
- `test_generate_task`: reply array with one good element, a second for the same topic, a wrong topic, two parts, a part without a rubric: one inserted with rubrics and `source = nightly`, four rejected; cursor written; a budget refusal ends `skipped`; a full queue spends no run.
- `test_setup_adds_columns`: a v0-shaped database gains the five columns after `setup(config)`; a second call is a no-op; the v0 question still serves through `item`.
- `test_unbound_acronyms`: `Tokenization and BPE` with a setup that never binds it → `["BPE"]`; bound → `[]`.
- `test_education_tool_split` and the existing guards unchanged; the suite stays offline.

## Manifest

Present

| Item | Version / location | Needed for |
|---|---|---|
| Python | 3.14.7, `.venv/Scripts/python.exe` | everything |
| fastapi, uvicorn, mcp, httpx, pytest | 0.141.1, 0.52.4, 2.2.0, 0.28.1, 9.1.1 | routes, tools, tests |
| SQLite | 3.50.4 via stdlib; `ALTER TABLE ADD COLUMN` with a CHECK | the migration |
| Claude Code CLI | 2.1.263 at `C:/Users/gudo/.local/bin/claude.exe` | `oneshot`, `run_task` |
| `ClaudeRunner.oneshot(ctx, mod, prompt, tools=(), max_turns=2)` | `app/claude.py`, main `191715e` | the two page runs |
| Test suite | 52 passed today in `../otto-education` at `191715e` | baseline |
| `data/otto.db` | 14 topics, 3 v0 questions, 0 answers; last `education.generate` done 2026-09-09 02:00 local | the migration target |
| jsdelivr and the npm registry | reachable today (`registry.npmjs.org`, `cdn.jsdelivr.net`) | fetching the renderers once |

Missing

| Package | Version | Needed for | Install target |
|---|---|---|---|
| katex (MIT) | 0.18.7 on npm: `dist/katex.mjs` 602,874 B, `dist/katex.min.css` 24,788 B, `dist/fonts/*.woff2` 20 files 259,792 B | LaTeX in setups, prompts and explanations | `app/static/vendor/katex/`, fetched from `https://cdn.jsdelivr.net/npm/katex@0.18.7/…`, sha256 into `SHA256SUMS` |
| marked (MIT) | 18.0.12 on npm: `lib/marked.esm.js` 43,991 B | markdown in the same places | `app/static/vendor/marked.esm.js`, same way |

Needs you

| Item | How |
|---|---|
| The merge | `main` is mid-merge with `web_search` from another session (conflicts in `app/config.py`, `config.toml`, `app/static/shell.js`). This branch is committed on `education` and merges after that resolves: `git merge main` on the branch, run the suite, merge into `main`, `/sync-architecture` |
| Daemon restart after the merge | `python -m app` restarts on the revision change; the columns land at boot |
| The three v0 questions | answer or skip them; they render without a tag chip and grade without a rubric |

Verify

| Check | Command |
|---|---|
| The columns exist after the restart | `.venv/Scripts/python.exe -c "import sqlite3; c=sqlite3.connect('data/otto.db'); print([r[1] for r in c.execute('pragma table_info(question_parts)')])"` |
| A page grade was unbudgeted on `otto-read` | `.venv/Scripts/python.exe -c "import sqlite3; print(sqlite3.connect('data/otto.db').execute(\"select ts, task, status, budgeted from llm_runs where module='education' order by id desc limit 3\").fetchall())"` |
| Rubrics never leave the server | `curl -s http://127.0.0.1:8765/api/education/item/1 \| findstr rubric` prints nothing |

## Worktree

```
git worktree add ../otto-education -b education
```

Exists; fast-forwarded to `main` at `191715e` today. Work there. When `education` is merged to `main`, run `/sync-architecture`.

## Pending decisions

1. Parts per question: 3 to 5 as requirement 7 says (built), or the old prompt's 3 to 7? One constant, `PARTS` in `questions.py`, and the two numbers in `generate.md` follow it.
