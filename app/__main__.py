"""python -m app [open|setup|status|daemon]

open    (default) make sure the daemon runs on the current code revision, then open the window
setup   register the Windows Task Scheduler entry that starts the daemon at logon
status  print the running daemon's health
daemon  run the daemon in this process (what the scheduled task runs)
"""

from __future__ import annotations

import json
import subprocess
import sys
import time

import httpx

from app import revision
from app.config import Config, load


def health(config: Config) -> dict | None:
    try:
        r = httpx.get(f"{config.url}/health", timeout=1.5)
        return r.json() if r.status_code == 200 else None
    except httpx.HTTPError:
        return None


def wait(pred, timeout: float):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        v = pred()
        if v:
            return v
        time.sleep(0.5)
    return None


def ensure_daemon(config: Config) -> dict:
    from app.daemon import spawn_daemon

    local = revision.compute(config.root)
    h = health(config)
    if h is None:
        spawn_daemon(config)
        h = wait(lambda: health(config), 30)
        if h is None:
            sys.exit("daemon did not come up; see data/daemon.log")
    if h["rev"] != local:
        httpx.post(f"{config.url}/admin/restart", timeout=5)

        def fresh():
            x = health(config)
            return x if x and x["rev"] == local and not x["draining"] else None

        h = wait(fresh, config.scheduler.drain_seconds + 40)
        if h is None:
            sys.exit("daemon did not restart on the new revision; see data/daemon.log")
    return h


def edge_path() -> str:
    import winreg

    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe") as k:
                return winreg.QueryValue(k, None)
        except OSError:
            continue
    sys.exit("Microsoft Edge not found in App Paths")


def open_window(config: Config) -> None:
    profile = config.root / "app" / ".browser-profile"
    profile.mkdir(exist_ok=True)
    subprocess.Popen(
        [edge_path(), f"--app={config.url}/", f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check"],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
    )


def setup(config: Config) -> None:
    pythonw = str((config.root / ".venv" / "Scripts" / "pythonw.exe").resolve())
    root = str(config.root)
    q = lambda s: "'" + s.replace("'", "''") + "'"
    script = "\n".join([
        f"$action = New-ScheduledTaskAction -Execute {q(pythonw)} -Argument '-m app.daemon' -WorkingDirectory {q(root)}",
        "$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME",
        "$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 "
        "-RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew",
        "Register-ScheduledTask -TaskName 'Otto' -Action $action -Trigger $trigger -Settings $settings "
        "-Description 'Otto daemon (starts at logon)' -Force | Out-Null",
    ])
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], check=True)
    print("Registered scheduled task 'Otto': at logon ->", pythonw, "-m app.daemon")


def main(argv: list[str]) -> None:
    config = load()
    cmd = argv[0] if argv else "open"
    if cmd == "daemon":
        from app.daemon import main as daemon_main

        daemon_main()
    elif cmd == "setup":
        setup(config)
    elif cmd == "status":
        print(json.dumps(health(config), indent=2))
    elif cmd == "open":
        h = ensure_daemon(config)
        print(f"daemon rev {h['rev']} pid {h['pid']} at {config.url}")
        open_window(config)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
