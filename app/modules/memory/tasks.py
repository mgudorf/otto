"""Scheduled, read-only LLM work: propose action items from the recent memories."""

from __future__ import annotations

import json

from app.runner import Skipped
from app.store import days_ago_iso, now_iso


def _json_array(raw: str) -> list:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("["):]
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < 0:
        raise ValueError(f"no JSON array in reply: {raw[:200]!r}")
    return json.loads(text[start:end + 1])


async def suggest(ctx) -> str:
    cfg = ctx.config.memory
    recent = ctx.store.query(
        "SELECT id, kind, text FROM memories WHERE created_at >= ? AND done_at IS NULL ORDER BY created_at",
        (days_ago_iso(cfg.suggest_lookback_days),),
    )
    if not recent:
        return Skipped(f"no memories in the last {cfg.suggest_lookback_days} days")
    # Every prior suggestion, any status: a suggestion is made once, ever.
    existing = [r["text"] for r in ctx.store.query("SELECT text FROM memory_suggestions ORDER BY created_at DESC")]
    prompt = "\n".join([
        f"These are the owner's memories from the last {cfg.suggest_lookback_days} days, as (id, kind, text):",
        *[f"- ({r['id']}, {r['kind']}) {r['text'][:300]}" for r in recent],
        "",
        "Already suggested, never repeat these or close variants:",
        *([f"- {t}" for t in existing] or ["- none"]),
        "",
        "Reply with only a JSON array. Each element: {\"text\": one concrete action item in one sentence, \"memory_ids\": [ids it comes from]}.",
        f"Suggest at most {cfg.suggest_max}, only when the memories clearly call for an action. An empty array is a fine answer.",
    ])
    raw = await ctx.run_task(prompt, tools=("memory_search", "memory_get"))
    items = _json_array(raw)[:cfg.suggest_max]
    added = 0
    with ctx.commit(cursor=("memory.suggest", now_iso())) as conn:
        for it in items:
            text = str(it.get("text", "")).strip()
            if not text:
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO memory_suggestions(text, memory_ids, created_at) VALUES (?, ?, ?)",
                (text, json.dumps([int(i) for i in it.get("memory_ids", []) if str(i).isdigit()]), now_iso()),
            )
            added += cur.rowcount
    return f"{added} new suggestion(s) from {len(items)} proposed"
