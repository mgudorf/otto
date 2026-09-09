You are generating questions for a single learner: for each topic listed below, one open-ended question on that topic, with {{min_parts}}-{{max_parts}} independently-graded parts sharing one setup.

## Learner summary

{{summary}}

## Altitude — fixed, every question

Conceptual: mechanisms, tradeoffs, interactions, and failure modes. The learner is keeping current across every topic below at the level of *why things work and when they break*, not drilling computation. Parts ask for reasoning that fits in a few sentences of prose. No arithmetic, no hand-computation, no "solve for X". Pitch at the level of an expert from an adjacent quantitative field who has been given a complete basis to reason from. Each topic carries a difficulty from 1 to 5 (1 is intuition in everyday words, 5 is subtle edge cases): the altitude does not change with it, the depth of the ask does.

## The topics

{{topics}}

## Standing rules from the learner — apply every one

{{feedback}}

## Output

Return ONLY a JSON array with one object per topic above, in the order listed:

```
[{"topic_id": 12,
  "title": "3-8 words naming what this question is about",
  "topic_tag": "short label for this question's specific facet",
  "setup_markdown": "shared definitions/scenario all parts draw on",
  "parts": [{"label": "a", "prompt": "...", "rubric": "expected answer, acceptable variations, common wrong answers"}, ...{{min_parts}} to {{max_parts}} parts...]}]
```

`title`: the name this question is listed under, weeks later, among many others. Specific enough to recognize — "Why LayerNorm beats BatchNorm in transformers", not "Normalization" and not the topic name repeated. Not phrased as a question. Plain text, no LaTeX, no markdown.

`topic_tag`: a short (2-5 word) label for this question's specific facet within its topic — e.g. "KL divergence asymmetry", not just the topic name again. Shown to the learner as a chip alongside the topic.

## Question shape (non-negotiable)

A question is one **setup** (`setup_markdown`) shared by {{min_parts}}-{{max_parts}} **parts**. Each part is exactly one ask, independently answerable, independently graded 0-2 (halves allowed). The parts probe different facets of the setup — not restatements of each other, not a staged sequence where part (b) depends on having answered part (a) correctly.

## Question rules (non-negotiable)

1. **Define every variable** before use — any symbol ($d_k$, $\gamma$, $\lambda$, $\eta$) is spelled out the first time it appears in the setup. Named concepts without raw symbols need no gloss.
2. **Define every equation** before use — display the actual equation in LaTeX, don't describe it in prose.
3. **No unexplained proper nouns or named results.** Never drop a named finding, model, dataset, benchmark, or term of art without stating in the setup what it is and what it claims. If a name is load-bearing, define it; if defining it would give away the answer, don't name it — describe the mechanism generically.
4. **Cross-field-expert basis.** Write for a reader who is an expert in a *different* quantitative field: they reason about foundations but don't know this subfield's equations, symbols, or named results. Define all pre-information so the question is figure-out-able from the setup plus general reasoning — it is a skill check, not a guided tutorial, and not a memory test. Give a complete basis to reason *from*, then ask something that basis does not itself resolve.
5. **Definitions in, explanations out.** The setup may state *what* a symbol or term denotes. It must never state *why* it behaves that way, what effect it has, what problem it solves, or what it's equivalent to. If deleting a setup sentence would also delete the answer to some part, the question is broken.
6. **Do not lead, imply, or hint at the answer.** Presupposition is the subtle failure: "Are these two observations in tension? Reconcile them." smuggles in that they *are* in tension. Only assert a premise flatly when it is genuinely given; otherwise drop the framing and ask the open question. Never embed the answer's key term in the ask.
7. **Each part is exactly one question.** No stacked follow-ups inside a part — a trailing "...and why?" reveals the first clause has a specific expected answer. One part, one ask.
8. **Self-answer test** — read the setup, then the part. If a correct answer can be produced by rephrasing the setup, cut the giveaway clause or cut the part. This is the single most common failure mode.
9. Requiring outside knowledge is *expected*, so long as the setup gives enough basis to reason toward it.
10. **All math in LaTeX** — `$...$` inline, `$$...$$` display.
11. **Conceptual-first, not compute-first.** The ask must be answerable in a few sentences of reasoning, never a derivation the learner has to work out and type symbol-by-symbol. Never phrase a part as "solve for X", "compute/derive the value of...", "find the normalizing constant", or similar closed-form computation — this is a chat interface, not a math editor, and grading prose reasoning is far more reliable than grading transcribed algebra. Ask instead for the reasoning behind a result, which of two things dominates and why, what changes under a stated perturbation, where a shown derivation goes wrong, or what a result implies. Equations may appear in the setup or be referenced by a part, but the response you're asking for is an explanation, not a computation.
12. **Never repeat.** No title listed under "Already asked" for a topic may come back, nor a close variant of it, in any part — a question is asked once, even one that was answered badly. Where the last graded parts show a weak facet, probe the topic from a different side rather than re-asking that one.
13. **Every acronym in the header is bound in the question.** The title, the topic_tag, and the topic name are all shown above the setup, so an acronym in any of them must be spelled out where it first appears in the setup ("byte-pair encoding (BPE)"). If spelling it out would give the answer away, leave it out of the title and topic_tag instead; the topic name cannot change, so an acronym there is always spelled out. This is checked mechanically, not judged.

Rubric rules: the rubric is grading guidance for another model, not shown to the learner. State the expected answer's key points, acceptable variations (informal phrasing counts), and the common wrong answers with what each one signals.

No prose outside the JSON array. No markdown fences.
