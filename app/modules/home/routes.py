"""Home aggregates the other modules: what still waits on a decision, one number each, and today's rows."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/home")

TODAY_ROWS = 5
REVIEW = "Review"


def _enabled(store, registry) -> list:
    return [
        m for m in registry.ordered()
        if m.manifest.page and m.name != "home" and store.setting(f"modules.{m.name}.enabled") is not False
    ]


def _group(m, label: str, rows: list[dict], shown: int | None) -> dict:
    """One LEFT group. shown=None keeps every row, so a queue is never cut."""
    kept = rows if shown is None else rows[:shown]
    return {
        "module": m.name,
        "label": label,
        "hue": m.manifest.hue,
        "icon": m.manifest.icon,
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
                out.append({"module": m.name, "hue": m.manifest.hue, "icon": m.manifest.icon, **n})
    return out


@router.get("/left")
def left_route(request: Request) -> dict:
    st = request.app.state
    mods = _enabled(st.store, st.registry)
    review = [_group(m, REVIEW, m.queue(st.store), None) for m in mods if m.queue]
    today = [_group(m, m.manifest.title, m.today(st.store), TODAY_ROWS) for m in mods if m.today]
    return {"groups": [g for g in review if g["count"]] + today}


def context(store, registry) -> str:
    mods = _enabled(store, registry)
    lines = []
    for m in mods:
        n = m.numbers(store) if m.numbers else None
        rows = m.today(store) if m.today else []
        head = f"{m.manifest.title}: " + (f"{n['value']} {n['label']}" if n else "no counter")
        lines.append(head + f"; {len(rows)} today")
        for r in rows[:TODAY_ROWS]:
            lines.append(f"  - {r.get('text', '')[:160]}")
    queues = [(m, m.queue(store)) for m in mods if m.queue]
    if queues:
        waiting = sum(len(rows) for _, rows in queues)
        lines.append(f"{REVIEW}: {waiting} waiting" if waiting else f"{REVIEW}: nothing waiting")
        for m, rows in queues:
            for r in rows:
                lines.append(f"  - ({m.name} {r.get('id')}) {r.get('text', '')[:160]}")
    return "\n".join(lines) if lines else "No modules report anything today."
