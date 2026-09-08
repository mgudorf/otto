"""Scheduled work: mirror the documents folder, and one nightly read-only web scout for leads."""

from __future__ import annotations

import json
from pathlib import Path

from app.runner import Skipped
from app.store import now_iso


def documents_folder(config) -> Path:
    return config.data.workspace / "business"


def _json_array(raw: str) -> list:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("["):]
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < 0:
        raise ValueError(f"no JSON array in reply: {raw[:200]!r}")
    return json.loads(text[start:end + 1])


async def index_documents(ctx) -> str:
    folder = documents_folder(ctx.config)
    folder.mkdir(parents=True, exist_ok=True)
    files = {str(p.resolve()): p.name for p in sorted(folder.iterdir()) if p.is_file()}
    known = {r["ref"] for r in ctx.store.query("SELECT ref FROM business_items WHERE kind = 'document'")}
    added = [ref for ref in files if ref not in known]
    gone = [ref for ref in known if ref not in files]
    if not added and not gone:
        return Skipped("folder unchanged")
    ts = now_iso()
    with ctx.commit() as conn:
        for ref in added:
            conn.execute(
                "INSERT OR IGNORE INTO business_items(kind, text, ref, created_at, updated_at) VALUES ('document', ?, ?, ?, ?)",
                (files[ref], ref, ts, ts),
            )
        for ref in gone:
            conn.execute("DELETE FROM business_items WHERE kind = 'document' AND ref = ?", (ref,))
    for ref in added:
        ctx.event("indexed", files[ref], ref=ref)
    return f"{len(added)} added, {len(gone)} removed"


async def scout(ctx) -> str:
    plans = ctx.store.query("SELECT id, text FROM business_items WHERE kind = 'plan' ORDER BY created_at")
    if not plans:
        return Skipped("no plans to steer the search")
    cap = ctx.config.business.leads_per_run
    seen = ctx.store.query("SELECT text, ref, status FROM business_items WHERE kind = 'lead' ORDER BY created_at DESC LIMIT 100")
    prompt = "\n".join([
        "The owner's current business plans, in their own words:",
        *[f"- {p['text'][:500]}" for p in plans],
        "",
        "Leads already recorded (status, url, text). Never repeat a url, and let accepted ones show what the owner values:",
        *([f"- ({s['status']}) {s['ref']} {s['text'][:120]}" for s in seen] or ["- none"]),
        "",
        f"Use WebSearch to find up to {cap} new leads that serve these plans: realistic job openings, calls, events, or news the owner should act on.",
        "Reply with only a JSON array. Each element: {\"text\": one line naming the lead, \"url\": the page it came from, \"why\": one sentence tying it to a plan}.",
        "An empty array is a fine answer when nothing new and concrete turned up.",
    ])
    raw = await ctx.run_task(prompt, tools=("business_search",))
    items = _json_array(raw)
    ts = now_iso()
    added: list[tuple[int, str]] = []
    with ctx.commit(cursor=("business.scout", ts)) as conn:
        for it in items:
            text = str(it.get("text", "")).strip()
            ref = str(it.get("url", "")).strip()
            if not text or not ref:
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO business_items(kind, text, ref, why, created_at, updated_at) VALUES ('lead', ?, ?, ?, ?, ?)",
                (text, ref, str(it.get("why", "")).strip() or None, ts, ts),
            )
            if cur.rowcount:
                added.append((cur.lastrowid, text))
            if len(added) >= cap:
                break
    for lead_id, text in added:
        ctx.event("found", text[:120], ref=str(lead_id))
    return f"{len(added)} new lead(s) from {len(items)} proposed"
