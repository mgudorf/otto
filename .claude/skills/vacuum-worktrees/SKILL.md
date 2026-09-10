---
name: vacuum-worktrees
description: Use when Otto's worktrees whose work is already on main should be removed; every other worktree is left alone and named.
disable-model-invocation: yes
---

# Vacuum the worktrees

Removes every worktree whose commits are all on `main`, and nothing else. Otto has no remote,
so a worktree holding commits `main` lacks is the only copy; this skill never touches one.
Runs from the primary tree with `main` checked out, never inside a worktree. It does not
merge; that is `triage-worktrees`.

## Do this

1. `git worktree list`. Skip the primary tree.
2. For each remaining worktree, gather both facts; one alone is a guess:
   - `git status --porcelain` in the worktree: any output is uncommitted work.
   - `git cherry main <branch>`: a line starting `+` is a commit whose change is not on
     `main`. This, not `git branch --merged`, decides; a squashed or rebased branch reads as
     unmerged and is not.
   Clean with no `+` lines is **vacuum**. Anything else is **keep**, with the reason:
   `<n> dirty files` or `<n> commits not on main`. A worktree whose path is gone from disk,
   or whose HEAD is detached, is **keep**; say so.
3. Print one table — worktree, branch, verdict, reason — and ask for an explicit yes on the
   **vacuum** list. Nothing is removed on your own reading.
4. On yes, for each **vacuum**: `git worktree remove <path>`, then `git branch -d <branch>`.
   Both refuse dirty or unmerged work by design; if either objects, leave that worktree and
   report what it said. Never `-f` or `-D`.
5. Reply with what was removed and what was kept, one line each with the reason.

## Rules

- Uncommitted work is never removed. There is no remote and no second copy.
- `git cherry` decides whether work is on `main`; ahead/behind counts do not.
- Remove only. No merge, rebase, commit or edit; a worktree holding work `main` lacks is
  `triage-worktrees`' job.
- Do not touch `docs/roadmap/`; retiring plans belongs to `sync-architecture`.
