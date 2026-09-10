# Science Plan

Status: planning, 2026-09-08. Version 0.

Science lets the owner open a notebook from Otto, run its cells on the user-wide Python, see the outputs, edit cells, and ask the module's agent to read, debug and run them. Without it, experiments stay in VS Code with the kernel handling the owner dislikes, and the agent has no view of them.

## Sources

| Source | Governs |
|---|---|
| `docs/ARCHITECTURE.md` Science; Daemon requirements, Mechanisms, Config, Claude, Module contract; UI frame contract | what the module does, kernel ownership, read/write split, hue `#6fb3b8`, order 4 |
| `docs/design/Personal Dashboard App.dc.html` rail icon (flask), `sciGroups` LEFT rows, `showNotebook` MIDDLE, `sci` agent entry, Home `kernels` number | LEFT shape (files by day, 6px live dot, mono name, time), MIDDLE shape (name · kernel state · ×, `[n]` cells, code block, stream/table/plot outputs), skills, placeholder, meta `2 kernels` |
| `app/modules/__init__.py`, `app/modules/memory/*`, `app/static/pages/memory.js` | the contract as built; the reference implementation |
| `app/runner.py`, `app/api.py` (`Broadcast`, session events), `app/daemon.py` lifespan | job queue and resource locks, server-sent events, where kernel handles live and die |
| `app/config.py`, `config.toml` | where the module's knobs land |
| `app/claude.py` `READ_BUILTINS`, workspace confinement | why the agent reads notebooks through MCP tools |

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | One kernel per notebook, started on the first run, launched through an explicit `KernelSpec` whose argv is `[science.python, -m, ipykernel_launcher, -f, {connection_file}]` | The module's stated interpreter. The daemon's `.venv` cannot see the user-wide kernelspec, and jupyter_client swaps a bare `python` argv for its own interpreter, which has no ipykernel. Verified today |
| 2 | The `.ipynb` on disk is the document. Every edit and every finished run writes it atomically (write `.tmp`, `os.replace`). No Save button, no dirty state | One source of truth for the page, the agent and the file system; kill-safe by construction |
| 3 | A run is a queued job on resource `kernel:<path>`; the route returns the job id. Outputs stream to the page over server-sent events through the shell's `Broadcast` on key `science`; the page reloads the item when the cell finishes. The finished run writes its outputs to the cell by id, not index. Edits are not queued: each is one synchronous read-modify-write in the route. Interrupt, restart and shutdown are immediate | Runs on one notebook serialize, long cells never hit an HTTP timeout, and the page stays a view of daemon state. Editing while a cell runs is the normal Jupyter rhythm, so an edit cannot wait behind a run, and a run's outputs must land on the cell it ran even after cells moved. Restart has to get past a running cell |
| 4 | No module tables. LEFT walks `science.root` at request time | The file system is the index; a table would be a copy that has to be kept in sync |
| 5 | Kernels live in `app.state.kernels`, die with the daemon (lifespan shuts them down), and a scheduled `reap` shuts down kernels idle past `science.idle_minutes` | Kernels are daemon-owned resources in a process that runs from logon; without a reaper memory only grows |
| 6 | `root` is `data/workspace/science`, created at boot if missing. The agent reads notebooks through the `science_*` tools; the CLI's `Read` and `Grep` builtins reach the same files because `root` sits under `data.workspace` | Owner's decision, 2026-09-08. Tools give shaped cells and capped outputs where raw `.ipynb` JSON is noise; search across notebooks comes free |
| 7 | Agent write tools are `science_run` and `science_set_cell` only. Delete cell, new notebook, interrupt, restart and shutdown are UI actions | Daemon contract: deletion is a user action; debugging needs run and refactor needs set |
| 8 | `.py` files are listed and viewable with the label `module`, not runnable | Artboard shows `module` with no kernel state; scripts are a different execution model, out of version 0 |
| 9 | Outputs rendered: `stream` and `text/plain` in mono, `image/png` as an image, `text/html` as the kernel's own markup, errors as the traceback in `#cf7b7b` | Covers the artboard's three output kinds (text, table, plot); tracebacks need a color the artboard does not give |
| 10 | Every cell carries an id (a pre-4.5 file gets positional ids on read, kept on its next write). Structural edits are one `set_cells` verb that replaces the cell list; a cell naming an existing id of the same type keeps its outputs. The page implements JupyterLab's model on top: command mode on the notebook element, edit mode in a cell's editor, the Lab key bindings, split/merge/move/type/paste/undo/redo as list transforms | Owner's decision, 2026-09-10: the page must navigate like Lab. One verb keeps the server a document store and makes undo a snapshot; ids keep outputs with their cell through every transform |

Rejected: nbclient (batch-executes a whole notebook, no interactive kernel); a `science_files` table plus scan task; the CLI's `Edit`/`NotebookEdit` builtins for the agent; running `.py` files; keeping kernels across daemon restarts.

## Layout

- `app/modules/science/__init__.py`: `MANIFEST`
- `app/modules/science/kernels.py`: `Kernel` (manager, client, state, last activity) and `Kernels` registry: `get`, `start`, `execute`, `interrupt`, `restart`, `shutdown`, `shutdown_all`. `Kernels.execute` is the seam tests fake
- `app/modules/science/notebook.py`: read and atomic write of `.ipynb` via nbformat, cell and output shaping for the wire
- `app/modules/science/routes.py`: router and hooks
- `app/modules/science/tasks.py`: `reap`
- `app/modules/science/tools.py`: read tools on both servers, write tools on `otto`
- `app/modules/science/agent.md`
- `app/static/pages/science.js`
- `app/static/shell.js`: add `science` to `PAGES`
- `app/config.py`, `config.toml`: `[science]` section
- `app/daemon.py`: create `Kernels` on `app.state`; `shutdown_all` in the lifespan `finally`
- `requirements.txt`: pin `jupyter_client==8.10.0`, `nbformat==5.11.1`
- `tests/test_science.py`
- No `schema.sql`: the module has no tables.

## Contract

Manifest: `name="science"`, `title="Science"`, `hue="#6fb3b8"`, `icon='<path d="M8 3v6l-4.5 7.5A1 1 0 0 0 4.4 18h11.2a1 1 0 0 0 .9-1.5L12 9V3"></path><path d="M6.5 3h7"></path><path d="M6 13h8"></path>'`, `order=4`, `schedules=(Schedule(task="reap", every="5m", resource="science"),)`, `agent=Agent(placeholder="Ask about the notebook…", skills=("inspect-cell", "run", "explain-output", "refactor"), read_tools=("science_files", "science_notebook", "science_cell", "science_kernels"), write_tools=("science_run", "science_set_cell"))`.

Config `[science]` (boot): `python` (interpreter path), `root` = `data/workspace/science` (directory of `.ipynb` and `.py` files, walked recursively; gitignored with the workspace, so the daemon creates it at boot), `idle_minutes` (reap threshold), `tool_output_chars` (per-output cap in agent tool replies). No live settings.

| Route | Wire shape |
|---|---|
| `GET /api/science/left` | `{groups: [{label: "05 Sep", count, rows: [{id: <relative posix path>, module: "science", text: <file name>, stamp: <mtime iso>, leading: {dot: hue or null}}]}], showing: "<n> files"}`; grouped by modification day, newest first; dot when a kernel is alive |
| `GET /api/science/blank` | `{kernels: <alive count>, files: <count>}`; drives the header meta `2 kernels · 14 files` |
| `GET /api/science/item/{id:path}` | `{id, module: "science", text: <name>, kind: "ipynb" or "py", created_at: <mtime>, kernel: {state: idle or busy, executions, started_at} or null, cells: [{id, index, type: code, markdown or raw, source, execution_count, running, outputs: [{kind: stream/text/html/image/error, text?, html?, png?, ename?, traceback?}]}], source: <for .py>, actions: []}` |
| `POST /api/science/action/run` `{id, index}` | `{job}`; starts the kernel if absent; queued on `kernel:<id>` |
| `POST /api/science/action/interrupt`, `restart`, `shutdown` `{id}` | `{ok}`; immediate, never queued; 409 without a kernel |
| `POST /api/science/action/set_cell` `{id, index, source}`, `insert_cell` `{id, after, type}`, `delete_cell` `{id, index}` | `{id}`; direct atomic writes |
| `POST /api/science/action/set_cells` `{id, cells: [{id?, type, source}]}` | `{id, cells}`; replaces the cell list in one write, keeping outputs where an id and type match; a `deleted` event per cell that vanished |
| `POST /api/science/action/new` `{name}` | `{id}`; creates `<name>.ipynb` in `root` with one empty code cell; resource `science` |
| `GET /api/science/events` | server-sent events `{path, cell, index, event: started/output/done/error, output?, execution_count?, ts}` |

Hooks: `numbers` gives `{value: <alive kernels>, label: "kernels"}` (artboard's Home tile). `today` lists files modified on the local day as LEFT rows. `item` as above; the shell's generic Inspector shows `text` for a row picked from Home, and the module's own MIDDLE renders the cells. `context` reports `root`, file count, each alive kernel with its notebook, state and idle minutes, and the five most recently modified files.

Agent: the lab assistant for the owner's notebooks. It lists files, reads any notebook's cells and outputs, explains an output or a traceback in plain terms, runs a cell when the owner asks, and rewrites a cell's source when asked to refactor, keeping the owner's variable names. It never deletes anything and never runs a cell the owner did not point at.

Departures from the artboard: every cell is an editor and the page has Lab's command and edit modes (the artboard is static): one click in the source edits, the gutter or margin selects, a hue bar marks the active cell, insert chips sit at its foot; a `.py` MIDDLE shows the source (the artboard shows placeholder bars); the notebook header carries `Run all`, `Interrupt`, `Restart`, `Shut down` and `+ cell` actions and a `Send to session` button (the artboard header has name, kernel and `×` only); tracebacks use `#cf7b7b`. Departures from Lab: markdown is not rendered; undo of a delete brings the cell back without its outputs; the gutter never runs a cell.

## Data

Tables: none. Cursors: none (nothing syncs; the reaper reads kernel activity from memory).

| Client | Who receives it | Test |
|---|---|---|
| `Kernels.get`, `Notebook.read` (read) | GET routes, `science_*` read tools on both MCP servers, `reap` | `test_science_read_tools_never_write` |
| `Kernels.execute`, `Notebook.write` (write) | `action/*` routes and `science_run`, `science_set_cell` on `otto` only | same test, plus an AST check that `tasks.py` names neither `execute` nor `write` |

`reap` is housekeeping like `system.prune_sessions`: it shuts down the daemon's own idle kernel processes and never touches a file in `root`.

## Phases

| Phase | Builds | Usable result |
|---|---|---|
| 1 Browse and run | manifest, `[science]` config, `kernels.py`, `notebook.py`, `left`/`blank`/`item`, `run`/`interrupt`/`restart`/`shutdown`, events stream, `reap`, lifespan shutdown, `numbers`/`today`/`item` hooks, page with LEFT list and MIDDLE notebook view, per-cell `Run` and header actions, outputs written back to the file | Open any notebook under `root`, run cells on the user-wide Python, watch outputs arrive, find them saved in the file |
| 2 Edit | every cell an editor, command and edit modes with the Lab keys (`Enter`/`Esc`, `Shift`/`Ctrl`/`Alt+Enter`, `A` `B`, `D,D`, `X` `C` `V`, `Z`/`Shift+Z`, `Y` `M` `R` `1`-`6`, `Shift+M`, `Ctrl+Shift+-`, `Ctrl+Shift+↑↓`, `Shift+↑↓`, `Ctrl+A`, `I,I`, `0,0`, `Tab`, `Ctrl+/`), blur saves, `set_cell`/`set_cells`/`insert_cell`/`delete_cell`/`new`, `.py` source view | Write and run a notebook end to end without VS Code, with Lab's muscle memory |
| 3 Agent | `tools.py`, `agent.md`, `context` hook, `Send to session` prefill with the selected file and cell | Ask about the open notebook; the agent inspects, explains, runs and rewrites cells on request |

## Tests

- `test_science_notebook_roundtrip`: a notebook in a tmp `root`; `left` lists it; `item` returns its cells; `set_cell` and `insert_cell` write a valid notebook (`nbformat.validate`) and no `.tmp` remains.
- `test_science_run_streams_and_saves`: `Kernels.execute` faked to yield one stream and one `execute_result`; `run` queues on `kernel:<path>`, events reach a subscriber, the file holds the outputs and execution count afterwards.
- `test_science_read_tools_never_write`: `science_run` and `science_set_cell` are absent from the read server; `tasks.py` never names `execute` or `write`.
- `test_science_reap`: a fake kernel idle past `idle_minutes` is shut down, a busy one is not.
- No real kernel in the suite; Claude stays mocked at `app.claude.spawn`.

## Manifest

Present

| Item | Version / location | Needed for |
|---|---|---|
| Python | 3.14.7 at `C:\Users\gudo\AppData\Local\Python\pythoncore-3.14-64\python.exe` | kernel interpreter (`science.python`) |
| ipykernel | 7.3.0 in the user-wide Python | kernel process |
| jupyter_client | 8.10.0 in `.venv` (installed, not in `requirements.txt`) | kernel manager and client |
| nbformat | 5.11.1 in `.venv` (installed, not in `requirements.txt`) | read, validate, write `.ipynb` |
| pyzmq, tornado | 27.2.0, 6.5.8 in `.venv`, pulled by jupyter_client | kernel transport; tornado supplies the selector thread pyzmq needs on the Windows Proactor loop (warning only, works) |
| Kernel start, execute, interrupt, shutdown from `.venv` with an explicit `KernelSpec` | verified 2026-09-07; the kernel reported the user-wide interpreter | decision 1 |

Missing

| Package | Version | Needed for | Install target |
|---|---|---|---|
| none | | | pin `jupyter_client==8.10.0` and `nbformat==5.11.1` in `requirements.txt` |

Needs you

| Item | How |
|---|---|
| Scientific packages in the user-wide Python (numpy, pandas, matplotlib are not installed today) | `C:\Users\gudo\AppData\Local\Python\pythoncore-3.14-64\python.exe -m pip install <pkg>` as experiments need them; the module does not manage them |

Verify

| Check | Command |
|---|---|
| Kernel launches on the user-wide Python | `.venv/Scripts/python.exe -c "import asyncio; from jupyter_client.manager import AsyncKernelManager; from jupyter_client.kernelspec import KernelSpec, KernelSpecManager; PY=r'C:\Users\gudo\AppData\Local\Python\pythoncore-3.14-64\python.exe'; S=type('S',(KernelSpecManager,),{'get_kernel_spec':lambda self,n: KernelSpec(argv=[PY,'-m','ipykernel_launcher','-f','{connection_file}'],display_name='otto',language='python')}); km=AsyncKernelManager(kernel_name='otto',kernel_spec_manager=S()); asyncio.run(km.start_kernel()); print('ok'); asyncio.run(km.shutdown_kernel(now=True))"` |
| Pins match the machine | `.venv/Scripts/python.exe -m pip index versions jupyter_client` and `... nbformat` |
| `root` is created at boot | `ls data/workspace/science` after `python -m app` |

## Worktree

```
git worktree add ../otto-science -b science
```

Work there. When `science` is merged to `main`, run `/sync-architecture`.

## Pending decisions

None. `science.root` was decided on 2026-09-08 (decision 6).
