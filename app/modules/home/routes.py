"""Home aggregates the other modules: what still waits on a decision, one number each, today's rows, and the newest items."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/home")

TODAY_ROWS = 5            # the day's rows a module contributes, on LEFT and in the agent's lines
RECENT_ROWS = 5           # the rows Recent draws per module, which is what each module is asked for
REVIEW = "Review"         # what a queue group is called; `waiting` on the group, not this word, is what marks it

log = logging.getLogger("otto.home")


def _enabled(store, registry) -> list:
    """Every module with hooks, page or not: a queue waits on the owner whether or not it has a rail entry."""
    return [
        m for m in registry.ordered()
        if m.name != "home" and store.setting(f"modules.{m.name}.enabled") is not False
    ]


def _text(r: dict) -> str:
    """A row's own words, whether its module names them `title` or still `text`."""
    return r.get("title") or r.get("text") or ""


def _row(m, r: dict) -> dict:
    """One ROW: id, module, title, when, tags, fixed, and whatever else its module put on it."""
    return {
        **r,
        "module": r.get("module") or m.name,
        "title": _text(r),
        "when": r.get("when") or r.get("stamp") or "",
        "tags": list(r.get("tags") or []),
        "fixed": list(r.get("fixed") or []),
    }


def _actions(store, m, r: dict) -> list:
    """The verbs the owning module offers on a waiting row, so what waits can be decided from Home."""
    if not m.item:
        return []
    try:
        return (m.item(store, str(r.get("id"))) or {}).get("actions") or []
    except HTTPException:      # the module says it has no such row: there is nothing to offer on it
        return []
    except Exception:          # anything else is the module failing, and a row with no verbs would hide that
        log.exception("%s could not describe waiting row %s", m.name, r.get("id"))
        return []


def _waiting(store, m) -> list[dict]:
    return [{**_row(m, r), "actions": r.get("actions") or _actions(store, m, r)} for r in m.queue(store)]


def _dated(m, rows: list[dict]) -> list[dict]:
    """Newest first, and only rows that carry a time: "newest" means nothing for one that has none, and Home invents none."""
    out = [row for row in (_row(m, r) for r in rows) if row["when"]]
    return sorted(out, key=lambda r: r["when"], reverse=True)


def _group(m, label: str, rows: list[dict], shown: int | None, waiting: bool) -> dict:
    """One group: `waiting` says its rows wait on a decision, `page` whether the header navigates; shown=None cuts nothing."""
    kept = rows if shown is None else rows[:shown]
    return {
        "module": m.name,
        "label": label,
        "waiting": waiting,
        "hue": m.manifest.hue,
        "icon": m.manifest.icon,
        "page": m.manifest.page,
        "count": len(rows),
        "rows": kept,
        "more": len(rows) - len(kept),
    }


@router.get("/numbers")
def numbers_route(request: Request) -> list[dict]:
    st = request.app.state
    out = []
    for m in _enabled(st.store, st.registry):
        if m.numbers:
            n = m.numbers(st.store)
            if n:
                out.append({"module": m.name, "hue": m.manifest.hue, "icon": m.manifest.icon, "page": m.manifest.page, **n})
    return out


@router.get("/left")
def left_route(request: Request) -> dict:
    """Every queue group first, marked `waiting` and never cut, then each module's rows from today."""
    st = request.app.state
    mods = _enabled(st.store, st.registry)
    review = [_group(m, REVIEW, _waiting(st.store, m), None, True) for m in mods if m.queue]
    today = [_group(m, m.manifest.title, [_row(m, r) for r in m.today(st.store)], TODAY_ROWS, False) for m in mods if m.today]
    return {"groups": [g for g in review if g["count"]] + today}


@router.get("/recent")
def recent_route(request: Request) -> dict:
    """Home's other mode: each module's newest items, as many as Recent draws and no more."""
    st = request.app.state
    mods = [m for m in _enabled(st.store, st.registry) if m.rows]
    return {"groups": [_group(m, m.manifest.title, _dated(m, m.rows(st.store, RECENT_ROWS)), None, False) for m in mods]}


def context(store, registry) -> str:
    mods = _enabled(store, registry)
    lines = []
    for m in mods:
        n = m.numbers(store) if m.numbers else None
        rows = m.today(store) if m.today else []
        head = f"{m.manifest.title}: " + (f"{n['value']} {n['label']}" if n else "no counter")
        lines.append(head + f"; {len(rows)} today")
        for r in rows[:TODAY_ROWS]:
            lines.append(f"  - {_text(r)[:160]}")
    queues = [(m, m.queue(store)) for m in mods if m.queue]
    if queues:
        waiting = sum(len(rows) for _, rows in queues)
        lines.append(f"{REVIEW}: {waiting} waiting" if waiting else f"{REVIEW}: nothing waiting")
        for m, rows in queues:
            for r in rows:
                lines.append(f"  - ({m.name} {r.get('id')}) {_text(r)[:160]}")
    return "\n".join(lines) if lines else "No modules report anything today."
