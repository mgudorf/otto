---
name: create-roadmap-item
description: Use when a module or feature of Otto is about to be built and needs its implementation plan under docs/roadmap/ before any code is written.
---

# Create a roadmap item

Writes `docs/roadmap/<slug>/PLAN.md`: the plan for one unit of work, built later in its own
git worktree. Assumes `main` is checked out and clean, and that `docs/ARCHITECTURE.md` and
`docs/design/Personal Dashboard App.dc.html` exist.

## Do this

1. Resolve the directory before writing anything. Every plan lives under
   `docs/roadmap/<slug>/PLAN.md` and nowhere else — never `docs/roadmap/PLAN.md`, never a
   bare file at the repo root, and never anywhere under `app/`. `app/` holds source code
   and data only; a plan written there is a defect, not a shortcut.
   - List `docs/roadmap/` and `app/modules/` first. They are the only source of the slug;
     do not invent one from the request's wording. `app/modules/` is read here for the
     canonical spelling of a module name and for nothing else — the skill never writes
     into it.
   - The item is an existing module: `<slug>` is that module's directory name copied
     exactly, spelling and all — `home`, not `homepage`; `web_search` keeps its underscore.
   - A `docs/roadmap/` directory already covers this item under any spelling: write into
     that directory and update the `PLAN.md` in it. Never a suffixed sibling
     (`-v1`, `-v2`, `-new`, `-rev`), never a second plan for one item. A rewrite, a later
     version and a course correction are all edits to the plan that is already there.
   - Nothing matches and the item is not a module: a new kebab-case feature slug
     (`session-tabs`), `mkdir -p docs/roadmap/<slug>`, and say in the reply that the
     directory is new.
   Print the resolved path and confirm it is under `docs/roadmap/<slug>/` before step 2.
2. Read every input before writing a word:
   - `docs/ARCHITECTURE.md`: the item's section, the Daemon requirements and mechanisms, the
     Module contract, Config, Claude, and the UI frame contract with the item's hue and order.
   - `docs/design/Personal Dashboard App.dc.html`: the item's LEFT and MIDDLE shapes, hue, icon.
   - The code the item touches under `app/`, and anything the request names (files, URLs,
     credentials, prior sessions).
   If any of these cannot be read, stop and report exactly what is missing, what you tried,
   and what unblocks it. No plan gets written on a substituted source.
3. Check the machine for every dependency the item needs: packages
   (`.venv/Scripts/python.exe -m pip index versions <pkg>`), binaries, credentials in
   `data/secrets/`, external APIs and their scopes. Record each as present, missing,
   needs the owner, or verify, with exact versions, paths and commands.
4. Write `PLAN.md` with the sections in `reference.md`, in that order, as tables and
   bullets. Three hundred lines is the ceiling; most items need far less.
5. Reply with the Decisions and Manifest tables and any question the owner must answer.
6. Commit the plan on `main` (`Plan <slug>`), and print the worktree command from the
   plan's Worktree section. Implementation never happens on `main`.

## Rules

- One item per plan, covering exactly what was asked. No future generality, no
  "structure to fill in later", no phase that ends with a page and no function.
- Every decision carries a why; every phase ends usable; every knob lands in
  `config.toml` (boot) or the `settings` table (live), named in the plan.
- The Manifest assumes nothing. A dependency is present only after a command on this
  machine said so, in this session.
- Scheduled work reads; user actions write. The plan names which client each path gets
  and how the split is tested, per the Daemon contract.
- Every departure from the artboard is named in the plan with its reason. Nothing is
  invented silently, including hues and icons for modules the artboard lacks.
- Do not write code, stubs or scaffolding while planning; do not create the worktree here.
- One directory per item, forever. If the resolved directory looks wrong — two candidates
  match, or the item spans modules — stop and ask which one, rather than opening a new one.
