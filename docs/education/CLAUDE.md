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
| Tables | `education_topics(name, description, difficulty 1-10, retired_at)`, `education_questions(topic_id, title, topic_tag, definitions (markdown, math in LaTeX; NULL before v2), premise (the scenario), difficulty 1-10, source nightly\|session, tags (JSON list), created_at, opened_at (last opened on the page), started_at (first answer), completed_at, score (mean of the parts once every one is scored), deleted_at)`, `education_question_parts(question_id, n, title (NULL before v2), text, rubric, answer, answered_at, verdict correct\|partial\|incorrect, score 0-100, note (the tutor's record), graded_at)`, `education_feedback` (the owner's words, unchanged; `question_id` survives a delete, since the words still describe that question). The package's `setup` adds the columns an older database lacks, `deleted_at` among them, and rebuilds `education_topics` and `education_questions` once for v2: the 1 to 10 CHECK (a v1 difficulty d becomes 2d-1), `skipped_at` gone with the skipped rows and their parts, `graded_at` renamed `completed_at`; foreign keys are checked afterwards |
| Files | `questions.py` (the shared reads, the generator prompt from `prompts/generate.md`, the reply parser, `validate_question`, `unbound_acronyms`, inserts, `part_title`, `clean_tags`), `grading.py` (`grade_brief` from `prompts/grade.md`, `apply_grade`, `complete`, the tutor's `grade`) |
| Format | definitions (each relation: a bold name, the equation as display LaTeX, one bullet per variable), a premise that refers to them by name, then lettered parts `(a)`, `(b)`, past `(z)` as `(aa)`, each with a 2 to 5 word reference title, one ask and a hidden rubric; a rubric leaves the server only to the tutor and only once its part is graded |
| Routes | `left` (every listed question in one group with no label: the queue first, questions with an answer ahead of the rest, then the completed history newest first and capped at 200; the chips and the search bar narrow it in the browser), `blank` (progress per topic), `item/{id}` (the row plus `definitions`, `premise`, `parts`, `feedback`, `actions`, and `text`, which carries title, setup and parts for Home and Feedback; the GET stamps `opened_at`, which makes the question the tutor's context), `action/answer` (stores the answer, clears the part's grade, starts the question, and hands the answer to the tutor as one turn of the pane through the platform's `pane_turn`: the Education pane's newest open tab, or a new one when none is open, briefed with `prompts/grade.md`; the turn is queued, not awaited, and the response names the session; 400 empty, 404 no part, 409 completed), `action/generate` (one question for the topic never asked or asked longest ago, through `oneshot` with `prompts/generate.md`, source `session`, not opened; 409 no active topic, 502 on a rejected reply or one that names no question for that topic, a `warning` for a header acronym the body never binds), `action/{complete\|delete\|tags\|add_topic\|retire_topic}` (`complete` 409 until every part is scored; `delete` on an active question only, stamping `deleted_at`; `tags` replaces the list, trimmed, unique, 40 characters each; `add_topic` revives a retired topic of the same name). `generate` runs on resource `education.llm`, the others on `education`; the grading turn runs on `session:<sid>` like any turn of the pane |
| Rows | every list — `left`, `today` and `rows` — hands back the same shape: `title`, `when` (completed, else created), `topic`, `difficulty`, `status` active\|completed, `score` (null until the quiz is complete), `pct` (the share of parts carrying an answer, 100 once complete), `snippet` (the part titles, which is what the search bar reads), `fixed` (the topic, then the question's facet tag; read-only), and `tags`, the question's own list first and then whatever the shell wrote to `app_tags` |
| Hooks | `numbers` (due), `today` (the active queue), `rows` (every listed question, most recently completed or created first), `item`, `context` (per topic: difficulty of 10, completed/asked, average, recent scores; the active count; the question opened last on the page, whatever its state, with its tags, definitions, premise, each part's title, prompt and answer, and once graded its verdict, score, note and rubric, or that the grade is awaited; the last five completed; recent feedback verbatim) |
| Tools | read: `education_topics`, `education_questions` (status `active\|completed\|deleted`, tags), `education_question` (the notes; rubrics on graded parts only), `education_feedback`; write: `education_add_topic`, `education_add_question(topic_id, title, topic_tag, definitions, premise, parts[{title, prompt, rubric}])` (validated like the generator's output, opened at once), `education_grade(question_id, part, score 0-100, note)` (the verdict follows the score; a call on a graded part revises it; it never completes a quiz), `education_record_feedback` |
| Schedule | `education.generate` every 24h inside the nightly window: `per_night` new questions whatever the queue already holds, one for each topic that has waited longest, one budgeted run with `prompts/generate.md` and no tools; an element is rejected for a missing title, tag, definitions or premise, a part without a title, prompt and rubric, a topic not asked for, or a title already used on the topic; a header acronym the body never binds is logged and kept. The prompt lists each topic's titles already asked with their part titles, deleted ones marked as such, so neither comes back |
| Deletion | `Delete` stamps `deleted_at` and the question is gone from both chips, from `today`, from `item/{id}` (404), from `education_question`, and from every count and average on the blank state, so a question the owner threw away never served its topic. The row and its parts stay, which is what stops it being asked twice: the generator's never-repeat list names it with `[deleted by the owner]`, `validate_question` still rejects its title on that topic, and `education_questions(status="deleted")` is the one place the tutor sees it |
| Grading | the tutor grades in the session: the brief carries the topic, difficulty of 10, definitions, premise, the part's title and prompt, its rubric, the answer, the earlier grade when the part was answered before, and the topic's feedback; it asks for understanding over transcription (typos, notation slips and malformed LaTeX cost nothing; a mechanism in plain words is full credit), for `education_grade` first and the explanation in the reply, which the pane renders with LaTeX. Scores are 0 to 100 with the verdict from the score; the note is the record, the explanation lives in the session. Once every part is scored the question's mean is kept; a new answer clears its part's grade and the mean until the tutor grades again |
| Flow | a new topic starts at `start_difficulty`; `Complete quiz` sets `completed_at`, keeps the mean, and moves the topic's difficulty by the flow band once: below `flow_low` one step down, above `flow_high` one step up, floor 1 and ceiling 10; a grade revised after completion recomputes the mean and never moves it again |
| Page | The list is every question in one run: a bar in the module's hue carrying how far the question has come, the title with its tags, and the score once it is finished. `Active` and `Completed` pick the slice, `Questions` and `Topics` pick the view, and the second one is a line per topic: the topic as a tag, its completed count over its asked count, and its average, fetched while that view is open and not behind it. `Generate` sits with the page's controls and asks for one more question, which opens as it lands. Hovering a row offers `Tag` and, while the question is open, `Delete`, which asks before it goes. Opening a row fills the pane with the question itself in PT Serif, sized to the pane and with the maths rendered: the title, the day, the tags, the definitions and premise, then each part as one paragraph — its title in bold, a colon, the ask — with an answer box under it. `Submit` (or Ctrl+Enter in the box, which the `?` overlay lists) hands the answer to the tutor, whose grade and explanation land in the drawer, and the part then reads `N/100` and offers `Resubmit`. The command palette runs that same action with the caret nowhere, so there it sends the first part holding text the tutor has not seen, and says so rather than going quiet when there is none. An answer half-typed in one part survives the reload another part's `Submit` causes, and the 30 s poll, until it is sent or the question goes; an emptied box is not an answer, so what the daemon holds reads there again on the next reload. A completed question shows its answers and takes no more. The buttons under the parts are the ones the daemon offers: `Complete quiz` in the hue, `Delete` in red and behind a confirmation |
| Departures | `Reschedule`, `Start` and `Skip` dropped (nothing is scheduled to a date, opening a question is what loads it for the tutor, an unwanted question is deleted); `Generate`, answer boxes, tags and the rendered setup are not drawn in the artboard; the preview's green and amber tint on a part's score is dropped, since colour is the module's hue on a card's border and on a primary button and nowhere else, and the preview's worded counts on the Topics view (`3 of 12 done`, `avg 88`) are the numbers alone |

## Patches

### The New tech item has no plan

- Kind: gap
- Where: Education constraint 5 (pick a new technology, see whether the owner can understand how it works)
- Found: 2026-09-10, sync-architecture
- Status: open, needs a decision

What happens: no module, task or page picks a technology or asks about it; the Education topics are the fourteen fixed domains.

Expected: a decision on where the technology comes from (a Newsfeed search is the obvious feed), how one is picked, and how the owner's understanding is checked.

Fix: the owner decides whether it is a mode of Education or of Newsfeed; then one change through `/feature-flow`.

### A question's tags live in two places

- Kind: bug
- Where: `app/modules/education/routes.py` `_owner_tags` and `_tags`, `education_questions.tags`, the platform's `app_tags`
- Found: 2026-09-20, porting the page to the new shell
- Status: open

What happens: the shell's tag popup writes every tag to `app_tags`, while `action/tags` (which the tutor and the old page used) replaces the JSON list on the question itself. The ported page calls `action/tags` nowhere, so that route now answers only the tutor. The row shows both stores, so nothing is hidden, but `/api/tags/remove` only reaches `app_tags`: the `×` on a tag that came from the JSON list does nothing, and the tutor's context lists only the JSON ones.

Expected: one tag store per question, added and removed from the same place, and the same set in the tutor's context.

Fix: move the question's tags into `app_tags` — `action/tags` writes there, `tags_of` reads there, and the JSON column is migrated once and dropped — or give the platform a per-module remove hook so both stores answer one `×`.

### The ported page drops things the old one had

- Kind: gap
- Where: `app/static/pages/education.js`, `app/modules/education/routes.py` `left`
- Found: 2026-09-20, porting the page to the new shell and its review; narrowed 09-20-2026, sync-architecture
- Status: open, the last part needs a decision

What happens: the preview the port follows draws none of them, so the page no longer adds or retires a topic (only the tutor can), the search bar reads the title, topic, tags and part titles but no longer the definitions or the premise, and the owner's recorded feedback on a question is no longer shown beside it. The same client-side narrowing puts a floor under the history: `left` caps the completed slice at 200 and reports `more`, which the page has no use for, so a question older than the 200th completed one is reached neither by scrolling nor by typing in the omnibox — it is off the page entirely.

Expected: a topic is added and retired on the Topics view, the feedback the owner gave about a question reads under it, and a search finds any completed question by a phrase in its title, its setup or its parts, however old.

Fix: a `+` and a retire button on the Topics view; the feedback lines back in the pane under the parts. For the search and the ceiling, the shell now hands `load` the typed text and asks a page that declares `serverQuery` again as it changes, so `left` can take a `query` and search every listed question server-side rather than the loaded slice — whether to do that or to lift the cap and load the whole history into the browser is still the owner's call.

### The question pane stamps a date on a question no date governs

- Kind: defect
- Where: `app/static/pages/education.js` `questionView`, the line under the title
- Found: 2026-09-20, the port review
- Status: open, needs a decision

What happens: the pane prints the question's day — its completion date, or its creation date while it is open — under the title. Nothing in Education is scheduled (constraint 3) and a date belongs only on a date-bound item, so the line stamps a question that no date governs. The preview put a worded progress line there instead (`38% graded`), which the no-chrome-text rule forbids, so neither shape is right as it stands.

Expected: the pane carries the title, the tags and the question, and under the title only what the owner wants there.

Fix: drop `dateLine` from `questionView`, or put in its place whatever the owner picks. The list row carries no date either, so dropping it takes the day off the page altogether — which is why this waits for them.
