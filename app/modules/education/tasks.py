"""Scheduled, read-only LLM work: top the due queue up with one new question per topic that has waited longest."""

from __future__ import annotations

import json

from app.claude import BudgetExceeded
from app.modules.education.tools import insert_question, validate_question
from app.runner import Skipped
from app.store import now_iso

OPEN = "graded_at IS NULL AND skipped_at IS NULL"


def _json_array(raw: str) -> list:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("["):]
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < 0:
        raise ValueError(f"no JSON array in reply: {raw[:200]!r}")
    return json.loads(text[start:end + 1])


def waiting_topics(store, limit: int) -> list[dict]:
    """Active topics that have waited longest for a question, never asked first: breadth over depth."""
    return store.query(
        """SELECT t.*, (SELECT MAX(created_at) FROM questions q WHERE q.topic_id = t.id) AS last_asked
           FROM topics t WHERE t.retired_at IS NULL ORDER BY last_asked IS NOT NULL, last_asked, t.name LIMIT ?""",
        (limit,),
    )


def build_prompt(store, topics: list[dict]) -> str:
    lines = [
        "Write one new question for each topic below. The owner answers later by typing short conceptual answers in a chat.",
        "Rules: plain language that teaches a concept and checks understanding; no algebra or derivations to type; any equation is "
        "introduced inside the premise; 3 to 5 parts, each intimately tied to the premise; use the difficulty given "
        "(1 = intuition in everyday words, 5 = subtle edge cases); never repeat a listed title or a close variant of it.",
        "",
    ]
    general = store.query("SELECT text FROM education_feedback WHERE topic_id IS NULL ORDER BY id DESC LIMIT 5")
    if general:
        lines += ["Owner feedback that applies everywhere, verbatim:", *[f"- \"{f['text'][:300]}\"" for f in general], ""]
    for t in topics:
        lines.append(f"Topic {t['id']}: {t['name']} (difficulty {t['difficulty']})")
        if t["description"]:
            lines.append(f"  What the owner wants: {t['description'][:300]}")
        asked = store.query("SELECT title FROM questions WHERE topic_id = ? ORDER BY created_at DESC", (t["id"],))
        lines.append("  Already asked, never repeat: " + ("; ".join(a["title"] for a in asked) if asked else "nothing yet"))
        last = store.one("SELECT id, title, score FROM questions WHERE topic_id = ? AND graded_at IS NOT NULL ORDER BY graded_at DESC LIMIT 1", (t["id"],))
        if last:
            notes = store.query("SELECT n, score, note FROM question_parts WHERE question_id = ? ORDER BY n", (last["id"],))
            lines.append(
                f"  Last graded, {last['score']}/100 on \"{last['title']}\": "
                + "; ".join(f"part {p['n']} {p['score']}" + (f" ({p['note']})" if p["note"] else "") for p in notes)
            )
        fb = store.query("SELECT text FROM education_feedback WHERE topic_id = ? ORDER BY id DESC LIMIT 5", (t["id"],))
        if fb:
            lines.append("  Owner feedback, verbatim: " + "; ".join(f"\"{f['text'][:200]}\"" for f in fb))
        lines.append("")
    lines += [
        "Reply with only a JSON array, one element per topic:",
        '{"topic_id": <id>, "title": <one line>, "premise": <the setup, with any equation introduced>, "parts": [<3 to 5 questions>], "difficulty": <as given>}',
    ]
    return "\n".join(lines)


async def generate(ctx) -> str:
    store = ctx.store
    open_n = store.scalar(f"SELECT COUNT(*) FROM questions WHERE {OPEN}")
    need = ctx.config.education.queue_size - open_n
    if need <= 0:
        return Skipped(f"queue full: {open_n} due")
    topics = waiting_topics(store, need)
    if not topics:
        return Skipped("no topics")
    try:
        raw = await ctx.run_task(build_prompt(store, topics), tools=("education_questions", "education_question"))
    except BudgetExceeded as e:
        return Skipped(str(e))
    items = _json_array(raw)
    wanted = {t["id"]: t["name"] for t in topics}
    added: list[str] = []
    rejected: list[str] = []
    with ctx.commit(cursor=("education.generate", now_iso())) as conn:
        for it in items:
            try:
                tid = int(it.get("topic_id"))
            except (TypeError, ValueError, AttributeError):
                rejected.append(f"no topic_id: {str(it)[:80]}")
                continue
            if tid not in wanted:
                rejected.append(f"topic {tid} not asked for")
                continue
            err = validate_question(store, tid, it.get("title"), it.get("premise"), it.get("parts"), it.get("difficulty"))
            if err:
                rejected.append(f"{wanted[tid]}: {err}")
                continue
            insert_question(conn, tid, it["title"], it["premise"], it["parts"], it["difficulty"], "nightly", False)
            added.append(wanted.pop(tid))                      # one per topic per night
    for r in rejected:
        ctx.log(f"rejected: {r}")
    return f"{len(added)} new question(s)" + (f" for {', '.join(added)}" if added else "") + (f"; {len(rejected)} rejected" if rejected else "")
