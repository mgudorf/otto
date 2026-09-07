"""One job runner for scheduled and user-triggered work.

Same queue, one lock per resource, a fixed worker count, one `jobs` row per job.
A job that raises marks its own row failed and never touches the others.
"""

from __future__ import annotations

import asyncio
import traceback
from contextlib import asynccontextmanager, contextmanager, nullcontext
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterator

from app.store import Store, now_iso

JobFn = Callable[["JobContext"], Awaitable[Any]]


@dataclass
class Job:
    id: int
    task: str
    module: str
    resource: str | None
    kind: str          # scheduled | action | session
    fn: JobFn
    notify: bool       # write an Activity event on success (failures always do)
    done: asyncio.Future


class JobContext:
    """What a job may touch. Tasks get read clients and one write path: commit()."""

    def __init__(self, job: Job, runner: "Runner"):
        self.job = job
        self.store: Store = runner.store
        self.registry = runner.registry
        self.config = runner.config
        self.claude = runner.claude

    def log(self, message: str) -> None:
        self.store.execute(
            "INSERT INTO job_logs(job_id, ts, message) VALUES (?, ?, ?)", (self.job.id, now_iso(), message)
        )

    @contextmanager
    def commit(self, cursor: tuple[str, str] | None = None) -> Iterator[Any]:
        """Results and the new cursor land in one transaction; there is no separate cursor write."""
        with self.store.tx() as conn:
            yield conn
            if cursor:
                conn.execute(
                    "INSERT INTO cursors(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    cursor,
                )

    def cursor(self, key: str) -> str | None:
        return self.store.cursor(key)

    def event(self, verb: str, text: str, ref: str | None = None) -> None:
        self.store.event(self.job.module, verb, text, self.job.id, ref)

    async def run_task(self, prompt: str, tools: tuple[str, ...] = ()) -> str:
        """A read-only, budgeted Claude run. The only Claude entry point a task can reach."""
        if self.claude is None:
            raise RuntimeError("Claude runner unavailable")
        return await self.claude.run_task(self, prompt, tools)


class Runner:
    def __init__(self, store: Store, config: Any, registry: Any, claude: Any = None, max_concurrent: int = 1):
        self.store = store
        self.config = config
        self.registry = registry
        self.claude = claude
        self.max_concurrent = max_concurrent
        self._queue: asyncio.Queue[Job] = asyncio.Queue()
        self._locks: dict[str, asyncio.Lock] = {}
        self._workers: list[asyncio.Task] = []
        self.running: set[int] = set()
        self.draining = False

    async def start(self) -> None:
        self.store.execute(
            "UPDATE jobs SET status = 'failed', finished_at = ?, error = 'daemon restarted' WHERE status IN ('queued', 'running')",
            (now_iso(),),
        )
        self._workers = [asyncio.create_task(self._worker(), name=f"runner-{i}") for i in range(self.max_concurrent)]

    def submit(self, task: str, module: str, resource: str | None, kind: str, fn: JobFn, notify: bool = False) -> Job:
        if self.draining:
            raise RuntimeError("daemon is restarting")
        cur = self.store.execute(
            "INSERT INTO jobs(task, module, resource, kind, status, queued_at) VALUES (?, ?, ?, ?, 'queued', ?)",
            (task, module, resource, kind, now_iso()),
        )
        job = Job(cur.lastrowid, task, module, resource, kind, fn, notify, asyncio.get_running_loop().create_future())
        self._queue.put_nowait(job)
        return job

    async def run_action(self, task: str, module: str, resource: str | None, fn: JobFn) -> Any:
        """User-triggered work: queued like everything else, awaited by the route. Actions write their own events."""
        job = self.submit(task, module, resource, "action", fn, notify=False)
        return await job.done

    async def _worker(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                await self._run(job)
            finally:
                self._queue.task_done()

    def _lock(self, resource: str | None):
        if resource is None:
            return nullcontext()
        return self._locks.setdefault(resource, asyncio.Lock())

    async def _run(self, job: Job) -> None:
        async with _as_async(self._lock(job.resource)):
            self.running.add(job.id)
            self.store.execute("UPDATE jobs SET status = 'running', started_at = ? WHERE id = ?", (now_iso(), job.id))
            ctx = JobContext(job, self)
            status, result, error = "done", None, None
            try:
                result = await job.fn(ctx)
                if isinstance(result, Skipped):
                    status, result = "skipped", str(result)
            except asyncio.CancelledError:
                status, error = "failed", "cancelled"
                self._finish(job, status, result, error)
                raise
            except Exception:
                status, error = "failed", traceback.format_exc()
            finally:
                self.running.discard(job.id)
            self._finish(job, status, result, error)

    def _finish(self, job: Job, status: str, result: Any, error: str | None) -> None:
        text = None if result is None else str(result)[:4000]
        self.store.execute(
            "UPDATE jobs SET status = ?, finished_at = ?, result = ?, error = ? WHERE id = ?",
            (status, now_iso(), text, error, job.id),
        )
        if job.kind == "scheduled":
            self.store.execute(
                "UPDATE tasks SET last_run = ?, last_status = ?, last_result = ? WHERE name = ?",
                (now_iso(), status, (error or text or "")[:500], job.task),
            )
        if status == "failed":
            self.store.event(job.module, "failed", f"{job.task}: {(error or '').strip().splitlines()[-1][:200]}", job.id)
        elif job.notify:
            self.store.event(job.module, "ran" if job.kind == "scheduled" else "did", f"{job.task}: {text or 'ok'}"[:200], job.id)
        if not job.done.done():
            if status == "failed":
                job.done.set_exception(JobFailed(error or "failed"))
            else:
                job.done.set_result(result)

    async def drain(self, timeout: float) -> None:
        """Stop accepting work, wait for running jobs, then stop the workers."""
        self.draining = True
        deadline = asyncio.get_running_loop().time() + timeout
        while self.running and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.2)
        for w in self._workers:
            w.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []


class JobFailed(Exception):
    pass


class Skipped(str):
    """Return this from a job to record it as skipped with a reason instead of done."""


@asynccontextmanager
async def _as_async(lock):
    if isinstance(lock, asyncio.Lock):
        async with lock:
            yield
    else:
        yield
