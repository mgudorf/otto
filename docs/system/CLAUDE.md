# System

## Built

| Piece | Current state |
|---|---|
| Facet | `routine`, hue `#A6ACB8`. Every row carries it as its one `fixed` tag. The module owns no tables and no agent: every row it lists is a row of the platform's `app_tasks` |
| Schedules | `system.heartbeat` every 60 s proves the clock runs; `system.prune_sessions` every 24 h deletes closed sessions older than `claude.sessions_kept_days`, resource `sessions` |
| Rows | One ROW per scheduled task, type `routine`, most recently run first and one that has never run behind them: `id` and `title` the task name, `when` its last run on the owner's clock, `snip` and `right` what the clock promises (`every 15 m`, or `nightly` for a task that runs only inside the nightly window), `late` when the last run failed, `paused` when the task is switched off, and `kv` of Every, Last run, Last result and the resource it holds |
| Queue | Only what broke: a task whose last run failed, `waits` the days it has stood that way, so the feed lists it under Priority |
| Verbs | `run` Run now hands the task to the runner as the clock would, so the run stamps the task with its own result; nothing is awaited, because a nightly task can run for minutes. `pause` and `resume` throw the scheduler's switch and write an event, and a paused task offers Resume in place of Pause |
| Routes | `action/{run\|pause\|resume}`, reached through the platform's `POST /api/verb`. An unknown verb and an unknown task name are each a 404 before anything is queued, and `run` on a module the daemon failed to load is a 409 |
| Hooks | `rows`, `queue`. No `numbers`, `today`, `item`, `context` and no tools |

## Patches

### A tag on a routine is written and never seen again

- Kind: bug
- Where: `app/modules/system/routes.py` (`_row`)
- Found: 09-21-2026, the one-page change
- Status: open

What happens: `_row` hands every routine an empty `tags` list and never marks it `taggable: false`, so the feed lets the owner tag one. The tag is written into `app_tags` under `system` and nothing ever reads it back, so the row shows no tag and the tag finds no routine.

Expected: either a routine takes a tag and shows it, as every other row does, or it takes none, as a Database table does.

Fix: decide which. A routine is the daemon's own shape rather than something the owner wrote, which argues for `taggable: false`; if it is to take tags, `_row` reads them from `tags_for(store, "system", names)` once for the whole list, the way the other modules' `rows` hooks do.

### Conversations are deleted 30 days after they close

- Kind: bug
- Where: `app/modules/system/tasks.py` (`prune_sessions`), `[claude] sessions_kept_days`, `app/static/settings.js` ("Old conversation cleanup"), against Chat's promise in `app/modules/chat/__init__.py`, `app/modules/chat/routes.py` and `docs/chat/CLAUDE.md`
- Found: 09-22-2026, the stale-code audit
- Status: open, needs a decision

What happens: `system.prune_sessions` runs daily and deletes every session closed more than `sessions_kept_days` (30) days ago, with its turns. Closing a drawer tab closes its session, so every conversation disappears a month after it was closed unless it was reopened, and its folder under `data/workspace/chat/<id>/` stays behind. Chat promises every conversation is kept until the owner deletes it. Nothing is gone yet: the oldest of the five closed sessions, 36 turns among them, crosses the line about 10-09-2026.

Expected: one rule, kept by the code and stated by Chat.

Fix: either the task prunes only the sessions that never started (`title = '(failed to start)'`) and `sessions_kept_days` goes, or Chat's promise and the task's title in Settings say 30 days and the task deletes the folder too. The first keeps the owner's record; the second keeps the store small.

### Opening a routine asks for a route System does not serve

- Kind: bug
- Where: `app/static/core.js` (`fill`), `app/modules/system/routes.py`
- Found: 09-22-2026, the stale-code audit
- Status: open

What happens: opening any row fetches `GET /api/<module>/item/<id>` to fill it out. System serves no `item` route, so every routine opened sends a request that answers 404, which `fill` swallows; the page draws the row as it came.

Expected: a routine opens without a failed request.

Fix: System serves `item/{name}` returning the routine's row, or its rows carry `full: true` so that `fill` asks nothing. The second is one key.
