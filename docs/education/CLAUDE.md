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

### Built

| Piece | Current state |
|---|---|
| Tables | `topics(name, description, difficulty 1-10, retired_at)`, `questions(topic_id, title, topic_tag, definitions (markdown, math in LaTeX; NULL before v2), premise (the scenario), difficulty 1-10, source nightly\|session, tags (JSON list), created_at, opened_at (last opened on the page), started_at (first answer), completed_at, score (mean of the parts once every one is scored), deleted_at)`, `question_parts(question_id, n, title (NULL before v2), text, rubric, answer, answered_at, verdict correct\|partial\|incorrect, score 0-100, note (the tutor's record), graded_at)`, `education_feedback` (the owner's words, unchanged; `question_id` survives a delete, since the words still describe that question). The package's `setup` adds the columns an older database lacks, `deleted_at` among them, and rebuilds `topics` and `questions` once for v2: the 1 to 10 CHECK (a v1 difficulty d becomes 2d-1), `skipped_at` gone with the skipped rows and their parts, `graded_at` renamed `completed_at`; foreign keys are checked afterwards |
| Files | `questions.py` (the shared reads, the generator prompt from `prompts/generate.md`, the reply parser, `validate_question`, `unbound_acronyms`, inserts, `part_title`, `clean_tags`), `grading.py` (`grade_brief` from `prompts/grade.md`, `apply_grade`, `complete`, the tutor's `grade`) |
| Format | definitions (each relation: a bold name, the equation as display LaTeX, one bullet per variable), a premise that refers to them by name, then lettered parts `(a)`, `(b)`, past `(z)` as `(aa)`, each with a 2 to 5 word reference title, one ask and a hidden rubric; a rubric leaves the server only to the tutor and only once its part is graded |
| Routes | `left` (`chip` `active`: the queue in one `due` group, questions with an answer first, then oldest first; `completed`: history by completion day, paged; the search reads title, definitions, premise, tags and part titles), `blank` (progress per topic, add-topic box), `item/{id}` (`text` carries title, setup and parts for Home and Feedback; the GET stamps `opened_at`, which makes the question the tutor's context), `action/answer` (stores the answer, clears the part's grade, starts the question, and hands the answer to the tutor as one turn of the pane through the platform's `pane_turn`: the Education pane's newest open tab, or a new one when none is open, briefed with `prompts/grade.md`; the turn is queued, not awaited, and the response names the session; 400 empty, 404 no part, 409 completed), `action/generate` (one question for the topic never asked or asked longest ago, through `oneshot` with `prompts/generate.md`, source `session`, not opened; 409 no active topic, 502 on a rejected reply or one that names no question for that topic, a `warning` for a header acronym the body never binds), `action/{complete\|delete\|tags\|add_topic\|retire_topic}` (`complete` 409 until every part is scored; `delete` on an active question only, stamping `deleted_at`; `tags` replaces the list, trimmed, unique, 40 characters each; `add_topic` revives a retired topic of the same name). `generate` runs on resource `education.llm`, the others on `education`; the grading turn runs on `session:<sid>` like any turn of the pane |
| Hooks | `numbers` (due), `today` (the active queue), `item`, `context` (per topic: difficulty of 10, completed/asked, average, recent scores; the active count; the question opened last on the page, whatever its state, with its tags, definitions, premise, each part's title, prompt and answer, and once graded its verdict, score, note and rubric, or that the grade is awaited; the last five completed; recent feedback verbatim) |
| Tools | read: `education_topics`, `education_questions` (status `active\|completed\|deleted`, tags), `education_question` (the notes; rubrics on graded parts only), `education_feedback`; write: `education_add_topic`, `education_add_question(topic_id, title, topic_tag, definitions, premise, parts[{title, prompt, rubric}])` (validated like the generator's output, opened at once), `education_grade(question_id, part, score 0-100, note)` (the verdict follows the score; a call on a graded part revises it; it never completes a quiz), `education_record_feedback` |
| Schedule | `education.generate` every 24h inside the nightly window: `per_night` new questions whatever the queue already holds, one for each topic that has waited longest, one budgeted run with `prompts/generate.md` and no tools; an element is rejected for a missing title, tag, definitions or premise, a part without a title, prompt and rubric, a topic not asked for, or a title already used on the topic; a header acronym the body never binds is logged and kept. The prompt lists each topic's titles already asked with their part titles, deleted ones marked as such, so neither comes back |
| Deletion | `Delete` stamps `deleted_at` and the question is gone from both chips, from `today`, from `item/{id}` (404), from `education_question`, and from every count and average on the blank state, so a question the owner threw away never served its topic. The row and its parts stay, which is what stops it being asked twice: the generator's never-repeat list names it with `[deleted by the owner]`, `validate_question` still rejects its title on that topic, and `education_questions(status="deleted")` is the one place the tutor sees it |
| Grading | the tutor grades in the session: the brief carries the topic, difficulty of 10, definitions, premise, the part's title and prompt, its rubric, the answer, the earlier grade when the part was answered before, and the topic's feedback; it asks for understanding over transcription (typos, notation slips and malformed LaTeX cost nothing; a mechanism in plain words is full credit), for `education_grade` first and the explanation in the reply, which the pane renders with LaTeX. Scores are 0 to 100 with the verdict from the score; the note is the record, the explanation lives in the session. Once every part is scored the question's mean is kept; a new answer clears its part's grade and the mean until the tutor grades again |
| Flow | a new topic starts at `start_difficulty`; `Complete quiz` sets `completed_at`, keeps the mean, and moves the topic's difficulty by the flow band once: below `flow_low` one step down, above `flow_high` one step up, floor 1 and ceiling 10; a grade revised after completion recomputes the mean and never moves it again |
| Page | LEFT: search, chips `active` and `completed`, rows with a progress bar (an active question's is the share of parts graded, a completed one's its score); MIDDLE blank: `Generate` above a row per topic (difficulty, done/asked, average, recent scores, last asked, retire) and the add-topic box; MIDDLE selected: title, topic and tag chips, the owner's tags each with `×` and a `+ tag` box (Enter or blur adds), then the setup pinned at the top of the track while the parts scroll (definitions, folded by their label; premise; the block capped at half the viewport and scrolling inside), each part a row (letter, title, score, caret) that folds it, graded parts sitting folded until opened, an open part showing the prompt, the answer box with `Submit` or `Resubmit` (Ctrl+Enter) and a status line (`sending…`, with the tutor, graded); a completed question shows each answer read-only; the owner's feedback lines; `Complete quiz` (primary, once every part is scored), `Delete` (confirmed), `Send to session`; an action that fails says so in a fixed line under the buttons. Question prose is 16px; the session pane renders the tutor's turns as markdown with LaTeX |
| Departures | `Reschedule`, `Start` and `Skip` dropped (nothing is scheduled to a date, opening a question is what loads it for the tutor, an unwanted question is deleted); LEFT is two chips rather than every question grouped by date; verdict colours correct `#7fb894`, partial `#d1a36a`, incorrect `#cf7b7b`; `Generate`, answer boxes, tags, the pinned setup and markdown in MIDDLE are not drawn in the artboard; the blank state is unspecified there |

## Patches

### The pinned setup cuts off with no cue when it is taller than half the viewport

- Kind: defect
- Where: `app/static/pages/education.js` the pinned setup block (`maxHeight: '50vh'`, `overflow: 'auto'`); `app/static/index.html` hides every scrollbar (`scrollbar-width: none`)
- Found: 2026-09-13, the education quiz work, in the headless smoke test
- Status: open

What happens: definitions plus premise longer than half the viewport are clipped at the block's cap. The block scrolls under the wheel and folding the definitions frees the space, but nothing shows that more is there: no scrollbar, no fade, and the premise can sit entirely below the cut on first open.

Expected: the owner can see that the setup continues, or the premise is never hidden by the definitions above it.

Fix: a fade at the block's bottom edge while it can scroll, or start with the definitions folded whenever the block would exceed its cap, so the premise is always in view.

### The New tech item has no plan

- Kind: gap
- Where: Education constraint 5 (pick a new technology, see whether the owner can understand how it works)
- Found: 2026-09-10, sync-architecture
- Status: open, needs a decision

What happens: no module, task or page picks a technology or asks about it; the Education topics are the fourteen fixed domains.

Expected: a decision on where the technology comes from (the nightly search's `work` findings are the obvious feed), how one is picked, and how the owner's understanding is checked.

Fix: the owner decides whether it is a mode of Education or of Search; then one change through `/feature-flow`.
