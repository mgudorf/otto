"""Every LLM call is the Claude Code CLI in headless mode under the user's own login.

Two entry points:
  run_task     scheduled, read-only, budgeted; the only one a task context can reach
  session_turn interactive; carries the module's write tools; reachable from routes only
`spawn` is the seam tests mock. No API key is ever passed; the CLI's environment is scrubbed.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.store import Store, iso, now, now_iso

READ_BUILTINS = ("Read", "Grep", "Glob", "WebSearch", "WebFetch")
SCRUB_PREFIXES = ("CLAUDECODE", "CLAUDE_CODE_", "ANTHROPIC_")
READ_SERVER = "otto-read"
FULL_SERVER = "otto"

OnEvent = Callable[[dict], Awaitable[None]]


class ClaudeError(Exception):
    pass


class BudgetExceeded(ClaudeError):
    pass


async def spawn(args: list[str], cwd: Path, env: dict[str, str]) -> asyncio.subprocess.Process:
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    return await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd),
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        creationflags=flags,
    )


def clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith(SCRUB_PREFIXES)}


def display_name(tool: str) -> str:
    for prefix in (f"mcp__{READ_SERVER}__", f"mcp__{FULL_SERVER}__"):
        if tool.startswith(prefix):
            return tool[len(prefix):]
    return tool


def events_from(msg: dict) -> list[dict]:
    """Translate one stream-json line into pane events."""
    out: list[dict] = []
    t = msg.get("type")
    if t == "assistant":
        for block in msg.get("message", {}).get("content", []):
            if block.get("type") == "text" and block.get("text", "").strip():
                out.append({"role": "model", "text": block["text"]})
            elif block.get("type") == "tool_use":
                out.append({"role": "tool", "id": block.get("id"), "tool": display_name(block.get("name", "")), "status": "…"})
    elif t == "user":
        for block in msg.get("message", {}).get("content", []) if isinstance(msg.get("message", {}).get("content"), list) else []:
            if block.get("type") == "tool_result":
                out.append({"role": "tool_result", "id": block.get("tool_use_id"), "status": "error" if block.get("is_error") else "done"})
    elif t == "result":
        out.append({
            "role": "result",
            "text": msg.get("result") or "",
            "is_error": bool(msg.get("is_error")),
            "session_id": msg.get("session_id"),
            "subtype": msg.get("subtype"),
        })
    elif t == "system" and msg.get("subtype") == "init":
        out.append({"role": "init", "tools": msg.get("tools", []), "session_id": msg.get("session_id")})
    return out


class ClaudeRunner:
    def __init__(self, config, store: Store, registry, mcp_url: str, spawn_fn=None):
        self.config = config
        self.store = store
        self.registry = registry
        self.mcp_url = mcp_url  # daemon base URL; servers live at /mcp/read and /mcp/full
        self.spawn = spawn_fn   # None: the module-level spawn, looked up at call time so tests can replace it
        self.workspace: Path = config.data.workspace
        self.workspace.mkdir(parents=True, exist_ok=True)

    # ---- budget -------------------------------------------------------------------------
    def budget(self) -> dict:
        local = datetime.now().astimezone()
        day_start = iso(local.replace(hour=0, minute=0, second=0, microsecond=0))
        used = self.store.scalar(
            "SELECT COUNT(*) FROM llm_runs WHERE ts >= ? AND budgeted = 1 AND status IN ('done', 'failed')", (day_start,)
        )
        start, end = self.config.nightly.bounds()
        from app.scheduler import in_window

        return {
            "used": used,
            "max": self.config.nightly.max_sessions,
            "window": self.config.nightly.window,
            "in_window": in_window(local.time(), start, end),
        }

    # ---- argument building --------------------------------------------------------------
    def _args(self, system_prompt: str, server: str, allowed: list[str], extra: list[str]) -> list[str]:
        mcp = {"mcpServers": {server: {"type": "http", "url": f"{self.mcp_url}/mcp/{'read' if server == READ_SERVER else 'full'}"}}}
        args = [
            self.config.claude.binary, "-p",
            "--output-format", "stream-json", "--verbose",
            "--setting-sources", "",
            "--restricted",
            "--strict-mcp-config", "--mcp-config", json.dumps(mcp),
            "--tools", ",".join(READ_BUILTINS),
            "--allowedTools", ",".join(list(READ_BUILTINS) + allowed),
            "--permission-prompts", "none",
            "--system-prompt", system_prompt,
        ]
        if self.config.claude.model != "default":
            args += ["--model", self.config.claude.model]
        return args + extra

    async def _stream(self, args: list[str], prompt: str, timeout: float, on_event: OnEvent | None) -> dict:
        proc = await (self.spawn or spawn)(args, self.workspace, clean_env())
        final: dict = {}
        assert proc.stdin and proc.stdout and proc.stderr
        proc.stdin.write(prompt.encode("utf-8"))
        await proc.stdin.drain()
        proc.stdin.close()
        err_task = asyncio.create_task(proc.stderr.read())

        async def read() -> None:
            async for raw in proc.stdout:
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                for ev in events_from(msg):
                    if ev["role"] == "result":
                        final.update(ev)
                    if on_event:
                        await on_event(ev)

        try:
            await asyncio.wait_for(read(), timeout=timeout)
            await asyncio.wait_for(proc.wait(), timeout=10)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise ClaudeError(f"claude killed after {timeout:.0f}s")
        stderr = (await err_task).decode("utf-8", "replace").strip()
        if not final:
            raise ClaudeError(f"claude exited {proc.returncode} without a result: {stderr[-800:]}")
        if final.get("is_error"):
            raise ClaudeError(f"claude error ({final.get('subtype')}): {final.get('text', '')[:800]}")
        return final

    # ---- scheduled, read-only --------------------------------------------------------------
    async def run_task(self, ctx, prompt: str, tools: tuple[str, ...] = ()) -> str:
        module, task = ctx.job.module, ctx.job.task
        b = self.budget()
        if not b["in_window"]:
            self._record(ctx, "skipped", 0, None)
            raise BudgetExceeded(f"outside nightly window {b['window']}")
        if b["used"] >= b["max"]:
            self._record(ctx, "skipped", 0, None)
            raise BudgetExceeded(f"nightly budget used ({b['used']}/{b['max']})")
        mod = ctx.registry.modules.get(module)
        system = self._system_prompt(mod, scheduled=True)
        allowed = [f"mcp__{READ_SERVER}__{t}" for t in tools]
        args = self._args(system, READ_SERVER, allowed, ["--max-turns", str(self.config.nightly.max_turns), "--no-session-persistence"])
        started = now()
        ctx.log(f"claude run_task tools={list(tools)}")
        try:
            final = await self._stream(args, prompt, self.config.nightly.max_minutes * 60, None)
        except Exception:
            self._record(ctx, "failed", (now() - started).total_seconds() / 60, None)
            raise
        self._record(ctx, "done", (now() - started).total_seconds() / 60, final.get("session_id"))
        return final.get("text", "")

    def _record(self, ctx, status: str, minutes: float, session_id: str | None, budgeted: bool = True) -> None:
        self.store.execute(
            "INSERT INTO llm_runs(ts, module, task, job_id, status, minutes, session_id, budgeted) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (now_iso(), ctx.job.module, ctx.job.task, ctx.job.id, status, minutes, session_id, int(budgeted)),
        )

    async def oneshot(self, ctx, mod, prompt: str, tools: tuple[str, ...] = (), max_turns: int = 2) -> str:
        """User-triggered, read-only, unbudgeted single answer (session close tagging, feedback filing)."""
        allowed = [f"mcp__{READ_SERVER}__{t}" for t in tools]
        args = self._args(self._system_prompt(mod, scheduled=True), READ_SERVER, allowed, ["--max-turns", str(max_turns), "--no-session-persistence"])
        started = now()
        try:
            final = await self._stream(args, prompt, self.config.nightly.max_minutes * 60, None)
        except Exception:
            self._record(ctx, "failed", (now() - started).total_seconds() / 60, None, budgeted=False)
            raise
        self._record(ctx, "done", (now() - started).total_seconds() / 60, final.get("session_id"), budgeted=False)
        return final.get("text", "")

    # ---- interactive -----------------------------------------------------------------------
    async def session_turn(self, mod, session_id: str, is_new: bool, text: str, on_event: OnEvent) -> dict:
        agent = mod.manifest.agent
        tools = list(agent.read_tools) + list(agent.write_tools)
        allowed = [f"mcp__{FULL_SERVER}__{t}" for t in tools]
        extra = ["--session-id", session_id] if is_new else ["--resume", session_id]
        args = self._args(self._system_prompt(mod, scheduled=False), FULL_SERVER, allowed, extra)
        return await self._stream(args, text, self.config.nightly.max_minutes * 60, on_event)

    # ---- prompts ---------------------------------------------------------------------------
    def _system_prompt(self, mod, scheduled: bool) -> str:
        base = (Path(__file__).parent / "modules" / "agent_base.md").read_text("utf-8")
        parts = [base.replace("{module}", mod.manifest.title if mod else "Otto")]
        if mod and mod.prompt:
            parts.append(mod.prompt)
        if scheduled:
            parts.append("This is a scheduled, unattended run. You can only read. Answer in the format the task asks for and nothing else.")
        if mod and mod.context:
            try:
                parts.append("# Current state\n" + mod.context(self.store, self.registry))
            except Exception as e:
                parts.append(f"# Current state\nunavailable: {e!r}")
        return "\n\n".join(p.strip() for p in parts if p and p.strip())
