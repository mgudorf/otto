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

None open.
