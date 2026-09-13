# Search

Meets Home requirement 2 and the Nightly Process: the owner names topics through the Chat agent, one nightly run searches the web for them, and each finding waits on Home for a yes or no that becomes the record. No page and no agent: the manifest sets `page=False`, so `/api/shell` lists it with `page: false` for its hue and icon, Home carries its `Review` group and number without a link, and Settings shows only its `runs` toggle.

## Built

| Piece | Current state |
|---|---|
| Tables | `search_topics(kind money\|work\|learn, text unique, created_at)`, `search_findings(topic_id, kind, title, url unique, summary, found_at, status open\|agreed\|disagreed, decided_at)`; a finding keeps its kind after its topic is removed |
| Routes | `item/{id}` (`Agree` primary, `Disagree`, `Open` as an href; a decided finding offers `Open` only), `action/{agree\|disagree}` `{id}` on resource `web_search` (409 on a decided finding; events `agreed`, `disagreed`). Home's inspector posts them |
| Hooks | `numbers` (open findings, `to review`), `today` (found in the local day), `queue` (every open finding, newest first: Home's `Review` group), `item`, `context` (topics by kind, the open queue with urls, last run) |
| Tools | read on both servers: `search_findings(query, status, limit)` (the same `LIKE` per word over title and summary, limit capped at 100), `search_topics`; write on `otto` only: `search_topic_add(kind, text)`, `search_topic_remove(id)`, declared by Chat's manifest, each writing a `topic added` or `topic removed` event marked `(agent)` |
| Schedule | `web_search.nightly` every 24h inside the nightly window, resource `web_search`: one budgeted run over every topic (listed as `(topic_id, kind) text`) with the CLI's WebSearch and no extra tools, the last hundred findings listed with their status as already found, a JSON array of `{topic_id, title, url, summary}` back (a fence is tolerated; a row naming no current topic or missing a title or url is dropped); up to `max_findings` new rows inserted with `INSERT OR IGNORE` on url and the cursor `web_search.nightly` in the same transaction, one `found` event per row. No topics, no run |
| Page | none. Home's `Review` group lists the open findings and its inspector shows the url and status with `Agree`, `Disagree` and `Open`; Activity's chip and the `events` log carry the module |
| Departures | the module is not in the artboard: title `Search`, hue `#d9915b` and magnifier icon are Otto's and colour Home's rows; there is no rail entry |

## Patches

### Scheduled follow-ups are not built

- Kind: gap
- Where: Nightly Process items 1 and 2 (previously scheduled follow-ups; tracking follow-ups and scheduling them for the future); `app/modules/web_search/`
- Found: 2026-09-10, sync-architecture
- Status: open

What happens: a finding is found once, decided once, and never revisited. `search_findings` has no follow-up date and the nightly prompt never asks for one, so a time-bound finding the owner agreed with (a filing deadline, a release, a hearing) is not searched again when its date comes.

Expected: the nightly run may attach a follow-up date to a finding; agreed findings past that date are listed in the next prompt as things to follow up on and surface again on Home.

Fix: `follow_up_at` and `parent_id` on `search_findings`, a line in the nightly prompt asking for a follow-up date, and a finding kind `follow` for the re-search; agreed findings past their date join the next prompt and Home's `Review` group.

### No search topics are entered, so the nightly search never runs

- Kind: gap
- Where: Home page requirement 2 and the Nightly Process section; `search_topics` table
- Found: 2026-09-10, sync-architecture
- Status: open, owner action

What happens: `search_topics` is empty (still zero rows on 2026-09-12). `web_search.nightly` returns `Skipped("no topics")` before spending a run, `search_findings` stays empty and Home has no `Review` group. The module has never produced a finding. Since the chat merge the Search page is gone; topics are edited only through the Chat agent's `search_topic_add` and `search_topic_remove` tools.

Expected: at least one topic per kind the owner cares about (`money`, `work`, `learn`), so the next nightly window queues up to `max_findings` findings for a yes or no.

Fix: ask the Chat agent to add the topics, one per line with its kind (`money`, `work` or `learn`); it writes them with `search_topic_add`. Nothing else is needed.
