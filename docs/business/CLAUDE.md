# Business

1. Houses business plans/networking (people, events, etc.)/documents
2. Finds/Tracks items immediately relevant to current pursuits, recommendations based on career improvement, business plans, job openings that are realistic, automated; 

## Built

| Piece | Current state |
|---|---|
| Table | `business_items(kind plan\|person\|event\|document\|lead, text, ref, why, status open\|accepted\|dismissed)`, unique on `(kind, ref)`; `ref` is a URL for a lead, an absolute path for a document and an optional link on the rest |
| Routes | `left` (query as `LIKE` per word over text and ref, chips per kind), `blank` (counts and the open leads), `item/{id}` (an open lead offers `accept` / `dismiss`, which the page posts as `action/lead {id, status}`; a ref gives an `Open` href), `action/{capture\|forget\|lead\|open}`: capture takes `plan`, `person` or `event` only, `forget` refuses a document (delete the file), `open` is `os.startfile` on a document whose file exists |
| Hooks | `numbers` (open leads), `today` (items created in the local day), `item`, `context` (counts, every plan verbatim, open leads, document paths) |
| Tools | read: `business_search`, `business_get`, `business_leads`; write: `business_add`, `business_lead` |
| Schedules | `business.index_documents` every 15m mirrors the top-level files in `data/workspace/business/` as `document` rows, drops rows whose file is gone and returns `Skipped` when nothing changed. `business.scout` every 24h inside the nightly window (`Skipped` with no plans) searches the web against every plan with the last hundred leads listed, expects a JSON array of `{text, url, why}`, and queues up to `leads_per_run` new leads, never repeating a url, cursor `business.scout` |
| Page | LEFT: search, chips, rows by day with the file extension as the leading slot for documents; MIDDLE blank: the capture box and the lead queue; MIDDLE selected: the item, its reason and url, `Accept` / `Dismiss` for a lead, `Open` for a document |
| Departures | chips are the five kinds rather than the artboard's `Accounts, Plans, Documents` (accounts are Finance); `Summarize` and `Share` dropped; the blank state is unspecified in the artboard |

## Patches

None open.
