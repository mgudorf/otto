# Four nightly LLM tasks compete for three runs a day

- Where: `config.toml` `[nightly] max_sessions = 3`; `memory.suggest`, `education.generate`, `email.triage`, `business.scout`
- Found: 2026-09-09, sync-architecture
- Status: open, needs a decision

What happens: four scheduled tasks declare `llm=True` and each is due once every 24 hours inside the same window, but the budget allows three runs a day. The fourth to reach the scheduler is refused with `BudgetExceeded`. Which one loses is decided by the order the scheduler happens to submit them, so the same task can starve several nights running, and the owner arrives to a module that quietly did not update.

Expected: every nightly task either runs each night, or is refused in an order the owner chose.

Fix: decide between raising `max_sessions` (the owner's stated concern is the weekly token allowance, not the run count), giving schedules a priority the scheduler honours when the budget is short, or moving a task off the nightly LLM path. Whichever is chosen, `docs/bugs/budget-refusal-marks-job-failed.md` should be fixed with it so a refusal reads as skipped rather than failed.
