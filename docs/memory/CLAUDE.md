# Memory

1. General note taking/to-do list/journaling module
2. Typically a dumping ground for random ideas/notes I have
3. Agent aimed at consolidating/collecting thoughts, must be very literal and not reword items/add to them. Can suggest action items based on current state/discoveries, never makes suggestion more than onces. 

## Built

| Piece | Current state |
|---|---|
| Tables | `memories(kind note\|link\|quote\|fact\|task, text, created_at, updated_at, done_at)`, `memory_tags`, `memory_suggestions(text unique, memory_ids, status open\|accepted\|dismissed)`, `memories_fts` (FTS5, trigger-maintained) |
| Routes | `left` (query: each word quoted, all required in `memories_fts`; chip All/Notes/Links/Quotes/Facts/Tasks, page), `blank` (kinds, counts, open suggestions), `item/{id}` (a link's `Open` is the first token of the text), `action/{capture\|forget\|tag\|untag\|done\|accept\|dismiss}`, each a `prepare(store, body)` that validates and answers 400 or 404 before the job, then a `write(ctx)` inside it. A suggestion's row id is `s<n>`, so it never collides with a memory of the same number: `item/s3` inspects one, `accept` and `dismiss` take it, and anything else under `s` is a 404 rather than a 500 |
| Hooks | `numbers` (total), `today` (captures of the local day), `queue` (every open suggestion, newest first, so Home's Review group keeps it however old it is), `item`, `context` (counts, last ten, open suggestions) |
| Tools | read: `memory_search`, `memory_get`, `memory_tags`, `memory_suggestions`; write: `memory_add`, `memory_tag`, `memory_suggest` (records a suggestion so it is never repeated) |
| Schedule | `memory.suggest`, every 24h inside the nightly window, resource `memory`: proposes up to `suggest_max` action items from the undone memories of the last `suggest_lookback_days` days as a JSON array of `{text, memory_ids}`, every prior suggestion listed in the prompt, tools `memory_search` and `memory_get`, inserted with `INSERT OR IGNORE`, cursor `memory.suggest` |
| Page | LEFT: search, kind chips, rows by day with the kind as leading slot; MIDDLE blank: capture box (kind chips, textarea, tags, `Save`, Ctrl+Enter) and open suggestions with `Accept` / `Dismiss`; MIDDLE selected: inspector with tags (add on Enter, click to remove), `Open` for links, `Done` for tasks, `Forget` |
| Dismissal | an accepted or dismissed suggestion leaves the blank state, `queue` and the agent's context. The row stays in `memory_suggestions`, which is what stops `memory.suggest` proposing it again: the prompt lists every prior suggestion whatever its status. `Done` on a task is not a dismissal, so a completed task stays on LEFT, struck through |
| Departures | the blank state (capture box) is not in the artboard, which left it unspecified |

## Patches

### Accepting a suggestion records the decision and nothing else

- Kind: gap
- Where: `app/modules/memory/routes.py` `_decide("accepted")`; `app/static/pages/memory.js` blank state; Home's `Review` group
- Found: 2026-09-13, the dismissal change
- Status: open, needs a decision

What happens: `Accept` and `Dismiss` on a suggestion both do the same thing, stamp `status`, and the row leaves the list either way. A suggestion is an action item ("call them today"); accepting it produces no task, no memory and no reminder, so the only trace is an `accepted` event and a row the nightly run will not repeat. Now that suggestions wait under Home's `Review`, the two buttons are side by side with no visible difference between them.

Expected: accepting an action item leaves the owner with the item, presumably a `task` memory carrying the suggestion's text and a link to the memories it came from.

Fix: decide whether `accept` writes a `task` row (text from the suggestion, tagged from `memory_ids`) and returns its id so the page can open it; if it does, the event says which memory it created, and `Dismiss` stays a bare status stamp.
