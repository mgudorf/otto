"""One nightly, read-only web search over the owner's topics. Findings queue for the owner's yes or no."""

from __future__ import annotations

import json

from app.runner import Skipped
from app.store import now_iso

KIND_MEANS = {
    "money": "investment, sector and legislation news",
    "work": "new techniques, algorithms and research for the owner's work and career",
    "learn": "topics the owner is learning and sources of questions about them",
}


def _json_array(raw: str) -> list:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("["):]
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < 0:
        raise ValueError(f"no JSON array in reply: {raw[:200]!r}")
    return json.loads(text[start:end + 1])


async def nightly(ctx) -> str:
    topics = ctx.store.query("SELECT id, kind, text FROM search_topics ORDER BY kind, created_at")
    if not topics:
        return Skipped("no topics")
    cap = ctx.config.web_search.max_findings
    seen = ctx.store.query("SELECT url, title, status FROM search_findings ORDER BY found_at DESC LIMIT 100")
    prompt = "\n".join([
        "The owner's search topics, as (topic_id, kind, text). Kinds: " + "; ".join(f"{k} = {v}" for k, v in KIND_MEANS.items()) + ".",
        *[f"- ({t['id']}, {t['kind']}) {t['text'][:300]}" for t in topics],
        "",
        "Already found (status, url, title). Never repeat a url; agreed ones show what the owner values, disagreed ones what to avoid:",
        *([f"- ({s['status']}) {s['url']} {s['title'][:100]}" for s in seen] or ["- none"]),
        "",
        f"Use WebSearch to find up to {cap} new pages, published recently, that serve these topics.",
        "Reply with only a JSON array. Each element: {\"topic_id\": the topic it serves, \"title\": the page title, \"url\": the page, \"summary\": two sentences on why it matters to the owner}.",
        "An empty array is a fine answer when nothing new turned up.",
    ])
    raw = await ctx.run_task(prompt)
    items = _json_array(raw)
    kinds = {t["id"]: t["kind"] for t in topics}
    ts = now_iso()
    added: list[tuple[int, str]] = []
    with ctx.commit(cursor=("web_search.nightly", ts)) as conn:
        for it in items:
            title = str(it.get("title", "")).strip()
            url = str(it.get("url", "")).strip()
            summary = str(it.get("summary", "")).strip()
            topic_id = it.get("topic_id")
            topic_id = int(topic_id) if str(topic_id).isdigit() else None
            if not title or not url or topic_id not in kinds:
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO search_findings(topic_id, kind, title, url, summary, found_at) VALUES (?, ?, ?, ?, ?, ?)",
                (topic_id, kinds[topic_id], title, url, summary, ts),
            )
            if cur.rowcount:
                added.append((cur.lastrowid, title))
            if len(added) >= cap:
                break
    for finding_id, title in added:
        ctx.event("found", title[:120], ref=str(finding_id))
    return f"{len(added)} new finding(s) from {len(items)} proposed"
