# Email and Education page actions fail silently

- Where: `app/static/pages/email.js` `Actions` (`act` and `bulk`, both `await post(...)` unguarded); `app/static/pages/education.js` `act` for `Start` and `Skip` (same unguarded `await post`, while `answer` and `generate` in the same file do catch); `app/static/api.js` `api` throws on a non-2xx
- Found: 2026-09-12, email organization roadmap session; Education added 2026-09-12, sync-architecture
- Status: open

What happens: every action button on the Email page posts through `api.js`, which throws an `Error` when the route answers 4xx or 5xx. Neither `act` (the selected message's Archive, Trash, Mark read, Star) nor `bulk` (the filter-wide Mark read, Archive, Trash) catches it, so the rejection is unhandled: the confirm dialog closes, no error is drawn, no refresh runs, and the row is unchanged. The page looks identical whether the mailbox changed or Gmail refused. Any route failure produces this, and there are several live ones: an expired refresh token (`docs/gaps/gmail-refresh-token-expires.md`), a Gmail quota refusal that outlasts five retries, and a 400 "nothing selected". Unlike `loadItem`, which stores `{error}` and renders it in the reader, the action path has no error surface at all. Education's `Start` and `Skip` behave the same way: a 409 because the tutor already graded or skipped the question is an unhandled rejection with nothing drawn.

Expected: an action that fails says so where it was pressed, in the module hue, and the list does not pretend the mailbox changed.

Fix: catch around both posts and render the message in the action bar, the way `Reader` renders `item.error`. The bar already has a label slot to hold it.
