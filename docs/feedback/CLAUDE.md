# Feedback

## Built

A `feedback` control in the header of every page records a change the owner wants, together with the selected item when its inspector loaded. Nothing touches the repo; the row is the record.

| Piece | Current state |
|---|---|
| Table | `feedback_items(created_at, page, item_module, item_id, item_text, text (the owner's words, verbatim), status queued\|filed\|failed, kind, title, summary, tags JSON, ref, draft, filed_at, job_id, error, cleared_at)` |
| Manifest | `page=False`, hue `#8b8f98`, order 99, so there is no rail entry |
| Setup | adds `cleared_at` to a `feedback_items` table that predates it, and marks every row still `queued` as `failed` with `daemon restarted`, so a note whose filing job died with the last daemon offers `retry` |
| Routes | `POST action/add` (400 on an empty page or text, 503 while the daemon drains, before any row exists) writes the row and an event under the originating page, submits a filing job on resource `feedback` and returns `{id}` at once; `retry` requeues a failed one (404 unknown, 409 unless `failed`); `GET recent?page=<page>` gives that page's last five rows and echoes the `page` it answered for (422 without one); `GET list` gives every field |
| Filing | a `oneshot` run with `feedback.max_turns` and the read tools `docs_list`, `docs_read` (markdown under `docs/` only) and `feedback_list`; the prompt carries the id, time, page, selected item (text cut to 300) and the owner's words in fenced blocks. The agent replies with one JSON object written to the row: `kind` (bug, defect, gap or roadmap), `title` (120), `summary` (200), `tags` (eight of 40), `ref` (the existing `docs/` file it belongs in) and `draft` (the body ready for that file, the owner's words quoted). Any other reply marks the row and the job `failed` with the error |
| Tools | read: `feedback_list`, every field but `item_text`, `draft`, `filed_at`, `job_id`, `error` and `cleared_at` |
| Commands | `python -m app.modules.feedback list <module>...` and `clear <module>...`; `clear` stamps `cleared_at` once a work session has read a row. Both refuse a database still under older table names until the daemon has started on the current code, and print UTF-8 whatever the console codepage, so the owner's arrows and quotes never end a listing early |
| Hooks | `context`: the built modules and each doc's count of open Patches entries |
| Panel | 520px, the shared growing textarea with the page and item as context, `↵` (Enter; Shift+Enter breaks, Esc closes and keeps the draft), rows reading `filing…`, `<kind> <summary>` or `failed <error>` with `retry`. One panel per page: a page change closes it and drops the draft, error and busy state, and a `recent` payload answering for another page is ignored, so a fetch in flight from the page just left never shows |
| Departures | the header icon and its panel are not in the artboard; they reuse the header's icon controls, the panel surfaces, the composer textarea and compact rows |

## Patches

### Feedback filed on anything but a row can never be listed

- Kind: bug
- Where: `app/modules/feedback/queue.py` (`SHELL_PAGES`, `names`, the `pages/<module>.js` match), `app/static/point.js` (`feedback`), `.claude/skills/feedback-queue/SKILL.md`, `README.md` (the module names for `feedback`), `app/modules/feedback/agent.md`
- Found: 09-22-2026, the stale-code audit, against the live database opened read-only
- Status: open

What happens: point mode files a note on anything that is not a row under the page `otto`. The queue tool accepts the module names, `app`, and the retired `activity` and `settings`, so `list otto` stops as unknown and `list app` does not match `otto`. Both open notes in the live database carry `otto`, and `/feedback-queue` can neither show nor clear them. The skill, the README and the filer's prompt still name the two retired pages, and the tool still matches patches that name `pages/<module>.js`, a folder that is gone.

Expected: every note the owner files is listed under the doc it belongs to.

Fix: `names` takes `otto` in place of `activity` and `settings` and reads it as the platform doc, as it read those two; the `pages/` match goes; the skill, the README and `agent.md` follow.

### Point mode's label and quote never reach the filer

- Kind: bug
- Where: `app/static/point.js` (`feedback`), `app/modules/feedback/routes.py` (`add`, `ITEM_TEXT_CHARS`, the selected-item block of the filing prompt), `feedback_items.item_text`
- Found: 09-22-2026, the stale-code audit
- Status: open

What happens: the popover names what was pointed at down to the paragraph and shows the quote, and the note it sends carries only `{module, id}`, or no item at all for anything but a row. `add` stores the item's `text` as `item_text`, which nothing sends any more, so every note has none: the filer learns a module and an id, or the page `otto`, beside the owner's words.

Expected: the filer reads what the owner pointed at.

Fix: `feedback` sends `ref.label` and `ref.quote` as the item's text, for a row and for everything else.

### The filer's orders sit in every drawer prompt

- Kind: defect
- Where: `app/modules/feedback/__init__.py` (the manifest's `agent`), `app/modules/feedback/agent.md`, `app/api.py` (`_agents`), `tests/test_app.py::test_otto_is_the_one_agent`
- Found: 09-22-2026, the stale-code audit
- Status: open

What happens: Feedback declares an agent so its filing run has a prompt and tools, and `_agents` folds every declared agent into the drawer. So every drawer turn's prompt carries the filer's orders, "You write no files" and "Reply with only the JSON object the note asks for. No prose before or after it", beside Chat's and Science's leave to write files and answer in prose. Feedback has no facet, so Settings offers no switch that would take it out.

Expected: the drawer's prompt holds what the drawer's agent does.

Fix: the filing rules move into the note the filing run already builds, and `agent.md` keeps only what Feedback is; or `_agents` skips a module whose agent serves only a one-off run.

### Routes and columns nothing reaches

- Kind: defect
- Where: `app/modules/feedback/routes.py` (the `retry` verb, `GET recent` and `RECENT`, `GET list`), `feedback_items.filed_at` and `job_id`, `tests/test_app.py::test_feedback_end_to_end`
- Found: 09-22-2026, the stale-code audit
- Status: open

What happens: the header panel that listed a page's notes and retried a failed one went with the pages. Feedback has no rows, so no row offers `retry`, and nothing requests `recent` or `list`; `filed_at` and `job_id` are written for `list` alone. A filing that fails therefore stays failed with no way to retry it. This doc's Built section still describes the header control, `page=False`, the rail and the panel.

Expected: a failed filing can be retried, and nothing is served for no one.

Fix: `retry` gets a place (the queue tool could offer it on a failed note); `recent`, `list` and the two columns go; the Built section is rewritten for point mode.
