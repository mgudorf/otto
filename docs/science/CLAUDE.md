# Science

1. Interface for scientific experiments via .py or .ipynb; 
2. Uses user-wide python C:\Users\gudo\AppData\Local\Python\pythoncore-3.14-64\python.exe
3. Agent is able to help read/debug notebooks, look at outputs/clean up files, etc; essentially a personalized jupyter + agent interface because I don't like how VSCode handles kernels.  

## Built

| Piece | Current state |
|---|---|
| Files | no tables; `science.root` is the index, walked at request time for `.ipynb` and `.py` (checkpoint and dot directories skipped), newest modification first. A file id is its posix path under the root; anything escaping the root is a 404 |
| Kernels | one per notebook, started on the first run on `science.python` through an explicit KernelSpec (the daemon's venv cannot see the user-wide kernelspec) with the notebook's directory as working directory, held in `state.py` by the `Kernels` registry of `kernels.py` (start, execute, interrupt, restart, shutdown), shut down at daemon exit; a kernel must answer `kernel_info` within 60 s; a run polls liveness every 5 s and fails as `kernel died` or `kernel restarted or shut down`; `Restart` is a shutdown and a fresh start. `science.reap` every 5m on resource `science` shuts down kernels idle past `idle_minutes` and never touches a file |
| Writes | the notebook on disk is the document: `notebook.py` reads it, shapes cells and outputs for the wire, and writes it whole after every edit and every finished run (`.tmp` then replace); no save button, no dirty state |
| Routes | `left` (files by modification day, a hue dot when the kernel is live, name in mono), `blank` (kernel and file counts), `item/{id:path}` (cells with ids, types `code\|markdown\|raw` and shaped outputs, the running cell's in-flight outputs replacing the saved ones; `.py` gives the source), `action/run` `{id, index}` (submitted on `kernel:<id>`, returns the job id; events `{path, cell, index, event started\|output\|done\|error, ...}` stream over `GET /api/science/events`, then the outputs and count are written to the cell by id, so a cell moved during the run still gets them), `action/{interrupt\|restart\|shutdown}` (immediate, never queued, 409 without a kernel), `action/{set_cell\|insert_cell\|delete_cell\|set_cells}` (synchronous read-modify-write of the file, no job; `set_cells` `{id, cells: [{id?, type, source}]}` replaces the list whole, a spec naming an existing id of the same type keeps that cell and its outputs, one `deleted` event per cell that vanished), `action/new` (an empty notebook in the root, name without `/`, `\` or a leading `.`, 409 if it exists, resource `science`). A pre-4.5 file gets positional cell ids on read and is bumped to nbformat 4.5 on its next write |
| Hooks | `numbers` (live kernels), `today` (files modified in the local day), `item`, `context` (root, file count, each kernel's state, idle minutes and runs, the five newest files) |
| Tools | read: `science_files`, `science_notebook` (outputs capped at `tool_output_chars`, images described), `science_cell` (uncapped), `science_kernels`; write: `science_run`, `science_set_cell`. Delete, new, interrupt, restart and shutdown are page actions only |
| Outputs | `stream` and `text/plain` in mono, `image/png` inline, `text/html` as the kernel's own markup, errors as the traceback in `#cf7b7b` |
| Page | LEFT: files by day and a `new` control; MIDDLE: nothing until a file is picked, then `name · python3 · state · ×`, `Run all`, `Interrupt` / `Restart` / `Shut down` while a kernel is live, `+ cell`, `Send to session`, then the cells as JupyterLab's two modes. Command mode: the notebook holds focus, a mousedown on a cell selects it, the selection is a span with a 2px hue bar on the active cell, and keys act on the span: `Enter` edits, `Shift+Enter` / `Ctrl+Enter` / `Alt+Enter` run (and select next, stay, or insert below), `↑ ↓ j k` move with `Shift` extending, `A` `B` insert, `X` `C` `V` cut copy paste, `D,D` delete, `Z` / `Shift+Z` undo redo, `Y` `M` `R` set the type, `1`-`6` a markdown heading, `Shift+M` merge, `Ctrl+Shift+↑/↓` move, `Ctrl+A` select all, `I,I` interrupt, `0,0` restart (chords within 1 s). Edit mode: a click in the source focuses its textarea; `Esc` or `Ctrl+M` returns, the run keys are the same, `Ctrl+Shift+-` splits at the caret, `Ctrl+/` toggles a comment, `Tab` indents four spaces, `↑` on the first line or `↓` on the last crosses into the neighbour; blur saves a changed draft through `set_cell`. Every structural change is one `set_cells` and one undo entry; the active cell alone shows `+ code` / `+ markdown` and a key hint; markdown cells are textareas, not rendered; a `.py` shows its source under the label `module` |
| Departures | the page is a full editor with JupyterLab's command and edit modes where the artboard's notebook is static with name, kernel and `×`; a `.py` shows source where the artboard shows bars; tracebacks use a colour the artboard does not give; scripts are listed, not run |

## Patches

### Command-mode `Shift+-` splits a cell at a stale caret

- Kind: bug
- Where: `app/static/pages/science.js` `commandKey` (`Shift+-` reads `areas[head].selectionStart`)
- Found: 2026-09-12, sync-architecture
- Status: open

What happens: the split binding is offered in command mode as well as edit mode. In command mode the textarea is not focused, so the caret it reads is whatever the editor last had, and 0 for a cell never edited. Selecting such a cell and pressing `Shift+-` inserts an empty cell above and moves the whole source, with its outputs, into the cell below. JupyterLab has no command-mode split.

Expected: `Shift+-` (with `Ctrl` in edit mode) splits only where a caret is visible; in command mode it does nothing.

Fix: drop the `Shift+-` case from `commandKey`, leaving `Ctrl+Shift+-` in `editKey`.

### A cell merge writes `deleted` events for text that survived

- Kind: bug
- Where: `app/modules/science/routes.py` `set_cells` (one `deleted` event per id absent from the new list)
- Found: 2026-09-12, sync-architecture
- Status: open

What happens: `set_cells` treats every id that vanished as a deletion. `Shift+M` on two cells sends a list in which both old ids are gone and one new cell holds the joined source, so Activity shows two `deleted <source>` events though nothing was lost. A split keeps the id on the tail and writes none, so the log is inconsistent between the two.

Expected: the event log records a deletion only when source left the notebook.

Fix: have the page send the merge as `{id: <first id>, ...}` so one cell keeps its identity and only the consumed one is reported, or compare sources rather than ids when deciding what to log.

### Science lists .py scripts but cannot run them

- Kind: gap
- Where: Science requirement 1 (experiments via .py or .ipynb); `app/modules/science/routes.py` `_run`, `app/static/pages/science.js`
- Found: 2026-09-10, sync-architecture
- Status: deferred by the owner

What happens: a `.py` file under the science root appears in LEFT and MIDDLE shows its source under the label `module`, but `action/run` answers 400 `only notebooks run` and the page offers no run control for it. Only `.ipynb` cells execute.

Expected: a script can be run on the user-wide Python from the page, with its output visible, the way a notebook cell is.

Fix: decide the execution model for scripts (a subprocess on `science.python` with stdout streamed over the same events key, or a throwaway kernel); the owner scoped it out of Science version 0 on 2026-09-08.
