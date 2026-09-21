# Home

1. Shows very high summaries
2. Shows any web search items found via nightly search which are immediately relevant; adds to a queue and creates a record once agreed/disagreed with; i.e. nightly search could return 3 results; at the end of the week there are 21 items to review. 

## Built

Home carries no facet, so it lists no rows of its own and takes no place on the brain. It serves the feed every other module fills.

| Piece | Current state |
|---|---|
| Feed | `GET /api/feed?mode=priority\|recent&tags=&q=&limit=` answers `{"items": [ROW, …]}` from every enabled module that carries a facet. `priority` is each module's `queue`, sorted by the `waits` its module set, a row left unranked behind every ranked one, then renumbered 1..n so the rank the feed groups by is the one inside a facet. `recent` is each module's `rows(store, limit)`, newest first, an undated row last. `tags` keeps a row only when it carries every named tag across `fixed` and `tags`; `q` is a case-insensitive substring over the title and the snip. A mode that is neither word is a 400 |
| Numbers | `GET /api/home/numbers`: one entry per enabled faceted module with a `numbers` hook, each carrying the module's facet, hue and icon beside its value and word |
| Hooks | `context` only, which is the one agent's Current state block: every faceted module's number, how many rows it has today and their titles, then `Review: N waiting` and one line per queued row with the module and id that own it. No `rows`, `queue`, `numbers` or `item`: Home owns no items |
| Agent | Home brings no tools. Its `agent.md` is one share of the single Otto prompt, and its `context` is what fills that prompt's Current state block |
| Queues | Five modules queue: Newsfeed's open entries, Second Brain's open suggestions and Education's due questions, each waiting however old it is, Email's one consent row while its refresh token is near expiry or dead, and System's failed tasks |

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

### Nothing reads the counts

- Kind: gap
- Where: `app/modules/home/routes.py` (`numbers_route`), `app/static/core.js` (`loadShell`, `load`)
- Found: 09-21-2026, the one-page change
- Status: open

What happens: `GET /api/home/numbers` still answers, and no file under `app/static/` asks for it. The brand menu was to show what each facet holds; it shows the modules and not their numbers, so every module's `numbers` hook is computed for nobody.

Expected: the one number a module reports is shown somewhere, or the hook goes.

Fix: have the brand menu read `/api/home/numbers` beside the facets it already lists, or drop the route and the `numbers` hook from the contract. The first is the smaller change and keeps the owner's one sanctioned counts strip.

### Home's agent prompt still speaks as one module's agent

- Kind: defect
- Where: `app/modules/home/agent.md`, `app/api.py` (`_otto`)
- Found: 09-21-2026, the one-page change
- Status: open

What happens: `_otto` joins every enabled module's `agent.md` into one prompt. Home's share opens "You are the Home agent", states "You have no tools; everything you know is in that block", and tells the owner to open a module when something needs that module's own agent. Otto holds every module's tools, and there are no modules to open.

Expected: Home's share of the prompt describes the day at a glance and nothing else, so it does not contradict the eight shares beside it.

Fix: cut the sentence that claims no tools and the one that sends the owner to another module, and drop the "You are the Home agent" opening. The same opening sits at the top of every other module's `agent.md`, so the ruling on how the shares are introduced belongs with `_otto` in `docs/app/CLAUDE.md`.

### The Gmail consent row cannot be opened

- Kind: bug
- Where: `app/modules/email/routes.py` (`queue`, `item`)
- Found: 09-20-2026, porting Home onto the shell
- Status: open

What happens: Email's queue puts a row with the id `consent` on the feed whenever the refresh token is near expiry or dead. It is not a message, so `item(store, "consent")` looks it up in `email_messages`, finds nothing and answers 404. The browser swallows that failure, so the row opens as its title alone with no verbs and no way to see the command to run.

Expected: the row opens like any other, showing the command to run, or it is not presented as something to open.

Fix: have Email's `item` answer the `consent` id itself with the same words the queue row carries and the one verb that applies, the way Second Brain and Newsfeed answer their prefixed ids.

### A row is found by its id alone, so two modules can collide

- Kind: bug
- Where: `app/static/core.js` (`itemOf`, `select`, `removeItem`, `pid`, `S.open`, `S.picked`)
- Found: 09-20-2026, porting Home onto the shell
- Status: open

What happens: the feed lists rows from every module at once. `load` keys the merge on `module` and `id` together, but the selection does not: `itemOf` finds the first row whose `id` matches, `pid` is the bare id, and `removeItem` deletes by id. Item ids are only unique inside a module, so Second Brain item 5 and Finance entry 5 are the same row to the browser: opening one can draw the other, both show as selected, and a tag meant for one can land on both.

Expected: a row is identified by its module and its id together, so two modules' rows never stand in for each other.

Fix: key the selection and the picked set the way `load` already keys the merge — `S.open` holds `module/id`, `itemOf` and `pid` match on both, and `select` takes the row rather than its id.
