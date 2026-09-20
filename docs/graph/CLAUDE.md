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
| Routes | `left` (tags by count with a `count` field, search, page), `graph` (every node the query matches with the owner's tags on it, the edges among them, build time and whole-table totals), `item/{tag}` (one tag as a ROW). Every moment a route returns is the owner's wall clock; the tables hold UTC. No `action`, `today` or `queue` |
| Hooks | `numbers` (nodes), `rows` (every tag as a ROW `{id, module, title, when: last_seen, fixed: [], tags, count, items, sessions}`, newest first, so a tag reaches `/api/items` and the cross-module search like anything else; the node is named by its tag, so the title carries it and no identity tag repeats it), `item`, `context` (totals, the ten largest tags, merges, prunes, curated link count) |
| Tools | read: `graph_nodes`, `graph_neighbors`, `graph_items` (a tag's Second Brain items and sessions, aliases included); write: `graph_link` (both ends must be nodes), `graph_unlink` (curated links only), `graph_merge`, `graph_prune`, `graph_restore`, each in one transaction with the rebuild and each writing an event |
| Schedule | `graph.rebuild` every 15m, plain SQL and no LLM, `build.rebuild` shared with every write tool, the cursor `graph.rebuild` served as `built_at`: tags on the same item become a `cooccur` edge weighted by shared items, a curated link an edge of weight 1 |
| Page | The map is the page: every tag a node sized by how much carries it, every co-occurrence and curated link a line, laid out by a deterministic spring so a node keeps its place while the counts hold. A click picks one tag, Ctrl+click adds one and Ctrl+Shift+click removes one, and the pick is written to the search bar's tag tokens, so the map and every module's list share one selection. The pane beside it names the intersection, says how many items carry all of it and in which modules, offers the tags shared with the selection as chips that narrow it further, opens the tag as its own page, hands the selection to the agent, and lists what carries it module by module; any of those items reads in the pane itself, and closing drops that preview first, then the selection. Browse is the same tags as rows with their counts, the modules they reach and their nearest neighbours; they are rows like any other, so `j`, `k`, `Enter`, `x` and `t` reach them and the row the keyboard lands on becomes the selection. The header is the title and the two views, nothing else |
| Departures | `extract-entities` chip dropped and `neighbors` added; a node's hover tooltip dropped, since the node already shows its count beside its name; the pane head's word for itself (Tag, Intersection, Preview) dropped, since the head names the module; an item previewed from another module shows its own title, date, tags and text rather than that module's pane, which the shell does not hand out; Ask sends the question instead of parking it in the composer; the tag and link totals and the rebuild time are off the header, where a count belongs to Home alone |

## Patches

### Ask sends the question instead of offering it

- Kind: defect
- Where: `app/static/pages/graph.js` `ask()`, `app/static/core.js` (the drawer seam)
- Found: 09-20-2026, porting the Graph page
- Status: open

What happens: the Ask button beside the intersection hands `What connects #a and #b?` to the agent and the turn starts at once.

Expected: the artboard put the question in the composer and left the cursor in it, so it could be edited or abandoned before it ran.

Fix: core's seam offers `askAgent` (open and focus, no text) and `sendToAgent` (text, sent); nothing drafts text without sending, and the composer is the drawer's own. Add a third call that sets the draft and focuses, then have `ask()` use it. Decide first which of the two the button should do.

### An item previewed on the map does not read in its own module's shape

- Kind: gap
- Where: `app/static/pages/graph.js` `preview()`, `app/static/core.js` (the `PAGES` registry)
- Found: 09-20-2026, porting the Graph page
- Status: open

What happens: picking one of the items that carries the selection opens it in the pane with its title, date, tags and whatever text the module's `item` route returns, rendered the same way whichever module it came from.

Expected: it reads as that module's own pane does, the way it would on that module's page.

Fix: core holds the page registry privately, so a page cannot reach another page's `detail`. Export a reader for it, or hand `detail` the neighbouring config, and have `preview()` use the item's own module when it has one.

### Nothing on the page says when the map was last rebuilt

- Kind: gap
- Where: `app/static/pages/graph.js`, `app/modules/graph/routes.py` (`graph`, `built_at` and `totals`)
- Found: 09-20-2026, the recheck of the ported page
- Status: open

What happens: the header used to read `127 tags, 340 links, rebuilt 03:29`. That is a count strip outside Home's one sanctioned strip and a word in front of a time, so it is gone, and with it the only place the rebuild moment was shown. `graph` still serves `built_at` and `totals` and nothing reads them. A map the rebuild has not touched for hours now looks exactly like a fresh one.

Expected: the owner can tell a stale map from a current one without opening Activity.

Fix: the header is not the place. Decide where it belongs — a line in the pane under the intersection, the empty map's own text, or nowhere at all if Activity's last-run line is enough — and either use `built_at` there or drop it from the route.
