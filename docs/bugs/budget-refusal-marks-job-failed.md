# Budget refusal marks the job failed instead of skipped

- Where: `app/claude.py` `run_task`; `app/modules/memory/tasks.py` `suggest`, `app/modules/email/tasks.py` `triage`, `app/modules/business/tasks.py` `scout`
- Found: 2026-09-07, sync-architecture
- Status: open

What happens: outside the nightly window or past `max_sessions`, `run_task` writes a `skipped` row to `llm_runs` and raises `BudgetExceeded`; the runner records the job as `failed` with a traceback and writes a `failed` event, so Activity shows a refusal as a failure. `app/modules/education/tasks.py` `generate` is the only task that catches it and returns `Skipped`; the other three do not. With four nightly LLM tasks against three runs a day, at least one refusal happens every night.

Expected: the job reads `skipped` with the reason and no `failed` event is written.

Fix: have the runner treat `BudgetExceeded` like `Skipped` (one `except` in `Runner._run`), which covers every task at once and lets the three tasks stop repeating the catch.
