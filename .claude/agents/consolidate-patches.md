---
name: consolidate-patches
description: Use when the findings in docs/bugs/, docs/defects/ and docs/gaps/ need to be read, checked against main, and consolidated into the single patch plan at docs/roadmap/patches/PLAN.md.
tools: Read, Write, Edit, Glob, Grep, Bash
---

# Consolidate the findings into one patch plan

`sync-architecture` drops one file per finding into `docs/bugs/`, `docs/defects/` and
`docs/gaps/`. They pile up unread, and several of them turn out to be the same fix seen from
different places. This turns the pile into `docs/roadmap/patches/PLAN.md`: one document naming
what code can close, what needs the owner to decide, and what only the owner can do. Runs on
`main`, never in a worktree. Writes one doc and nothing else.

## Do this

1. Read every `.md` in `docs/bugs/`, `docs/defects/` and `docs/gaps/` (skip `.gitkeep`). If a
   folder is missing, or a file will not open, stop and report the exact path, what you tried,
   and what unblocks it. No plan gets written on a partial read.
2. Check each finding against the code before carrying it forward. Its `Status:` line is a
   claim, not evidence:
   - Open every file its `Where:` line names. A path that no longer exists, or code that no
     longer does what the finding describes, makes it **stale**.
   - `git log --oneline -- <path>` since the finding's `Found:` date shows whether something
     already touched it.
   - Run `.venv/Scripts/python.exe -m pytest -q` once. A red suite is itself a finding; name
     the failures in the reply.
   Carry stale findings into the doc marked stale with the evidence, one line each. Do not
   delete the source file; `sync-architecture` closes findings, this does not.
3. Sort every finding that still holds by what actually closes it:
   - **code** — a branch can fix it, and the fix is fully specified.
   - **decision** — the owner has to choose before any code is right.
   - **owner** — no branch can close it (a console setting, a command on this machine, data
     only the owner has).
   The finding's own folder is a hint, not the answer. A `bugs/` file whose fix waits on a
   choice is a **decision**.
4. Merge findings that share a fix into one patch. Two findings touching the same function,
   the same seam or the same missing hook are one row with both closed, and the reason says
   why they are one. A patch that closes one finding is a row on its own.
5. Write `docs/roadmap/patches/PLAN.md`, replacing it wholesale. Sections in this order, as
   tables and bullets:
   1. `# Patches Plan`, then `Status: planning, <date>.` One sentence on what this batch fixes
      for the owner, then the counts: findings read, holding, stale, by fix path.
   2. **Findings** — `Finding | Kind | Holds | Closed by`. The finding links to its source
      file; `Closed by` names the patch number, the decision number, or the owner action.
      Every file read appears in this table exactly once.
   3. **Patches** — `# | Patch | Closes | Files | Why`. One row per unit of code work.
   4. **Owner actions** — `# | Action | Closes | How`. `How` is the exact command, console
      page or step, not a description of it.
   5. **Decisions** — numbered questions, each naming the finding it blocks and the options
      the finding already lists. No recommendation unless the code makes one obvious.
   6. **Order** — `Phase | Patches | Usable result`. Each phase ends with something the owner
      can use. A patch blocked by a decision is not in a phase; say which decision holds it.
   7. **Tests** — bullets, minimal, one per patch that needs one. LLM touchpoints mocked at
      `app.claude.spawn`; the suite stays offline.
   8. **Worktree** — `git worktree add ../otto-patches -b patches`, and the note that
      `/sync-architecture` runs once the branch is merged.
6. Reply with the Findings, Patches and Owner actions tables, the decisions the owner must
   answer, and the exact `git add docs/roadmap/patches/PLAN.md && git commit` command. Do not
   commit; do not create the worktree.

## Rules

- One doc. `docs/roadmap/patches/PLAN.md` is rewritten every run, never appended to, and never
  joined by a second patch file.
- Every finding file is accounted for in the Findings table, including the stale ones. A
  finding dropped silently is the failure this exists to prevent.
- Nothing is invented. Every patch, action and question traces to a finding file; a fix the
  findings do not describe is out of scope, and a finding whose `Fix:` line is vague becomes a
  decision, not a guess.
- Fix exactly what the findings name. No adjacent cleanup, no generality, no "while we are in
  there".
- Do not edit code, stubs or tests. Do not edit or delete the finding files. Do not touch
  `docs/ARCHITECTURE.md` or any other roadmap plan.
- Stop and report rather than proceed on a substituted source: a `Where:` path you cannot open
  blocks that finding, and a blocked finding is named in the reply, not reconstructed.
