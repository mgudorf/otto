# Settings, Data: Export button not built

- Where: artboard Settings > Data (`Back up now`, `Export`, `Vacuum`); `app/static/pages/settings.js`
- Found: 2026-09-07, sync-architecture
- Status: open, needs a decision

What happens: the Data section offers `Back up now` and `Vacuum`. `Export` is absent because nothing defines what it exports.

Expected: either an export with a defined target (a copy of the database, or a JSON dump of chosen tables), or the button dropped from the design.

Fix: decide the target, then one action route and one button.
