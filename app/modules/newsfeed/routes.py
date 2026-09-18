"""Newsfeed: the entries the nightly searches return, the yes or no on each, tags on entries and searches, and killing a search.

A search's row id is `s<id>`; an entry's is the bare integer, so Home's inspector and the page post the same thing.
Nothing here creates a search: that is the agent's newsfeed_search_add. Every write is a user action through the runner.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Body, HTTPException, Request

from app.store import Store, iso, now_iso, parse

router = APIRouter(prefix="/api/newsfeed")

CHIPS = {"All": "status != 'dismissed'", "Open": "status = 'open'", "Accepted": "status = 'accepted'"}
LISTED = CHIPS["All"]                              # a dismissed entry leaves every list; the row stays so no run proposes it again
SEARCH = "s"                                       # a search's row id, "s12"; an entry carries the bare integer
RESOURCE = "newsfeed"


def _day(ts: str) -> str:
    return parse(ts).astimezone().strftime("%d-%m-%Y")


def _happens(starts_at: str) -> str:
    return datetime.fromisoformat(starts_at).strftime("%a %d-%m-%Y")


def _row(r: dict) -> dict:
    row = {
        "id": r["id"],
        "module": "newsfeed",
        "text": r["text"],
        "stamp": r["found_at"],
        "unread": r["status"] == "open",   # bright until decided, like unread mail
    }
    if r["starts_at"]:
        row["stampText"] = _happens(r["starts_at"])
    return row


def _group_by_day(rows: list[dict]) -> list[dict]:
    groups: list[dict] = []
    for r in rows:
        label = _day(r["found_at"])
        if not groups or groups[-1]["label"] != label:
            groups.append({"label": label, "count": 0, "rows": []})
        groups[-1]["rows"].append(_row(r))
        groups[-1]["count"] += 1
    return groups


def _search(query: str) -> tuple[list[str], list[str]]:
    """One LIKE per word over text, url, summary and tags, all words required."""
    where, params = [], []
    for term in query.split():
        where.append(
            "(text LIKE ? OR url LIKE ? OR summary LIKE ?"
            " OR id IN (SELECT ref FROM newsfeed_tags WHERE kind = 'item' AND tag LIKE ?))"
        )
        params += [f"%{term}%"] * 4
    return where, params


def tags_of(store: Store, kind: str, ref: int) -> list[str]:
    return [r["tag"] for r in store.query("SELECT tag FROM newsfeed_tags WHERE kind = ? AND ref = ? ORDER BY tag", (kind, ref))]


def _ref(value) -> tuple[str, int]:
    """("search", 12) for "s12", ("item", 12) for 12 or "12"; anything else is a 400, so a bad id never becomes a failed job."""
    text = str(value if value is not None else "")
    if text.startswith(SEARCH) and text[len(SEARCH):].isdigit():
        return "search", int(text[len(SEARCH):])
    if text.isdigit():
        return "item", int(text)
    raise HTTPException(400, "id required")


def _get_item(store: Store, item_id: int) -> dict:
    row = store.one("SELECT * FROM newsfeed_items WHERE id = ?", (item_id,))
    if row is None:
        raise HTTPException(404, "no such entry")
    return row


def _get_search(store: Store, search_id: int) -> dict:
    row = store.one("SELECT * FROM newsfeed_searches WHERE id = ?", (search_id,))
    if row is None:
        raise HTTPException(404, "no such search")
    return row


def searches(store: Store) -> list[dict]:
    """Every search with its tags and how many of its entries still wait, for the blank state and the agent."""
    rows = store.query(
        "SELECT s.*, (SELECT COUNT(*) FROM newsfeed_items i WHERE i.search_id = s.id AND i.status = 'open') AS open"
        " FROM newsfeed_searches s ORDER BY s.created_at, s.id"
    )
    return [{**r, "id": f"{SEARCH}{r['id']}", "tags": tags_of(store, "search", r["id"])} for r in rows]


@router.get("/left")
def left(request: Request, query: str = "", chip: str = "All", page: int = 0) -> dict:
    store: Store = request.app.state.store
    size = int(store.setting("ui.page_size"))
    limit = size * (page + 1)
    chip = chip if chip in CHIPS else "All"
    where, params = _search(query)
    where.append(CHIPS[chip])
    sql_where = "WHERE " + " AND ".join(where)
    total = store.scalar(f"SELECT COUNT(*) FROM newsfeed_items {sql_where}", tuple(params))
    rows = store.query(f"SELECT * FROM newsfeed_items {sql_where} ORDER BY found_at DESC, id DESC LIMIT ?", (*params, limit))
    return {
        "groups": _group_by_day(rows),
        "chips": list(CHIPS),
        "chip": chip,
        "more": total > limit,
    }


@router.get("/blank")
def blank(request: Request) -> dict:
    store: Store = request.app.state.store
    return {
        "searches": searches(store),
        "open": store.scalar("SELECT COUNT(*) FROM newsfeed_items WHERE status = 'open'"),
        "total": store.scalar(f"SELECT COUNT(*) FROM newsfeed_items WHERE {LISTED}"),
        "last_run": store.cursor("newsfeed.run"),
    }


@router.get("/item/{item_id}")
def item_route(request: Request, item_id: str) -> dict:
    return item(request.app.state.store, item_id)


def _search_item(store: Store, search_id: int) -> dict:
    r = _get_search(store, search_id)
    return {
        **r,
        "id": f"{SEARCH}{r['id']}",
        "module": "newsfeed",
        "kind": "search",
        "text": r["name"],
        "tags": tags_of(store, "search", r["id"]),
        "open": store.scalar("SELECT COUNT(*) FROM newsfeed_items WHERE search_id = ? AND status = 'open'", (r["id"],)),
        "entries": store.scalar("SELECT COUNT(*) FROM newsfeed_items WHERE search_id = ?", (r["id"],)),
        "actions": [{"verb": "kill", "label": "Kill", "confirm": "Kill this search? Its entries stay.", "removes": True}],
    }


def item(store: Store, item_id: str) -> dict:
    kind, ref = _ref(item_id)
    if kind == "search":
        return _search_item(store, ref)
    r = _get_item(store, ref)
    actions = []
    if r["status"] == "open":
        actions.append({"verb": "accept", "label": "Accept", "primary": True})
        actions.append({"verb": "dismiss", "label": "Dismiss", "removes": True})
    actions.append({"verb": "link", "label": "Open", "href": r["url"]})
    search = store.one("SELECT name FROM newsfeed_searches WHERE id = ?", (r["search_id"],)) if r["search_id"] else None
    return {
        **r,
        "module": "newsfeed",
        "kind": "entry",
        "created_at": r["found_at"],
        "search": search["name"] if search else None,
        "tags": tags_of(store, "item", r["id"]),
        "actions": actions,
    }


@router.post("/action/{verb}")
async def action(request: Request, verb: str, body: dict = Body(default={})) -> dict:
    st = request.app.state
    store: Store = st.store
    prepare = ACTIONS.get(verb)
    if prepare is None:
        raise HTTPException(404, f"unknown action {verb}")
    write = prepare(store, body)   # validates here, so a bad request answers 400 / 404 / 409 and never becomes a failed job

    async def run(ctx):
        return write(ctx)

    return await st.runner.run_action(f"newsfeed.{verb}", "newsfeed", RESOURCE, run)


# Each action validates against the store first and returns the write to run inside the job.
def _decide(status: str):
    def prepare(store: Store, body: dict):
        kind, ref = _ref(body.get("id"))
        if kind != "item":
            raise HTTPException(400, "only an entry is accepted or dismissed")
        r = _get_item(store, ref)
        if r["status"] != "open":
            raise HTTPException(409, f"already {r['status']}")

        def write(ctx) -> dict:
            with ctx.commit() as conn:
                conn.execute("UPDATE newsfeed_items SET status = ?, decided_at = ? WHERE id = ?", (status, now_iso(), r["id"]))
            ctx.event(status, r["text"][:120], ref=str(r["id"]))
            return {"id": r["id"], "status": status}

        return write

    return prepare


def _tag(store: Store, body: dict):
    kind, ref = _ref(body.get("id"))
    r = _get_search(store, ref) if kind == "search" else _get_item(store, ref)
    tags = [str(t).strip().lower() for t in body.get("tags", []) if str(t).strip()]
    if not tags:
        raise HTTPException(400, "no tags")

    def write(ctx) -> dict:
        with ctx.commit() as conn:
            for t in tags:
                conn.execute("INSERT OR IGNORE INTO newsfeed_tags(kind, ref, tag) VALUES (?, ?, ?)", (kind, ref, t))
        ctx.event("tagged", f"{', '.join(tags)} on {r.get('name') or r.get('text')[:80]}", ref=body.get("id") and str(body["id"]))
        return {"id": body["id"], "tags": tags_of(store, kind, ref)}

    return write


def _untag(store: Store, body: dict):
    kind, ref = _ref(body.get("id"))
    _get_search(store, ref) if kind == "search" else _get_item(store, ref)

    def write(ctx) -> dict:
        with ctx.commit() as conn:
            conn.execute("DELETE FROM newsfeed_tags WHERE kind = ? AND ref = ? AND tag = ?", (kind, ref, str(body.get("tag", "")).strip().lower()))
        return {"id": body["id"], "tags": tags_of(store, kind, ref)}

    return write


def _kill(store: Store, body: dict):
    kind, ref = _ref(body.get("id"))
    if kind != "search":
        raise HTTPException(400, "only a search is killed; an entry is dismissed")
    r = _get_search(store, ref)

    def write(ctx) -> dict:
        with ctx.commit() as conn:
            conn.execute("DELETE FROM newsfeed_tags WHERE kind = 'search' AND ref = ?", (r["id"],))
            conn.execute("DELETE FROM newsfeed_searches WHERE id = ?", (r["id"],))   # entries keep their rows, search_id set NULL
        ctx.event("killed", r["name"], ref=f"{SEARCH}{r['id']}")
        return {"id": f"{SEARCH}{r['id']}"}

    return write


ACTIONS = {"accept": _decide("accepted"), "dismiss": _decide("dismissed"), "tag": _tag, "untag": _untag, "kill": _kill}


# ---- shell hooks ---------------------------------------------------------------------------
def numbers(store: Store) -> dict:
    return {"value": store.scalar("SELECT COUNT(*) FROM newsfeed_items WHERE status = 'open'"), "label": "to review"}


def today(store: Store) -> list[dict]:
    """Entries found today, plus any that happen today; the day's feed and the day's plan."""
    start = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = store.query(
        f"SELECT * FROM newsfeed_items WHERE {LISTED} AND (found_at >= ? OR starts_at BETWEEN ? AND ?) ORDER BY found_at DESC, id DESC",
        (iso(start), start.strftime("%Y-%m-%d"), start.strftime("%Y-%m-%dT23:59")),
    )
    return [_row(r) for r in rows]


def queue(store: Store) -> list[dict]:
    """Every entry still waiting on a yes or no, newest first; Home lists these under Review however old they are."""
    rows = store.query("SELECT * FROM newsfeed_items WHERE status = 'open' ORDER BY found_at DESC, id DESC")
    return [_row(r) for r in rows]


def context(store: Store, registry) -> str:
    lines = ["Searches (id, name, every N days, cap per run, next run, tags):"]
    for s in searches(store):
        lines.append(f"  {s['id']} {s['name']}: every {s['every_days']} d, cap {s['cap']}, next {s['next_run']}, tags {', '.join(s['tags']) or 'none'}")
    if len(lines) == 1:
        lines.append("  none")
    open_ = store.query("SELECT id, text, url FROM newsfeed_items WHERE status = 'open' ORDER BY found_at DESC, id DESC")
    lines.append(f"Awaiting a yes or no ({len(open_)}):")
    lines += [f"  #{o['id']} {o['text'][:100]} <{o['url']}>" for o in open_] or ["  none"]
    lines.append("Last run: " + (store.cursor("newsfeed.run") or "never"))
    return "\n".join(lines)
