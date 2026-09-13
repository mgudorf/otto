---
name: feature-flow
description: Worktree -> implement -> update module doc -> merge
---
Follow these steps in order for: $ARGUMENTS

Run from the primary checkout on `main` (`C:\Users\gudo\Desktop\otto`; the live database and the `.venv` exist only there). `<module>` is a directory name under `app/modules/`, or `app` for the platform, whose doc is `docs/app/CLAUDE.md`.

0. Feedback and patches: `.venv/Scripts/python.exe -m app.modules.feedback list <module>...` prints my uncleared feedback for those modules and every open `## Patches` entry that concerns them (their own doc, and entries elsewhere that name their code). Show me both lists as printed and ask which outstanding patches and feedback items this work should resolve. Wait for my answer; step 1 does not start without it.
1. `git worktree add ../wt-<slug> -b feat/<slug>` from the default branch.
2. Implement the change in that worktree only.
3. Update the module's doc (`docs/<module>/CLAUDE.md`) to match the change: `## Built` describes the code as it now is; every Patches entry the change closes is removed; every feedback item from step 0 the change does not resolve becomes a Patches entry (`Found: <date>, feedback #<id>`, my words quoted), so clearing the queue in step 6 loses nothing.
4. Run tests: `../otto/.venv/Scripts/python.exe -m pytest -q` in the worktree. Stop and report if they fail.
5. Commit, then STOP and wait for my approval before merging.
6. On approval: `git merge main` in the worktree if `main` moved (keep the shared seams in rail order), then on `main`: merge the branch, run the suite, `.venv/Scripts/python.exe -m app.modules.feedback clear <module>...`, then `git worktree remove ../wt-<slug>`.
