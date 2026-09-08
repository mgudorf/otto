# Finance Plan

Status: planning, 2026-09-07.

Finance is the one place the owner writes down money facts by hand: account balances, recurring payments, investment holdings and budget caps. It shows what those add up to each month and lets the owner ask questions about them in plain language. Without it, this information stays scattered across statements and memory, and nothing in Otto can answer "what do I pay every month".

Version 0 is manual entry only: no bank, broker or price feed, no scheduled work, and an agent that only reads.

## Sources

| Source | Governs |
|---|---|
| `docs/ARCHITECTURE.md` Finance | scope: budget, recurring payments, investments as a manual proxy; agent answers natural language questions |
| `docs/ARCHITECTURE.md` Daemon, Mechanisms | user actions through `runner.run_action`, one transaction per write, failure is local, UI is a view |
| `docs/ARCHITECTURE.md` Module contract, Claude, Config | file layout, manifest, hooks, wire shape, tool servers, no new config keys |
| `docs/ARCHITECTURE.md` UI frame contract, Departures | hue `#7fb894`, order 5, banknote icon, tokens, row and chip specs; Finance split from the artboard's Money |
| `docs/design/Personal Dashboard App.dc.html` Money page | rail entry, LEFT chips and groups, item inspector actions, session placeholder and skills, header meta `128` |
| `app/modules/__init__.py`, `app/modules/memory/*`, `app/static/pages/memory.js` | the contract as implemented; Memory is the reference module |
| `app/static/shell.js`, `app/static/rows.js`, `app/modules/home/routes.py`, `app/api.py` | page registration, `Row` leading and `stampText` slots, Home hooks, shell and session routes |
| `tests/conftest.py`, `tests/test_app.py`, `tests/test_platform.py` | offline test pattern, end-to-end pattern, read-only agent proof |

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | One table `finance_entries` with `kind` in account, recurring, holding, budget | The four things ARCHITECTURE names share one shape: a name, an amount, an optional cadence, a note. One table is the cheapest to discard or replace |
| 2 | Amounts are integer cents in one implicit currency, shown with two decimals and no symbol | Float sums drift; the owner has one currency, so a currency knob would be decoration |
| 3 | Every capture and update appends a row to `finance_amounts` | A balance or holding value that is overwritten is gone for good; one insert per write keeps the trend the agent needs for "how has this changed" |
| 4 | Cadence is monthly, yearly or weekly, normalized to a monthly figure for totals | Subscriptions bill on all three; the owner thinks in months |
| 5 | LEFT groups by kind, the stamp slot shows the amount, the leading slot is an active or ended dot | Amount is what the owner scans for; the entry time is visible in the inspector |
| 6 | Search is `LIKE` over name and note, no paging | Tens of rows, typed by hand. FTS5 and paging would be structure without function |
| 7 | No schedules and no LLM task | Nothing arrives from outside to sync or annotate. The scheduler table shows no Finance rows, which is correct |
| 8 | The agent has read tools only; writes go through the page | Owner's ruling, 2026-09-08: agents are read-only for insight for now; writes are left to a future version. ARCHITECTURE also limits the Finance agent to questions, and a read-only agent makes the read/write split trivial to prove |
| 9 | Ended entries stay listed, struck through, at the foot of their group | A cancelled subscription is still a fact the agent may be asked about; `forget` exists for mistakes |

Rejected: a currency setting; a separate table per kind; FTS5 over entries; paging with `ui.page_size`; a nightly summary task; agent write tools (`finance_add`, `finance_update`); a document kind (documents belong to Business per the ARCHITECTURE split).

## Layout

| File | Change |
|---|---|
| `app/modules/finance/__init__.py` | new: `MANIFEST` with hue, icon, order 5, agent, no schedules |
| `app/modules/finance/schema.sql` | new: `finance_entries`, `finance_amounts` |
| `app/modules/finance/routes.py` | new: `left`, `blank`, `item/{id}`, `action/{verb}`, hooks `numbers`, `today`, `item`, `context` |
| `app/modules/finance/tools.py` | new: three read tools registered on both servers, nothing on `full` |
| `app/modules/finance/agent.md` | new: the agent's job |
| `app/static/pages/finance.js` | new: `load`, `meta`, `Left`, `Middle` |
| `app/static/shell.js` | import `pages/finance.js` and add it to `PAGES` |
| `tests/test_finance.py` | new: end-to-end and read-only proof |

No `tasks.py`: the manifest declares no schedules.

## Contract

Manifest: `name="finance"`, `title="Finance"`, `hue="#7fb894"`, `order=5`, icon copied from the artboard's Money rail entry (`<rect x="2" y="5" width="16" height="10" rx="1.5"></rect><circle cx="10" cy="10" r="2.5"></circle><path d="M5 8.5v3M15 8.5v3"></path>`), `schedules=()`, `agent=Agent(placeholder="Ask about money…", skills=("totals", "monthly", "history"), read_tools=("finance_list", "finance_get", "finance_totals"), write_tools=())`.

Routes, all under `/api/finance`:

| Route | Wire shape |
|---|---|
| `GET left?query=&chip=All` | `{groups: [{label: "Accounts", count, rows: [{id, module: "finance", text: name, stamp: updated_at, stampText: "1,234.00" or "15.49 /mo", leading: {dot: hue or "transparent"}, done: ended}]}], chips: ["All","Accounts","Recurring","Holdings","Budgets"], chip}`. Groups in kind order; ended rows last in each group; `query` matches name or note |
| `GET blank` | `{kinds, cadences, counts: {kind: n}, totals: {accounts, holdings, monthly_recurring, monthly_budget}}`, totals in cents over active entries |
| `GET item/{id}` | `{id, module, kind, name, amount, cadence, note, text, created_at, updated_at, ended_at, history: [{ts, amount}], actions}`; `text` is the name, amount with cadence, and note on separate lines; actions are `update` (primary, needs `amount`), `end` (hidden once ended), `forget` (confirm) |
| `POST action/capture` | body `{kind, name, amount, cadence?, note?}`; `amount` is a decimal string or number, parsed with `Decimal` to cents; cadence required for recurring and budget, ignored otherwise; returns `{id}` |
| `POST action/update` | body `{id, amount, note?}`; returns `{id, amount}` |
| `POST action/end` | body `{id}`; sets `ended_at`; returns `{id}` |
| `POST action/forget` | body `{id}`; deletes the entry and its history; returns `{id}` |

Every action runs through `runner.run_action("finance.<verb>", "finance", "finance", fn)` and writes inside one `ctx.commit()`. Events: `captured`, `updated`, `ended`, `forgot`, with the entry id as `ref`.

Hooks: `numbers` returns the active entry count with label `records`; `today` returns entries created or updated during the local day; `item` is the inspector shape above; `context` renders the four totals and every active entry as `id kind name amount cadence` lines, then ended entries in one line of names.

MCP tools, read server and full server both: `finance_list(kind=None, include_ended=False)`, `finance_get(id)` with history, `finance_totals()`. No write tools.

Agent: answers questions about the owner's money from the Current state block and the three read tools. Totals, what is due monthly, which holding changed most, what a budget leaves after recurring payments. It quotes amounts exactly as stored and never estimates prices or balances the owner has not entered. It cannot add or change anything and says so when asked.

Page `finance.js`: `load` fetches `left` and `blank`; `meta` is the active count. LEFT: search, chips, one group per kind using `GroupHeader` and `Row`. MIDDLE blank: four numbers in the Home number style (accounts, holdings, monthly recurring, monthly budget), then the capture form: kind chips, name, amount, cadence chips shown for recurring and budget, note, `Save`, Ctrl+Enter. MIDDLE selected: `Inspector` with an amount input and `Update` as the primary action, the amount history as compact mono rows, `End`, `Forget`, `Send to session`.

Departures from the artboard, each because the artboard's Money page is a document list that ARCHITECTURE moved to Business:

| Artboard | Plan |
|---|---|
| Chips All, Accounts, Plans, Documents | All, Accounts, Recurring, Holdings, Budgets |
| Rows grouped by day with an `ext` leading slot and a time stamp | grouped by kind, active dot, amount in the stamp slot |
| Item actions Open, Summarize, Share | Update, End, Forget |
| Skills summarize, extract, reconcile, plan | totals, monthly, history |
| Title Money, meta `128` | Title Finance, meta is the active count |
| Blank state unspecified | totals and capture form |

## Data

`schema.sql`:

| Table | Columns |
|---|---|
| `finance_entries` | `id INTEGER PRIMARY KEY`, `kind TEXT CHECK (kind IN ('account','recurring','holding','budget'))`, `name TEXT NOT NULL`, `amount INTEGER NOT NULL` (cents), `cadence TEXT CHECK (cadence IN ('monthly','yearly','weekly'))` nullable, `note TEXT`, `created_at`, `updated_at`, `ended_at` (UTC ISO); index on `updated_at` |
| `finance_amounts` | `entry_id REFERENCES finance_entries(id) ON DELETE CASCADE`, `ts TEXT`, `amount INTEGER`; index on `(entry_id, ts)` |

Cursors: none.

External clients: none. The only system is the store. Scheduled work: none. User actions write through `ctx.commit()` inside `run_action`; the agent reads through the two MCP servers. The split is proven by `test_finance_agent_reads_only`: build the app, list tools on `mcp_read` and `mcp_full`, assert the Finance tools on `full` equal those on `read`, and assert `MANIFEST.agent.write_tools == ()`.

## Phases

| Phase | Builds | Usable result |
|---|---|---|
| 1 | schema, manifest, routes and hooks, `finance.js`, shell registration, `test_finance_end_to_end` | Finance appears in the rail. The owner enters accounts, subscriptions, holdings and budgets, sees monthly recurring and budget totals with account and holding sums, updates a value and sees its history, ends or forgets an entry. Home shows the record count and today's changes |
| 2 | `tools.py`, `agent.md`, `context` hook, `test_finance_agent_reads_only` | The session pane answers "what do I pay monthly", "what is my biggest holding", "how much of the food budget is left after recurring" from the owner's records, and cannot write |

## Tests

- `test_finance_end_to_end`: capture one entry per kind (yearly 120.00 recurring), `left` groups by kind and honors chip and query, `blank.totals.monthly_recurring == 1000`, `item` after `update` shows two history rows, `end` marks `done` in `left`, Home `numbers` and `left` include Finance, `forget` returns 404 afterwards, events read `forgot, ended, updated, captured`.
- `test_finance_agent_reads_only`: as described under Data.
- Amount parsing rejects a non-decimal string with 400; one assertion inside the end-to-end test.
- No LLM touchpoint is added; `no_real_claude` in `conftest.py` keeps the suite offline.

## Manifest

Present:

| Item | Version / location | Needed for |
|---|---|---|
| Python | 3.14.7, `.venv/Scripts/python.exe` | everything |
| fastapi, uvicorn, mcp, httpx, pytest | 0.141.1, 0.52.4, 2.2.0, 0.28.1, 9.1.1 installed in `.venv` | routes, tool servers, tests |
| SQLite | 3.50.4 via stdlib `sqlite3` | schema |
| `decimal` | stdlib | amount parsing |
| Preact, htm, fonts | `app/static/vendor/` | page |
| Test suite | 16 passed today with `.venv/Scripts/python.exe -m pytest -q` | baseline |

Missing: nothing. No package is added.

Needs you: nothing.

Verify:

| Check | Command |
|---|---|
| Suite still green in the worktree | `.venv/Scripts/python.exe -m pytest -q` |
| Finance loads in the registry | `.venv/Scripts/python.exe -c "from app.modules import Registry; r=Registry(); r.load(); print(r.errors, 'finance' in r.modules)"` |
| Rail shows Finance at order 5 | `python -m app` then `GET /api/shell` lists `finance` between `memory` and `graph` |

## Worktree

```
git worktree add ../otto-finance -b finance
```

Work in `../otto-finance`. When the branch is merged to `main`, run `/sync-architecture`.

## Pending decisions

None. The agent-write question was settled read-only on 2026-09-08 (Decision 8).
