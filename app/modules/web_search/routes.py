"""Web Search: topics the owner names, findings the nightly run queues, decisions the owner records. Every write is a user action through the runner."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Body, HTTPException, Request

from app.store import Store, iso, now_iso, parse

router = APIRouter(prefix="/api/web_search")

KINDS = ("money", "work", "learn")
CHIPS = {"All": None, "Open": "open", "Agreed": "agreed", "Disagreed": "disagreed"}
RESOURCE = "web_search"


def _row(r: dict) -> dict:
    return {
        "id": r["id"],
        "module": "web_search",
        "text": r["title"],
        "stamp": r["found_at"],
        "leading": {"kind": r["kind"]},
        "done": r["status"] == "disagreed",
    }


def _day_label(ts: str) -> str:
    return parse(ts).astimezone().strftime("%d %b")


def _group_by_day(rows: list[dict]) -> list[dict]:
    groups: list[dict] = []
    for r in rows:
        label = _day_label(r["found_at"])
        if not groups or groups[-1]["label"] != label:
            groups.append({"label": label, "count": 0, "rows": []})
        groups[-1]["rows"].append(_row(r))
        groups[-1]["count"] += 1
    return groups


def _search(query: str) -> tuple[list[str], list[str]]:
    """One LIKE per word over title and summary, all words required."""
    where, params = [], []
    for term in query.split():
        where.append("(title LIKE ? OR summary LIKE ?)")
        params += [f"%{term}%", f"%{term}%"]
    return where, params


def _get(store: Store, finding_id: int) -> dict:
    row = store.one("SELECT * FROM search_findings WHERE id = ?", (finding_id,))
    if row is None:
        raise HTTPException(404, "no such finding")
    return row


@router.get("/left")
def left(request: Request, query: str = "", chip: str = "All", page: int = 0) -> dict:
    store: Store = request.app.state.store
    size = int(store.setting("ui.page_size"))
    limit = size * (page + 1)
    status = CHIPS.get(chip)
    where, params = _search(query)
    if status:
        where.append("status = ?")
        params.append(status)
    sql_where = ("WHERE " + " AND ".join(where)) if where else ""
    total = store.scalar(f"SELECT COUNT(*) FROM search_findings {sql_where}", tuple(params))
    rows = store.query(f"SELECT * FROM search_findings {sql_where} ORDER BY found_at DESC, id DESC LIMIT ?", (*params, limit))
    return {
        "groups": _group_by_day(rows),
        "chips": list(CHIPS),
        "chip": chip if chip in CHIPS else "All",
        "showing": f"{min(limit, total)} / {total}",
        "more": total > limit,
    }


@router.get("/blank")
def blank(request: Request) -> dict:
    store: Store = request.app.state.store
    topics = store.query("SELECT id, kind, text FROM search_topics ORDER BY kind, created_at")
    queue = store.query(
        "SELECT id, kind, title, url, summary, found_at FROM search_findings WHERE status = 'open' ORDER BY found_at DESC, id DESC"
    )
    return {"kinds": list(KINDS), "topics": topics, "queue": queue, "last_run": store.cursor("web_search.nightly")}


@router.get("/item/{finding_id}")
def item_route(request: Request, finding_id: int) -> dict:
    return item(request.app.state.store, str(finding_id))


def item(store: Store, finding_id: str) -> dict:
    r = _get(store, int(finding_id))
    actions = []
    if r["status"] == "open":
        actions.append({"verb": "agree", "label": "Agree", "primary": True})
        actions.append({"verb": "disagree", "label": "Disagree"})
    actions.append({"verb": "link", "label": "Open", "href": r["url"]})
    return {**r, "module": "web_search", "text": f"{r['title']}\n\n{r['summary']}", "created_at": r["found_at"], "actions": actions}


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

    return await st.runner.run_action(f"web_search.{verb}", "web_search", RESOURCE, run)


def _validate(store: Store, verb: str, body: dict) -> None:
    """Reject bad input before the job is queued, so the client sees a 400 rather than a failed job."""
    if verb == "topic_add":
        if body.get("kind") not in KINDS:
            raise HTTPException(400, "kind must be money, work or learn")
        text = (body.get("text") or "").strip()
        if not text:
            raise HTTPException(400, "empty text")
        if store.one("SELECT id FROM search_topics WHERE text = ?", (text,)):
            raise HTTPException(409, "topic already listed")
        return
    if verb == "topic_remove":
        if store.one("SELECT id FROM search_topics WHERE id = ?", (int(body.get("id", 0)),)) is None:
            raise HTTPException(404, "no such topic")
        return
    r = _get(store, int(body.get("id", 0)))
    if r["status"] != "open":
        raise HTTPException(409, f"already {r['status']}")


def _topic_add(store: Store, body: dict, ctx) -> dict:
    text = body["text"].strip()
    with ctx.commit() as conn:
        cur = conn.execute("INSERT INTO search_topics(kind, text, created_at) VALUES (?, ?, ?)", (body["kind"], text, now_iso()))
    ctx.event("topic added", f"{body['kind']}: {text[:120]}", ref=str(cur.lastrowid))
    return {"id": cur.lastrowid}


def _topic_remove(store: Store, body: dict, ctx) -> dict:
    t = store.one("SELECT * FROM search_topics WHERE id = ?", (int(body["id"]),))
    with ctx.commit() as conn:
        conn.execute("DELETE FROM search_topics WHERE id = ?", (t["id"],))
    ctx.event("topic removed", f"{t['kind']}: {t['text'][:120]}", ref=str(t["id"]))
    return {"id": t["id"]}


def _decide(status: str):
    def fn(store: Store, body: dict, ctx) -> dict:
        r = _get(store, int(body["id"]))
        with ctx.commit() as conn:
            conn.execute("UPDATE search_findings SET status = ?, decided_at = ? WHERE id = ?", (status, now_iso(), r["id"]))
        ctx.event(status, r["title"][:120], ref=str(r["id"]))
        return {"id": r["id"], "status": status}

    return fn


ACTIONS = {"topic_add": _topic_add, "topic_remove": _topic_remove, "agree": _decide("agreed"), "disagree": _decide("disagreed")}


# ---- shell hooks ---------------------------------------------------------------------------
def numbers(store: Store) -> dict:
    return {"value": store.scalar("SELECT COUNT(*) FROM search_findings WHERE status = 'open'"), "label": "to review"}


def today(store: Store) -> list[dict]:
    start = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = store.query("SELECT * FROM search_findings WHERE found_at >= ? ORDER BY found_at DESC, id DESC", (iso(start),))
    return [_row(r) for r in rows]


def queue(store: Store) -> list[dict]:
    """Every finding still waiting on the owner, newest first; Home lists these under Review."""
    rows = store.query("SELECT * FROM search_findings WHERE status = 'open' ORDER BY found_at DESC, id DESC")
    return [_row(r) for r in rows]


def context(store: Store, registry) -> str:
    topics = store.query("SELECT id, kind, text FROM search_topics ORDER BY kind, created_at")
    queue = store.query("SELECT id, kind, title, url FROM search_findings WHERE status = 'open' ORDER BY found_at DESC")
    lines = ["Topics (id, kind, text):"]
    lines += [f"  {t['id']} {t['kind']}: {t['text'][:200]}" for t in topics] or ["  none"]
    lines.append(f"Open findings ({len(queue)}):")
    lines += [f"  #{f['id']} {f['kind']}: {f['title'][:100]} <{f['url']}>" for f in queue] or ["  none"]
    lines.append("Last run: " + (store.cursor("web_search.nightly") or "never"))
    return "\n".join(lines)
