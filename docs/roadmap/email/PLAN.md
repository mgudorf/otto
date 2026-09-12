# Email Organization Plan

Status: planning, 2026-09-12.

Email mirrors and reads the mailbox but cannot organize it: three near-identical buttons act on one message or on everything matching a search, nothing in between, and the only view is the inbox. This item makes the mailbox navigable the way Gmail's own sidebar is (eleven partitions and the owner's labels), lets the owner pick out a subset with ctrl and shift, marks Trash as the destructive button it is, and stops a failed action or a dying credential from being invisible. Without it the module stays a reader and inbox cleanup goes back to the Chrome UI that misbehaves on bulk deletes.

## Sources

| Source | Governs |
|---|---|
| `docs/ARCHITECTURE.md` E-mail section | the built tables, routes, hooks, tools, schedules and departures this item changes |
| `docs/ARCHITECTURE.md` Daemon requirements and mechanisms | read client for tasks, write client for actions, idempotent commits, per-resource locks, "the user never presses a button whose only purpose is to make the system run" |
| `docs/ARCHITECTURE.md` Module contract | hooks (`numbers`, `today`, `queue`, `item`, `context`), `setup(config)` for a column added to an existing table, LEFT wire shape |
| `docs/ARCHITECTURE.md` Config | `config.toml` is boot values; `PUT /api/settings` accepts only `ui.*` and `modules.<name>.{enabled,scheduled}`, so a new email knob cannot live in the settings table |
| `docs/ARCHITECTURE.md` UI frame contract | hue `#cf7b7b`, chips `3px 9px` wrapping, 36px rows, primary is hue background, Email's reader carries no actions |
| `docs/design/Personal Dashboard App.dc.html` `isEmail` LEFT | chips All / Unread / Flagged; rows by day with a 6px dot; `n / total` and `more` |
| artboard `selInfo` for `em` rows | inspector primary `Reply`, actions `Archive`, `Snooze` — already departed from and departed from further here |
| `app/modules/email/routes.py` | `_where` (hard-codes `INBOX`), `_resolve` (`ids` or `filter` only), `VERBS`, `CHIPS`, the hooks |
| `app/modules/email/gmail.py` | `GmailRead` has no `labels`; `GmailWrite` has only `modify`; `list_ids` omits spam and trash |
| `app/modules/email/tasks.py` | imports `HAS`/`PRIORITIES` from `routes.py`, so `routes.py` cannot import it at module level |
| `app/static/pages/email.js`, `app/static/rows.js`, `app/static/shell.js` | the sticky action bar, `Row`'s `onClick=${onSelect}` (no event), the shared state bag reset on page switch |
| `docs/bugs/email-actions-fail-silently.md` | closed by phase 1 |
| `docs/bugs/home-email-actions-post-id.md` | closed by phase 1 |
| `docs/gaps/gmail-refresh-token-expires.md` | the owner declined Production on 2026-09-12; the 7-day token is permanent, so phase 1 surfaces it |
| live mailbox, 2026-09-12 | label counts and the purchases answer below |

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | Trash carries the hue; Archive becomes secondary | The hue `#cf7b7b` is the only red in the palette and the frame contract gives it to the primary action. Archive is reversible, Trash is not (30 days, then gone), so the destructive one gets the weight. Owner, 2026-09-12 |
| 2 | Eleven partitions from Gmail's own labels: Inbox, Starred, Important, Personal, Social, Updates, Promotions, Forums, Purchases, Spam, Trash. `_where` stops hard-coding `INBOX`; the partition decides | Ten are label ids already in the mirror (counts in the Manifest), so filtering stays a local `json_each` test and is instant. The current `_where` forces `INBOX` into every query, which is exactly why Spam and Trash are unreachable |
| 3 | Purchases is mirrored as a column `is_purchase`, set by `sync` from one `list_ids("category:purchases")` per run | Verified live 2026-09-12: the search term works and returns 412 messages, but Gmail exposes no label id for it, so the mirror cannot recognise one. One extra `messages.list` per five-minute sync (5 quota units, one page) buys a local flag, so all eleven partitions filter by the same mechanism at the same 5-minute staleness. The alternative, a Gmail round-trip each time the chip is picked, would make one partition behave unlike the other ten |
| 4 | The backfill passes `includeSpamTrash=true` | `list_ids` omits both today, so the Spam and Trash partitions would hold only what drifted in through history (25 and 60 rows against a 3,183-message mailbox). A partition that is silently partial is worse than none |
| 5 | Clicking an unread message marks it read, through the write client, gated by `[email] read_on_open` | Requirement 2 in the owner's words; it is a user action from a route, so the read-only-agent fence is untouched. It is a knob because it makes a click mutate the mailbox, and that is a decision the owner must be able to reverse. `config.toml`, not the settings table, because `PUT /api/settings` accepts only `ui.*` and `modules.*.enabled`/`.scheduled` |
| 6 | Ctrl-click toggles one row, shift-click extends from the anchor over the flattened visible order; the bar acts on the picked set when it is non-empty, else the selected message, else the whole filter | The three scopes the owner needs, in one bar, with no checkbox column. `Row` gains the click event (`onClick=${(e) => onSelect(e)}`), which every other page ignores |
| 7 | The picked set lives in the shell's state bag as `picked`, reset on page switch beside `query`, `chip` and `more` | It is selection state, the same kind the shell already resets; a module-level variable in `email.js` would survive a page switch and act on rows the owner cannot see |
| 8 | `POST action/sync` runs the existing `sync` task through `runner.run_action` on resource `gmail`, importing `tasks` inside the handler | Same function, same lock, so a manual sync and the 5-minute one serialize instead of racing. The deferred import is forced: `tasks.py` imports `routes.py`, so the reverse cannot happen at module level |
| 9 | `sync` writes a cursor `email.synced_at` on every successful run; `blank` reads it | `blank.last_sync` reads `tasks.last_run`, which a manual action never advances, so a sync button would leave the timestamp stale and look broken |
| 10 | Both action paths in the page catch and render the failure in the bar's label slot | Closes `email-actions-fail-silently.md`: today a refused route is indistinguishable from a successful one, which is how a dead credential went eight hours unnoticed on 2026-09-12 |
| 11 | `_resolve` accepts `{id}` as a one-element `ids` | Closes `home-email-actions-post-id.md` in the change that reworks the action shape anyway; one line, and Home stays module-agnostic |
| 12 | A `queue` hook returns one row when the refresh token expires within `[email] consent_warn_days` | The owner declined Production on 2026-09-12, so the token dies every 7 days for good. Home already lists every module's `queue`, so the warning costs one hook and arrives before the outage instead of after it |
| 13 | User labels are read into `email_labels` by `sync`, applied by `action/label` and `action/unlabel`, created by `action/create_label`. No agent tool writes a label | Requirement 4 is a hard constraint: `email_flag` stays the only write tool, and labels are page actions. The agent gets a read tool `email_labels` so it can name one in a suggestion |

Rejected: chips for all fourteen states in one row (fourteen 13px chips wrap to four lines and bury the rows); a per-row checkbox column (the artboard has none and ctrl-click is what the owner asked for); querying Gmail per partition (decision 3); `category:reservations` as a twelfth partition (verified live: 0 messages); permanent delete (still outside `gmail.modify`); a settings-table knob for `read_on_open` (the platform allowlist would have to change).

## Layout

| File | Change |
|---|---|
| `app/modules/email/__init__.py` | `setup(config)` adds `is_purchase`; agent read tool `email_labels` |
| `app/modules/email/schema.sql` | `email_labels`; `is_purchase` on `email_messages` for a fresh database |
| `app/modules/email/gmail.py` | `list_ids(query, include_spam_trash=False)`; `GmailRead.labels()`; `GmailWrite.create_label(name)` |
| `app/modules/email/tasks.py` | `sync` flags purchases, mirrors labels, writes `email.synced_at`; backfill includes spam and trash |
| `app/modules/email/routes.py` | `PARTITIONS`; `_where(query, chip, partition)`; `_resolve` takes `{id}`; verbs `label`, `unlabel`, `create_label`, `sync`; `read_on_open` on `item`; partition counts in `blank`; `queue` hook |
| `app/modules/email/tools.py` | read tool `email_labels` |
| `app/modules/email/agent.md` | the agent may name a label, never apply one |
| `app/static/pages/email.js` | partition chips, label chips and `+ label`, multi-select, `Sync`, Trash in the hue, the error line |
| `app/static/rows.js` | `Row` passes the click event to `onSelect` |
| `app/static/shell.js` | `picked: []` in the initial state and the page-switch reset |
| `app/config.py`, `config.toml` | `[email]` gains `read_on_open`, `consent_warn_days` |
| `tests/test_email.py` | the six tests below |

## Contract

Manifest unchanged except `setup` and the new read tool: `name="email"`, `hue="#cf7b7b"`, `order=1` (ties with Chat, which sorts first).

| Schedule | Every | Resource | LLM | Change |
|---|---|---|---|---|
| `email.sync` | 5m | `gmail` | no | also flags purchases, mirrors labels, writes `email.synced_at` |
| `email.triage` | 24h | `email` | yes | unchanged |

Routes, prefix `/api/email`:

| Route | Wire shape |
|---|---|
| `GET left?query&chip&partition&page` | as today, plus `partitions` (the eleven, each `{name, count}`), `partition`, `labels` (`[{id, name, count}]`). `chips` drops `Flagged` (Starred is a partition) leaving `All`, `Unread`, `Priority` |
| `GET blank` | `{partitions: {...counts}, labels: [...], unread, priority, last_sync}` from `email.synced_at` |
| `GET item/{id}` | as today; when the message is unread and `read_on_open` is set, the route removes `UNREAD` through the write client first, then returns the item read |
| `POST action/{verb}` | `{ids}`, `{id}`, or `{filter: {query, chip, partition}}`. Verbs: today's six, plus `label` and `unlabel` (`{label_id}`), `create_label` (`{name}`), `sync` (no target) |

Partition meaning: Inbox `INBOX`, Starred `STARRED`, Important `IMPORTANT`, Personal `CATEGORY_PERSONAL`, Social `CATEGORY_SOCIAL`, Updates `CATEGORY_UPDATES`, Promotions `CATEGORY_PROMOTIONS`, Forums `CATEGORY_FORUMS`, Spam `SPAM`, Trash `TRASH`, Purchases `is_purchase = 1`. The `All` / `Unread` / `Priority` chips narrow within the partition; search is FTS as today.

Hooks: `numbers` and `today` unchanged (both stay scoped to `INBOX`). New `queue`: one row `Gmail consent expires <stamp>` when the token's remaining refresh life is under `consent_warn_days`, so Home shows it. `context` gains the partition counts and the owner's label names. `item` as above.

MCP tools: read `email_search`, `email_get`, `email_triage`, and new `email_labels` (id, name, count) on both servers. Write on `otto` only: `email_flag`. Nothing new can reach Gmail.

Agent: unchanged in job. It triages, prioritizes and flags with a reason, and may now say "this looks like Receipts" by name, because it can read the label list. It cannot apply, create or remove a label, archive, trash or send; asked to, it says the owner does that from LEFT.

Departures from the artboard, each with its reason:

- Trash takes the hue and Archive goes secondary (decision 1). The artboard's primary is `Reply`, which does not exist here — no compose in this module.
- Partition chips and label chips are not drawn; the artboard's LEFT has `All` / `Unread` / `Flagged` only. Requirement 2 needs the eleven, and `Flagged` becomes the Starred partition rather than a second way to say the same thing.
- `+ label` and the `Sync` control are not drawn anywhere in the artboard.
- Multi-select is not drawn; the artboard's rows select one at a time.
- `Sync` also departs from the Daemon contract's "the user never presses a button whose only purpose is to make the system run". The schedule still runs every five minutes and nothing waits on the button; it exists so the owner can confirm a bulk action landed instead of waiting out the interval. Requirement 3, owner, 2026-09-12.
- Purchases is a search term, not a label (decision 3), so this one partition is as fresh as the last sync rather than as fresh as the mirror.

## Data

`schema.sql`:

| Table | Columns |
|---|---|
| `email_messages` | unchanged plus `is_purchase INTEGER NOT NULL DEFAULT 0`; added by `setup` on the existing database, in `schema.sql` for a fresh one |
| `email_labels` | `id TEXT PRIMARY KEY` (Gmail label id), `name TEXT NOT NULL`, `kind TEXT NOT NULL` (`system` or `user`), `synced_at TEXT NOT NULL` |

Cursors: `email.history` and `email.backfill` unchanged. New `email.synced_at`, the stamp of the last successful sync however it was started, written inside the same `ctx.commit` as the history id.

External clients:

| Path | Client | Can |
|---|---|---|
| `email.sync` task | `read_client` | profile, list, get, history, `labels.list` |
| `item` route when `read_on_open` and the message is unread | `write_client` | `batchModify` removing `UNREAD` |
| `action/*` routes | `write_client` | `batchModify`, `labels.create` |
| `action/sync` route | the task's own `read_client` | as the task |
| session agent | MCP tools only | read the mirror and the label list, write `email_triage` |

Split proof: `test_email_client_split` keeps its AST scan of `tasks.py` and `tools.py` and gains `create_label` and `labels` to the forbidden set for `tools.py` only — `tasks.py` legitimately calls `GmailRead.labels`, so the scan asserts `GmailRead` has neither `modify` nor `create_label` and that `tasks.py` names no writing symbol. The tool-registration half is unchanged: the only tool on `full` and not on `read` is `email_flag`.

## Phases

| Phase | Builds | Usable result |
|---|---|---|
| 1 | Trash in the hue, `read_on_open`, multi-select (`rows.js`, `shell.js`, the bar), `{id}` in `_resolve`, the caught-and-rendered error, `action/sync`, `email.synced_at`, the `queue` warning, `read_on_open` and `consent_warn_days` in config, tests 1 to 3 | The owner picks out a subset with ctrl and shift and archives or trashes exactly it; opening a message marks it read; the destructive button looks destructive; a refused action says why; a manual sync confirms the mailbox; the dying token appears on Home two days early instead of as a silent outage |
| 2 | `PARTITIONS`, `_where` without the forced `INBOX`, `is_purchase` and its sync call, `includeSpamTrash`, partition counts in `blank` and `context`, test 4 | All eleven Gmail partitions browse in Otto, Spam and Trash included, with counts on the blank state |
| 3 | `email_labels`, `GmailRead.labels`, `GmailWrite.create_label`, verbs `label` / `unlabel` / `create_label`, the label chips and `+ label`, the `email_labels` tool, test 5 | The owner sees their labels with counts, applies one to a picked subset, and creates a new one without leaving Otto |

## Tests

- `test_email_multi_select_actions`: `archive` with `{ids}` of three, `trash` with `{id}` of one, and `read` with `{filter}`; the `batchModify` body and the local labels are asserted for each, and an `events` row is written.
- `test_email_read_on_open`: `item/{id}` on an unread message removes `UNREAD` through the write client when the knob is on and touches Gmail not at all when it is off or the message is already read.
- `test_email_manual_sync`: `action/sync` runs the task on resource `gmail` and writes `email.synced_at`; a second call while one is running serializes. `test_email_consent_warning`: the `queue` hook yields one row inside the window and none outside, reading the token file only.
- `test_email_partitions`: a fixture carrying the real label sets (including a spam row, a trash row and a purchases flag) is selected correctly by each of the eleven, and by a partition combined with `Unread` and with a search.
- `test_email_labels`: `labels.list` lands in `email_labels` with `kind`; `create_label` posts the right body and `label` applies the returned id; `unlabel` removes it.
- `test_email_client_split`: extended as in Data.

All against `httpx.MockTransport` through `TRANSPORT`; Claude stays mocked at `app.claude.spawn` by `conftest.py`; the suite stays offline.

## Manifest

Present:

| Item | Version / location | Needed for |
|---|---|---|
| Python | 3.14.7 in `.venv` | everything |
| httpx | 0.28.1 in `.venv`, pinned | Gmail REST, `MockTransport` |
| SQLite with FTS5 and JSON1 | 3.50.4, stdlib | `email_fts`, `json_each` partition tests |
| `data/secrets/google_client.json` | web client, project `central-shift-507603-b1`, secret rotated 2026-09-12 and verified working against `oauth2.googleapis.com` today; redirect `http://localhost:8756/m/email/api/oauth/callback` registered | token refresh, `consent` |
| `data/secrets/token.json` | scope `gmail.modify`; refresh token issued 2026-09-12 17:39 local, `refresh_token_expires_in` 604799, so it dies about 2026-09-19 17:39 | sync, actions, labels |
| Live mailbox, read 2026-09-12 | `matthew.gudorf@gmail.com`, 3,183 messages, history id 13784752; `email.sync` recovered at 21:43 UTC with "21 updated" | the counts below |
| Partition labels in the mirror | `INBOX` 2123, `CATEGORY_UPDATES` 1391, `CATEGORY_PROMOTIONS` 737, `IMPORTANT` 112, `UNREAD` 91, `TRASH` 60, `CATEGORY_PERSONAL` 38, `CATEGORY_SOCIAL` 27, `SPAM` 25, `CATEGORY_FORUMS` 5, `STARRED` 2 | ten of the eleven partitions, no new sync needed |
| `category:purchases` | 412 messages, verified live 2026-09-12 through `GmailRead.list_ids` | the eleventh partition, decision 3 |
| User labels | none exist on the account today; `email_labels` starts empty and `create_label` is how the first one appears | phase 3 |

Missing: none. No new package, binary or scope; `labels.list` and `labels.create` are both inside `gmail.modify`.

Needs you:

| Item | How |
|---|---|
| Re-consent every 7 days | `.venv/Scripts/python.exe -m app.modules.email.gmail consent`, while the consent screen stays in Testing (owner declined Production, 2026-09-12). Phase 1's `queue` row is the reminder; it does not remove the chore |
| The stale `email` worktree | `../otto-email` and branch `email` still sit at `69bef94`, the landed work, so this item cannot reuse the name. Remove them, or accept the branch named in Worktree below. Removing a worktree is yours to run |

Verify:

| Check | Command |
|---|---|
| The rotated secret still refreshes | `.venv/Scripts/python.exe -c "import asyncio,httpx;from app.config import load;from app.modules.email.gmail import read_client;gm=read_client(load());print(asyncio.run(gm.profile())['emailAddress'])"` |
| Purchases still answers, before phase 2 | `.venv/Scripts/python.exe -c "import asyncio;from app.config import load;from app.modules.email.gmail import read_client;print(len(asyncio.run(read_client(load()).list_ids('category:purchases'))))"` |
| Days of refresh token left | `.venv/Scripts/python.exe -c "import json;print(json.load(open('data/secrets/token.json'))['refresh_token_expires_in']/86400)"` |
| Labels endpoint answers, before phase 3 | `.venv/Scripts/python.exe -c "import asyncio;from app.config import load;from app.modules.email.gmail import read_client;print(asyncio.run(read_client(load()).labels()))"` |

## Worktree

```
git worktree add ../otto-email-organization -b email-organization
```

Work in `../otto-email-organization`. The plain `email` name is taken by the landed branch and its worktree; if you remove those first, use `git worktree add ../otto-email -b email` instead. When the branch is merged to `main`, run `/sync-architecture`.

## Pending decisions

1. Purchases is included as decision 3 on the strength of today's live check (412 messages). You reserved this call: say so and it comes out, leaving ten partitions and no `is_purchase` column.
2. Phase 1's token warning (decision 12) is beyond the four things you asked for. It is here because the credential dying silently is what made the reported symptom unreadable. Cut it and phase 1 loses one hook and one config key.
