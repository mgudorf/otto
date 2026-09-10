"""Scheduled, read-only LLM work: `per_night` new questions every night, one for each topic that has waited longest.

The queue is never topped up to a size: a night that finds unanswered questions still writes its full count.
"""

from __future__ import annotations

from app.claude import BudgetExceeded
from app.modules.education import questions
from app.runner import Skipped
from app.store import now_iso


async def generate(ctx) -> str:
    store = ctx.store
    topics = questions.waiting_topics(store, ctx.config.education.per_night)
    if not topics:
        return Skipped("no topics")
    try:
        raw = await ctx.run_task(questions.generate_prompt(store, topics))
    except BudgetExceeded as e:
        return Skipped(str(e))
    items = questions.parse_array(raw)
    wanted = {t["id"]: t for t in topics}
    added: list[str] = []
    rejected: list[str] = []
    with ctx.commit(cursor=("education.generate", now_iso())) as conn:
        for it in items:
            try:
                tid = int(it.get("topic_id"))
            except (TypeError, ValueError, AttributeError):
                rejected.append(f"no topic_id: {str(it)[:80]}")
                continue
            t = wanted.get(tid)
            if t is None:
                rejected.append(f"topic {tid} not asked for")
                continue
            err = questions.validate_question(store, tid, it.get("title"), it.get("topic_tag"), it.get("setup_markdown"), it.get("parts"))
            if err:
                rejected.append(f"{t['name']}: {err}")
                continue
            questions.insert_question(conn, tid, it["title"], it["topic_tag"], it["setup_markdown"], it["parts"], t["difficulty"], "nightly", False)
            unbound = questions.unbound_acronyms(it["title"], it["topic_tag"], t["name"], it["setup_markdown"], it["parts"])
            if unbound:
                ctx.log(f"{t['name']}: header acronym(s) not bound in the question body: {', '.join(unbound)}")
            added.append(wanted.pop(tid)["name"])              # one per topic per night
    for r in rejected:
        ctx.log(f"rejected: {r}")
    return f"{len(added)} new question(s)" + (f" for {', '.join(added)}" if added else "") + (f"; {len(rejected)} rejected" if rejected else "")
