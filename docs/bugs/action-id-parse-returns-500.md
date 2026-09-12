# A missing or non-numeric `id` on an action is a 500, not a 400

- Where: `app/modules/finance/routes.py` `_check_update` and `_check_id` (`int(body["id"])`); `app/modules/web_search/routes.py` `agree` and `disagree` checks (`int(body.get("id", 0))`)
- Found: 2026-09-12, sync-architecture
- Status: open

What happens: both modules promise that an action is validated before the job is queued, but the id is parsed with a bare `int()` before any check runs. Finance's `update`, `end` and `forget` posted without an `id` raise `KeyError`, and any of these posted with `"id": "abc"` raises `ValueError`, so the route answers 500 with a traceback in the log instead of the 400 the other checks produce. The pages always send integer ids, so only an agent or a hand-made request hits it.

Expected: a malformed id is a 400 naming the field, like every other validation failure in those routes.

Fix: one helper that reads `body.get("id")` and answers `HTTPException(400, "id required")` on a missing or non-integer value, used by both modules' checks.
