"""Education: questions on the owner's topics, answered on the page and graded through oneshot. Page actions write through the runner."""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request

from app.modules.education import grading, questions
from app.modules.education.questions import (
    OPEN, RECENT, SELECT, due_count, due_queue, feedback_of, label, parts_of, question, status_of, topic_rows,
)
from app.runner import JobFailed
from app.store import Store, now_iso, parse

router = APIRouter(prefix="/api/education")

RESOURCE = "education"                                         # page actions
RESOURCE_LLM = "education.llm"                                 # the generate and grade runs: they serialize with each other, never with page actions


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
        day = _day_label(q["graded_at"] or q["skipped_at"])
        if not groups or groups[-1]["label"] != day:
            groups.append({"label": day, "count": 0, "rows": []})
        groups[-1]["rows"].append(_row(q))
        groups[-1]["count"] += 1
    return groups


def detail(store: Store, question_id: int) -> dict | None:
    """The item inspector's shape. `text` is self-contained for Home's generic inspector; the page renders setup and parts as markdown. Rubrics never leave the server."""
    q = question(store, question_id)
    if q is None:
        return None
    st = status_of(q)
    parts = [
        {"n": p["n"], "label": label(p["n"]), "text": p["text"], "answer": p["answer"], "answered_at": p["answered_at"],
         "verdict": p["verdict"], "score": p["score"], "note": p["note"], "graded_at": p["graded_at"]}
        for p in parts_of(store, q["id"])
    ]
    actions = []
    if st == "open":
        actions.append({"verb": "start", "label": "Start", "primary": True})
    if st in ("open", "started"):
        actions.append({"verb": "skip", "label": "Skip"})
    kind = f"{q['topic']} · d{q['difficulty']}" + (f" · {q['score']}" if st == "graded" else "")
    text = f"{q['title']}\n\n{q['premise']}\n\n" + "\n".join(f"({p['label']}) {p['text']}" for p in parts)
    return {
        "id": q["id"], "module": "education", "kind": kind, "title": q["title"], "topic_tag": q["topic_tag"], "text": text,
        "setup": q["premise"], "topic_id": q["topic_id"], "topic": q["topic"], "difficulty": q["difficulty"], "source": q["source"],
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


def _question_for(store: Store, body: dict, allowed: tuple[str, ...]) -> dict:
    q = question(store, int(body.get("id") or 0))
    if q is None:
        raise HTTPException(404, "no such question")
    if status_of(q) not in allowed:
        raise HTTPException(409, f"question is {status_of(q)}")
    return q


def _reason(e: JobFailed) -> str:
    lines = [line for line in str(e).strip().splitlines() if line.strip()]
    return (lines[-1] if lines else "failed")[:300]


# The two LLM actions come before the generic verb route so their literal paths win.
@router.post("/action/answer")
async def answer(request: Request, body: dict = Body(default={})) -> dict:
    """Store the owner's answer to one part, start its question, and grade it: one oneshot run, awaited."""
    st = request.app.state
    store: Store = st.store
    q = _question_for(store, body, ("open", "started"))
    n = int(body.get("n") or 0)
    part = store.one("SELECT * FROM question_parts WHERE question_id = ? AND n = ?", (q["id"], n))
    if part is None:
        raise HTTPException(404, "no such part")
    if part["graded_at"]:
        raise HTTPException(409, "part is graded")
    text = (body.get("answer") or "").strip()
    if not text:
        raise HTTPException(400, "empty answer")
    ts = now_iso()
    with store.tx() as conn:
        conn.execute(
            "UPDATE questions SET started_at = NULL WHERE started_at IS NOT NULL AND graded_at IS NULL AND skipped_at IS NULL AND id != ?", (q["id"],)
        )
        conn.execute("UPDATE questions SET started_at = COALESCE(started_at, ?) WHERE id = ?", (ts, q["id"]))
        conn.execute("UPDATE question_parts SET answer = ?, answered_at = ? WHERE question_id = ? AND n = ?", (text, ts, q["id"], n))
    mod = st.registry.modules["education"]

    async def run(ctx):
        fresh = question(store, q["id"])
        if fresh is None or fresh["skipped_at"]:
            raise ValueError("the question was skipped")
        raw = await st.claude.oneshot(ctx, mod, grading.grade_prompt(store, fresh, {**part, "answer": text}))
        verdict, score, explanation = grading.parse_grade(raw)
        with ctx.commit() as conn:
            out = grading.apply_grade(conn, ctx.config, fresh, n, score, explanation, verdict)
        if out.get("completed"):
            ctx.event("graded", f"Q{q['id']} {q['title'][:100]}: {out['question_score']}", ref=str(q["id"]))
        return {"id": q["id"], "n": n, "verdict": verdict, "score": score}

    try:
        return await st.runner.run_action("education.grade", "education", RESOURCE_LLM, run)
    except JobFailed as e:
        raise HTTPException(502, _reason(e))


@router.post("/action/generate")
async def generate_now(request: Request, body: dict = Body(default={})) -> dict:
    """One question on the topic that has waited longest, through the generator the nightly run uses; awaited."""
    st = request.app.state
    store: Store = st.store
    topics = questions.waiting_topics(store, 1)
    if not topics:
        raise HTTPException(409, "no active topic")
    t = topics[0]
    prompt = questions.generate_prompt(store, topics)
    mod = st.registry.modules["education"]

    async def run(ctx):
        raw = await st.claude.oneshot(ctx, mod, prompt)
        items = [it for it in questions.parse_array(raw) if isinstance(it, dict)]
        it = next((it for it in items if str(it.get("topic_id")) == str(t["id"])), items[0] if items else {})
        err = questions.validate_question(store, t["id"], it.get("title"), it.get("topic_tag"), it.get("setup_markdown"), it.get("parts"))
        if err:
            raise ValueError(f"rejected: {err}")
        unbound = questions.unbound_acronyms(it["title"], it["topic_tag"], t["name"], it["setup_markdown"], it["parts"])
        with ctx.commit() as conn:
            qid = questions.insert_question(conn, t["id"], it["title"], it["topic_tag"], it["setup_markdown"], it["parts"], t["difficulty"], "session", False)
        warning = ("header acronym(s) not bound in the question body: " + ", ".join(unbound)) if unbound else None
        ctx.event("generated", str(it["title"]).strip()[:120] + (f" (warning: {warning})" if warning else ""), ref=str(qid))
        return {"id": qid, "warning": warning} if warning else {"id": qid}

    try:
        return await st.runner.run_action("education.generate_now", "education", RESOURCE_LLM, run)
    except JobFailed as e:
        raise HTTPException(502, _reason(e))


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
        tag = f", tag: {started['topic_tag']}" if started["topic_tag"] else ""
        lines.append(f"Started question Q{started['id']} \"{started['title']}\" ({started['topic']}, d{started['difficulty']}{tag}):")
        lines.append("  Setup: " + started["premise"])
        for p in parts_of(store, started["id"]):
            lines.append(f"  ({label(p['n'])}) {p['text']}")
            lines.append(f"      answer: {p['answer']}" if p["answer"] else "      not answered")
            if p["graded_at"]:
                lines.append(f"      graded: {p['verdict']} {p['score']}/100" + (f" — {p['note']}" if p["note"] else ""))
                if p["rubric"]:
                    lines.append(f"      rubric: {p['rubric']}")
    else:
        lines.append("No question is started. The owner answers on the page; a submitted answer starts its question.")
    last = store.query(f"{SELECT} WHERE q.graded_at IS NOT NULL ORDER BY q.graded_at DESC LIMIT ?", (RECENT,))
    if last:
        lines.append("Last graded: " + "; ".join(f"Q{q['id']} {q['title'][:60]} ({q['topic']}) {q['score']}" for q in last))
    fb = store.query("SELECT f.text, t.name AS topic FROM education_feedback f LEFT JOIN topics t ON t.id = f.topic_id ORDER BY f.id DESC LIMIT ?", (RECENT,))
    if fb:
        lines.append("Owner feedback, verbatim: " + "; ".join(f"\"{f['text'][:160]}\"" + (f" ({f['topic']})" if f["topic"] else "") for f in fb))
    return "\n".join(lines)
