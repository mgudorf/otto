# Nightly budget counts finished runs only, so concurrent runs slip past the cap

- Where: `app/claude.py` `ClaudeRunner.budget` and `run_task`; `app/runner.py` worker count
- Found: 2026-09-10, sync-architecture
- Status: open

What happens: `budget()` counts `llm_runs` rows with status `done` or `failed`, and `run_task` writes its row only after the CLI exits. The scheduler submits every nightly task in the same tick and the runner starts `max_concurrent` of them at once, so each sees `used = 0`. On 2026-09-09 three runs started at 02:00:02 local and a fourth at 02:00:05 after the first finished; all four completed against `max_sessions = 3`. The cap holds only when runs happen to serialize.

Expected: at most `max_sessions` budgeted runs start per local day, whatever the concurrency.

Fix: write the `llm_runs` row with status `running` before spawning and count `running` too, updating the row to `done` or `failed` afterwards; or hand every `llm=True` schedule the same resource so they serialize and the count is exact.
