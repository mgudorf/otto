# Memory

1. General note taking/to-do list/journaling module
2. Typically a dumping ground for random ideas/notes I have
3. Agent aimed at consolidating/collecting thoughts, must be very literal and not reword items/add to them. Can suggest action items based on current state/discoveries, never makes suggestion more than onces. 

## Built

| Piece | Current state |
|---|---|
| Tables | `memories(kind note\|link\|quote\|fact\|task, text, created_at, updated_at, done_at)`, `memory_tags`, `memory_suggestions(text unique, memory_ids, status open\|accepted\|dismissed)`, `memories_fts` (FTS5, trigger-maintained) |
| Routes | `left` (query: each word quoted, all required in `memories_fts`; chip All/Notes/Links/Quotes/Facts/Tasks, page), `blank` (kinds, counts, open suggestions), `item/{id}` (a link's `Open` is the first token of the text), `action/{capture\|forget\|tag\|untag\|done\|suggestion}`, each a `prepare(store, body)` that validates and answers 400 or 404 before the job, then a `write(ctx)` inside it |
| Hooks | `numbers` (total), `today` (captures of the local day), `item`, `context` (counts, last ten, open suggestions) |
| Tools | read: `memory_search`, `memory_get`, `memory_tags`, `memory_suggestions`; write: `memory_add`, `memory_tag`, `memory_suggest` (records a suggestion so it is never repeated) |
| Schedule | `memory.suggest`, every 24h inside the nightly window, resource `memory`: proposes up to `suggest_max` action items from the undone memories of the last `suggest_lookback_days` days as a JSON array of `{text, memory_ids}`, every prior suggestion listed in the prompt, tools `memory_search` and `memory_get`, inserted with `INSERT OR IGNORE`, cursor `memory.suggest` |
| Page | LEFT: search, kind chips, rows by day with the kind as leading slot; MIDDLE blank: capture box (kind chips, textarea, tags, `Save`, Ctrl+Enter) and open suggestions with `Accept` / `Dismiss`; MIDDLE selected: inspector with tags (add on Enter, click to remove), `Open` for links, `Done` for tasks, `Forget` |
| Departures | the blank state (capture box) is not in the artboard, which left it unspecified |

## Patches

None open.
