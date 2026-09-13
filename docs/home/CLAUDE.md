# Home

1. Shows very high summaries
2. Shows any web search items found via nightly search which are immediately relevant; adds to a queue and creates a record once agreed/disagreed with; i.e. nightly search could return 3 results; at the end of the week there are 21 items to review. 

## Built

`GET /api/home/numbers` (one number per module with a `numbers` hook) and `GET /api/home/left`, which reads every module that is not switched off, page or not, in rail order, and puts a `Review` group per module with a `queue` hook first, every waiting row and no cut (an empty queue yields no group), then each module's `today` rows, five per module with a `+N` link into the module (an empty day still yields the group, shown as `nothing today`). Groups and numbers carry `page`; a header, `+N` or number navigates only when it is true. Search's open findings are the `Review` group today and are decided from Home's inspector. Groups are keyed `label:module`, so one module can yield both. MIDDLE blank state is the number grid; selecting a row opens the owning module's item inspector and posts its verbs as `{id}` to that module's action route (an `href` opens a tab, `confirm` prompts, `forget` clears the selection). The Home agent has no tools; its Current state block carries the same numbers, today rows and `Review: N waiting` lines.

## Nightly Process

Web search to gather data on anything that could potentially help me in my life; obvious ones; items displayed on homepage.

1. Previously scheduled follow ups
2. Investment news/sector news/legislation etc. Should track potential follow-ups and schedule them for the future. 
3. New techniques/algorithms/research relevant to my research, career, etc. 
4. Topics of learning/question sources 

MUST BE CAPPED TO SOME REASONABLE DEGREE; I am using usage associated with CLAUDE MAX account, but do not want to incur any other api charges, nor do I want to use all of my weekly tokens in 2 days. 

### Built

The Search module runs the nightly web search over the owner's topics in the three kinds `money`, `work` and `learn`; `business.scout` searches for leads against the owner's plans. The `[nightly]` budget caps every scheduled LLM run.

## Patches

### Home posts Accept and Dismiss for a Business lead to routes that do not exist

- Kind: bug
- Where: `app/static/pages/home.js` `Middle` (`post(\`/api/${item.module}/action/${a.verb}\`, { id })`); `app/modules/business/routes.py` `ACTIONS` and `item`
- Found: 2026-09-12, sync-architecture
- Status: open

What happens: a Business lead's `item` offers the verbs `accept` and `dismiss`. The Business page knows they are page-local and posts `action/lead {id, status}` instead; Home's generic inspector posts each verb as it is named, so `POST /api/business/action/accept` answers 404 `unknown action accept` and the button does nothing visible. Same family as the entry `Home posts a single id to email actions, which read ids`: Home trusts every module's verbs to be routes that take `{id}`.

Expected: a lead accepted or dismissed from Home changes exactly as it does from the Business page.

Fix: give the item's actions a `body` (or make `accept` and `dismiss` real routes that call `lead`) so the verb Home posts is one the module serves; either way, one place decides what Home may post, and a shared test walks every module's `item` verbs against its `ACTIONS`.

### Home posts a single id to email actions, which read ids

- Kind: bug
- Where: `app/static/pages/home.js` `Middle` (`post(... { id: item.id })`); `app/modules/email/routes.py` `_resolve`
- Found: 2026-09-12, email reader session
- Status: open

What happens: selecting an email row on Home opens the generic inspector with the email item's actions (Archive, Trash, Mark read or unread, Star or Unstar, Open in Gmail). Every verb posts `{id}` for whichever module owns the item, but the email action route resolves its targets from `ids` or `filter` only, so it answers 400 "nothing selected" and the button does nothing visible. Open in Gmail is unaffected because it opens a tab and never posts.

Expected: an email action taken from Home applies to that one message, exactly as the action bar on the Email page does.

Fix: accept `id` in `_resolve` as a one-element `ids` (one line, keeps Home module-agnostic), or have Home post `{ids: [item.id]}` when the item's module is `email`.

### Business leads and Memory suggestions never reach Home's Review group

- Kind: defect
- Where: Home page requirement 2 (a week of items to review); `app/modules/business/routes.py`, `app/modules/memory/routes.py`
- Found: 2026-09-09, sync-architecture
- Status: open, needs a decision

What happens: Home renders a `Review` group for any module with a `queue` hook; Search has one, Business and Memory do not. Both keep rows that wait on a yes or no: `business_items` leads with `status = 'open'` (six on 2026-09-09, eight on 2026-09-12), and `memory_suggestions` with `status = 'open'`. Each is visible only through the module's `today` hook, which covers the local day, and through its own blank state. A lead the nightly scout queued on Monday is off Home by Tuesday and survives only as the `leads` number.

Expected: everything waiting on the owner's decision is on the first page they open, however old it is, which is what the `queue` seam was built for.

Fix: decide whether these two queues belong in `Review`. If they do, each is one `queue(store)` function returning the open rows in the LEFT row shape, as `app/modules/web_search/routes.py` does; the pages, verbs and inspectors already exist.
