# Web Search Plan

Status: planning, 2026-09-07.

Every night Otto searches the web for the topics the owner cares about, keeps a few findings, and lines them up on Home for a yes or no. Each yes or no becomes a record of what the owner found worth keeping. Without it the Home requirement "web search items found via nightly search" and the whole Nightly Process section stay unbuilt.

## Sources

| Source | Governs |
|---|---|
| `docs/ARCHITECTURE.md` Home page (requirement 2), Nightly Process | what is searched, the review queue on Home, the cap |
| `docs/ARCHITECTURE.md` Daemon requirements, Mechanisms, Config, Claude, Module contract, UI frame contract | schedule, budget, read-only runs, files, wire shapes, tokens |
| `docs/design/Personal Dashboard App.dc.html` | LEFT rows and chips, MIDDLE inspector, rail. No search module exists in the artboard |
| `docs/gaps/nightly-search-not-built.md` | the gap this closes; WebSearch verification, done below |
| `app/modules/memory/` | the reference module: task with JSON reply, `INSERT OR IGNORE`, cursor in the same transaction, Accept / Dismiss rows |
| `app/modules/home/routes.py`, `app/static/pages/home.js` | Home already renders every module's `today` rows and `numbers`; untouched |
| `app/claude.py`, `app/runner.py`, `app/config.py`, `app/static/shell.js` | `run_task` flags and budget, `ctx.commit`, boot config, the `PAGES` map |

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | Its own module `web_search` with a page; Home shows it through the existing `today` and `numbers` hooks | Home already aggregates hooks; the module owns its data and Home code does not change |
| 2 | Topics are rows the owner types on the page, one of three kinds: `money` (investment, sector, legislation), `work` (techniques, research, career), `learn` (topics and question sources) | The three search categories from the Nightly Process, in the owner's words; no topic, no search, no budget spent |
| 3 | One Claude run per night for all topics, returning a JSON array of at most `max_findings` items | One run is one of the `[nightly] max_sessions`; the cap is in `config.toml`, not in a prompt |
| 4 | A finding is unique on `url`; inserted with `INSERT OR IGNORE`; the last hundred seen urls go into the prompt as "already found" | Idempotent and kill-safe; a rerun adds nothing twice; the agent stops resurfacing the same page |
| 5 | Agree and Disagree are user actions that set `status` and `decided_at` on the finding; nothing is deleted | The decision is the record the requirement asks for; disagreed urls still count as seen |
| 6 | LEFT search is `LIKE` over title and summary, no FTS5 | A few rows a night never needs an index |
| 7 | Follow-ups come in Phase 2: the nightly agent may set `follow_up_at`; agreed findings past that date are re-searched | Nightly Process item 1; needs Phase 1's records to exist first |

Rejected: a separate search API or key (ARCHITECTURE: no paid search, no API key); deriving topics from Memory (invents interest the owner never stated); a Home-only queue without a module (no place to manage topics or history); one run per topic (multiplies budget use).

## Layout

| File | Change |
|---|---|
| `app/modules/web_search/__init__.py` | `MANIFEST` |
| `app/modules/web_search/schema.sql` | `search_topics`, `search_findings` |
| `app/modules/web_search/tasks.py` | `nightly(ctx)` |
| `app/modules/web_search/routes.py` | `left`, `blank`, `item`, `action/{topic_add,topic_remove,decide}`, hooks |
| `app/modules/web_search/tools.py` | read tools; write tools in Phase 3 |
| `app/modules/web_search/agent.md` | the agent's job |
| `app/static/pages/web_search.js` | `load`, `meta`, `Left`, `Middle` |
| `app/static/shell.js` | one import and one `PAGES` entry |
| `app/config.py`, `config.toml` | `[web_search] max_findings` |
| `tests/test_web_search.py` | the tests below |

## Contract

| Field | Value |
|---|---|
| name, title | `web_search`, `Search` |
| hue, icon, order | `#d9915b`, magnifier `<circle cx="9" cy="9" r="5.5"></circle><path d="M13 13l4 4"></path>`, 9 (after Database) |
| schedule | `Schedule(task="nightly", every="24h", resource="web_search", llm=True)` |
| agent | placeholder `Ask about findings…`, skills `findings`, `topics`; read tools `search_findings`, `search_topics`; write tools none until Phase 3 |

Routes, prefix `/api/web_search`:

| Route | Wire shape |
|---|---|
| `GET left?query&chip&page` | LEFT shape; groups by night (`05 Sep`), rows `{id, module, text: title, stamp: found_at, leading: {kind}, done: status == disagreed}`; chips `All / Open / Agreed / Disagreed` |
| `GET blank` | `{kinds, topics: [{id, kind, text}], queue: [{id, kind, title, url, summary, found_at}], last_run}` |
| `GET item/{id}` | `{id, module, kind, text: title + summary, url, status, created_at: found_at, actions}`; actions `Open` (href), `Agree` (primary), `Disagree`; decided findings show only `Open` |
| `POST action/topic_add` | `{kind, text}` → `{id}`; 409 when listed; event `topic added` |
| `POST action/topic_remove` | `{id}` → `{id}`; findings keep their `kind` |
| `POST action/agree`, `POST action/disagree` | `{id}` → `{id, status}`; 409 when already decided; event `agreed` / `disagreed` with `ref`. Two verbs so Home's generic inspector can post them with only an id |

Hooks: `numbers` → open findings, label `to review`; `today` → findings found in the local day, any status; `queue` → every open finding, newest first, in the LEFT row shape (Home's `Review` group, per `docs/roadmap/homepage/PLAN.md`); `item`; `context` → topics by kind, the open queue, last run stamp.

Page: LEFT is search, chips, rows by night. MIDDLE blank is the topic editor (kind chips, input, `Add`, topics as removable chips) above the open queue, each row with `Agree` / `Disagree` like Memory's suggestions. MIDDLE selected is the shared Inspector.

Agent: answers questions about what was found and why it was kept, quoting titles and urls from `search_findings`; lists and explains topics from `search_topics`; never claims a finding exists that a tool did not return.

Departures from the artboard: the module is not in it, so title, hue, icon and rail position are proposed here (pending decision 1); the topic editor and queue as the blank state follow Memory's precedent, not a drawing.

## Data

| Table | Columns |
|---|---|
| `search_topics` | `id, kind CHECK IN (money, work, learn), text UNIQUE, created_at` |
| `search_findings` | `id, topic_id, kind, title, url UNIQUE, summary, found_at, status CHECK IN (open, agreed, disagreed) DEFAULT open, decided_at`; Phase 2 adds `follow_up_at, parent_id` |

Cursor `web_search.nightly`: ISO time of the last completed run, written in the same transaction as the findings.

| Path | Client | Proof |
|---|---|---|
| `nightly` task | `ctx.run_task` on the `otto-read` server with the built-in `WebSearch` / `WebFetch`; writes only through `ctx.commit` | `test_nightly_inserts_and_is_idempotent`; platform `test_tasks_never_reach_interactive_claude` |
| action routes | the store, through `runner.run_action`; no external system is ever written | `test_actions_write_status` asserts no route imports `app.claude` |

The external system is the public web, read-only by nature; this module has no write client.

## Phases

| Phase | Builds | Usable result |
|---|---|---|
| 1 | built; see ARCHITECTURE.md | |
| 2 | `follow_up_at` and `parent_id`; the prompt asks for a follow-up date when a finding is time-bound; agreed findings past their date are listed as "follow up on" in the next prompt and appear as kind `follow` | Scheduled follow-ups surface on their own |
| 3 | Write tools `search_topic_add`, `search_decide` on the full server | Topics and decisions from the session pane |

## Tests

- `test_nightly_inserts_and_is_idempotent`: `fake_spawn` returns a JSON array of two findings; the run inserts two rows and the cursor in one transaction; the same reply run again inserts zero.
- `test_nightly_skips_without_topics`: no topics returns `Skipped` and never calls `spawn`.
- `test_actions_write_status`: through the real app, add a topic, seed a finding, `agree` sets status and `decided_at`, `left?chip=Agreed` shows it, `/api/home/left` carries the `web_search` group and `/api/home/numbers` the open count.
- `test_registry_loads_real_modules` already covers the manifest import.

## Manifest

Present:

| Item | Version / location | Needed for |
|---|---|---|
| Python | 3.14.7, `.venv/Scripts/python.exe` | everything |
| fastapi, mcp, httpx, pytest | 0.141.1, 2.2.0, 0.28.1, 9.1.1 (installed) | routes, tools, tests |
| Claude Code CLI | 2.1.263, `C:/Users/gudo/.local/bin/claude.exe` | the nightly run |
| WebSearch in a headless run | verified today with the daemon's flags (`--restricted --setting-sources "" --permission-prompts none --tools ...WebSearch`): `WebSearch` was called, `is_error: false`, 5.7 s, 2 turns | the nightly run |
| Overage charges | `rate_limit_event` reports `overageStatus: rejected, org_level_disabled` | the "no other api charges" constraint |

Missing: none.

Needs you:

| Item | How |
|---|---|
| The first topics | type them on the Search page after the branch merges; nothing runs before that |

Verify:

| Check | Command |
|---|---|
| WebSearch still answers headless | `echo "Use WebSearch once for the fastapi version on PyPI; one line." \| env -u CLAUDECODE claude -p --output-format json --setting-sources "" --restricted --tools WebSearch --allowedTools WebSearch --permission-prompts none --max-turns 4` |
| Suite offline | `.venv/Scripts/python.exe -m pytest -q` |

## Worktree

```
git worktree add ../otto-web_search -b web_search
```

Work there. When `web_search` merges to `main`, run `/sync-architecture`.

## Pending decisions

1. Title `Search`, hue `#d9915b`, magnifier icon, rail order 9: built as proposed on 2026-09-08; change `MANIFEST` in `app/modules/web_search/__init__.py` to pick another.
