"""The questions data and the generator.

The reads shared by the routes, the tools, the task and the grader live here. The generator is one prompt,
prompts/generate.md, written for the owner's previous project: one titled question per listed topic, a shared
setup in markdown and LaTeX, lettered parts each with a hidden rubric, as many as the setup supports on one theme
and never a count. Every writer (the nightly task, a page press, the tutor's hand) passes validate_question; the two LLM writers also share render, parse_array and
unbound_acronyms.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.store import Store, now_iso

PROMPTS = Path(__file__).parent / "prompts"
RECENT = 5                                                     # scores listed per topic, items listed in the agent's state
OPEN = "q.graded_at IS NULL AND q.skipped_at IS NULL"
SELECT = """SELECT q.*, t.name AS topic,
  (SELECT COUNT(*) FROM question_parts p WHERE p.question_id = q.id) AS parts,
  (SELECT COUNT(*) FROM question_parts p WHERE p.question_id = q.id AND p.score IS NOT NULL) AS graded_parts
FROM questions q JOIN topics t ON t.id = q.topic_id"""

# Header acronyms: a run of capitals (plural s stripped) in the title, the tag or the topic name must occur in the
# setup or a prompt, or the question names something it never defines. Crude by design; false positives go here.
ACRONYM = re.compile(r"\b([A-Z][A-Z0-9]+)s?\b")
ACRONYM_EXCEPTIONS = {"AI", "ML", "II", "III", "IV", "VI", "VII", "VIII", "IX", "XI", "XII"}


def label(n: int) -> str:
    """(a), (b), ... and past (z) the spreadsheet way, (aa), (ab): no count is imposed on a question."""
    out = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        out = chr(97 + r) + out
    return out


# ---- reads ---------------------------------------------------------------------------------------
def status_of(q: dict) -> str:
    if q["graded_at"]:
        return "graded"
    if q["skipped_at"]:
        return "skipped"
    return "started" if q["started_at"] else "open"


def question(store: Store, question_id: int) -> dict | None:
    return store.one(f"{SELECT} WHERE q.id = ?", (question_id,))


def parts_of(store: Store, question_id: int) -> list[dict]:
    return store.query("SELECT * FROM question_parts WHERE question_id = ? ORDER BY n", (question_id,))


def feedback_of(store: Store, question_id: int) -> list[str]:
    return [f["text"] for f in store.query("SELECT text FROM education_feedback WHERE question_id = ? ORDER BY id", (question_id,))]


def due_queue(store: Store) -> list[dict]:
    return store.query(f"{SELECT} WHERE {OPEN} ORDER BY q.started_at IS NULL, q.created_at")


def due_count(store: Store) -> int:
    return store.scalar(f"SELECT COUNT(*) FROM questions q WHERE {OPEN}")


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


def waiting_topics(store: Store, limit: int) -> list[dict]:
    """Active topics that have waited longest for a question, never asked first: breadth over depth."""
    return store.query(
        """SELECT t.*, (SELECT MAX(created_at) FROM questions q WHERE q.topic_id = t.id) AS last_asked
           FROM topics t WHERE t.retired_at IS NULL ORDER BY last_asked IS NOT NULL, last_asked, t.name LIMIT ?""",
        (limit,),
    )


# ---- the generator -------------------------------------------------------------------------------
def render(name: str, payload: dict) -> str:
    """Fill the {{key}} placeholders of prompts/<name>.md. Not string.Template: the templates hold LaTeX dollars."""
    text = (PROMPTS / f"{name}.md").read_text("utf-8")

    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in payload:
            raise KeyError(f"prompt {name} needs {{{{{key}}}}}")
        value = payload[key]
        return value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=False)

    return re.sub(r"\{\{(\w+)\}\}", sub, text)


def feedback_lines(store: Store, topic_id: int | None = None) -> str:
    """The owner's words, verbatim: the general ones, plus a topic's when asked."""
    where, params = ("WHERE topic_id IS NULL", ()) if topic_id is None else ("WHERE topic_id IS NULL OR topic_id = ?", (topic_id,))
    rows = store.query(f"SELECT text FROM education_feedback {where} ORDER BY id DESC LIMIT ?", (*params, RECENT))
    return "\n".join(f'- "{r["text"][:300]}"' for r in rows) or "(none yet)"


def _topic_block(store: Store, t: dict) -> str:
    lines = [f"Topic {t['id']}: {t['name']} — difficulty {t['difficulty']}/5"]
    if t.get("description"):
        lines.append(f"  What the owner wants: {t['description'][:300]}")
    asked = store.query("SELECT title FROM questions WHERE topic_id = ? ORDER BY created_at DESC", (t["id"],))
    lines.append("  Already asked, never repeat: " + ("; ".join(a["title"] for a in asked) if asked else "nothing yet"))
    last = store.one(
        "SELECT id, title, score FROM questions WHERE topic_id = ? AND graded_at IS NOT NULL ORDER BY graded_at DESC LIMIT 1", (t["id"],)
    )
    if last:
        graded = [p for p in parts_of(store, last["id"]) if p["score"] is not None]
        lines.append(
            f'  Last graded, {last["score"]}/100 on "{last["title"]}": '
            + "; ".join(f"({label(p['n'])}) {p['verdict'] or '-'} {p['score']}" for p in graded)
        )
    fb = store.query("SELECT text FROM education_feedback WHERE topic_id = ? ORDER BY id DESC LIMIT ?", (t["id"], RECENT))
    if fb:
        lines.append("  Owner feedback on this topic, verbatim: " + "; ".join(f'"{f["text"][:200]}"' for f in fb))
    return "\n".join(lines)


def generate_prompt(store: Store, topics: list[dict]) -> str:
    """The generator for these topics: the learner summary, one block per topic, the owner's general feedback."""
    summary = "\n".join(
        f"- {t['name']}: difficulty {t['difficulty']}/5, {t['graded']}/{t['asked']} graded, "
        f"average {'-' if t['average'] is None else t['average']}, recent {' '.join(map(str, t['recent'])) or '-'}"
        for t in topic_rows(store)
    ) or "(no topics yet)"
    return render("generate", {
        "summary": summary,
        "topics": "\n\n".join(_topic_block(store, t) for t in topics),
        "feedback": feedback_lines(store),
    })


def parse_array(raw: str) -> list:
    """The generator's reply as a list, tolerating fences and prose around the array."""
    start, end = raw.find("["), raw.rfind("]")
    if start < 0 or end < 0:
        raise ValueError(f"no JSON array in reply: {raw[:200]!r}")
    data = json.loads(raw[start:end + 1])
    if not isinstance(data, list):
        raise ValueError("reply is not an array")
    return data


def clean_parts(parts) -> list[dict]:
    """Parts as {prompt, rubric} with stripped text; anything else becomes an empty field the validator names."""
    out = []
    for p in parts if isinstance(parts, (list, tuple)) else []:
        if isinstance(p, dict):
            out.append({"prompt": str(p.get("prompt") or "").strip(), "rubric": str(p.get("rubric") or "").strip()})
        else:
            out.append({"prompt": str(p or "").strip(), "rubric": ""})
    return out


def validate_question(store: Store, topic_id, title, topic_tag, setup, parts) -> str | None:
    """The rules every new question meets, whoever wrote it. Returns the problem, or None."""
    if store.one("SELECT id FROM topics WHERE id = ? AND retired_at IS NULL", (topic_id,)) is None:
        return f"no active topic {topic_id}"
    if not isinstance(parts, (list, tuple)):
        return "parts must be a list"
    clean = clean_parts(parts)
    if not clean:
        return "a question needs at least one part"
    for i, p in enumerate(clean, 1):
        if not p["prompt"] or not p["rubric"]:
            return f"part ({label(i)}) needs a prompt and a rubric"
    if not str(title or "").strip() or not str(topic_tag or "").strip() or not str(setup or "").strip():
        return "title, topic_tag and setup are required"
    if store.one("SELECT id FROM questions WHERE topic_id = ? AND title = ?", (topic_id, str(title).strip())):
        return f"a question titled {str(title).strip()!r} already exists on topic {topic_id}"
    return None


def acronyms_in(text: str | None) -> set[str]:
    out = set()
    for m in ACRONYM.finditer(text or ""):
        a = m.group(1)
        if sum(ch.isupper() for ch in a) >= 2 and a not in ACRONYM_EXCEPTIONS:
            out.add(a)
    return out


def unbound_acronyms(title, topic_tag, topic_name, setup, parts) -> list[str]:
    """Acronyms of the header (title, tag, topic name) bound nowhere in the setup or a prompt. Sorted, for stable text."""
    header = " ".join([title or "", topic_tag or "", topic_name or ""])
    body = " ".join([setup or ""] + [p["prompt"] for p in clean_parts(parts)])
    return sorted(a for a in acronyms_in(header) if not re.search(rf"\b{re.escape(a)}s?\b", body))


def insert_question(conn, topic_id, title, topic_tag, setup, parts, difficulty, source: str, start: bool) -> int:
    """Write one validated question and its parts on an open connection. A started one un-starts any other."""
    ts = now_iso()
    if start:
        conn.execute("UPDATE questions SET started_at = NULL WHERE started_at IS NOT NULL AND graded_at IS NULL AND skipped_at IS NULL")
    cur = conn.execute(
        "INSERT INTO questions(topic_id, title, topic_tag, premise, difficulty, source, created_at, started_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (topic_id, str(title).strip(), str(topic_tag).strip(), str(setup).strip(), int(difficulty), source, ts, ts if start else None),
    )
    for n, p in enumerate(clean_parts(parts), 1):
        conn.execute("INSERT INTO question_parts(question_id, n, text, rubric) VALUES (?, ?, ?, ?)", (cur.lastrowid, n, p["prompt"], p["rubric"]))
    return cur.lastrowid


def add_question(store: Store, topic_id, title, topic_tag, setup, parts, source: str, start: bool) -> dict:
    """One validated question at the topic's difficulty: the tutor's path, and the tests'."""
    err = validate_question(store, topic_id, title, topic_tag, setup, parts)
    if err:
        return {"error": err}
    t = store.one("SELECT name, difficulty FROM topics WHERE id = ?", (topic_id,))
    with store.tx() as conn:
        qid = insert_question(conn, topic_id, title, topic_tag, setup, parts, t["difficulty"], source, start)
    out = {"id": qid, "parts": len(clean_parts(parts))}
    unbound = unbound_acronyms(title, topic_tag, t["name"], setup, parts)
    if unbound:
        out["warning"] = "header acronym(s) not bound in the question body: " + ", ".join(unbound)
    return out
