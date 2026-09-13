"""The daemon: FastAPI app, scheduler, runner and two MCP tool servers on a fixed loopback port.

Runs detached under pythonw. Logs to data/daemon.log. Restart = spawn a replacement, exit;
the replacement waits for the port to free (Windows cannot exec in place).
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import subprocess
import sys
import time
import traceback
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from mcp.server.mcpserver import MCPServer

from app import api, revision
from app.claude import FULL_SERVER, READ_SERVER, ClaudeRunner, clean_env
from app.config import Config, load
from app.modules import Registry
from app.runner import Runner
from app.scheduler import Scheduler
from app.store import Store, now_iso

HERE = Path(__file__).parent
log = logging.getLogger("otto")


class Static(StaticFiles):
    """Every file revalidates against its etag, so a restarted daemon never serves a page from the old revision."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


def build(config: Config, spawn_fn=None) -> FastAPI:
    store = Store(config.data.db)
    store.migrate((HERE / "schema.sql").read_text("utf-8"))
    registry = Registry()
    registry.load()
    for m in registry.ordered():
        if m.schema:
            store.migrate(m.schema)
    for m in registry.ordered():
        if m.setup:
            try:
                m.setup(config)
            except Exception:
                registry.errors[m.name] = traceback.format_exc()
                del registry.modules[m.name]
    with store.tx() as conn:
        conn.execute("DELETE FROM module_errors")
        for name, err in registry.errors.items():
            conn.execute("INSERT INTO module_errors(module, ts, error) VALUES (?, ?, ?)", (name, now_iso(), err))
            log.error("module %s failed to load:\n%s", name, err)
    store.seed_settings({
        "ui.start_page": config.ui.start_page,
        "ui.refresh_seconds": config.ui.refresh_seconds,
        "ui.time_format": config.ui.time_format,
        "ui.page_size": config.ui.page_size,
        "ui.side_max": config.ui.side_max,
        "ui.middle_max": config.ui.middle_max,
        **{f"modules.{m.name}.enabled": True for m in registry.ordered() if m.manifest.page},
        **{f"modules.{m.name}.scheduled": True for m in registry.ordered() if m.manifest.schedules},
    })

    read = MCPServer(READ_SERVER, instructions="Read-only tools over the owner's Otto data.")
    full = MCPServer(FULL_SERVER, instructions="Tools over the owner's Otto data, including writes the owner asked for.")
    for m in registry.ordered():
        if m.register_tools:
            m.register_tools(read, full, store, config)
    read_app = read.streamable_http_app(streamable_http_path="/mcp/read", json_response=True, stateless_http=True)
    full_app = full.streamable_http_app(streamable_http_path="/mcp/full", json_response=True, stateless_http=True)

    claude = ClaudeRunner(config, store, registry, config.url, spawn_fn=spawn_fn)
    runner = Runner(store, config, registry, claude, config.scheduler.max_concurrent)
    scheduler = Scheduler(store, config, registry, runner)

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    st = app.state
    st.config, st.store, st.registry, st.claude, st.runner, st.scheduler = config, store, registry, claude, runner, scheduler
    st.mcp_read, st.mcp_full = read, full
    st.rev = revision.compute(config.root)
    st.started_at = now_iso()
    st.server = None
    st.broadcast = api.Broadcast()
    st.session_busy = set()

    app.include_router(api.router)
    for m in registry.ordered():
        if m.router is not None:
            app.include_router(m.router)
    app.router.routes.extend(read_app.routes)
    app.router.routes.extend(full_app.routes)
    app.mount("/", Static(directory=HERE / "static", html=True), name="static")
    return app


@asynccontextmanager
async def lifespan(app: FastAPI):
    st = app.state
    async with st.mcp_read.session_manager.run(), st.mcp_full.session_manager.run():
        await st.runner.start()
        st.scheduler.sync_tasks()
        tick = asyncio.create_task(st.scheduler.run(), name="scheduler")
        st.store.event("system", "started", f"daemon rev {st.rev} pid {os.getpid()}")
        log.info("daemon rev %s pid %s listening on %s", st.rev, os.getpid(), st.config.url)
        try:
            yield
        finally:
            tick.cancel()
            await asyncio.gather(tick, return_exceptions=True)
            await st.runner.drain(st.config.scheduler.drain_seconds)
            for m in st.registry.ordered():
                if m.shutdown:
                    try:
                        await m.shutdown()
                    except Exception:
                        log.exception("module %s shutdown failed", m.name)
            st.store.event("system", "stopped", f"daemon rev {st.rev}")
            st.store.close()
            log.info("daemon stopped")


def port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def wait_port_free(config: Config, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while not port_free(config.server.host, config.server.port):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.5)
    return True


def spawn_daemon(config: Config) -> subprocess.Popen:
    """Start a detached daemon process (no console, survives the parent)."""
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = str(pythonw if pythonw.exists() else sys.executable)
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(
        [exe, "-m", "app.daemon"],
        cwd=str(config.root),
        creationflags=flags,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        close_fds=True,
        env=clean_env(),
    )


def setup_logging(config: Config) -> None:
    path = config.data.db.parent / "daemon.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> None:
    config = load()
    setup_logging(config)
    if not wait_port_free(config, config.scheduler.drain_seconds + 15):
        log.error("port %s still busy; another daemon is running", config.server.port)
        sys.exit(1)
    app = build(config)
    server = uvicorn.Server(uvicorn.Config(app, host=config.server.host, port=config.server.port, log_config=None, access_log=False))
    app.state.server = server
    server.run()


if __name__ == "__main__":
    main()
