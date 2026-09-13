"""Grading: the tutor grades in the session. prompts/grade.md is the brief a submitted answer sends there, the tutor
writes the grade back through education_grade (the write every grader shares, `grade`), and explains in its reply.
Complete quiz is the owner's press, and the only thing that moves a topic's difficulty."""

from __future__ import annotations

from app.modules.education.questions import DIFFICULTY_MAX, feedback_lines, label, part_title, question, render
from app.store import Store, now_iso

NO_RUBRIC = "(none — grade against the prompt and the setup alone)"   # v0 rows have no rubric
NO_DEFINITIONS = "(none — the premise carries every definition)"      # rows older than v2


def grade_brief(store: Store, q: dict, part: dict, previous: dict | None) -> str:
    """The turn that asks the tutor to grade one answer: the whole question, the rubric, the answer, the earlier attempt if any."""
    t = store.one("SELECT name, description FROM education_topics WHERE id = ?", (q["topic_id"],))
    earlier = "(none: this is the first answer to this part)"
    if previous:
        earlier = (
            f"Scored {previous['score']}/100, {previous['verdict']}. Your note then: {previous['note'] or '-'}\n"
            f"The answer then:\n{previous['answer'] or '-'}"
        )
    return render("grade", {
        "id": str(q["id"]),
        "n": str(part["n"]),
        "label": label(part["n"]),
        "title": q["title"],
        "part_title": part_title(part),
        "topic": t["name"],
        "description": t["description"] or "(none)",
        "difficulty": str(q["difficulty"]),
        "max": str(DIFFICULTY_MAX),
        "definitions": q["definitions"] or NO_DEFINITIONS,
        "premise": q["premise"],
        "prompt": part["text"],
        "rubric": part["rubric"] or NO_RUBRIC,
        "answer": part["answer"],
        "earlier": earlier,
        "feedback": feedback_lines(store, q["topic_id"]),
    })


def verdict_for(score: int) -> str:
    """The tutor grades 0 to 100 without a verdict: full marks is correct, none is incorrect, the rest partial."""
    return "correct" if score >= 100 else "incorrect" if score <= 0 else "partial"


def apply_grade(conn, q: dict, n: int, score: int, note: str | None, verdict: str) -> dict:
    """Score one part on an open connection. Once every part is scored the question's mean is kept; completion is the owner's press."""
    conn.execute(
        "UPDATE education_question_parts SET verdict = ?, score = ?, note = ?, graded_at = ? WHERE question_id = ? AND n = ?",
        (verdict, score, (note or "").strip() or None, now_iso(), q["id"], n),
    )
    out: dict = {"question_id": q["id"], "part": n, "verdict": verdict, "score": score}
    out["remaining"] = conn.execute("SELECT COUNT(*) FROM education_question_parts WHERE question_id = ? AND score IS NULL", (q["id"],)).fetchone()[0]
    if out["remaining"] == 0:
        mean = round(conn.execute("SELECT AVG(score) FROM education_question_parts WHERE question_id = ?", (q["id"],)).fetchone()[0])
        conn.execute("UPDATE education_questions SET score = ? WHERE id = ?", (mean, q["id"]))
        out["question_score"] = mean
    return out


def complete(conn, config, q: dict) -> dict:
    """Close the quiz on an open connection: every part scored, the mean kept, the topic's difficulty moved by the flow band once."""
    remaining = conn.execute("SELECT COUNT(*) FROM education_question_parts WHERE question_id = ? AND score IS NULL", (q["id"],)).fetchone()[0]
    if remaining:
        raise ValueError(f"{remaining} part(s) not graded yet")
    mean = round(conn.execute("SELECT AVG(score) FROM education_question_parts WHERE question_id = ?", (q["id"],)).fetchone()[0])
    conn.execute("UPDATE education_questions SET completed_at = ?, score = ? WHERE id = ?", (now_iso(), mean, q["id"]))
    band = config.education
    d = conn.execute("SELECT difficulty FROM education_topics WHERE id = ?", (q["topic_id"],)).fetchone()[0]
    nd = min(DIFFICULTY_MAX, d + 1) if mean > band.flow_high else max(1, d - 1) if mean < band.flow_low else d
    if nd != d:
        conn.execute("UPDATE education_topics SET difficulty = ? WHERE id = ?", (nd, q["topic_id"]))
    return {"id": q["id"], "score": mean, "topic_difficulty": nd}


def grade(store: Store, question_id, part, score, note) -> dict:
    """The tutor's grade: 0 to 100 and a note for the record, on one part. A completed question's grade may still be revised; its mean follows."""
    q = question(store, int(question_id))
    if q is None:
        return {"error": f"no question {question_id}"}
    row = store.one("SELECT * FROM education_question_parts WHERE question_id = ? AND n = ?", (q["id"], int(part)))
    if row is None:
        return {"error": f"question {question_id} has no part {part}"}
    try:
        s = int(score)
    except (TypeError, ValueError):
        return {"error": "score is 0 to 100"}
    if not 0 <= s <= 100:
        return {"error": "score is 0 to 100"}
    with store.tx() as conn:
        out = apply_grade(conn, q, int(part), s, note, verdict_for(s))
    store.event("education", "graded", f"Q{q['id']} ({label(row['n'])}) {part_title(row)[:80]}: {s}", ref=str(q["id"]))
    return out
