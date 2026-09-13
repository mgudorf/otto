---
name: sync-architecture
description: Use when main has moved without its docs: checks docs/app/CLAUDE.md and every docs/<module>/CLAUDE.md against the code, fixes drift, and files or closes Patches entries.
disable-model-invocation: yes
---

# Sync the docs with main

Makes `docs/app/CLAUDE.md` (the platform) and each `docs/<module>/CLAUDE.md` (one module) describe what
`main` does today, and keeps every doc's `## Patches` section current. Runs on `main` after merges or edits
that bypassed `/feature-flow`, never in a worktree. Edits docs only.

## Do this

1. `git log --oneline <last commit touching docs/>..HEAD` and `git status --short`: the code that moved.
   Run `.venv/Scripts/python.exe -m pytest -q`; a red suite means stop and report, not sync.
2. For each module the log touched (`app/modules/<name>/`, `app/static/pages/<name>.js`,
   `tests/test_<name>.py`), read the code and its doc. Rewrite the `## Built` rows that no longer hold:
   what it does for the owner, tables, routes, hooks, tools, schedules, page, departures from the artboard.
   Platform changes (`app/*.py`, `app/static/` outside `pages/`, `config.toml`) go to `docs/app/CLAUDE.md`.
   Requirements stay requirements; sentences no longer true go; nothing about history or plans.
3. Patches: read every doc's `## Patches`. An entry whose `Where:` code no longer does what it describes is
   closed. A divergence you saw that no entry covers gets one, in the shape the project CLAUDE.md gives,
   `Found: <date>, sync-architecture`. Expand an entry that already covers the cause instead of adding one.
4. List the closures and ask for an explicit yes before removing them.
5. Commit: `Sync docs with main: <modules>`. Reply with what changed per doc and which entries were
   added or closed.

## Rules

- The doc changes, never the code. A bug found here is a Patches entry and a line in the reply.
- A doc states what the code does; the divergence lives only in Patches. No "not yet" inside `## Built`.
- Compress: a `## Built` table longer than the module's own agent.md is too long.
- Do not describe work sitting in an unmerged worktree; an entry may say it is in progress on a branch.
