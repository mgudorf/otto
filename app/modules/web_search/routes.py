"""Web Search: findings the nightly run queues, decisions the owner records on Home. Every write is a user action through the runner.

No page: Home's Review group and its inspector are the surface; topics are edited through the tools in tools.py.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Body, HTTPException, Request

from app.store import Store, iso, now_iso

router = APIRouter(prefix="/api/web_search")

KINDS = ("money", "work", "learn")
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
    r = _get(store, int(body.get("id", 0)))
    if r["status"] != "open":
        raise HTTPException(409, f"already {r['status']}")

    async def run(ctx):
        return fn(store, body, ctx)

    return await st.runner.run_action(f"web_search.{verb}", "web_search", RESOURCE, run)


def _decide(status: str):
    def fn(store: Store, body: dict, ctx) -> dict:
        r = _get(store, int(body["id"]))
        with ctx.commit() as conn:
            conn.execute("UPDATE search_findings SET status = ?, decided_at = ? WHERE id = ?", (status, now_iso(), r["id"]))
        ctx.event(status, r["title"][:120], ref=str(r["id"]))
        return {"id": r["id"], "status": status}

    return fn


ACTIONS = {"agree": _decide("agreed"), "disagree": _decide("disagreed")}


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
