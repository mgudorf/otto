# Five nightly LLM tasks compete for three runs a day

- Where: `config.toml` `[nightly] max_sessions = 3`; `memory.suggest`, `education.generate`, `email.triage`, `business.scout`, `web_search.nightly`
- Found: 2026-09-09, sync-architecture
- Status: resolved 2026-09-10 — the file can go

What happens: five scheduled tasks declare `llm=True` and each is due once every 24 hours inside the same window, but the budget allows three runs a day. Today all of them run only because the cap is not enforced against runs in flight (`docs/bugs/budget-counts-finished-runs-only.md`); once that is fixed, the last two to reach a free worker are refused with `BudgetExceeded`. Which two lose is decided by the order the scheduler happens to submit them, so the same task can starve several nights running, and the owner arrives to a module that quietly did not update.

Expected: every nightly task either runs each night, or is refused in an order the owner chose.

Decided (owner, 2026-09-10): `max_sessions` is raised to five, one per nightly task, and the owner gets a `runs` switch per module on Settings to take one out of the lineup by hand rather than have the scheduler pick a loser. The scheduler now also holds nightly runs to one per `[nightly] stagger_minutes` and orders due tasks by `next_run, name`, so they no longer overlap and the order is no longer arbitrary.

Still open and unchanged by this: `docs/bugs/budget-counts-finished-runs-only.md` and `docs/bugs/budget-refusal-marks-job-failed.md`. A refusal is no longer due every night, so the second is less urgent, but four of the five nightly tasks still record one as a failure.
