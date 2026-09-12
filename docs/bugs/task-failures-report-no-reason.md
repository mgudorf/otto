# A failed task reports no reason anywhere in the UI

- Where: `app/runner.py` `_finish` (line 152 writes the event, line 149 writes `tasks.last_result`)
- Found: 2026-09-12, email organization roadmap session
- Status: open

What happens: both places that surface a failure take the wrong slice of the traceback. The event text is `(error or '').strip().splitlines()[-1][:200]`, the traceback's last line, which is the exception message only when that message is single-line; `tasks.last_result` is `(error or text or '')[:500]`, the traceback's first 500 characters, which is frame headers and never reaches the exception. `GmailError` renders as `gmail 401: {` then the JSON body over several lines, so on 2026-09-12 Otto recorded 216 consecutive `email.sync` failures over roughly eight hours whose entire Activity text was `email.sync: }` and whose `last_result` was three `File "..."` frames. The two real causes, an expired refresh token (`invalid_grant`) and then a deleted client secret (`invalid_client`), were readable only by grepping `data/daemon.log`. Any exception whose message spans lines loses its reason the same way, in every module.

Expected: the event names the exception, and `tasks.last_result` holds the end of the traceback, so Activity says why a task failed without the owner opening the log.

Fix: take the last non-blank line of the formatted exception rather than of the whole traceback (`traceback.format_exception_only(e)[-1]`), and slice `last_result` from the tail (`error[-500:]`) so the exception survives. Neither changes the stored `jobs.error`, which is already the full traceback.
