"""Home serves the one feed: every faceted module's rows merged into a single list, narrowed by tag and by typed text."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.store import tag_key

router = APIRouter()

FEED_ROWS = 200           # rows Recent asks of one module; the feed is the merge of those
TODAY_ROWS = 5            # the day's rows a module contributes to the agent's lines
REVIEW = "Review"         # what the agent's lines call the queue
LAST = float("inf")       # a queue row its module left unranked waits behind every ranked one; the feed ranks the rest


def _enabled(store, registry) -> list:
    """Every enabled module carrying a facet; one without a facet lists no rows, so it reaches no feed."""
    return [
        m for m in registry.ordered()
        if m.manifest.facet and store.setting(f"modules.{m.name}.enabled") is not False
    ]


def _row(m, r: dict) -> dict:
    return {**r, "module": r.get("module") or m.name}


def _keeps(row: dict, want: set[str], q: str) -> bool:
    """A row survives when it carries every named tag and its own words hold the typed text."""
    carried = {tag_key(t) for t in [*(row.get("fixed") or []), *(row.get("tags") or [])]}
    return want <= carried and q in f"{row.get('title') or ''}\n{row.get('snip') or ''}".lower()


@router.get("/api/feed")
def feed_route(request: Request, mode: str = "priority", tags: str = "", q: str = "", limit: int = FEED_ROWS) -> dict:
    """Priority is every queue, least patient first; Recent is every module's newest, undated rows last."""
    if mode not in ("priority", "recent"):
        raise HTTPException(400, "mode must be priority or recent")
    st = request.app.state
    want = {t for t in (tag_key(t) for t in tags.split(",")) if t}
    needle = q.strip().lower()
    mods = _enabled(st.store, st.registry)
    if mode == "priority":
        items = [_row(m, r) for m in mods if m.queue for r in m.queue(st.store)]
        items = [r for r in items if _keeps(r, want, needle)]
        items.sort(key=lambda r: LAST if r.get("waits") is None else r["waits"])
        for rank, r in enumerate(items, 1):   # the feed groups by facet, so the rank that matters is the one inside a facet
            r["waits"] = rank
    else:
        cap = max(1, min(limit, 1000))
        items = [_row(m, r) for m in mods if m.rows for r in m.rows(st.store, cap)]
        items = [r for r in items if _keeps(r, want, needle)]
        items.sort(key=lambda r: (bool(r.get("when")), r.get("when") or ""), reverse=True)
    return {"items": items}


@router.get("/api/home/numbers")
def numbers_route(request: Request) -> list[dict]:
    st = request.app.state
    out = []
    for m in _enabled(st.store, st.registry):
        if m.numbers:
            n = m.numbers(st.store)
            if n:
                out.append({"module": m.name, "facet": m.manifest.facet, "hue": m.manifest.hue, "icon": m.manifest.icon, **n})
    return out


def context(store, registry) -> str:
    mods = _enabled(store, registry)
    lines = []
    for m in mods:
        n = m.numbers(store) if m.numbers else None
        rows = m.today(store) if m.today else []
        head = f"{m.manifest.title}: " + (f"{n['value']} {n['label']}" if n else "no counter")
        lines.append(head + f"; {len(rows)} today")
        for r in rows[:TODAY_ROWS]:
            lines.append(f"  - {(r.get('title') or '')[:160]}")
    queues = [(m, m.queue(store)) for m in mods if m.queue]
    if queues:
        waiting = sum(len(rows) for _, rows in queues)
        lines.append(f"{REVIEW}: {waiting} waiting" if waiting else f"{REVIEW}: nothing waiting")
        for m, rows in queues:
            for r in rows:
                lines.append(f"  - ({m.name} {r.get('id')}) {(r.get('title') or '')[:160]}")
    return "\n".join(lines) if lines else "No modules report anything today."
