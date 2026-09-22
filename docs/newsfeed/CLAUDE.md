# Newsfeed

1. One module for everything Otto searches the web for on my behalf; the scouting Business and Social used to do, and the nightly Search, consolidated here
2. The scheduled searches are the module's specifics; the line items are the entries those searches return
3. The starting screen lists the scheduled searches, each killable from there; creation goes ONLY through the agent
4. Everything is tag-able

## Built

| Piece | Current state |
|---|---|
| Facet | `newsfeed`, hue `#D79EBB`. Every row carries it as its one `fixed` tag |
| Tables | `newsfeed_searches(name unique, prompt, every_days, cap, created_at, next_run, last_run, last_result)`, `newsfeed_items(search_id → searches ON DELETE SET NULL, text, url unique, summary, starts_at, follow_up_at, follows, found_at, status open\|accepted\|dismissed, decided_at)`, `newsfeed_tags(kind search\|item, ref, tag)`. `next_run`, `follow_up_at` and `starts_at` are local dates (`starts_at` carries a `THH:MM` when the listing gave a time); an entry keeps its row and tags after its search is killed |
| Ids | an entry is its integer, a search is `s<id>`; every route, action and tool takes either form where both make sense, and a bad id is a 400 (`_ref`) |
| Rows | One ROW per listed entry, type `article`, newest first: `title` the headline, `when` the day and time it was found on the owner's clock, `tags` the run's own from `newsfeed_tags` merged with the owner's from `app_tags`, `snip` its search's name, `kv` of search, link host, the day it happens and the day to come back to it, `body` the summary as one paragraph, `dim` once decided, and `url`. A search answers the same shape from `item/s<id>`, its prompt as the body, but no list returns one |
| Verbs | an entry waiting on a yes or no offers `accept` Accept, `link` Open link and `dismiss` Dismiss; a decided one offers only `link`. A search offers `kill` Kill. `dismiss` is destructive, so the browser asks first and drops the row |
| Routes | `left` (query as `LIKE` per word over text, url, summary and tags, each word escaped so `%`, `_` and a backslash stand for themselves; chips `All` (not dismissed), `Open`, `Accepted`; rows by the day found, newest first), `blank` (the searches with their tags and open counts, the open and listed totals, last run), `item/{id}`, `action/{accept\|dismiss\|tag\|untag\|kill}` on resource `newsfeed`: `accept` and `dismiss` take an open entry (409 once decided), `tag {id, tags}` and `untag {id, tag}` take either, `kill {id}` deletes a search and its tags and leaves its entries. No capture route: a search is created by the agent only |
| Hooks | `numbers` (open entries, `to review`), `today` (found today or happening today, a dismissed one excluded), `queue` (every open entry, newest first, `waits` the days it has stood), `rows` (every listed entry, newest first, capped at 200), `item`, `context` (each search with its schedule and tags, the open entries with urls, last run) |
| Tools | read on both servers: `newsfeed_search(query, status, limit)` (the same `LIKE` per word, tags included, limit capped at 100), `newsfeed_get(id)`, `newsfeed_searches()`; write on `otto` only: `newsfeed_search_add(name, prompt, tags, every_days=1, cap=None)` (`cap` falls back to `items_per_run`; the first run is the next nightly window; event `search added`), `newsfeed_tag(id, tags)` (event `tagged`) |
| Schedule | `newsfeed.run` every 24h inside the nightly window, resource `newsfeed`. It takes every search whose `next_run` is today or earlier and runs each as one budgeted, read-only CLI run with the CLI's WebSearch and WebFetch and no Otto tools: the prompt is today's date, the search's own prompt, the last hundred of its entries with their status (a dismissed one shows what to stop bringing), the accepted entries whose follow-up day has come, and the JSON shape `{text, url, summary, date, time, follow_up, tags, follows}` (a fence is tolerated). Up to `cap` new rows go in with `INSERT OR IGNORE` on url, each tagged with the search's tags plus the run's; the follow-ups asked about are consumed; `next_run` moves `every_days` on; the entry count is the search's `last_result` and the cursor `newsfeed.run` moves, all in one transaction per search, one `found` event per row. A reply with no JSON array is that search's `last_result` (`bad reply: …`), it stays due, and the run goes on to the next search. A budget refusal midway stops the job as skipped with what already committed kept. `Skipped` with no searches or none due |
| Follow-ups | the run may attach `follow_up` to an entry; once it is accepted and the day has come, the next run of its search lists it as due, the reply's new entries may name it in `follows`, and the date is cleared so it is asked once |
| Config | `[newsfeed]`: `items_per_run` (the cap a search gets when the agent sets none) |
| Dismissal | a dismissed entry leaves every list, `today`, `queue` and the agent's context, and offers only its url. The row stays in `newsfeed_items`, which is what stops the run proposing the same url again. One url is one entry: a listing that repeats a url on another date is not proposed twice |

## Patches

### A standing search is nowhere in the app

- Kind: gap
- Where: `app/modules/newsfeed/routes.py` (`rows`, `searches`, `_search_item`)
- Found: 2026-09-20, porting the page to the new shell; widened 09-21-2026 by the one-page change
- Status: open

What happens: `rows` returns entries only, so no list the browser draws contains a search. `blank` still serves them, `item/s<id>` still answers for one and nothing asks. Only the agent, through `newsfeed_searches`, can say what Otto is watching for, how often it runs, when it runs next, or that a run whose reply carried no JSON array has been leaving `bad reply: …` in `last_result` night after night. `kill` therefore has nothing to fire at, and a search cannot be tagged from the app.

Expected: requirement 3 — the searches are listed, each killable from there. A search that failed says so on its own row.

Fix: `rows` emits the searches beside the entries, either as rows of the `newsfeed` facet marked by their type or behind the facet's own second mode, with `last_result` on the row when it starts with `bad`. Tagging one is a decision first: a search's tags ride onto every entry its next run brings back, so either the platform's tag routes gain a per-module hook that writes `newsfeed_tags` for an `s<id>`, or a search's own tags become ordinary `app_tags` that do not ride onto its entries, which changes what tagging a search means for the run, the tools and the agent's context.

### Open link goes nowhere

- Kind: bug
- Where: `app/modules/newsfeed/routes.py` (`_verbs`, `ACTIONS`), `app/api.py` (`POST /api/verb`), `app/static/core.js` (`doVerb`'s `r.url`)
- Found: 09-21-2026, the one-page change
- Status: open

What happens: every entry with a url offers the verb `link`, labelled Open link. `ACTIONS` has no `link`, so the verb posts to `POST /api/verb`, reaches `action/link` and comes back as the toast `unknown action link`. `doVerb` opens a tab when the answer carries a `url`, and `/api/verb` never returns one, so no verb in any module can open a link.

Expected: Open link opens the entry's url.

Fix: `/api/verb` answers with the row's `url` for a verb the module declares as a link, or the browser handles `link` itself from the `url` already on the row, as it handles `edit` and `query`. The second needs no round trip and is the smaller change.

### Kill neither asks nor removes

- Kind: bug
- Where: `app/static/core.js` (`DESTRUCTIVE`), `app/api.py` (`REMOVES`), `app/modules/newsfeed/routes.py` (`_kill`)
- Found: 09-20-2026, the recheck of the ported page; restated 09-21-2026
- Status: open

What happens: `kill` deletes a search and is in neither the browser's `DESTRUCTIVE` set nor the daemon's `REMOVES` set. So it fires on one click with no question, and the answer says the row stays, though the search is gone.

Expected: a verb that deletes asks first and takes its row away, as `dismiss` and `forget` do.

Fix: add `kill` to both sets. They are two lists of the same fact in two files, so the better fix is one list: the module declares which of its verbs remove, on the verb, and both sides read it.

### Newsfeed's own tags are missing from the tag catalog

- Kind: gap
- Where: `app/store.py` (`all_tags`), `app/modules/newsfeed/routes.py` (`_written`)
- Found: 2026-09-20, porting the page to the new shell
- Status: open

What happens: the tags a nightly run writes live in `newsfeed_tags`, and `/api/tags` counts only `app_tags` and `second_brain_tags`. A tag carried only by newsfeed entries never appears in the search bar's suggestions or the palette, though the feed still narrows by it because the rows carry it.

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
