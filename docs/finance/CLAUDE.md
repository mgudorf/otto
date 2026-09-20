# Finance

1. General place for me to organize important information regarding anything money related; budget/recurring subscriptions/payments, stock/investment info (not direct link to account, just a proxy with manual inputs)
2. Agent should be able to be asked general questions regarding finances; i.e. natural language queries. 

## Built

| Piece | Current state |
|---|---|
| Tables | `finance_entries(kind account\|recurring\|holding\|budget, name, amount in cents, cadence monthly\|yearly\|weekly, note, due_on YYYY-MM-DD or null, ended_at)`, `finance_amounts` (every value the entry has held). The package's `setup` adds `due_on` to a database created before the column existed |
| Routes | `left` (every entry as a ROW, grouped by kind, active first then by name, the Recurring group soonest due first then undated then ended; the page narrows it by chip and by the search bar's tokens), `blank` (the four totals, the kinds and cadences the capture box offers, and the word each kind goes by, which is where the page's chips and group headers get their labels), `item/{id}` (the ROW plus the anchor `due_on` the date box edits, the `HISTORY` most recent amounts, newest first, and the actions `update` as `Update amount` and primary, `due` as `Set date` on a recurring entry, `end` while active, `forget` with confirm and marked `removes`), `action/{capture\|update\|due\|end\|forget}`, each validated before the job is queued: `cadence` is required for recurring and budget and dropped otherwise, amounts parse with commas and round half-up to cents, `due_on` is kept on capture for recurring only and `due` refuses any other kind (400), a blank date clears it, and `update` is the only path that appends to `finance_amounts`; a missing or non-integer `id` is a 400 naming the field (`app.modules.int_id`, shared with Second Brain) |
| ROW | `title` the name, `when` the last touch, `fixed` the kind, `tags` the owner's from `app_tags`, and the extras the page reads: `kind`, `amount` in cents, `cadence`, `due` the next occurrence, `ended`, `note` (it rides the row so that typing a word from a note finds its entry) |
| Due date | `due_on` is the one date the owner entered; `next_due` is never stored but projected on every read as the first occurrence on or after today, stepped from the anchor by the cadence (weekly by weeks; monthly and yearly by months, a day past a short month's end clamped to its last day, measured from the anchor so it clamps once). An ended or undated entry has none |
| Hooks | `numbers` (active records), `today` (entries touched in the local day), `rows` (every entry, most recently touched first, which is what `/api/items`, the tag page, Home's Recent and the Graph read), `item`, `context` (the four totals, every active entry with its next due where dated, the ended names) |
| Tools | read only: `finance_list` and `finance_get` carry `due_on` and `next_due`, `finance_totals`. The manifest declares no write tools |
| Totals | recurring and budget amounts normalize to a month as yearly / 12 and weekly x 52 / 12; accounts and holdings sum as entered |
| Page | One card per kind, in the order and under the words `blank` sends, with those same words as the chips beside All narrowing to one kind, and the header carrying the four totals and a `+`; the page holds no list of kinds of its own. A row is its title and tags, the cadence, the date (the next occurrence, or the end date once ended, tinted danger once it has passed) and the amount on the right, tabular; an ended row is struck through and dimmed, and a hovered row offers Update and Tag. The `+` opens the capture box over the list, empty every time it opens: one named row per field — Kind, Name, Amount, Cadence on a recurring or budget entry, Date on a recurring one, Note — and nothing that says what to type; Enter or the check saves, Esc closes, and a missing name or an amount that will not parse comes back as the daemon's own message. Selecting a row opens the entry — title, the amount large, the date, tags, cadence, note, the amounts it has held by date, then the buttons `item.actions` names: `Update amount` and `Set date` open a one-box popup over the button — an amount left blank or one that will not parse comes back as the daemon's own message, the way the capture box's does — `End` is a plain button, `Forget` is red and asks first |
| Departures | the artboard's Money page is a document list: chips are the four kinds, rows group by kind rather than day. A typed date is `MM-DD-YYYY`, converted before it is sent; an unfinished one is refused with a toast rather than sent |

## Patches

### Ending an entry is a one-way door

- Kind: defect
- Where: `app/modules/finance/routes.py`, the `end` action in `item()` and `_end`; `app/static/pages/finance.js` `actionBtn`
- Found: 2026-09-20, the review of the ported Finance page
- Status: open

What happens: `End` runs on one click — the action carries neither `confirm` nor `removes`, so the pane fires it straight away — and nothing can take it back. `_update` and `_due` never clear `ended_at` and no action sets it to null, so an entry ended by a misclick can only be forgotten and captured again, which loses its amount history.

Expected: an irreversible change either asks first or can be undone.

Fix: your call between the two, which is why it is filed rather than fixed. Either mark the `end` action `confirm` (`"End this entry?"`), the way `forget` already guards itself, or add a `resume` action that clears `ended_at` and offer it on an ended entry — that second one also decides whether the entry's amount rejoins the totals and its next due starts projecting again.
