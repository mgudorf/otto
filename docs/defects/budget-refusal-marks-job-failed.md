# Budget refusal marks the job failed instead of skipped

- Kind: defect
- Where: `app/claude.py` `run_task`; every task that calls `ctx.run_task` (today `app/modules/memory/tasks.py` `suggest`)
- Found: 2026-09-07, sync-architecture
- Status: open

What happens: outside the nightly window or past `max_sessions`, `run_task` writes a `skipped` row to `llm_runs` and raises `BudgetExceeded`; the runner records the job as `failed` with a traceback and writes a `failed` event, so Activity shows a refusal as a failure.

Expected: the job reads `skipped` with the reason and no `failed` event is written.

Fix: have the runner treat `BudgetExceeded` like `Skipped` (one `except` in `Runner._run`), or catch it in each task and return `Skipped(str(e))`.
