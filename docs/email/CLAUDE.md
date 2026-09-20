# Email

1. Uses gmail OAuth
2. Search bar/full ability to interact with inbox (Google chrome behaves very strangely when trying to do bulk deletes; I would like to resolve by explicitly using API here)
3. Agent only performs triage&sorting, prioritization and flagging of relevant items
4. Agent does NOT have the ability to write nor delete on its own. This needs to be a HARD CONSTRAINT determined by tooling or gmail api implementation. 

## Built

| Piece | Current state |
|---|---|
| Tables | `email_messages(n rowid, id Gmail id, thread_id, from_name, from_addr, to_addr, subject, snippet, internal_date, labels JSON, synced_at)`, `email_bodies(message_id, text, html, attachments JSON filenames)` filled on first open, `email_triage(message_id, priority high\|normal\|low, reason, ts, source scheduled\|session)`, `email_fts` (FTS5 over sender, subject and snippet, trigger-maintained) |
| Row | One `_row` for every list: `{id, module, title subject, from sender name else address, snippet, when local wall time, tags, unread, starred, priority, attachments}`. The sender and the subject stay apart, so the page can seat them in cells of their own or join them itself when the reader is open. `when` is local because the page reads the day and the clock straight off the string. `SELECT` joins `email_triage` and `email_bodies`, so a row carries its priority and its attachment names without a second query, and `_rows` reads the owner's tags for a whole list at once |
| Routes | `left` (`query`, chip All/Unread/Flagged/Priority over the inbox: `UNREAD`, `STARRED`, triage `high`; `limit`, 200 by default) returning `groups` of ROWs by day, `more`, and the `read_on_open` knob; `item/{id}`; `action/{archive\|trash\|read\|unread\|star\|unstar}` with `{ids}`, `{id}` or `{filter: {query, chip}}` (400 when none selects anything); and `action/sync`, declared first so `action/{verb}` cannot swallow it, which runs the scheduler's own `tasks.sync` through `run_action` on resource `gmail` (a deferred import: `tasks.py` imports this module). A chip and what is typed are both served by the daemon, never by filtering a page of results, so each narrows the whole mailbox: `query` goes through `email_fts`, which indexes sender, subject and snippet, and `more` says rows were held back. One `_where` serves the list, the bulk actions and `email_search` |
| Item | `body_of` fetches the message once through the read client into `email_bodies` (shared with `email_get`); on failure the snippet stands in, a `failed` event is written and the next open retries. The ROW plus `from_addr`, `to_addr`, `text` (`subject` + body, for Home and Feedback), `body`, `html`, `in_inbox`, `reason`, and `actions` in the order the pane draws them: `archive` primary while in the inbox, read/unread, star/unstar, `open` as a Gmail href, then `trash` with its confirm, last and away from the primary one; both inbox verbs are marked `removes`, since the row leaves the inbox list |
| Body | `body.py`: `extract` gives text (plain parts, else the html as text, else the snippet), sanitized html (`None` when nothing is visible) and attachment names; no attachment is ever fetched. `sanitize` keeps a fixed tag set bare (integer `colspan`, `rowspan`, `start` only), drops scripts, styles, forms, media and anything hidden inline, writes a link as its text with the raw URL in a `title` for http, https, mailto and tel, and an image as its alt text only when that text is not `BOILERPLATE` (the fallback sentence for a client that blocks images, and spacer, logo and icon labels). A table's own tags are held as marks until it closes (`_resolve_table`): a table whose rows each hold at most one cell that says anything is layout, so its cells become `div` blocks and the table, its rows and any `tbody` go, while a table with a row of two speaking cells stays a table, so a label keeps its value beside it; nesting resolves inside out. `_tidy` then drops cells, rows and blocks holding nothing but whitespace and collapses runs of breaks, three passes, because a dropped cell can empty its row. Measured over the owner's own promotional mail: raw URLs were 58% of the reader's text |
| Actions | labels change through `batchModify` in chunks of 1000, then the local rows in the same job; `trash` is Gmail's Trash (the `gmail.modify` scope cannot delete permanently); events `archived`, `trashed`, `marked read`, `marked unread`, `starred`, `unstarred` name the subject for one id, else `N messages · chip`. Opening a message posts `read` for it when `[email] read_on_open` is set, once per message per window; opening means a press and a release on the same row, and the click that ends the gesture takes the press back, so a drag, a cancelled press, a press that closes the pane, and the keyboard walking the list never write to Gmail |
| Hooks | `numbers` (unread), `rows` (the inbox as ROWs, newest first, capped at `limit` and narrowed by `chip` and `query`; the list route and the cross-module lists share it), `today` (inbox mail of the local day), `queue` (one ROW carrying the fixed tag `notice` when the refresh token is inside `[email] consent_warn_days`, or already dead, naming the consent command; Home lists it), `item`, `context` (counts, last sync, ten newest, high-priority with reasons) |
| Tools | read: `email_search`, `email_get` (text and attachment names), `email_triage`; write: `email_flag`, which upserts Otto's triage row with source `session`. No tool reaches Gmail. `test_email_client_split` forbids every writing name in `tasks.py` and `tools.py` |
| Schedules | `email.sync` every 5m on resource `gmail`: first a `backfill_days` backfill (`newer_than`, ten metadata fetches in flight) committed in pages of 100 under the cursor `email.backfill` (`<historyId>\|<started>`, resumed by the next run), then Gmail history from `email.history`, re-fetching added and relabelled ids and deleting removed ones; a 404 on that id (expired) backfills again. `email.triage` every 24h inside the nightly window prioritizes `triage_batch` untriaged inbox messages with a JSON-array reply, `INSERT OR IGNORE` so a session flag is never overwritten, cursor `email.triage` |
| Gmail | `gmail.py`: the token, refreshed 60 s before expiry and written back; `save_token` records `refresh_expires_at` absolutely whenever Google sends a refresh-token lifetime, and `consent_expires` reads it, so the queue hook can warn without knowing when the file was written. `GmailRead` (`profile`, `list_ids`, `metadata`, `body`, `history`) for tasks and body fetches; `GmailWrite` adds `batchModify` and is reachable only from action routes; `TRANSPORT` is the test seam; the `consent` command. A quota refusal (429, or 403 naming the quota) pauses every call in flight together for 61 s and retries up to five times |
| Page | `pages/email.js`, the densest list the shell draws: the inbox by day, newest first, each row a checkbox, an unread dot, the star, the sender, the subject with its tags inline, and the time for mail that arrived today; an unread row is `.unread`, a read one `.dim`. Archive, Tag and Trash sit under the pointer on a row, Trash asking first. The chips All, Unread, Flagged and Priority are served by the daemon, so picking one reloads the list rather than narrowing the rows in hand; `load` tags each list with the chip it asked for and asks again when the chip moved while the request was out, so a quick change of mind cannot leave the wrong mailbox on screen. The page declares `serverQuery`, so the shell hands it what is typed instead of filtering the rows in hand: `load` sends it as `query` and the whole mailbox is searched, and new words start the list over at its first 200. While the daemon says `more`, a `More` button asks for another 200 on top of what is shown. `Sync now` runs `action/sync`. Ctrl click picks rows; the bar over the list then tags, archives or trashes the set. Opening a row splits the track: the sender column collapses into the title and the pane carries the subject, the date with the clock in the format Settings holds, the tags, then From, Priority with the triage's reason and the attachment names, each drawn only when the message carries it, the sanitized html under the stylesheet's `.mail` rules or the plain text in `.prose`, and the buttons `item` offers — the primary one in the hue, a confirming one subtly red and asking through the shared popover, a `href` one opening Gmail |
| Departures | `Unread` chip restored beside `Priority`; no `Reply` (no compose) and no `Snooze` (no API); the old sticky action bar is gone — one row's verbs live on the row, a set's on the bulk bar, and the open message's come from `item`, so nothing acts on the whole filter from the page any more (the `{filter}` body stays for the agent and the API); `Sync now` departs from the Daemon contract's "the user never presses a button whose only purpose is to make the system run" so a bulk action can be confirmed without waiting out the five-minute interval (owner, 2026-09-12); multi-select and the sync control are drawn nowhere in the artboard |

## Patches

### Gmail refresh token expires every 7 days

- Kind: gap
- Where: Email requirement 1 (Gmail OAuth); `data/secrets/token.json`, `app/modules/email/gmail.py`
- Found: 2026-09-09, sync-architecture
- Status: open, owner action; recurring while the consent screen stays in Testing

What happens: the OAuth consent screen for project `central-shift-507603-b1` is in Testing, so every refresh token Google issues lives 7 days. The current one carries `refresh_expires_at` 2026-09-25T00:32:21Z and dies about 09-24-2026 20:32 local. Once it dies, `email.sync` fails every five minutes (`invalid_grant`), `email.triage` has nothing new to read, and every action route on the Email page fails. The owner declined Production, so this repeats every 7 days.

Expected: a refresh token with no expiry, so the mirror and the bulk actions keep working without the owner touching them.

Fix: every 7 days meanwhile, `.venv/Scripts/python.exe -m app.modules.email.gmail consent`. Permanently, set the consent screen to Production in the Cloud console for `central-shift-507603-b1`, confirm the redirect `http://localhost:8756/m/email/api/oauth/callback` is still registered on the client, then run `python -m app.modules.email.gmail consent` once. The new `token.json` should have no `refresh_token_expires_in`.

### The mailbox is only the inbox: no partitions, no labels

- Kind: gap
- Where: Email requirement 2; `app/modules/email/routes.py` (`_where` hard-codes `INBOX`), `app/modules/email/gmail.py` (`GmailRead` has no `labels`, `list_ids` omits spam and trash), `app/modules/email/tasks.py`, `app/static/pages/email.js`
- Found: 2026-09-12, the owner's request
- Status: open, not started

What happens: `_where` puts `INBOX` into every query, so Spam, Trash and Gmail's categories cannot be reached from Otto at all, and the owner's own labels are neither shown nor applied nor created.

Expected: eleven partitions from Gmail's own labels (Inbox, Starred, Important, Personal, Social, Updates, Promotions, Forums, Purchases, Spam, Trash) as a chip row, `_where` taking the partition instead of forcing `INBOX`, the backfill passing `includeSpamTrash=true`, and Purchases as a column `is_purchase` that `sync` sets from one `list_ids("category:purchases")` per run (verified live 2026-09-12: 412 messages and no label id; `category:reservations` answers 0 and is out). Then user labels: `email_labels(id, name, kind system|user, synced_at)` mirrored by `sync` through a new `GmailRead.labels`, verbs `label`, `unlabel` (`{label_id}`) and `create_label` (`{name}`) through a new `GmailWrite.create_label`, and a read tool `email_labels`. `email_flag` stays the only write tool and no agent tool touches a label. `numbers` and `today` stay scoped to `INBOX`. Rejected: fourteen chips in one row, a checkbox column, a Gmail round-trip per partition, permanent delete (outside `gmail.modify`).

Fix: two changes through `/feature-flow`, partitions first, then labels. `test_email_client_split` gains `create_label` and `labels` to the names forbidden in `tools.py` and asserts `GmailRead` has neither `modify` nor `create_label`.

### A half-typed word finds nothing until it is finished

- Kind: defect
- Where: `app/modules/email/routes.py` (`_fts`), `app/modules/second_brain/routes.py` (`_fts`)
- Found: 09-20-2026, restoring the daemon-side search
- Status: open

What happens: `_fts` wraps each typed word in quotes, so the index is asked for that whole word. The shell asks again a moment after each keystroke, so `l`, `lu` and `lun` each say nothing matches and only `lunch` finds the message. Second Brain's `_fts` is the same three lines and behaves the same way.

Expected: a word narrows as it is typed, the way a substring search does.

Fix: make the last word of the query a prefix (`lun*`) and leave the earlier ones whole, in both `_fts` helpers, so a finished word still means that word. It widens what the index answers, which is why it is filed rather than folded into the restore.

### The consent notice waits on the owner and offers nothing to press

- Kind: gap
- Where: `app/modules/email/routes.py` (`queue`), `app/static/pages/home.js` (`run`, `rowActs`), `app/static/pages/email.js` (`actionBtn`)
- Found: 2026-09-20, the UI port review
- Status: open, owner decision

What happens: the queue row that says Gmail consent is expiring carries no `actions`, and Home draws a row's buttons only from that field, so the one row whose whole purpose is to make the owner act is a line of text with nothing beside it. Home's fallback asks Email's `item` hook for the verbs and gets a 404, because `consent` is not a message id. The preview gave this row a `Copy command` button.

Expected: the notice offers that button, so the consent command reaches the clipboard in one press.

Fix: the shape Home and Email share knows two kinds of action, a `verb` posted to `/api/<module>/action/<verb>` and an `href` that opens, and copying text is neither, so the owner picks. Either a third kind lands in that shape, which is Home's `run` and Email's `actionBtn` together, or the notice gets a real verb and the daemon runs the consent flow itself, which it cannot do today: `gmail.py consent` needs a terminal and a browser. An action added to the row before then would post a verb that does not exist.

### The reader's own stylesheet is written into the page at runtime

- Kind: defect
- Where: `app/static/pages/email.js` (`MAIL`, `ensureStyles`), `app/static/styles.css`
- Found: 2026-09-20, the UI port review
- Status: open, not started

What happens: the twenty rules that give a sanitized message back its shape live as a string in the page module and are appended to `document.head` the first time a message is opened. Every other page's look is in `styles.css`; Email is the only one carrying CSS of its own.

Expected: one stylesheet holds the look, the page module holds behaviour.

Fix: move the `MAIL` rules into `styles.css` under `.mail` and drop `ensureStyles` with its call in `detail`. Nothing else changes: the variables the block uses all exist there and its specificity over `.dbody .prose` is already what the rules assume.
