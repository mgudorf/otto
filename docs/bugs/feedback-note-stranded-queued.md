# A feedback note stays `queued` forever after a restart or during a drain

- Where: `app/modules/feedback/routes.py` `add` and `_submit`; `app/runner.py` `start` (orphans marked failed) and `submit` (raises while draining)
- Found: 2026-09-12, sync-architecture
- Status: open

What happens: `add` inserts the `feedback` row as `queued` and submits the filing job in memory only. If the daemon restarts before the run finishes (the launcher restarts it on every code change), `Runner.start` marks the orphaned job `failed` but nothing touches the `feedback` row, so the panel shows `filing…` forever and `retry` answers 409 because the row is not `failed`. During a drain the same row is written first and then `runner.submit` raises `daemon is restarting`, so the client gets a 500 and the row sits `queued` with nothing to resubmit it.

Expected: a note whose filing job died reads `failed` with the reason and can be retried; a note sent during a drain is either refused before the row exists or picked up after the restart.

Fix: at boot, mark `feedback` rows still `queued` as `failed` with `daemon restarted` (the runner already does this for jobs), and in `add` check the runner's draining flag before the insert. Requeueing them instead is also one query over `status = 'queued'` at boot.
