# A rotated daemon log is tracked in git

- Where: `.gitignore` (`data/*.log`); `app/daemon.py` `RotatingFileHandler(maxBytes=1_000_000, backupCount=3)`
- Found: 2026-09-10, sync-architecture
- Status: open

What happens: the daemon rotates `data/daemon.log` to `daemon.log.1`, `.2`, `.3`. The ignore pattern `data/*.log` does not match those names, so `git add` picked up `data/daemon.log.1` (4,866 lines) in commit `9593a2c`. Every later rotation leaves a modified tracked file in the working tree and a diff in every commit that adds it.

Expected: no file under `data/` other than `.gitkeep` is tracked; the log and its rotations stay local.

Fix: add `data/*.log.*` to `.gitignore` and run `git rm --cached data/daemon.log.1` once.
