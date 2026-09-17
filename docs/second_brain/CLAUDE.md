# Second Brain

1. General note taking/to-do list/journaling module
2. Typically a dumping ground for random ideas/notes I have
3. Agent aimed at consolidating/collecting thoughts, must be very literal and not reword items/add to them. Can suggest action items based on current state/discoveries, never makes suggestion more than onces. 

## Built

| Piece | Current state |
|---|---|
| Tables | `second_brain_items(kind note\|link\|quote\|fact\|task, text, created_at, updated_at, done_at)`, `second_brain_tags(item_id, tag)`, `second_brain_suggestions(text unique, item_ids, status open\|accepted\|dismissed)`, `second_brain_fts` (FTS5, trigger-maintained) |
| Setup | `setup(config)` renames in place the columns a database from before 2026-09-17 still holds under the module's old name, `memory` (`memory_id`, `memory_ids`); the tables themselves are lines in `app/migrate.py` `RENAMES`, and the module's name in platform rows a line in `MODULE_RENAMES` |
| Routes | `left` (query: each word quoted, all required in `second_brain_fts`; chip All/Notes/Links/Quotes/Facts/Tasks, page), `blank` (kinds, counts, open suggestions), `item/{id}` (a link's `Open` is the first token of the text), `action/{capture\|forget\|tag\|untag\|done\|accept\|dismiss}`, each a `prepare(store, body)` that validates and answers 400 or 404 before the job, then a `write(ctx)` inside it. A suggestion's row id is `s<n>`, so it never collides with an item of the same number: `item/s3` inspects one, `accept` and `dismiss` take it, and anything else under `s` is a 404 rather than a 500 |
| Hooks | `numbers` (total), `today` (captures of the local day), `queue` (every open suggestion, newest first, so Home's Review group keeps it however old it is), `item`, `context` (counts, last ten, open suggestions) |
| Tools | read: `second_brain_search`, `second_brain_get`, `second_brain_tags`, `second_brain_suggestions`; write: `second_brain_add`, `second_brain_tag`, `second_brain_suggest` (records a suggestion so it is never repeated) |
| Schedule | `second_brain.suggest`, every 24h inside the nightly window, resource `second_brain`: proposes up to `suggest_max` action items from the undone items of the last `suggest_lookback_days` days as a JSON array of `{text, item_ids}`, every prior suggestion listed in the prompt, tools `second_brain_search` and `second_brain_get`, inserted with `INSERT OR IGNORE`, cursor `second_brain.suggest` |
| Page | LEFT: search, kind chips, rows by day with the kind as leading slot; MIDDLE blank: capture box (kind chips, textarea, tags, `Save`, Ctrl+Enter) and open suggestions with `Accept` / `Dismiss`; MIDDLE selected: inspector with tags (add on Enter, click to remove), `Open` for links, `Done` for tasks, `Forget` |
| Dismissal | an accepted or dismissed suggestion leaves the blank state, `queue` and the agent's context. The row stays in `second_brain_suggestions`, which is what stops `second_brain.suggest` proposing it again: the prompt lists every prior suggestion whatever its status. `Done` on a task is not a dismissal, so a completed task stays on LEFT, struck through |
| Departures | the blank state (capture box) is not in the artboard, which left it unspecified |

## Patches

### Accepting a suggestion records the decision and nothing else

- Kind: gap
- Where: `app/modules/second_brain/routes.py` `_decide("accepted")`; `app/static/pages/second_brain.js` blank state; Home's `Review` group
- Found: 2026-09-13, the dismissal change
- Status: open, deferred 2026-09-17: the owner chose to leave it as is for now

What happens: `Accept` and `Dismiss` on a suggestion both do the same thing, stamp `status`, and the row leaves the list either way. A suggestion is an action item ("call them today"); accepting it produces no task, no item and no reminder, so the only trace is an `accepted` event and a row the nightly run will not repeat. Now that suggestions wait under Home's `Review`, the two buttons are side by side with no visible difference between them.

Expected: accepting an action item leaves the owner with the item, presumably a `task` row carrying the suggestion's text and a link to the items it came from.

Fix: decide whether `accept` writes a `task` row (text from the suggestion, tagged from `item_ids`) and returns its id so the page can open it; if it does, the event says which item it created, and `Dismiss` stays a bare status stamp. Options weighed on 2026-09-17: Accept creates a `task` item tagged from its sources (recommended); Accept prefills the capture box as a task; the suggestion stays under Review until done; leave as is (chosen for now).
