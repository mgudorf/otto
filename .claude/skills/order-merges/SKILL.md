---
name: order-merges
description: Use when more than one of Otto's worktrees holds work main lacks and the owner wants the sequence to merge them in that keeps every seam resolution small and in rail order.
disable-model-invocation: yes
---

# Order the merges

Reads every open worktree and prints the one sequence to merge them in, with what each
branch will have to resolve and why it sits where it does. Reads only: no merge, no checkout,
no edit. `triage-worktrees` merges "in the order the owner gives"; this skill is where that
order comes from. Runs from the primary tree on `main`.

Every module branch touches the same five seams (`app/config.py`, `config.toml`,
`app/static/shell.js`, the contract docstring in `app/modules/__init__.py`, shared tests), each
adding adjacent lines in rail order. Merging in rail order means every branch appends below what
`main` already has at the seam; merging out of it means a branch inserts between lines `main`
already holds, which is the reflow the project rules forbid. That is the whole basis of the
ordering below.

## Do this

1. `git worktree list`. Skip the primary tree. For each worktree gather, in this order:
   - `git status --porcelain` in the worktree: dirty file count.
   - `git cherry main <branch>`: count of `+` lines. Zero means nothing to merge.
   - `git rev-list --count <branch>..main`: how far behind `main` it sits.
   - `git diff --name-only main...<branch>`: the files it changes. From this, the seams it
     touches, and its module: the one `app/modules/<name>/` directory it adds or changes
     (`docs/roadmap/<branch>/PLAN.md` names it when the branch name is not the module). A
     branch with no module of its own is a **platform** branch.
   - The module's rail position: `order=` in `git show <branch>:app/modules/<name>/__init__.py`.
   - `git merge-tree --write-tree main <branch>`: exit 0 is clean; exit 1 prints the
     conflicting paths. Writes objects only, no refs, no worktree.
   A worktree whose path is gone from disk is reported and left out; say so.
2. For every pair of branches that both have work to merge, `git merge-tree --write-tree <a> <b>`.
   The conflicting paths are what the second of the two to land must resolve against the
   first. Split each list into seam paths and everything else; a non-seam conflict is real
   overlap and is named in the report, never buried in a count.
3. Leave out, and list separately with the reason:
   - **unfinished**: dirty files. The owner's call, never yours.
   - **nothing to merge**: no `+` lines. That is `vacuum-worktrees`' list.
4. Order the rest. Tiers first, then the rule inside the tier:
   1. **Prerequisite first.** A branch whose plan names another open branch as something it
      builds on, or whose diff imports `app.modules.<other>` that `main` lacks, goes after
      that branch. This overrides every tier below.
   2. **Free merges.** Branches that conflict with `main` and with no peer. Oldest branch
      first; they cost nothing and shrink the rest of the problem.
   3. **Platform branches.** Modules build on the frame, so the frame lands before the modules
      that will resolve against it. Fewest seams touched first.
   4. **Module branches in rail order**, ascending `order`. Same position: fewest seams first,
      then fewest commits behind `main`.
5. Print one table, one row per branch in merge position: position, branch, module, rail order,
   commits ahead, commits behind, seams touched, and **resolves against** — the earlier branches
   it conflicts with and the paths. Under the table, the excluded worktrees with their reason,
   and any non-seam conflict with the two branches and the path on one line.
6. Print the sequence as commands, one block per branch in order: in the worktree
   `git merge main`, resolve keeping both sides in rail order, `.venv/Scripts/python.exe -m
   pytest -q`; then on `main` `git merge --no-ff <branch>`. End by saying the list is the order
   to give `triage-worktrees`, and that `sync-architecture` follows the last merge.

## Rules

- Read only. No merge, rebase, checkout, edit or commit; `merge-tree` is the only thing that
  writes, and it writes no refs.
- `git cherry` decides whether a branch has work; `merge-tree` decides whether it conflicts.
  Ahead and behind counts describe distance and never move a branch between tiers.
- A seam conflict is expected and gets a position; a non-seam conflict gets a sentence, because
  it is two branches building the same thing.
- One row per branch and the reason fits in the tier name. A branch that needs a paragraph is
  a question for the owner, not a position.
- Every rerun recomputes from git; the previous order is never read back.
