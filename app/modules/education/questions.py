"""The questions data and the generator.

The reads shared by the routes, the tools, the task and the grader live here. The generator is one prompt,
prompts/generate.md: one titled question per listed topic, its definitions (every relation and variable, up front)
and premise in markdown and LaTeX, lettered parts each with a reference title and a hidden rubric, as many as the
setup supports on one theme and never a count. Every writer (the nightly task, a page press, the tutor's hand) passes
validate_question; the two LLM writers also share render, parse_array and unbound_acronyms.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.store import Store, now_iso

PROMPTS = Path(__file__).parent / "prompts"
RECENT = 5                                                     # scores listed per topic, items listed in the agent's state
DIFFICULTY_MAX = 10                                            # 1-2 introduction, 3-5 intro course, 6-8 advanced/masters, 9-10 expert
TAG_CHARS = 40
ACTIVE = "q.completed_at IS NULL"
LISTED = "q.deleted_at IS NULL"                                # a deleted question is off both slices; the row stays, unrepeatable
SELECT = """SELECT q.*, t.name AS topic,
  (SELECT COUNT(*) FROM education_question_parts p WHERE p.question_id = q.id) AS parts,
  (SELECT COUNT(*) FROM education_question_parts p WHERE p.question_id = q.id AND p.score IS NOT NULL) AS graded_parts
FROM education_questions q JOIN education_topics t ON t.id = q.topic_id"""

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


def part_title(p: dict) -> str:
    """The part's reference title; a row older than v2 has none and shows the start of its prompt."""
    if p.get("title"):
        return p["title"]
    words = re.sub(r"\s+", " ", p.get("text") or "").split()
    return " ".join(words[:6]) + ("…" if len(words) > 6 else "")


def tags_of(q: dict) -> list[str]:
    try:
        return [str(t) for t in json.loads(q.get("tags") or "[]")]
    except ValueError:
        return []


def clean_tags(tags) -> list[str]:
    """Trimmed, non-empty, unique, in the order given; anything else is not a tag list."""
    if not isinstance(tags, (list, tuple)):
        raise ValueError("tags must be a list")
    out: list[str] = []
    for t in tags:
        s = str(t or "").strip()[:TAG_CHARS]
        if s and s not in out:
            out.append(s)
    return out


# ---- reads ---------------------------------------------------------------------------------------
def status_of(q: dict) -> str:
    if q.get("deleted_at"):
        return "deleted"
    return "completed" if q["completed_at"] else "active"


def question(store: Store, question_id: int) -> dict | None:
    return store.one(f"{SELECT} WHERE {LISTED} AND q.id = ?", (question_id,))


def parts_of(store: Store, question_id: int) -> list[dict]:
    return store.query("SELECT * FROM education_question_parts WHERE question_id = ? ORDER BY n", (question_id,))


def feedback_of(store: Store, question_id: int) -> list[str]:
    return [f["text"] for f in store.query("SELECT text FROM education_feedback WHERE question_id = ? ORDER BY id", (question_id,))]


def due_queue(store: Store) -> list[dict]:
    """Active questions, the ones with an answer in progress first, then oldest first."""
    return store.query(f"{SELECT} WHERE {LISTED} AND {ACTIVE} ORDER BY q.started_at IS NULL, q.created_at")


def due_count(store: Store) -> int:
    return store.scalar(f"SELECT COUNT(*) FROM education_questions q WHERE {LISTED} AND {ACTIVE}")


def open_question(store: Store) -> dict | None:
    """The question the page opened last, whatever its state: the tutor's context."""
    return store.one(f"{SELECT} WHERE {LISTED} AND q.opened_at IS NOT NULL ORDER BY q.opened_at DESC, q.id DESC LIMIT 1")


def topic_rows(store: Store) -> list[dict]:
    """Progress per topic: difficulty, completed/asked, average, the last RECENT scores, last asked."""
    rows = store.query(
        f"""SELECT t.id, t.name, t.description, t.difficulty,
             (SELECT COUNT(*) FROM education_questions q WHERE q.topic_id = t.id AND {LISTED}) AS asked,
             (SELECT COUNT(*) FROM education_questions q WHERE q.topic_id = t.id AND {LISTED} AND q.completed_at IS NOT NULL) AS completed,
             (SELECT AVG(score) FROM education_questions q WHERE q.topic_id = t.id AND {LISTED} AND q.completed_at IS NOT NULL) AS average,
             (SELECT MAX(created_at) FROM education_questions q WHERE q.topic_id = t.id AND {LISTED}) AS last_asked
           FROM education_topics t WHERE t.retired_at IS NULL ORDER BY t.name"""
    )
    for t in rows:
        t["average"] = None if t["average"] is None else round(t["average"])
        t["recent"] = [
            r["score"] for r in store.query(
                "SELECT score FROM education_questions WHERE topic_id = ? AND deleted_at IS NULL AND completed_at IS NOT NULL"
                " ORDER BY completed_at DESC LIMIT ?", (t["id"], RECENT)
            )
        ]
    return rows


def waiting_topics(store: Store, limit: int) -> list[dict]:
    """Active topics that have waited longest for a question, never asked first: breadth over depth."""
    return store.query(
        f"""SELECT t.*, (SELECT MAX(created_at) FROM education_questions q WHERE q.topic_id = t.id AND {LISTED}) AS last_asked
           FROM education_topics t WHERE t.retired_at IS NULL ORDER BY last_asked IS NOT NULL, last_asked, t.name LIMIT ?""",
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


def _asked_line(store: Store, q: dict) -> str:
    """A title and its part titles: what "never repeat" covers. A deleted one says so; it is why it must not come back."""
    parts = [p["title"] for p in parts_of(store, q["id"]) if p["title"]]
    return q["title"] + (f" ({', '.join(parts)})" if parts else "") + (" [deleted by the owner]" if q["deleted_at"] else "")


def _topic_block(store: Store, t: dict) -> str:
    lines = [f"Topic {t['id']}: {t['name']} — difficulty {t['difficulty']}/{DIFFICULTY_MAX}"]
    if t.get("description"):
        lines.append(f"  What the owner wants: {t['description'][:300]}")
    asked = store.query("SELECT id, title, deleted_at FROM education_questions WHERE topic_id = ? ORDER BY created_at DESC", (t["id"],))
    lines.append("  Already asked, never repeat: " + ("; ".join(_asked_line(store, a) for a in asked) if asked else "nothing yet"))
    last = store.one(
        "SELECT id, title, score FROM education_questions WHERE topic_id = ? AND deleted_at IS NULL AND completed_at IS NOT NULL"
        " ORDER BY completed_at DESC LIMIT 1", (t["id"],)
    )
    if last:
        graded = [p for p in parts_of(store, last["id"]) if p["score"] is not None]
        lines.append(
            f'  Last completed, {last["score"]}/100 on "{last["title"]}": '
            + "; ".join(f"({label(p['n'])}) {part_title(p)}: {p['verdict'] or '-'} {p['score']}" for p in graded)
        )
    fb = store.query("SELECT text FROM education_feedback WHERE topic_id = ? ORDER BY id DESC LIMIT ?", (t["id"], RECENT))
    if fb:
        lines.append("  Owner feedback on this topic, verbatim: " + "; ".join(f'"{f["text"][:200]}"' for f in fb))
    return "\n".join(lines)


def generate_prompt(store: Store, topics: list[dict]) -> str:
    """The generator for these topics: the learner summary, one block per topic, the owner's general feedback."""
    summary = "\n".join(
        f"- {t['name']}: difficulty {t['difficulty']}/{DIFFICULTY_MAX}, {t['completed']}/{t['asked']} completed, "
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
    """Parts as {title, prompt, rubric} with stripped text; anything else becomes an empty field the validator names."""
    out = []
    for p in parts if isinstance(parts, (list, tuple)) else []:
        if isinstance(p, dict):
            out.append({k: str(p.get(k) or "").strip() for k in ("title", "prompt", "rubric")})
        else:
            out.append({"title": "", "prompt": str(p or "").strip(), "rubric": ""})
    return out


def validate_question(store: Store, topic_id, title, topic_tag, definitions, premise, parts) -> str | None:
    """The rules every new question meets, whoever wrote it. Returns the problem, or None."""
    if store.one("SELECT id FROM education_topics WHERE id = ? AND retired_at IS NULL", (topic_id,)) is None:
        return f"no active topic {topic_id}"
    if not isinstance(parts, (list, tuple)):
        return "parts must be a list"
    clean = clean_parts(parts)
    if not clean:
        return "a question needs at least one part"
    for i, p in enumerate(clean, 1):
        if not p["title"] or not p["prompt"] or not p["rubric"]:
            return f"part ({label(i)}) needs a title, a prompt and a rubric"
    if not str(title or "").strip() or not str(topic_tag or "").strip():
        return "title and topic_tag are required"
    if not str(definitions or "").strip() or not str(premise or "").strip():
        return "definitions and premise are required"
    if store.one("SELECT id FROM education_questions WHERE topic_id = ? AND title = ?", (topic_id, str(title).strip())):
        return f"a question titled {str(title).strip()!r} already exists on topic {topic_id}"
    return None


def acronyms_in(text: str | None) -> set[str]:
    out = set()
    for m in ACRONYM.finditer(text or ""):
        a = m.group(1)
        if sum(ch.isupper() for ch in a) >= 2 and a not in ACRONYM_EXCEPTIONS:
            out.add(a)
    return out


def unbound_acronyms(title, topic_tag, topic_name, definitions, premise, parts) -> list[str]:
    """Acronyms of the header (title, tag, topic name) bound nowhere in the setup or a prompt. Sorted, for stable text."""
    header = " ".join([title or "", topic_tag or "", topic_name or ""])
    body = " ".join([definitions or "", premise or ""] + [p["prompt"] for p in clean_parts(parts)])
    return sorted(a for a in acronyms_in(header) if not re.search(rf"\b{re.escape(a)}s?\b", body))


def insert_question(conn, topic_id, title, topic_tag, definitions, premise, parts, difficulty, source: str, opened: bool) -> int:
    """Write one validated question and its parts on an open connection. `opened` makes it the tutor's context at once."""
    ts = now_iso()
    cur = conn.execute(
        "INSERT INTO education_questions(topic_id, title, topic_tag, definitions, premise, difficulty, source, created_at, opened_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (topic_id, str(title).strip(), str(topic_tag).strip(), str(definitions).strip(), str(premise).strip(), int(difficulty), source, ts, ts if opened else None),
    )
    for n, p in enumerate(clean_parts(parts), 1):
        conn.execute(
            "INSERT INTO education_question_parts(question_id, n, title, text, rubric) VALUES (?, ?, ?, ?, ?)", (cur.lastrowid, n, p["title"], p["prompt"], p["rubric"])
        )
    return cur.lastrowid


def add_question(store: Store, topic_id, title, topic_tag, definitions, premise, parts, source: str, opened: bool) -> dict:
    """One validated question at the topic's difficulty: the tutor's path, and the tests'."""
    err = validate_question(store, topic_id, title, topic_tag, definitions, premise, parts)
    if err:
        return {"error": err}
    t = store.one("SELECT name, difficulty FROM education_topics WHERE id = ?", (topic_id,))
    with store.tx() as conn:
        qid = insert_question(conn, topic_id, title, topic_tag, definitions, premise, parts, t["difficulty"], source, opened)
    out = {"id": qid, "parts": len(clean_parts(parts))}
    unbound = unbound_acronyms(title, topic_tag, t["name"], definitions, premise, parts)
    if unbound:
        out["warning"] = "header acronym(s) not bound in the question body: " + ", ".join(unbound)
    return out
