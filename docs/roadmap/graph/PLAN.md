# Graph v0 Plan

Status: planning, 2026-09-07.

Graph shows the owner how the things they tagged relate: every tag from Memory and from closed
sessions becomes a node, tags that share an item become an edge, and the agent answers questions
about the picture and tidies it on request. Without it the tags written across Otto stay flat
lists nobody ever reads together.

## Sources

| Source | Governs |
|---|---|
| `docs/ARCHITECTURE.md` Summary, Graph, Claude (sessions, `sessions.tags`) | what feeds the graph; the agent as architect |
| `docs/ARCHITECTURE.md` Daemon requirements, Mechanisms, Module contract, Config, UI frame contract | schedule, write split, files, hue `#b3b06a`, rail order 7 |
| `docs/design/Personal Dashboard App.dc.html` lines 29, 48, 151-157, 208, 254-262, 355, 414, 449-460 | rail icon, shared search, LEFT rows, Home number, MIDDLE ring and highlight, agent chips, header meta, layout formulas |
| `app/modules/memory/` (`schema.sql`, `routes.py`, `tools.py`, `tasks.py`) | `memory_tags` source; the module precedent |
| `app/api.py` `_closer`, `app/schema.sql` `sessions` | session tags as a JSON list, written on `/clear` |
| `app/runner.py`, `app/scheduler.py`, `app/daemon.py` | `ctx.commit`, resource locks, schedule sync, tool registration |
| `app/static/shell.js`, `rows.js`, `pages/memory.js` | page registry, tokens, search and rows |
| `tests/conftest.py`, `tests/test_app.py`, `tests/test_platform.py` | test seams and the read-only checks |

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | Nodes are tags, exactly as written on memories (`memory_tags`) and on closed sessions (`sessions.tags`); nothing is extracted from text | Graph requirement 1: explicitly tagged items only; the artboard says "tags as nodes" |
| 2 | Two edge kinds: `cooccur` (two tags on the same item, weight = shared items) and `link` (curated by the agent) | co-occurrence is the only edge the sources imply; the artboard says "curated links as edges" |
| 3 | `graph_nodes` and `graph_edges` are rebuilt whole, in one transaction, by a scheduled task every 15 minutes and after every curation write | the page and the agent read plain tables; a full rebuild is idempotent and kill-safe by construction; the schedule is what keeps the view current |
| 4 | Curation lives in overlay tables (`graph_merges`, `graph_pruned`, `graph_links`) applied during rebuild; Memory and session rows are never written | Graph requirement 1: view-only over other modules' data; overlays make curation survive every rebuild |
| 5 | Node key is the tag lowercased and stripped | Memory tags are free text, session tags are lowercase; otherwise `SQLite` and `sqlite` are two nodes the agent must merge by hand |
| 6 | Curation reaches the graph only through the agent's write tools; no curation buttons | the artboard's Graph page has no actions; requirement 3 names the agent as the architect |
| 7 | MIDDLE draws exactly the nodes LEFT lists (search and page applied) on a deterministic ring computed by the page | the artboard's own layout; `ui.page_size` already bounds how many nodes are drawn, so no new knob |
| 8 | Selecting a node highlights it and its neighbours; no inspector | the artboard's Graph MIDDLE does this |
| 9 | No `today` or `item` hook; Home shows only the node count | the graph is derived and produces nothing "today"; the artboard Home grid shows `nodes` |

Rejected: computing nodes and edges at query time (every route and tool repeats the join, and merges have no home); a graph database (ARCHITECTURE lists it as not used); the artboard's `extract-entities` chip (writes nodes the owner never tagged); a nightly LLM consolidation task (scheduled agents only read; consolidation is a write).

## Layout

| File | Change |
|---|---|
| `app/modules/graph/__init__.py` | `MANIFEST` |
| `app/modules/graph/schema.sql` | five tables below |
| `app/modules/graph/build.py` | `sources(conn)` and `rebuild(conn)`: the one rebuild used by the task and by every write tool; kept out of `routes.py` so tools do not import routes for it |
| `app/modules/graph/tasks.py` | `async def rebuild(ctx)` |
| `app/modules/graph/routes.py` | `left`, `graph`, hooks `numbers`, `context` |
| `app/modules/graph/tools.py` | read tools on both servers, write tools on `otto` only |
| `app/modules/graph/agent.md` | the architect's job |
| `app/static/pages/graph.js` | `load`, `meta`, `Left`, `Middle` |
| `app/static/shell.js` | one line: `graph` added to `PAGES` |
| `tests/test_graph.py` | tests below |

## Contract

Manifest: `name="graph"`, `title="Graph"`, `hue="#b3b06a"`, icon copied from artboard line 29 (four circles and three strokes), `order=7`, `schedules=(Schedule("rebuild", "15m", resource="graph"),)`, `agent=Agent(placeholder="Curate the graph…", skills=("neighbors", "link", "merge", "prune"), read_tools=("graph_nodes", "graph_neighbors", "graph_items"), write_tools=("graph_link", "graph_unlink", "graph_merge", "graph_prune", "graph_restore"))`.

| Route | Wire shape |
|---|---|
| `GET /api/graph/left?query=&page=` | `{groups: [{label: "tags", count, rows: [{id: tag, module: "graph", text: tag, stamp: last_seen, leading: {dot: null}, count}]}], showing, more}`; rows by count desc then tag; `query` is a substring match on the tag; page size `ui.page_size` |
| `GET /api/graph/graph?query=&page=` | `{nodes: [{tag, count, memories, sessions, last_seen}], edges: [{a, b, kind, weight}], built_at}`; the same node set as `left`; edges only among those nodes |
| `item/{id}`, `action/{verb}` | none in v0: no inspector and no UI writes (decisions 6, 8, 9) |

Hooks: `numbers(store)` returns `{value: node count, label: "nodes"}`; `context(store, registry)` returns node and edge counts, `built_at`, the ten largest nodes with counts, every merge and pruned tag, and the curated link count. No `today`, no `item`.

| MCP tool | Server | Does |
|---|---|---|
| `graph_nodes(query="", limit=50)` | both | nodes matching the substring, largest first |
| `graph_neighbors(tag)` | both | edges touching the tag with kind and weight |
| `graph_items(tag, limit=20)` | both | the memories (id, kind, text) and sessions (id, title, closed_at) carrying the tag |
| `graph_link(a, b, note="")` | `otto` | records a curated link; rebuilds |
| `graph_unlink(a, b)` | `otto` | removes a curated link; rebuilds |
| `graph_merge(alias, into)` | `otto` | folds `alias` into `into`; existing aliases of `alias` are rewritten to `into` so the table stays one level deep; rebuilds |
| `graph_prune(tag)` | `otto` | hides a tag from the graph; rebuilds |
| `graph_restore(tag)` | `otto` | undoes a merge or prune of that tag; rebuilds |

Every write tool validates that the tags exist in the sources, runs the overlay change and the rebuild inside one `store.tx()`, and writes an `events` row (`linked`, `unlinked`, `merged`, `pruned`, `restored`). The store's single guarded connection makes a tool write and a scheduled rebuild safe to interleave; both end in the same table state.

Agent: the Graph architect. It answers questions about how the owner's tags relate using only the graph tools and the Current state block, quoting tags exactly. On the owner's request it links, merges, prunes or restores, reports a change only when the tool returned success, and never touches the memories or sessions behind the tags.

Page: LEFT is the shared search, a `tags N` group header and 32px rows (6px dot, tag, count in mono dim, stamp) rendered by the page rather than the shared `Row`, because the artboard row has a count column. MIDDLE is the artboard's meta line (`<tag> · N linked`, `×` clears) over an 800x560 box: node `i` of `n` sits at angle `2πi/n` and radius `150 + (hash(tag) mod 100)`, x `400 + cos·r·1.1`, y `280 + sin·r·0.8`; diameter `2·(5 + round(count/40))`; label to the right on the left half and to the left on the right half. Colours are the artboard's: selected node filled in the hue, neighbours stroked in the hue, others stroked `rgba(230,231,234,.3)`; dimmed labels `rgba(230,231,234,.25)`; edges in the hue when touching the selection, `.06` alpha when something else is selected, `.14` otherwise. Header meta is `N nodes · M edges`. Selection is `app.select({module: "graph", id: tag, local: node})` so the shell fetches no item.

Departures from the artboard, each with its reason:

- `extract-entities` chip dropped; `neighbors` added (decision 1; the chips name what the agent does).
- Node radius uses the artboard formula; with today's counts every node draws at radius 5. The formula is kept so the picture scales as tags accrue.
- Ring radius comes from a hash of the tag instead of the artboard's index-seeded random, so a node stays put when the list order changes.
- The artboard's placeholder counts (`1,902 nodes · 6,410 edges`) become live counts.

## Data

| Table | Columns | Written by |
|---|---|---|
| `graph_nodes` | `tag` PK, `count`, `memories`, `sessions`, `last_seen` | rebuild only |
| `graph_edges` | `a`, `b`, `kind` (`cooccur` or `link`), `weight`, `note`; PK `(a, b, kind)`; `a < b` | rebuild only |
| `graph_merges` | `alias` PK, `into`, `ts` | `graph_merge`, `graph_restore` |
| `graph_pruned` | `tag` PK, `ts` | `graph_prune`, `graph_restore` |
| `graph_links` | `a`, `b`, `note`, `ts`; PK `(a, b)`; `a < b` | `graph_link`, `graph_unlink` |

Sources, read every rebuild: `memory_tags` joined to `memories.created_at`, and `sessions` with `json_each(tags)` where `closed_at` is set. Rebuild: normalise tags (decision 5), map aliases through `graph_merges`, drop `graph_pruned`, aggregate per tag, count item pairs for `cooccur`, add `graph_links` as `link`, then delete and reinsert both rebuilt tables. Graph depends on the Memory module's tables being present, which they are on `main`.

| Cursor | Value |
|---|---|
| `graph.rebuild` | ISO time of the last completed rebuild, set through `ctx.commit(cursor=...)` by the task; returned as `built_at` |

External clients: none. The write split is internal: the scheduled task receives `ctx.store` and `ctx.commit` and touches only `graph_*` tables; the write tools exist on `otto` only. Proved by `test_write_tools_only_on_full` and `test_sources_untouched` below.

## Phases

| Phase | Builds | Usable result |
|---|---|---|
| 1 | schema, `build.py`, `tasks.rebuild`, routes and hooks, read tools, `agent.md`, page, shell registration | Graph is in the rail; tags from Memory and closed sessions draw with co-occurrence edges; clicking a tag highlights its neighbours; Home shows the node count; the agent answers questions about the graph |
| 2 | the five write tools, their events, rebuild on write | the agent links, merges, prunes and restores on request; curated links draw as edges; merged tags collapse; pruned tags vanish |

## Tests

- `test_rebuild_from_sources`: two memories sharing a tag plus one closed tagged session give the expected counts, `last_seen` and one `cooccur` edge with weight 2; running twice leaves identical rows.
- `test_overlays`: a merge collapses counts into the target, a prune hides a tag, a link appears as a `link` edge, restore brings a pruned tag back.
- `test_write_tools_only_on_full`: register with two recording fakes; write names appear on `full` only.
- `test_sources_untouched`: `memories`, `memory_tags` and `sessions` rows are identical before and after a rebuild and every write tool.
- `test_graph_routes`: through `build(config)` with httpx: `left` and `graph` return the shapes above for the same query, and `/api/home/numbers` carries the node count.
- No LLM touchpoint is added: `rebuild` is plain SQL and sessions are already covered with the fake CLI. The suite stays offline.

## Manifest

Present

| Item | Version / location | Needed for |
|---|---|---|
| Python | 3.14.7, `.venv/Scripts/python.exe` | everything |
| SQLite with JSON functions | 3.50.4 stdlib; `json_each` ran against `data/otto.db` this session | reading `sessions.tags` |
| fastapi, mcp, httpx, pytest | 0.141.1, 2.2.0, 0.28.1, 9.1.1 installed in `.venv` | routes, tools, tests |
| Preact and htm | vendored in `app/static/vendor/` | page |
| Graph hue, icon, order | `#b3b06a`, artboard line 29, order 7 in ARCHITECTURE | manifest |
| Test suite | 16 passed on `main` this session | baseline |
| Source rows in `data/otto.db` | `memory_tags`: 1 (`otto`); `sessions`: 2, none tagged yet | the first rebuild draws one node; the graph fills as tags accrue |

Missing: nothing; no new package or binary.

Needs you: nothing.

Verify

| Check | Command |
|---|---|
| Session tags parse | `.venv/Scripts/python.exe -c "import sqlite3; c=sqlite3.connect('data/otto.db'); print(c.execute('select s.id, j.value from sessions s, json_each(s.tags) j').fetchall())"` |
| Suite green before branching | `.venv/Scripts/python.exe -m pytest -q` |

## Worktree

```
git worktree add ../otto-graph -b graph
```

Work in `../otto-graph`. When `graph` is merged to `main`, run `/sync-architecture`.

## Pending decisions

1. Tags are folded to lowercase (decision 5). If case must stay significant, say so before phase 1 and the key becomes the exact tag.
