# Otto

Every command you run by hand. Run them in PowerShell from the repo root, `C:\Users\gudo\Desktop\otto`. Commands that read or write the database only work here, not in a `wt-*` worktree, because `data/otto.db` and `.venv` exist only in this checkout.

## Daily

| Command | What it does |
|---|---|
| `Otto.exe` | Opens Otto: double-click it in the repo root, or pin it to the taskbar or Start. Starts the daemon if it is down, restarts it if the code changed since it started, then opens the window in Chrome under the Otto icon. No terminal and no Python command; a failed launch shows its message in a box. While Otto is open, a pinned `Otto.exe` and the window are two taskbar buttons. |
| `.venv/Scripts/python.exe -m app` | The same open from a terminal, where its messages print instead. |
| `.venv/Scripts/python.exe -m app status` | Prints the daemon's health: code revision, process id, start time, running jobs. `null` means it is not running. |

## Recurring

| When | Command | What it does |
|---|---|---|
| Every 7 days; next by 2026-09-24 20:32 | `.venv/Scripts/python.exe -m app.modules.email.gmail consent` | Renews Gmail access. Opens a Google consent page in the browser and writes `data/secrets/token.json`. Without it, the mail sync fails every five minutes and every Email page action fails. Home shows a notice when the token is about to expire. Setting the Google Cloud consent screen to Production ends the 7-day cycle (see the Email doc's Patches). |

## Once per machine

| Command | What it does |
|---|---|
| `py -3.14 -m venv .venv` then `.venv/Scripts/python.exe -m pip install -r requirements.txt` | Creates the Python environment and installs the pinned packages. |
| `.venv/Scripts/python.exe -m app setup` | Registers the Windows scheduled task `Otto`, which starts the daemon at every logon. Not yet run on this machine; until it is, the daemon runs only after `python -m app`. Check it with `Get-ScheduledTask -TaskName Otto`. |
| `.venv/Scripts/python.exe -m app.modules.email.gmail consent` | The first Gmail authorization. Needs the Google OAuth client file at `data/secrets/google_client.json` first. |

Otto also needs Google Chrome installed and the Claude Code command-line tool logged in to your claude.ai account. Otto has no API key.

## Development

| Command | What it does |
|---|---|
| `.venv/Scripts/python.exe -m pytest -q` | Runs the test suite. It runs offline: Claude and Gmail are mocked. |
| `.venv/Scripts/python.exe -m app.modules.feedback list <module>...` | Prints the feedback you left on those modules' pages that no work has cleared, plus the open `## Patches` entries in their docs. `/feedback-queue` runs this. |
| `.venv/Scripts/python.exe -m app.modules.feedback clear <module>...` | Marks that feedback as handled. Nothing is deleted. `/feature-flow` runs this after a merge. |
| `.venv/Scripts/python.exe -m app daemon` | Runs the daemon in this terminal instead of in the background, so its errors print here. The scheduled task runs the same thing. |
| `.venv/Scripts/python.exe -m app build` | Rebuilds `app/static/otto.ico` and `Otto.exe` from `otto.png` and `app/build.py`. Both are committed, so run it only after changing the logo or the launcher, and commit the result. Needs nothing beyond Windows: PowerShell and the .NET Framework C# compiler. |

Module names for `feedback`: any folder under `app/modules/` that has an `__init__.py`, plus `app`, `activity` and `settings`.


## Where things are

| Path | What |
|---|---|
| `data/daemon.log` | The daemon's log. Look here when Otto does not come up. |
| `data/otto.db` | All of Otto's data, in one SQLite file. |
| `data/backups/` | Database backups: from the Settings page's `Back up now`, and taken automatically before every migration. |
| `config.toml` | Startup settings. After changing it, run `python -m app` again so the daemon restarts on the new values. |
| `docs/<module>/CLAUDE.md` | What each module does, and its open problems under `## Patches`. |
