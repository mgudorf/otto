# Graph

1. A knowledge graph which picks up any items which were explicitly tagged via the other modules; entirely a read-only/view-only insight layered on top of data generated elsewhere.    
2. Agent serves as natural language interface for graph data. 
3. Agent has ability to query, clean/consolidate/delete nodes/edges from the graph; i.e. it is the graph architect  

## Built

Graph carries no facet and has no `rows` hook: a tag is how items are found, not one of them. It builds and curates the tag map, and the agent is the only thing that changes it.

| Piece | Current state |
|---|---|
| Sources | every tag on a Second Brain item, every tag the owner wrote on any module's row in `app_tags`, and every tag on a session, open or closed (a Chat conversation is tagged after its first turn; its time is `closed_at` or else `opened_at`), lowercased and stripped, so `GRADient` and `gradient` are one node. The rebuild knows which module each tag came from and `graph_nodes` does not keep it. Graph never writes those tables |
| Tables | `graph_nodes(tag, count, items, sessions, last_seen)` and `graph_edges(a, b, kind cooccur\|link, weight, note)`, both replaced whole on each rebuild; the curation overlays `graph_merges`, `graph_pruned` and `graph_links` survive it. A curated link whose end is pruned is dropped at rebuild and a merged end is remapped; merges stay one level deep and a cycle is refused |
| Setup | `setup(config)` renames `graph_nodes.memories`, the column a database from before 2026-09-17 has, to `items`; the next rebuild fills it |
| Routes | `left` (tags by count with a `count` field, search, page), `graph` (every node the query matches with the owner's tags on it, the edges among them, build time and whole-table totals), `item/{tag}` (one tag as a ROW with `fixed` empty). Every moment a route returns is the owner's wall clock; the tables hold UTC. No `action`: nothing here is a verb |
| Hooks | `numbers` (nodes), `item`, `context` (totals, the ten largest tags, merges, prunes, curated link count). No `rows` and no `queue` |
| Tools | read: `graph_nodes`, `graph_neighbors`, `graph_items` (a tag's Second Brain items and sessions, aliases included); write: `graph_link` (both ends must be nodes), `graph_unlink` (curated links only), `graph_merge`, `graph_prune`, `graph_restore`, each in one transaction with the rebuild and each writing an event |
| Schedule | `graph.rebuild` every 15m, plain SQL and no LLM, resource `graph`; the cursor `graph.rebuild` is served as `built_at`. It runs `build.rebuild`, which every write tool also runs inside its own transaction: tags on the same item become a `cooccur` edge weighted by shared items, a curated link an edge of weight 1 |

## Patches

### The brain does not read the graph

- Kind: gap
- Where: `app/static/brain.js` (the tag nodes, built from `ITEMS`), `app/modules/graph/routes.py` (`left`, `graph`, `numbers`), `app/api.py` (the `/api/brain` route that was not built)
- Found: 09-21-2026, the one-page change
- Status: open

What happens: the brain places every tag it draws from the rows the feed is holding, so it sees only the tags on the two hundred newest rows and the queue, and it knows nothing of how tags relate. The map that does know — `graph_nodes` and `graph_edges`, rebuilt every fifteen minutes — reaches the browser through nothing: `/api/graph` and `/api/graph/left` have no caller, `/api/brain` does not exist, and `numbers` is no longer read because the counts cover faceted modules only. A tag whose items have scrolled out of the feed is absent from the brain, an edge is never drawn, and nothing says when the map was last rebuilt.

Expected: the brain is the graph, drawn. Every tag the rebuild knows is a node whether or not its items are in the feed, the edges position it, and a stale map is tellable from a fresh one.

Fix: build `GET /api/brain` over `graph_nodes`, `graph_edges` and `all_tags`, returning each tag with its count, the facets its items belong to and the map's `built_at`, and have `brain.js` take its nodes from that instead of from `ITEMS`. Which facets a tag belongs to is what positions it on the figure, so `graph_nodes` gains a column for the modules the rebuild already reads off its sources.
