"""Home aggregates the other modules: one number each, and what each produced today."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/home")

TODAY_ROWS = 5


def _enabled_pages(request: Request):
    st = request.app.state
    return [
        m for m in st.registry.ordered()
        if m.manifest.page and m.name != "home" and st.store.setting(f"modules.{m.name}.enabled") is not False
    ]


@router.get("/numbers")
def numbers_route(request: Request) -> list[dict]:
    store = request.app.state.store
    out = []
    for m in _enabled_pages(request):
        if m.numbers:
            n = m.numbers(store)
            if n:
                out.append({"module": m.name, "hue": m.manifest.hue, "icon": m.manifest.icon, **n})
    return out


@router.get("/left")
def left_route(request: Request) -> dict:
    store = request.app.state.store
    groups = []
    for m in _enabled_pages(request):
        if not m.today:
            continue
        rows = m.today(store)
        groups.append({
            "module": m.name,
            "label": m.manifest.title,
            "hue": m.manifest.hue,
            "icon": m.manifest.icon,
            "count": len(rows),
            "rows": rows[:TODAY_ROWS],
            "more": max(0, len(rows) - TODAY_ROWS),
        })
    return {"groups": groups}


def context(store, registry) -> str:
    lines = []
    for m in registry.ordered():
        if not m.manifest.page or m.name == "home" or store.setting(f"modules.{m.name}.enabled") is False:
            continue
        n = m.numbers(store) if m.numbers else None
        rows = m.today(store) if m.today else []
        head = f"{m.manifest.title}: " + (f"{n['value']} {n['label']}" if n else "no counter")
        lines.append(head + f"; {len(rows)} today")
        for r in rows[:TODAY_ROWS]:
            lines.append(f"  - {r.get('text', '')[:160]}")
    return "\n".join(lines) if lines else "No modules report anything today."
