---
name: triage-worktrees
description: Use when Otto's git worktrees need sorting into what has to be merged into main and in what order, what can be deleted, and what is unfinished — and then merging and removing them.
disable-model-invocation: yes
---

# Triage the worktrees

Gives every worktree one verdict — **merge**, **delete**, **unfinished** or **blocked** — puts
the **merge** verdicts in the one sequence that keeps each seam resolution small, and, after the
owner says yes, merges and removes them. Otto has no remote, so `main` in
`C:\Users\gudo\Desktop\otto` is the only record of what is built; a worktree whose work is
already there is pure clutter, and one whose work is not is the only copy. Runs on `main`,
never inside a worktree.

Every module branch touches the same five seams (`app/config.py`, `config.toml`,
`app/static/shell.js`, the contract docstring in `app/modules/__init__.py`, shared tests), each
adding adjacent lines in rail order. Merging in rail order means every branch appends below what
`main` already has at the seam; merging out of it means a branch inserts between lines `main`
already holds, which is the reflow the project rules forbid. That is the whole basis of the
ordering in step 4.

## Do this

1. Stop before anything else unless the primary tree is on `main` with `git status --porcelain`
   empty. A dirty `main` makes every merge below unreadable.
2. List the worktrees with `git worktree list`; skip the primary tree. For each one gather all
   of the following; a verdict from fewer is a guess:
   - `git status --porcelain` in the worktree: uncommitted work.
   - `git cherry main <branch>`: lines starting `+` are commits whose changes are genuinely
     absent from `main`. This, not `git branch --merged`, decides whether work survives —
     a squashed or rebased branch reads as unmerged and is not.
   - `git log --oneline main..<branch>`: what those commits actually are.
   - `git rev-list --count <branch>..main`: how far behind `main` it sits.
   - `git diff --name-only main...<branch>`: the files it changes. From this, the seams it
     touches, and its module: the one `app/modules/<name>/` directory it adds or changes
     (`docs/roadmap/<branch>/PLAN.md` names it when the branch name is not the module). A
     branch with no module of its own is a **platform** branch.
   - The module's rail position: `order=` in `git show <branch>:app/modules/<name>/__init__.py`.
   - `git merge-tree --write-tree main <branch>`: exit 0 is clean; exit 1 prints the
     conflicting paths. Writes objects only, no refs, no worktree.
   If a worktree path is gone from disk, or a branch has no worktree, say so and run nothing
   until the owner answers.
3. Assign one verdict per worktree:
   - **delete** — clean tree, no `+` lines from `git cherry`. Everything it did is on `main`.
   - **merge** — clean tree, `+` lines present. It holds work `main` lacks.
   - **unfinished** — uncommitted files. The owner's call, never yours; report the file count
     and leave it alone whatever `git cherry` says.
   - **blocked** — the test suite is red once the merge is attempted. A `merge-tree` conflict is
     not **blocked**; seam conflicts are expected and step 4 gives them a position.
4. Order the **merge** verdicts. First, for every pair of them, `git merge-tree --write-tree
   <a> <b>`: the conflicting paths are what the second of the two to land must resolve against
   the first. Split each list into seam paths and everything else; a non-seam conflict is real
   overlap and is named in the report, never buried in a count. Then tiers, and the rule inside
   the tier:
   1. **Prerequisite first.** A branch whose plan names another open branch as something it
      builds on, or whose diff imports `app.modules.<other>` that `main` lacks, goes after
      that branch. This overrides every tier below.
   2. **Free merges.** Branches that conflict with `main` and with no peer. Oldest branch
      first; they cost nothing and shrink the rest of the problem.
   3. **Platform branches.** Modules build on the frame, so the frame lands before the modules
      that will resolve against it. Fewest seams touched first.
   4. **Module branches in rail order**, ascending `order`. Same position: fewest seams first,
      then fewest commits behind `main`.
5. Print one table, one row per worktree — merge position, worktree, branch, module, rail order,
   verdict, commits ahead, commits behind, dirty files, seams touched, and **resolves against**:
   the earlier branches it conflicts with and the paths. Under the table, the **unfinished** and
   **delete** worktrees with their one-line reason, any non-seam conflict as one line naming the
   two branches and the path, and the exact commands each verdict implies. Ask for an explicit
   yes. Never merge or delete on your own reading.
6. On yes, take the **merge** verdicts one at a time in the printed order, unless the owner gives
   another: in the worktree `git merge main`, resolve keeping both sides in rail order,
   `.venv/Scripts/python.exe -m pytest -q`; then on `main` `git merge --no-ff <branch>` and
   `.venv/Scripts/python.exe -m pytest -q` again. A red suite stops that branch at once —
   `git merge --abort`, mark it **blocked**, move to the next. Do not delete a worktree you just
   merged in the same pass; it becomes a **delete** on the next triage, once the merge is proven.
7. On yes, for each **delete**: `git worktree remove <path>`, then `git branch -d <branch>`.
   Both refuse to destroy unmerged or dirty work by design — if either objects, keep the
   worktree and report what it said. Never reach for `-f` or `-D`.
8. Reply with what merged, what was removed, and what still needs the owner. Name the branches
   left **unfinished** or **blocked** and why. If anything merged, say that `sync-architecture`
   is now the next run, so `docs/ARCHITECTURE.md` describes what `main` gained.

## Rules

- Uncommitted work is never triaged away. There is no remote and no second copy; a lost
  worktree is lost.
- `git cherry` decides whether work survives; `merge-tree` decides whether it conflicts. Ahead
  and behind counts describe distance and never move a branch between tiers or verdicts.
- Behind `main` is not a verdict. Every branch drifts behind; that is what the merge fixes.
- A seam conflict is expected and gets a position; a non-seam conflict gets a sentence, because
  it is two branches building the same thing.
- One verdict and one position per worktree, and the reason fits on one line. A worktree that
  needs a paragraph is a question for the owner, not a verdict.
- The order is recomputed from git on every run; a previous run's order is never read back.
- Merge and delete are separate passes over separate branches. A branch merged this run is not
  deleted this run.
- Do not edit code, rebase, or commit anything but the merges the owner approved. Do not touch
  `docs/roadmap/`; retiring plans belongs to `sync-architecture`.
