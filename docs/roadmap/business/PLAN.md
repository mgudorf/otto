# Business Plan

Status: planning, 2026-09-07.

Business is where the owner keeps what they are pursuing professionally: plans, the people and events around them, the documents behind them, and a nightly-found queue of leads (openings, calls, news) worth a yes or no. Without it those live in browser tabs and chat threads, and nothing looks for the next relevant thing while the owner sleeps.

## Sources

| Source | Governs |
|---|---|
| `docs/ARCHITECTURE.md` Business | the three goals: house plans/networking/documents; find and track relevant items and realistic openings, automated |
| `docs/ARCHITECTURE.md` Daemon, Mechanisms, Config, Claude, Module contract, Platform tables | task shape, `ctx.commit`, `ctx.run_task` as the only LLM path for tasks, budget window, wire shapes, hooks |
| `docs/ARCHITECTURE.md` Frame contract, Departures | hue `#c98ba8`, briefcase icon, rail order 6; Business split from the artboard's Money |
| `docs/ARCHITECTURE.md` Home page | numbers per module, today rows, review queue for nightly finds |
| `docs/design/Personal Dashboard App.dc.html` `isBiz` block (lines 135-148), `bgp` groups, `sk === 'bz'` inspector | LEFT chips, rows with an `ext` leading slot and a stamp, inspector with primary `Open` and actions `Summarize`, `Share` |
| `app/modules/memory/*`, `app/static/pages/memory.js` | the reference module: routes, actions through the runner, hooks, tools split, capture box |
| `app/modules/__init__.py`, `app/runner.py`, `app/claude.py`, `app/config.py`, `config.toml` | Manifest, JobContext (`store`, `config`, `commit`, `run_task`), `READ_BUILTINS` includes WebSearch and WebFetch, typed config |
| `tests/conftest.py`, `tests/test_app.py`, `tests/test_platform.py` | the spawn mock and the end-to-end pattern to copy |

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | One table `business_items` with kinds plan, person, event, document, lead | One LEFT query, one search, one inspector, one `item` hook. A lead is a row with a status, not a second module |
| 2 | Documents are files the owner drops in `data/workspace/business/`; a 15-minute task indexes the folder into document rows | Claude's Read tool is confined to the workspace, so the agent can open them; Explorer already handles copying files better than any upload box |
| 3 | The nightly `scout` task is a read-only LLM run using the CLI's built-in WebSearch, seeded by the owner's plans, writing leads with `INSERT OR IGNORE` on `(kind, ref)` | Uses the budget and window that already exist; no search API, no key, no charge. Re-running never duplicates |
| 4 | Leads are a review queue: Accept and Dismiss on the blank state, surfaced on Home through `today` | The Home section asks for exactly this: nightly finds queued until agreed or disagreed with |
| 5 | Event dates stay in the text | Same rule as Memory; a `when_at` column with parsing is structure the owner did not ask for |
| 6 | Search is `LIKE`, not FTS5 | Hundreds of rows at most; the FTS trigger set is cost with no gain here |
| 7 | One knob, `[business] leads_per_run` in `config.toml` | A cap is required by the Home section; it belongs in config, not in code. Everything else is derived from existing config |
| 8 | Hue `#c98ba8`, briefcase icon, order 6 | Already fixed in ARCHITECTURE; the artboard has no Business entry |

Rejected: storing business items as tagged memories (entangles two modules and breaks the replace-a-module seam); a separate leads table; an upload route and file store; a document `Summarize` action (the session pane already does this through `Send to session`).

## Layout

| File | Change |
|---|---|
| `app/modules/business/__init__.py` | `MANIFEST` |
| `app/modules/business/schema.sql` | `business_items` and its unique index |
| `app/modules/business/tasks.py` | `index_documents(ctx)`, `scout(ctx)` |
| `app/modules/business/routes.py` | `left`, `blank`, `item/{id}`, `action/{verb}`; hooks `numbers`, `today`, `item`, `context` |
| `app/modules/business/tools.py` | `register(read, full, store)` |
| `app/modules/business/agent.md` | the agent's job |
| `app/static/pages/business.js` | `load`, `meta`, `Left`, `Middle` |
| `app/config.py`, `config.toml` | `Business(leads_per_run)` dataclass and `[business]` section, required at boot like every other key |
| `tests/test_business.py` | the tests below |

## Contract

Manifest: `name="business"`, `title="Business"`, `hue="#c98ba8"`, `order=6`, icon (briefcase, 20x20, stroke 1.5): `<rect x="3" y="7" width="14" height="10" rx="2"></rect><path d="M7 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M3 11h14"></path>`. Agent placeholder `Ask business…`, skills `recall`, `add`, `scout`, `summarize`.

| Schedule | every | resource | llm | Does |
|---|---|---|---|---|
| `index_documents` | 15m | `business` | no | mirrors `data/workspace/business/` into document rows; creates the folder if missing |
| `scout` | 24h | `business` | yes | one budgeted run: searches the web for leads matching the owner's plans, inserts up to `leads_per_run` new ones |

| Route | Wire |
|---|---|
| `GET /api/business/left?query&chip&page` | LEFT shape; chips `All, Plans, People, Events, Documents, Leads`; rows grouped by day, `leading` is `{ext}` for documents and `{kind}` otherwise, `done` for dismissed leads; `showing`, `more` |
| `GET /api/business/blank` | `{kinds: [plan, person, event], counts: {kind: n}, leads: [open leads]}` |
| `GET /api/business/item/{id}` | the row plus `actions`: document `Open` (primary); lead `Accept` (primary), `Dismiss`, `Open` (`href`); plan, person, event `Forget` (confirm) |
| `POST /api/business/action/capture` | `{kind, text, ref?}` → `{id}`; through `run_action`, resource `business` |
| `POST /api/business/action/forget` | `{id}` → `{id}` |
| `POST /api/business/action/lead` | `{id, status: accepted or dismissed}` → `{id, status}` |
| `POST /api/business/action/open` | `{id}` → `os.startfile` on a document's path; the daemon launches the viewer, the page never handles a path |

| MCP tool | Server | Does |
|---|---|---|
| `business_search(query, kind?, limit)` | read + full | `LIKE` search, newest first |
| `business_get(id)` | read + full | one row |
| `business_leads(status)` | read + full | leads by status; checked before proposing anything |
| `business_add(kind, text, ref?)` | full | capture with the owner's exact words |
| `business_lead(text, ref, why)` | full | record a lead found in a session so `scout` never repeats it |

Hooks: `numbers` → `{value: open leads, label: "leads"}`; `today` → leads found today and items captured today; `item` as above; `context` → counts per kind, every plan in full (they are short and they steer the agent), open leads, the document list with paths.

The agent keeps the owner's professional picture straight: it recalls plans, people, events and leads by tool, reads documents from the workspace on request, drafts summaries and next steps from them, and when asked to scout it searches the web the same way the nightly task does and records each lead once. It never edits a plan's words, never sends anything anywhere, and says so when asked to.

Departures from the artboard: chips are `Plans, People, Events, Documents, Leads` instead of `Accounts, Plans, Documents` (accounts are Finance); inspector actions `Summarize` and `Share` are dropped (summarize is `Send to session`; there is nothing to share to); the blank state (capture box and lead queue) is unspecified there; hue and icon come from ARCHITECTURE.

## Data

| Table | Columns |
|---|---|
| `business_items` | `id`, `kind` CHECK IN (plan, person, event, document, lead), `text` NOT NULL, `ref` (URL for a lead, absolute path for a document), `why` (scout's one-line reason, leads only), `status` NOT NULL DEFAULT open CHECK IN (open, accepted, dismissed), `created_at`, `updated_at`; unique index on `(kind, ref) WHERE ref IS NOT NULL`; index on `created_at` |

| Cursor | Meaning |
|---|---|
| `business.scout` | timestamp of the last completed scout, written in the same transaction as its leads; informational, since leads are keyed by `ref` |
| `index_documents` | none; each run is a full rescan that upserts present files and deletes document rows whose file is gone, in one transaction |

| External system | Scheduled tasks get | User actions get | Proof |
|---|---|---|---|
| Web (search, fetch) | `ctx.run_task` on the read server with the CLI's read-only built-ins | the session pane (`session_turn`) | `test_tasks_never_reach_interactive_claude` (existing) plus `test_scout_inserts_capped_and_idempotent` mocking `run_task` |
| Local files | `index_documents` reads the folder only | `action/open` launches a viewer; nothing is written to the folder by the app | `test_index_documents_mirrors_folder` |

## Phases

| Phase | Builds | Usable result |
|---|---|---|
| 1 Catalog | schema, manifest, `left`, `blank`, `item`, `capture`, `forget`, all four hooks, the page with chips, capture box and inspector | Owner captures plans, people and events, searches them, sees today's captures on Home |
| 2 Documents and agent | `index_documents`, `open` action, `ext` rows, `agent.md`, `tools.py` | Files dropped in the folder appear in LEFT and open on click; the session answers from plans and reads documents |
| 3 Scout | `[business]` config, `scout` task, lead rows, `lead` action, `business_lead` tool, leads in `blank` and `today` | Each night inside the window Otto finds up to `leads_per_run` leads; the owner accepts or dismisses them from Business or Home |

## Tests

- `test_business_end_to_end`: capture a plan and a person through the client, list, select, forget; copy of `test_memory_end_to_end`.
- `test_index_documents_mirrors_folder`: two files in a tmp workspace produce two document rows with `ext`; deleting one and rerunning removes its row.
- `test_scout_inserts_capped_and_idempotent`: `run_task` mocked to return five leads with one duplicate `ref`; `leads_per_run=3` inserts three, a second run inserts none, no plans returns `Skipped`.
- `test_registry_loads_real_modules` (existing) covers the manifest and prompt file.
- Everything offline; the spawn seam raises on a real invocation as today.

## Manifest

Present

| Item | Version / location | Needed for |
|---|---|---|
| Python | 3.14.7, `.venv/Scripts/python.exe` | everything |
| fastapi, uvicorn, mcp, httpx, pytest | 0.141.1, 0.52.4, 2.2.0, 0.28.1, 9.1.1 installed in `.venv` | routes, tools, tests |
| SQLite | 3.50.4 (stdlib) | `business_items` |
| Claude Code CLI | 2.1.263 at `C:/Users/gudo/.local/bin/claude.exe` | scout, session |
| WebSearch under the daemon's flags | probed today from `data/workspace` with `--setting-sources "" --restricted --tools WebSearch --permission-prompts none` and a scrubbed environment: completed, one web search request, no API key | scout |
| `data/workspace/` | exists, empty; `business/` subfolder is created by `index_documents` | documents |
| Preact, htm | vendored in `app/static/vendor/` | page |

Missing

| Package | Version | Needed for | Install target |
|---|---|---|---|
| none | | | |

Needs you

| Item | How |
|---|---|
| At least one plan captured before the first nightly window | `scout` returns `Skipped` with no plans, since plans are its only steer |

Verify

| Check | Command |
|---|---|
| Suite offline and green after each phase | `.venv/Scripts/python.exe -m pytest -q` |
| Module loads and the rail shows it | `.venv/Scripts/python.exe -m app status` after relaunch |
| Scout reaches the web from the daemon | Activity: the `business.scout` row shows `done` with `N new lead(s)` after the first window |

## Worktree

```
git worktree add ../otto-business -b business
```

Work in `../otto-business`. When the branch is merged to `main`, run `/sync-architecture`.

## Pending decisions

None.
