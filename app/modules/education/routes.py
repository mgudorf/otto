"""Education: questions on the owner's topics, answered on the page; every answer is a turn in the tutor's session, where it is
graded and discussed. The owner completes a quiz once every part is scored. Page actions write through the runner."""

from __future__ import annotations

import json

from fastapi import APIRouter, Body, HTTPException, Request

from app.api import pane_turn
from app.modules.education import grading, questions
from app.modules.education.questions import (
    ACTIVE, DIFFICULTY_MAX, LISTED, RECENT, SELECT, clean_tags, due_count, due_queue, feedback_of, label, open_question, part_title,
    parts_of, question, status_of, tags_of, topic_rows,
)
from app.runner import JobFailed
from app.store import Store, now_iso, tag_key, tags_for

router = APIRouter(prefix="/api/education")

MODULE = "education"
RESOURCE = "education"                                         # page actions
RESOURCE_LLM = "education.llm"                                 # the generate run: serializes with itself, never with page actions
ROW_LIMIT = 200                                                # the completed history one list carries; the client narrows it


def _part_facts(store: Store, ids: list[int]) -> dict[int, dict]:
    """Per question, in one query: how many parts carry an answer, and the part titles the search reads."""
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    rows = store.query(
        "SELECT question_id, SUM(answered_at IS NOT NULL) AS answered, GROUP_CONCAT(COALESCE(title, ''), ' · ') AS titles"
        f" FROM education_question_parts WHERE question_id IN ({marks}) GROUP BY question_id",
        tuple(ids),
    )
    return {r["question_id"]: r for r in rows}


def _owner_tags(q: dict, shared: list[str]) -> list[str]:
    """The owner's tags: the question's own list first, then any the shell wrote to app_tags."""
    own = [t for t in (tag_key(t) for t in tags_of(q)) if t]
    return own + [t for t in shared if t not in own]


def _row(q: dict, tags: list[str], facts: dict | None) -> dict:
    """One ROW. `pct` fills the bar while the question is open, `score` replaces it once the quiz is complete."""
    done = q["completed_at"] is not None
    answered = (facts or {}).get("answered") or 0
    fixed = [tag_key(q["topic"])] + ([tag_key(q["topic_tag"])] if q["topic_tag"] else [])
    return {
        "id": q["id"], "module": MODULE, "title": q["title"], "when": q["completed_at"] or q["created_at"],
        "fixed": fixed, "tags": [t for t in tags if t not in fixed], "snippet": (facts or {}).get("titles") or "",
        "topic": q["topic"], "difficulty": q["difficulty"], "status": status_of(q), "score": q["score"],
        "pct": 100 if done else (round(100 * answered / q["parts"]) if q["parts"] else 0),
    }


def _rows(store: Store, qs: list[dict]) -> list[dict]:
    ids = [q["id"] for q in qs]
    shared, facts = tags_for(store, MODULE, ids), _part_facts(store, ids)
    return [_row(q, _owner_tags(q, shared.get(q["id"], [])), facts.get(q["id"])) for q in qs]


def detail(store: Store, question_id: int) -> dict | None:
    """The item inspector's shape. `text` is self-contained for Home's generic inspector; the page renders definitions,
    premise and prompts as markdown. Rubrics and the tutor's notes never leave the server this way."""
    q = question(store, question_id)
    if q is None:
        return None
    st = status_of(q)
    parts = [
        {"n": p["n"], "label": label(p["n"]), "title": part_title(p), "text": p["text"], "answer": p["answer"], "answered_at": p["answered_at"],
         "verdict": p["verdict"], "score": p["score"], "graded_at": p["graded_at"]}
        for p in parts_of(store, q["id"])
    ]
    actions = []
    if st == "active":
        if parts and all(p["score"] is not None for p in parts):
            actions.append({"verb": "complete", "label": "Complete quiz", "primary": True})
        actions.append({"verb": "delete", "label": "Delete", "confirm": f'Delete "{q["title"]}"?', "removes": True})
    kind = f"{q['topic']} · d{q['difficulty']}" + (f" · {q['score']}" if st == "completed" else "")
    setup = (f"{q['definitions']}\n\n" if q["definitions"] else "") + q["premise"]
    text = f"{q['title']}\n\n{setup}\n\n" + "\n".join(f"({p['label']}) {p['title']}: {p['text']}" for p in parts)
    return {
        **_rows(store, [q])[0], "kind": kind, "text": text,
        "definitions": q["definitions"], "premise": q["premise"], "topic_id": q["topic_id"],
        "source": q["source"], "created_at": q["created_at"], "completed_at": q["completed_at"],
        "parts": parts, "feedback": feedback_of(store, q["id"]), "actions": actions,
    }


# ---- routes -------------------------------------------------------------------------------------
@router.get("/left")
def left(request: Request) -> dict:
    """Every question the page holds, the queue first and the completed history behind it; the chips and the search
    bar narrow it in the browser, so one group carries both slices."""
    store: Store = request.app.state.store
    active = store.query(f"{SELECT} WHERE {LISTED} AND {ACTIVE} ORDER BY q.started_at IS NULL, q.created_at")
    done = store.query(f"{SELECT} WHERE {LISTED} AND NOT ({ACTIVE}) ORDER BY q.completed_at DESC LIMIT ?", (ROW_LIMIT,))
    total = store.scalar(f"SELECT COUNT(*) FROM education_questions q WHERE {LISTED} AND NOT ({ACTIVE})")
    rows = _rows(store, active + done)
    return {"groups": [{"label": "", "count": len(rows), "rows": rows}] if rows else [], "more": total > len(done)}


@router.get("/blank")
def blank(request: Request) -> dict:
    store: Store = request.app.state.store
    return {"due": due_count(store), "topics": topic_rows(store)}


@router.get("/item/{question_id}")
def item_route(request: Request, question_id: int) -> dict:
    """Opening a question on the page makes it the tutor's context: the latest opened_at wins."""
    store: Store = request.app.state.store
    d = item(store, str(question_id))
    store.execute("UPDATE education_questions SET opened_at = ? WHERE id = ?", (now_iso(), question_id))
    return d


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


# The two literal actions come before the generic verb route so their paths win.
@router.post("/action/answer")
async def answer(request: Request, body: dict = Body(default={})) -> dict:
    """Store the owner's answer to one part and hand it to the tutor: one turn in the Education session, where the tutor
    grades it through education_grade and explains. A graded part takes a new answer; the brief carries the earlier grade."""
    st = request.app.state
    store: Store = st.store
    q = _question_for(store, body, ("active",))
    n = int(body.get("n") or 0)
    part = store.one("SELECT * FROM education_question_parts WHERE question_id = ? AND n = ?", (q["id"], n))
    if part is None:
        raise HTTPException(404, "no such part")
    text = (body.get("answer") or "").strip()
    if not text:
        raise HTTPException(400, "empty answer")
    mod = st.registry.modules[MODULE]
    brief = grading.grade_brief(store, q, {**part, "answer": text}, part if part["graded_at"] else None)
    ts = now_iso()
    with store.tx() as conn:                                   # a new answer clears the grade of the old one; the brief carries it
        conn.execute("UPDATE education_questions SET started_at = COALESCE(started_at, ?), opened_at = ?, score = NULL WHERE id = ?", (ts, ts, q["id"]))
        conn.execute(
            "UPDATE education_question_parts SET answer = ?, answered_at = ?, verdict = NULL, score = NULL, note = NULL, graded_at = NULL WHERE question_id = ? AND n = ?",
            (text, ts, q["id"], n),
        )
    shown = f"({label(n)}) {part_title(part)}\n{text}"
    job, sess = pane_turn(st, mod, shown, brief)
    store.event(MODULE, "answered", f"Q{q['id']} ({label(n)}) {part_title(part)[:80]}", ref=str(q["id"]))
    return {"id": q["id"], "n": n, "queued": job.id, "session": sess["id"]}


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
    mod = st.registry.modules[MODULE]

    async def run(ctx):
        raw = await st.claude.oneshot(ctx, mod, prompt)
        items = [it for it in questions.parse_array(raw) if isinstance(it, dict)]
        it = next((it for it in items if str(it.get("topic_id")) == str(t["id"])), None)
        if it is None:
            raise ValueError(f"rejected: the reply names no question for topic {t['id']} {t['name']}")
        fields = (it.get("title"), it.get("topic_tag"), it.get("definitions_markdown"), it.get("premise_markdown"), it.get("parts"))
        err = questions.validate_question(store, t["id"], *fields)
        if err:
            raise ValueError(f"rejected: {err}")
        unbound = questions.unbound_acronyms(fields[0], fields[1], t["name"], fields[2], fields[3], fields[4])
        with ctx.commit() as conn:
            qid = questions.insert_question(conn, t["id"], *fields, t["difficulty"], "session", False)
        warning = ("header acronym(s) not bound in the question body: " + ", ".join(unbound)) if unbound else None
        ctx.event("generated", str(it["title"]).strip()[:120] + (f" (warning: {warning})" if warning else ""), ref=str(qid))
        return {"id": qid, "warning": warning} if warning else {"id": qid}

    try:
        return await st.runner.run_action("education.generate_now", MODULE, RESOURCE_LLM, run)
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

    return await st.runner.run_action(f"education.{verb}", MODULE, RESOURCE, run)


def _complete(store: Store, body: dict):
    q = _question_for(store, body, ("active",))
    parts = parts_of(store, q["id"])
    if not parts or any(p["score"] is None for p in parts):
        raise HTTPException(409, "every part must be graded first")

    def write(ctx) -> dict:
        with ctx.commit() as conn:
            out = grading.complete(conn, ctx.config, q)
        ctx.event("completed", f"Q{q['id']} {q['title'][:100]}: {out['score']}", ref=str(q["id"]))
        return out

    return write


def _delete(store: Store, body: dict):
    q = _question_for(store, body, ("active",))

    def write(ctx) -> dict:
        # Stamped, not dropped: off the page and out of the tutor's reach, but still in the generator's never-repeat list.
        with ctx.commit() as conn:
            conn.execute("UPDATE education_questions SET deleted_at = ? WHERE id = ?", (now_iso(), q["id"]))
        ctx.event("deleted", q["title"][:120], ref=str(q["id"]))
        return {"id": q["id"]}

    return write


def _tags(store: Store, body: dict):
    q = _question_for(store, body, ("active", "completed"))
    try:
        tags = clean_tags(body.get("tags"))
    except ValueError as e:
        raise HTTPException(400, str(e))

    def write(ctx) -> dict:
        with ctx.commit() as conn:
            conn.execute("UPDATE education_questions SET tags = ? WHERE id = ?", (json.dumps(tags), q["id"]))
        return {"id": q["id"], "tags": tags}

    return write


def _add_topic(store: Store, body: dict):
    name = (body.get("name") or "").strip()
    description = (body.get("description") or "").strip() or None
    if not name:
        raise HTTPException(400, "empty name")
    existing = store.one("SELECT * FROM education_topics WHERE name = ? COLLATE NOCASE", (name,))
    if existing and existing["retired_at"] is None:
        raise HTTPException(409, "topic exists")

    def write(ctx) -> dict:
        with ctx.commit() as conn:
            if existing:                                       # a retired topic comes back rather than failing UNIQUE
                conn.execute("UPDATE education_topics SET retired_at = NULL, description = COALESCE(?, description) WHERE id = ?", (description, existing["id"]))
                tid = existing["id"]
            else:
                tid = conn.execute(
                    "INSERT INTO education_topics(name, description, difficulty, created_at) VALUES (?, ?, ?, ?)",
                    (name, description, ctx.config.education.start_difficulty, now_iso()),
                ).lastrowid
        ctx.event("added topic", name, ref=str(tid))
        return {"id": tid}

    return write


def _retire_topic(store: Store, body: dict):
    t = store.one("SELECT * FROM education_topics WHERE id = ? AND retired_at IS NULL", (int(body.get("id") or 0),))
    if t is None:
        raise HTTPException(404, "no such topic")

    def write(ctx) -> dict:
        with ctx.commit() as conn:
            conn.execute("UPDATE education_topics SET retired_at = ? WHERE id = ?", (now_iso(), t["id"]))
        ctx.event("retired topic", t["name"], ref=str(t["id"]))
        return {"id": t["id"]}

    return write


ACTIONS = {"complete": _complete, "delete": _delete, "tags": _tags, "add_topic": _add_topic, "retire_topic": _retire_topic}


# ---- shell hooks ---------------------------------------------------------------------------------
def numbers(store: Store) -> dict:
    return {"value": due_count(store), "label": "due"}


def today(store: Store) -> list[dict]:
    return _rows(store, due_queue(store))


def rows(store: Store, limit: int = ROW_LIMIT) -> list[dict]:
    """Every question the owner still has, the most recently answered or completed first."""
    qs = store.query(f"{SELECT} WHERE {LISTED} ORDER BY COALESCE(q.completed_at, q.created_at) DESC LIMIT ?", (max(1, limit),))
    return _rows(store, qs)


def context(store: Store, registry) -> str:
    lines = [f"Topics (id, name, difficulty of {DIFFICULTY_MAX}, completed/asked, average, recent scores):"]
    for t in topic_rows(store):
        avg = "-" if t["average"] is None else t["average"]
        lines.append(f"  {t['id']} {t['name']}: d{t['difficulty']}, {t['completed']}/{t['asked']}, avg {avg}, recent {' '.join(map(str, t['recent'])) or '-'}")
    if len(lines) == 1:
        lines.append("  none yet; the owner adds topics on the page or asks you to")
    due = due_queue(store)
    lines.append(f"Active: {len(due)} question(s) waiting" + ("; " + "; ".join(f"Q{q['id']} {q['title'][:80]}" for q in due[:RECENT]) if due else ""))
    q = open_question(store)
    if q:
        tag = f", tag: {q['topic_tag']}" if q["topic_tag"] else ""
        tags = f", owner's tags: {', '.join(tags_of(q))}" if tags_of(q) else ""
        lines.append(f"Open on the page: Q{q['id']} \"{q['title']}\" ({q['topic']}, d{q['difficulty']}{tag}, {status_of(q)}{tags}):")
        if q["definitions"]:
            lines.append("  Definitions: " + q["definitions"])
        lines.append("  Premise: " + q["premise"])
        for p in parts_of(store, q["id"]):
            lines.append(f"  ({label(p['n'])}) {part_title(p)}: {p['text']}")
            lines.append(f"      answer: {p['answer']}" if p["answer"] else "      not answered")
            if p["graded_at"]:
                lines.append(f"      graded: {p['verdict']} {p['score']}/100" + (f" — {p['note']}" if p["note"] else ""))
                if p["rubric"]:
                    lines.append(f"      rubric: {p['rubric']}")
            elif p["answered_at"]:
                lines.append("      answered; your grade through education_grade is awaited")
    else:
        lines.append("No question is open on the page. The owner opens one there; a submitted answer reaches you as a turn to grade.")
    last = store.query(f"{SELECT} WHERE q.completed_at IS NOT NULL ORDER BY q.completed_at DESC LIMIT ?", (RECENT,))
    if last:
        lines.append("Last completed: " + "; ".join(f"Q{q['id']} {q['title'][:60]} ({q['topic']}) {q['score']}" for q in last))
    fb = store.query("SELECT f.text, t.name AS topic FROM education_feedback f LEFT JOIN education_topics t ON t.id = f.topic_id ORDER BY f.id DESC LIMIT ?", (RECENT,))
    if fb:
        lines.append("Owner feedback, verbatim: " + "; ".join(f"\"{f['text'][:160]}\"" + (f" ({f['topic']})" if f["topic"] else "") for f in fb))
    return "\n".join(lines)
