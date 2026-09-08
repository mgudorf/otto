# Homepage v0 Plan

Status: planning, 2026-09-08.

Home shows everything still waiting for a yes or no, not just what arrived today, so a week of unreviewed findings is one list on the first page the owner opens. Without it, findings older than today leave Home and survive only as a number; the owner has to go to the Search page to clear the queue.

The nightly search, its table, its topics and the agree / disagree actions are `docs/roadmap/web_search/PLAN.md`. This item is the seam Home offers to any module that keeps a queue, and web_search is its first implementer.

## Sources

| Source | Governs |
|---|---|
| `docs/ARCHITECTURE.md` › Home page requirement 2 ("adds to a queue", "21 items to review") | The queue must be visible on Home in full |
| `docs/ARCHITECTURE.md` › Module contract, UI frame contract | Hook shape, LEFT wire shape, rows and group headers |
| `docs/design/Personal Dashboard App.dc.html` lines 49–75 | Home LEFT: a hue-coloured module header with icon and count, 36px rows, `+N` |
| `app/modules/__init__.py` | `Module` fields and how hooks are picked up from `routes.py` |
| `app/modules/home/routes.py`, `app/static/pages/home.js` | Home's `left`, `context`, the group renderer and the inspector's action posting |
| `docs/roadmap/web_search/PLAN.md` | `search_findings.status`, `action/agree`, `action/disagree`, `item`, the row shape web_search already returns |

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | A fifth hook on the Module contract: `queue(store) -> rows`, every row still waiting on the owner, newest first, in the LEFT row shape | Home already reads modules through hooks and never their tables; the hook keeps web_search the owner of its schema and lets Home stay ignorant of it |
| 2 | Home's `left` puts one group per enabled module with a `queue` hook before the `today` groups: label `Review`, the module's hue and icon, every row, `more: 0` | The queue is what the owner must act on; it is bounded by the producer's nightly cap, so no paging and no five-row cut |
| 3 | Selecting a row and acting on it goes through the owning module's `item` and `action/<verb>` routes, as it does today | Home's inspector already posts `{id}` to `/api/<module>/action/<verb>`; web_search exposes `agree` and `disagree` as verbs for exactly this |
| 4 | Home's Current state block gains `Review: N` and one line per queued row | The Home agent answers from that block; it should be able to say what is waiting |
| 5 | No Home number for the queue | web_search's own `numbers` hook already reports `to review`; a second count would say the same thing twice |
| 6 | `home.js` is not changed | The existing group renderer takes `{module, label, hue, icon, count, rows, more}`; a decided row disappears on the next refresh because the hook no longer returns it |

Rejected: Home reading `search_findings` directly (couples Home to one module's schema); reusing `today` with a wider window (today means today for every other module); a `queue` route on web_search that Home calls over HTTP (hooks are in-process; nothing else on Home goes through the network).

## Layout

| File | Change |
|---|---|
| `app/modules/__init__.py` | `Module.queue: Callable[[Any], list[dict]] \| None`; `_load_one` picks it up with `getattr(routes_mod, "queue", None)`; docstring names it |
| `app/modules/home/routes.py` | `left_route` prepends the `Review` groups; `context` adds the queue lines |
| `app/modules/home/agent.md` | one sentence: the Review lines are what still needs a decision; say which is worth opening, never decide |
| `docs/ARCHITECTURE.md` Module contract row for `routes.py` | add `queue(store) -> rows` (done by `/sync-architecture` after merge) |
| `tests/test_app.py` | `test_home_review_group` |
| `tests/test_platform.py` | add `m.queue` to the hooks-take-the-store loop |

## Contract

| Field | Value |
|---|---|
| Manifest | unchanged: `home`, `Home`, `#e6e7ea`, diamond icon, order 0, no schedules, tool-less agent |
| Hook | `queue(store) -> [{id, module, text, stamp, leading?, done?}]`, optional on every module; the rows are the same shape `today` returns |

`GET /api/home/left`:

```
{groups: [
  {module: "web_search", label: "Review", hue, icon, count: N, rows: [...every queued row...], more: 0},
  ...the today groups exactly as now
]}
```

A module is included only if its package has the hook, `manifest.page` is true, and `modules.<name>.enabled` is not false. A module whose queue is empty contributes no group. The `Review` groups come first, in rail order.

`context(store, registry)`: after the existing per-module lines, `Review: N waiting` and `  - (<module> <id>) <text[:160]>` per queued row; `Review: nothing waiting` when every queue is empty.

Departures from the artboard: the artboard's Home LEFT has only today-per-module groups. `Review` reuses the same module header, rows and hue, and sits above them; nothing else is drawn differently.

## Data

No table, cursor or client. Home reads through hooks and writes nothing; it has no tasks. The scheduled / user-action split is web_search's to prove; this item's test only asserts that Home never touches a module table (`app/modules/home/` imports no other module).

## Phases

| Phase | Builds | Usable result |
|---|---|---|
| 1 | The hook field, the `Review` groups in `left`, the context lines, the tests | Every queued finding is listed at the top of Home; selecting one opens the shared inspector; `Agree` or `Disagree` removes it on the next refresh |

## Tests

- `test_home_review_group`: build the app, inject a `Module` with `page=True`, a `queue` hook returning two rows and an `item` hook into `app.state.registry.modules`, set `modules.<name>.enabled`; `GET /api/home/left` first group is `Review` for that module with count 2 and both rows; `context` names both; set the setting to false and the group is gone; a module without the hook (Memory) never produces a `Review` group.
- `test_registry_loads_real_modules`: the hook loop includes `queue`, so a route handler named `queue` fails the suite.
- Suite stays offline; nothing here spawns Claude.

## Manifest

Present

| Item | Version / location | Needed for |
|---|---|---|
| Python | 3.14.7, `.venv/Scripts/python.exe` | everything |
| fastapi, httpx, pytest | 0.141.1, 0.28.1, 9.1.1 installed in `.venv` (`pip list`, 2026-09-07) | routes, tests |

Missing

| Package | Version | Needed for | Install target |
|---|---|---|---|
| none | | | |

Needs you

| Item | How |
|---|---|
| nothing | |

Verify

| Check | Command |
|---|---|
| Suite offline | `.venv/Scripts/python.exe -m pytest -q` |
| Once web_search has merged: Home lists the open findings | open Home; the first group is `Review` with the same count as the `to review` number |

## Worktree

```
git worktree add ../otto-homepage -b homepage
```

Work there. When `homepage` is merged to `main`, run `/sync-architecture`. Merge order does not matter: without a module that implements `queue`, Home is unchanged.

## Pending decisions

None. web_search's plan must add `queue(store)` to its hooks (open findings, newest first, the row shape its `left` already returns); that is one line in its Contract section.
