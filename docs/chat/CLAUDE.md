# Chat

## Built

The owner's general conversations with Claude inside Otto: any topic, web search on demand, files in and out, every conversation kept until the owner deletes it. Not in the artboard.

| Piece | Current state |
|---|---|
| Data | no table of its own: a conversation is an `app_sessions` row with module `chat`, never closed, its turns in `app_session_turns`; its files live in `data/workspace/chat/<id>/`, created on the first turn, upload or `new` |
| Routes | `left` (query as one `LIKE` per word over the title and every turn's text, all required; page; ROWs by day of last activity, newest first, the title the tagger's or the first user line, `when` in the owner's own clock so a conversation is filed under their day and shows their time; beside the groups, the one verb every conversation offers, so a button on a row asks what the pane's button asks), `item/{id}` (the ROW plus `busy`, `turns`, `files` and the one action, `delete`), `new` (an empty conversation, so files can be attached before the first message), `send` `{id?, text, files?}` → `{id, queued}` (no id creates the conversation; 400 on empty text or an attachment name not in the folder; 409 while a turn runs), `action/{verb}` → `delete` `{id}` (row, turns by cascade and folder; 409 while busy), `upload/{id}` (multipart `file`, a plain name only, a duplicate name gets ` (2)`, 413 over `upload_max_mb`), `files/{id}`, `file/{id}/{name}`, `events/{id}` (server-sent events on key `chat:<id>`) |
| Turns | `send` stores the owner's words and hands the CLI the text plus a trailer naming the folder and the attached paths; the turn is a `session` job on resource `session:<id>`, so conversations run concurrently and one conversation's turns, tag job, upload and delete serialize. After the first completed turn of an untitled conversation `tag_session` runs without closing; the `tagged` event carries the title and tags and Graph counts the conversation from then on. Every resumed turn carries a replay preamble of the last `replay_chars` characters of the stored transcript, used only when the CLI has lost the conversation. Events `attached`, `deleted`, `tagged` |
| Hooks | `numbers` (conversations), `rows` (every conversation as a ROW, the one that moved last first; its tags are the tagger's on the session, then any the owner added), `context` (count, the five most recent titles, the folder rule). No `today`, `queue` or `item`: a conversation opens on its own page |
| Agent | `builtins` `Write` and `Edit` on top of the read set; no Bash and no Otto tools. Skills `web`, `files`; placeholder `Ask anything…`. Adding a built-in later is a word in `Agent.builtins`; any Otto tool is its name in the manifest |
| Page | One row per conversation, grouped by the day it last moved, newest first: the title, its tags, and the time of day for one that moved today. Hovering a row offers Tag and a Delete that asks first; `+` in the header opens a blank conversation and puts the cursor in it. The pane holds the conversation: title, day, tags, the files in its folder as links, then the whole transcript — the owner's turns as bubbles, Claude's through markdown, each tool call with its status — with the reply arriving a piece at a time. Under it a box sends the next message into that session, Enter sends and Shift+Enter breaks a line; Delete, the one action the item offers, sits at the end. Attaching lives on that box, the only place the conversation's folder is in reach: a file picked through the clip beside it, or dropped anywhere on it, uploads into the folder at once and waits above the box as a chip the next message names, its `×` taking it off that message and leaving the file in the folder; one larger than `upload_max_mb` is refused by the daemon and the refusal is said on screen under the file's own name. A finished turn rebuilds the pane and the box keeps the half-typed line, the files waiting on it and the caret in it. A stream that reconnects subscribes to a fresh queue, so the frames it missed are lost; for as long as a conversation is open, and wherever its pane was opened from, the page asks the daemon for it again on the shell's refresh interval, and that answer settles the transcript and whether a turn is running, so a dropped `idle` never leaves the box locked. The stream closes as soon as the conversation is no longer the open row, wherever the pane was opened from |
| Departures | title, hue `#d9915b`, speech-bubble icon and rail order 1 (ties with Email; the registry loads packages alphabetically and sorts stably, so Chat sits first after Home) are Otto's; the conversation opens in the shell's detail pane, transcript and composer together, while the drawer beside it stays the page's agent. From the Summary: a chat is tagged after its first turn, not at a close it never has |

## Patches

### A conversation's own tags cannot be removed

- Kind: defect
- Where: `app/modules/chat/routes.py` `_tags`, against `app/api.py` `/api/tags/remove`
- Found: 09-20-2026, porting the Chat page to the new shell
- Status: open

What happens: the tagger writes a conversation's tags into `app_sessions.tags`, and the page surfaces them as the row's `tags`, so they are offered in the tag popup like any other. Removing one posts `/api/tags/remove`, which deletes from `app_tags` only, so the tag is still there after the refresh and nothing says why.

Expected: a tag shown as the owner's can be taken off, or is drawn as an identity tag that cannot.

Fix: have the tagger's tags land in `app_tags` alongside the session's JSON, so the platform's tag routes reach them.

### The typed search never reaches what a conversation says

- Kind: gap
- Where: `app/static/core.js` `applyTokens` and the search bar, against `app/modules/chat/routes.py` `left`'s `query`
- Found: 09-20-2026, fixing the review of the ported Chat page
- Status: open

What happens: `left` takes a `query` and matches every turn's text, but no page ever sends one. Typing in the search bar re-renders the rows the shell already holds and filters them over the title and the tags alone, so a word that occurs inside a conversation but not in its title empties the list and says nothing matches, while the route would have found it.

Expected: a word the owner remembers from inside a conversation finds that conversation.

Fix: the shell hands the typed query to `load()` and reloads the page's data when it changes, and its own text filter stands down for a page whose route does the searching. That is one change in `core.js` for every module, not Chat's alone, which is why it is not made here.

### Only the newest page of conversations can be reached

- Kind: gap
- Where: `app/static/pages/chat.js` `load`, against `app/modules/chat/routes.py` `left`'s `page` and `more`
- Found: 09-20-2026, fixing the review of the ported Chat page
- Status: open

What happens: `left` returns at most `ui.page_size` conversations and says `more` when it held some back. The page asks for the first page and reads neither, so everything older is unreachable from the page and nothing on screen shows there is more.

Expected: the older conversations can be reached.

Fix: the shell grows one way to ask for the next page — a button under the list, or the list asking for itself as it is scrolled — and pages pass `page` through `load()`. Every module's `left` already returns `more`, so which of the two it is, and whether the number held back is shown at all, is the owner's call rather than Chat's.

### A dropped `tagged` frame leaves the open pane's title behind

- Kind: defect
- Where: `app/static/pages/chat.js` `repair` and `reload`
- Found: 09-20-2026, the recheck of the pane wedging busy
- Status: open

What happens: the tagger's title and tags reach the page only as the `tagged` event, which calls `reload`. A stream that reconnects subscribes to a fresh queue, so that frame can be lost like any other. The clock's repair asks the daemon for the conversation again and settles the transcript and the box, but it writes only those, so the pane's heading keeps the first user line while the row in the list beside it already carries the tagger's title. Reopening the conversation clears it.

Expected: the heading catches up with the row.

Fix: either the repair notices the answer's title differs from the one on screen and reloads the whole item, which rebuilds the pane under a half-typed message, or the pane reads the title from the row rather than from the fetched item. Which of the two depends on whether a rebuild under the cursor is acceptable.

### A file attached while Claude is answering sits there until the turn ends

- Kind: defect
- Where: `app/modules/chat/routes.py` `upload/{sid}`, against `app/runner.py`
- Found: 09-20-2026, restoring attachment to the ported page
- Status: open

What happens: the upload is an action on resource `session:<id>`, the same lock the running turn holds, so a file picked while Claude is answering waits for the whole turn before it is written. The request stays open for as long as that takes, the chip does not appear, nothing on screen says why, and one of the runner's three workers is held waiting.

Expected: a file can be handed to a conversation while it is busy, or the wait is visible.

Fix: the lock is there so that the turn and the upload cannot both invent a name in the folder. Either the upload takes a lock of its own on the folder rather than the session, which makes it independent of the turn, or the page draws the file as waiting until the daemon answers. The first is the daemon's call about what the session lock protects.
