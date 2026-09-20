# Second Brain

1. General note taking/to-do list/journaling module
2. Typically a dumping ground for random ideas/notes I have
3. Agent aimed at consolidating/collecting thoughts, must be very literal and not reword items/add to them. Can suggest action items based on current state/discoveries, never makes suggestion more than onces. 

## Built

| Piece | Current state |
|---|---|
| Tables | `second_brain_items(kind note\|link\|quote\|fact\|task, text, created_at, updated_at, done_at)`, `second_brain_tags(item_id, tag)`, `second_brain_suggestions(text unique, item_ids, status open\|accepted\|dismissed)`, `second_brain_fts` (FTS5, trigger-maintained) |
| Setup | `setup(config)` renames in place the columns a database from before 2026-09-17 still holds under the module's old name, `memory` (`memory_id`, `memory_ids`); the tables themselves are lines in `app/migrate.py` `RENAMES`, and the module's name in platform rows a line in `MODULE_RENAMES` |
| Routes | `left` (query: each word quoted, all required in `second_brain_fts`; chip All/Tasks, page) and `item/{id}` both answer the shared ROW: `id`, `module`, `title`, local `when`, `tags`, `fixed` (the kind, read-only), `kind`, `done`, and the `actions` the row's buttons and the pane's are both built from, so `Forget` asks one question wherever it is pressed. `blank` (open suggestions, each a ROW under `suggestion` carrying the `accept` and `dismiss` it still waits on, `dismiss` with the question it asks first; the ROW is `taggable` false, since no item of the owner's stands behind it for a tag to point at), `action/{capture|forget|tag|untag|done|reopen|accept|dismiss}`, each a `prepare(store, body)` that validates and answers 400 or 404 before the job (a missing or non-integer `id` is a 400 through `app.modules.int_id`), then a `write(ctx)` inside it. A link's `Open` is the first token of the text. A suggestion's row id is `s<n>`, so it never collides with an item of the same number: `item/s3` inspects one, `accept` and `dismiss` take it, and anything else under `s` is a 404 rather than a 500 |
| Hooks | `numbers` (total), `today` (captures of the local day), `rows` (every item as a ROW, newest first, which the tag intersection and Home's Recent read), `queue` (every open suggestion, newest first, so Home's Review group keeps it however old it is), `item`, `context` (counts, last ten, open suggestions) |
| Tools | read: `second_brain_search`, `second_brain_get`, `second_brain_tags`, `second_brain_suggestions`; write: `second_brain_add`, `second_brain_tag`, `second_brain_suggest` (records a suggestion so it is never repeated) |
| Schedule | `second_brain.suggest`, every 24h inside the nightly window, resource `second_brain`: proposes up to `suggest_max` action items from the undone items of the last `suggest_lookback_days` days as a JSON array of `{text, item_ids}`, every prior suggestion listed in the prompt, tools `second_brain_search` and `second_brain_get`, inserted with `INSERT OR IGNORE`, cursor `second_brain.suggest` |
| Page | One list under `All`, `Tasks`, `Notes`, `Links`, grouped by day. A task carries a box in the module's hue that completes or reopens it, anything else the mark of its kind; a done task is struck through and dim, and a row's tags sit beside its text. The `+` opens the capture box over the list, always on Note: a Note/Task segment, a tag field and `Save`; Enter saves, Escape closes, and text starting with a URL is captured as a link. Open suggestions sit on their own plate above the days with `Accept` and `Dismiss`, and `Dismiss` asks before it drops the suggestion for good. A suggestion holds none of the owner's tags and its ROW says so, so no checkbox, ctrl-click, `x`, `t` or bulk verb reaches it, on this page or under Home's `Review`. A picked row opens the pane: the text, its date, its tags, then the buttons the daemon's `actions` list offers — the primary one in the hue, a link's `Open` under the external symbol, red only on the one that asks first. Rows selected together take `Done` from the bulk bar, which is there only while one of them is an open task: each task is its own write, a failure is said once and the rest still run, and a row that leaves the list is unpicked with it |
| Dismissal | an accepted or dismissed suggestion leaves the suggestions plate, `queue` and the agent's context. The row stays in `second_brain_suggestions`, which is what stops `second_brain.suggest` proposing it again: the prompt lists every prior suggestion whatever its status. `Done` on a task is not a dismissal, so a completed task stays on the list, struck through |
| Departures | the capture box and the suggestions plate are not in the artboard, which left both unspecified |

## Patches

### Accepting a suggestion records the decision and nothing else

- Kind: gap
- Where: `app/modules/second_brain/routes.py` `_decide("accepted")`; the suggestions plate on `app/static/pages/second_brain.js`; Home's `Review` group
- Found: 2026-09-13, the dismissal change
- Status: open, deferred 2026-09-17: the owner chose to leave it as is for now

What happens: `Accept` and `Dismiss` on a suggestion both do the same thing, stamp `status`, and the row leaves the list either way. A suggestion is an action item ("call them today"); accepting it produces no task, no item and no reminder, so the only trace is an `accepted` event and a row the nightly run will not repeat. On the page and under Home's `Review` the two buttons sit side by side with no difference between what they do.

Expected: accepting an action item leaves the owner with the item, presumably a `task` row carrying the suggestion's text and a link to the items it came from.

Fix: decide whether `accept` writes a `task` row (text from the suggestion, tagged from `item_ids`) and returns its id so the page can open it; if it does, the event says which item it created, and `Dismiss` stays a bare status stamp. Options weighed on 2026-09-17: Accept creates a `task` item tagged from its sources (recommended); Accept prefills the capture box as a task; the suggestion stays under Review until done; leave as is (chosen for now).

### The list stops at one page and nothing reaches the older rows

- Kind: gap
- Where: `app/modules/second_brain/routes.py` `left`; `app/static/pages/second_brain.js` `load`
- Found: 2026-09-20, the port of the page to the new shell
- Status: open

What happens: `left` answers the newest `ui.page_size` items (40) and says `more: true` when there are others, and the page loads that one answer. The old page had a button that asked for the next page; the new list has none, so the rows past the first page cannot be reached, and the chips and the search bar narrow only what was loaded. The route still takes `query`, `chip` and `page`, and nothing calls it with them.

Expected: recall reaches every captured item, and typing in the search bar searches the table, not the loaded rows.

Fix: decide how the new list grows, then drive `left` from it: either the page asks for the next page as the list is scrolled and `load` keeps what it has, or the shell's search text reaches `load` so the daemon's own full-text query does the narrowing.