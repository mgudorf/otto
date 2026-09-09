---
name: triage-worktrees
description: Use when Otto's git worktrees need sorting into what still has to be merged into main, what can be deleted, and what is unfinished.
disable-model-invocation: yes
---

# Triage the worktrees

Gives every worktree one verdict — **merge**, **delete**, **unfinished** or **blocked** — and,
after the owner says yes, merges and removes them. Otto has no remote, so `main` in
`C:\Users\gudo\Desktop\otto` is the only record of what is built; a worktree whose work is
already there is pure clutter, and one whose work is not is the only copy. Runs on `main`,
never inside a worktree.

## Do this

1. Stop before anything else unless the primary tree is on `main` with `git status --porcelain`
   empty. A dirty `main` makes every merge below unreadable.
2. List the worktrees with `git worktree list`. For each one, gather all four facts; a verdict
   from fewer is a guess:
   - `git status --porcelain` in the worktree: uncommitted work.
   - `git rev-list --count main..<branch>`: commits `main` does not have.
   - `git cherry main <branch>`: lines starting `+` are commits whose changes are genuinely
     absent from `main`. This, not `git branch --merged`, decides whether work survives —
     a squashed or rebased branch reads as unmerged and is not.
   - `git log --oneline main..<branch>`: what those commits actually are.
   If a worktree path is gone from disk, or a branch has no worktree, say so and run nothing
   until the owner answers.
3. Assign one verdict per worktree:
   - **delete** — clean tree, no `+` lines from `git cherry`. Everything it did is on `main`.
   - **merge** — clean tree, `+` lines present. It holds work `main` lacks.
   - **unfinished** — uncommitted files. The owner's call, never yours; report the file count
     and leave it alone whatever `git cherry` says.
   - **blocked** — the merge below conflicts, or the test suite is red. Report the conflicting
     paths; do not resolve them here.
4. Print one table — worktree, branch, verdict, commits ahead, dirty files, one-line reason —
   and the exact commands each verdict implies. Ask for an explicit yes. Never merge or delete
   on your own reading.
5. On yes, take the **merge** verdicts one at a time, in the order the owner gives or oldest
   first: `git merge --no-ff <branch>`, then `.venv/Scripts/python.exe -m pytest -q`. A red
   suite or a conflict stops that branch at once — `git merge --abort`, mark it **blocked**,
   move to the next. Do not delete a worktree you just merged in the same pass; it becomes a
   **delete** on the next triage, once the merge is proven.
6. On yes, for each **delete**: `git worktree remove <path>`, then `git branch -d <branch>`.
   Both refuse to destroy unmerged or dirty work by design — if either objects, keep the
   worktree and report what it said. Never reach for `-f` or `-D`.
7. Reply with what merged, what was removed, and what still needs the owner. Name the branches
   left **unfinished** or **blocked** and why. If anything merged, say that `sync-architecture`
   is now the next run, so `docs/ARCHITECTURE.md` describes what `main` gained.

## Rules

- Uncommitted work is never triaged away. There is no remote and no second copy; a lost
  worktree is lost.
- `git cherry` decides whether work survives; ahead/behind counts only describe distance.
- Behind `main` is not a verdict. Every branch drifts behind; that is what the merge fixes.
- One verdict per worktree, and the reason fits on one line. A worktree that needs a paragraph
  is a question for the owner, not a verdict.
- Merge and delete are separate passes over separate branches. A branch merged this run is not
  deleted this run.
- Do not edit code, rebase, resolve a conflict, or commit anything but the merges the owner
  approved. Do not touch `docs/roadmap/`; retiring plans belongs to `sync-architecture`.
