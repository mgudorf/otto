# Education

1. Aimed towards teaching concepts and high level understanding; minimal algebra/derivations as it is hard to type by hand.
2. Has a corpus of topics/questions manageable via database. 
3. Progress tracker
4. Aims for "flow state"; balance of difficulty and understanding determined by score range. 
5. Agent grades answers, makes notes of past performance, uses as context when creating future questions, takes into account feedback.
6. Must provide clearly worded questions, must introduce any equations as part of premise/prompt
7. A question is one shared setup with as many parts as that setup genuinely opens on one coherent theme, never a count; every part is intimately related to the original question
8. "Grading" should allow for back and forth communication; i.e. answer given -> LLM response
   
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
| Tables | `topics(name, description, difficulty 1-5, retired_at)`, `questions(topic_id, title, topic_tag, premise (the setup: markdown, math in LaTeX), difficulty, source nightly\|session, started_at, graded_at, skipped_at, score)`, `question_parts(question_id, n, text, rubric, answer, answered_at, verdict correct\|partial\|incorrect, score 0-100, note (the explanation), graded_at)`, `education_feedback` (the owner's words, unchanged). The package's `setup` adds `topic_tag`, `rubric`, `answer`, `answered_at` and `verdict` to a database whose tables predate them |
| Files | `questions.py` (the shared reads, the generator prompt from `prompts/generate.md`, the reply parser, `validate_question`, `unbound_acronyms`, inserts), `grading.py` (the grade prompt from `prompts/grade.md`, the parser, `apply_grade`, the tutor's `grade`) |
| Format | one setup shared by lettered parts `(a)`, `(b)`, past `(z)` as `(aa)`; each part one ask with a hidden rubric; a rubric leaves the server only to the tutor and only once its part is graded |
| Routes | `left` (the due queue, then history by day; search over title and setup; an open question's bar is the share of parts graded, a closed one's its score; page), `blank` (progress per topic, add-topic box), `item/{id}` (`text` carries title, setup and part prompts for Home and Feedback), `action/answer` (stores the answer, starts its question, un-starting any other, then grades it through `oneshot` with `prompts/grade.md`, awaited; 400 empty, 409 already graded or skipped, 502 on a bad reply keeps the answer), `action/generate` (one question for the topic never asked or asked longest ago, through `oneshot` with `prompts/generate.md`, source `session`, not started; 409 with no active topic, 502 on a rejected reply, a `warning` for a header acronym the body never binds), `action/{start\|skip\|add_topic\|retire_topic}` (`add_topic` revives a retired topic of the same name). The two LLM actions run on resource `education.llm`, the rest on `education` |
| Hooks | `numbers` (due), `today` (the due queue), `item`, `context` (per topic: difficulty, graded/asked, average, recent scores; the started question with each part's prompt, answer, verdict, score, explanation and, once graded, rubric; the last five graded; recent feedback verbatim) |
| Tools | read: `education_topics`, `education_questions`, `education_question` (rubrics on graded parts only), `education_feedback`; write: `education_add_topic`, `education_add_question(topic_id, title, topic_tag, setup, parts)` (validated like the generator's output, started at once), `education_grade(question_id, part, score 0-100, note)` (the verdict follows the score), `education_record_feedback` |
| Schedule | `education.generate` every 24h inside the nightly window: `per_night` new questions whatever the queue already holds, one for each topic that has waited longest, one budgeted run with `prompts/generate.md` and no tools; an element is rejected for a missing title, tag or setup, a part without a prompt and rubric, a topic not asked for, or a title already used on the topic; a header acronym the body never binds is logged and kept |
| Grading | the grader sees topic, description, difficulty, setup, prompt, rubric, answer and the topic's feedback and answers `{verdict, score 0-2 in halves, explanation}`; the score is stored as 0-100 with the verdict; the last part scored sets the question's mean and moves the topic's difficulty by the flow band once; a re-grade recomputes the mean and never moves it again. The nightly prompt carries every topic's learner summary, each listed topic's titles already asked, last verdicts and feedback, then the general feedback |
| Flow | a new topic starts at `start_difficulty`; a completed question averaging below `flow_low` drops its topic one step, above `flow_high` raises it, floor 1 and ceiling 5 |
| Page | LEFT: search, the `due` group, then history by day with the score as a progress bar; MIDDLE blank: `Generate` above a row per topic (difficulty, graded/asked, average, recent scores, last asked, retire) and the add-topic box; MIDDLE selected: title, topic and tag chips, the setup as markdown with LaTeX, each part with its prompt and either an answer box with `Submit` (Ctrl+Enter, `grading…` in flight) or the graded block (the answer, the score in the verdict colour, the explanation), the owner's feedback lines, `Start` or `Skip`, `Send to session` |
| Departures | `Reschedule` dropped (nothing is scheduled to a date); LEFT leads with `due` instead of grouping everything by date; verdict colours correct `#7fb894`, partial `#d1a36a`, incorrect `#cf7b7b`; `Generate`, answer boxes and markdown in MIDDLE are not drawn in the artboard; the blank state is unspecified there |

## Patches

### `Generate` files a question under the wrong topic when the reply names another

- Kind: bug
- Where: `app/modules/education/routes.py` `generate_now` (falls back to `items[0]` when no element names the chosen topic)
- Found: 2026-09-12, sync-architecture
- Status: open

What happens: the page action asks for one question on the topic that has waited longest and then looks for an element whose `topic_id` is that topic. When none matches it takes the first element anyway and inserts it under the chosen topic, and the validator only checks that the topic is active. A reply carrying another topic's id therefore becomes a question on the wrong topic, counted against the topic that waited longest. The nightly task rejects such an element as `not asked for`; the page action does not.

Expected: a reply that does not name the asked topic is a 502, the same as any other rejected reply.

Fix: remove the `items[0]` fallback and let the missing match raise into the existing 502 path.

### The New tech item has no plan

- Kind: gap
- Where: Education constraint 5 (pick a new technology, see whether the owner can understand how it works)
- Found: 2026-09-10, sync-architecture
- Status: open, needs a decision

What happens: no module, task or page picks a technology or asks about it; the Education topics are the fourteen fixed domains.

Expected: a decision on where the technology comes from (the nightly search's `work` findings are the obvious feed), how one is picked, and how the owner's understanding is checked.

Fix: the owner decides whether it is a mode of Education or of Search; then one change through `/feature-flow`.
