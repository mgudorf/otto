import asyncio
import dataclasses
from pathlib import Path

import pytest

import app.claude as claude_mod
from app.config import ROOT, Data, load
from app.store import Store

SCHEMA = (ROOT / "app" / "schema.sql").read_text("utf-8")


@pytest.fixture(autouse=True)
def no_real_claude(monkeypatch):
    """Every LLM touchpoint is mocked at the spawn seam; a real invocation raises."""

    async def forbidden(*a, **k):
        raise RuntimeError("real claude invocation inside tests")

    monkeypatch.setattr(claude_mod, "spawn", forbidden)


@pytest.fixture(autouse=True)
def no_real_gmail(monkeypatch):
    """Gmail is mocked at the transport seam; a real call raises."""
    import httpx

    import app.modules.email.gmail as gmail_mod

    def forbidden(request):
        raise RuntimeError(f"real gmail call inside tests: {request.url}")

    monkeypatch.setattr(gmail_mod, "TRANSPORT", httpx.MockTransport(forbidden))


@pytest.fixture
def config(tmp_path: Path):
    base = load(ROOT)
    return dataclasses.replace(base, data=Data(db=tmp_path / "otto.db", workspace=tmp_path / "workspace"))


@pytest.fixture
def store(config):
    s = Store(config.data.db)
    s.migrate(SCHEMA)
    yield s
    s.close()


def run(coro):
    return asyncio.run(coro)


class FakeStream:
    def __init__(self, lines: list[str]):
        self._buf = b"".join(l.encode() + b"\n" for l in lines)

    async def read(self, n: int = -1):
        take = len(self._buf) if n < 0 else n
        out, self._buf = self._buf[:take], self._buf[take:]
        return out


class FakeStdin:
    def __init__(self):
        self.data = b""

    def write(self, b):
        self.data += b

    async def drain(self):
        pass

    def close(self):
        pass


class FakeProc:
    """Stands in for the claude CLI: emits canned stream-json lines, and stderr lines when given."""

    def __init__(self, lines: list[str], stderr: list[str] = ()):
        self.stdin = FakeStdin()
        self.stdout = FakeStream(lines)
        self.stderr = FakeStream(list(stderr))
        self.returncode = 0

    async def wait(self):
        return 0

    def kill(self):
        self.returncode = -9


def fake_spawn(lines: list[str], calls: list | None = None, stderr: list[str] = ()):
    async def spawn(args, cwd, env):
        if calls is not None:
            calls.append({"args": args, "cwd": cwd, "env": env})
        return FakeProc(list(lines), stderr)

    return spawn
