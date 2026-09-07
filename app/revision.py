"""Code revision = hash of the source tree. The launcher compares it with the running daemon's."""

from __future__ import annotations

import hashlib
from pathlib import Path

SUFFIXES = {".py", ".js", ".mjs", ".html", ".css", ".sql", ".md", ".toml"}
SKIP_DIRS = {"__pycache__", ".browser-profile", ".pytest_cache"}


def _files(root: Path) -> list[Path]:
    out = []
    for p in (root / "app").rglob("*"):
        if p.is_file() and p.suffix in SUFFIXES and not (SKIP_DIRS & set(p.parts)):
            out.append(p)
    out.append(root / "config.toml")
    return sorted(out)


def compute(root: Path) -> str:
    h = hashlib.sha256()
    for p in _files(root):
        h.update(str(p.relative_to(root)).encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:12]
