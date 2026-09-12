# Business leads and Memory suggestions never reach Home's Review group

- Where: Home page requirement 2 (a week of items to review); `app/modules/business/routes.py`, `app/modules/memory/routes.py`
- Found: 2026-09-09, sync-architecture
- Status: open, needs a decision

What happens: Home renders a `Review` group for any module with a `queue` hook; Search has one, Business and Memory do not. Both keep rows that wait on a yes or no: `business_items` leads with `status = 'open'` (six on 2026-09-09, eight on 2026-09-12), and `memory_suggestions` with `status = 'open'`. Each is visible only through the module's `today` hook, which covers the local day, and through its own blank state. A lead the nightly scout queued on Monday is off Home by Tuesday and survives only as the `leads` number.

Expected: everything waiting on the owner's decision is on the first page they open, however old it is, which is what the `queue` seam was built for.

Fix: decide whether these two queues belong in `Review`. If they do, each is one `queue(store)` function returning the open rows in the LEFT row shape, as `app/modules/web_search/routes.py` does; the pages, verbs and inspectors already exist.
