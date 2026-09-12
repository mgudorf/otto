# Finance Dates Plan

Status: planning, 2026-09-12.

A recurring payment in Finance says what it costs and how often, but not when. The owner cannot see what is charged next, only what is charged eventually, so "what comes out this week" is still a question for a bank statement. This item adds one date to a recurring entry: the day it bills. From that date and the cadence Finance works out the next occurrence, shows it on the row and in the inspector, orders the recurring list by what is soonest, and hands it to the agent.

Nothing else changes. Accounts, holdings and budgets are untouched, no new page structure, no schedule, no new config key, and the agent still only reads.

## Sources

| Source | Governs |
|---|---|
| `docs/ARCHITECTURE.md` Finance, Built | the tables, routes, hooks, tools and page this item extends |
| `docs/ARCHITECTURE.md` Module contract | `schema.sql` only creates, so a column on an existing table is the module's `setup`; hook names; the LEFT wire shape |
| `docs/ARCHITECTURE.md` Daemon, Mechanisms | user actions through `runner.run_action`, one transaction per write, the UI is a view |
| `docs/ARCHITECTURE.md` Config | boot keys vs the `settings` table; this item adds neither |
| `docs/ARCHITECTURE.md` UI frame contract | row `stamp` and `stampText` slots, `05 Sep` stamp format, chip and input specs, hue `#7fb894` |
| `docs/design/Personal Dashboard App.dc.html` Money page (`isBiz`, `bizChips`, `bgp`) | the artboard row: an `ext` slot, a bar and a time stamp; no date field anywhere |
| `app/modules/finance/{__init__.py, schema.sql, routes.py, tools.py, agent.md}` | what exists today |
| `app/modules/education/__init__.py` | the column-migration pattern this item copies |
| `app/modules/home/routes.py` | why the `today` hook keeps its own stamp |
| `app/static/pages/finance.js`, `app/static/rows.js` | the capture form, the inspector, `stamp()` |
| `tests/test_finance.py` | the assertions that must stay green |

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | One nullable column `due_on` on `finance_entries`, a plain `YYYY-MM-DD` date | A bill lands on a calendar day, not an instant; storing it as a UTC timestamp like the other columns would let a payment on the 1st render as the 31st. Nullable because every entry that exists today has no date and the owner may not know one |
| 2 | The date is an anchor, not a countdown: one occurrence, past or future, and the cadence does the rest | The owner knows "it bills on the 15th". A stored next-due would need something to advance it, which means a scheduled task for a fact arithmetic already knows |
| 3 | The next occurrence is computed on every read, never stored | Nothing can go stale, nothing to migrate, and no row is written at midnight. It is a pure function of the anchor, the cadence and today |
| 4 | Every step is measured from the anchor, and a day past the end of a short month clamps to that month's last day | A 31st anchor must give 30 Apr and 28 Feb without the entry permanently sliding to the 28th, which is what stepping from the previous result would do |
| 5 | The date belongs to `recurring` only; it is ignored on the other three kinds | A budget is a cap over a period and an account balance is a standing figure; neither is an event with a day. `cadence` is already ignored the same way |
| 6 | A new verb `action/due`, rather than a field on `action/update` | `update` exists to record a new amount and appends a row to `finance_amounts`. Changing a date is not an amount change and must not leave a duplicate figure in the history |
| 7 | LEFT puts the next due date in the existing `stamp` slot for a dated recurring row, and the Recurring group sorts by it | The slot already renders `05 Oct`; the date answers the question the row is being scanned for. Undated entries keep the touch time and sort last |
| 8 | The `today` hook keeps `updated_at` as its stamp | Home's group is what changed today; a future date in a list of today's activity reads as an error. Owner's ruling, 2026-09-12: upcoming payments stay on the Finance page |
| 9 | The three existing tools carry the two new fields; no fourth tool | `finance_list` and `finance_get` already return the whole row. A tool per field is structure without function |
| 10 | No config key and no live setting | The item has no window, horizon or threshold to tune. Nothing is hard-coded because there is no value to hide |

Rejected: a look-ahead `Review` group on Home behind a `due_within_days` knob (the queue seam is for rows waiting on a yes or no, and the owner chose the Finance page); a fifth number in the totals strip; a stored `next_due` column with a nightly task to roll it; dates on budgets; a separate `finance_due` tool; making `amount` optional on `action/update`; a day-of-month integer instead of a date (it cannot express weekly or yearly).

## Layout

| File | Change |
|---|---|
| `app/modules/finance/schema.sql` | add `due_on TEXT` to `finance_entries`, so a fresh database has it |
| `app/modules/finance/__init__.py` | add `setup(config)`: the column on a database that predates it |
| `app/modules/finance/routes.py` | `next_due`, date validation in `_check_capture`, `_check_due` and `_due`, `due` in `CHECKS`/`ACTIONS`, `_row(r, due=False)`, the Recurring sort in `_group_by_kind`, `due_on`/`next_due` and the `due` action in `item`, the projection in `context` |
| `app/modules/finance/tools.py` | `next_due` on the rows `finance_list` and `finance_get` return |
| `app/modules/finance/agent.md` | three lines: what the anchor is, that the next date is projected, that it cannot set one |
| `app/static/pages/finance.js` | a date input in the capture form when the kind is recurring, and in the inspector with `Set date` |
| `tests/test_finance.py` | `test_finance_due_dates`, `test_finance_due_column_added` |

No `tasks.py`: the manifest still declares no schedules.

Shared seams: none. `app/config.py`, `config.toml`, `shell.js` and the contract docstring are untouched, so this branch conflicts with nothing outside `app/modules/finance/` and its test file.

## Contract

Manifest: unchanged except that `__init__.py` gains `setup`. Name, title, hue, icon, order 5, `schedules=()`, and `agent.write_tools=()` all stay as they are.

`next_due(row, today)` in `routes.py`: `None` when the entry has no `due_on`, no cadence, or an `ended_at`; otherwise the first occurrence on or after `today`, as a `YYYY-MM-DD` string.

| Cadence | Step | Clamp |
|---|---|---|
| weekly | the anchor plus whole weeks | none; the weekday is fixed |
| monthly | the anchor's day in each later month | to the month's last day (31 → 30 Apr, 28 or 29 Feb) |
| yearly | the anchor's month and day in each later year | 29 Feb → 28 Feb outside a leap year |

Routes under `/api/finance`:

| Route | Change |
|---|---|
| `GET left` | a dated recurring row's `stamp` is its next due date; the Recurring group orders by next due, undated entries after dated ones, ended entries still last. Every other group is unchanged |
| `GET blank` | unchanged |
| `GET item/{id}` | adds `due_on` and `next_due`; a dated entry's `text` gains a third line `next 05 Oct`; `actions` gains `{verb: "due", label: "Set date"}` for a recurring entry, after `update` |
| `POST action/capture` | accepts `due_on` when `kind` is recurring, optional, ignored otherwise. A value `date.fromisoformat` rejects is a 400 |
| `POST action/due` | new: body `{id, due_on}`; 400 unless the entry is recurring; an empty or missing `due_on` clears it; returns `{id, due_on, next_due}` |

`action/due` runs through `runner.run_action("finance.due", "finance", "finance", fn)` inside one `ctx.commit()`, writes `updated_at`, and emits the event `dated` with the entry id as `ref` and the text `<name>: 15 of each month` or `<name>: date cleared`. It never touches `finance_amounts`.

Hooks: `numbers` unchanged; `today` unchanged, keeping `updated_at` as the stamp per decision 8; `item` as above; `context` appends ` next <date>` to a dated recurring line, so the state block reads `12 recurring Netflix: 15.49 /mo next 2026-10-15`.

Tools: `finance_list` and `finance_get` return `due_on` and `next_due` on every row; no signature changes, no new tool, nothing on `full` that is not on `read`.

Agent: unchanged job, plus the date. It can say when a payment is next due and what falls in a range, and must say that a next date is projected from the owner's anchor rather than entered. It still cannot set, change or clear one, and says the Finance page does that.

Page: the capture form shows a `due date` input beside the cadence chips when the kind is `recurring`, placeholder `YYYY-MM-DD`, empty allowed. The inspector shows `next 05 Oct` under the amount for a dated recurring entry, a date input pre-filled with `due_on`, and `Set date` as a secondary action that posts `action/due`; clearing the input and pressing it clears the date.

Departures from the artboard, in addition to the four the Finance section already records:

| Artboard | Plan |
|---|---|
| The Money row's stamp is a file time | a dated recurring row stamps its next due date, in the same mono 13px slot and `05 Oct` format |
| No date control anywhere on the Money page | a date input in the capture form and the inspector, built from the existing input style |

## Data

`schema.sql` gains one column:

| Table | Column |
|---|---|
| `finance_entries` | `due_on TEXT` — the anchor date, `YYYY-MM-DD`, null unless the entry is recurring and the owner gave one |

No new table, no index (tens of rows, and the projection happens in Python). `finance_amounts` is untouched.

Migration: `Store.migrate` only creates, so the live database keeps the nine columns it has today. `setup(config)` opens `config.data.db`, reads `PRAGMA table_info(finance_entries)`, and adds `due_on` when it is absent — the same shape as `app/modules/education/__init__.py`. It is a no-op on a fresh database and on every boot after the first.

Cursors: none. External clients: none; the store is the only system, so there is no read/write client split to add. The existing `test_finance_agent_reads_only` still proves the agent's half, and this item adds no tool to `full`.

## Phases

| Phase | Builds | Usable result |
|---|---|---|
| 1 | the column, `setup`, `next_due`, capture and `due` actions, `item`, the LEFT stamp and sort, `finance.js`, `test_finance_due_dates`, `test_finance_due_column_added` | The owner enters a subscription with the day it bills, sees its next date on the row and in the inspector, reads the Recurring group top-down as what is coming, and changes or clears a date without touching the amount |
| 2 | `tools.py`, `agent.md`, the `context` line | The session pane answers "what comes out this week", "when is the next charge", "what do I pay before the 20th" from the owner's own dates, and says which figures are projected |

## Tests

- `test_finance_due_dates`: capture a monthly recurring anchored on a 31st and assert the next due clamps in a 30-day month and in February; a weekly and a yearly entry project correctly; `action/due` sets, changes and clears; an entry with no date has `next_due` of `None`; an ended entry has `next_due` of `None`; `action/due` on an account is 400 and a malformed `due_on` on capture is 400; `left` stamps the dated recurring row with its next due and orders the Recurring group by it; the event reads `dated`.
- `test_finance_due_column_added`: apply the nine-column v0 `finance_entries` to a temporary database, run `setup`, assert `due_on` is there, run `setup` again and assert it still is and nothing raised.
- `next_due` takes today as an argument, so no test depends on the clock.
- The two existing Finance tests stay unchanged and green; no LLM touchpoint is added and the suite stays offline.

## Manifest

Present, verified on this machine today:

| Item | Version / location | Needed for |
|---|---|---|
| Python | 3.14.7, `.venv/Scripts/python.exe` | everything |
| `datetime` (`date`, `timedelta`, `calendar.monthrange`) | stdlib, `date(2026,1,31)` constructed today | the projection and its clamp |
| fastapi, mcp, pytest | 0.141.1, 2.2.0, 9.1.1 in `.venv` | the route, the tools, the tests |
| SQLite | 3.50.4 via stdlib `sqlite3`; `ALTER TABLE ADD COLUMN` is supported | the migration |
| `data/otto.db` | `finance_entries` has the nine v0 columns and zero rows | the migration runs, and no live data is at risk |
| Preact, htm, fonts | `app/static/vendor/` | the date inputs |
| Test suite | 63 passed today, `.venv/Scripts/python.exe -m pytest -q` | baseline |

Missing: nothing. No package is added.

Needs you: nothing.

Verify:

| Check | Command |
|---|---|
| Suite green in the worktree | `.venv/Scripts/python.exe -m pytest -q` |
| The column reaches the live database | `python -m app`, then `.venv/Scripts/python.exe -c "import sqlite3; print([r[1] for r in sqlite3.connect('data/otto.db').execute('PRAGMA table_info(finance_entries)')])"` |
| Finance still loads | `.venv/Scripts/python.exe -c "from app.modules import Registry; r=Registry(); r.load(); print(r.errors, 'finance' in r.modules)"` |

## Worktree

```
git worktree add ../otto-finance -b finance
```

Work in `../otto-finance`. Run `git merge main` in the branch before merging it back. When the branch is merged to `main`, run `/sync-architecture`.

## Pending decisions

None. Both open questions were settled on 2026-09-12: the landed v0 plan is replaced by this file, and upcoming payments stay on the Finance page (decision 8).
