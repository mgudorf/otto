# Email

1. Uses gmail OAuth
2. Search bar/full ability to interact with inbox (Google chrome behaves very strangely when trying to do bulk deletes; I would like to resolve by explicitly using API here)
3. Agent only performs triage&sorting, prioritization and flagging of relevant items
4. Agent does NOT have the ability to write nor delete on its own. This needs to be a HARD CONSTRAINT determined by tooling or gmail api implementation. 

## Built

| Piece | Current state |
|---|---|
| Tables | `email_messages(n rowid, id Gmail id, thread_id, from_name, from_addr, to_addr, subject, snippet, internal_date, labels JSON, synced_at)`, `email_bodies(message_id, text, html, attachments JSON filenames)` filled on first open, `email_triage(message_id, priority high\|normal\|low, reason, ts, source scheduled\|session)`, `email_fts` (FTS5 over sender, subject and snippet, trigger-maintained) |
| Routes | `left` (query: each word a quoted FTS phrase, all required; chips All/Unread/Flagged/Priority over the inbox: `UNREAD`, `STARRED`, triage `high`; page), `blank` (inbox, unread, flagged, priority counts and the last sync), `item/{id}`, `action/{archive\|trash\|read\|unread\|star\|unstar}` with `{ids}` or `{filter: {query, chip}}` (400 when neither selects anything); one `_where` serves LEFT, the bulk actions and `email_search` |
| Item | `body_of` fetches the message once through the read client into `email_bodies` (shared with `email_get`); on failure the snippet stands in, a `failed` event is written and the next open retries. Fields: headers, `text` (`subject` + body, for Home and Feedback), `body`, `html`, `attachments`, `unread`, `starred`, `in_inbox`, `priority`, `reason`, `actions` (`archive` primary and `trash` with confirm while in the inbox, read/unread, star/unstar, `open` as a Gmail href) |
| Body | `body.py`: `extract` gives text (plain parts, else the html as text, else the snippet), sanitized html (`None` when nothing is visible) and attachment names; no attachment is ever fetched. `sanitize` keeps a fixed tag set bare (integer `colspan`, `rowspan`, `start` only), drops scripts, styles, forms, media and anything hidden inline, writes a link as its text plus the raw URL for http, https, mailto and tel, and an image as its alt text |
| Actions | labels change through `batchModify` in chunks of 1000, then the local rows in the same job; `trash` is Gmail's Trash (the `gmail.modify` scope cannot delete permanently); events `archived`, `trashed`, `marked read`, `marked unread`, `starred`, `unstarred` name the subject for one id, else `N messages · chip` |
| Hooks | `numbers` (unread), `today` (inbox mail of the local day), `item`, `context` (counts, last sync, ten newest, high-priority with reasons) |
| Tools | read: `email_search`, `email_get` (text and attachment names), `email_triage`; write: `email_flag`, which upserts Otto's triage row with source `session`. No tool reaches Gmail. `test_email_client_split` forbids every writing name in `tasks.py` and `tools.py` |
| Schedules | `email.sync` every 5m on resource `gmail`: first a `backfill_days` backfill (`newer_than`, ten metadata fetches in flight) committed in pages of 100 under the cursor `email.backfill` (`<historyId>\|<started>`, resumed by the next run), then Gmail history from `email.history`, re-fetching added and relabelled ids and deleting removed ones; a 404 on that id (expired) backfills again. `email.triage` every 24h inside the nightly window prioritizes `triage_batch` untriaged inbox messages with a JSON-array reply, `INSERT OR IGNORE` so a session flag is never overwritten, cursor `email.triage` |
| Gmail | `gmail.py`: the token, refreshed 60 s before expiry and written back; `GmailRead` (`profile`, `list_ids`, `metadata`, `body`, `history`) for tasks and body fetches; `GmailWrite` adds `batchModify` and is reachable only from action routes; `TRANSPORT` is the test seam; the `consent` command. A quota refusal (429, or 403 naming the quota) pauses every call in flight together for 61 s and retries up to five times |
| Page | LEFT: search, chips, then a sticky action bar, then rows by day as `sender: subject` with the unread dot. The bar shows the selected message's actions (`1 selected`), or `Mark read`, `Archive`, `Trash` over every message matching the filter (archive and trash confirm with the count); archiving or trashing the selection clears it. MIDDLE blank: one status line of the counts and last sync. MIDDLE selected: the reader in a `72ch` measure: kind and time, `Send to session`, `×`, subject, `from → to`, priority and reason, attachment names, then the sanitized html under the `.mail` rules or the plain text. No mailbox action lives in MIDDLE |
| Departures | `Priority` chip added; no `Reply` (no compose) and no `Snooze` (no API); the inspector's action row became the LEFT bar so one control serves one message and the whole filter; the blank state is unspecified in the artboard |

## Patches

### Email and Education page actions fail silently

- Kind: bug
- Where: `app/static/pages/email.js` `Actions` (`act` and `bulk`, both `await post(...)` unguarded); `app/static/pages/education.js` `act` for `Start` and `Skip` (same unguarded `await post`, while `answer` and `generate` in the same file do catch); `app/static/api.js` `api` throws on a non-2xx
- Found: 2026-09-12, email organization session; Education added 2026-09-12, sync-architecture
- Status: open

What happens: every action button on the Email page posts through `api.js`, which throws an `Error` when the route answers 4xx or 5xx. Neither `act` (the selected message's Archive, Trash, Mark read, Star) nor `bulk` (the filter-wide Mark read, Archive, Trash) catches it, so the rejection is unhandled: the confirm dialog closes, no error is drawn, no refresh runs, and the row is unchanged. The page looks identical whether the mailbox changed or Gmail refused. Any route failure produces this, and there are several live ones: an expired refresh token (the entry `Gmail refresh token expires around 2026-09-12` below), a Gmail quota refusal that outlasts five retries, and a 400 "nothing selected". Unlike `loadItem`, which stores `{error}` and renders it in the reader, the action path has no error surface at all. Education's `Start` and `Skip` behave the same way: a 409 because the tutor already graded or skipped the question is an unhandled rejection with nothing drawn.

Expected: an action that fails says so where it was pressed, in the module hue, and the list does not pretend the mailbox changed.

Fix: catch around both posts and render the message in the action bar, the way `Reader` renders `item.error`. The bar already has a label slot to hold it.

### `email_search` tells the agent three chips when four exist

- Kind: bug
- Where: `app/modules/email/tools.py` `email_search` docstring; `app/modules/email/agent.md` line 3; `app/modules/email/routes.py` `CHIPS`
- Found: 2026-09-12, sync-architecture
- Status: open

What happens: the tool's description, which is what the agent reads when choosing arguments, says the chip narrows to `All`, `Unread` or `Flagged`. The route accepts `Priority` as well and the agent's instructions tell it to use that chip. An agent that follows the tool description never asks for the priority view it is told to triage from.

Expected: the tool description names the four chips the route serves.

Fix: add `Priority` to the docstring, or build the docstring from `CHIPS` so the two cannot drift.

### Gmail refresh token expires around 2026-09-12

- Kind: gap
- Where: Email requirement 1 (Gmail OAuth); `data/secrets/token.json`, `app/modules/email/gmail.py`
- Found: 2026-09-09, sync-architecture
- Status: open, owner action; recurring while the consent screen stays in Testing

What happens: the token still carries `refresh_token_expires_in`, 205,388 seconds as of 2026-09-10 and 1,075 seconds at the 2026-09-12 sync, because it was issued while the OAuth consent screen for project `central-shift-507603-b1` was in Testing. From 2026-09-12 the refresh stops working: `email.sync` fails every five minutes, `email.triage` has nothing new to read, and every action route on the Email page fails. On 2026-09-12 it did stop: 216 `email.sync` failures over eight hours (`invalid_grant`, then `invalid_client` once the client secret was deleted). The secret was rotated and a new token issued at 17:39 local with `refresh_token_expires_in` 604799, so it dies about 2026-09-19 17:39. The owner declined Production that day, so this repeats every 7 days.

Expected: a refresh token with no expiry, so the mirror and the bulk actions keep working without the owner touching them.

Fix: every 7 days meanwhile, `.venv/Scripts/python.exe -m app.modules.email.gmail consent`. Permanently, set the consent screen to Production in the Cloud console for `central-shift-507603-b1`, confirm the redirect `http://localhost:8756/m/email/api/oauth/callback` is still registered on the client, then run `python -m app.modules.email.gmail consent` once. The new `token.json` should have no `refresh_token_expires_in`.

### The mailbox cannot be organized from Otto

- Kind: gap
- Where: Email requirements 2 and 4; `app/modules/email/routes.py` (`_where` hard-codes `INBOX`; `_resolve` takes `ids` or `filter` only), `app/modules/email/gmail.py` (`GmailRead` has no `labels`, `list_ids` omits spam and trash), `app/modules/email/tasks.py`, `app/static/pages/email.js`, `app/static/rows.js` (`Row` drops the click event), `app/static/shell.js` (the state bag reset on page switch)
- Found: 2026-09-12, the owner's request; decisions taken 2026-09-12
- Status: open, not started

What happens: the mirror reads the mailbox but cannot organize it. The bar acts on one message or on everything matching a search, nothing in between; the only view is the inbox, so Spam, Trash and Gmail's categories are unreachable; Archive carries the hue while Trash, the irreversible action, does not; a refused action draws nothing (the entry `Email and Education page actions fail silently`); and the refresh token dies every 7 days without warning (the entry `Gmail refresh token expires around 2026-09-12`). Inbox cleanup goes back to the Chrome UI that misbehaves on bulk deletes.

Expected: the owner's decisions of 2026-09-12. Trash takes the hue and Archive goes secondary. Eleven partitions from Gmail's own labels (Inbox, Starred, Important, Personal, Social, Updates, Promotions, Forums, Purchases, Spam, Trash): `_where` stops forcing `INBOX`, the backfill passes `includeSpamTrash=true`, and Purchases is a column `is_purchase` that `sync` sets from one `list_ids("category:purchases")` per run (verified live: 412 messages and no label id; `category:reservations` answers 0 and is out); `Flagged` becomes the Starred partition, leaving the chips `All`, `Unread`, `Priority`. Ctrl-click toggles a row and shift-click extends from the anchor over the visible order; the bar acts on the picked set, else the selected message, else the whole filter; `picked` lives in the shell's state bag beside `query`, `chip` and `more`, and `Row` passes the click event to `onSelect`. Opening an unread message marks it read through the write client, gated by `[email] read_on_open` in `config.toml` (the settings table accepts only `ui.*` and `modules.*`). `POST action/sync` runs the sync task through `run_action` on resource `gmail`, importing `tasks` inside the handler because `tasks.py` imports `routes.py`; `sync` writes the cursor `email.synced_at` on every successful run and `blank` reads it instead of `tasks.last_run`. Both page action paths catch and render the failure in the bar's label slot; `_resolve` accepts `{id}` as a one-element `ids`. A `queue` hook yields one row `Gmail consent expires <stamp>` when the token's remaining life is under `[email] consent_warn_days`, so Home warns before the outage. User labels: `email_labels(id, name, kind system|user, synced_at)` mirrored by `sync` through `GmailRead.labels`, verbs `label`, `unlabel` (`{label_id}`) and `create_label` (`{name}`) through `GmailWrite.create_label`, a read tool `email_labels` on both servers; `email_flag` stays the only write tool and no agent tool touches a label. `numbers` and `today` stay scoped to `INBOX`. Rejected: fourteen chips in one row, a checkbox column, a Gmail round-trip per partition, permanent delete (outside `gmail.modify`), a settings-table knob. Departures: no `Reply` (no compose); partition chips, label chips, `+ label`, `Sync` and multi-select are drawn nowhere in the artboard; `Sync` departs from "the user never presses a button whose only purpose is to make the system run" so a bulk action can be confirmed without waiting out the interval (owner, 2026-09-12). Still open: whether Purchases stays (the owner reserved the call) and whether the token warning stays in the first phase.

Fix: three changes through `/feature-flow`, in order. First the hue swap, `read_on_open`, multi-select, `{id}` in `_resolve`, the rendered error, `action/sync` with `email.synced_at`, the token warning and the two config keys (closes `Email and Education page actions fail silently` here and `Home posts a single id to email actions, which read ids` in the Home doc). Then the partitions with `is_purchase`, `includeSpamTrash` and the counts in `blank` and `context`. Then the labels. Tests run against `httpx.MockTransport` through `TRANSPORT`; `test_email_client_split` gains `create_label` and `labels` to the names forbidden in `tools.py` and asserts `GmailRead` has neither `modify` nor `create_label`. The `email` branch and `../otto-email` sit at landed work, so the branch takes another name unless they are removed first.
