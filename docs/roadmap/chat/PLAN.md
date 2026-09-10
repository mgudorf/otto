# Chat Plan

Status: planning, 2026-09-10.

Chat is the page where the owner talks to Claude the way they do in the Claude desktop app: any topic, web search on demand, files in and out, every conversation kept and findable, without leaving Otto. Without it the owner keeps two apps open, and the Search page stays a rail entry whose one interactive job (ask the web) the chat does better.

## Sources

| Source | Governs |
|---|---|
| `docs/ARCHITECTURE.md` Summary (several conversations; a closed session is tagged and reaches Graph), Daemon requirements and Mechanisms, Config, Claude (`session_turn`, `oneshot`, sessions, budget), Module contract, Home page requirement 2, Search, System, UI frame contract and Departures | what a conversation is, which client each path gets, the wire shapes, hues and rail order, what Home must keep showing |
| `docs/design/Personal Dashboard App.dc.html` lines 23–26 (rail icons), 320–326 (session pane: raised user bubble at 85%, `▸ tool · status` line), 349–356 (pane presets) | the transcript's visual shape and the icon style. No chat page exists in the artboard |
| `app/claude.py` | `_args`, `session_turn`, `oneshot`, `events_from`, `READ_BUILTINS`; the seam every turn goes through |
| `app/api.py` sessions block, `app/static/session.js` | the turn job, on-event persistence, busy state, `Broadcast`, `event_stream`, the closer and tagger: extracted, not rewritten |
| `app/modules/__init__.py`, `app/modules/home/routes.py`, `app/static/shell.js`, `app/static/pages/settings.js`, `app/daemon.py` | `Agent` and `Manifest`, Home's `_enabled`, the `PAGES` map and RIGHT track, module toggles, setting seeds |
| `app/modules/web_search/*`, `app/static/pages/web_search.js`, `docs/roadmap/web_search/PLAN.md` | what the owner asked to remove (the page) and keep (nightly run, tables, hooks, decisions, tools); its Phase 3 write tools land here |
| `app/modules/system/tasks.py` | `prune_sessions`, which would delete closed chats after `sessions_kept_days` |
| `app/static/md.js` | `Markdown` for model turns |
| `docs/gaps/session-tabs-deferred.md`, `docs/gaps/search-topics-not-entered.md` | the module panes stay single-session (that gap is untouched); the topics gap's fix path becomes the chat agent |
| This session's probes (2026-09-10) | `Write` under the daemon's flags; the `--include-partial-messages` stream shape |

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | A module `chat` with a page. A conversation is a `sessions` row with module `chat`, several open at once; its turns are `session_turns` | the tables, the tagger, Graph's reading of `sessions.tags` and the prune task already exist; a conversation is a session with a page instead of a pane |
| 2 | MIDDLE is the conversation (transcript and composer), LEFT the conversation list, RIGHT the conversation's folder | the pane is 22.8% of the window; a chat the owner lives in needs the widest track. On this page the agentic window is MIDDLE (departure, named below) |
| 3 | Every turn runs through the platform's session machinery, extracted from the `api.py` route into helpers keyed by session id and broadcast key | one implementation of persistence, busy state, events and tagging; the module panes keep one open session each and the tabs gap stays its own item |
| 4 | Agent tools: the read built-ins plus `Write` and `Edit`, declared as `Agent.builtins` and passed on session turns only; MCP `search_findings`, `search_topics` (read), `search_topic_add`, `search_topic_remove` (write). No Bash | `Write` verified today under the daemon's flags; `--restricted` confines file tools to the workspace. Bash is not confined and every run has `--permission-prompts none`; Science's kernels are the code path |
| 5 | Attachments are files: an upload lands in `data/workspace/chat/<id>/`, the prompt sent to the CLI names that folder and the attached paths, the agent Reads them and saves what it makes there; RIGHT lists the folder | the CLI reads images and PDFs natively; one folder is the conversation's shelf for both directions; the stored user turn stays the owner's words |
| 6 | `web_search` keeps tables, nightly run, hooks, `item`, `agree` / `disagree` and read tools; loses page, agent, `left`, `blank`, topic routes (`page=False`, `agent=None`); topics are edited by the chat agent through the two new write tools | the owner's call: on-demand search is the chat's, the nightly search still feeds Home's Review, and topics need exactly one entry point |
| 7 | Home aggregates any module with hooks, page or not; `/api/shell` lists page-less modules with `page: false`; rail, the `shown` toggle and the start-page list filter on `page`; the `runs` toggle stays for any module with tasks | Review must keep listing findings, hue and icon must resolve for its rows, and the owner keeps the per-module nightly switch decided on 2026-09-10 |
| 8 | Tables stay where they are | moving `search_topics` / `search_findings` under chat is a rename, and `Store.migrate` only creates: the live database would diverge silently |
| 9 | Closing tags a conversation (the existing tagger) and makes it read-only; deleting is a confirmed click that removes row, turns and folder; chat rows are never pruned (`Manifest.keep_sessions=True`) | the conversations are the catalog the owner is building; a 30-day prune suits pane sessions, not these |
| 10 | Title: the first user line until the conversation is closed; the tagger's title after | no extra LLM run at every start |
| 11 | `[chat] upload_max_mb` is the only knob | the one number the code would otherwise hard-code |
| 12 | Phase 2 streams tokens: `--include-partial-messages` on session turns, `delta` events broadcast and never stored | shape verified today; without it MIDDLE sits on `thinking…` for the whole turn |
| 13 | A conversation whose CLI transcript is gone can be read, not continued; Otto's record is complete either way | the CLI holds the working memory (`--resume`), Otto holds the transcript; retention is the owner's CLI setting (Needs you) |

Rejected: the Anthropic API (metered separately from the Max plan, a second credential; the CLI seam already exists); Bash for the agent; folding Search's tables into chat; every module's read tools for the chat agent (not asked; a later item); a tab strip in the module panes (`session-tabs-deferred`, unchanged); a topic editor on Settings (data, not a knob); a Home `today` row per conversation (a chat is not an arrival to act on).

## Layout

| File | Change |
|---|---|
| `app/modules/chat/__init__.py` | `MANIFEST` |
| `app/modules/chat/routes.py` | `left`, `item`, `send`, `close`, `delete`, `upload`, `files`, `file`, `events`; hooks `numbers`, `context` |
| `app/modules/chat/agent.md` | the agent's job |
| `app/static/pages/chat.js` | `load`, `meta`, `Left`, `Middle`, `Right` |
| `app/static/shell.js` | import and `PAGES` entry for chat (rail order 1); `web_search` import and entry removed; RIGHT renders `impl.Right` when the page exports one, else the session pane as today; rail filters `m.page` |
| `app/api.py` | `/api/shell` lists page-less modules with `page`; the turn job, closer and busy set become `start_turn(st, mod, sid, started, text, prompt, key)` and `close_session(st, mod, sid, key)`, busy keyed by session id; the module routes call them with key `<module>`, chat with `chat:<id>` |
| `app/claude.py` | `_args` takes the built-in list; `session_turn` passes `READ_BUILTINS + agent.builtins` to `--tools` and `--allowedTools`; Phase 2: `--include-partial-messages` on session turns, `events_from` maps `stream_event` text deltas to `{"role": "delta", "text"}` |
| `app/modules/__init__.py` | `Agent.builtins: tuple[str, ...] = ()`, `Manifest.keep_sessions: bool = False`; docstring |
| `app/modules/home/routes.py`, `app/static/pages/home.js` | `_enabled` drops the `page` test; a group carries `page`; the header navigates only when it is true |
| `app/static/pages/settings.js` | `shown` toggle and start-page options only for `m.page` |
| `app/daemon.py` | seeds `modules.<name>.scheduled` for every module with schedules |
| `app/modules/system/tasks.py` | `prune_sessions` skips modules whose manifest sets `keep_sessions` |
| `app/modules/web_search/__init__.py` | `page=False`, `agent=None` |
| `app/modules/web_search/routes.py` | `left`, `blank`, `topic_add`, `topic_remove`, `_group_by_day`, `CHIPS` removed; `item`, `agree`, `disagree`, the hooks stay |
| `app/modules/web_search/tools.py` | `search_topic_add(kind, text)`, `search_topic_remove(id)` on `full`; the two read tools unchanged |
| `app/modules/web_search/agent.md`, `app/static/pages/web_search.js` | deleted |
| `app/config.py`, `config.toml` | `Chat(upload_max_mb)`; `[chat]` after `[nightly]`, in rail order |
| `tests/test_chat.py`, `tests/test_web_search.py`, `tests/test_app.py` | the tests below |

## Contract

| Field | Value |
|---|---|
| name, title | `chat`, `Chat` |
| hue, icon, order | `#d9915b` (Search's hue follows the function), speech bubble `<path d="M4 4h12v9H9l-4 3v-3H4Z"></path>`, 1 (after Home) — pending decision 1 |
| schedules | none |
| agent | placeholder `Ask anything…`, skills `web`, `files`, `topics`; `builtins=("Write", "Edit")`; read tools `search_findings`, `search_topics`; write tools `search_topic_add`, `search_topic_remove` |
| keep_sessions | `True` |

Routes, prefix `/api/chat`. Every write is a user action through the runner; a turn is a `session` job on resource `session:<id>`, so conversations run concurrently and one conversation's turns serialize.

| Route | Wire shape |
|---|---|
| `GET left?query&chip&page` | LEFT shape; groups by day of last activity; rows `{id, module: "chat", text: title, stamp: last turn ts, leading: {dot: hue while open, null when closed}}`; chips `All / Open / Closed`; `query` is `LIKE` over the title and the turns' text; `showing`, `more` by `ui.page_size` |
| `GET item/{id}` | `{id, module, title, tags, opened_at, closed_at, busy, turns: [{id, ts, role, text, tool, status}], files: [{name, bytes, modified}]}` |
| `POST send` | `{id?, text, files?: [name]}` → `{id, queued}`; no `id` creates the conversation; 400 empty; 409 busy or closed. The stored turn is `text`; the prompt sent is `text` plus one trailer line naming the folder and the attached paths |
| `POST close` | `{id}` → `{id}`; queues the close job (tagger, `closed` event); 409 busy or closed |
| `POST delete` | `{id}` → `{id}`; row, turns and folder go; 409 busy |
| `POST upload/{id}` | multipart `file` → `{name, bytes}`; basename only, a duplicate name gets a numeric suffix; 413 over `upload_max_mb` |
| `GET files/{id}`, `GET file/{id}/{name}` | the folder listing; the file itself, 404 outside the folder |
| `GET events/{id}` | server-sent events on key `chat:<id>`: `user`, `model`, `tool`, `tool_result`, `error`, `idle`, `closed`; Phase 2 adds `delta` |

Hooks: `numbers` → open conversations, label `open chats`; `context` → open and closed counts, the five most recent titles, the folder root. No `today`, `queue` or `item`: a conversation is opened on its own page.

Page. LEFT: search, chips, `new`, rows by day. MIDDLE with nothing selected: the composer alone, starting a conversation on send. MIDDLE selected: header (title, opened stamp, tag chips once closed, `close`, `delete` with confirm, `×`), the transcript (user turns as raised bubbles right-aligned at 85%, model turns through `Markdown`, tool calls as `▸ tool · status`, system lines dim mono), `thinking…` while busy, the composer pinned below with attach (file picker and drop), Enter sends, Shift+Enter breaks a line. RIGHT: `files · n`, one row per file (`name · bytes · stamp`), click opens it; with nothing selected a dim `pick or start a conversation`.

Agent: the owner's general assistant inside Otto. Searches and fetches the web when the question needs it. Works with files in the conversation's folder: reads what the owner attached, saves anything it makes there and nowhere else. Knows the nightly search: lists and edits topics through its tools, tells the owner findings wait on Home, never decides one. Writes markdown because this page renders it; the base rules on the owner's words and on never inventing records apply unchanged.

Departures from the artboard: the module is not in it, so title, hue, icon and rail position are Otto's; RIGHT on this page is the conversation's folder instead of the session pane, and MIDDLE carries the transcript in the pane's own shapes; the composer's attach control and the drop target are not drawn anywhere. Search's rail entry, page and pane go.

## Data

No new table and no cursor. Conversations and turns are the platform's `sessions` and `session_turns`; `search_topics` and `search_findings` stay web_search's, unchanged. Files: `data/workspace/chat/<id>/`, created on first upload or first turn.

| Path | Client | Proof |
|---|---|---|
| a turn | `session_turn`: server `otto`, the four search tools, `Write` / `Edit` confined to the workspace by `--restricted` | `test_chat_conversation_lifecycle` reads the spawn args |
| close | `oneshot` on `otto-read`, no tools, not budgeted | the same test, `CLOSE` reply |
| upload, delete | the folder under the workspace, through `runner.run_action` | `test_chat_upload_and_files` |
| topics | `search_topic_add` / `search_topic_remove` write `search_topics` and an event, `full` server only | `test_search_topic_tools` |

Chat has no `tasks.py`, so no scheduled path exists; `test_tasks_never_reach_interactive_claude` and `test_read_builtins_exclude_writers` hold, and `test_chat_conversation_lifecycle` asserts a scheduled run's args carry no `Write`.

## Phases

| Phase | Builds | Usable result |
|---|---|---|
| 1 | The module, its page and helpers; Search's page removed; Home, shell, Settings and prune changes; the two topic tools; config | The owner chats with web search and files inside Otto, keeps every conversation, and Home still reviews the nightly findings |
| 2 | `--include-partial-messages` on session turns, `delta` events, MIDDLE appends them until the whole turn arrives | Text appears as it is written, as in the desktop app |

## Tests

- `test_chat_conversation_lifecycle`: `fake_spawn` with a `Write` tool call; `send` without an id creates the conversation and persists `user`, `tool Write done`, `model`; the args carry `--session-id`, `Write` and `Edit` in `--tools`, `mcp__otto__search_topic_add` in `--allowedTools`; a second `send` resumes; a second conversation runs at the same time (two `running` jobs); `left` groups both under today and the chips filter; `close` with the `CLOSE` reply writes title and tags and `left?chip=Closed` lists it; `send` to it is 409; `delete` removes row, turns and folder; web_search's `nightly` through the same fake carries no `Write`.
- `test_chat_upload_and_files`: the upload lands in the folder, `files` lists it, `file` serves it, the next `send`'s stdin names its path; a path with a separator is 400; a body over `upload_max_mb` is 413.
- `test_chat_keeps_sessions`: `prune_sessions` deletes an old closed memory session and keeps an old closed chat.
- `test_web_search.py`: `/api/shell` lists `web_search` with `page: false`; Home's `Review` group and `to review` number still carry it; `left`, `blank` and the topic routes are 404; `test_search_topic_tools` adds and removes a topic through `tools.register` on fake servers, read server without the write tools.
- `test_app.py`: `test_session_turn_and_clear` unchanged and green after the extraction; `test_home_review_group` adds a page-less queue module.
- Phase 2, `test_chat_stream_deltas`: `stream_event` text deltas reach the event stream as `delta` and never become a `session_turns` row.

## Manifest

Present:

| Item | Version / location | Needed for |
|---|---|---|
| Python | 3.14.7, `.venv/Scripts/python.exe` | everything |
| fastapi, uvicorn, mcp, httpx, pytest | 0.141.1, 0.52.4, 2.2.0, 0.28.1, 9.1.1 (`pip show`, today) | routes, servers, tests |
| python-multipart | 0.0.32 installed | `UploadFile` on `upload` |
| Claude Code CLI | 2.1.263, `C:/Users/gudo/.local/bin/claude.exe` | every turn |
| `Write` under the daemon's flags | verified today: `--restricted --setting-sources "" --strict-mcp-config --permission-prompts none --tools Read,Write --allowedTools Read,Write` wrote `note.txt`, two turns, exit 0, empty stderr | file handling |
| `--include-partial-messages` | verified today: `stream_event` lines with `content_block_start`, `content_block_delta` (`text_delta`, `input_json_delta`), `message_stop`, beside the `assistant`, `user` and `result` lines Otto already parses | Phase 2 |
| `--session-id` then `--resume` | in use by every module pane today | continuing a conversation |
| marked, KaTeX, `md.js` | `app/static/vendor/` 18.0.12, 0.18.7; `Markdown` export | model turns |

Missing: none.

Needs you:

| Item | How |
|---|---|
| CLI transcript retention | `~/.claude/settings.json` has no `cleanupPeriodDays`, so the CLI deletes transcripts after 30 days of inactivity and a conversation past that reads but cannot take a turn (decision 13). Add `"cleanupPeriodDays": 3650` there if chats must stay continuable |
| Pending decisions 1–4 | answer below |

Verify:

| Check | Command |
|---|---|
| `Edit` under the daemon's flags | in an empty dir with `note.txt` present: `echo "Use the Edit tool to change ok to done in note.txt; one line back." \| env -u CLAUDECODE claude -p --output-format json --setting-sources "" --restricted --strict-mcp-config --tools Read,Edit --allowedTools Read,Edit --permission-prompts none --max-turns 4 --no-session-persistence` |
| Suite offline | `.venv/Scripts/python.exe -m pytest -q` |
| After merge | the rail shows Chat and no Search; Home's `Review` still lists the open findings; a dropped PDF is answered from its contents |

## Worktree

```
git worktree add ../otto-chat -b chat
```

Work there. When `chat` merges to `main`, run `/sync-architecture`; it retires the Search page from the doc and re-points `docs/gaps/search-topics-not-entered.md` at the chat agent.

## Pending decisions

1. Title `Chat`, hue `#d9915b`, speech-bubble icon, rail order 1 after Home.
2. No Bash for the chat agent; Science's kernels stay the code path.
3. Chat conversations are never pruned; deletion is the owner's click.
4. A closed conversation is read-only; there is no reopen.
