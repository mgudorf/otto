# Finance

1. General place for me to organize important information regarding anything money related; budget/recurring subscriptions/payments, stock/investment info (not direct link to account, just a proxy with manual inputs)
2. Agent should be able to be asked general questions regarding finances; i.e. natural language queries. 

## Built

| Piece | Current state |
|---|---|
| Tables | `finance_entries(kind account\|recurring\|holding\|budget, name, amount in cents, cadence monthly\|yearly\|weekly, note, ended_at)`, `finance_amounts` (every value the entry has held) |
| Routes | `left` (query, chips All/Accounts/Recurring/Holdings/Budgets; rows ordered active first then by name, the amount as `stampText`), `blank` (totals, kinds, cadences, counts), `item/{id}` with the amount history (`update` primary, `end` while active, `forget` with confirm), `action/{capture\|update\|end\|forget}`, each validated before the job is queued: `cadence` is required for recurring and budget and dropped otherwise, amounts parse with commas and round half-up to cents, and `update` is the only path that appends to `finance_amounts` |
| Hooks | `numbers` (active records), `today` (entries touched in the local day), `item`, `context` (the four totals, every active entry, the ended names) |
| Tools | read only: `finance_list`, `finance_get`, `finance_totals`. The manifest declares no write tools |
| Totals | recurring and budget amounts normalize to a month as yearly / 12 and weekly x 52 / 12; accounts and holdings sum as entered |
| Page | LEFT: search, kind chips, one group per kind with the amount in the stamp slot and a dot for active, ended entries last in their group and struck through; MIDDLE blank: the totals and the capture form; MIDDLE selected: the entry, its amount history, `Update`, `End`, `Forget` |
| Departures | the artboard's Money page was a document list, now Business: chips are the four kinds, rows group by kind rather than day, item actions are `Update` / `End` / `Forget` |

## Patches

### A missing or non-numeric `id` on an action is a 500, not a 400

- Kind: bug
- Where: `app/modules/finance/routes.py` `_check_update` and `_check_id` (`int(body["id"])`); `app/modules/web_search/routes.py` `agree` and `disagree` checks (`int(body.get("id", 0))`)
- Found: 2026-09-12, sync-architecture
- Status: open

What happens: both modules promise that an action is validated before the job is queued, but the id is parsed with a bare `int()` before any check runs. Finance's `update`, `end` and `forget` posted without an `id` raise `KeyError`, and any of these posted with `"id": "abc"` raises `ValueError`, so the route answers 500 with a traceback in the log instead of the 400 the other checks produce. The pages always send integer ids, so only an agent or a hand-made request hits it.

Expected: a malformed id is a 400 naming the field, like every other validation failure in those routes.

Fix: one helper that reads `body.get("id")` and answers `HTTPException(400, "id required")` on a missing or non-integer value, used by both modules' checks.

### Recurring payments have no billing date

- Kind: gap
- Where: Finance requirement 1 (recurring subscriptions/payments); `finance_entries`, `app/modules/finance/routes.py`, `app/static/pages/finance.js`
- Found: 2026-09-12, the owner's request
- Status: in progress on branch `finance` (`../otto-finance`, one commit ahead of `main`)

What happens: a recurring entry records what it costs and how often, not when it bills, so what comes out this week is still a question for a bank statement.

Expected: one nullable `due_on` date (`YYYY-MM-DD`) on `finance_entries`, added by the module's `setup` on a database that predates it; the next occurrence projected on every read from that anchor and the cadence (a day past the end of a short month clamps to its last day), never stored; the date on recurring entries only; a new `action/due` verb rather than a field on `update`, so the amount history is untouched; LEFT stamps a dated recurring row with its next date and sorts the Recurring group by it; `today` keeps `updated_at` as its stamp; `finance_list` and `finance_get` carry `due_on` and `next_due`; no new tool, config key or setting.

Fix: merge branch `finance`; this entry goes and `## Built` gains the column, the verb, the projection and the page controls in that commit.
