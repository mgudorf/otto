# Feedback

## Built

A `feedback` control in the header of every page records a change the owner wants, together with the selected item when its inspector loaded. `POST /api/feedback/action/add` (400 on an empty page or text) writes the row, an event under the originating page, and returns `{id}` at once after submitting a filing job on resource `feedback`; `retry` requeues a failed one (404 unknown, 409 unless `failed`). The filing job is a `oneshot` run with `feedback.max_turns` and the read tools `docs_list`, `docs_read` (markdown under `docs/` only) and `feedback_list`; its prompt carries the id, time, page, selected item (text cut to 300) and the owner's words in fenced blocks. The agent replies with one JSON object and the job writes it to the row: `kind` (bug, defect, gap or roadmap), `title` (120), `summary` (200), `tags` (eight of 40), `ref` (the existing `docs/` file it belongs in) and `draft` (the body ready for that file, with the owner's words quoted). A reply that is not that object marks the row `failed` with the error and the job failed. `GET /api/feedback/recent` feeds the panel with the last five rows; `GET /api/feedback/list` gives every field over HTTP, and the `feedback_list` tool gives agents everything but `item_text`, `draft`, `filed_at`, `job_id`, `error` and `cleared_at`. Nothing touches the repo; the row is the record. Table `feedback(created_at, page, item_module, item_id, item_text, text (the owner's words, verbatim), status queued, filed or failed, kind, title, summary, tags JSON, ref, draft, filed_at, job_id, error, cleared_at)`. The manifest sets `page=False`, hue `#8b8f98`, order 99, so there is no rail entry; `setup` adds `cleared_at` to a `feedback` table that predates it, the stamp `python -m app.modules.feedback clear <module>` sets once a work session has read a row; the agent's Current state block names the built modules and each doc's count of open Patches entries. Panel: 360px, a 3-row textarea with the page and item as context, `Send` (Enter; Shift+Enter breaks, Esc closes and keeps the draft), rows reading `filing…`, `<kind> <summary>` or `failed <error>` with `retry`.

The `feedback` control in the header and its panel are not in the artboard; they reuse the header meta style, the panel surfaces, the composer textarea and compact rows.

## Patches

### A feedback note stays `queued` forever after a restart or during a drain

- Kind: bug
- Where: `app/modules/feedback/routes.py` `add` and `_submit`; `app/runner.py` `start` (orphans marked failed) and `submit` (raises while draining)
- Found: 2026-09-12, sync-architecture
- Status: open

What happens: `add` inserts the `feedback` row as `queued` and submits the filing job in memory only. If the daemon restarts before the run finishes (the launcher restarts it on every code change), `Runner.start` marks the orphaned job `failed` but nothing touches the `feedback` row, so the panel shows `filing…` forever and `retry` answers 409 because the row is not `failed`. During a drain the same row is written first and then `runner.submit` raises `daemon is restarting`, so the client gets a 500 and the row sits `queued` with nothing to resubmit it.

Expected: a note whose filing job died reads `failed` with the reason and can be retried; a note sent during a drain is either refused before the row exists or picked up after the restart.

Fix: at boot, mark `feedback` rows still `queued` as `failed` with `daemon restarted` (the runner already does this for jobs), and in `add` check the runner's draining flag before the insert. Requeueing them instead is also one query over `status = 'queued'` at boot.
