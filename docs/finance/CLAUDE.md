# Finance

1. General place for me to organize important information regarding anything money related; budget/recurring subscriptions/payments, stock/investment info (not direct link to account, just a proxy with manual inputs)
2. Agent should be able to be asked general questions regarding finances; i.e. natural language queries. 

## Built

| Piece | Current state |
|---|---|
| Facet | `finance`, hue `#8CC79E`. Every row carries it as its one `fixed` tag |
| Tables | `finance_entries(kind account\|recurring\|holding\|budget, name, amount in cents, cadence monthly\|yearly\|weekly, note, due_on YYYY-MM-DD or null, ended_at)`, `finance_amounts` (every value the entry has held). The package's `setup` adds `due_on` to a database created before the column existed |
| Rows | One ROW per entry, type `ledger`, most recently touched first: `title` the name, `when` the last touch on the owner's clock, `tags` the kind first and then the owner's from `app_tags`, `snip` the cadence, `amount` the money with its sign, `due` the next occurrence, `dim` once ended, and `note`, which rides the row so that typing a word from a note finds its entry |
| Verbs | `update` Update amount, `due` Set date on a recurring entry, `end` End while active, `forget` Forget. `end` and `forget` go through `POST /api/verb` and the browser asks first; `update` and `due` never leave the browser — they open the drawer with a draft for the agent |
| Item | `item/{id}` is the row plus what only the open entry needs: the anchor `due_on`, `kv` of cadence and note, and `hist`, the twelve most recent amounts by date, newest first |
| Routes | `left` (`query` as `LIKE` per word over name and note, all words required, each word escaped so `%`, `_` and a backslash stand for themselves; every entry it reaches as a ROW, grouped by kind, active first then by name, the Recurring group soonest due first then undated then ended, and `more` always false because nothing is held back), `blank` (the four totals, the kinds and cadences a capture offers, and the word each kind goes by), `item/{id}`, `action/{capture\|update\|due\|end\|forget}`, each validated before the job is queued: `cadence` is required for recurring and budget and dropped otherwise, amounts parse with commas and round half-up to cents, `due_on` is kept on capture for recurring only and `due` refuses any other kind (400), a blank date clears it, and `update` is the only path that appends to `finance_amounts`; a missing or non-integer `id` is a 400 naming the field (`app.modules.int_id`, shared with Second Brain) |
| Due date | `due_on` is the one date the owner entered; `next_due` is never stored but projected on every read as the first occurrence on or after today, stepped from the anchor by the cadence (weekly by weeks; monthly and yearly by months, a day past a short month's end clamped to its last day, measured from the anchor so it clamps once). An ended or undated entry has none |
| Hooks | `numbers` (active records), `today` (entries touched in the local day), `rows`, `item`, `context` (the four totals, every active entry with its next due where dated, the ended names). No `queue`: nothing in the ledger waits on the owner |
| Tools | read only: `finance_list` and `finance_get` carry `due_on` and `next_due`, `finance_totals`. The manifest declares no write tools |
| Totals | recurring and budget amounts normalize to a month as yearly / 12 and weekly x 52 / 12; accounts and holdings sum as entered |

## Patches

### Nothing can add or change an entry

- Kind: gap
- Where: `app/modules/finance/routes.py` (`action/capture`, `action/update`, `action/due`), `app/modules/finance/tools.py` (no write tools), `app/static/core.js` (`HERE.update`, `HERE.due`)
- Found: 09-21-2026, the one-page change
- Status: open

What happens: capture had a box on the Finance page and update and due had popups over their buttons; both went with the page. `capture` now has no caller at all, and `update` and `due` are verbs the browser answers itself, opening the drawer with `update the amount to ` for the agent to finish — but the manifest declares no write tools, so the agent cannot carry that sentence out either. The ledger can only be read.

Expected: an amount can be recorded and changed from the app.

Fix: either give the module the write tools the drafts assume (capture, update the amount, set the date), or make `update` and `due` ordinary verbs that take the `value` `POST /api/verb` already carries and add a path for a new entry. The first puts the ledger in the agent's hands; the second keeps it out of them.

### Ending an entry is a one-way door

- Kind: defect
- Where: `app/modules/finance/routes.py`, `_end` and the `end` verb in `_verbs`
- Found: 2026-09-20, the review of the ported Finance page
- Status: open

What happens: the browser now asks before running `end`, but nothing can take it back. `_update` and `_due` never clear `ended_at` and no action sets it to null, so an entry ended by mistake can only be forgotten and captured again, which loses its amount history.

Expected: an irreversible change can be undone.

Fix: add a `resume` action that clears `ended_at`, and offer it on an ended entry in place of `end`. That also decides whether the entry's amount rejoins the totals and its next due starts projecting again, which is why it is filed rather than fixed.
