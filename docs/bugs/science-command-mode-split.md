# Command-mode `Shift+-` splits a cell at a stale caret

- Where: `app/static/pages/science.js` `commandKey` (`Shift+-` reads `areas[head].selectionStart`)
- Found: 2026-09-12, sync-architecture
- Status: open

What happens: the split binding is offered in command mode as well as edit mode. In command mode the textarea is not focused, so the caret it reads is whatever the editor last had, and 0 for a cell never edited. Selecting such a cell and pressing `Shift+-` inserts an empty cell above and moves the whole source, with its outputs, into the cell below. JupyterLab has no command-mode split.

Expected: `Shift+-` (with `Ctrl` in edit mode) splits only where a caret is visible; in command mode it does nothing.

Fix: drop the `Shift+-` case from `commandKey`, leaving `Ctrl+Shift+-` in `editKey`.
