# Chat Plan

Status: planning, 2026-09-12.

Chat is the page where the owner talks to Claude the way they do in the Claude desktop app: any topic, web search on demand, files in and out, every conversation kept forever and always continuable, without leaving Otto. Without it the owner keeps two apps open, and the Search page stays a rail entry whose one interactive job (ask the web) the chat does better.

## Sources

| Source | Governs |
|---|---|
| `docs/ARCHITECTURE.md` Summary (several conversations; tagged sessions reach Graph), Daemon requirements and Mechanisms, Config, Claude (`session_turn`, `oneshot`, sessions, budget), Module contract, Home page requirement 2, Search, Graph, System, UI frame contract and Departures | what a conversation is, which client each path gets, the wire shapes, hues and rail order, what Home must keep showing |
| `docs/design/Personal Dashboard App.dc.html` lines 23–26 (rail icons), 320–326 (session pane: raised user bubble at 85%, `▸ tool · status` line), 349–356 (pane presets) | the transcript's visual shape and the icon style. No chat page exists in the artboard |
| `app/claude.py` | `_args`, `session_turn`, `oneshot`, `_stream`, `events_from`, `READ_BUILTINS`; the seam every turn goes through |
| `app/api.py` sessions block, `app/static/session.js` | the turn job, on-event persistence, busy state, `Broadcast`, `event_stream`, the tagger: extracted, not rewritten |
| `app/modules/__init__.py`, `app/modules/home/routes.py`, `app/static/shell.js`, `app/static/pages/settings.js`, `app/daemon.py` | `Agent`, Home's `_enabled`, the `PAGES` map and RIGHT track, module toggles, setting seeds |
| `app/modules/graph/build.py` `SOURCES`, `tests/test_graph.py` | Graph reads closed sessions only today; chat conversations never close |
| `app/modules/web_search/*`, `app/static/pages/web_search.js`, `docs/roadmap/web_search/PLAN.md` | what the owner asked to remove (the page) and keep (nightly run, tables, hooks, decisions, tools); its Phase 3 write tools land here |
| `app/modules/system/tasks.py` | `prune_sessions` deletes closed sessions only |
| `app/static/md.js` | `Markdown` for model turns |
| `docs/gaps/session-tabs-deferred.md`, `docs/gaps/search-topics-not-entered.md` | the module panes stay single-session (that gap is untouched); the topics gap's fix path becomes the chat agent |
| Owner's answers, 2026-09-12 | title, hue, icon and order as proposed; no Bash now but a clear path to more tools; nothing pruned unless deleted and nothing ever hidden; conversations stay open, as a provider keeps them |
| This session's probes (2026-09-10, 2026-09-12) | `Write` under the daemon's flags; the `--include-partial-messages` stream shape; the CLI's answer to a lost transcript |

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | A module `chat` with a page. A conversation is a `sessions` row with module `chat`, many at once, never closed; its turns are `session_turns` | the tables, the tagger and Graph exist; a conversation is a session with a page instead of a pane. The CLI exits after every turn and `--resume` reloads from disk, so an open conversation costs nothing to keep |
| 2 | MIDDLE is the conversation (transcript and composer), LEFT the list, RIGHT the conversation's folder | the pane is 22.8% of the window; a chat the owner lives in needs the widest track. On this page the agentic window is MIDDLE (departure, named below) |
| 3 | Every turn runs through the platform's session machinery, extracted from the `api.py` route into helpers keyed by session id and broadcast key | one implementation of persistence, busy state, events and tagging; the module panes keep one open session each and the tabs gap stays its own item |
| 4 | Agent tools now: the read built-ins plus `Write` and `Edit`, declared as `Agent.builtins` and passed on session turns only; MCP `search_findings`, `search_topics` (read), `search_topic_add`, `search_topic_remove` (write). No Bash | `Write` verified under the daemon's flags; `--restricted` confines file tools to the workspace. Bash is not confined and every run has `--permission-prompts none` |
| 5 | Adding a tool later is one line, none built now: a built-in is a word in `Agent.builtins`; any Otto tool is its name in chat's manifest, whichever module registers it; an external MCP server is one more entry in the `--mcp-config` JSON `_args` already writes, allowed as `mcp__<server>` | the owner asked for the path, not the tools; `_args` and the manifest are the two seams and both take a list |
| 6 | Attachments are files: an upload lands in `data/workspace/chat/<id>/`, the prompt sent to the CLI names that folder and the attached paths, the agent Reads them and saves what it makes there; RIGHT lists the folder | the CLI reads images and PDFs natively; one folder is the conversation's shelf for both directions; the stored user turn stays the owner's words |
| 7 | A conversation is titled and tagged by the tagger after its first completed turn (an unbudgeted `oneshot`, exactly what `/clear` runs today), never on a close; Graph reads every tagged session, open or closed | providers title after the first exchange; there is no close to hang tagging on; Graph's `closed_at` filter would otherwise never see a chat |
| 8 | `web_search` keeps tables, nightly run, hooks, `item`, `agree` / `disagree` and read tools; loses page, agent, `left`, `blank`, topic routes (`page=False`, `agent=None`); topics are edited by the chat agent through the two new write tools | the owner's call: on-demand search is the chat's, the nightly search still feeds Home's Review, and topics need exactly one entry point |
| 9 | Home aggregates any module with hooks, page or not; `/api/shell` lists page-less modules with `page: false`; rail, the `shown` toggle and the start-page list filter on `page`; the `runs` toggle stays for any module with tasks | Review must keep listing findings, hue and icon must resolve for its rows, and the owner keeps the per-module nightly switch decided on 2026-09-10 |
| 10 | Tables stay where they are | moving `search_topics` / `search_findings` under chat is a rename, and `Store.migrate` only creates: the live database would diverge silently |
| 11 | Nothing removes a conversation but the owner's `delete` (confirmed): row, turns and folder. `prune_sessions` deletes closed sessions only and a chat never closes, so no flag is needed. LEFT lists every conversation; no state hides one | the owner's rule: pruned only if deleted, never hidden |
| 12 | A conversation is always continuable: `--resume`; when the CLI has dropped the transcript (`result` `error_during_execution`, `num_turns` 0, stderr `No conversation found with session ID`), the turn is re-sent with `--session-id <same id>` and the stored transcript's last `replay_chars` characters as preamble, and a `system` turn `resumed from Otto's record` marks the join | the CLI holds the working memory, Otto holds the record; the record wins. The signal was verified today |
| 13 | `[chat] upload_max_mb` and `[chat] replay_chars` are the knobs | the two numbers the code would otherwise hard-code |
| 14 | Phase 2 streams tokens: `--include-partial-messages` on session turns, `delta` events broadcast and never stored | shape verified; without it MIDDLE sits on `thinking…` for the whole turn |

Rejected: the Anthropic API (metered separately from the Max plan, a second credential; the CLI seam already exists); Bash for the agent (now); an empty `[chat] mcp_servers` table today (structure with no function); folding Search's tables into chat; a close or archive state (the owner: keep them open); tagging on a schedule (a task can only reach `run_task`, nightly and budgeted); a tab strip in the module panes (`session-tabs-deferred`, unchanged); a topic editor on Settings (data, not a knob); a Home `today` row per conversation (a chat is not an arrival to act on).

## Layout

| File | Change |
|---|---|
| `app/modules/chat/__init__.py` | `MANIFEST` |
| `app/modules/chat/routes.py` | `left`, `item`, `send`, `delete`, `upload`, `files`, `file`, `events`; hooks `numbers`, `context` |
| `app/modules/chat/agent.md` | the agent's job |
| `app/static/pages/chat.js` | `load`, `meta`, `Left`, `Middle`, `Right` |
| `app/static/shell.js` | import and `PAGES` entry for chat (rail order 1); `web_search` import and entry removed; RIGHT renders `impl.Right` when the page exports one, else the session pane as today; rail filters `m.page` |
| `app/api.py` | `/api/shell` lists page-less modules with `page`; the turn job, tagger and busy set become `start_turn(st, mod, sid, started, text, prompt, key)` and `tag_session(st, mod, sid, key, close)`, busy keyed by session id; the module routes call them with key `<module>` and `close=True`, chat with `chat:<id>` and `close=False` |
| `app/claude.py` | `_args` takes the built-in list; `session_turn` passes `READ_BUILTINS + agent.builtins` to `--tools` and `--allowedTools`; `ClaudeError` from an `is_error` result carries the subtype, `num_turns` and stderr; Phase 2: `--include-partial-messages` on session turns, `events_from` maps `stream_event` text deltas to `{"role": "delta", "text"}` |
| `app/modules/__init__.py` | `Agent.builtins: tuple[str, ...] = ()`; docstring |
| `app/modules/graph/build.py` | `SOURCES` takes every session with tags, `ts` = `closed_at` or `opened_at` |
| `app/modules/home/routes.py`, `app/static/pages/home.js` | `_enabled` drops the `page` test; a group carries `page`; the header navigates only when it is true |
| `app/static/pages/settings.js` | `shown` toggle and start-page options only for `m.page` |
| `app/daemon.py` | seeds `modules.<name>.scheduled` for every module with schedules |
| `app/modules/web_search/__init__.py` | `page=False`, `agent=None` |
| `app/modules/web_search/routes.py` | `left`, `blank`, `topic_add`, `topic_remove`, `_group_by_day`, `CHIPS` removed; `item`, `agree`, `disagree`, the hooks stay |
| `app/modules/web_search/tools.py` | `search_topic_add(kind, text)`, `search_topic_remove(id)` on `full`; the two read tools unchanged |
| `app/modules/web_search/agent.md`, `app/static/pages/web_search.js` | deleted |
| `app/config.py`, `config.toml` | `Chat(upload_max_mb, replay_chars)`; `[chat]` after `[nightly]`, in rail order |
| `tests/test_chat.py`, `tests/test_web_search.py`, `tests/test_graph.py`, `tests/test_app.py`, `tests/conftest.py` | the tests below; `FakeProc` takes stderr lines |

## Contract

| Field | Value |
|---|---|
| name, title | `chat`, `Chat` |
| hue, icon, order | `#d9915b` (Search's hue follows the function), speech bubble `<path d="M4 4h12v9H9l-4 3v-3H4Z"></path>`, 1 (after Home); decided 2026-09-12 |
| schedules | none |
| agent | placeholder `Ask anything…`, skills `web`, `files`, `topics`; `builtins=("Write", "Edit")`; read tools `search_findings`, `search_topics`; write tools `search_topic_add`, `search_topic_remove` |

Routes, prefix `/api/chat`. Every write is a user action through the runner; a turn is a `session` job on resource `session:<id>`, so conversations run concurrently and one conversation's turns and its tag job serialize.

| Route | Wire shape |
|---|---|
| `GET left?query&page` | LEFT shape; groups by day of last activity; rows `{id, module: "chat", text: title, stamp: last turn ts}`; no chips; `query` is `LIKE` over the title and the turns' text; `showing`, `more` by `ui.page_size` |
| `GET item/{id}` | `{id, module, title, tags, opened_at, busy, turns: [{id, ts, role, text, tool, status}], files: [{name, bytes, modified}]}` |
| `POST send` | `{id?, text, files?: [name]}` → `{id, queued}`; no `id` creates the conversation; 400 empty; 409 busy. The stored turn is `text`; the prompt sent is `text` plus one trailer line naming the folder and the attached paths. After the first completed turn of an untitled conversation the route queues the tag job |
| `POST delete` | `{id}` → `{id}`; row, turns and folder go; 409 busy |
| `POST upload/{id}` | multipart `file` → `{name, bytes}`; basename only, a duplicate name gets a numeric suffix; 413 over `upload_max_mb` |
| `GET files/{id}`, `GET file/{id}/{name}` | the folder listing; the file itself, 404 outside the folder |
| `GET events/{id}` | server-sent events on key `chat:<id>`: `user`, `model`, `tool`, `tool_result`, `error`, `idle`, `tagged {title, tags}`; Phase 2 adds `delta` |

Hooks: `numbers` → conversations, label `conversations`; `context` → the count, the five most recent titles, the folder root. No `today`, `queue` or `item`: a conversation is opened on its own page.

Page. LEFT: search, `new`, rows by day, every conversation. MIDDLE with nothing selected: the composer alone, starting a conversation on send. MIDDLE selected: header (title, opened stamp, tag chips, `delete` with confirm, `×`), the transcript (user turns as raised bubbles right-aligned at 85%, model turns through `Markdown`, tool calls as `▸ tool · status`, system lines dim mono), `thinking…` while busy, the composer pinned below with attach (file picker and drop), Enter sends, Shift+Enter breaks a line. RIGHT: `files · n`, one row per file (`name · bytes · stamp`), click opens it; with nothing selected a dim `pick or start a conversation`.

Agent: the owner's general assistant inside Otto. Searches and fetches the web when the question needs it. Works with files in the conversation's folder: reads what the owner attached, saves anything it makes there and nowhere else. Knows the nightly search: lists and edits topics through its tools, tells the owner findings wait on Home, never decides one. Writes markdown because this page renders it; the base rules on the owner's words and on never inventing records apply unchanged.

Departures from the artboard: the module is not in it, so title, hue, icon and rail position are Otto's; RIGHT on this page is the conversation's folder instead of the session pane, and MIDDLE carries the transcript in the pane's own shapes; the composer's attach control and the drop target are not drawn anywhere. Search's rail entry, page and pane go. Departure from the Summary: a chat is tagged after its first turn, not at a close it never has.

## Data

No new table and no cursor. Conversations and turns are the platform's `sessions` and `session_turns`; `search_topics` and `search_findings` stay web_search's, unchanged. Files: `data/workspace/chat/<id>/`, created on first upload or first turn.

| Path | Client | Proof |
|---|---|---|
| a turn | `session_turn`: server `otto`, the four search tools, `Write` / `Edit` confined to the workspace by `--restricted` | `test_chat_conversation_lifecycle` reads the spawn args |
| titling | `oneshot` on `otto-read`, no tools, not budgeted | the same test, `TAG` reply |
| upload, delete | the folder under the workspace, through `runner.run_action` | `test_chat_upload_and_files` |
| topics | `search_topic_add` / `search_topic_remove` write `search_topics` and an event, `full` server only | `test_search_topic_tools` |

Chat has no `tasks.py`, so no scheduled path exists; `test_tasks_never_reach_interactive_claude` and `test_read_builtins_exclude_writers` hold, and `test_chat_conversation_lifecycle` asserts a scheduled run's args carry no `Write`.

## Phases

| Phase | Builds | Usable result |
|---|---|---|
| 1 | The module, its page and helpers; Search's page removed; Home, shell, Settings and Graph changes; the two topic tools; replay; config | The owner chats with web search and files inside Otto, every conversation stays listed and continuable, and Home still reviews the nightly findings |
| 2 | `--include-partial-messages` on session turns, `delta` events, MIDDLE appends them until the whole turn arrives | Text appears as it is written, as in the desktop app |

## Tests

- `test_chat_conversation_lifecycle`: `fake_spawn` with a `Write` tool call; `send` without an id creates the conversation and persists `user`, `tool Write done`, `model`; the args carry `--session-id`, `Write` and `Edit` in `--tools`, `mcp__otto__search_topic_add` in `--allowedTools`; the tag job runs with a `TAG` reply and writes title and tags, `closed_at` stays null, a `tagged` event streams, `graph.build.rebuild` counts the conversation; a second `send` resumes and queues no tag job; a second conversation runs at the same time (two `running` jobs); `left` groups both under today; `delete` removes row, turns and folder; web_search's `nightly` through the same fake carries no `Write`.
- `test_chat_replays_lost_transcript`: a spawn sequence whose first process answers the verified error `result` with stderr `No conversation found with session ID` and whose second succeeds; the second args carry `--session-id`, its stdin carries the earlier turns cut to `replay_chars`, a `system` turn `resumed from Otto's record` is stored, and the model turn lands.
- `test_chat_upload_and_files`: the upload lands in the folder, `files` lists it, `file` serves it, the next `send`'s stdin names its path; a path with a separator is 400; a body over `upload_max_mb` is 413.
- `test_web_search.py`: `/api/shell` lists `web_search` with `page: false`; Home's `Review` group and `to review` number still carry it; `left`, `blank` and the topic routes are 404; `test_search_topic_tools` adds and removes a topic through `tools.register` on fake servers, read server without the write tools.
- `test_graph.py`: the seed's open session carries no tags (only the tagger writes them); an open tagged session counts as a source.
- `test_app.py`: `test_session_turn_and_clear` unchanged and green after the extraction; `test_home_review_group` adds a page-less queue module.
- Phase 2, `test_chat_stream_deltas`: `stream_event` text deltas reach the event stream as `delta` and never become a `session_turns` row.

## Manifest

Present:

| Item | Version / location | Needed for |
|---|---|---|
| Python | 3.14.7, `.venv/Scripts/python.exe` | everything |
| fastapi, uvicorn, mcp, httpx, pytest | 0.141.1, 0.52.4, 2.2.0, 0.28.1, 9.1.1 (`pip show`, 2026-09-10) | routes, servers, tests |
| python-multipart | 0.0.32 installed | `UploadFile` on `upload` |
| Claude Code CLI | 2.1.263, `C:/Users/gudo/.local/bin/claude.exe` | every turn |
| `Write` under the daemon's flags | verified 2026-09-10: `--restricted --setting-sources "" --strict-mcp-config --permission-prompts none --tools Read,Write --allowedTools Read,Write` wrote `note.txt`, two turns, exit 0, empty stderr | file handling |
| `--include-partial-messages` | verified 2026-09-10: `stream_event` lines with `content_block_start`, `content_block_delta` (`text_delta`, `input_json_delta`), `message_stop`, beside the `assistant`, `user` and `result` lines Otto already parses | Phase 2 |
| lost-transcript signal | verified 2026-09-12: `--resume` of an unknown id emits one `result` line `subtype error_during_execution, is_error true, num_turns 0`, stderr `No conversation found with session ID: <id>`, exit 1, no tokens | replay |
| `--session-id` then `--resume` | in use by every module pane today | continuing a conversation |
| marked, KaTeX, `md.js` | `app/static/vendor/` 18.0.12, 0.18.7; `Markdown` export | model turns |

Missing: none.

Needs you:

| Item | How |
|---|---|
| CLI transcript retention, optional | `~/.claude/settings.json` has no `cleanupPeriodDays`, so the CLI forgets a transcript after 30 idle days; replay covers that, at the cost of a fresh session that has only the replayed text. Add `"cleanupPeriodDays": 3650` there to keep the CLI's own memory of long-idle chats |

Verify:

| Check | Command |
|---|---|
| `Edit` under the daemon's flags | in an empty dir with `note.txt` present: `echo "Use the Edit tool to change ok to done in note.txt; one line back." \| env -u CLAUDECODE claude -p --output-format json --setting-sources "" --restricted --strict-mcp-config --tools Read,Edit --allowedTools Read,Edit --permission-prompts none --max-turns 4 --no-session-persistence` |
| Suite offline | `.venv/Scripts/python.exe -m pytest -q` |
| After merge | the rail shows Chat and no Search; Home's `Review` still lists the open findings; a dropped PDF is answered from its contents; a conversation is titled after its first answer |

## Worktree

```
git worktree add ../otto-chat -b chat
```

Work there. When `chat` merges to `main`, run `/sync-architecture`; it retires the Search page from the doc and re-points `docs/gaps/search-topics-not-entered.md` at the chat agent.

## Pending decisions

None. The four questions of 2026-09-10 were answered on 2026-09-12 and are folded into decisions 1, 4, 5, 7, 11 and 12.
