"""MCP tools for the tutor. Read tools go on both servers; write tools on the full server only.

`validate_question`, `insert_question`, `add_question` and `grade` are plain functions, shared with the nightly task and the tests.
"""

from __future__ import annotations

from app.config import load
from app.modules.education.routes import SELECT, detail, question, status_of, topic_rows
from app.store import Store, now_iso

PARTS = (3, 5)                                                 # parts per question, requirement 7
STATUS_SQL = {
    "open": "q.graded_at IS NULL AND q.skipped_at IS NULL AND q.started_at IS NULL",
    "started": "q.graded_at IS NULL AND q.skipped_at IS NULL AND q.started_at IS NOT NULL",
    "graded": "q.graded_at IS NOT NULL",
    "skipped": "q.skipped_at IS NOT NULL",
}


def _clean_parts(parts) -> list[str]:
    return [str(p).strip() for p in (parts or []) if str(p).strip()]


def validate_question(store: Store, topic_id, title, premise, parts, difficulty) -> str | None:
    """The rules every new question meets, nightly or in session. Returns the problem, or None."""
    if store.one("SELECT id FROM topics WHERE id = ? AND retired_at IS NULL", (topic_id,)) is None:
        return f"no active topic {topic_id}"
    n = len(_clean_parts(parts))
    if not PARTS[0] <= n <= PARTS[1]:
        return f"a question has {PARTS[0]} to {PARTS[1]} parts, got {n}"
    if not str(title or "").strip() or not str(premise or "").strip():
        return "title and premise are required"
    try:
        d = int(difficulty)
    except (TypeError, ValueError):
        return "difficulty is 1 to 5"
    if not 1 <= d <= 5:
        return "difficulty is 1 to 5"
    if store.one("SELECT id FROM questions WHERE topic_id = ? AND title = ?", (topic_id, str(title).strip())):
        return f"a question titled {str(title).strip()!r} already exists on topic {topic_id}"
    return None


def insert_question(conn, topic_id, title, premise, parts, difficulty, source: str, start: bool) -> int:
    """Write one validated question and its parts on an open connection. A started one un-starts any other."""
    ts = now_iso()
    if start:
        conn.execute("UPDATE questions SET started_at = NULL WHERE started_at IS NOT NULL AND graded_at IS NULL AND skipped_at IS NULL")
    cur = conn.execute(
        "INSERT INTO questions(topic_id, title, premise, difficulty, source, created_at, started_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (topic_id, str(title).strip(), str(premise).strip(), int(difficulty), source, ts, ts if start else None),
    )
    for n, text in enumerate(_clean_parts(parts), 1):
        conn.execute("INSERT INTO question_parts(question_id, n, text) VALUES (?, ?, ?)", (cur.lastrowid, n, text))
    return cur.lastrowid


def add_question(store: Store, topic_id, title, premise, parts, difficulty, source: str, start: bool) -> dict:
    err = validate_question(store, topic_id, title, premise, parts, difficulty)
    if err:
        return {"error": err}
    with store.tx() as conn:
        qid = insert_question(conn, topic_id, title, premise, parts, difficulty, source, start)
    return {"id": qid, "parts": len(_clean_parts(parts))}


def grade(store: Store, config, question_id, part, score, note) -> dict:
    """Score one part. The last part completes the question and moves the topic's difficulty by the flow band, once."""
    q = question(store, int(question_id))
    if q is None:
        return {"error": f"no question {question_id}"}
    if status_of(q) == "skipped":
        return {"error": f"question {question_id} was skipped"}
    if store.one("SELECT 1 FROM question_parts WHERE question_id = ? AND n = ?", (q["id"], int(part))) is None:
        return {"error": f"question {question_id} has no part {part}"}
    try:
        s = int(score)
    except (TypeError, ValueError):
        return {"error": "score is 0 to 100"}
    if not 0 <= s <= 100:
        return {"error": "score is 0 to 100"}
    band = config.education
    ts = now_iso()
    out: dict = {"question_id": q["id"], "part": int(part), "score": s}
    with store.tx() as conn:
        conn.execute(
            "UPDATE question_parts SET score = ?, note = ?, graded_at = ? WHERE question_id = ? AND n = ?",
            (s, (note or "").strip() or None, ts, q["id"], int(part)),
        )
        out["remaining"] = conn.execute("SELECT COUNT(*) FROM question_parts WHERE question_id = ? AND score IS NULL", (q["id"],)).fetchone()[0]
        if out["remaining"] == 0:
            mean = round(conn.execute("SELECT AVG(score) FROM question_parts WHERE question_id = ?", (q["id"],)).fetchone()[0])
            conn.execute("UPDATE questions SET score = ? WHERE id = ?", (mean, q["id"]))
            out["question_score"] = mean
            if q["graded_at"] is None:
                conn.execute("UPDATE questions SET graded_at = ? WHERE id = ?", (ts, q["id"]))
                d = conn.execute("SELECT difficulty FROM topics WHERE id = ?", (q["topic_id"],)).fetchone()[0]
                nd = min(5, d + 1) if mean > band.flow_high else max(1, d - 1) if mean < band.flow_low else d
                if nd != d:
                    conn.execute("UPDATE topics SET difficulty = ? WHERE id = ?", (nd, q["topic_id"]))
                out["topic_difficulty"] = nd
                out["completed"] = True
    if out.get("completed"):
        store.event("education", "graded", f"Q{q['id']} {q['title'][:100]}: {out['question_score']}", ref=str(q["id"]))
    return out


def register(read, full, store: Store, config=None) -> None:
    config = config or load()                                  # the daemon passes none today; this is the config.toml it booted from

    def education_topics() -> list[dict]:
        """Active topics with difficulty (1 intuition to 5 subtle), questions graded/asked, average score and the last five scores."""
        return topic_rows(store)

    def education_questions(topic_id: int | None = None, status: str | None = None, limit: int = 50) -> list[dict]:
        """Questions newest first: id, topic, title, difficulty, status (open, started, graded, skipped), score. Check here before writing a question so nothing repeats."""
        where, params = [], []
        if topic_id is not None:
            where.append("q.topic_id = ?")
            params.append(topic_id)
        if status:
            if status not in STATUS_SQL:
                return [{"error": f"status must be one of {', '.join(STATUS_SQL)}"}]
            where.append(STATUS_SQL[status])
        sql_where = ("WHERE " + " AND ".join(where)) if where else ""
        rows = store.query(f"{SELECT} {sql_where} ORDER BY q.created_at DESC LIMIT ?", (*params, max(1, min(limit, 200))))
        return [
            {
                "id": q["id"], "topic_id": q["topic_id"], "topic": q["topic"], "title": q["title"], "difficulty": q["difficulty"],
                "status": status_of(q), "score": q["score"], "source": q["source"], "created_at": q["created_at"], "graded_at": q["graded_at"],
            }
            for q in rows
        ]

    def education_question(id: int) -> dict:
        """One question in full: premise, parts with any scores and notes, and the owner's feedback on it."""
        d = detail(store, id)
        return d if d else {"error": f"no question {id}"}

    def education_feedback(topic_id: int | None = None) -> list[dict]:
        """The owner's feedback lines, verbatim, newest first. topic_id narrows."""
        where, params = ("WHERE f.topic_id = ?", (topic_id,)) if topic_id is not None else ("", ())
        return store.query(
            f"SELECT f.id, f.ts, f.topic_id, t.name AS topic, f.question_id, f.text FROM feedback f LEFT JOIN topics t ON t.id = f.topic_id {where} ORDER BY f.id DESC LIMIT 100",
            params,
        )

    def education_add_topic(name: str, description: str | None = None) -> dict:
        """Add a topic, a domain the owner wants to learn, at the starting difficulty. description: one line on what they want from it, optional."""
        name = name.strip()
        if not name:
            return {"error": "empty name"}
        existing = store.one("SELECT * FROM topics WHERE name = ? COLLATE NOCASE", (name,))
        if existing and existing["retired_at"] is None:
            return {"error": f"topic {existing['id']} already exists: {existing['name']}"}
        desc = (description or "").strip() or None
        with store.tx() as conn:
            if existing:
                conn.execute("UPDATE topics SET retired_at = NULL, description = COALESCE(?, description) WHERE id = ?", (desc, existing["id"]))
                tid = existing["id"]
            else:
                tid = conn.execute(
                    "INSERT INTO topics(name, description, difficulty, created_at) VALUES (?, ?, ?, ?)",
                    (name, desc, config.education.start_difficulty, now_iso()),
                ).lastrowid
        store.event("education", "added topic", f"(agent) {name}", ref=str(tid))
        return {"id": tid, "difficulty": config.education.start_difficulty if not existing else existing["difficulty"]}

    def education_add_question(topic_id: int, title: str, premise: str, parts: list[str], difficulty: int) -> dict:
        """Write a question the owner will answer now: a clear premise that introduces any equation, then 3 to 5 parts that each build on it. It starts at once."""
        out = add_question(store, topic_id, title, premise, parts, difficulty, "session", True)
        if "id" in out:
            store.event("education", "asked", f"(agent) {title.strip()[:120]}", ref=str(out["id"]))
        return out

    def education_grade(question_id: int, part: int, score: int, note: str) -> dict:
        """Record the score (0 to 100) for one part with a one-line note on the answer. Grade a part again to revise it. The last part completes the question and tunes the topic's difficulty."""
        return grade(store, config, question_id, part, score, note)

    def education_record_feedback(text: str, topic_id: int | None = None, question_id: int | None = None) -> dict:
        """Store the owner's words about a question, the grading or what they want to learn, unchanged."""
        text = text.strip()
        if not text:
            return {"error": "empty text"}
        if question_id is not None:
            q = store.one("SELECT id, topic_id FROM questions WHERE id = ?", (question_id,))
            if q is None:
                return {"error": f"no question {question_id}"}
            topic_id = q["topic_id"] if topic_id is None else topic_id
        if topic_id is not None and store.one("SELECT id FROM topics WHERE id = ?", (topic_id,)) is None:
            return {"error": f"no topic {topic_id}"}
        with store.tx() as conn:
            cur = conn.execute("INSERT INTO feedback(ts, topic_id, question_id, text) VALUES (?, ?, ?, ?)", (now_iso(), topic_id, question_id, text))
        store.event("education", "feedback", text[:120], ref=str(cur.lastrowid))
        return {"id": cur.lastrowid}

    for server in (read, full):
        server.tool()(education_topics)
        server.tool()(education_questions)
        server.tool()(education_question)
        server.tool()(education_feedback)
    full.tool()(education_add_topic)
    full.tool()(education_add_question)
    full.tool()(education_grade)
    full.tool()(education_record_feedback)
