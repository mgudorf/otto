# Science

1. Interface for scientific experiments via .py or .ipynb; 
2. Uses user-wide python C:\Users\gudo\AppData\Local\Python\pythoncore-3.14-64\python.exe
3. Agent is able to help read/debug notebooks, look at outputs/clean up files, etc; essentially a personalized jupyter + agent interface because I don't like how VSCode handles kernels.  
4. LEFT is the real directory tree under `data/workspace` (the working directory of every Claude session), with `py`, `ipynb` and `folder` creation.
5. The agent can create files, folders, notebooks and scripts and edit `.ipynb` cells and `.py` files; after a change it tells me to refresh the page with Ctrl+Shift+R.
6. Code runs can be scheduled through the daemon.
7. A `.py` is viewed whole, highlighted like an editor, not as cells.

## Built

| Piece | Current state |
|---|---|
| Facet | `science`, title Science, hue `#7FC0C4`. A `.ipynb` is type `notebook`, a `.py` type `script`; a file's id and title are its posix path under the root. Verbs: `Run all` on a notebook, `Run` on a script or `Interrupt` while its process is alive, then `Interrupt`, `Restart kernel` and `Shut down kernel` while a kernel is up, then `Schedule` or `Unschedule`. The row's right-hand cell is its schedule when it has one, else the file's time; the page's stamp is `status`, what the kernel or the process is doing and then the schedule. There is no `queue` hook, so files fill Recent and never Priority |
| Files | `science.root` (`data/workspace`, the Claude workspace itself) is the index, walked at request time by `notebook.tree`: every directory and every `.ipynb` or `.py`, directories first, names in order, dot names, `.ipynb_checkpoints` and `__pycache__` skipped; `notebook.scan` flattens it newest first for the hooks and the tools. Anything escaping the root is a 404. `notebook.target` validates a new path (every part plain, no leading dot, the suffix added for a file, 409 if it exists) and `notebook.create` makes a folder, an empty script or a one-cell notebook, parents included |
| Tables | `science_schedules` (one row per file id: `every_seconds`, `at` HH:MM or NULL, `next_run`, `last_run`, `last_status` done\|failed, `last_result`), `science_script_runs` (one row per script run: `started_at`, `finished_at`, `status` running\|done\|failed, `exit_code`, `output` with stdout and stderr merged) |
| Kernels | one per notebook, started on the first run on `science.python` through an explicit KernelSpec (the daemon's venv cannot see the user-wide kernelspec) with the notebook's directory as working directory, held in `state.py` by the `Kernels` registry of `kernels.py` (start, execute, interrupt, restart, shutdown), shut down at daemon exit; a kernel must answer `kernel_info` within 60 s; a run polls liveness every 5 s and fails as `kernel died` or `kernel restarted or shut down`; `Restart` is a shutdown and a fresh start. `science.reap` every 5m on resource `science` shuts down kernels idle past `idle_minutes` and never touches a file |
| Scripts | `runs.run_script`: `science.python -u <file>` as a subprocess in the file's directory, stdin closed, stdout and stderr merged and read in 4 KiB chunks, each chunk published as a `stream` output and the whole kept in `science_script_runs`; the process is held in `state.scripts` by file id while it runs (one at a time per file); a non-zero exit fails the run as `exit <code>` |
| Runs | `runs.py` is shared by the routes, the tools and the `due` task: `run_cell` executes one cell and writes its outputs back by id (so a cell moved during the run still gets them), `run_notebook` runs every code cell in order and stops at the first error, `run_file` picks by suffix. A route passes `publish`, so events `{path, cell, event started\|output\|done\|error, ...}` stream over `GET /api/science/events`; a script's events carry `cell: "script"` |
| Schedules | `science.due` every 5m runs every `science_schedules` row whose `next_run` has passed: the next slot is booked first from the planned time (`runs.next_run`, clock time kept, missed slots skipped), the file runs inline through `run_file`, then `last_run`, `last_status` and `last_result` are written and a `ran` or `failed` event logged. `runs.every_seconds` is the manifest grammar (`30m`, `6h`, `1d`); `runs.first_run` anchors to the next local `at` HH:MM or one interval from now |
| Writes | the notebook on disk is the document: `notebook.py` reads it, shapes cells and outputs for the wire, and writes it whole after every edit and every finished run (`.tmp` then replace); no save button, no dirty state |
| Routes | `left` (every file as a ROW under the folder it sits in), `blank` (kernel and file counts), `item/{id:path}` (the ROW plus `cells`), `action/run` `{id, index}` for one cell, or `{id}` alone for the whole file — a notebook top to bottom (job on `kernel:<id>`) or a script as a subprocess (job `science.script` on `script:<id>`, 409 while it runs), `action/interrupt` (a script's process is killed, 409 when not running; a kernel is interrupted), `action/{restart\|shutdown}` (immediate, never queued, 409 without a kernel), `action/{set_cell\|insert_cell\|delete_cell\|set_cells}` (synchronous read-modify-write of the file, no job; `set_cells` `{id, cells: [{id?, type, source}]}` replaces the list whole, a spec naming an existing id of the same type keeps that cell and its outputs, and a vanished cell is logged `deleted` only when its stripped text is no longer anywhere in the notebook, so a merge logs nothing), `action/new` `{path, kind py\|ipynb\|folder}` (resource `science`, returns `{id, kind}`), `action/schedule` `{id, every, at?}` (upsert, returns `next_run`), `action/unschedule` `{id}`. `ACTIONS` names every verb the route serves and the family that runs it; anything else is a 404. The four edit verbs and `new` answer the agent's tools now: the page reads a file and never writes one. A pre-4.5 file gets positional cell ids on read and is bumped to nbformat 4.5 on its next write |
| Rows | a file's ROW is `{id, title}` the posix path under the root, `when` the mtime, `fixed` the facet, the owner's `tags` from `app_tags`, `type` from the suffix, `status` (`running`, a kernel's own state, `idle` for a script, `no kernel`, then the schedule), `right` the schedule when there is one, and `verbs`. `item` adds `cells`: a notebook's are its cells in order, each `{g` the `[n]` gutter label, `code`, `out` every output flattened into one block, `err`, `run`}, the running cell's in-flight outputs replacing the saved ones; a script is one cell, the whole file under its newest *finished* run's output, since a run still going has none |
| Hooks | `numbers` (live kernels), `rows` (every file as a ROW, newest first), `today` (files modified in the local day), `item`, `context` (root, file count, each kernel's state, idle minutes and runs, every schedule's next run and last status, the five newest files) |
| Agent | built-ins `Write` and `Edit` on top of the read set, confined to the workspace, which is the root: scripts and other files are edited directly, notebooks only through the cell tools. Read tools `science_files` (flat, with `kernel` and `running`), `science_notebook` (outputs capped at `tool_output_chars`, images described), `science_cell` (uncapped), `science_kernels`; write tools `science_run` (a cell by index, or a whole script when the id is a `.py`, returning its status, exit code and capped output), `science_set_cell`, `science_insert_cell(id, after, type, source)`, `science_new(path, kind)`. `agent.md` has it end every reply that changed a file or folder with the Ctrl+Shift+R refresh instruction |
| Outputs | every output of a cell is flattened into one text block for the page: `stream` and `text/plain` as they are, an error as `<ename>: <evalue>`, `text/html` as the kernel's own markup, an image as `[image]`; the block is drawn in mono under the source, and red when any output was an error. A script's is its run's merged stdout and stderr |
| Departures | files group under the science facet where the artboard and the old page grouped them by folder, so the folder is read from the path on each row; a `.py` is its plain source in mono, neither highlighted nor editable, where requirement 7 asks for an editor's look; the cell keyboard, the `+` that made a file and the kernel counts went with the page, so a file is made with `science_new` and the kernel is read from the row's stamp |

## Patches

### A script has no line numbers
- Kind: gap
- Where: `app/modules/science/routes.py` (`_script_cells`), the `script` renderer
- Found: 09-20-2026, restoring the notebook editor; still true 09-21-2026 in the one page
- Status: open

What happens: a `.py` is one cell holding the whole file, with the gutter label empty. The page before the shell was replaced put a line-number gutter beside it, which is how a traceback's `line 41` is found.

Expected: I can count to the line an error names.

Fix: number the lines in the gutter the cell grid already has, which for a script means the cell carries its line count rather than a single `[n]` label.

### A schedule cannot be given an interval or a first run
- Kind: bug
- Where: `app/modules/science/routes.py` (`_schedule`, `_verbs`), against `app/api.py` `POST /api/verb`
- Found: 09-20-2026, porting the page onto the new shell; widened 09-21-2026, the one-page change
- Status: open

What happens: `Schedule` is a bare `[verb, label]` pair, so pressing it posts `{module, id, verb}` and nothing else. `_schedule` reads `every` from the body, finds nothing, and answers 400 "every must be like 30m, 6h or 1d", so a file cannot be scheduled at all from the page. The route still takes `at` as HH:MM, and nothing has sent that since the old page went, so a nightly run cannot be pinned to a time the way `rl/sweep_spec.py` is pinned to 06:00.

Expected: `Schedule` asks for an interval and, if I want one, an hour, and books it.

Fix: `/api/verb` carries a `value` for a verb that takes one, so the browser needs a pick before it posts and `_schedule` needs to read the interval and the time out of `value`. What the pick looks like is the page's call; the daemon half is reading one field instead of two.

### A folder with no files in it is invisible
- Kind: defect
- Where: `app/modules/science/routes.py` (`rows`, `left`)
- Found: 09-20-2026, porting the page onto the new shell
- Status: open

What happens: rows are files, so a folder holding nothing has no row anywhere. `science_new` makes one and nothing on screen changes.

Expected: a folder I just made is somewhere I can see it.

Fix: carry an empty folder as a row of its own type, or have the making of a folder make its first file in one go.

### What a run prints does not reach the page until the file is opened again
- Kind: gap
- Where: `app/modules/science/runs.py` (`run_script`), `app/modules/science/routes.py` (`item`), `GET /api/science/events`
- Found: 09-20-2026, fixing the ported page against its review; widened 09-21-2026, the one-page change
- Status: open

What happens: a run's chunks are held in memory and written to `science_script_runs` only when the run ends, so while it runs the event stream is the only copy — and nothing subscribes to that stream any more. The page asks `item/{id}` once, when the row is opened, and the refresh keeps what it already fetched, so the cells on screen are the file as it was at that moment: outputs arriving from a run, whether the owner started it or the clock did, appear only when the file is opened afresh.

Expected: pressing Run shows the run happening.

Fix: two halves. The daemon keeps a running script's chunks where a read can reach them — appended to `science_script_runs.output` as they land, or a buffer beside `state.scripts` — and `item()` hands back the run in flight in place of the last finished one. The page subscribes to `/api/science/events` for the open file and re-reads the item when a run ends.
