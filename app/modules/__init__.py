"""Module contract and registry.

A module is a package under app/modules/<name>/ with:
  __init__.py   MANIFEST
  schema.sql    its own tables, every one named <module>_<table> (optional)
  tasks.py      async def <task>(ctx) for each declared schedule (optional)
  routes.py     router (APIRouter) plus hooks numbers(store), today(store), queue(store), rows(store, limit),
                item(store, id), context(store, registry) (all optional; route handlers must not share these names)
  tools.py      register(read, full, store, config) adding MCP tools (optional)
  agent.md      the module's share of the one agent's system prompt (optional)
  setup(config) / async shutdown()   on the package, for modules that own process resources (optional)
A module that fails to import or set up is recorded and skipped; the rest of the app keeps running.

MANIFEST.facet is the module's immutable tag: the one `fixed` tag every row of it carries, which decides the row's
group on the feed, its hue and its mark. A module without a facet lists no rows and has no place on the brain.

rows(store, limit) is the module's own items as ROWs, newest first; queue(store) is the ones still waiting on the owner.
A ROW:
  id       unique within the module; may be prefixed ("s12", "query:12") or a path
  module   str
  title    str
  when     ISO-8601, or None for an undated row
  fixed    [facet] — exactly one element, the module's facet, never the item's kind
  tags     from app.store.tags_for: the owner's own tags, editable
  type     which renderer the page uses (note, task, email, question, notebook, ledger, table, conversation, …)
  verbs    [[verb, "Label"], …] what the module allows on this row, in the order the owner should see them
  waits    int on a queue row, lower first; None elsewhere
  …extras  per type: snip, unread, dim, done, starred, late, due, right, amount, pct, summary, related, taggable
A kind worth filtering on is a plain tag, not `fixed`. A verb named trash, dismiss, forget, delete, archive, later or
end removes the row: the browser asks before running it, and the row then leaves every list that presents it (queue,
today and the agent's context) while staying in its table, so no task suggests it again.

There is one page and one agent. /api/feed groups every module's rows by facet, /api/brain draws their tags, and
POST /api/verb runs a row's verb through the module's own /api/<module>/action/<verb>.
"""

from __future__ import annotations

import importlib
import pkgutil
import traceback
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Awaitable, Callable

from fastapi import HTTPException

UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def int_id(body: dict, key: str = "id") -> int:
    """The integer id an action body names; a missing or non-integer value is a 400 naming the field, never a 500."""
    value = body.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, str)) or (isinstance(value, str) and not value.strip().isdigit()):
        raise HTTPException(400, f"{key} required")
    return int(value)


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
    skills: tuple[str, ...] = ()       # named in the palette, which sends them to the drawer
    read_tools: tuple[str, ...] = ()   # MCP tool names on the read server
    write_tools: tuple[str, ...] = ()  # MCP tool names on the full server only
    builtins: tuple[str, ...] = ()     # CLI built-ins beyond the read set (Write, Edit) on session turns; tasks never get them
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
    facet: str | None = None           # the module's immutable tag; a module without one lists no rows and has no place on the brain


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
    queue: Callable[[Any], list[dict]] | None    # rows still waiting on the owner, each with waits; Priority lists every one
    item: Callable[[Any, str], dict | None] | None
    context: Callable[[Any, Any], str] | None   # (store, registry) -> text for the agent's system prompt
    register_tools: Callable[..., None] | None
    prompt: str | None
    rows: Callable[[Any, int], list[dict]] | None = None   # (store, limit) -> ROWs newest first; /api/items and the feed
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
            queue=getattr(routes_mod, "queue", None),
            item=getattr(routes_mod, "item", None),
            context=getattr(routes_mod, "context", None),
            rows=getattr(routes_mod, "rows", None),
            register_tools=getattr(tools_mod, "register", None),
            prompt=prompt_file.read_text("utf-8") if prompt_file else None,
            setup=getattr(mod, "setup", None),
            shutdown=getattr(mod, "shutdown", None),
        )

    def ordered(self) -> list[Module]:
        return sorted(self.modules.values(), key=lambda m: m.manifest.order)

    def get(self, name: str) -> Module:
        return self.modules[name]
