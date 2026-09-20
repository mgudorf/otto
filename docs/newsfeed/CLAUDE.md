# Newsfeed

1. One module for everything Otto searches the web for on my behalf; the scouting Business and Social used to do, and the nightly Search, consolidated here
2. The scheduled searches are the module's specifics; the line items are the entries those searches return
3. The starting screen lists the scheduled searches, each killable from there; creation goes ONLY through the agent
4. Everything is tag-able

## Built

| Piece | Current state |
|---|---|
| Tables | `newsfeed_searches(name unique, prompt, every_days, cap, created_at, next_run, last_run, last_result)`, `newsfeed_items(search_id → searches ON DELETE SET NULL, text, url unique, summary, starts_at, follow_up_at, follows, found_at, status open\|accepted\|dismissed, decided_at)`, `newsfeed_tags(kind search\|item, ref, tag)`. `next_run`, `follow_up_at` and `starts_at` are local dates (`starts_at` carries a `THH:MM` when the listing gave a time); an entry keeps its row and tags after its search is killed |
| Ids | an entry is its integer, a search is `s<id>`; every route, action and tool takes either form where both make sense, and a bad id is a 400 (`_ref`) |
| Routes | `left` (query as `LIKE` per word over text, url, summary and tags, each word escaped so `%`, `_` and a backslash stand for themselves; chips `All` (not dismissed), `Open`, `Accepted`; `limit` 200 by default, raised by the page until `more` goes false; rows by the day found, newest first), `blank` (the searches with their tags and open counts, the open and listed totals, last run), `item/{id}` (an entry: its row, `kind`, and `Accept` primary and `Dismiss` while open, `Open` as an href where the entry has a url; a search: prompt, every, cap, next and last run, counts, tags, `Kill` with confirm), `action/{accept\|dismiss\|tag\|untag\|kill}` on resource `newsfeed`: `accept` and `dismiss` take an open entry (409 once decided), `tag {id, tags}` and `untag {id, tag}` take either, `kill {id}` deletes a search and its tags and leaves its entries. No capture route: a search is created by the agent only |
| Rows | every list answers with the same row: `id`, `module`, `title` (the headline), `when` (the day and time it was found, in the owner's clock), `tags` (the owner's own, from `app_tags`, editable anywhere in the shell), `fixed` (the tags the run wrote, its search's among them, not editable), `status`, `summary`, `url`, `search` (its name, null once the search is killed), and `happens` / `followUp` where the entry has them |
| Hooks | `numbers` (open entries, `to review`), `today` (found today or happening today, a dismissed one excluded), `queue` (every open entry, newest first: Home's `Review` group), `rows` (every listed entry, newest first, capped at 200: the tag intersection and Home's Recent), `item`, `context` (each search with its schedule and tags, the open entries with urls, last run) |
| Tools | read on both servers: `newsfeed_search(query, status, limit)` (the same `LIKE` per word, tags included, limit capped at 100), `newsfeed_get(id)`, `newsfeed_searches()`; write on `otto` only: `newsfeed_search_add(name, prompt, tags, every_days=1, cap=None)` (`cap` falls back to `items_per_run`; the first run is the next nightly window; event `search added`), `newsfeed_tag(id, tags)` (event `tagged`) |
| Schedule | `newsfeed.run` every 24h inside the nightly window, resource `newsfeed`. It takes every search whose `next_run` is today or earlier and runs each as one budgeted, read-only CLI run with the CLI's WebSearch and WebFetch and no Otto tools: the prompt is today's date, the search's own prompt, the last hundred of its entries with their status (a dismissed one shows what to stop bringing), the accepted entries whose follow-up day has come, and the JSON shape `{text, url, summary, date, time, follow_up, tags, follows}` (a fence is tolerated). Up to `cap` new rows go in with `INSERT OR IGNORE` on url, each tagged with the search's tags plus the run's; the follow-ups asked about are consumed; `next_run` moves `every_days` on; the entry count is the search's `last_result` and the cursor `newsfeed.run` moves, all in one transaction per search, one `found` event per row. A reply with no JSON array is that search's `last_result` (`bad reply: …`), it stays due, and the run goes on to the next search. A budget refusal midway stops the job as skipped with what already committed kept. `Skipped` with no searches or none due |
| Follow-ups | the run may attach `follow_up` to an entry; once it is accepted and the day has come, the next run of its search lists it as due, the reply's new entries may name it in `follows`, and the date is cleared so it is asked once. Nightly Process items 1 and 2 on Home |
| Config | `[newsfeed]`: `items_per_run` (the cap a search gets when the agent sets none) |
| Page | The entries, on a plate per day they were found: a dot in the hue while one waits, the headline with its tags, and the day it happens or the day to come back to it. `Open`, `Accepted` and `All` narrow the list, the tags in the search bar narrow it further, and a second control swaps the entries for the searches. The page declares `serverQuery`, so the shell hands it what is typed instead of filtering the rows in hand: `load` sends it as `query` and the whole feed is searched, and new words start the list over at its first 200. While the daemon says `more` and the entries are the view, a `More` button beside the controls asks for another 200 on top of what is shown; the searches all arrive with the page's own load, so they never carry one. The chip stays the page's own, applied in the browser, so deciding an entry does not shut the pane the decision was made in. A row offers the same two verbs the `item` route declares for an open entry, `Accept` and `Dismiss` behind a confirm, and `Tag` under the pointer; one verb asks one question, so the row and the pane word it the same. Opening one shows the headline, its one date, its tags, its search and its link, the summary, and the buttons the daemon offers with it (`Accept` in the hue, `Dismiss` red behind a confirm, `Open` as a symbol where the entry has a url). The searches view is one row per standing search: its name and tags, how often it runs, how many entries a run may bring, the day it next runs, how many of its entries still wait, and `Kill` behind a confirm; opening a search shows its prompt, that same schedule as one line, its tags and `Kill`, all from the page's own load. The pane belongs to the view under it, so swapping the control closes a pane the other view cannot carry and no button fires at a row that is off screen. Creating a search is the agent's, so the view has no form |
| Dismissal | a dismissed entry leaves every chip, `today`, `queue` and the agent's context, and its item offers only the url. The row stays in `newsfeed_items`, which is what stops the run proposing the same url again |
| Departures | not in the artboard: title, hue `#D79EBB`, the feed-arcs icon and rail order 6 are Otto's. The searches are a second view under the entries rather than a capture box, since creating one is the agent's. One url is one entry: a listing that repeats a url on another date is not proposed twice, where Social kept each date |

## Patches

### A search that stopped working looks healthy

- Kind: gap
- Where: `app/static/pages/newsfeed.js` (`searchesView`, `searchView`), `app/modules/newsfeed/routes.py` (`searches`)
- Found: 2026-09-20, porting the page to the new shell
- Status: open

What happens: a run whose reply carried no JSON array leaves `bad reply: …` in the search's `last_result`, and the searches view shows the name, the cadence, the cap and the next day but nothing about the failure, so a search that brings nothing back night after night reads the same as one that works. Opening the search shows its prompt and the same schedule and is equally silent about it.

Expected: the search that failed says so on its own row.

Fix: show `last_result` on the row, and in the pane, when it starts with `bad`. The approved preview had no failing search, so the port had nowhere to carry the red line the old page showed.

### A time in the open entry ignores the 12-hour setting

- Kind: defect
- Where: `app/static/core.js` (`clock`, not exported), `app/static/pages/newsfeed.js` (`oneDate`)
- Found: 2026-09-20, porting the page to the new shell
- Status: open

What happens: a row's stamp runs the time through the shell's clock, which honours `ui.time_format`, while the open entry's date line takes the time straight off the string. With the setting on 12h the same entry reads `6:30 pm` in the list and `18:30` in the pane.

Expected: one clock across the app.

Fix: export `clock` from `core.js` and use it wherever a page prints a time; every ported page with a time in its pane has the same split.

### A search cannot be tagged from the page

- Kind: gap
- Where: `app/static/core.js` (`openTagPop`), `app/api.py` (`/api/tags/add`, `/api/tags/remove`), `app/modules/newsfeed/routes.py` (`searches`, `_tag`), `app/static/pages/newsfeed.js`
- Found: 2026-09-20, porting the page to the new shell
- Status: open

What happens: a search's tags sit in `newsfeed_tags` and ride onto every entry its next run brings back, so they are written through `action/tag` and `action/untag`. The shell has one tag picker and it posts to `/api/tags/add`, which writes `app_tags` — a table a search's row never reads. So the page shows a search's tags and cannot change them; only the agent's `newsfeed_tag` can, and a tag added through the shared picker would be stored and never seen. The old page carried its own tag box on each search row.

Expected: a search is tagged where every other row in Otto is tagged.

Fix: either give the platform's tag routes a per-module hook, so `newsfeed` writes `newsfeed_tags` for an `s<id>`, or rule that a search's inherited tags are `fixed` and the owner's tags on a search are ordinary `app_tags` that do not ride onto its entries. The second changes what tagging a search means for the run, the tools and the agent's context, so it is a decision rather than a repair. Until then the page shows a search's tags and does not offer to edit them: a picker of its own would be a second way of doing the one thing the shell already does everywhere else.

### Newsfeed's own tags are missing from the tag catalog

- Kind: gap
- Where: `app/store.py` (`all_tags`), `app/modules/newsfeed/routes.py` (`_fixed`)
- Found: 2026-09-20, porting the page to the new shell
- Status: open

What happens: the tags a nightly run writes live in `newsfeed_tags`, and `/api/tags` counts only `app_tags` and `second_brain_tags`. A tag carried only by newsfeed entries never appears in the search bar's suggestions, the palette or the Graph, though `/api/items` still narrows by it because the rows carry it in `fixed`.

Expected: one tag system; a tag a run wrote is counted with the rest.

Fix: read `newsfeed_tags` in `all_tags` beside the other two tables.

### The one-time migration still ships

- Kind: defect
- Where: `app/modules/newsfeed/migrate.py`, `app/modules/newsfeed/__main__.py`, `tests/test_newsfeed.py::test_migrate_converts_the_retired_modules`
- Found: 2026-09-18, CLAUDE.md audit
- Status: open

What happens: the live database was already converted, yet `python -m app.modules.newsfeed migrate` and its test remain, reading tables of modules that no longer exist.

Expected: code that has done its one job is deleted; git keeps it.

Fix: delete `migrate.py`, `__main__.py` and the test; the old Business, Social and Search tables are dropped only when the owner asks in words.

### The confirm a search's Kill declares is never the one asked

- Kind: defect
- Where: `app/static/pages/newsfeed.js` (`kill`), `app/modules/newsfeed/routes.py` (`_search_item`, `blank`), `app/static/core.js` (`loadItem`)
- Found: 09-20-2026, the recheck of the ported page
- Status: open

What happens: `item/s<id>` declares `Kill` with the confirm `Kill this search? Its entries stay.`, and nothing ever reads it. The searches come with the page's own load from `blank`, which carries no `actions`, and `loadItem` looks a selected row up in the entries it holds, so it never asks for `s<id>` at all. The page therefore writes its own question, `Kill <name>? Its entries stay.`, and one action has its wording stated in two places that can drift apart. An entry's verbs are already single-sourced; a search's are not.

Expected: one action, one declaration, wherever it is asked.

Fix: either serve each search's `actions` from `blank` beside its tags and open count, so the page asks with what the module declared, or drop the `confirm` from `_search_item` and say in the contract that a search's buttons are the page's. The first keeps the rule every other row follows; the second admits the search rows are not ROWs.
