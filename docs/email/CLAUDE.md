# Email

1. Uses gmail OAuth
2. Search bar/full ability to interact with inbox (Google chrome behaves very strangely when trying to do bulk deletes; I would like to resolve by explicitly using API here)
3. Agent only performs triage&sorting, prioritization and flagging of relevant items
4. Agent does NOT have the ability to write nor delete on its own. This needs to be a HARD CONSTRAINT determined by tooling or gmail api implementation. 

## Built

| Piece | Current state |
|---|---|
| Facet | `email`, title Email, hue `#E38A8A`. A message is type `email`; the consent notice `queue` raises is type `decision`, `taggable` false and carries no verb. A message's verbs, in the order they are drawn: `archive` while it is in the inbox, then `read`/`unread`, `star`/`unstar`, `open` in Gmail, and `trash` last and away from the first |
| Tables | `email_messages(n rowid, id Gmail id, thread_id, from_name, from_addr, to_addr, subject, snippet, internal_date, labels JSON, synced_at)`, `email_bodies(message_id, text, html, attachments JSON filenames)` filled on first open, `email_triage(message_id, priority high\|normal\|low, reason, ts, source scheduled\|session)`, `email_fts` (FTS5 over sender, subject and snippet, trigger-maintained) |
| Row | One `_row` for every list: the subject is the `title`, the sender the `snip` beside it, the Gmail snippet the `summary` under it, `when` local wall time so the page reads the day and the clock straight off the string, `fixed` the facet, `unread` and its inverse `dim`, `starred`, and `href`, the Gmail url `open` needs. `SELECT` joins `email_triage` and `email_bodies`, so a row carries its priority and its attachment names without a second query, and `_rows` reads the owner's tags for a whole list at once |
| Routes | `left` (`query`, chip All/Unread/Flagged/Priority over the inbox: `UNREAD`, `STARRED`, triage `high`; `limit`, 200 by default) returning `groups` of ROWs by day, `more` and the `read_on_open` knob; `item/{id}`; `action/{archive\|trash\|read\|unread\|star\|unstar}` with `{ids}`, `{id}` or `{filter: {query, chip}}` (400 when none selects anything); and `action/sync`, declared first so `action/{verb}` cannot swallow it, which runs the scheduler's own `tasks.sync` through `run_action` on resource `gmail` (a deferred import: `tasks.py` imports this module). One `_where` serves the list, the bulk actions and `email_search`; `query` goes through `email_fts` |
| Item | `body_of` fetches the message once through the read client into `email_bodies` (shared with `email_get`); on failure the snippet stands in, a `failed` event is written and the next open retries. The ROW plus `kv` — From, Priority with the triage's reason, and the attachment names, each only when the message carries it — and `body`, the sanitized html, or the plain text as paragraphs when there is none |
| Body | `body.py`: `extract` gives text (plain parts, else the html as text, else the snippet), sanitized html (`None` when nothing is visible) and attachment names; no attachment is ever fetched. `sanitize` keeps a fixed tag set bare (integer `colspan`, `rowspan`, `start` only), drops scripts, styles, forms, media and anything hidden inline, writes a link as its text with the raw URL in a `title` for http, https, mailto and tel, and an image as its alt text only when that text is not `BOILERPLATE` (the fallback sentence for a client that blocks images, and spacer, logo and icon labels). A table's own tags are held as marks until it closes (`_resolve_table`): a table whose rows each hold at most one cell that says anything is layout, so its cells become `div` blocks and the table, its rows and any `tbody` go, while a table with a row of two speaking cells stays a table, so a label keeps its value beside it; nesting resolves inside out. `_tidy` then drops cells, rows and blocks holding nothing but whitespace and collapses runs of breaks, three passes, because a dropped cell can empty its row. Measured over the owner's own promotional mail: raw URLs were 58% of the reader's text |
| Actions | labels change through `batchModify` in chunks of 1000, then the local rows in the same job; `trash` is Gmail's Trash (the `gmail.modify` scope cannot delete permanently); events `archived`, `trashed`, `marked read`, `marked unread`, `starred`, `unstarred` name the subject for one id, else `N messages · chip`. The page runs one row's verb through `POST /api/verb`, which posts `{id}`; `{ids}` and `{filter}` stay for the API and the agent |
| Hooks | `numbers` (unread), `rows` (the inbox as ROWs, newest first, capped at `limit` and narrowed by `chip` and `query`, both defaulted, since the feed asks for the limit alone), `today` (inbox mail of the local day), `queue` (the consent notice while the refresh token is inside `[email] consent_warn_days`, or already dead, naming the consent command), `item`, `context` (counts, last sync, ten newest, high-priority with reasons) |
| Tools | read: `email_search`, `email_get` (text and attachment names), `email_triage`; write: `email_flag`, which upserts Otto's triage row with source `session`. No tool reaches Gmail. `test_email_client_split` forbids every writing name in `tasks.py` and `tools.py` |
| Schedules | `email.sync` every 5m on resource `gmail`: first a `backfill_days` backfill (`newer_than`, ten metadata fetches in flight) committed in pages of 100 under the cursor `email.backfill` (`<historyId>\|<started>`, resumed by the next run), then Gmail history from `email.history`, re-fetching added and relabelled ids and deleting removed ones; a 404 on that id (expired) backfills again. `email.triage` every 24h inside the nightly window prioritizes `triage_batch` untriaged inbox messages with a JSON-array reply, `INSERT OR IGNORE` so a session flag is never overwritten, cursor `email.triage` |
| Gmail | `gmail.py`: the token, refreshed 60 s before expiry and written back; `save_token` records `refresh_expires_at` absolutely whenever Google sends a refresh-token lifetime, and `consent_expires` reads it, so the queue hook can warn without knowing when the file was written. `GmailRead` (`profile`, `list_ids`, `metadata`, `body`, `history`) for tasks and body fetches; `GmailWrite` adds `batchModify` and is reachable only from action routes; `TRANSPORT` is the test seam; the `consent` command. A quota refusal (429, or 403 naming the quota) pauses every call in flight together for 61 s and retries up to five times |
| Departures | no `Reply` (no compose) and no `Snooze` (no API); the chips and the `Sync now` button went with the page, so the mailbox is narrowed by the search bar's tags and words like every other facet; rows picked together take tags and nothing else, so the bulk verbs live on in the route for the API and the agent alone; `read_on_open` is still answered by `left` and nothing acts on it, so opening a message no longer writes to Gmail |

## Patches

### Gmail refresh token expires every 7 days

- Kind: gap
- Where: Email requirement 1 (Gmail OAuth); `data/secrets/token.json`, `app/modules/email/gmail.py`
- Found: 2026-09-09, sync-architecture
- Status: open, owner action; recurring while the consent screen stays in Testing

What happens: the OAuth consent screen for project `central-shift-507603-b1` is in Testing, so every refresh token Google issues lives 7 days. The current one carries `refresh_expires_at` 2026-09-25T00:32:21Z and dies about 09-24-2026 20:32 local. Once it dies, `email.sync` fails every five minutes (`invalid_grant`), `email.triage` has nothing new to read, and every action route fails.

Expected: a refresh token with no expiry, so the mirror and the bulk actions keep working without the owner touching them.

Fix: every 7 days meanwhile, `.venv/Scripts/python.exe -m app.modules.email.gmail consent`. Permanently, set the consent screen to Production in the Cloud console for `central-shift-507603-b1`, confirm the redirect `http://localhost:8756/m/email/api/oauth/callback` is still registered on the client, then run `python -m app.modules.email.gmail consent` once. The new `token.json` should have no `refresh_token_expires_in`.

### The mailbox is only the inbox: no partitions, no labels

- Kind: gap
- Where: Email requirement 2; `app/modules/email/routes.py` (`_where` hard-codes `INBOX`), `app/modules/email/gmail.py` (`GmailRead` has no `labels`, `list_ids` omits spam and trash), `app/modules/email/tasks.py`
- Found: 2026-09-12, the owner's request
- Status: open, not started

What happens: `_where` puts `INBOX` into every query, so Spam, Trash and Gmail's categories cannot be reached from Otto at all, and the owner's own labels are neither shown nor applied nor created.

Expected: eleven partitions from Gmail's own labels (Inbox, Starred, Important, Personal, Social, Updates, Promotions, Forums, Purchases, Spam, Trash), `_where` taking the partition instead of forcing `INBOX`, the backfill passing `includeSpamTrash=true`, and Purchases as a column `is_purchase` that `sync` sets from one `list_ids("category:purchases")` per run (verified live 2026-09-12: 412 messages and no label id; `category:reservations` answers 0 and is out). Then user labels: `email_labels(id, name, kind system|user, synced_at)` mirrored by `sync` through a new `GmailRead.labels`, verbs `label`, `unlabel` (`{label_id}`) and `create_label` (`{name}`) through a new `GmailWrite.create_label`, and a read tool `email_labels`. `email_flag` stays the only write tool and no agent tool touches a label. `numbers` and `today` stay scoped to `INBOX`. A partition is a tag on the row now that one feed carries every module, so the fourteen chips the page could not hold are a question of which tags the search bar offers. Rejected: a checkbox column, a Gmail round-trip per partition, permanent delete (outside `gmail.modify`).

Fix: two changes through `/feature-flow`, partitions first, then labels. `test_email_client_split` gains `create_label` and `labels` to the names forbidden in `tools.py` and asserts `GmailRead` has neither `modify` nor `create_label`.

### Open in Gmail answers "unknown action open"

- Kind: bug
- Where: `app/modules/email/routes.py` (`_verbs`, `VERBS`), against `app/api.py` `POST /api/verb`
- Found: 09-21-2026, the one-page change
- Status: open

What happens: every message offers `open`, and the row carries the message's Gmail url as `href`. Nothing reads `href`: the browser posts every verb to `/api/verb`, which hands it to `action/{verb}`, and `open` is not in `VERBS`, so the press answers 404 and says so. The browser does know what to do with a url — it opens `url` when a verb answers with one — so only the daemon half is missing. Since the one-page change the browser handles `open` itself: `core.js` maps it to `away`, which reads `href` and calls `window.open`, so the 404 no longer happens. What is left is that the link opens in the app's own Chrome profile, filed in the app doc as "Open in Gmail, and every link the page opens, lands in a browser that is not mine".

Expected: `Open in Gmail` opens the message in Gmail.

Fix: serve `open` beside the six label verbs, returning `{"url": "https://mail.google.com/mail/u/0/#all/<id>"}` and writing no event, and drop `href` from the row, which nothing else reads. Second Brain's link `open` is the same shape and needs the same thing.

### A half-typed word finds nothing until it is finished

- Kind: defect
- Where: `app/modules/email/routes.py` (`_fts`), `app/modules/second_brain/routes.py` (`_fts`)
- Found: 09-20-2026, restoring the daemon-side search
- Status: open

What happens: `_fts` wraps each typed word in quotes, so the index is asked for that whole word, and `l`, `lu` and `lun` each find nothing where `lunch` finds the message. It is `email_search`'s path now that the page asks the daemon for nothing. Second Brain's `_fts` is the same three lines and behaves the same way.

Expected: a word narrows as it is typed, the way a substring search does.

Fix: make the last word of the query a prefix (`lun*`) and leave the earlier ones whole, in both `_fts` helpers, so a finished word still means that word.

### The consent notice waits on the owner and offers nothing to press

- Kind: gap
- Where: `app/modules/email/routes.py` (`queue`)
- Found: 2026-09-20, the UI port review
- Status: open, owner decision

What happens: the row that says Gmail consent is expiring is the one row whose whole purpose is to make the owner act, and it carries no verbs, so it is a line of text with nothing beside it. The command it names has to be retyped by hand.

Expected: the notice offers a press that puts the consent command in the clipboard.

Fix: the verb shape is a `[verb, label]` pair run through `/api/verb`, and copying text is not that, so the owner picks. Either `/api/verb` answers a field the browser copies, the way it already answers `url` to open, or the notice gets a real verb and the daemon runs the consent flow itself, which it cannot do today: `gmail.py consent` needs a terminal and a browser.

### Nothing can ask for a sync

- Kind: gap
- Where: `app/modules/email/routes.py` (`action/sync`, `_verbs`)
- Found: 09-21-2026, the one-page change
- Status: open

What happens: `action/sync` still runs the scheduler's own task on the `gmail` lock, and nothing reaches it. The `Sync now` button went with the page, no row lists `sync` among its verbs, and no tool asks for it, so after a bulk action the owner waits out the five-minute interval to see the mailbox settle. The button was the owner's own call on 2026-09-12.

Expected: a sync can be asked for without waiting for the clock.

Fix: a verb the facet serves rather than a row's — the palette lists the open row's verbs only — so this needs a place for a verb that belongs to a facet instead of an item, or `sync` becomes a verb on every message, which is a lie about what it acts on.

### Reading a message no longer marks it read

- Kind: defect
- Where: `app/modules/email/routes.py` (`left`'s `read_on_open`, `item_route`), `[email] read_on_open` in `config.toml`
- Found: 09-21-2026, the one-page change
- Status: open

What happens: `read_on_open` is on, and the page that acted on it is gone. Opening a message fetches `item/{id}`, which writes nothing to Gmail, so a message read in Otto stays unread there and in the counter, and the setting now describes nothing.

Expected: what the setting says: opening an unread message marks it read in Gmail, once per message.

Fix: `item_route` posts `read` for an unread message when the knob is on, which puts the rule where the message is actually opened and takes `read_on_open` out of `left`'s answer; or the knob goes.
