# Chat

## Built

The owner's general conversations with Claude inside Otto: any topic, web search on demand, files in and out, every conversation kept until the owner deletes it. Not in the artboard.

| Piece | Current state |
|---|---|
| Facet | `chats`, title Chat, hue `#E0A06E`. Every row is type `conversation`; opened, it reads as the last four turns of what was said. Its verbs are `reopen`, which brings the conversation back as a drawer tab, then `delete`. There is no `queue` hook: a conversation waits on nobody, so the facet fills Recent and never Priority |
| Data | no table of its own: a conversation is an `app_sessions` row, its turns in `app_session_turns`, its files in `data/workspace/chat/<id>/`, created on the first turn, upload or `new`. The facet holds every conversation whichever agent held it, so `rows` and `_get` read a session by id alone and never by module; the drawer's own conversations are sessions under the name `otto` |
| Routes | `left` (query as one `LIKE` per word over the title and every turn's text, all required; page; ROWs by day of last activity, newest first, the title the tagger's or the first user line, `when` in the owner's own clock; it is the one read here still scoped to `module = 'chat'`), `item/{id}` (the ROW plus `busy`, the tail of the transcript and the files in the folder), `new` (an empty conversation, so files can be attached before the first message), `send` `{id?, text, files?}` → `{id, queued}` (no id creates the conversation; 400 on empty text or an attachment name not in the folder; 409 while a turn runs), `action/{verb}` → `delete` `{id}` (row, turns by cascade and folder; 409 while busy) and `reopen` `{id}` (clears `closed_at`; the turns were never removed), `upload/{id}` (multipart `file`, a plain name only, a duplicate name gets ` (2)`, 413 over `upload_max_mb`), `files/{id}`, `file/{id}/{name}`, `events/{id}` (server-sent events on key `chat:<id>`) |
| Turns | `send` stores the owner's words and hands the CLI the text plus a trailer naming the folder and the attached paths; the turn is a `session` job on resource `session:<id>`, so conversations run concurrently and one conversation's turns, tag job, upload and delete serialize. After the first completed turn of an untitled conversation `tag_session` runs without closing; the `tagged` event carries the title and tags and Graph counts the conversation from then on. Every resumed turn carries a replay preamble of the last `replay_chars` characters of the stored transcript, used only when the CLI has lost the conversation. Events `attached`, `deleted`, `tagged` |
| Reached by | the page asks `item/{id}` for the open row and runs `reopen` and `delete` through `POST /api/verb`. The drawer sends every turn through the platform's `/api/session/otto/send` and ends a conversation with `/clear`, which tags it and closes it; `send`, `new`, `upload`, `files` and `events/{id}` here answer nothing on screen |
| Hooks | `numbers` (conversations held under the module name `chat`), `rows` (every conversation as a ROW, the one that moved last first; its tags are the tagger's on the session, then any the owner added), `context` (count, the five most recent titles, the folder rule) |
| Agent | Chat's share of the one agent: skills `web` and `files`, built-ins `Write` and `Edit` on top of the read set, and no Otto tools of its own. Otto's tools are the union of every enabled module's, so a turn in the drawer reaches them all |
| Departures | title, hue and the speech-bubble icon are Otto's; `order` 1 ties with Email and the registry sorts stably from an alphabetical load, so the chats group heads the feed. The conversation is read in the page as an excerpt while the live one is held in the drawer. From the Summary: a chat is tagged after its first turn, not at a close it never has |

## Patches

### A conversation the drawer never held cannot be reopened

- Kind: bug
- Where: `app/modules/chat/routes.py` `_reopen`, `numbers` and `context`, against `app/api.py` `_open` and `_session`, and `app/static/drawer.js` `openConversation`
- Found: 09-21-2026, the one-page change
- Status: open

What happens: the facet lists every session, whatever module column it carries, but the drawer is the session module `otto`: `_open` and `_session` both select `WHERE module = ?`. `Reopen` on a conversation the drawer did not open clears `closed_at`, then `/api/session/otto` does not list it and `/api/session/otto/<id>` answers 404, so the tab never appears and the transcript draws empty; typing into it answers "no open session with that id". Every conversation from before this change, and every one a module's own pane held, is in that state. `numbers` and `context` count `module = 'chat'` for the same reason, so the counter reads a handful of old conversations while the facet lists them all, and Otto's own lines carry that number.

Expected: any conversation the facet lists comes back as a tab, and one count of them.

Fix: either `reopen` moves the session's `module` to `otto` as it clears `closed_at`, or the platform's session lookups take the id alone the way `_get` here now does. The first keeps the module column meaning who held the conversation; the second makes it decoration.

### A file cannot be handed to a conversation

- Kind: gap
- Where: `app/modules/chat/routes.py` `upload/{sid}`, `files/{sid}`, `send`; `app/static/drawer.js`; `app/api.py` `session_send`
- Found: 09-21-2026, the one-page change
- Status: open

What happens: files in and out is what Chat is for, and the folder under the workspace is still made and still named in every turn's trailer. The drawer sends through `/api/session/otto/send`, which takes text alone, and it draws no clip, no drop target and no chips, so nothing can put a file in the folder. The upload route answers only a caller outside the browser.

Expected: a file dropped on the composer reaches the open conversation's folder and the next message names it.

Fix: the drawer grows the clip and the drop target the old composer had, posting to a platform upload beside `session_send` (the folder belongs to the session, not to this module), and the attached names go into the turn's trailer as they do here.

### A conversation's own tags cannot be removed

- Kind: defect
- Where: `app/modules/chat/routes.py` `_tags`, against `app/api.py` `/api/tags/remove`
- Found: 09-20-2026, porting the Chat page to the new shell
- Status: open

What happens: the tagger writes a conversation's tags into `app_sessions.tags`, and the row surfaces them as its `tags`, so they are offered in the tag popup like any other. Removing one posts `/api/tags/remove`, which deletes from `app_tags` only, so the tag is still there after the refresh and nothing says why.

Expected: a tag shown as the owner's can be taken off, or is drawn as an identity tag that cannot.

Fix: have the tagger's tags land in `app_tags` alongside the session's JSON, so the platform's tag routes reach them.

### A file attached while Claude is answering sits there until the turn ends

- Kind: defect
- Where: `app/modules/chat/routes.py` `upload/{sid}`, against `app/runner.py`
- Found: 09-20-2026, restoring attachment to the ported page
- Status: open

What happens: the upload is an action on resource `session:<id>`, the same lock the running turn holds, so a file handed to a conversation while Claude is answering waits for the whole turn before it is written. The request stays open for as long as that takes, and one of the runner's three workers is held waiting.

Expected: a file can be handed to a conversation while it is busy, or the wait is visible.

Fix: the lock is there so that the turn and the upload cannot both invent a name in the folder. Either the upload takes a lock of its own on the folder rather than the session, which makes it independent of the turn, or the caller is told the file is waiting. The first is the daemon's call about what the session lock protects.
