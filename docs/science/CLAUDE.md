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
| Files | `science.root` (`data/workspace`, the Claude workspace itself) is the index, walked at request time by `notebook.tree`: every directory and every `.ipynb` or `.py`, directories first, names in order, dot names, `.ipynb_checkpoints` and `__pycache__` skipped; `notebook.scan` flattens it newest first for the hooks and the tools. A file id is its posix path under the root; anything escaping the root is a 404. `notebook.target` validates a new path (every part plain, no leading dot, the suffix added for a file, 409 if it exists) and `notebook.create` makes a folder, an empty script or a one-cell notebook, parents included |
| Tables | `science_schedules` (one row per file id: `every_seconds`, `at` HH:MM or NULL, `next_run`, `last_run`, `last_status` done\|failed, `last_result`), `science_script_runs` (one row per script run: `started_at`, `finished_at`, `status` running\|done\|failed, `exit_code`, `output` with stdout and stderr merged) |
| Kernels | one per notebook, started on the first run on `science.python` through an explicit KernelSpec (the daemon's venv cannot see the user-wide kernelspec) with the notebook's directory as working directory, held in `state.py` by the `Kernels` registry of `kernels.py` (start, execute, interrupt, restart, shutdown), shut down at daemon exit; a kernel must answer `kernel_info` within 60 s; a run polls liveness every 5 s and fails as `kernel died` or `kernel restarted or shut down`; `Restart` is a shutdown and a fresh start. `science.reap` every 5m on resource `science` shuts down kernels idle past `idle_minutes` and never touches a file |
| Scripts | `runs.run_script`: `science.python -u <file>` as a subprocess in the file's directory, stdin closed, stdout and stderr merged and read in 4 KiB chunks, each chunk published as a `stream` output and the whole kept in `science_script_runs`; the process is held in `state.scripts` by file id while it runs (one at a time per file); a non-zero exit fails the run as `exit <code>` |
| Runs | `runs.py` is shared by the routes, the tools and the `due` task: `run_cell` executes one cell and writes its outputs back by id (so a cell moved during the run still gets them), `run_notebook` runs every code cell in order and stops at the first error, `run_file` picks by suffix. A route passes `publish`, so events `{path, cell, event started\|output\|done\|error, ...}` stream over `GET /api/science/events`; a script's events carry `cell: "script"` |
| Schedules | `science.due` every 5m runs every `science_schedules` row whose `next_run` has passed: the next slot is booked first from the planned time (`runs.next_run`, clock time kept, missed slots skipped), the file runs inline through `run_file`, then `last_run`, `last_status` and `last_result` are written and a `ran` or `failed` event logged. `runs.every_seconds` is the manifest grammar (`30m`, `6h`, `1d`); `runs.first_run` anchors to the next local `at` HH:MM or one interval from now |
| Writes | the notebook on disk is the document: `notebook.py` reads it, shapes cells and outputs for the wire, and writes it whole after every edit and every finished run (`.tmp` then replace); no save button, no dirty state |
| Routes | `left` (`{groups, more}`: every file as a ROW under the folder it sits in, the root's group unlabelled), `blank` (kernel and file counts), `item/{id:path}` (that ROW plus `actions`, `next_run` and the body: a notebook's cells with ids, types `code\|markdown\|raw` and shaped outputs, the running cell's in-flight outputs replacing the saved ones; a `.py` gives `source` and `last`, the latest *finished* `science_script_runs` row or null — the row of a run still going carries no output, so it never stands in for the last one), `action/run` `{id, index}` for one cell, or `{id}` alone for the whole file — a notebook top to bottom (job on `kernel:<id>`) or a script as a subprocess (job `science.script` on `script:<id>`, 409 while it runs), `action/interrupt` (a script's process is killed, 409 when not running; a kernel is interrupted), `action/{restart\|shutdown}` (immediate, never queued, 409 without a kernel), `action/{set_cell\|insert_cell\|delete_cell\|set_cells}` (synchronous read-modify-write of the file, no job; `set_cells` `{id, cells: [{id?, type, source}]}` replaces the list whole, a spec naming an existing id of the same type keeps that cell and its outputs, and a vanished cell is logged `deleted` only when its stripped text is no longer anywhere in the notebook, so a merge logs nothing), `action/new` `{path, kind py\|ipynb\|folder}` (resource `science`, returns `{id, kind}`), `action/schedule` `{id, every, at?}` (upsert, returns `next_run`), `action/unschedule` `{id}`. `ACTIONS` names every verb the route serves and the family that runs it; anything else is a 404. A pre-4.5 file gets positional cell ids on read and is bumped to nbformat 4.5 on its next write |
| Rows | a file's ROW is `{id, title}` the posix path under the root, `when` the mtime, `kind` `py`\|`ipynb`, `fixed` `script`\|`notebook`, the owner's `tags` from `app_tags`, `kernel` the kernel's state or null, `running` while a script's process or a busy kernel is on it, `schedule` as `every 1 d at 06:00` or null |
| Hooks | `numbers` (live kernels), `rows` (every file as a ROW, newest first, behind `/api/items` and Home's Recent), `today` (files modified in the local day), `item`, `context` (root, file count, each kernel's state, idle minutes and runs, every schedule's next run and last status, the five newest files) |
| Agent | built-ins `Write` and `Edit` on top of the read set, confined to the workspace, which is the root: scripts and other files are edited directly, notebooks only through the cell tools. Read tools `science_files` (flat, with `kernel` and `running`), `science_notebook` (outputs capped at `tool_output_chars`, images described), `science_cell` (uncapped), `science_kernels`; write tools `science_run` (a cell by index, or a whole script when the id is a `.py`, returning its status, exit code and capped output), `science_set_cell`, `science_insert_cell(id, after, type, source)`, `science_new(path, kind)`. `agent.md` has it end every reply that changed a file or folder with the Ctrl+Shift+R refresh instruction. Interrupt, restart, shutdown and scheduling are page actions only |
| Outputs | `stream` and `text/plain` in mono, `image/png` inline, `text/html` as the kernel's own markup, errors as the traceback in `#cf7b7b`; a script's output is one `stream` block under its source |
| Page | One list of every file, newest first, under the folder it sits in, narrowed by the chips `All`, `Notebooks`, `Scripts` and `Running`. A row is the file's icon, its leaf name and its tags, and on the right `running` in the hue, the kernel's state or its schedule; a running file's row is lit, and `Run` and `Tag` sit on hover; `Run` only queues the job, so the click says the run is queued. `+` in the header asks for a name — `name.py` a script, `name.ipynb` a notebook, anything else a folder, at that path under the root — and opens what it made. The pane is the file: its path, then the kernel (`running` or `kernel idle`), the schedule and a script's last finished run as its date and `exit <code>`, on one line, its tags, then the buttons `item` offers (`Run` / `Run all`, `Interrupt`, `Restart`, `Shut down`, `Schedule` which picks an interval first, `Unschedule`) — `Restart` and `Shut down` carry a `confirm`, so they are red and ask before the kernel's variables go — then the body. A notebook's body is its cells in order, each `[n]` or `[*]` while it runs, code in mono and markdown as prose, outputs beneath, and the cell the keyboard is in an editor (the row below); a script's is the whole file highlighted by the vendored highlight.js 11.11.1 (`vendor/highlight/core.min.js` and `python.min.js`, recoloured into the stylesheet's own token classes) with the run streaming now, or the last run's output, under it. A run's events arrive over `GET /api/science/events` and land in the open cell as they come; the page opens that stream on the file the pane stands on and closes it as soon as that file is no longer the open row, wherever the pane was opened from, so no window without an open file holds a subscriber; the pane is rebuilt on every render and put back where it was being read, so a long notebook holds its place |
| Editor | A notebook is edited where it is read, in the cells themselves, with no save button and nothing held that the daemon has not been told about. The cell the keyboard is in is a box to type in; every other cell is its highlighted source, so only the cell under the caret changes and nothing on the page moves. Command mode is the cell list holding the keyboard, edit mode is one cell's box: clicking the code opens that cell with the caret where the click landed, `↵` opens the active cell, `esc` leaves it, and a cell whose text changed is written through `action/set_cell` when the keyboard leaves it — by `esc`, by a click on another cell, by a click on a button, or by the pane moving to another file. Every structural change writes the whole list through `action/set_cells`, so a cell keeps its id and its outputs unless its text left the notebook: `a` and `b` add a cell above and below, `x` `c` `v` cut, copy and paste, `d,d` deletes, `y` `m` `r` set the type, `1`-`6` make a heading, `Shift+m` merges with the one below, `Ctrl+Shift+-` splits at the caret, `Ctrl+Shift+↑` and `Ctrl+Shift+↓` move, and `z` and `Shift+z` walk back and forward through those changes, keeping any text typed since. `k` `j` and the arrows walk the cells, `Shift` extends to a span that every one of those acts on, and `Ctrl+a` takes every cell. `Ctrl+↵`, `Shift+↵` and `Alt+↵` run the selection, run it and step down, run it and add a cell. Inside a cell, `Tab`, `Shift+Tab` and `Ctrl+/` indent, outdent and comment through the browser's own insert so `Ctrl+z` still undoes them, `↑` and `↓` step to the next cell from the first and last line, and `Ctrl+s` writes now. `i,i` and `0,0` interrupt and restart the kernel. The `+` beside the pane's buttons adds a cell below the active one and opens it. The keys are listed under `?` and each is also a palette action. A key the notebook answers never reaches the shell's own list keys; one it does not — `?`, `/`, `t` — still does, and `esc` in command mode is the shell's, so it closes the pane. The pane is rebuilt on every draw, so the cell holding the keyboard takes it back with its caret after each one |
| Departures | rows group by the folder a file sits in where the artboard groups by day (my request); a `.py` shows its highlighted source where the artboard shows bars, and is read-only, as it was before; the code colours are the stylesheet's four token classes, which the artboard does not give; the notebook takes the keyboard when a cell is clicked or the pane is tabbed into, never when a file is opened, so `j` and `k` keep walking the list; the cell being typed in is the one cell not highlighted |

## Patches

### A script has no line numbers
- Kind: gap
- Where: `app/static/pages/science.js` (`scriptEl`)
- Found: 09-20-2026, restoring the notebook editor
- Status: open

What happens: a `.py` is one highlighted block. The page before the shell was replaced put a line-number gutter beside it, which is how a traceback's `line 41` is found.

Expected: I can count to the line an error names.

Fix: a numbered column left of the source, in the gutter the cell grid already has.

### A schedule cannot pick its first run
- Kind: gap
- Where: `app/static/pages/science.js`, `app/modules/science/routes.py` (`_schedule`)
- Found: 09-20-2026, porting the page onto the new shell
- Status: open

What happens: `Schedule` offers a list of intervals and posts `every` alone, so the first run is one interval from now and every later one keeps that clock time. The route still takes `at` as HH:MM and the old page asked for it.

Expected: a nightly run can be pinned to a time, the way `rl/sweep_spec.py` is pinned to 06:00.

Fix: let the interval list carry a time, or add a second pick of the hour, and post `at` with it.

### A folder with no files in it is invisible
- Kind: defect
- Where: `app/modules/science/routes.py` (`left`), `app/static/pages/science.js`
- Found: 09-20-2026, porting the page onto the new shell
- Status: open

What happens: rows are files and a group is the folder they sit in, so a folder holding nothing has no group and no row. `+` makes one and the page looks unchanged.

Expected: a folder I just made is somewhere I can see it.

Fix: carry empty folders through `left` as groups with no rows, or have `+` make the folder and its first file in one go.

### What a script printed before its pane opened is not shown
- Kind: gap
- Where: `app/modules/science/runs.py` (`run_script`), `app/modules/science/routes.py` (`item`)
- Found: 09-20-2026, fixing the ported page against its review
- Status: open

What happens: a run's chunks are held in memory and written to `science_script_runs` only when the run ends, so while it runs the event stream is the only copy. Open a running script, or reload the page mid-run, and the pane shows the last finished run plus whatever arrives from that moment on; the lines already printed appear only when the run ends.

Expected: opening a running script shows what it has printed so far.

Fix: keep the chunks where a read can reach them — appended to `science_script_runs.output` as they land, or a buffer beside `state.scripts` — and have `item()` hand the page the run in flight in place of the last finished one.
