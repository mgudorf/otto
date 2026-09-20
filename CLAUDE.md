## OTTO 

Otto, a personification of the word "auto" is a PERSONALIZED dashboard application aimed at meeting MY SPECIFIC NEEDS in regards to optimizing my life, throughput, and reducing wasted time and effort. 

## Intent

1. Dashboard which
   1. Covers the items that I have either had a hard time adopting/keeping up to date
   2. Have interest in or utilize frequently
   3. Slowly creates a catalog of data which defines who "I" am which will be leveraged for either recall, context, or creating "paragon" agents which enforce items that uniquely benefit me. 


## UI

1. **Let the functionality speak for itself. This rule keeps being broken, so hold every change to it.** If the surrounding content already makes a thing's purpose evident, it gets no title, label, caption or hint. A date is a date: never "captured 09-18-2026", "follow up 10-02-2026" or "due 09-15-2026", only the date. A row of tags gets no word "Tags" above it. A skill in the palette gets no "runs in the drawer" beside it and its group is "Skills", not "Home agent skills". Enter gets no "send", the search bar no description of what to type, the chat box no "ask about this page", a button no key beside its label. A symbol that depicts the function carries it; text next to it is clutter. What still gets a title: a module's name. Nothing whose meaning the content already shows. The `?` overlay is the one place keys are listed.
2. **No chrome text.** A title is the module's title. No counts, no column headers, no separator lines, no content previews; a date only on a date-bound item. The one exception is Home's counts strip in the header: there each number keeps its word, because without it the number means nothing.
3. **Tags are neutral and one system.** No colours. Identity tags and my own tags look the same, five show and then "+N", and they align in one column.
4. **Colour is the module's hue on a card's left border and on a primary button, nothing else.** A hovered card deepens its tint; its neighbours keep theirs, so the eye can still find them. Depth comes from canvas, plates and shadows. Rainbow is the dark palette tinted with the open module's hue; Dark is neutral apart from those two places; there is no light theme, and no white button on dark.
5. **PP Formula everywhere, one cut per text role; Geist Mono for code.** The one exception is an Education question body: a textbook serif with LaTeX rendered.
6. **Selection is an intersection, never a path.** Tags in the search bar and tags picked on the Graph are the same set; adding one narrows. A related item from another module previews in place; nothing navigates away to show it.
7. **The browser owns history.** Every page change is a history entry, so the mouse back and forward buttons walk pages.
8. **Home shows what waits, or the five newest items per module.** Priority and Recent are its two modes; neither explains itself, and the search bar's tokens narrow both.
9. **A state change is a button.** Delete, edit, forget and the like are real buttons, never italic text. A destructive button is tinted a subtle red; the × on a tag chip is not.

## Development

1. **Module work goes through `/feature-flow <what to change>`.** One worktree per change (`git worktree add ../wt-<slug> -b feat/<slug>` from `main`), the module doc updated in the same commit as the code, the suite green, my approval before the merge. Nothing is implemented on `main`.
2. **Before new work, list what is already owed and resolve it.** `/feedback-queue <module>` (feature-flow's step 0) prints my uncleared feedback and the open `## Patches` entries for the module; show me both, and the change resolves every one of them alongside the feature. Ask only about an item whose fix depends on my decision (a preference, what content or data to show, a choice between designs); an item with a determined fix, such as a bug, is resolved without asking.
3. **Every module touches the same shared seams, so every merge conflicts there.** The seams: `app/config.py` (a dataclass, a `Config` field, a `load` line), `config.toml` (a section), `app/static/shell.js` (an import and the `PAGES` map), the module contract docstring in `app/modules/__init__.py`, and shared tests that reach into Home. Each branch adds adjacent lines at the same spot, so git cannot auto-merge them.
   - On a branch: add your entries in rail order (the `order` in the manifest), one line each, never reflow neighbours. Tests find a module by name, never by index.
   - Before merging: `git merge main` into the branch first; the branch resolves, `main` stays clean.
   - Resolving: keep both sides in rail order. The contract docstring and shared tests take `main`'s side, then re-add anything only the branch had. Run the suite on `main` before committing the merge.

## Commands

1. `.venv/Scripts/python.exe -m pytest -q` runs the suite, offline; in a worktree it is `../otto/.venv/Scripts/python.exe -m pytest -q`. `README.md` lists every other command.
2. `data/otto.db` and `.venv` exist only in the primary checkout, so commands that read or write the database run there, never in a `wt-*` worktree.

## Layout

1. `app/` is the daemon. Platform files sit flat at the top: `__main__.py` launcher, `daemon.py` app factory and lifespan, `api.py` platform routes, `config.py` typed config from `config.toml`, `store.py` and `schema.sql` for SQLite and the platform tables, `migrate.py` the table names an older database used and the boot step that renames them, `scheduler.py` the clock, `runner.py` the job queue, `claude.py` the only path to the Claude CLI, `revision.py` the source hash the launcher compares, `build.py` the step that turns `otto.png` into `app/static/otto.ico` and `Otto.exe`.
2. `app/modules/<name>/` is one package per module. The contract (manifest, `schema.sql`, `tasks.py`, `routes.py`, `tools.py`, `agent.md`) is the docstring in `app/modules/__init__.py`; `agent_base.md` is the prompt every module agent shares. System and Feedback have no page.
3. `app/static/` is the browser side, no build step. `shell.js` is the frame and the `PAGES` map, `pages/<name>.js` one file per module page plus `activity.js` and `settings.js`, `rows.js` tokens and shared components, `session.js` the agent pane, `api.js` the fetch helpers, `md.js` markdown with LaTeX, `feedback.js` and `module_settings.js` the header's two panels, `vendor/` pinned copies of Preact, htm, marked, KaTeX, highlight.js and the fonts.
4. `tests/` is one file per module (Home and System have none; the shared tests cover them) plus `test_app.py`, `test_migrate.py`, `test_platform.py`, `test_runner.py` and `test_scheduler.py` for the platform. `conftest.py` mocks the Claude and Gmail seams so the suite runs offline.
5. `data/` is runtime state, gitignored: the SQLite file, the daemon log, `secrets/` for the Google OAuth files, `workspace/` as the working directory every Claude session is confined to.
6. `.claude/skills/` are the repo's own workflows: `feature-flow` (worktree, change, module doc, merge), `feedback-queue` (my feedback and the open patches for a module, listed and cleared), `sync-architecture` (the docs checked against `main` when a change bypassed feature-flow), `data-migration` (the live database sized against free space, confirmed when large, backed up, the migration proved on the suite and a copy, then run once).

## Documentation

1. `docs/app/CLAUDE.md` describes the platform (`app/`) on `main`: daemon, config, Claude, module contract, UI frame, the shell pages, an index of the module docs, and the platform's own `## Patches`. It is the `app` module doc: `/feedback-queue app` and `/feature-flow` treat it like any other.
2. `docs/<module>/CLAUDE.md` is the one description of a module on `main`: my requirements, `## Built` (tables, routes, hooks, tools, schedules, page, departures from the artboard) and `## Patches`. It changes in the same commit as the module's code and states current functionality only, nothing about history or plans. `/sync-architecture` catches what slipped.
3. `docs/design/` is the imported Claude Design artboard and its runtime; open the html in a browser. It is the source for hues, icons and each page's LEFT and MIDDLE shape.

## Patches

1. **A bug, defect, gap or request seen during any work is recorded before the work continues**, as an entry under `## Patches` in the doc of the module whose code closes it (`docs/app/CLAUDE.md` for the platform). Naming it only in a reply loses it; a reply is not a record. Record it in whatever tree you are working in, so it merges with the branch.
2. **Expand an existing entry rather than duplicating it.** `/feedback-queue <module>` lists the open entries, including those in other docs that name the module's code. When one covers the same cause, add what you saw to it: another path in `Where:`, a sentence in `What happens:`. A related but separate cause gets its own entry.
3. **Shape**: `### <Title>`, then `- Kind: bug | defect | gap | roadmap`, `- Where:`, `- Found: <date>, <what saw it>`, `- Status: open`, then one paragraph each for `What happens:`, `Expected:` and `Fix:`. bug: the code does something it was not meant to do. defect: built as designed, but wrong for me or against the artboard or a tenet. gap: a requirement or artboard element not met. roadmap: something new I asked for. When two fit, the earlier one wins.
4. **Filing is not fixing.** Do not detour to repair what you filed; it waits for feature-flow's step 0. Something inside the scope of the current change is fixed in that change and needs no entry. An entry the change closes is removed in the same commit, and feedback the change does not resolve becomes an entry before its queue is cleared.
