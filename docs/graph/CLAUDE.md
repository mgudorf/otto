# Graph

1. A knowledge graph which picks up any items which were explicitly tagged via the other modules; entirely a read-only/view-only insight layered on top of data generated elsewhere.    
2. Agent serves as natural language interface for graph data. 
3. Agent has ability to query, clean/consolidate/delete nodes/edges from the graph; i.e. it is the graph architect  

## Built

| Piece | Current state |
|---|---|
| Sources | every tag on a Second Brain item and on any tagged session, open or closed (a pane's session is tagged when it closes, a Chat conversation after its first turn; its time is `closed_at` or else `opened_at`), lowercased and stripped, so `GRADient` and `gradient` are one node. Graph never writes those tables |
| Tables | `graph_nodes(tag, count, items, sessions, last_seen)` and `graph_edges(a, b, kind cooccur\|link, weight, note)`, both replaced whole on each rebuild; the curation overlays `graph_merges`, `graph_pruned` and `graph_links` survive it. A curated link whose end is pruned is dropped at rebuild and a merged end is remapped; merges stay one level deep and a cycle is refused |
| Setup | `setup(config)` renames `graph_nodes.memories`, the column a database from before 2026-09-17 has, to `items`; the next rebuild fills it |
| Routes | `left` (tags by count with a `count` field, search, page), `graph` (the same query and page: the visible nodes, the edges among them, build time and whole-table totals). No `item`, `action`, `today` or `queue`; selecting a tag is local to the page |
| Hooks | `numbers` (nodes), `context` (totals, the ten largest tags, merges, prunes, curated link count) |
| Tools | read: `graph_nodes`, `graph_neighbors`, `graph_items` (a tag's Second Brain items and sessions, aliases included); write: `graph_link` (both ends must be nodes), `graph_unlink` (curated links only), `graph_merge`, `graph_prune`, `graph_restore`, each in one transaction with the rebuild and each writing an event |
| Schedule | `graph.rebuild` every 15m, plain SQL and no LLM, `build.rebuild` shared with every write tool, the cursor `graph.rebuild` served as `built_at`: tags on the same item become a `cooccur` edge weighted by shared items, a curated link an edge of weight 1 |
| Page | LEFT: search and boxed tag rows with their counts, no header; a neighbour of the selected tag reads in the hue; MIDDLE: a ring of nodes with their edges, selecting a tag lights its neighbours and says how many are linked |
| Departures | `extract-entities` chip dropped and `neighbors` added; ring radius comes from a hash of the tag so a node stays put when the list reorders; counts are live |

## Patches

None open.
