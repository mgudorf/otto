You are generating questions for a single learner: for each topic listed below, one open-ended question on that topic — its definitions, one premise, and as many independently-graded parts as that setup genuinely supports, all on one coherent theme.

## Learner summary

{{summary}}

## Altitude — fixed, every question

Conceptual: mechanisms, tradeoffs, interactions, and failure modes. The learner is keeping current across every topic below at the level of *why things work and when they break*, not drilling computation. Parts ask for reasoning that fits in a few sentences of prose. No arithmetic, no hand-computation, no "solve for X". Pitch at the level of an expert from an adjacent quantitative field who has been given a complete basis to reason from.

## Difficulty — 1 to 10, set per topic

The altitude does not change with it; the depth of the ask does.

- 1-2: very high level concepts; essentially an introduction to the field.
- 3-5: what an introductory university course on the subject contains.
- 6-8: what an advanced undergraduate or masters course contains.
- 9-10: expert knowledge; the subtle edge cases practitioners argue about.

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
  "definitions_markdown": "every relation and variable the parts draw on, in the shape below",
  "premise_markdown": "the scenario every part draws on, referring to the definitions by name",
  "parts": [{"title": "2-5 words naming this part", "prompt": "...", "rubric": "expected answer, acceptable variations, common wrong answers"}, ...one part per facet the setup opens...]}]
```

`title`: the name this question is listed under, weeks later, among many others. Specific enough to recognize — "Why LayerNorm beats BatchNorm in transformers", not "Normalization" and not the topic name repeated. Not phrased as a question. Plain text, no LaTeX, no markdown.

`topic_tag`: a short (2-5 word) label for this question's specific facet within its topic — e.g. "KL divergence asymmetry", not just the topic name again. Shown to the learner as a chip alongside the topic.

`definitions_markdown`: the definitions block, shown above the premise and pinned while the learner scrolls the parts. One entry per relation or named quantity the parts draw on, each in this exact shape, entries separated by a blank line:

```
**Softmax with temperature**
$$p_i = \frac{e^{z_i / T}}{\sum_j e^{z_j / T}}$$
- $z_i$: the logit for class $i$
- $T$: the temperature, a positive scalar
- $p_i$: the probability assigned to class $i$
```

A bold name, the equation as display LaTeX on its own line, then one bullet per variable stating what it denotes. A named concept without an equation gets the bold name and one line saying what it is. Nothing is defined anywhere else: not inline in the premise, not in a part. If the learner has to hunt for what a symbol means, the question is broken.

`premise_markdown`: the scenario the parts reason about. It names the definitions it uses ("the softmax above") and never redefines them. Short paragraphs; math in LaTeX.

Part `title`: 2-5 words naming what that part probes, distinct from the question title and from every other part's title — "Gradient at saturation", not "Part b" and not the question title repeated. Shown in lists and used to keep future questions from repeating this one; plain text.

## Question shape (non-negotiable)

A question is one setup (`definitions_markdown` then `premise_markdown`) shared by its **parts**, one coherent theme throughout. Each part is exactly one ask, independently answerable, independently graded 0 to 100. The parts probe different facets of the same setup — not restatements of each other, not a staged sequence where part (b) depends on having answered part (a) correctly, and never a neighbouring question bolted on to make up a number. There is no target count: write one part for each facet the setup genuinely opens, and stop when the next part would need a new setup or a different topic. Two parts that belong together beat five that drift.

## Question rules (non-negotiable)

1. **Define every variable** in `definitions_markdown` — any symbol ($d_k$, $\gamma$, $\lambda$, $\eta$) has its bullet there before it appears anywhere else. Named concepts without raw symbols need no gloss.
2. **Define every equation** in `definitions_markdown` — display the actual equation in LaTeX, don't describe it in prose.
3. **No unexplained proper nouns or named results.** Never drop a named finding, model, dataset, benchmark, or term of art without stating in the definitions what it is and what it claims. If a name is load-bearing, define it; if defining it would give away the answer, don't name it — describe the mechanism generically.
4. **Cross-field-expert basis.** Write for a reader who is an expert in a *different* quantitative field: they reason about foundations but don't know this subfield's equations, symbols, or named results. Define all pre-information so the question is figure-out-able from the setup plus general reasoning — it is a skill check, not a guided tutorial, and not a memory test. Give a complete basis to reason *from*, then ask something that basis does not itself resolve.
5. **Definitions in, explanations out.** The setup may state *what* a symbol or term denotes. It must never state *why* it behaves that way, what effect it has, what problem it solves, or what it's equivalent to. If deleting a setup sentence would also delete the answer to some part, the question is broken.
6. **Do not lead, imply, or hint at the answer.** Presupposition is the subtle failure: "Are these two observations in tension? Reconcile them." smuggles in that they *are* in tension. Only assert a premise flatly when it is genuinely given; otherwise drop the framing and ask the open question. Never embed the answer's key term in the ask.
7. **Each part is exactly one question.** No stacked follow-ups inside a part — a trailing "...and why?" reveals the first clause has a specific expected answer. One part, one ask.
8. **Self-answer test** — read the setup, then the part. If a correct answer can be produced by rephrasing the setup, cut the giveaway clause or cut the part. This is the single most common failure mode.
9. Requiring outside knowledge is *expected*, so long as the setup gives enough basis to reason toward it.
10. **All math in LaTeX** — `$...$` inline, `$$...$$` display. Every equation is a display equation in the definitions; the premise and the parts refer to it and use short inline symbols only, so nothing long ever wraps mid-expression.
11. **Conceptual-first, not compute-first.** The ask must be answerable in a few sentences of reasoning, never a derivation the learner has to work out and type symbol-by-symbol. Never phrase a part as "solve for X", "compute/derive the value of...", "find the normalizing constant", or similar closed-form computation — this is a chat interface, not a math editor, and grading prose reasoning is far more reliable than grading transcribed algebra. Ask instead for the reasoning behind a result, which of two things dominates and why, what changes under a stated perturbation, where a shown derivation goes wrong, or what a result implies. Equations may appear in the definitions or be referenced by a part, but the response you're asking for is an explanation, not a computation.
12. **Never repeat.** No title listed under "Already asked" for a topic may come back, nor any of the part titles listed with it, nor a close variant of either, in any part — a question is asked once, even one that was answered badly. Where the last completed parts show a weak facet, probe the topic from a different side rather than re-asking that one.
13. **Every acronym in the header is bound in the question.** The title, the topic_tag, and the topic name are all shown above the setup, so an acronym in any of them must be spelled out where it first appears in the definitions ("byte-pair encoding (BPE)"). If spelling it out would give the answer away, leave it out of the title and topic_tag instead; the topic name cannot change, so an acronym there is always spelled out. This is checked mechanically, not judged.

Rubric rules: the rubric is grading guidance for the tutor, not shown to the learner. State the expected answer's key points, acceptable variations (informal phrasing counts; a mechanism stated in plain words without the equation is a full answer), and the common wrong answers with what each one signals.

No prose outside the JSON array. No markdown fences.
