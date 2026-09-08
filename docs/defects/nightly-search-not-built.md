# Home shows no nightly search results

- Kind: gap
- Where: Home page requirement 2 and the Nightly Process section; `app/modules/home/`
- Found: 2026-09-07, sync-architecture
- Status: open, needs its roadmap item

What happens: Home aggregates module numbers and today rows only. No scheduled search runs and no review queue exists. The `[nightly]` budget that will cap it already applies to every scheduled LLM run.

Expected: a nightly, capped web search whose results queue on Home for agree / disagree, each decision creating a record.

Fix: plan it with `/create-roadmap-item` (the owner's folders are `docs/roadmap/homepage/` and `docs/roadmap/web_search/`). First verify that WebSearch works in a headless `claude -p` run; that is unverified.
