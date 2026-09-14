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
    model: str                    # the CLI's --model unless a module picks its own; "default" leaves the CLI's choice alone
    models: tuple[str, ...]       # what a module may pick on its page, besides "default"
    efforts: tuple[str, ...]      # --effort levels a module may pick, besides "default"
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
class Chat:
    upload_max_mb: int   # an attachment larger than this is refused
    replay_chars: int    # characters of the stored transcript replayed when the CLI has lost a conversation


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
    read_on_open: bool
    consent_warn_days: int


@dataclass(frozen=True)
class WebSearch:
    max_findings: int


@dataclass(frozen=True)
class Social:
    cities: tuple[str, ...]
    radius_miles: int
    horizon_days: int
    events_per_run: int


@dataclass(frozen=True)
class Feedback:
    max_turns: int


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
    chat: Chat
    business: Business
    memory: Memory
    science: Science
    education: Education
    database: Database
    email: Email
    web_search: WebSearch
    social: Social
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
        claude=Claude(**{**raw["claude"], "models": tuple(raw["claude"]["models"]), "efforts": tuple(raw["claude"]["efforts"])}),
        data=Data(db=root / raw["data"]["db"], workspace=root / raw["data"]["workspace"]),
        nightly=Nightly(**raw["nightly"]),
        chat=Chat(**raw["chat"]),
        business=Business(**raw["business"]),
        memory=Memory(**raw["memory"]),
        science=Science(**{**raw["science"], "root": root / raw["science"]["root"]}),
        education=Education(**raw["education"]),
        database=Database(**raw["database"]),
        email=Email(**{
            **raw["email"],
            "client_file": root / raw["email"]["client_file"],
            "token_file": root / raw["email"]["token_file"],
        }),
        web_search=WebSearch(**raw["web_search"]),
        social=Social(**{**raw["social"], "cities": tuple(raw["social"]["cities"])}),
        feedback=Feedback(**raw["feedback"]),
        ui=Ui(**raw["ui"]),
    )
