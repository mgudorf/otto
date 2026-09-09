"""Grading one answer on the page: prompts/grade.md through oneshot, one turn, then the write every grader shares.

The grader scores 0 to 2 in halves, as the owner's previous project did; the store keeps 0 to 100 (SCALE), so the
flow band, the LEFT bars and the topic table read what they always did. The tutor's education_grade lands here too.
"""

from __future__ import annotations

import json

from app.modules.education.questions import feedback_lines, question, render, status_of
from app.store import Store, now_iso

SCALE = 50                                                     # halves of two -> percent
HALVES = (0, 0.5, 1, 1.5, 2)
VERDICTS = ("correct", "partial", "incorrect")
NO_RUBRIC = "(none — grade against the prompt and the setup alone)"   # v0 rows have no rubric


def grade_prompt(store: Store, q: dict, part: dict) -> str:
    t = store.one("SELECT name, description FROM topics WHERE id = ?", (q["topic_id"],))
    return render("grade", {
        "topic": t["name"],
        "description": t["description"] or "(none)",
        "difficulty": str(q["difficulty"]),
        "setup": q["premise"],
        "prompt": part["text"],
        "rubric": part["rubric"] or NO_RUBRIC,
        "answer": part["answer"],
        "feedback": feedback_lines(store, q["topic_id"]),
    })


def parse_grade(raw: str) -> tuple[str, int, str]:
    """(verdict, score 0 to 100, explanation) from the grader's reply, or ValueError naming what is wrong."""
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < 0:
        raise ValueError(f"no JSON object in reply: {raw[:200]!r}")
    data = json.loads(raw[start:end + 1])
    verdict = data.get("verdict")
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {', '.join(VERDICTS)}, got {verdict!r}")
    score = data.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or score not in HALVES:
        raise ValueError(f"score must be one of {HALVES}, got {score!r}")
    explanation = str(data.get("explanation") or "").strip()
    if not explanation:
        raise ValueError("explanation is required")
    return verdict, int(score * SCALE), explanation


def verdict_for(score: int) -> str:
    """The tutor grades 0 to 100 without a verdict: full marks is correct, none is incorrect, the rest partial."""
    return "correct" if score >= 100 else "incorrect" if score <= 0 else "partial"


def apply_grade(conn, config, q: dict, n: int, score: int, note: str | None, verdict: str) -> dict:
    """Score one part on an open connection. The last part completes the question and moves the topic's difficulty by the flow band, once."""
    ts = now_iso()
    conn.execute(
        "UPDATE question_parts SET verdict = ?, score = ?, note = ?, graded_at = ? WHERE question_id = ? AND n = ?",
        (verdict, score, (note or "").strip() or None, ts, q["id"], n),
    )
    out: dict = {"question_id": q["id"], "part": n, "verdict": verdict, "score": score}
    out["remaining"] = conn.execute("SELECT COUNT(*) FROM question_parts WHERE question_id = ? AND score IS NULL", (q["id"],)).fetchone()[0]
    if out["remaining"] == 0:
        mean = round(conn.execute("SELECT AVG(score) FROM question_parts WHERE question_id = ?", (q["id"],)).fetchone()[0])
        conn.execute("UPDATE questions SET score = ? WHERE id = ?", (mean, q["id"]))
        out["question_score"] = mean
        if q["graded_at"] is None:
            band = config.education
            conn.execute("UPDATE questions SET graded_at = ? WHERE id = ?", (ts, q["id"]))
            d = conn.execute("SELECT difficulty FROM topics WHERE id = ?", (q["topic_id"],)).fetchone()[0]
            nd = min(5, d + 1) if mean > band.flow_high else max(1, d - 1) if mean < band.flow_low else d
            if nd != d:
                conn.execute("UPDATE topics SET difficulty = ? WHERE id = ?", (nd, q["topic_id"]))
            out["topic_difficulty"] = nd
            out["completed"] = True
    return out


def grade(store: Store, config, question_id, part, score, note) -> dict:
    """The tutor's grade: 0 to 100 and the explanation, on a part of a question that was not skipped."""
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
    with store.tx() as conn:
        out = apply_grade(conn, config, q, int(part), s, note, verdict_for(s))
    if out.get("completed"):
        store.event("education", "graded", f"Q{q['id']} {q['title'][:100]}: {out['question_score']}", ref=str(q["id"]))
    return out
