---
name: feature-flow
description: Worktree -> implement -> update module doc -> merge
---
Follow these steps in order for: $ARGUMENTS

Run from the primary checkout on `main` (`C:\Users\gudo\Desktop\otto`; the live database and the `.venv` exist only there). `<module>` is a directory name under `app/modules/`, or `app` for the platform, whose doc is `docs/app/CLAUDE.md`.

0. Feedback and patches: `.venv/Scripts/python.exe -m app.modules.feedback list <module>...` prints my uncleared feedback for those modules and every open `## Patches` entry that concerns them (their own doc, and entries elsewhere that name their code). Show me both lists as printed. Every item listed is in scope for this change alongside the requested feature; the change resolves all of them. Sort each item by whether its fix is determined by the code or by me. A bug, a defect against the artboard or a tenet, or a gap with one obvious shape has a determined fix: resolve it without asking. An item whose fix turns on my preference, on what content or data to show, or on a choice between designs needs my decision: list those items in one message, each with the decision needed and your recommended option, and wait for my answer. If no item needs a decision, start step 1 without asking.
1. `git worktree add ../wt-<slug> -b feat/<slug>` from the default branch.
2. Implement the change in that worktree only.
3. Update the module's doc (`docs/<module>/CLAUDE.md`) to match the change: `## Built` describes the code as it now is; every Patches entry the change closes is removed; every feedback item from step 0 that my answer deferred becomes a Patches entry (`Found: <date>, feedback #<id>`, my words quoted), so clearing the queue in step 6 loses nothing.
4. Run tests: `../otto/.venv/Scripts/python.exe -m pytest -q` in the worktree. Stop and report if they fail.
5. Commit, then STOP and wait for my approval before merging.
6. On approval: `git merge main` in the worktree if `main` moved (keep the shared seams in rail order), then on `main`: merge the branch, run the suite, `.venv/Scripts/python.exe -m app.modules.feedback clear <module>...`, then `git worktree remove ../wt-<slug>`.
