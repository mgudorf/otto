# Home

1. Shows very high summaries
2. Shows any web search items found via nightly search which are immediately relevant; adds to a queue and creates a record once agreed/disagreed with; i.e. nightly search could return 3 results; at the end of the week there are 21 items to review. 

## Built

`GET /api/home/numbers` (one number per module with a `numbers` hook), `GET /api/home/left` and `GET /api/home/recent`. Both row routes read every module that is not switched off, page or not, in rail order: `/left` puts a `Review` group per module with a `queue` hook first, every waiting row and no cut (an empty queue yields no group), then each module's `today` rows, five per module; `/recent` asks each module with a `rows` hook for the five rows Recent draws and no more, newest first, leaving out any row that carries no time, because "newest" says nothing about a row that has none and Home invents no date. Every group carries `waiting`, true only for a queue group, and each row reaches the page carrying its group's mark, so one module can yield both and Priority sorts them by the mark rather than by the word `Review`. Every row either route returns is a ROW — `id`, `module`, `title`, `when`, `tags`, `fixed` and whatever else its module put on it — so a module still naming its words `text` and its time `stamp` reads the same here; a waiting row also carries the verbs its own module's `item` offers, where a module answering "no such row" offers none and any other failure is written to the daemon's log rather than passing for a row with nothing to decide. Groups and numbers carry `page`; a number navigates only when it is true. Three modules queue: Newsfeed's open entries and Second Brain's open suggestions, each waiting under `Review` however old it is, and Email's one consent row while its refresh token is near expiry or dead, which names the command to run. Home owns no items, so it has no `rows` hook of its own. The Home agent has no tools; its Current state block carries the same numbers, today rows and `Review: N waiting` lines.

The page has two modes on one segment control, kept across visits. Priority is what waits: the rows whose group is marked `waiting` and nothing that merely arrived today, each with the verbs its module offered on it and the date it is bound to, and never cut. Recent is each module's five newest, which is all the route returns, so the search bar narrows those five and an older item is found on its tag's page instead; a Recent row carries the time it landed, or its date once the day has passed. The search bar's tags and filters narrow both. Either way the rows fall into one card per module in rail order, the module's hue on the card's left border and its icon beside its name. A row opens beside the list in the owning module's own detail shape once that module has answered for it; until then, and where the module cannot answer at all, it opens as its title, date, tags and the buttons its `item` route offers — a primary verb in the hue, one that confirms or removes tinted red and asking through the confirm popup first, an `href` opening a tab, a verb marked `removes` closing the pane because its row is gone. The counts strip sits in the header: each module's icon, its number and its word, and clicking one opens that module.

## Nightly Process

Web search to gather data on anything that could potentially help me in my life; obvious ones; items displayed on homepage.

1. Previously scheduled follow ups
2. Investment news/sector news/legislation etc. Should track potential follow-ups and schedule them for the future. 
3. New techniques/algorithms/research relevant to my research, career, etc. 
4. Topics of learning/question sources 

MUST BE CAPPED TO SOME REASONABLE DEGREE; I am using usage associated with CLAUDE MAX account, but do not want to incur any other api charges, nor do I want to use all of my weekly tokens in 2 days. 

### Built

Newsfeed runs every search the agent recorded, each on its own nights, one budgeted CLI run per search; a follow-up day the run attaches to an entry brings it back into the prompt once the owner has accepted it and the day has come. The `[nightly]` budget caps every scheduled LLM run.

## Patches

### The Gmail consent row cannot be opened

- Kind: bug
- Where: `app/modules/email/routes.py` (`queue`, `item`)
- Found: 09-20-2026, porting Home onto the shell
- Status: open

What happens: Email's queue puts a row with the id `consent` on Home whenever the refresh token is near expiry or dead. It is not a message, so `item(store, "consent")` looks it up in `email_messages`, finds nothing and answers 404. Home shows the row and offers it no verbs, and clicking it puts `no such message` in the header instead of opening anything.

Expected: the row opens like any other, showing the command to run, or it is not presented as something to open.

Fix: have Email's `item` answer the `consent` id itself with the same words the queue row carries and the one verb that applies, the way Second Brain and Newsfeed answer their prefixed ids.

### A row is found by its id alone, so two modules can collide

- Kind: bug
- Where: `app/static/core.js` (`selection`, `loadItem`, `rowEl`'s `sel` class, `S.picked`), seen through `app/static/pages/home.js`
- Found: 09-20-2026, porting Home onto the shell
- Status: open

What happens: Home and the tag page list rows from every module at once, but the shell keys a row by `id` and nothing else. Item ids are only unique inside a module, so Second Brain item 5 and Finance entry 5 are the same row to the shell: opening one can fetch the other's detail, both draw as selected, and a tag meant for one can land on both.

Expected: a row is identified by its module and its id together, so two modules' rows never stand in for each other.

Fix: key the shell's selection and picked set on `module` and `id` — `select` takes both, `selection` and `loadItem` match on both, and `rowEl` writes both onto the element.

### Priority still pays for the rows it does not draw

- Kind: defect
- Where: `app/modules/home/routes.py` (`left_route`), `tests/test_app.py`, `tests/test_education.py`, `tests/test_finance.py`, `tests/test_science.py`
- Found: 09-20-2026, the port review
- Status: open

What happens: `/left` returns each module's `today` rows beside the `Review` groups, and the page draws only the `Review` rows, because what merely arrived today is what Recent already shows. The today rows are still read from every module on each 30-second refresh and sent to a browser that discards them.

Expected: the route returns what waits and nothing else, so Priority costs one queue read per module.

Fix: drop the today groups from `left_route`. They cannot go on their own: `tests/test_app.py` asserts a `Second Brain` group and a `more` count on `/left`, and Education, Finance and Science each assert their today group's count there. The route, those four test files and this doc move in one change, which is the integrator's rather than one module's.

### Graph's tags reach Recent as items

- Kind: defect
- Where: `app/modules/graph/routes.py` (`rows`), `app/modules/__init__.py` (the `rows` contract), `app/modules/home/routes.py` (`recent_route`)
- Found: 09-20-2026, the port review
- Status: open

What happens: Recent reads every module's `rows`, and Graph's rows are tags. Home draws a Graph card of the five most recently seen tag names. Database's table names dropped out once Recent began requiring a time on a row, but a tag carries `last_seen` and still passes.

Expected: Recent is each module's newest items. A tag is how items are found, not one of them.

Fix: the contract gives a module no way to say its rows are structure rather than items, and Home must not carry a list of module names. Add that distinction to the hook — a flag on the row, or a second hook — and Recent reads only item rows while `/api/items` and the tag page keep reading everything.

### Education's due questions are not in what waits

- Kind: gap
- Where: `app/modules/education/routes.py` (`today`, and the `queue` it does not define)
- Found: 09-20-2026, the port review
- Status: open

What happens: Education has no `queue` hook, so the questions it has due reach Home through `today`, which Priority no longer draws. A question waiting to be answered now shows on Home only as the number beside Education in the counts strip.

Expected: a due question waits on the owner exactly as an open suggestion does, so it belongs under Review with the rest.

Fix: Education exposes its due queue as `queue(store)`, the same rows `today` already returns, and Home lists them with no further change.

### Home keeps a second copy of the page registry

- Kind: defect
- Where: `app/static/core.js` (`PAGES`, `registerPages`), `app/static/pages/home.js` (`owners`)
- Found: 09-20-2026, the port review
- Status: open

What happens: to open a row in its own module's pane, Home re-imports `./<module>.js` and keeps the configs in a map of its own, although `app.js` has already handed every one of them to core through `registerPages`. `docs/graph/CLAUDE.md` files the same workaround on Graph.

Expected: a page that needs another page's config asks core for it.

Fix: core exports a reader for its registry; Home and Graph then drop their maps and their dynamic imports. One change in core closes both.

### A waiting row's verbs cost one module call per row on every refresh

- Kind: defect
- Where: `app/modules/home/routes.py` (`_actions`), `app/modules/newsfeed/routes.py`, `app/modules/second_brain/routes.py`, `app/modules/email/routes.py` (each `queue`)
- Found: 09-20-2026, the port review
- Status: open

What happens: a queue row arrives with no verbs on it, so Home asks the owning module's `item` about each one, on every `/left`, which is every 30 seconds while Home is open. Home's own requirement expects a 21-entry review backlog, and Email's `item` reads a message body besides.

Expected: Home reads each queue once and asks nothing further.

Fix: each `queue` puts the row's verbs on the row, the way its `item` already builds them. `_waiting` prefers `r["actions"]` and calls `item` only when they are missing, so nothing in Home changes.
