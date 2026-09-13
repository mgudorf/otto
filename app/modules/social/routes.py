"""Social: interests the owner records, events the nightly scout finds around the configured cities, and the yes/no on each.

Every verb the item offers is a real route that takes `{id}`, so Home's generic inspector posts the same thing the page does.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Body, HTTPException, Request

from app.store import Store, iso, now_iso, parse

router = APIRouter(prefix="/api/social")

# Six characters at most: the shared Row component gives the leading slot 40px and anything longer runs into the title.
CATEGORIES = ("class", "meet", "biz", "music", "art", "food", "game", "animal", "film", "local")
MEANS = {
    "class": "workshops, classes and hands-on sessions",
    "meet": "meetups and mixers for meeting people and making friends",
    "biz": "small business, startup and entrepreneur events",
    "music": "live music and performances",
    "art": "art, craft, maker and theatre events",
    "food": "food festivals, markets and tastings",
    "game": "game nights, trivia, board and video games",
    "animal": "animal, pet and wildlife events",
    "film": "film screenings and movie nights",
    "local": "town festivals, fairs and community days",
}
# No "All": the shell resets every page's chip to "All", and an unknown chip falls back to Upcoming, which is the useful landing slice.
CHIPS = ("Upcoming", "Going", "Past", "Interests")
RESOURCE = "social"


def today_stamp() -> str:
    """Start of the local day in the naive form starts_at is stored in, so it string-compares directly."""
    return datetime.now().astimezone().strftime("%Y-%m-%dT00:00")


def _where(chip: str) -> str:
    """Each chip is its own slice with its own natural order; events read soonest-first, records newest-first."""
    if chip == "Going":
        return "kind = 'event' AND status = 'going'"
    if chip == "Past":
        return "kind = 'event' AND starts_at < :today"
    if chip == "Interests":
        return "kind = 'interest'"
    return "kind = 'event' AND starts_at >= :today"      # Upcoming: every future event, a dismissed one struck through


def _order(chip: str) -> str:
    if chip == "Past":
        return "starts_at DESC, id DESC"
    if chip == "Interests":
        return "created_at DESC, id DESC"
    return "starts_at ASC, id ASC"


def _when(r: dict) -> datetime:
    if r["kind"] == "event" and r["starts_at"]:
        return datetime.fromisoformat(r["starts_at"])
    return parse(r["created_at"]).astimezone()


def _clock(r: dict, fmt: str) -> str | None:
    """The time an event starts, or `all day` when the listing gave none. Interests keep the shared stamp."""
    if r["kind"] != "event" or not r["starts_at"]:
        return None
    at = datetime.fromisoformat(r["starts_at"])
    if at.hour == 0 and at.minute == 0:
        return "all day"
    return at.strftime("%I:%M %p").lstrip("0") if fmt == "12h" else at.strftime("%H:%M")


def _row(r: dict, fmt: str) -> dict:
    row = {
        "id": r["id"],
        "module": "social",
        "text": r["text"],
        "stamp": r["created_at"],
        "leading": {"kind": r["category"] or "interest"},
        "done": r["status"] == "dismissed",
    }
    clock = _clock(r, fmt)
    if clock is not None:
        row["stampText"] = clock
    return row


def _group_by_day(rows: list[dict], fmt: str) -> list[dict]:
    groups: list[dict] = []
    for r in rows:
        label = _when(r).strftime("%a %d %b")
        if not groups or groups[-1]["label"] != label:
            groups.append({"label": label, "count": 0, "rows": []})
        groups[-1]["rows"].append(_row(r, fmt))
        groups[-1]["count"] += 1
    return groups


def _search(query: str) -> tuple[list[str], dict]:
    """One LIKE per word over text, link, venue, city and category, all words required."""
    where, params = [], {}
    for i, term in enumerate(query.split()):
        params[f"q{i}"] = f"%{term}%"
        where.append(f"(text LIKE :q{i} OR ref LIKE :q{i} OR venue LIKE :q{i} OR city LIKE :q{i} OR category LIKE :q{i})")
    return where, params


def _get(store: Store, item_id: int) -> dict:
    row = store.one("SELECT * FROM social_items WHERE id = ?", (item_id,))
    if row is None:
        raise HTTPException(404, "no such item")
    return row


@router.get("/left")
def left(request: Request, query: str = "", chip: str = "Upcoming", page: int = 0) -> dict:
    store: Store = request.app.state.store
    size = int(store.setting("ui.page_size"))
    fmt = str(store.setting("ui.time_format"))
    limit = size * (page + 1)
    chip = chip if chip in CHIPS else "Upcoming"
    where, params = _search(query)
    where.append(_where(chip))
    params["today"] = today_stamp()
    sql_where = "WHERE " + " AND ".join(where)
    total = store.scalar(f"SELECT COUNT(*) FROM social_items {sql_where}", params)
    rows = store.query(f"SELECT * FROM social_items {sql_where} ORDER BY {_order(chip)} LIMIT :limit", {**params, "limit": limit})
    return {
        "groups": _group_by_day(rows, fmt),
        "chips": list(CHIPS),
        "chip": chip,
        "showing": f"{min(limit, total)} / {total}",
        "more": total > limit,
    }


@router.get("/blank")
def blank(request: Request) -> dict:
    st = request.app.state
    store: Store = st.store
    today = today_stamp()
    counts = {
        r["category"]: r["n"]
        for r in store.query(
            "SELECT category, COUNT(*) AS n FROM social_items WHERE kind = 'event' AND status != 'dismissed' AND starts_at >= ?"
            " GROUP BY category", (today,)
        )
    }
    events = store.query(
        "SELECT id, text, ref, why, category, city, venue, starts_at FROM social_items"
        " WHERE kind = 'event' AND status = 'open' AND starts_at >= ? ORDER BY starts_at ASC, id ASC LIMIT 20", (today,)
    )
    return {
        "categories": list(CATEGORIES),
        "counts": counts,
        "events": events,
        "cities": list(st.config.social.cities),
        "going": store.scalar("SELECT COUNT(*) FROM social_items WHERE kind = 'event' AND status = 'going' AND starts_at >= ?", (today,)),
        "interests": store.scalar("SELECT COUNT(*) FROM social_items WHERE kind = 'interest'"),
    }


@router.get("/item/{item_id}")
def item_route(request: Request, item_id: int) -> dict:
    return item(request.app.state.store, str(item_id))


def item(store: Store, item_id: str) -> dict:
    r = _get(store, int(item_id))
    actions = []
    if r["kind"] == "event":
        if r["status"] != "going":
            actions.append({"verb": "going", "label": "Going", "primary": True})
        if r["status"] != "dismissed":
            actions.append({"verb": "dismiss", "label": "Dismiss"})
        if r["ref"]:
            actions.append({"verb": "link", "label": "Open", "href": r["ref"]})
    else:
        if r["ref"]:
            actions.append({"verb": "link", "label": "Open", "href": r["ref"]})
        actions.append({"verb": "forget", "label": "Forget", "confirm": "Forget this interest?"})
    return {**r, "module": "social", "actions": actions}


@router.post("/action/{verb}")
async def action(request: Request, verb: str, body: dict = Body(default={})) -> dict:
    st = request.app.state
    store: Store = st.store
    fn = ACTIONS.get(verb)
    if fn is None:
        raise HTTPException(404, f"unknown action {verb}")
    _validate(store, verb, body)

    async def run(ctx):
        return fn(store, body, ctx)

    return await st.runner.run_action(f"social.{verb}", "social", RESOURCE, run)


def _validate(store: Store, verb: str, body: dict) -> None:
    """Reject bad input before the job is queued, so the client sees a 400 rather than a failed job."""
    if verb == "capture":
        if not (body.get("text") or "").strip():
            raise HTTPException(400, "empty text")
        return
    r = _get(store, int(body.get("id", 0)))
    if verb == "forget" and r["kind"] != "interest":
        raise HTTPException(400, "only an interest is forgotten; an event is dismissed")
    if verb in ("going", "dismiss") and r["kind"] != "event":
        raise HTTPException(400, "not an event")


def _capture(store: Store, body: dict, ctx) -> dict:
    text = body["text"].strip()
    ref = (body.get("ref") or "").strip() or None
    ts = now_iso()
    with ctx.commit() as conn:
        cur = conn.execute(
            "INSERT INTO social_items(kind, text, ref, created_at, updated_at) VALUES ('interest', ?, ?, ?, ?)", (text, ref, ts, ts)
        )
    ctx.event("captured", f"interest: {text[:120]}", ref=str(cur.lastrowid))
    return {"id": cur.lastrowid}


def _forget(store: Store, body: dict, ctx) -> dict:
    r = _get(store, int(body["id"]))
    with ctx.commit() as conn:
        conn.execute("DELETE FROM social_items WHERE id = ?", (r["id"],))
    ctx.event("forgot", f"interest: {r['text'][:120]}", ref=str(r["id"]))
    return {"id": r["id"]}


def _decide(status: str):
    def fn(store: Store, body: dict, ctx) -> dict:
        r = _get(store, int(body["id"]))
        with ctx.commit() as conn:
            conn.execute("UPDATE social_items SET status = ?, updated_at = ? WHERE id = ?", (status, now_iso(), r["id"]))
        ctx.event(status, r["text"][:120], ref=str(r["id"]))
        return {"id": r["id"], "status": status}

    return fn


ACTIONS = {"capture": _capture, "forget": _forget, "going": _decide("going"), "dismiss": _decide("dismissed")}


# ---- shell hooks ---------------------------------------------------------------------------
def numbers(store: Store) -> dict:
    return {
        "value": store.scalar(
            "SELECT COUNT(*) FROM social_items WHERE kind = 'event' AND status = 'open' AND starts_at >= ?", (today_stamp(),)
        ),
        "label": "to review",
    }


def today(store: Store) -> list[dict]:
    """Events happening today, plus anything recorded today; the day's plan rather than the day's writes."""
    fmt = str(store.setting("ui.time_format"))
    start = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = store.query(
        "SELECT * FROM social_items WHERE (kind = 'event' AND status != 'dismissed' AND starts_at >= ? AND starts_at <= ?)"
        " OR created_at >= ? ORDER BY starts_at IS NULL, starts_at ASC, created_at DESC",
        (today_stamp(), start.strftime("%Y-%m-%dT23:59"), iso(start)),
    )
    return [_row(r, fmt) for r in rows]


def queue(store: Store) -> list[dict]:
    """Every upcoming event still waiting on a yes or no, soonest first; Home lists these under Review."""
    fmt = str(store.setting("ui.time_format"))
    rows = store.query(
        "SELECT * FROM social_items WHERE kind = 'event' AND status = 'open' AND starts_at >= ? ORDER BY starts_at ASC, id ASC",
        (today_stamp(),),
    )
    return [_row(r, fmt) for r in rows]


def context(store: Store, registry) -> str:
    today_ = today_stamp()
    interests = store.query("SELECT id, text FROM social_items WHERE kind = 'interest' ORDER BY created_at")
    going = store.query(
        "SELECT id, text, city, venue, starts_at FROM social_items WHERE kind = 'event' AND status = 'going' AND starts_at >= ?"
        " ORDER BY starts_at", (today_,)
    )
    open_ = store.query(
        "SELECT id, text, category, city, starts_at, ref FROM social_items WHERE kind = 'event' AND status = 'open' AND starts_at >= ?"
        " ORDER BY starts_at", (today_,)
    )
    lines = ["Interests (id, text):"]
    lines += [f"  {i['id']}: {i['text'][:300]}" for i in interests] or ["  none"]
    lines.append(f"Going ({len(going)}):")
    lines += [f"  #{g['id']} {g['starts_at']} {g['text'][:100]} @ {g['venue'] or '?'}, {g['city'] or '?'}" for g in going] or ["  none"]
    lines.append(f"Awaiting a yes or no ({len(open_)}):")
    lines += [f"  #{o['id']} {o['starts_at']} [{o['category']}] {o['text'][:100]} <{o['ref']}>" for o in open_] or ["  none"]
    lines.append("Last scout: " + (store.cursor("social.scout") or "never"))
    return "\n".join(lines)
