"""Module contract and registry.

A module is a package under app/modules/<name>/ with:
  __init__.py   MANIFEST
  schema.sql    its own tables (optional)
  tasks.py      async def <task>(ctx) for each declared schedule (optional)
  routes.py     router (APIRouter) plus hooks numbers(store), today(store), item(store, id), context(store, registry)
                (all optional; route handlers must not share these names)
  tools.py      register(read, full, store) adding MCP tools (optional)
  agent.md      system prompt for the module's Claude session (optional)
  setup(config) / async shutdown()   on the package, for modules that own process resources (optional)
A module that fails to import or set up is recorded and skipped; the rest of the app keeps running.
"""

from __future__ import annotations

import importlib
import pkgutil
import traceback
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Awaitable, Callable

UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


@dataclass(frozen=True)
class Schedule:
    task: str
    every: str                  # "60s" | "15m" | "24h" | "7d"
    resource: str | None = None  # jobs on the same resource never overlap
    llm: bool = False            # runs only inside the nightly window and counts against its budget

    @property
    def seconds(self) -> int:
        return int(self.every[:-1]) * UNITS[self.every[-1]]


@dataclass(frozen=True)
class Agent:
    placeholder: str
    skills: tuple[str, ...] = ()       # chips shown in the session pane
    read_tools: tuple[str, ...] = ()   # MCP tool names on the read server
    write_tools: tuple[str, ...] = ()  # MCP tool names on the full server only
    prompt: str = "agent.md"


@dataclass(frozen=True)
class Manifest:
    name: str
    title: str
    hue: str
    icon: str                          # inner SVG markup for a 20x20 viewBox, copied from the artboard
    order: int
    schedules: tuple[Schedule, ...] = ()
    agent: Agent | None = None
    page: bool = True                  # False: tasks only, no rail entry


TaskFn = Callable[[Any], Awaitable[Any]]


@dataclass
class Module:
    manifest: Manifest
    path: Path
    tasks: dict[str, TaskFn]
    router: Any | None
    schema: str | None
    numbers: Callable[[Any], dict | None] | None
    today: Callable[[Any], list[dict]] | None
    item: Callable[[Any, str], dict | None] | None
    context: Callable[[Any, Any], str] | None   # (store, registry) -> text for the agent's system prompt
    register_tools: Callable[..., None] | None
    prompt: str | None
    setup: Callable[[Any], None] | None = None          # (config) at build, for modules holding process resources
    shutdown: Callable[[], Awaitable[None]] | None = None  # awaited when the daemon stops

    @property
    def name(self) -> str:
        return self.manifest.name


def _optional(package: str, name: str) -> ModuleType | None:
    try:
        return importlib.import_module(f"{package}.{name}")
    except ModuleNotFoundError as e:
        if e.name == f"{package}.{name}":
            return None
        raise


class Registry:
    def __init__(self) -> None:
        self.modules: dict[str, Module] = {}
        self.errors: dict[str, str] = {}

    def load(self, package: str = "app.modules") -> None:
        pkg = importlib.import_module(package)
        for info in pkgutil.iter_modules(pkg.__path__):
            if not info.ispkg:
                continue
            try:
                self.modules[info.name] = self._load_one(package, info.name)
            except Exception:
                self.errors[info.name] = traceback.format_exc()

    def _load_one(self, package: str, name: str) -> Module:
        mod = importlib.import_module(f"{package}.{name}")
        manifest: Manifest = mod.MANIFEST
        path = Path(mod.__file__).parent
        tasks_mod = _optional(f"{package}.{name}", "tasks")
        routes_mod = _optional(f"{package}.{name}", "routes")
        tools_mod = _optional(f"{package}.{name}", "tools")
        tasks = {s.task: getattr(tasks_mod, s.task) for s in manifest.schedules}
        schema_file = path / "schema.sql"
        prompt_file = path / manifest.agent.prompt if manifest.agent else None
        if prompt_file and not prompt_file.exists():
            raise FileNotFoundError(f"{name}: agent prompt {prompt_file} missing")
        return Module(
            manifest=manifest,
            path=path,
            tasks=tasks,
            router=getattr(routes_mod, "router", None),
            schema=schema_file.read_text("utf-8") if schema_file.exists() else None,
            numbers=getattr(routes_mod, "numbers", None),
            today=getattr(routes_mod, "today", None),
            item=getattr(routes_mod, "item", None),
            context=getattr(routes_mod, "context", None),
            register_tools=getattr(tools_mod, "register", None),
            prompt=prompt_file.read_text("utf-8") if prompt_file else None,
            setup=getattr(mod, "setup", None),
            shutdown=getattr(mod, "shutdown", None),
        )

    def ordered(self) -> list[Module]:
        return sorted(self.modules.values(), key=lambda m: m.manifest.order)

    def get(self, name: str) -> Module:
        return self.modules[name]
