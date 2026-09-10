# No search topics are entered, so the nightly search never runs

- Where: Home page requirement 2 and the Nightly Process section; `search_topics` table
- Found: 2026-09-10, sync-architecture
- Status: open, owner action

What happens: `search_topics` is empty. `web_search.nightly` returns `Skipped("no topics")` before spending a run, `search_findings` stays empty, Home has no `Review` group and the Search page reads `nothing found yet`. The module has never produced a finding.

Expected: at least one topic per kind the owner cares about (`money`, `work`, `learn`), so the next nightly window queues up to `max_findings` findings for a yes or no.

Fix: type the topics on the Search page's blank state, one line each with its kind; nothing else is needed.
