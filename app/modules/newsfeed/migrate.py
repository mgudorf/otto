"""One-time conversion of the Business, Social and Search rows into Newsfeed searches and entries, behind a backup.

`python -m app.modules.newsfeed migrate`: the plans become the `business` search and its leads the entries; the social
scout's towns, radius, horizon and categories become the `social` search and its events the entries; each search topic
becomes a search of its own and its findings the entries. The old tables are left where they are. Safe to run twice.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from app.modules.newsfeed.tasks import local_today
from app.store import Store, now_iso

SCHEMA = Path(__file__).with_name("schema.sql").read_text("utf-8")

# The [business], [social] and [web_search] values in config.toml when those modules were retired, now the searches' own words.
BUSINESS_CAP = 3
BUSINESS_LEAD = "Find realistic job openings, calls, events, or news the owner should act on. The owner's current business plans, in their own words:"
SOCIAL_CAP = 5
SOCIAL_PROMPT = "\n".join([
    "Find events happening within 15 miles of any of these towns: Woodstock, GA, Roswell, GA, Canton, GA, Alpharetta, GA, Marietta, GA.",
    "Only events starting within the next 30 days. Each must be real, dated and open to the public; give its date and time.",
    "",
    "Tag each event with its town and exactly one of these categories:",
    "- class: workshops, classes and hands-on sessions",
    "- meet: meetups and mixers for meeting people and making friends",
    "- biz: small business, startup and entrepreneur events",
    "- music: live music and performances",
    "- art: art, craft, maker and theatre events",
    "- food: food festivals, markets and tastings",
    "- game: game nights, trivia, board and video games",
    "- animal: animal, pet and wildlife events",
    "- film: film screenings and movie nights",
    "- local: town festivals, fairs and community days",
    "",
    "Skip anything built around drinking: bar crawls, brewery and distillery tours, wine tastings, happy hours, drink specials.",
    "A venue that happens to serve alcohol is fine when the event itself is not about it.",
])
TOPIC_CAP = 3
TOPIC_MEANS = {
    "money": "investment, sector and legislation news",
    "work": "new techniques, algorithms and research for the owner's work and career",
    "learn": "topics the owner is learning and sources of questions about them",
}
STATUS = {"open": "open", "accepted": "accepted", "dismissed": "dismissed", "going": "accepted", "agreed": "accepted", "disagreed": "dismissed"}


def _has(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone() is not None


def _search(conn: sqlite3.Connection, added: dict, name: str, prompt: str, cap: int, created_at: str, tags: list[str]) -> int:
    """The search's id, created on the first run and found on the next."""
    row = conn.execute("SELECT id FROM newsfeed_searches WHERE name = ?", (name,)).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO newsfeed_searches(name, prompt, every_days, cap, created_at, next_run) VALUES (?, ?, 1, ?, ?, ?)",
        (name, prompt, cap, created_at, local_today()),
    )
    for t in tags:
        conn.execute("INSERT OR IGNORE INTO newsfeed_tags(kind, ref, tag) VALUES ('search', ?, ?)", (cur.lastrowid, t))
    added["searches"] += 1
    return cur.lastrowid


def _entry(conn: sqlite3.Connection, added: dict, search_id: int, r, summary, starts_at, decided_at, tags: list[str]) -> None:
    """One old row (text, ref or url, created_at or found_at, status) as an entry; a url already there is left alone."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO newsfeed_items(search_id, text, url, summary, starts_at, found_at, status, decided_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (search_id, r["text"], r["ref"], summary, starts_at, r["created_at"], STATUS[r["status"]], decided_at),
    )
    if cur.rowcount:
        for t in tags:
            conn.execute("INSERT OR IGNORE INTO newsfeed_tags(kind, ref, tag) VALUES ('item', ?, ?)", (cur.lastrowid, t))
        added["entries"] += 1


def convert(store: Store) -> dict[str, int]:
    """Copy what the three old modules recorded into the newsfeed tables, in one transaction. Returns what was added."""
    store.migrate(SCHEMA)
    added = {"searches": 0, "entries": 0}
    with store.tx() as conn:
        if _has(conn, "business_items"):
            plans = conn.execute("SELECT text, created_at FROM business_items WHERE kind = 'plan' ORDER BY created_at, id").fetchall()
            leads = conn.execute("SELECT * FROM business_items WHERE kind = 'lead' ORDER BY id").fetchall()
            if plans or leads:
                prompt = "\n".join([BUSINESS_LEAD, *[f"- {p['text']}" for p in plans]])
                sid = _search(conn, added, "business", prompt, BUSINESS_CAP, plans[0]["created_at"] if plans else now_iso(), ["business"])
                for r in leads:
                    _entry(conn, added, sid, r, r["why"], None, r["updated_at"] if r["status"] != "open" else None, ["business"])
        if _has(conn, "social_items"):
            events = conn.execute("SELECT * FROM social_items WHERE kind = 'event' ORDER BY id").fetchall()
            sid = _search(conn, added, "social", SOCIAL_PROMPT, SOCIAL_CAP, events[0]["created_at"] if events else now_iso(), ["social"])
            for r in events:
                starts = r["starts_at"][:10] if r["starts_at"] and r["starts_at"].endswith("T00:00") else r["starts_at"]
                town = (r["city"] or "").split(",")[0].strip().lower()
                tags = ["social", *([r["category"]] if r["category"] else []), *([town] if town else [])]
                _entry(conn, added, sid, r, r["why"], starts, r["updated_at"] if r["status"] != "open" else None, tags)
        if _has(conn, "web_search_topics") and _has(conn, "web_search_findings"):
            for t in conn.execute("SELECT id, kind, text, created_at FROM web_search_topics ORDER BY id").fetchall():
                prompt = f"Find pages published recently about {t['kind']} ({TOPIC_MEANS[t['kind']]}): {t['text']}"
                sid = _search(conn, added, t["text"], prompt, TOPIC_CAP, t["created_at"], [t["kind"]])
                for f in conn.execute(
                    "SELECT title AS text, url AS ref, summary, found_at AS created_at, status, decided_at FROM web_search_findings WHERE topic_id = ? ORDER BY id",
                    (t["id"],),
                ).fetchall():
                    _entry(conn, added, sid, f, f["summary"], None, f["decided_at"], [t["kind"]])
    return added


def main(argv: list[str], config) -> int:
    if argv[:1] != ["migrate"]:
        print("usage: python -m app.modules.newsfeed migrate")
        return 2
    store = Store(config.data.db)
    try:
        dest = config.data.db.parent / "backups" / f"otto-{datetime.now():%Y%m%d-%H%M%S}-pre-newsfeed.db"
        store.backup(dest)
        print(f"backup {dest}")
        added = convert(store)
        print(f"added {added['searches']} search(es), {added['entries']} entr(ies)")
        for s in store.query("SELECT name, cap, next_run, (SELECT COUNT(*) FROM newsfeed_items i WHERE i.search_id = s.id) AS n FROM newsfeed_searches s ORDER BY id"):
            print(f"  {s['name']}: {s['n']} entries, cap {s['cap']}, next {s['next_run']}")
    finally:
        store.close()
    return 0
