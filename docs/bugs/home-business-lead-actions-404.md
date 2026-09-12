# Home posts Accept and Dismiss for a Business lead to routes that do not exist

- Where: `app/static/pages/home.js` `Middle` (`post(\`/api/${item.module}/action/${a.verb}\`, { id })`); `app/modules/business/routes.py` `ACTIONS` and `item`
- Found: 2026-09-12, sync-architecture
- Status: open

What happens: a Business lead's `item` offers the verbs `accept` and `dismiss`. The Business page knows they are page-local and posts `action/lead {id, status}` instead; Home's generic inspector posts each verb as it is named, so `POST /api/business/action/accept` answers 404 `unknown action accept` and the button does nothing visible. Same family as `docs/bugs/home-email-actions-post-id.md`: Home trusts every module's verbs to be routes that take `{id}`.

Expected: a lead accepted or dismissed from Home changes exactly as it does from the Business page.

Fix: give the item's actions a `body` (or make `accept` and `dismiss` real routes that call `lead`) so the verb Home posts is one the module serves; either way, one place decides what Home may post, and a shared test walks every module's `item` verbs against its `ACTIONS`.
