"""MCP tools for the tutor. Read tools go on both servers; write tools on the full server only."""

from __future__ import annotations

from app.config import load
from app.modules.education.grading import grade
from app.modules.education.questions import SELECT, add_question, parts_of, status_of, tags_of, topic_rows
from app.modules.education.routes import detail
from app.store import Store, now_iso

STATUS_SQL = {"active": "q.completed_at IS NULL", "completed": "q.completed_at IS NOT NULL"}


def register(read, full, store: Store, config=None) -> None:
    config = config or load()                                  # the daemon passes none today; this is the config.toml it booted from

    def education_topics() -> list[dict]:
        """Active topics with difficulty (1 to 10: 1-2 a first introduction to the field, 3-5 an introductory university course, 6-8 an advanced undergraduate or masters course, 9-10 expert), questions completed/asked, average score and the last five scores."""
        return topic_rows(store)

    def education_questions(topic_id: int | None = None, status: str | None = None, limit: int = 50) -> list[dict]:
        """Questions newest first: id, topic, title, topic_tag, difficulty, status (active or completed), score, the owner's tags. Check here before writing a question so nothing repeats."""
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
                "id": q["id"], "topic_id": q["topic_id"], "topic": q["topic"], "title": q["title"], "topic_tag": q["topic_tag"],
                "difficulty": q["difficulty"], "status": status_of(q), "score": q["score"], "tags": tags_of(q), "source": q["source"],
                "created_at": q["created_at"], "completed_at": q["completed_at"],
            }
            for q in rows
        ]

    def education_question(id: int) -> dict:
        """One question in full: definitions, premise, each part with its title, prompt, the owner's answer, verdict, score and your note, the rubric once a part is graded, and the owner's feedback on it."""
        d = detail(store, id)
        if not d:
            return {"error": f"no question {id}"}
        rows = {p["n"]: p for p in parts_of(store, id)}
        for p in d["parts"]:
            row = rows[p["n"]]
            p["note"] = row["note"]
            if p["graded_at"] and row["rubric"]:
                p["rubric"] = row["rubric"]
        return d

    def education_feedback(topic_id: int | None = None) -> list[dict]:
        """The owner's feedback lines, verbatim, newest first. topic_id narrows."""
        where, params = ("WHERE f.topic_id = ?", (topic_id,)) if topic_id is not None else ("", ())
        return store.query(
            f"SELECT f.id, f.ts, f.topic_id, t.name AS topic, f.question_id, f.text FROM education_feedback f LEFT JOIN topics t ON t.id = f.topic_id {where} ORDER BY f.id DESC LIMIT 100",
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

    def education_add_question(topic_id: int, title: str, topic_tag: str, definitions: str, premise: str, parts: list[dict]) -> dict:
        """Write a question the owner answers on the page. title: 3 to 8 words naming it, not a question. topic_tag: its facet, 2 to 5 words. definitions: markdown, up front and never inline: for each relation its name in bold, the equation as display LaTeX, then one bullet per variable with its meaning; no answer given away. premise: the scenario the parts draw on, referring to the definitions by name, markdown with LaTeX. parts: {title, prompt, rubric} objects, one per facet the setup genuinely opens and no more (no target count); title 2 to 5 words naming the part, prompt one ask answerable in a few sentences of reasoning (no computation), rubric the expected answer, acceptable variations and common wrong answers, never shown to the owner. It becomes the question in your context at once; point the owner to it on the page."""
        out = add_question(store, topic_id, title, topic_tag, definitions, premise, parts, "session", True)
        if "id" in out:
            store.event("education", "asked", f"(agent) {title.strip()[:120]}", ref=str(out["id"]))
        return out

    def education_grade(question_id: int, part: int, score: int, note: str) -> dict:
        """Record the grade of one part: score 0 to 100 (100 fully correct, 0 no credit) and a note of one or two sentences kept as the record; the owner reads your reply in the pane, not the note. part is its number, (a) is 1. Call it again to revise a grade. Completing the quiz is the owner's button."""
        return grade(store, question_id, part, score, note)

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
            cur = conn.execute("INSERT INTO education_feedback(ts, topic_id, question_id, text) VALUES (?, ?, ?, ?)", (now_iso(), topic_id, question_id, text))
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
