---
name: feedback-queue
description: List or clear my feedback queue and the open patches for one or more modules; feature-flow's step 0 and step 6, and useful on its own before any change.
---
Run from the primary checkout (`C:\Users\gudo\Desktop\otto`); a worktree has no `data/otto.db`.

`.venv/Scripts/python.exe -m app.modules.feedback list $ARGUMENTS`

For each module named (a directory under `app/modules/`, or `activity` / `settings` for the shell pages) it prints every feedback row not yet cleared (my words verbatim, the filed kind, title, summary, ref and draft) and every open `## Patches` entry that concerns the module: its own `docs/<module>/CLAUDE.md`, plus entries in other docs that name `app/modules/<module>/`, `pages/<module>.js` or `/api/<module>/`. Show me the output as printed; do not summarize the feedback text.

`.venv/Scripts/python.exe -m app.modules.feedback clear <module>...` stamps `cleared_at` on those rows and prints their ids; nothing is deleted. Clear only once every row was either resolved on `main` or written into the module doc's Patches section.
