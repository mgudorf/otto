# Education

1. Aimed towards teaching concepts and high level understanding; minimal algebra/derivations as it is hard to type by hand.
2. Has a corpus of topics/questions manageable via database. 
3. Progress tracker
4. Aims for "flow state"; balance of difficulty and understanding determined by score range. 
5. Agent grades answers, makes notes of past performance, uses as context when creating future questions, takes into account feedback.
6. Must provide clearly worded questions, must introduce any equations as part of premise/prompt
7. A question is one shared setup with as many parts as that setup genuinely opens on one coherent theme, never a count; every part is intimately related to the original question
8. "Grading" should allow for back and forth communication; i.e. answer given -> LLM response
9. Definitions come first, never inline: every equation or relation named, its variables listed out, then the premise. The premise stays pinned while the parts scroll.
10. Difficulty is 1 to 10: 1-2 very high level concepts, an introduction to the field; 3-5 what an introductory university course contains; 6-8 an advanced undergraduate or masters course; 9-10 expert knowledge.
11. Grading rewards high level answers over written-out equations; LaTeX-esque answers in a raw text box carry typos that must not cost a score.
12. The grade's explanation comes back in the session pane, LaTeX rendered, with the question loaded as the session's context, so the grading is a discourse and an answer can be resubmitted with the first grading in view. The Submit buttons stay, so nothing has to be typed to ask for a grade.
13. Every part has a short reference title, so repeats are avoided and the tutor keeps its focus; a part folds to its title and score.
14. A quiz is completed by a button once every part is scored and moves from the active list to a completed one; unwanted questions are deleted, never struck through; questions, active or completed, take the owner's tags.
   
## Education Constraints

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
5. New tech (pick a new technology, see if I can understand how it works): not built; see Patches.

## Built

| Piece | Current state |
|---|---|
| Facet | `education`, title Education, hue `#86AAE3`. Every row is type `question`, its bar filled by `pct`. Its verbs are `complete` ("Complete quiz"), offered only once every part is scored, then `delete`; a completed question offers none. The page draws one folding card for the definitions and the premise and one per part, each showing its score or, on the part next in line, that the answer goes in the drawer; a question carries no date, since nothing about it is scheduled |
| Tables | `education_topics(name, description, difficulty 1-10, retired_at)`, `education_questions(topic_id, title, topic_tag, definitions (markdown, math in LaTeX; NULL before v2), premise (the scenario), difficulty 1-10, source nightly\|session, tags (JSON list), created_at, opened_at (last opened), started_at (first answer), completed_at, score (mean of the parts once every one is scored), deleted_at)`, `education_question_parts(question_id, n, title (NULL before v2), text, rubric, answer, answered_at, verdict correct\|partial\|incorrect, score 0-100, note (the tutor's record), graded_at)`, `education_feedback` (the owner's words, unchanged; `question_id` survives a delete, since the words still describe that question). The package's `setup` adds the columns an older database lacks, `deleted_at` among them, and rebuilds `education_topics` and `education_questions` once for v2: the 1 to 10 CHECK (a v1 difficulty d becomes 2d-1), `skipped_at` gone with the skipped rows and their parts, `graded_at` renamed `completed_at`; foreign keys are checked afterwards |
| Files | `questions.py` (the shared reads, the generator prompt from `prompts/generate.md`, the reply parser, `validate_question`, `unbound_acronyms`, inserts, `part_title`, `clean_tags`), `grading.py` (`grade_brief` from `prompts/grade.md`, `apply_grade`, `complete`, the tutor's `grade`) |
| Format | definitions (each relation: a bold name, the equation as display LaTeX, one bullet per variable), a premise that refers to them by name, then lettered parts `(a)`, `(b)`, past `(z)` as `(aa)`, each with a 2 to 5 word reference title, one ask and a hidden rubric; a rubric leaves the server only to the tutor and only once its part is graded |
| Routes | `blank` (progress per topic), `item/{id}` (the ROW plus `defs`, `premise`, `parts`, `feedback`, `topic_id` and the dates; the GET stamps `opened_at`, which makes the question the tutor's context), `action/answer` (stores the answer, clears the part's grade, starts the question, and hands the answer to the tutor as one turn through the platform's `pane_turn`, briefed with `prompts/grade.md`; the turn is queued, not awaited; 400 empty, 404 no part, 409 completed), `action/generate` (one question for the topic never asked or asked longest ago, through `oneshot` with `prompts/generate.md`, source `session`, not opened; 409 no active topic, 502 on a rejected reply or one that names no question for that topic, a `warning` for a header acronym the body never binds), `action/{complete\|delete\|tags\|add_topic\|retire_topic}` (`complete` 409 until every part is scored; `delete` on an active question only, stamping `deleted_at`; `tags` replaces the list, trimmed, unique, 40 characters each; `add_topic` revives a retired topic of the same name). `generate` runs on resource `education.llm`, the others on `education`; the grading turn runs on `session:<sid>` like any turn |
| Rows | every list — `queue`, `today` and `rows` — hands back the same shape: `title`, `when` (completed, else created, in the owner's own clock), `fixed` the facet alone, `tags` led by the topic and its tag and then the question's own list and anything the shell wrote to `app_tags`, `snip` (the part titles), `topic`, `difficulty`, `status` active\|completed, `score` (null until the quiz is complete), `done`, and `pct`, the share of parts carrying a stored answer, 100 once complete |
| Hooks | `numbers` (due), `queue` (every question still open, which is what waits on the owner), `today` (the same list), `rows` (every listed question, most recently completed or created first), `item`, `context` (per topic: difficulty of 10, completed/asked, average, recent scores; the active count; the question opened last, whatever its state, with its tags, definitions, premise, each part's title, prompt and answer, and once graded its verdict, score, note and rubric, or that the grade is awaited; the last five completed; recent feedback verbatim) |
| Tools | read: `education_topics`, `education_questions` (status `active\|completed\|deleted`, tags), `education_question` (the notes; rubrics on graded parts only), `education_feedback`; write: `education_add_topic`, `education_add_question(topic_id, title, topic_tag, definitions, premise, parts[{title, prompt, rubric}])` (validated like the generator's output, opened at once), `education_grade(question_id, part, score 0-100, note)` (the verdict follows the score; a call on a graded part revises it; it never completes a quiz), `education_record_feedback` |
| Schedule | `education.generate` every 24h inside the nightly window: `per_night` new questions whatever the queue already holds, one for each topic that has waited longest, one budgeted run with `prompts/generate.md` and no tools; an element is rejected for a missing title, tag, definitions or premise, a part without a title, prompt and rubric, a topic not asked for, or a title already used on the topic; a header acronym the body never binds is logged and kept. The prompt lists each topic's titles already asked with their part titles, deleted ones marked as such, so neither comes back |
| Deletion | `Delete` stamps `deleted_at` and the question is gone from the feed, from `queue`, from `item/{id}` (404), from `education_question`, and from every count and average on the blank state, so a question the owner threw away never served its topic. The row and its parts stay, which is what stops it being asked twice: the generator's never-repeat list names it with `[deleted by the owner]`, `validate_question` still rejects its title on that topic, and `education_questions(status="deleted")` is the one place the tutor sees it |
| Grading | the tutor grades in the drawer: the brief carries the topic, difficulty of 10, definitions, premise, the part's title and prompt, its rubric, the answer, the earlier grade when the part was answered before, and the topic's feedback; it asks for understanding over transcription (typos, notation slips and malformed LaTeX cost nothing; a mechanism in plain words is full credit), for `education_grade` first and the explanation in the reply, which the drawer renders with LaTeX. Scores are 0 to 100 with the verdict from the score; the note is the record, the explanation lives in the session. Once every part is scored the question's mean is kept; a new answer clears its part's grade and the mean until the tutor grades again |
| Flow | a new topic starts at `start_difficulty`; `Complete quiz` sets `completed_at`, keeps the mean, and moves the topic's difficulty by the flow band once: below `flow_low` one step down, above `flow_high` one step up, floor 1 and ceiling 10; a grade revised after completion recomputes the mean and never moves it again |
| Departures | `Reschedule`, `Start` and `Skip` dropped (nothing is scheduled to a date, opening a question is what loads it for the tutor, an unwanted question is deleted); the chips, the Topics view and `Generate` went with the page, so a topic's progress is asked of the tutor and a new question comes from the nightly run or from `education_add_question`; the preview's green and amber tint on a part's score is dropped, since colour is the module's hue on a card's border and on a primary button and nowhere else |

## Patches

### The New tech item has no plan

- Kind: gap
- Where: Education constraint 5 (pick a new technology, see whether the owner can understand how it works)
- Found: 2026-09-10, sync-architecture
- Status: open, needs a decision

What happens: no module, task or page picks a technology or asks about it; the Education topics are the fourteen fixed domains.

Expected: a decision on where the technology comes from (a Newsfeed search is the obvious feed), how one is picked, and how the owner's understanding is checked.

Fix: the owner decides whether it is a mode of Education or of Newsfeed; then one change through `/feature-flow`.

### An answer given in the drawer is never stored

- Kind: gap
- Where: `app/modules/education/routes.py` `action/answer`, `_part_facts`, `_row`; `grading.py` (`grade_brief`), `prompts/grade.md`, `tools.py` (`education_question`)
- Found: 09-21-2026, the one-page change; widened 09-22-2026, the stale-code audit
- Status: open

What happens: answering is a message to Otto with the question and its next part named as the reference. `action/answer` is the only path that writes `education_question_parts.answer`, and nothing calls it, so the words are in the transcript and nowhere else. `started_at` is never stamped, `pct` counts stored answers and so reads 0 on a question that is fully graded, the tutor's context says every part's answer is awaited, and a resubmission cannot be compared with what was said before. The rubric of an ungraded part reaches no agent either: `grade_brief`, built only by `action/answer`, was its one carrier, and `education_question` and Education's context show a rubric only once a part is graded, so the drawer's tutor grades without it, though `agent.md` says the brief carries it.

Expected: the answer the tutor grades is the answer the question holds.

Fix: either the page grows the answer box back and posts `action/answer` (which already briefs the tutor and clears the part's grade), or `education_grade` takes the answer it graded and stores it with the score. The second makes the tutor the only witness of what was written, which is why the first is the shape to rebuild. Either way the tutor needs the rubric before it grades: through the brief, or through `education_question` on an ungraded part. `action/answer` hands its turn to `pane_turn`, which opens an `education` session the drawer never lists, so the first way also means turning in the drawer's own tab.

### A topic cannot be added or retired, and recorded feedback is drawn nowhere

- Kind: gap
- Where: `app/modules/education/routes.py` `blank`, `action/add_topic`, `action/retire_topic`, `detail`'s `feedback`
- Found: 2026-09-20, porting the page to the new shell; narrowed 09-21-2026, the one-page change; corrected 09-22-2026, the stale-code audit
- Status: open

What happens: `blank` answers the per-topic progress and the two topic verbs still work, and nothing on screen reaches any of them. The owner can add a topic only by asking the tutor, whose `education_add_topic` repeats `_add_topic`, and cannot retire one at all: no tool retires a topic, and `retired_at` is written only by the unreachable `retire_topic`. The owner sees a topic's completed count and average only in what the tutor says. `item/{id}` hands back the feedback the owner recorded about a question and the page draws the definitions, the premise and the parts alone, so those words are lost to view.

Expected: the fourteen domains and their progress are the owner's to see and change, and the feedback given about a question reads beside it.

Fix: progress per topic is a shape the feed has no place for — a topic is not a row — so it wants the brain or a facet callout rather than a card; the feedback is one more block in the `question` renderer, under the parts.

### Education has a tag of its own, and draws its topic as a tag

- Kind: defect
- Where: `app/modules/education/routes.py` (`_row_tags`, the context line, the generator's fields), `questions.py` (`validate_question`, `insert_question`, `add_question`, `unbound_acronyms`), `schema.sql` (`topic_tag`), `tasks.py`, `tools.py` (`education_add_question`, `education_questions`), `prompts/generate.md` (the output shape, `topic_tag`, rule 13), `agent.md`; `docs/design/data.js` (the sample questions' `hyperbolic-geometry`)
- Found: 09-21-2026, the owner seeing `#probability and statistics` and `#estimation and inference` on a row
- Status: open

What happens: `_row_tags` puts the topic's name and the question's `topic_tag` at the head of the row's tags, so they are drawn, narrowed on and placed on the brain as tags, but nobody gave them and the × cannot take them off. `topic_tag` is a tag of Education's own: a 2 to 5 word "facet within the topic" that the generator and `education_add_question` must supply, checked for acronyms and stored in its own column. A topic named "Probability and statistics" becomes a three-word tag on every question under it. The page draws neither anywhere else.

Expected: Education has no tag of its own. A question carries ordinary tags, one word each, given by the generator and the tutor like any agent's: `estimation`, `inference`, `probability`, `statistics`. The topic stays what the generator writes for and is never drawn as a tag, so it shows nowhere on the page.

Fix: `topic_tag` goes wherever it is named: the column through the data-migration skill, the generator's output shape and rule 13, the tool's argument, validation and the acronym check. The generator and `education_add_question` take `tags`, kept through `word_tags` and written to the one store of the platform entry "A tag lives in one of six stores"; `_row_tags` reads that store alone. The artboard's sample questions carry one-word tags.

### Code nothing reaches

- Kind: defect
- Where: `app/modules/education/routes.py` (`action/generate` with `RESOURCE_LLM`, `_reason` and the `JobFailed` and `questions` imports; the `ACTIVE` import; `item_route`'s `opened_at` stamp; the rows' `topic`, `difficulty` and `score`), `questions.py` (`open_question`), `tools.py` (`register`'s `config=None`, `config or load()` and the `load` import), `grading.py` (`complete`'s ungraded-part error), `tests/test_education.py` (the `generate` calls, the assertions on the tutor's context)
- Found: 09-22-2026, the stale-code audit
- Status: open

What happens: `action/generate` writes one question on demand through the nightly generator's own steps; its fixed path is one `/api/verb` cannot reach, nothing else calls it, and this doc's Routes row still lists it. Opening a question stamps `opened_at` so that Education's context can show "the question open on the page", but that context now reaches only the nightly generator, which has no use for it: the drawer's Current state is Home's. The feed rows carry `topic`, `difficulty` and `score`, which the page never reads. `register` falls back to `load()` when the daemon passes no config, and the daemon always passes one; its comment says the opposite. `complete` refuses a quiz with ungraded parts, which `_complete` has already refused. `ACTIVE` is imported and unused.

Expected: Education serves what the feed, the verbs, the tools and the nightly run use.

Fix: delete them and their tests. Whether the item open in the drawer should reach the agent's prompt is the platform's question, in "Five modules build a Current state that no agent receives".
