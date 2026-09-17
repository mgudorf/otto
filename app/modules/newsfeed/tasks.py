"""One nightly job runs every search whose day has come: one read-only, budgeted web search each, entries capped per search.

Each search commits on its own (entries, tags, consumed follow-ups, its next day), so a budget refusal or a bad reply
midway loses nothing already written. A reply the parser rejects is that search's last_result; the rest still run.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from app.runner import Skipped
from app.store import now_iso

SEEN = 100          # entries listed back to the model per search, newest first, so a url is never proposed twice
TAG_CHARS = 24      # a tag longer than this is cut; the chips are one word each


def local_today() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d")


def parse_array(raw: str) -> list:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("["):]
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < 0:
        raise ValueError(f"no JSON array in reply: {raw[:200]!r}")
    items = json.loads(text[start:end + 1])
    if not isinstance(items, list):
        raise ValueError("reply is not a JSON array")
    return [it for it in items if isinstance(it, dict)]


def clean_tags(values) -> list[str]:
    """Lowercased, trimmed, cut at TAG_CHARS, in order without repeats; anything that is not a list of strings is ignored."""
    if not isinstance(values, (list, tuple)):
        return []
    out: list[str] = []
    for v in values:
        tag = str(v).strip().lower()[:TAG_CHARS] if isinstance(v, (str, int, float)) else ""
        if tag and tag not in out:
            out.append(tag)
    return out


def a_date(value) -> str | None:
    """`YYYY-MM-DD` or None."""
    try:
        return date.fromisoformat(str(value).strip()).isoformat()
    except (TypeError, ValueError):
        return None


def starts_at(day, clock) -> str | None:
    """The day an entry happens with its `HH:MM` when the listing gave one, as the naive local stamp starts_at holds."""
    d = a_date(day)
    if d is None:
        return None
    try:
        return f"{d}T{datetime.strptime(str(clock).strip(), '%H:%M'):%H:%M}"
    except (TypeError, ValueError):
        return d


def search_tags(store, search_id: int) -> list[str]:
    return [r["tag"] for r in store.query("SELECT tag FROM newsfeed_tags WHERE kind = 'search' AND ref = ? ORDER BY tag", (search_id,))]


def prompt(store, s: dict, today: str) -> tuple[str, list[int]]:
    """The run's prompt for one search, and the ids of the accepted entries it asks to follow up on."""
    seen = store.query(
        "SELECT url, text, status FROM newsfeed_items WHERE search_id = ? ORDER BY found_at DESC, id DESC LIMIT ?", (s["id"], SEEN)
    )
    due = store.query(
        "SELECT id, url, text, follow_up_at FROM newsfeed_items WHERE search_id = ? AND status = 'accepted'"
        " AND follow_up_at IS NOT NULL AND follow_up_at <= ? ORDER BY follow_up_at, id",
        (s["id"], today),
    )
    lines = [
        f"Today is {today}.",
        "",
        s["prompt"].strip(),
        "",
        "Already recorded for this search (status, url, text). Never repeat a url; an accepted one shows what the owner values,"
        " a dismissed one what to stop bringing:",
        *([f"- ({r['status']}) {r['url']} {r['text'][:120]}" for r in seen] or ["- none"]),
    ]
    if due:
        lines += [
            "",
            "Accepted entries whose follow-up day has come (id, day, url, text). Search for what has changed since and report it as a"
            " new entry with \"follows\" set to that id:",
            *[f"- ({r['id']}, {r['follow_up_at']}) {r['url']} {r['text'][:120]}" for r in due],
        ]
    lines += [
        "",
        f"Use WebSearch and WebFetch to find up to {s['cap']} new entries. Each must be real, current and have a page of its own.",
        'Reply with only a JSON array. Each element: {"text": one line naming it, "url": its page,'
        ' "summary": one or two sentences on why it matters to the owner,'
        ' "date": "YYYY-MM-DD" when it happens on a day, else "", "time": "HH:MM" when the listing gives one, else "",'
        ' "follow_up": "YYYY-MM-DD" when the owner should check back on it (a deadline, a release, a decision), else "",'
        ' "tags": one to three short lowercase words, "follows": the id it follows up on, else null}.',
        "An empty array is a fine answer when nothing new and concrete turned up.",
    ]
    return "\n".join(lines), [r["id"] for r in due]


def store_items(ctx, s: dict, items: list, due_ids: list[int], today: str) -> int:
    """Write one search's run in one transaction: capped new entries with their tags, the follow-ups consumed, the next day booked."""
    ts = now_iso()
    inherited = search_tags(ctx.store, s["id"])
    added: list[tuple[int, str]] = []
    next_run = (date.fromisoformat(today) + timedelta(days=max(1, int(s["every_days"])))).isoformat()
    with ctx.commit(cursor=("newsfeed.run", ts)) as conn:
        for it in items:
            text = str(it.get("text", "")).strip()
            url = str(it.get("url", "")).strip()
            if not text or not url:
                continue
            follows = it.get("follows")
            follows = int(follows) if str(follows).isdigit() and int(follows) in due_ids else None
            cur = conn.execute(
                "INSERT OR IGNORE INTO newsfeed_items(search_id, text, url, summary, starts_at, follow_up_at, follows, found_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    s["id"], text, url, str(it.get("summary", "")).strip() or None,
                    starts_at(it.get("date"), it.get("time")), a_date(it.get("follow_up")), follows, ts,
                ),
            )
            if cur.rowcount:
                added.append((cur.lastrowid, text))
                for tag in dict.fromkeys(inherited + clean_tags(it.get("tags"))):
                    conn.execute("INSERT OR IGNORE INTO newsfeed_tags(kind, ref, tag) VALUES ('item', ?, ?)", (cur.lastrowid, tag))
            if len(added) >= s["cap"]:
                break
        for item_id in due_ids:
            conn.execute("UPDATE newsfeed_items SET follow_up_at = NULL WHERE id = ?", (item_id,))
        conn.execute(
            "UPDATE newsfeed_searches SET next_run = ?, last_run = ?, last_result = ? WHERE id = ?",
            (next_run, ts, f"{len(added)} new from {len(items)} proposed", s["id"]),
        )
    for item_id, text in added:
        ctx.event("found", f"{s['name']}: {text[:120]}", ref=str(item_id))
    return len(added)


async def run(ctx) -> str:
    today = local_today()
    due = ctx.store.query("SELECT * FROM newsfeed_searches WHERE next_run <= ? ORDER BY next_run, id", (today,))
    if not due:
        return Skipped("no searches" if ctx.store.scalar("SELECT COUNT(*) FROM newsfeed_searches") == 0 else "nothing due")
    out = []
    for s in due:
        text, due_ids = prompt(ctx.store, s, today)
        raw = await ctx.run_task(text)
        try:
            items = parse_array(raw)
        except ValueError as e:
            with ctx.commit() as conn:
                conn.execute("UPDATE newsfeed_searches SET last_run = ?, last_result = ? WHERE id = ?", (now_iso(), f"bad reply: {e}"[:500], s["id"]))
            out.append(f"{s['name']}: bad reply")
            continue
        out.append(f"{s['name']}: {store_items(ctx, s, items, due_ids, today)} new")
    return "; ".join(out)
