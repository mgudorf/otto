# Second Brain

1. General note taking/to-do list/journaling module
2. Typically a dumping ground for random ideas/notes I have
3. Agent aimed at consolidating/collecting thoughts, must be very literal and not reword items/add to them. Can suggest action items based on current state/discoveries, never makes suggestion more than onces. 

## Built

| Piece | Current state |
|---|---|
| Facet | `entry`, hue `#DDB06F`. The module's package is `second_brain` and its title is `Entry`, which is what the feed, the brain and the search bar say. A captured item's kind is its type — `note`, `task`, `link`, `quote`, `fact` — and also its first plain tag, so `#task` narrows to tasks while the facet stays the one fixed tag. A suggestion is type `suggestion` and `taggable` false. Verbs: a link offers `open` then `forget`, a task `done` or `reopen` then `forget`, anything else `forget` alone; an open suggestion offers `accept` and `dismiss`, a decided one nothing |
| Tables | `second_brain_items(kind note\|link\|quote\|fact\|task, text, created_at, updated_at, done_at)`, `second_brain_tags(item_id, tag)`, `second_brain_suggestions(text unique, item_ids, status open\|accepted\|dismissed)`, `second_brain_fts` (FTS5, trigger-maintained) |
| Setup | `setup(config)` renames in place the columns a database from before 2026-09-17 still holds under the module's old name, `memory` (`memory_id`, `memory_ids`); the tables themselves are lines in `app/migrate.py` `RENAMES`, and the module's name in platform rows a line in `MODULE_RENAMES` |
| Routes | `item/{id}` answers the shared ROW: `id`, `module`, `title` (the text itself), local `when`, `fixed` the facet, `tags`, `type`, `done`, `href` on a link, and `verbs`. `blank` (open suggestions as ROWs), `action/{capture|forget|tag|untag|done|reopen|accept|dismiss}`, each a `prepare(store, body)` that validates and answers 400 or 404 before the job (a missing or non-integer `id` is a 400 through `app.modules.int_id`), then a `write(ctx)` inside it. A suggestion's row id is `s<n>`, so it never collides with an item of the same number: `item/s3` inspects one, `accept` and `dismiss` take it, and anything else under `s` is a 404 rather than a 500 |
| Hooks | `numbers` (total), `today` (captures of the local day), `rows` (every item as a ROW, newest first), `queue` (every open suggestion, newest first, which is what the facet contributes to Priority), `item`, `context` (counts, last ten, open suggestions) |
| Tools | read: `second_brain_search`, `second_brain_get`, `second_brain_tags`, `second_brain_suggestions`; write: `second_brain_add`, `second_brain_tag`, `second_brain_suggest` (records a suggestion so it is never repeated). `second_brain_add` is how a thought is captured now: the capture box went with the page, so what is typed into the drawer is what files it. A tag through `second_brain_add` or `second_brain_tag` is one word each, letters and digits; a list with one that is not is refused naming it |
| Schedule | `second_brain.suggest`, every 24h inside the nightly window, resource `second_brain`: proposes up to `suggest_max` action items from the undone items of the last `suggest_lookback_days` days as a JSON array of `{text, item_ids}`, every prior suggestion listed in the prompt, tools `second_brain_search` and `second_brain_get`, inserted with `INSERT OR IGNORE`, cursor `second_brain.suggest` |
| Dismissal | an accepted or dismissed suggestion leaves `queue` and the agent's context. The row stays in `second_brain_suggestions`, which is what stops `second_brain.suggest` proposing it again: the prompt lists every prior suggestion whatever its status. `Done` on a task is not a dismissal, so a completed task stays in the feed, struck through and dim |
| Departures | the artboard specifies neither the capture box nor the suggestions plate, and both went with the page: a suggestion is a row of the facet like any other, carrying the two verbs it waits on. The item's mark is the facet's, so a kind is read from the row's tags rather than from an icon of its own |

## Patches

### The Entry group sits fourth in the feed and first on the brain

- Kind: defect
- Where: `app/modules/second_brain/__init__.py` (`order`), against `app/static/brain.js` (`SLOT`, `LOBES`)
- Found: 09-21-2026, the one-page change
- Status: open

What happens: the feed groups by `MANIFEST.order`, which is still the module's old place in the rail, 3. The brain places a facet's callout by its own fixed slot, where `entry` is first. So the facets read chats, email, education, entry, science on one side of the page and entry, chats, email, education, science on the other.

Expected: one order of facets, the one the brain draws: entry, chats, email, education, science, finance, newsfeed, database, routine.

Fix: `order = 0` here, which is free (Home carries 0 and has no facet, so it takes no place in the feed). Nothing else moves: every other faceted module already sits in the brain's order.

### Accepting a suggestion records the decision and nothing else

- Kind: gap
- Where: `app/modules/second_brain/routes.py` `_decide("accepted")`
- Found: 2026-09-13, the dismissal change
- Status: open, deferred 2026-09-17: the owner chose to leave it as is for now

What happens: `Accept` and `Dismiss` on a suggestion both do the same thing, stamp `status`, and the row leaves the feed either way. A suggestion is an action item ("call them today"); accepting it produces no task, no item and no reminder, so the only trace is an `accepted` event and a row the nightly run will not repeat.

Expected: accepting an action item leaves the owner with the item, presumably a `task` row carrying the suggestion's text and a link to the items it came from.

Fix: decide whether `accept` writes a `task` row (text from the suggestion, tagged from `item_ids`) and returns its id so the page can open it; if it does, the event says which item it created, and `Dismiss` stays a bare status stamp. Options weighed on 2026-09-17: Accept creates a `task` item tagged from its sources (recommended); Accept prefills a capture; the suggestion stays under Review until done; leave as is (chosen for now).

### Code nothing reaches

- Kind: defect
- Where: `app/modules/second_brain/routes.py` (`blank`), `app/modules/second_brain/tasks.py` (the `second_brain.suggest` cursor), `second_brain_suggestions.item_ids`, `tests/test_second_brain.py` (the `blank` calls, the cursor assertion, the unused `JobFailed` import)
- Found: 09-22-2026, the stale-code audit
- Status: open

What happens: nothing requests `blank`. The suggest run writes a cursor nothing reads. Every suggestion stores the ids of the items it came from, and nothing reads them either: `second_brain_suggestions` lists suggestions without them, and a suggestion row carries no `related`. The Tools row above says the drawer is the only way to capture; point mode's Capture posts `action/capture` too.

Expected: Entry serves what the feed, the verbs, the tools and the clock use.

Fix: `blank`, the cursor and the import go. `item_ids` stays for "Accepting a suggestion records the decision and nothing else", which would read it; meanwhile it can become the row's `related`, so a suggestion's sources show under it.

### A suggestion's page is empty under its title

- Kind: bug
- Where: `app/static/core.js` (`contentEl`, the `suggestion` case), `app/modules/second_brain/routes.py` (`_suggestion_item`)
- Found: 09-22-2026, the stale-code audit
- Status: open

What happens: the renderer draws a suggestion's `body`, and no suggestion carries one, so the page shows the text in its head and nothing below. The platform doc's table says a suggestion is drawn as its prose.

Expected: the suggestion reads as prose on its page.

Fix: `_suggestion_item` sends the text as `body`, escaped, the way Newsfeed sends a summary.
