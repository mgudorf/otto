# No search topics are entered, so the nightly search never runs

- Where: Home page requirement 2 and the Nightly Process section; `search_topics` table
- Found: 2026-09-10, sync-architecture
- Status: open, owner action

What happens: `search_topics` is empty (still zero rows on 2026-09-12). `web_search.nightly` returns `Skipped("no topics")` before spending a run, `search_findings` stays empty and Home has no `Review` group. The module has never produced a finding. Since the chat merge the Search page is gone; topics are edited only through the Chat agent's `search_topic_add` and `search_topic_remove` tools.

Expected: at least one topic per kind the owner cares about (`money`, `work`, `learn`), so the next nightly window queues up to `max_findings` findings for a yes or no.

Fix: ask the Chat agent to add the topics, one per line with its kind (`money`, `work` or `learn`); it writes them with `search_topic_add`. Nothing else is needed.
