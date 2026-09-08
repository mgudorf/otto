"""Education: a queue of conceptual questions per topic, graded in the tutor session. Page actions write through the runner."""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request

from app.store import Store, now_iso, parse

router = APIRouter(prefix="/api/education")

RESOURCE = "education"
RECENT = 5                                                     # scores listed per topic, items listed in the agent's state
OPEN = "q.graded_at IS NULL AND q.skipped_at IS NULL"
SELECT = """SELECT q.*, t.name AS topic,
  (SELECT COUNT(*) FROM question_parts p WHERE p.question_id = q.id) AS parts,
  (SELECT COUNT(*) FROM question_parts p WHERE p.question_id = q.id AND p.score IS NOT NULL) AS graded_parts
FROM questions q JOIN topics t ON t.id = q.topic_id"""


def status_of(q: dict) -> str:
    if q["graded_at"]:
        return "graded"
    if q["skipped_at"]:
        return "skipped"
    return "started" if q["started_at"] else "open"


def _row(q: dict) -> dict:
    st = status_of(q)
    if st in ("graded", "skipped"):
        pct, stamp = q["score"] or 0, q["graded_at"] or q["skipped_at"]
    else:
        pct, stamp = (round(100 * q["graded_parts"] / q["parts"]) if q["parts"] else 0), q["created_at"]
    return {"id": q["id"], "module": "education", "text": q["title"], "stamp": stamp, "leading": {"pct": pct}, "done": st == "skipped"}


def _day_label(ts: str) -> str:
    return parse(ts).astimezone().strftime("%d %b")


def _group_by_day(rows: list[dict]) -> list[dict]:
    groups: list[dict] = []
    for q in rows:
        label = _day_label(q["graded_at"] or q["skipped_at"])
        if not groups or groups[-1]["label"] != label:
            groups.append({"label": label, "count": 0, "rows": []})
        groups[-1]["rows"].append(_row(q))
        groups[-1]["count"] += 1
    return groups


# ---- reads shared with tools.py ----------------------------------------------------------------
def due_queue(store: Store) -> list[dict]:
    return store.query(f"{SELECT} WHERE {OPEN} ORDER BY q.started_at IS NULL, q.created_at")


def due_count(store: Store) -> int:
    return store.scalar(f"SELECT COUNT(*) FROM questions q WHERE {OPEN}")


def question(store: Store, question_id: int) -> dict | None:
    return store.one(f"{SELECT} WHERE q.id = ?", (question_id,))


def parts_of(store: Store, question_id: int) -> list[dict]:
    return store.query("SELECT n, text, score, note FROM question_parts WHERE question_id = ? ORDER BY n", (question_id,))


def feedback_of(store: Store, question_id: int) -> list[str]:
    return [f["text"] for f in store.query("SELECT text FROM feedback WHERE question_id = ? ORDER BY id", (question_id,))]


def topic_rows(store: Store) -> list[dict]:
    """Progress per topic: difficulty, graded/asked, average, the last RECENT scores, last asked."""
    rows = store.query(
        """SELECT t.id, t.name, t.description, t.difficulty,
             (SELECT COUNT(*) FROM questions q WHERE q.topic_id = t.id) AS asked,
             (SELECT COUNT(*) FROM questions q WHERE q.topic_id = t.id AND q.graded_at IS NOT NULL) AS graded,
             (SELECT AVG(score) FROM questions q WHERE q.topic_id = t.id AND q.graded_at IS NOT NULL) AS average,
             (SELECT MAX(created_at) FROM questions q WHERE q.topic_id = t.id) AS last_asked
           FROM topics t WHERE t.retired_at IS NULL ORDER BY t.name"""
    )
    for t in rows:
        t["average"] = None if t["average"] is None else round(t["average"])
        t["recent"] = [
            r["score"] for r in store.query(
                "SELECT score FROM questions WHERE topic_id = ? AND graded_at IS NOT NULL ORDER BY graded_at DESC LIMIT ?", (t["id"], RECENT)
            )
        ]
    return rows


def detail(store: Store, question_id: int) -> dict | None:
    """The item inspector's shape. `text` is self-contained for Home's generic inspector; the page uses premise and parts."""
    q = question(store, question_id)
    if q is None:
        return None
    st = status_of(q)
    parts = parts_of(store, q["id"])
    actions = []
    if st == "open":
        actions.append({"verb": "start", "label": "Start", "primary": True})
    if st in ("open", "started"):
        actions.append({"verb": "skip", "label": "Skip"})
    kind = f"{q['topic']} · d{q['difficulty']}" + (f" · {q['score']}" if st == "graded" else "")
    text = f"{q['title']}\n\n{q['premise']}\n\n" + "\n".join(f"{p['n']}. {p['text']}" for p in parts)
    return {
        "id": q["id"], "module": "education", "kind": kind, "title": q["title"], "text": text, "premise": q["premise"],
        "topic_id": q["topic_id"], "topic": q["topic"], "difficulty": q["difficulty"], "source": q["source"],
        "created_at": q["created_at"], "status": st, "score": q["score"], "parts": parts,
        "feedback": feedback_of(store, q["id"]), "actions": actions,
    }


# ---- routes -------------------------------------------------------------------------------------
@router.get("/left")
def left(request: Request, query: str = "", page: int = 0) -> dict:
    store: Store = request.app.state.store
    size = int(store.setting("ui.page_size"))
    limit = size * (page + 1)
    where, params = "", ()
    if query.strip():
        where, params = " AND (q.title LIKE ? OR q.premise LIKE ?)", (f"%{query.strip()}%",) * 2
    due = store.query(f"{SELECT} WHERE {OPEN}{where} ORDER BY q.started_at IS NULL, q.created_at", params)
    total = store.scalar(f"SELECT COUNT(*) FROM questions q WHERE NOT ({OPEN}){where}", params)
    history = store.query(
        f"{SELECT} WHERE NOT ({OPEN}){where} ORDER BY COALESCE(q.graded_at, q.skipped_at) DESC LIMIT ?", (*params, limit)
    )
    groups = [{"label": "due", "count": len(due), "rows": [_row(q) for q in due]}] if due else []
    return {"groups": groups + _group_by_day(history), "showing": f"{min(limit, total)} / {total}", "more": total > limit}


@router.get("/blank")
def blank(request: Request) -> dict:
    store: Store = request.app.state.store
    return {"due": due_count(store), "topics": topic_rows(store)}


@router.get("/item/{question_id}")
def item_route(request: Request, question_id: int) -> dict:
    return item(request.app.state.store, str(question_id))


def item(store: Store, question_id: str) -> dict:
    d = detail(store, int(question_id))
    if d is None:
        raise HTTPException(404, "no such question")
    return d


@router.post("/action/{verb}")
async def action(request: Request, verb: str, body: dict = Body(default={})) -> dict:
    st = request.app.state
    fn = ACTIONS.get(verb)
    if fn is None:
        raise HTTPException(404, f"unknown action {verb}")
    write = fn(st.store, body)                                 # validates now: bad input is a 4xx, never a failed job

    async def run(ctx):
        return write(ctx)

    return await st.runner.run_action(f"education.{verb}", "education", RESOURCE, run)


def _question_for(store: Store, body: dict, allowed: tuple[str, ...]) -> dict:
    q = question(store, int(body.get("id") or 0))
    if q is None:
        raise HTTPException(404, "no such question")
    if status_of(q) not in allowed:
        raise HTTPException(409, f"question is {status_of(q)}")
    return q


def _start(store: Store, body: dict):
    q = _question_for(store, body, ("open", "started"))

    def write(ctx) -> dict:
        with ctx.commit() as conn:
            conn.execute("UPDATE questions SET started_at = NULL WHERE started_at IS NOT NULL AND graded_at IS NULL AND skipped_at IS NULL")
            conn.execute("UPDATE questions SET started_at = ? WHERE id = ?", (q["started_at"] or now_iso(), q["id"]))
        if not q["started_at"]:
            ctx.event("started", q["title"][:120], ref=str(q["id"]))
        return {"id": q["id"]}

    return write


def _skip(store: Store, body: dict):
    q = _question_for(store, body, ("open", "started"))

    def write(ctx) -> dict:
        with ctx.commit() as conn:
            conn.execute("UPDATE questions SET skipped_at = ? WHERE id = ?", (now_iso(), q["id"]))
        ctx.event("skipped", q["title"][:120], ref=str(q["id"]))
        return {"id": q["id"]}

    return write


def _add_topic(store: Store, body: dict):
    name = (body.get("name") or "").strip()
    description = (body.get("description") or "").strip() or None
    if not name:
        raise HTTPException(400, "empty name")
    existing = store.one("SELECT * FROM topics WHERE name = ? COLLATE NOCASE", (name,))
    if existing and existing["retired_at"] is None:
        raise HTTPException(409, "topic exists")

    def write(ctx) -> dict:
        with ctx.commit() as conn:
            if existing:                                       # a retired topic comes back rather than failing UNIQUE
                conn.execute("UPDATE topics SET retired_at = NULL, description = COALESCE(?, description) WHERE id = ?", (description, existing["id"]))
                tid = existing["id"]
            else:
                tid = conn.execute(
                    "INSERT INTO topics(name, description, difficulty, created_at) VALUES (?, ?, ?, ?)",
                    (name, description, ctx.config.education.start_difficulty, now_iso()),
                ).lastrowid
        ctx.event("added topic", name, ref=str(tid))
        return {"id": tid}

    return write


def _retire_topic(store: Store, body: dict):
    t = store.one("SELECT * FROM topics WHERE id = ? AND retired_at IS NULL", (int(body.get("id") or 0),))
    if t is None:
        raise HTTPException(404, "no such topic")

    def write(ctx) -> dict:
        with ctx.commit() as conn:
            conn.execute("UPDATE topics SET retired_at = ? WHERE id = ?", (now_iso(), t["id"]))
        ctx.event("retired topic", t["name"], ref=str(t["id"]))
        return {"id": t["id"]}

    return write


ACTIONS = {"start": _start, "skip": _skip, "add_topic": _add_topic, "retire_topic": _retire_topic}


# ---- shell hooks ---------------------------------------------------------------------------------
def numbers(store: Store) -> dict:
    return {"value": due_count(store), "label": "due"}


def today(store: Store) -> list[dict]:
    return [_row(q) for q in due_queue(store)]


def context(store: Store, registry) -> str:
    lines = ["Topics (id, name, difficulty, graded/asked, average, recent scores):"]
    for t in topic_rows(store):
        avg = "-" if t["average"] is None else t["average"]
        lines.append(f"  {t['id']} {t['name']}: d{t['difficulty']}, {t['graded']}/{t['asked']}, avg {avg}, recent {' '.join(map(str, t['recent'])) or '-'}")
    if len(lines) == 1:
        lines.append("  none yet; the owner adds topics on the page or asks you to")
    due = due_queue(store)
    lines.append(f"Due: {len(due)} question(s) waiting" + ("; " + "; ".join(f"Q{q['id']} {q['title'][:80]}" for q in due[:RECENT]) if due else ""))
    started = next((q for q in due if q["started_at"]), None)
    if started:
        lines.append(f"Started question Q{started['id']} ({started['topic']}, d{started['difficulty']}): {started['title']}")
        lines.append("  Premise: " + started["premise"])
        for p in parts_of(store, started["id"]):
            graded = f" -> {p['score']}/100" + (f": {p['note']}" if p["note"] else "") if p["score"] is not None else " -> not graded"
            lines.append(f"  {p['n']}. {p['text']}{graded}")
    else:
        lines.append("No question is started. The owner starts one from the page, or asks you for a new one.")
    last = store.query(f"{SELECT} WHERE q.graded_at IS NOT NULL ORDER BY q.graded_at DESC LIMIT ?", (RECENT,))
    if last:
        lines.append("Last graded: " + "; ".join(f"Q{q['id']} {q['title'][:60]} ({q['topic']}) {q['score']}" for q in last))
    fb = store.query("SELECT f.text, t.name AS topic FROM feedback f LEFT JOIN topics t ON t.id = f.topic_id ORDER BY f.id DESC LIMIT ?", (RECENT,))
    if fb:
        lines.append("Owner feedback, verbatim: " + "; ".join(f"\"{f['text'][:160]}\"" + (f" ({f['topic']})" if f["topic"] else "") for f in fb))
    return "\n".join(lines)
