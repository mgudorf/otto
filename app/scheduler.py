"""The daemon owns the clock. Manifest schedules become rows in `tasks`; this loop submits the due ones.

LLM tasks only become due inside the nightly window, and go one at a time `stagger_minutes` apart so two
nightly runs never overlap; everything else runs on its interval. A module the owner switched off on
Settings holds every one of its tasks back; the rows stay due and go the tick after it is switched on.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta

from app.runner import Runner
from app.store import Store, iso, now, now_iso


def in_window(t: time, start: time, end: time) -> bool:
    if start <= end:
        return start <= t < end
    return t >= start or t < end  # window crosses midnight


def next_window_start(local_now: datetime, start: time) -> datetime:
    candidate = local_now.replace(hour=start.hour, minute=start.minute, second=0, microsecond=0)
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate


class Scheduler:
    def __init__(self, store: Store, config, registry, runner: Runner):
        self.store = store
        self.config = config
        self.registry = registry
        self.runner = runner

    def sync_tasks(self) -> None:
        """Manifests are the only source of scheduled tasks; rows for vanished tasks are removed."""
        declared = {}
        for module in self.registry.ordered():
            for s in module.manifest.schedules:
                declared[f"{module.name}.{s.task}"] = (module.name, s)
        with self.store.tx() as conn:
            for name, (mod, s) in declared.items():
                conn.execute(
                    """INSERT INTO app_tasks(name, module, interval_seconds, resource, llm, enabled, next_run)
                       VALUES (?, ?, ?, ?, ?, 1, ?)
                       ON CONFLICT(name) DO UPDATE SET module = excluded.module, interval_seconds = excluded.interval_seconds,
                         resource = excluded.resource, llm = excluded.llm""",
                    (name, mod, s.seconds, s.resource, int(s.llm), self._first_run(s.llm)),
                )
            existing = [r[0] for r in conn.execute("SELECT name FROM app_tasks").fetchall()]
            for name in existing:
                if name not in declared:
                    conn.execute("DELETE FROM app_tasks WHERE name = ?", (name,))

    def _first_run(self, llm: bool) -> str:
        if not llm:
            return now_iso()
        local = datetime.now().astimezone()
        start, end = self.config.nightly.bounds()
        if in_window(local.time(), start, end):
            return now_iso()
        return iso(next_window_start(local, start))

    def _next_run(self, llm: bool, interval_seconds: int) -> str:
        if llm:
            start, _ = self.config.nightly.bounds()
            return iso(next_window_start(datetime.now().astimezone(), start))
        return iso(now() + timedelta(seconds=interval_seconds))

    def _staggered(self) -> bool:
        """True while a nightly run went in the last `stagger_minutes`: the next one waits its turn."""
        cutoff = iso(now() - timedelta(minutes=self.config.nightly.stagger_minutes))
        return bool(self.store.scalar(
            "SELECT 1 FROM app_jobs j JOIN app_tasks t ON t.name = j.task WHERE t.llm = 1 AND j.kind = 'scheduled' AND j.queued_at >= ? LIMIT 1",
            (cutoff,),
        ))

    def runs(self, module: str) -> bool:
        """The owner's per-module switch on Settings. Nothing but the owner ever writes it."""
        return self.store.setting(f"modules.{module}.scheduled") is not False

    def tick(self) -> list[str]:
        """Submit every enabled task whose next_run has passed. Returns the names submitted."""
        due = self.store.query(
            "SELECT * FROM app_tasks WHERE enabled = 1 AND next_run IS NOT NULL AND next_run <= ? ORDER BY next_run, name", (now_iso(),)
        )
        submitted = []
        for row in due:
            if not self.runs(row["module"]):
                continue                     # switched off: the row stays due rather than skipping a turn
            if row["llm"] and self._staggered():
                continue                     # one nightly run per gap; the rest stay due for a later tick
            self.store.execute(
                "UPDATE app_tasks SET next_run = ? WHERE name = ?", (self._next_run(bool(row["llm"]), row["interval_seconds"]), row["name"])
            )
            module = self.registry.modules.get(row["module"])
            task_name = row["name"].split(".", 1)[1]
            fn = module.tasks.get(task_name) if module else None
            if fn is None:
                self.store.execute(
                    "UPDATE app_tasks SET last_run = ?, last_status = 'failed', last_result = 'module not loaded' WHERE name = ?",
                    (now_iso(), row["name"]),
                )
                continue
            self.runner.submit(row["name"], row["module"], row["resource"], "scheduled", fn, notify=bool(row["llm"]))
            submitted.append(row["name"])
        return submitted

    async def run(self) -> None:
        while True:
            await asyncio.sleep(self.config.scheduler.tick_seconds)
            try:
                if not self.runner.draining:
                    self.tick()
            except Exception as e:  # the clock never dies because one tick failed
                self.store.event("system", "failed", f"scheduler tick: {e!r}"[:200])

    def set_enabled(self, name: str, enabled: bool) -> None:
        row = self.store.one("SELECT llm FROM app_tasks WHERE name = ?", (name,))
        if row is None:
            raise KeyError(name)
        self.store.execute(
            "UPDATE app_tasks SET enabled = ?, next_run = COALESCE(next_run, ?) WHERE name = ?",
            (int(enabled), self._first_run(bool(row["llm"])), name),
        )
