## OTTO 

Otto, a personification of the word "auto" is a PERSONALIZED dashboard application aimed at meeting MY SPECIFIC NEEDS in regards to optimizing my life, throughput, and reducing wasted time and effort. 

## Intent

1. Dashboard which
   1. Covers the items that I have either had a hard time adopting/keeping up to date
   2. Have interest in or utilize frequently
   3. Slowly creates a catalog of data which defines who "I" am which will be leveraged for either recall, context, or creating "paragon" agents which enforce items that uniquely benefit me. 

## Development

1. Use worktrees for branches for each independent module.
2. **Every module touches the same shared seams, so every merge conflicts there.** The seams: `app/config.py` (a dataclass, a `Config` field, a `load` line), `config.toml` (a section), `app/static/shell.js` (an import and the `PAGES` map), the module contract docstring in `app/modules/__init__.py`, and shared tests that reach into Home. Each branch adds adjacent lines at the same spot, so git cannot auto-merge them.
   - On a branch: add your entries in rail order (the `order` in the manifest), one line each, never reflow neighbours. Tests find a module by name, never by index.
   - Before merging: `git merge main` into the branch first; the branch resolves, `main` stays clean.
   - Resolving: keep both sides in rail order. The contract docstring and shared tests take `main`'s side, then re-add anything only the branch had. Run the suite on `main` before committing the merge, then `/sync-architecture`.


## Layout

1. `app/` is the daemon. Platform files sit flat at the top: `__main__.py` launcher, `daemon.py` app factory and lifespan, `api.py` platform routes, `config.py` typed config from `config.toml`, `store.py` and `schema.sql` for SQLite and the platform tables, `scheduler.py` the clock, `runner.py` the job queue, `claude.py` the only path to the Claude CLI, `revision.py` the source hash the launcher compares.
2. `app/modules/<name>/` is one package per module. The contract (manifest, `schema.sql`, `tasks.py`, `routes.py`, `tools.py`, `agent.md`) is the docstring in `app/modules/__init__.py`; `agent_base.md` is the prompt every module agent shares. System and Feedback have no page.
3. `app/static/` is the browser side, no build step. `shell.js` is the frame and the `PAGES` map, `pages/<name>.js` one file per module page plus `activity.js` and `settings.js`, `rows.js` tokens and shared components, `session.js` the agent pane, `vendor/` pinned copies of Preact, htm, marked, KaTeX and the fonts.
4. `tests/` is one file per module plus `test_app.py`, `test_platform.py`, `test_runner.py` and `test_scheduler.py` for the platform. `conftest.py` mocks the Claude and Gmail seams so the suite runs offline.
5. `data/` is runtime state, gitignored: the SQLite file, the daemon log, `secrets/` for the Google OAuth files, `workspace/` as the working directory every Claude session is confined to.
6. `.claude/skills/` and `.claude/agents/` are the repo's own workflows: roadmap items, architecture sync, worktree triage, merge order and vacuum, finding consolidation.

## Documentation

1. `docs/ARCHITECTURE.md` is the one description of what `main` does today, periodically synced against the code base by `/sync-architecture`. This will TYPICALLY be up to date, but may be subject to changes from active worktrees.
2. `docs/roadmap/<slug>/PLAN.md` is the plan for one unit of work, written by `/create-roadmap-item` before any code and built in its own worktree. One directory per item, forever; the plan file is temporary. **Roadmap files are only ever added or consolidated, never edited.** A plan that needs a change gets a new plan, written from `ARCHITECTURE.md`, that replaces the old file whole; the sync removes a plan once its branch has landed and never writes into one. A plan is never documentation: anything worth keeping goes into `ARCHITECTURE.md` before the plan goes. `patches/PLAN.md`, rewritten whole by the consolidate-patches agent from the findings below, is the one consolidation.
3. `docs/bugs/`, `docs/defects/` and `docs/gaps/` hold one file per open finding, filed by the sync and sorted by what closes it: code, an owner decision, or a roadmap item or owner action.
4. `docs/design/` is the imported Claude Design artboard and its runtime; open the html in a browser. It is the source for hues, icons and each page's LEFT and MIDDLE shape.

## Findings

1. **A bug, defect or gap seen during unrelated work is filed as its own markdown before the work continues.** It goes in `docs/bugs/`, `docs/defects/` or `docs/gaps/`, chosen by what closes it as above. Naming it only in a reply loses it; a reply is not a record. File it in whatever tree you are working in, so it merges with the branch.
2. **Expand an existing finding rather than duplicating it.** Read all three folders first. When an open file already covers the same cause, add what you saw to that file — another `Where:` path, a sentence in `What happens:` — instead of writing a second one. A related but separate cause gets its own file.
3. **Shape is the sync's shape**, so the two are indistinguishable: `# <Title>`, then `- Where:`, `- Found: <date>, <what saw it>`, `- Status: open`, then one paragraph each for `What happens:`, `Expected:` and `Fix:`.
4. **Filing is not fixing.** Do not detour to repair what you filed; the fix is a patch plan or the owner's call. Something inside the scope of the current change is fixed in that change and needs no file.
