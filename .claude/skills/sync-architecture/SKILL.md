---
name: sync-architecture
description: Use when a roadmap branch has merged to main and docs/ARCHITECTURE.md must describe what now exists; records findings and removes the plans whose work landed.
disable-model-invocation: yes
---

# Sync ARCHITECTURE.md with main

Makes `docs/ARCHITECTURE.md` the one document of Otto's current state, records every finding
in `docs/bugs/`, `docs/defects/` or `docs/gaps/`, then removes the roadmap plans whose branch
has landed. Runs on `main` after a merge, never in a worktree. Toward `docs/roadmap/` it is
reductive only: it deletes whole plan files and never writes into one.

## Do this

1. Establish what exists from the code, not from memory or from any plan's own status line:
   - `git log --oneline <last commit touching docs/ARCHITECTURE.md>..HEAD`
   - `app/modules/*/` (manifest, schedules, tools, agent.md), `app/api.py`, `config.toml`,
     `app/static/pages/`, `tests/`.
   - Run `.venv/Scripts/python.exe -m pytest -q`; a red suite means stop and report, not sync.
2. Read every `docs/roadmap/*/PLAN.md` and classify it against the code:
   - **landed**: `main` holds its first phase; the files its Layout section names exist and
     do what that phase says. A merge commit or an empty `git cherry main <branch>` confirms
     it; the code decides.
   - **unstarted**: none of it is on `main`, or its branch sits in a worktree with commits
     `main` lacks (`git worktree list`, `git cherry main <branch>`).
   There is no partial class. A landed plan is read once more, here, and then removed
   whatever share of it was built.
3. Update `docs/ARCHITECTURE.md`, keeping its shape (Summary, Daemon, module sections, UI):
   - Add or rewrite one section per built module: what it does for the owner, its tables,
     schedules, tools, agent, and any departure from the artboard. Platform facts (layout,
     contracts, config knobs, how to run and restart) go in the Daemon and Summary sections.
   - Every fact a landed plan carries about how `main` behaves that the doc lacks and a new
     agent would need moves into the doc now, verified against the code. This is the last
     time the plan is read.
   - Requirements stay requirements. Sentences that are no longer true go. Nothing about
     history or plans: current functionality only, tables and bullets, one code name per
     sentence at most.
   - Keep the UI section's pointer to the design project and `docs/design/`.
4. Record every finding as one file, `docs/<kind>/<slug>.md`, where the folder is the kind:
   - `bugs/`: the code does something it was not meant to do (wrong result, wrong status,
     crash). The fix is code.
   - `defects/`: works as built, but what was built is wrong for the owner, or contradicts the
     artboard or a tenet. The fix starts with a decision.
   - `gaps/`: a requirement or artboard element `main` does not meet yet. The fix is a roadmap
     item or an owner action. A phase of a landed plan that `main` lacks is a gap only when a
     requirement or the artboard asks for it; its `Fix:` names the work, never the removed
     file.
   Shape: `# <Title>`, then `- Where: <file or requirement>`, `- Found: <date>, sync-architecture`,
   `- Status: open | owner action | deferred by the owner`, then one paragraph each for
   `What happens:`, `Expected:`, `Fix:`. Update a file that already exists. Read all three
   folders first: a file whose finding is gone from `main` joins the removal list in step 5.
5. List the **landed** plans and the closed finding files and ask for an explicit yes. Then
   `git rm docs/roadmap/<slug>/PLAN.md` and `git rm` each closed finding; never a bare `rm`.
   The plan's directory stays with its `.gitkeep` (add one if it has none). Git history keeps
   the text.
6. Commit: `Sync ARCHITECTURE.md with main; retire <slugs>`. Reply with what changed in the
   doc, which findings were added or closed by kind, and which plans were removed, naming any
   phase of them that was never built.

## Rules

- Reductive on `docs/roadmap/`: the only change this skill makes there is `git rm` of a
  whole `PLAN.md`. No status line, no trimmed phase, no `built; see ARCHITECTURE.md`, no
  edit of any kind. Work a removed plan still describes is a `gaps/` file and, when the
  owner wants it, a new plan from `/create-roadmap-item`.
- A plan is not documentation. ARCHITECTURE.md is the only description of what `main` does;
  what a plan says that is true, useful and absent from the doc goes into the doc, and the
  rest goes with the plan.
- A plan's "built" claim is not evidence. Only code and passing tests on `main` are.
- Never paste a plan into ARCHITECTURE.md. Compress to what a new agent needs to work on
  the code; a section longer than the module's own agent.md is too long.
- Do not edit code during a sync. If the doc and the code disagree, the doc changes; a bug
  gets a file in `docs/bugs/` and a line in the reply, never a fix here.
- ARCHITECTURE.md states what the code does; the divergence from a requirement lives only in
  the three finding folders. Do not write "not yet" or "deferred" notes into the doc.
- One folder per finding, chosen by its fix: code, a decision, or a roadmap item. When two
  fit, the earlier one in that order wins.
- Do not touch a plan whose work sits in an unmerged worktree.
- Do not remove or soften a Daemon requirement because the code does not meet it yet;
  report the gap instead.
