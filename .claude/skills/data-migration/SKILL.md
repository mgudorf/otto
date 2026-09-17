---
name: data-migration
description: Move or reshape rows in the live database: check the space, confirm when it is large, back it up, prove the migration on the suite and on a copy, then run it once against data/otto.db.
disable-model-invocation: yes
---

# Migrate the live data

Runs from the primary checkout (`C:\Users\gudo\Desktop\otto`): the live database `data/otto.db` and the `.venv` exist only there. The migration itself is code on `main` with a test, never a one-off script: a table rename is a line in `app/migrate.py` `RENAMES`, a reshape is `app/modules/<module>/migrate.py` behind `python -m app.modules.<module> migrate`. It is idempotent (a second run adds nothing) and it never drops a source table; dropping is a separate request I make in words. Nothing here changes a row until step 5, and nothing is written at all while the drive cannot hold the backup.

## Do this

1. Size it. `data/otto.db` plus `data/otto.db-wal`, in bytes, and the free space on the drive. The backup needs the database's size again and the migration grows the WAL, so twice the size free is the floor. Free space under the floor means stop and report; no backup, no migration.
2. Confirm when it is large. Over 1 GB: stop before the backup, state the size, the free space, the backup path, what the migration reads and writes, and wait for my yes; a backup or a migration that fails for lack of space is how a database gets corrupted. Under 1 GB: say the size and the free space and go on.
3. Back it up. `Store.backup` (the SQLite backup API, which reads through the WAL while the daemon runs) into `data/backups/otto-<YYYYmmdd-HHMMSS>-pre-<slug>.db`. Open the copy and run `PRAGMA integrity_check`; anything but `ok` means stop and report. Say the path and size.
4. Prove it.
   - `.venv/Scripts/python.exe -m pytest -q`; the migration's own test builds the old shape with rows and checks the new one, run twice. A red suite means stop and report.
   - Dry run on a copy: copy the backup into the scratch directory, run the migration against the copy, print what it added (counts per table, a sample of rows), run it a second time and show it adds nothing. A count that does not match the source rows it should cover means stop and report.
5. Migrate. The daemon keeps running; run outside the nightly window (`[nightly] window` in `config.toml`) so no scheduled task writes to the source tables mid-way. Run the migration command once against the live database. Compare its counts with the dry run; a difference means stop and report.
6. Report: backup path, counts added, what stays (source tables until I say to drop them), and whether a relaunch (`python -m app`) is needed for the new tables to be served.
