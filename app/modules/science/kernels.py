"""Kernels the daemon owns: one per notebook, on the configured interpreter, started on the first run.

Every kernel resolves to one argv on `science.python` through an explicit KernelSpec: the daemon's
venv cannot see the user-wide kernelspec, and jupyter_client would swap a bare `python` for itself.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from queue import Empty
from typing import Any, Callable

from jupyter_client.kernelspec import KernelSpec, KernelSpecManager
from jupyter_client.manager import AsyncKernelManager

from app.store import iso, now

READY_SECONDS = 60     # kernel must answer kernel_info within this
POLL_SECONDS = 5       # between liveness checks while waiting on a running cell

Output = dict[str, Any]          # an nbformat output dict
OnOutput = Callable[[Output], None]


class _OneSpec(KernelSpecManager):
    def __init__(self, python: str):
        super().__init__()
        self.python = python

    def get_kernel_spec(self, kernel_name: str) -> KernelSpec:
        return KernelSpec(argv=[self.python, "-m", "ipykernel_launcher", "-f", "{connection_file}"], display_name="otto", language="python")


@dataclass
class Kernel:
    path: Path
    manager: Any
    client: Any
    started_at: str
    last_activity: datetime
    executions: int = 0
    running: dict | None = None          # {"cell": id, "outputs": [...]} while a cell executes
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def state(self) -> str:
        return "busy" if self.running else "idle"

    def idle_minutes(self) -> float:
        return (now() - self.last_activity).total_seconds() / 60


def _output(msg_type: str, content: dict) -> Output | None:
    if msg_type == "stream":
        return {"output_type": "stream", "name": content.get("name", "stdout"), "text": content.get("text", "")}
    if msg_type in ("execute_result", "display_data"):
        out = {"output_type": msg_type, "data": content.get("data", {}), "metadata": content.get("metadata", {})}
        if msg_type == "execute_result":
            out["execution_count"] = content.get("execution_count")
        return out
    if msg_type == "error":
        return {"output_type": "error", "ename": content.get("ename", ""), "evalue": content.get("evalue", ""), "traceback": content.get("traceback", [])}
    return None


class Kernels:
    def __init__(self, python: str):
        self.python = python
        self._k: dict[str, Kernel] = {}

    @staticmethod
    def _key(path: Path) -> str:
        return str(Path(path).resolve())

    def get(self, path: Path) -> Kernel | None:
        return self._k.get(self._key(path))

    def alive(self) -> list[Kernel]:
        return list(self._k.values())

    async def start(self, path: Path) -> Kernel:
        k = self.get(path)
        if k is not None:
            return k
        km = AsyncKernelManager(kernel_name="otto", kernel_spec_manager=_OneSpec(self.python))
        await km.start_kernel(cwd=str(Path(path).resolve().parent))
        kc = km.client()
        kc.start_channels()
        try:
            await kc.wait_for_ready(timeout=READY_SECONDS)
        except Exception:
            kc.stop_channels()
            await km.shutdown_kernel(now=True)
            raise
        k = Kernel(path=Path(path).resolve(), manager=km, client=kc, started_at=iso(now()), last_activity=now())
        self._k[self._key(path)] = k
        return k

    async def execute(self, path: Path, cell: str, source: str, on_output: OnOutput | None = None) -> tuple[int | None, list[Output]]:
        """Run source on the notebook's kernel, starting it if needed; `cell` is the id the outputs belong to. Returns (execution_count, nbformat outputs)."""
        k = await self.start(path)
        async with k.lock:
            client = k.client
            k.running = {"cell": cell, "outputs": []}
            k.last_activity = now()
            try:
                msg_id = client.execute(source)
                count = None
                while True:
                    try:
                        msg = await client.get_iopub_msg(timeout=POLL_SECONDS)
                    except Empty:
                        if k.client is not client or self._k.get(self._key(path)) is not k:
                            raise RuntimeError("kernel restarted or shut down")
                        if not await k.manager.is_alive():
                            raise RuntimeError("kernel died")
                        continue
                    if msg["parent_header"].get("msg_id") != msg_id:
                        continue
                    t, c = msg["msg_type"], msg["content"]
                    if t == "execute_input":
                        count = c.get("execution_count")
                    elif t == "status" and c.get("execution_state") == "idle":
                        break
                    elif t == "clear_output":
                        k.running["outputs"].clear()
                    else:
                        out = _output(t, c)
                        if out is not None:
                            k.running["outputs"].append(out)
                            if on_output:
                                on_output(out)
                while True:   # the shell reply for this request; drains nothing else
                    reply = await client.get_shell_msg(timeout=READY_SECONDS)
                    if reply["parent_header"].get("msg_id") == msg_id:
                        count = reply["content"].get("execution_count", count)
                        break
                outputs = k.running["outputs"]
            finally:
                k.running = None
                k.last_activity = now()
                if k.client is not client or self._k.get(self._key(path)) is not k:
                    client.stop_channels()   # restart or shutdown happened under us; the old client is ours to close
            k.executions += 1
            return count, outputs

    async def interrupt(self, path: Path) -> bool:
        k = self.get(path)
        if k is None:
            return False
        await k.manager.interrupt_kernel()
        return True

    async def restart(self, path: Path) -> bool:
        """A fresh process on fresh ports: jupyter_client's in-place restart left the new kernel's iopub silent here."""
        if not await self.shutdown(path):
            return False
        await self.start(path)
        return True

    async def shutdown(self, path: Path) -> bool:
        k = self._k.pop(self._key(path), None)
        if k is None:
            return False
        if not k.lock.locked():
            k.client.stop_channels()
        await k.manager.shutdown_kernel(now=True)
        return True

    async def shutdown_all(self) -> None:
        for key in list(self._k):
            await self.shutdown(Path(key))
