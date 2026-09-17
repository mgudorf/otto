# Finance

1. General place for me to organize important information regarding anything money related; budget/recurring subscriptions/payments, stock/investment info (not direct link to account, just a proxy with manual inputs)
2. Agent should be able to be asked general questions regarding finances; i.e. natural language queries. 

## Built

| Piece | Current state |
|---|---|
| Tables | `finance_entries(kind account\|recurring\|holding\|budget, name, amount in cents, cadence monthly\|yearly\|weekly, note, due_on YYYY-MM-DD or null, ended_at)`, `finance_amounts` (every value the entry has held). The package's `setup` adds `due_on` to a database created before the column existed |
| Routes | `left` (query, chips All/Accounts/Recurring/Holdings/Budgets; rows ordered active first then by name, the amount as `stampText`, a dated recurring row reading `amount · 05 Oct` and the Recurring group sorted soonest due first, undated next, ended last), `blank` (totals, kinds, cadences, counts), `item/{id}` with the amount history and `next_due` (`update` primary, `due` as `Set date` on a recurring entry, `end` while active, `forget` with confirm, marked `removes`), `action/{capture\|update\|due\|end\|forget}`, each validated before the job is queued: `cadence` is required for recurring and budget and dropped otherwise, amounts parse with commas and round half-up to cents, `due_on` is kept on capture for recurring only and `due` refuses any other kind (400), a blank date clears it, and `update` is the only path that appends to `finance_amounts` |
| Due date | `due_on` is the one date the owner entered; `next_due` is never stored but projected on every read as the first occurrence on or after today, stepped from the anchor by the cadence (weekly by weeks; monthly and yearly by months, a day past a short month's end clamped to its last day, measured from the anchor so it clamps once). An ended or undated entry has none |
| Hooks | `numbers` (active records), `today` (entries touched in the local day, stamped by `updated_at`), `item`, `context` (the four totals, every active entry with its next due where dated, the ended names) |
| Tools | read only: `finance_list` and `finance_get` carry `due_on` and `next_due`, `finance_totals`. The manifest declares no write tools |
| Totals | recurring and budget amounts normalize to a month as yearly / 12 and weekly x 52 / 12; accounts and holdings sum as entered |
| Page | LEFT: search, kind chips, one group per kind with the amount (and the next date on a dated recurring row) in the stamp slot and a dot for active, ended entries last in their group and struck through; MIDDLE blank: the totals and the capture form, which shows a `due date` box when the kind is recurring; MIDDLE selected: the entry, a `new amount` box, a `due date` box on a recurring entry (Enter or `Set date` posts it, blank clears), its amount history, `Update`, `End`, `Forget` |
| Departures | the artboard's Money page was a document list, now Business: chips are the four kinds, rows group by kind rather than day, item actions are `Update` / `Set date` / `End` / `Forget` |

## Patches

### A missing or non-numeric `id` on an action is a 500, not a 400

- Kind: bug
- Where: `app/modules/finance/routes.py` `_check_update` and `_check_id` (`int(body["id"])`)
- Found: 2026-09-12, sync-architecture; 2026-09-13, the dismissal change found the same in Business and Social, retired into Newsfeed on 2026-09-16
- Status: open

What happens: Finance promises that an action is validated before the job is queued, but the id is parsed with a bare `int()` before any check runs. Its `update`, `end` and `forget` posted without an `id` raise `KeyError`, and any of these posted with `"id": "abc"` raises `ValueError`, so the route answers 500 with a traceback in the log instead of the 400 the other checks produce. The page always sends integer ids, so only an agent or a hand-made request hits it. Second Brain and Newsfeed are clear of it: `_suggestion_id` answers 404 on anything that is not `s<digits>`, and Newsfeed's `_ref` answers 400 on anything that is not an integer or `s<digits>`.

Expected: a malformed id is a 400 naming the field, like every other validation failure in those routes.

Fix: one helper that reads `body.get("id")` and answers `HTTPException(400, "id required")` on a missing or non-integer value, used by every module's checks.
