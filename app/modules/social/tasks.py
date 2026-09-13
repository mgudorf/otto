"""One nightly, read-only web scout for events around the configured cities. Each find waits on the owner's yes or no."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from app.modules.social.routes import CATEGORIES, MEANS
from app.store import now_iso

NO_ALCOHOL = (
    "Skip anything built around drinking: bar crawls, brewery and distillery tours, wine tastings, happy hours, drink specials. "
    "A venue that happens to serve alcohol is fine when the event itself is not about it."
)


def _json_array(raw: str) -> list:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("["):]
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < 0:
        raise ValueError(f"no JSON array in reply: {raw[:200]!r}")
    return json.loads(text[start:end + 1])


def _starts_at(day: str, clock: str, first: datetime, last: datetime) -> str | None:
    """`YYYY-MM-DD` plus an optional `HH:MM` into the naive local stamp, or None when it is unusable or out of the horizon."""
    try:
        at = datetime.strptime(f"{day.strip()}T{(clock.strip() or '00:00')}", "%Y-%m-%dT%H:%M")
    except ValueError:
        return None
    return at.strftime("%Y-%m-%dT%H:%M") if first <= at <= last else None


async def scout(ctx) -> str:
    cfg = ctx.config.social
    cap = cfg.events_per_run
    now = datetime.now().astimezone().replace(tzinfo=None)
    first = now.replace(hour=0, minute=0, second=0, microsecond=0)
    last = first + timedelta(days=cfg.horizon_days)
    interests = ctx.store.query("SELECT text FROM social_items WHERE kind = 'interest' ORDER BY created_at")
    seen = ctx.store.query(
        "SELECT text, ref, starts_at, status FROM social_items WHERE kind = 'event' ORDER BY created_at DESC LIMIT 100"
    )
    prompt = "\n".join([
        f"Find events happening within {cfg.radius_miles} miles of any of these towns: " + ", ".join(cfg.cities) + ".",
        f"Only events starting between {first:%Y-%m-%d} and {last:%Y-%m-%d}.",
        "",
        "Each event is filed under exactly one category:",
        *[f"- {c}: {MEANS[c]}" for c in CATEGORIES],
        "",
        NO_ALCOHOL,
        "",
        "What the owner has said they are interested in, in their own words. Let these steer the search; they do not limit it:",
        *([f"- {i['text'][:300]}" for i in interests] or ["- nothing recorded yet, so cover the categories broadly"]),
        "",
        "Events already recorded (status, date, url, text). Never repeat a url on the same date; a `going` one shows what the owner picks,"
        " a `dismissed` one what to stop bringing:",
        *([f"- ({s['status']}) {s['starts_at']} {s['ref']} {s['text'][:100]}" for s in seen] or ["- none"]),
        "",
        f"Use WebSearch and WebFetch to find up to {cap} new events. Each must be real, dated and open to the public.",
        'Reply with only a JSON array. Each element: {"text": one line naming the event, "url": its listing page,'
        f' "category": one of {", ".join(CATEGORIES)}, "city": the town it is in, "venue": where,'
        ' "date": "YYYY-MM-DD", "time": "HH:MM" or "" when the listing gives none,'
        ' "why": one sentence on why it suits the owner}.',
        "An empty array is a fine answer when nothing new and concrete turned up.",
    ])
    raw = await ctx.run_task(prompt, tools=("social_search",))
    items = _json_array(raw)
    ts = now_iso()
    added: list[tuple[int, str]] = []
    with ctx.commit(cursor=("social.scout", ts)) as conn:
        for it in items:
            text = str(it.get("text", "")).strip()
            ref = str(it.get("url", "")).strip()
            category = str(it.get("category", "")).strip().lower()
            starts_at = _starts_at(str(it.get("date", "")), str(it.get("time", "")), first, last)
            if not text or not ref or category not in CATEGORIES or not starts_at:
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO social_items(kind, text, ref, why, category, city, venue, starts_at, created_at, updated_at)"
                " VALUES ('event', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    text, ref, str(it.get("why", "")).strip() or None, category,
                    str(it.get("city", "")).strip() or None, str(it.get("venue", "")).strip() or None,
                    starts_at, ts, ts,
                ),
            )
            if cur.rowcount:
                added.append((cur.lastrowid, text))
            if len(added) >= cap:
                break
    for event_id, text in added:
        ctx.event("found", text[:120], ref=str(event_id))
    return f"{len(added)} new event(s) from {len(items)} proposed"
