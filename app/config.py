"""config.toml -> typed Config. Every key is required; a missing key fails loudly at boot."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Server:
    host: str
    port: int


@dataclass(frozen=True)
class Scheduler:
    tick_seconds: float
    max_concurrent: int
    drain_seconds: float


@dataclass(frozen=True)
class Claude:
    binary: str
    model: str
    sessions_kept_days: int


@dataclass(frozen=True)
class Data:
    db: Path
    workspace: Path


@dataclass(frozen=True)
class Nightly:
    window: str
    max_sessions: int
    max_turns: int
    max_minutes: int

    def bounds(self) -> tuple[time, time]:
        start, end = self.window.split("-")
        return time.fromisoformat(start), time.fromisoformat(end)


@dataclass(frozen=True)
class Business:
    leads_per_run: int


@dataclass(frozen=True)
class Database:
    max_rows: int      # rows a query returns at most
    max_seconds: float  # a statement past this is interrupted


@dataclass(frozen=True)
class Ui:
    start_page: str
    refresh_seconds: int
    time_format: str
    page_size: int


@dataclass(frozen=True)
class Config:
    root: Path
    server: Server
    scheduler: Scheduler
    claude: Claude
    data: Data
    nightly: Nightly
    business: Business
    database: Database
    ui: Ui

    @property
    def url(self) -> str:
        return f"http://{self.server.host}:{self.server.port}"


def load(root: Path = ROOT) -> Config:
    raw = tomllib.loads((root / "config.toml").read_text("utf-8"))
    return Config(
        root=root,
        server=Server(**raw["server"]),
        scheduler=Scheduler(**raw["scheduler"]),
        claude=Claude(**raw["claude"]),
        data=Data(db=root / raw["data"]["db"], workspace=root / raw["data"]["workspace"]),
        nightly=Nightly(**raw["nightly"]),
        business=Business(**raw["business"]),
        database=Database(**raw["database"]),
        ui=Ui(**raw["ui"]),
    )
