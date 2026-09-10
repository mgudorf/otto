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
    stagger_minutes: int

    def bounds(self) -> tuple[time, time]:
        start, end = self.window.split("-")
        return time.fromisoformat(start), time.fromisoformat(end)


@dataclass(frozen=True)
class Business:
    leads_per_run: int


@dataclass(frozen=True)
class Memory:
    suggest_lookback_days: int
    suggest_max: int


@dataclass(frozen=True)
class Science:
    python: str
    root: Path
    idle_minutes: int
    tool_output_chars: int


@dataclass(frozen=True)
class Education:
    per_night: int
    start_difficulty: int
    flow_low: int
    flow_high: int


@dataclass(frozen=True)
class Database:
    max_rows: int      # rows a query returns at most
    max_seconds: float  # a statement past this is interrupted


@dataclass(frozen=True)
class Email:
    client_file: Path
    token_file: Path
    backfill_days: int
    triage_batch: int


@dataclass(frozen=True)
class WebSearch:
    max_findings: int


@dataclass(frozen=True)
class Feedback:
    max_turns: int


@dataclass(frozen=True)
class Ui:
    start_page: str
    refresh_seconds: int
    time_format: str
    page_size: int
    side_max: int
    middle_max: int


@dataclass(frozen=True)
class Config:
    root: Path
    server: Server
    scheduler: Scheduler
    claude: Claude
    data: Data
    nightly: Nightly
    business: Business
    memory: Memory
    science: Science
    education: Education
    database: Database
    email: Email
    web_search: WebSearch
    feedback: Feedback
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
        memory=Memory(**raw["memory"]),
        science=Science(**{**raw["science"], "root": root / raw["science"]["root"]}),
        education=Education(**raw["education"]),
        database=Database(**raw["database"]),
        email=Email(
            client_file=root / raw["email"]["client_file"], token_file=root / raw["email"]["token_file"],
            backfill_days=raw["email"]["backfill_days"], triage_batch=raw["email"]["triage_batch"],
        ),
        web_search=WebSearch(**raw["web_search"]),
        feedback=Feedback(**raw["feedback"]),
        ui=Ui(**raw["ui"]),
    )
