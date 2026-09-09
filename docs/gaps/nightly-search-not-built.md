# Home shows no nightly search results

- Where: Home page requirement 2 and the Nightly Process section; `app/modules/`
- Found: 2026-09-07, sync-architecture
- Status: open, needs its roadmap item

What happens: Home renders a `Review` group for every module with a `queue` hook, but no module on `main` has one, so nothing queues for a yes or no. No scheduled web search runs. The `[nightly]` budget that will cap it already applies to every scheduled LLM run.

Expected: a nightly, capped web search whose results queue on Home for agree / disagree, each decision creating a record.

Fix: `docs/roadmap/web_search/PLAN.md` covers it and its work sits on the unmerged `web_search` branch; merge it. Before that, verify that WebSearch works in a headless `claude -p` run; that is still unverified.
