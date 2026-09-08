"""One SQLite file, WAL mode, one guarded connection. Timestamps are UTC ISO strings."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator


def now() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds")


def now_iso() -> str:
    return iso(now())


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def days_ago_iso(days: int) -> str:
    return iso(now() - timedelta(days=days))


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._ro: sqlite3.Connection | None = None
        self.ro_lock = threading.Lock()

    def read_only(self) -> sqlite3.Connection:
        """A second connection opened mode=ro: SQLite itself refuses every write on it. Guard use with ro_lock."""
        if self._ro is None:
            self._ro = sqlite3.connect(f"file:{self.path.resolve().as_posix()}?mode=ro", uri=True, check_same_thread=False)
            self._ro.execute("PRAGMA busy_timeout=5000")
        return self._ro

    def migrate(self, sql: str) -> None:
        with self._lock:
            self._conn.executescript(sql)

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """One transaction. Everything inside commits together or not at all."""
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            self._conn.execute("COMMIT")

    def execute(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def query(self, sql: str, params: tuple | dict = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def one(self, sql: str, params: tuple | dict = ()) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(sql, params).fetchone()
            return dict(row) if row else None

    def scalar(self, sql: str, params: tuple | dict = ()) -> Any:
        with self._lock:
            row = self._conn.execute(sql, params).fetchone()
            return row[0] if row else None

    # settings: JSON values keyed by dotted name
    def setting(self, key: str) -> Any:
        row = self.one("SELECT value FROM settings WHERE key = ?", (key,))
        return json.loads(row["value"]) if row else None

    def set_setting(self, key: str, value: Any) -> None:
        self.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )

    def seed_settings(self, defaults: dict[str, Any]) -> None:
        for key, value in defaults.items():
            self.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, json.dumps(value)))

    def all_settings(self) -> dict[str, Any]:
        return {r["key"]: json.loads(r["value"]) for r in self.query("SELECT key, value FROM settings")}

    # cursors: per-task sync positions
    def cursor(self, key: str) -> str | None:
        return self.scalar("SELECT value FROM cursors WHERE key = ?", (key,))

    def event(self, module: str, verb: str, text: str, job_id: int | None = None, ref: str | None = None) -> None:
        self.execute(
            "INSERT INTO events(ts, module, verb, text, job_id, ref) VALUES (?, ?, ?, ?, ?, ?)",
            (now_iso(), module, verb, text, job_id, ref),
        )

    def backup(self, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, sqlite3.connect(dest) as out:
            self._conn.backup(out)

    def vacuum(self) -> None:
        with self._lock:
            self._conn.execute("VACUUM")

    def close(self) -> None:
        with self._lock:
            self._conn.close()
        if self._ro is not None:
            with self.ro_lock:
                self._ro.close()
