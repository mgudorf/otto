"""The feedback queue as the repo's workflows read it: a module's uncleared rows, and the open Patches entries that concern it.

`python -m app.modules.feedback list <module>...` before work starts; `clear <module>...` once every row was either resolved
on main or written into the module doc's Patches section. Runs from the primary checkout, where the live database is.
"""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path
from textwrap import indent

import app.modules
from app.store import Store, now_iso

MODULES_DIR = Path(app.modules.__file__).parent
PLATFORM = "app"                          # the platform doc, docs/app/CLAUDE.md, is a module doc like the others
SHELL_PAGES = ("activity", "settings")   # feedback pages that are not modules; their patches live in the platform doc
FIELDS = "id, created_at, page, item_module, item_id, item_text, text, status, kind, title, summary, ref, draft, error"


def add_cleared_at(conn: sqlite3.Connection) -> None:
    """The column a feedback table created before it lacks; a no-op afterwards."""
    if "cleared_at" not in {r[1] for r in conn.execute("PRAGMA table_info(feedback)")}:
        conn.execute("ALTER TABLE feedback ADD COLUMN cleared_at TEXT")


def names() -> list[str]:
    """Every module package, the platform, and the shell pages: the names `list` and `clear` accept."""
    return sorted(p.name for p in MODULES_DIR.iterdir() if (p / "__init__.py").exists()) + [PLATFORM, *SHELL_PAGES]


def _scope(modules: list[str]) -> tuple[str, list[str]]:
    marks = ", ".join("?" * len(modules))
    return f"cleared_at IS NULL AND (page IN ({marks}) OR item_module IN ({marks}))", [*modules, *modules]


def pending(store: Store, modules: list[str]) -> list[dict]:
    """Rows recorded from a module's page, or about one of its items, that no work session has cleared. Any status."""
    where, params = _scope(modules)
    return store.query(f"SELECT {FIELDS} FROM feedback WHERE {where} ORDER BY id", tuple(params))


def clear(store: Store, modules: list[str]) -> list[int]:
    """Stamp cleared_at on every pending row of the modules; nothing is deleted. Returns the ids."""
    where, params = _scope(modules)
    ids = [r["id"] for r in store.query(f"SELECT id FROM feedback WHERE {where} ORDER BY id", tuple(params))]
    if ids:
        store.execute(f"UPDATE feedback SET cleared_at = ? WHERE id IN ({', '.join('?' * len(ids))})", (now_iso(), *ids))
    return ids


def _field(body: str, name: str) -> str:
    m = re.search(rf"^- {name}: (.*)$", body, re.M)
    return m.group(1).strip() if m else ""


def entries(root: Path) -> list[dict]:
    """Every `### ` entry under `## Patches` in each docs/<module>/CLAUDE.md, the platform's `app` among them."""
    docs = sorted((p.parent.name, p) for p in (root / "docs").glob("*/CLAUDE.md"))
    out = []
    for doc, path in docs:
        if not path.exists():
            continue
        section = re.search(r"^## Patches\n(.*?)(?=^## |\Z)", path.read_text("utf-8"), re.S | re.M)
        if not section:
            continue
        for block in re.split(r"^(?=### )", section.group(1), flags=re.M):
            if block.startswith("### "):
                title, _, body = block.partition("\n")
                out.append({"doc": doc, "path": path.relative_to(root).as_posix(), "title": title[4:].strip(),
                            "kind": _field(body, "Kind"), "status": _field(body, "Status"), "body": body})
    return out


def patches(root: Path, modules: list[str]) -> list[dict]:
    """Open entries for the modules: those in their own docs, plus entries elsewhere whose text names their code."""
    own = {m: PLATFORM if m in SHELL_PAGES else m for m in modules}
    out = []
    for e in entries(root):
        hits = [m for m in modules if e["doc"] == own[m] or any(s in e["body"] for s in (f"modules/{m}/", f"pages/{m}.js", f"/api/{m}/"))]
        if hits:
            out.append({**e, "modules": hits})
    return out


def open_counts(root: Path) -> dict[str, int]:
    """Open entries per doc, for the Feedback agent's Current state block."""
    counts: dict[str, int] = {}
    for e in entries(root):
        counts[e["doc"]] = counts.get(e["doc"], 0) + 1
    return counts


def _print(rows: list[dict]) -> None:
    for r in rows:
        item = f" · item {r['item_module']} {r['item_id']}" if r["item_module"] else ""
        kind = f" {r['kind']}" if r["kind"] else ""
        print(f"#{r['id']}  {r['created_at']}  page {r['page']}{item}  {r['status']}{kind}")
        for key in ("title", "summary", "ref", "error"):
            if r[key]:
                print(f"  {key}: {r[key]}")
        print("  text: |")
        print(indent(r["text"], "    "))
        if r["item_text"]:
            print("  item_text: |")
            print(indent(r["item_text"], "    "))
        if r["draft"]:
            print("  draft: |")
            print(indent(r["draft"], "    "))
        print()


def main(argv: list[str], config) -> int:
    valid = names()
    verb, modules = (argv[0] if argv else ""), argv[1:]
    unknown = [m for m in modules if m not in valid]
    if verb not in ("list", "clear") or not modules or unknown:
        print(f"usage: python -m app.modules.feedback list|clear <module>...\nmodules: {', '.join(valid)}", file=sys.stderr)
        if unknown:
            print(f"unknown: {', '.join(unknown)}", file=sys.stderr)
        return 2
    if not config.data.db.exists():
        print(f"no database at {config.data.db}; run from the primary checkout", file=sys.stderr)
        return 1
    store = Store(config.data.db)
    try:
        with store.raw() as conn:
            add_cleared_at(conn)
        who = ", ".join(modules)
        if verb == "clear":
            ids = clear(store, modules)
            print(f"cleared {len(ids)} feedback rows for {who}: {', '.join(map(str, ids)) or 'none'}")
            return 0
        rows = pending(store, modules)
        print(f"feedback · {who} · {len(rows)} pending\n")
        _print(rows)
        found = patches(config.root, modules)
        print(f"patches · {who} · {len(found)} open\n")
        for e in found:
            print(f"- {e['path']}: {e['title']} [{e['kind']}, {e['status']}]")
        return 0
    finally:
        store.close()
