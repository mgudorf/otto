# Home posts a single id to email actions, which read ids

- Where: `app/static/pages/home.js` `Middle` (`post(... { id: item.id })`); `app/modules/email/routes.py` `_resolve`
- Found: 2026-09-12, email reader session
- Status: open

What happens: selecting an email row on Home opens the generic inspector with the email item's actions (Archive, Trash, Mark read or unread, Star or Unstar, Open in Gmail). Every verb posts `{id}` for whichever module owns the item, but the email action route resolves its targets from `ids` or `filter` only, so it answers 400 "nothing selected" and the button does nothing visible. Open in Gmail is unaffected because it opens a tab and never posts.

Expected: an email action taken from Home applies to that one message, exactly as the action bar on the Email page does.

Fix: accept `id` in `_resolve` as a one-element `ids` (one line, keeps Home module-agnostic), or have Home post `{ids: [item.id]}` when the item's module is `email`.
