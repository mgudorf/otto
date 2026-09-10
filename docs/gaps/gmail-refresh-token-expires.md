# Gmail refresh token expires around 2026-09-12

- Where: Email requirement 1 (Gmail OAuth); `data/secrets/token.json`, `app/modules/email/gmail.py`
- Found: 2026-09-09, sync-architecture
- Status: open, owner action

What happens: the token still carries `refresh_token_expires_in`, 205,388 seconds as of 2026-09-10, because it was issued while the OAuth consent screen for project `central-shift-507603-b1` was in Testing. Around 2026-09-12 the refresh stops working: `email.sync` fails every five minutes, `email.triage` has nothing new to read, and every action route on the Email page fails.

Expected: a refresh token with no expiry, so the mirror and the bulk actions keep working without the owner touching them.

Fix: set the consent screen to Production in the Cloud console for `central-shift-507603-b1`, confirm the redirect `http://localhost:8756/m/email/api/oauth/callback` is still registered on the client, then run `python -m app.modules.email.gmail consent` once. The new `token.json` should have no `refresh_token_expires_in`.
