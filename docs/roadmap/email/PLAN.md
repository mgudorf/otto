# Email Plan

Status: planning, 2026-09-07.

Email mirrors the Gmail inbox into Otto so the owner can search it, read it, and archive or trash it in bulk from one place, while a nightly agent marks what deserves attention. Without it, inbox cleanup stays in the Chrome Gmail UI that misbehaves on bulk deletes, and nothing flags the mail that matters.

## Sources

| Source | Governs |
|---|---|
| `docs/ARCHITECTURE.md` E-mail section | Gmail OAuth, search and bulk actions, agent reads only |
| `docs/ARCHITECTURE.md` Daemon requirements and mechanisms | read client for tasks, write client for actions, idempotent commits, resource locks |
| `docs/ARCHITECTURE.md` Module contract, Config, Claude, Platform tables | file layout, manifest, hooks, MCP servers, budget, `config.toml` keys |
| `docs/ARCHITECTURE.md` UI frame contract | hue `#cf7b7b`, rail order 1, row and chip specs, inspector layout |
| `docs/design/Personal Dashboard App.dc.html` `isEmail` LEFT | chips All / Unread / Flagged; rows by day: 6px dot, sender, subject, time; `n / total` and `more` |
| artboard `selInfo` for `he` / `em` rows | inspector kind `email`, primary `Reply`, actions `Archive`, `Snooze` |
| artboard `AGENTS.email`, `ICONS.email`, Home `he` rows | skills triage, draft-reply, summarize, tag; placeholder `Ask about the inbox…`; envelope icon; Home rows carry the unread dot |
| `app/modules/__init__.py`, `app/runner.py`, `app/claude.py`, `app/scheduler.py`, `app/config.py` | Manifest, JobContext, run_task, nightly window, strict Config |
| `app/modules/memory/*`, `app/static/pages/memory.js`, `app/static/shell.js`, `app/static/rows.js` | the built module this one copies; `PAGES` map in shell.js must list the page |
| `tests/conftest.py`, `tests/test_platform.py` | `fake_spawn`, the AST test that keeps tasks off interactive Claude |
| `data/secrets/google_client.json`, `data/secrets/token.json` | web OAuth client, redirect `http://localhost:8756/m/email/api/oauth/callback`; token scope `gmail.modify` |

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | Talk to Gmail over plain REST with `httpx`; no new packages | `httpx` is already the daemon's client and is async; the module needs seven endpoints. The discovery client is synchronous and would need thread hops |
| 2 | `gmail.py` has `GmailRead` (profile, list, get, history) and `GmailWrite(GmailRead)` adding `modify`. `tasks.py` and `tools.py` import only `read_client`; `routes.py` alone imports `write_client`. A test enforces it | The "agent never writes or deletes" rule has to be structural: the object a task or tool holds has no method that can change Gmail |
| 3 | Keep scope `gmail.modify`; "delete" means Trash | The token in hand covers archive, trash, read and star and cannot permanently delete anything (that needs the full mail scope). Trash is reversible for 30 days; a second fence under the constraint |
| 4 | Local mirror: metadata for all mail newer than `backfill_days`, then `history.list` increments every 5 minutes | LEFT, search and bulk actions run on the local table instantly; history keeps unread and starred honest when mail is read on the phone |
| 5 | Bulk actions apply to everything matching the current LEFT filter (query and chip) | Solves the bulk-delete problem with no checkbox UI; search plus chip already define the set |
| 6 | Nightly triage writes priorities to a local table; the session agent gets read tools plus one local write tool `email_flag` | Requirement 3 and 4: triage, prioritize, flag; nothing the agent holds reaches Gmail |
| 7 | Body text is fetched when a message is opened or when `email_get` asks, then cached | Backfill stays metadata plus snippet; triage works from sender, subject and snippet |
| 8 | `python -m app.modules.email.gmail consent` runs the OAuth flow on the redirect already registered (`localhost:8756/m/email/api/oauth/callback`) | `token.json` carries `refresh_token_expires_in = 604799`: the OAuth app is in Testing status and refresh tokens die after 7 days (next around 2026-09-12). Without a re-consent path the module stops within a week; the daemon's port 8765 is not a registered redirect |

Rejected: `google-api-python-client` (installed, unpinned, synchronous); full mail scope (re-consent and irreversible deletes); querying Gmail per page instead of mirroring; per-row checkboxes; an OAuth route inside the daemon (needs a console change first).

## Layout

| File | Change |
|---|---|
| `app/modules/email/__init__.py` | `MANIFEST` |
| `app/modules/email/gmail.py` | token load and refresh, `GmailRead`, `GmailWrite`, `read_client(config)`, `write_client(config)`, `consent` command |
| `app/modules/email/schema.sql` | `email_messages`, `email_triage`, `email_fts` and triggers |
| `app/modules/email/tasks.py` | `sync`, `triage` |
| `app/modules/email/routes.py` | `left`, `blank`, `item`, `action/{verb}`, hooks |
| `app/modules/email/tools.py` | `email_search`, `email_get`, `email_triage`, `email_flag` |
| `app/modules/email/agent.md` | the agent's job |
| `app/static/pages/email.js` | LEFT, MIDDLE blank, inspector |
| `app/static/shell.js` | import the page and add `email` to `PAGES` |
| `app/config.py`, `config.toml` | `[email]` section: `client_file`, `token_file`, `backfill_days`, `triage_batch` |
| `tests/test_email.py` | the four tests below |

## Contract

Manifest: `name="email"`, `title="Email"`, `hue="#cf7b7b"`, icon `<rect x="3" y="5" width="14" height="10" rx="2"></rect><path d="M3 7l7 5 7-5"></path>`, `order=1`.

| Schedule | Every | Resource | LLM | Does |
|---|---|---|---|---|
| `email.sync` | 5m | `gmail` | no | backfill on first run, `history.list` afterwards; one commit with the new history id |
| `email.triage` | 24h | `email` | yes | prioritizes up to `triage_batch` untriaged inbox messages inside the nightly window |

Routes, prefix `/api/email`:

| Route | Wire shape |
|---|---|
| `GET left?query&chip&page` | `{groups: [{label "05 Sep", count, rows: [{id, module: "email", text: "<from_name>: <subject>", stamp: internal_date, leading: {dot: hue when unread else "transparent"}}]}], chips: ["All","Unread","Flagged","Priority"], chip, showing: "40 / 2,838", more, total}` |
| `GET blank` | `{inbox, unread, flagged, priority, last_sync}` |
| `GET item/{id}` | `{id, module: "email", kind: "email", subject, from_name, from_addr, to_addr, created_at: internal_date, text: body or snippet, unread, starred, priority, reason, actions}` where actions are `archive` (primary), `trash` (confirm "Trash this message?"), `read` or `unread`, `star` or `unstar`, `open` (href `https://mail.google.com/mail/u/0/#all/<id>`) |
| `POST action/{verb}` | body `{ids: [...]}` or `{filter: {query, chip}}`; verbs `archive`, `trash`, `read`, `unread`, `star`, `unstar`; runs through `runner.run_action` on resource `gmail`; returns `{count}` |

Chip meaning: All = has `INBOX`; Unread = `INBOX` and `UNREAD`; Flagged = `INBOX` and `STARRED`; Priority = `INBOX` and triage `high`. Search is FTS over sender, address, subject and snippet, combined with the chip.

MIDDLE blank: one mono status line (`2,838 in inbox · 2,549 unread · synced 14:02`), then the bulk bar for the current filter: `{total} matching` with `Mark read`, `Archive` and `Trash` (confirm "Trash N messages?"). Each action posts `{filter}` and refreshes.

Hooks: `numbers` = unread in inbox, label `unread` (the platform renders the session context label from it); `today` = inbox messages received today, newest first; `item` as above; `context` = counts, last sync, the ten newest inbox lines as `(id, from, subject)`, and open high-priority items.

MCP tools: read on both servers: `email_search(query, chip, limit)`, `email_get(id)` (body via `read_client` when not cached), `email_triage(priority)`. Write on `otto` only: `email_flag(id, priority, reason)`, which writes `email_triage` and nothing else. No tool anywhere touches `GmailWrite`.

Agent: the Email agent reads the mirror and says what matters. It triages by sender, subject and snippet, ranks what the owner should open first, and flags items with `email_flag` and a one-line reason. It never sends, archives, trashes or labels; when asked to, it says the owner does that from the inspector. Skills chips: `triage`, `summarize`, `flag`.

Departures from the artboard, each with its reason:

- Chip `Priority` added: the agent's output needs a place the owner sees on arrival.
- Rows are one text span `sender: subject` instead of two skeleton spans: the shared `Row` has one text slot and Home renders Email rows with it.
- Inspector: no `Reply` (no compose in version 0), no `Snooze` (Gmail has no API for it); `Archive` is primary; `Trash`, read/unread, star/unstar and `Open in Gmail` are the user actions the E-mail requirement asks for.
- Skill chips `draft-reply` and `tag` dropped: no compose, and labels are not an agent action; `flag` names what the agent does.
- MIDDLE blank state is the status line plus the bulk bar: the artboard leaves Email's blank state undefined and requirement 2 needs a bulk surface.

## Data

`schema.sql`:

| Table | Columns |
|---|---|
| `email_messages` | `n INTEGER PRIMARY KEY`, `id TEXT NOT NULL UNIQUE` (Gmail id), `thread_id`, `from_name`, `from_addr`, `to_addr`, `subject`, `snippet`, `internal_date TEXT` (UTC ISO), `labels TEXT` (JSON list of label ids), `body_text TEXT`, `synced_at TEXT`; index on `internal_date` |
| `email_triage` | `message_id TEXT PRIMARY KEY REFERENCES email_messages(id) ON DELETE CASCADE`, `priority TEXT CHECK (high, normal, low)`, `reason TEXT`, `ts TEXT`, `source TEXT` (`scheduled` or `session`) |
| `email_fts` | FTS5 over `from_name, from_addr, subject, snippet`, `content='email_messages'`, `content_rowid='n'`, trigger-maintained. `n` exists so rowids survive Vacuum |

Cursors: `email.history` = Gmail history id after the last committed sync; `email.triage` = timestamp of the last triage run. Sync reads the profile's history id before listing so nothing between list and commit is lost; a 404 on `history.list` (expired id) clears the cursor and backfills again. Every row change and the cursor land in one `ctx.commit`.

External clients:

| Path | Client | Can |
|---|---|---|
| `email.sync` task | `read_client` → `GmailRead` | profile, list, get, history |
| `email.triage` task | none (store only) plus `ctx.run_task` | read |
| `item` route, `email_get` tool | `read_client` | get body |
| `action/*` routes | `write_client` → `GmailWrite` | `messages.batchModify` in chunks of 1000 (add or remove `INBOX`, `TRASH`, `UNREAD`, `STARRED`), then the local labels in the same action |
| session agent | MCP tools only | read the mirror, write `email_triage` |

Split proof: `test_email_client_split` parses `tasks.py` and `tools.py` and asserts none of `GmailWrite`, `write_client`, `modify`, `batchModify`, `trash`, `delete` appear; asserts `GmailRead` has no `modify` attribute; registers the tools on two fake servers and asserts the only tool on `full` that is not on `read` is `email_flag`; asserts the manifest's `write_tools == ("email_flag",)`.

Token handling: both clients read `token_file`, refresh through `token_uri` when `expires_at` has passed, and write the new access token back. Refresh is not a Gmail write. The `consent` command listens on the registered redirect, exchanges the code and writes `token_file` in the same shape.

## Phases

| Phase | Builds | Usable result |
|---|---|---|
| 1 | `gmail.py`, `[email]` config, `schema.sql`, `sync`, routes `left` / `blank` / `item` / `action`, hooks, `email.js`, shell registration, `MANIFEST` with the agent on read tools `email_search` and `email_get`, tests 1 to 3 | The inbox lists and searches in Otto; the owner archives, trashes, marks and stars one message from the inspector or every match from the bulk bar; Home shows unread count and today's mail; the session answers questions about the mirror |
| 2 | `triage` task, `email_triage`, `Priority` chip, `email_triage` and `email_flag` tools, `agent.md` triage rules, test 4 | On arrival the Priority chip and the blank state show what the agent flagged overnight; the session flags on request with a reason |

## Tests

- `test_email_client_split`: the structural proof above.
- `test_email_sync`: `httpx.MockTransport` stands in for Gmail (token refresh included). First run backfills rows and sets `email.history`; second run applies a history page with a label change and a deletion; a 404 on history clears the cursor and re-backfills.
- `test_email_actions`: `archive` by ids and `trash` by filter through the app: the `batchModify` request body is asserted, local labels change, an `events` row is written.
- `test_email_triage`: `fake_spawn` returns a JSON array; rows land in `email_triage`; a second run skips already-triaged ids. Real Claude raises via `conftest`.

## Manifest

Present:

| Item | Version / location | Needed for |
|---|---|---|
| Python | 3.14.7 in `.venv` | everything |
| httpx | 0.28.1 in `.venv`, pinned in `requirements.txt` | Gmail REST client, `MockTransport` in tests |
| SQLite with FTS5 | 3.50.4, stdlib | `email_fts` |
| `data/secrets/google_client.json` | web client, project `central-shift-507603-b1`, redirect `http://localhost:8756/m/email/api/oauth/callback` | token refresh, `consent` |
| `data/secrets/token.json` | scope `https://www.googleapis.com/auth/gmail.modify`; refreshed today and read the profile: `matthew.gudorf@gmail.com`, 3,122 messages, inbox 2,838 with 2,549 unread, history id 13770154 | sync and actions |
| google-api-python-client, google-auth, google-auth-oauthlib | 2.200.0, 2.57.1, 1.4.1 in `.venv`, not in `requirements.txt` | not used by this plan; left alone |

Missing: none.

Needs you:

| Item | How |
|---|---|
| OAuth publishing status | `token.json` shows `refresh_token_expires_in: 604799`, the mark of Testing status; the refresh token issued 2026-09-05 dies around 2026-09-12. Either publish the consent screen to Production in the Cloud console for project `central-shift-507603-b1`, or run the `consent` command each week |
| Redirect URI | confirm `http://localhost:8756/m/email/api/oauth/callback` is still registered on the client; `consent` depends on it |

Verify:

| Check | Command |
|---|---|
| Refresh token lifetime | `.venv/Scripts/python.exe -c "import json;print(json.load(open('data/secrets/token.json')).get('refresh_token_expires_in'))"` (a number means Testing status) |
| History endpoint answers from the current cursor | `.venv/Scripts/python.exe -c "from app.modules.email.gmail import read_client; from app.config import load; import asyncio; print(asyncio.run(read_client(load()).history('13770154')))"` after phase 1 |
| FTS5 available | `.venv/Scripts/python.exe -c "import sqlite3; c=sqlite3.connect(':memory:'); c.execute('CREATE VIRTUAL TABLE t USING fts5(x)'); print('ok')"` |

## Worktree

```
git worktree add ../otto-email -b email
```

Work in `../otto-email`. When `email` is merged to `main`, run `/sync-architecture`.

## Pending decisions

1. Publish the OAuth consent screen to Production, or accept running `consent` weekly?
2. Version 0 treats Trash as delete and never deletes permanently. Confirm.
