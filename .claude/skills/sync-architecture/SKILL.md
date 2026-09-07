---
name: sync-architecture
description: Use when a roadmap item has been merged to main and docs/ARCHITECTURE.md must describe what now exists, retiring the roadmap plans it absorbs.
disable-model-invocation: yes
---

# Sync ARCHITECTURE.md with main

Makes `docs/ARCHITECTURE.md` the one document of Otto's current state, then removes the
roadmap plans that state now covers. Runs on `main` after a merge, never in a worktree.

## Do this

1. Establish what exists from the code, not from memory or from any plan's own status line:
   - `git log --oneline <last commit touching docs/ARCHITECTURE.md>..HEAD`
   - `app/modules/*/` (manifest, schedules, tools, agent.md), `app/api.py`, `config.toml`,
     `app/static/pages/`, `tests/`.
   - Run `.venv/Scripts/python.exe -m pytest -q`; a red suite means stop and report, not sync.
2. Read every `docs/roadmap/*/PLAN.md` and classify it against the code:
   **absorbed** (everything it planned is on `main`), **partial** (some phases are), or
   **untouched**. Work living in an unmerged worktree counts as untouched.
3. Update `docs/ARCHITECTURE.md`, keeping its shape (Summary, Daemon, module sections, UI):
   - Add or rewrite one section per built module: what it does for the owner, its tables,
     schedules, tools, agent, and any departure from the artboard. Platform facts (layout,
     contracts, config knobs, how to run and restart) go in the Daemon and Summary sections.
   - Requirements stay requirements. Sentences that are no longer true go. Nothing about
     history or plans: current functionality only, tables and bullets, one code name per
     sentence at most.
   - Keep the UI section's pointer to the design project and `docs/design/`.
4. For **partial** plans, cut the built phases down to one line each, `built; see
   ARCHITECTURE.md`, so the plan carries only what remains.
5. List the **absorbed** plans and ask for an explicit yes. Then `git rm -r docs/roadmap/<slug>`
   for each; never a bare `rm`. Git history keeps them.
6. Commit: `Sync ARCHITECTURE.md with main; retire <slugs>`. Reply with what changed in the
   doc and which plans were retired or trimmed.

## Rules

- A plan's "built" claim is not evidence. Only code and passing tests on `main` are.
- Never paste a plan into ARCHITECTURE.md. Compress to what a new agent needs to work on
  the code; a section longer than the module's own agent.md is too long.
- Do not edit code during a sync. If the doc and the code disagree, the doc changes; a real
  defect is reported in the reply, not fixed here.
- Do not touch plans whose work sits in an unmerged worktree, and do not retire a partial
  plan.
- Do not remove or soften a Daemon requirement because the code does not meet it yet;
  report the gap instead.
