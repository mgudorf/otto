# Daemon does not start at logon on this machine

- Kind: gap
- Where: Daemon requirement "It starts at logon"; `app/__main__.py` `setup`
- Found: 2026-09-07, sync-architecture
- Status: open, owner action

What happens: `python -m app setup` registers the Task Scheduler entry `Otto`, but it has not been run; the daemon starts only when `python -m app` is run.

Expected: the daemon is running after every logon.

Fix: run `python -m app setup` once from the repo root, then confirm with `Get-ScheduledTask -TaskName Otto`.
