"""Education: the question format, a generated question, answers handed to the tutor's session and graded through its tool,
completing and deleting a quiz, tags, the nightly task, the v1 to v2 migration."""

import json
import sqlite3

from app.daemon import build
from app.modules.education import setup
from app.modules.education.grading import grade
from app.modules.education.questions import add_question, label, unbound_acronyms, validate_question
from app.store import now_iso
from tests.conftest import FakeProc, fake_spawn, run
from tests.test_app import client_for, settle

PARTS = [
    {"title": "Pinned output", "prompt": "Why does a large $z_k$ pin the output?", "rubric": "the exponential dominates the sum"},
    {"title": "Low temperature", "prompt": "What does a low temperature do?", "rubric": "sharpens toward argmax"},
    {"title": "Smallest gradient", "prompt": "When is the gradient smallest?", "rubric": "saturation: near one-hot outputs"},
]
DEFS = "**Softmax with temperature**\n$$p_i = \\frac{e^{z_i/T}}{\\sum_j e^{z_j/T}}$$\n- $z_i$: the logit for class $i$\n- $T$: the temperature"
QUESTION = {
    "topic_id": 1, "title": "Why softmax saturates", "topic_tag": "softmax temperature",
    "definitions_markdown": DEFS, "premise_markdown": "A classifier ends in the softmax above.", "parts": PARTS,
}
INIT = json.dumps({"type": "system", "subtype": "init", "session_id": "s1", "tools": ["mcp__otto__education_grade"]})
TOOL = json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "mcp__otto__education_grade", "input": {"question_id": 1, "part": 1, "score": 100, "note": "right"}}]}})
TOOL_OK = json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "{}"}]}})
TEXT = json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "100. Right: $e^{z_k}$ dominates the sum."}]}})
RESULT = json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "100. Right.", "session_id": "s1"})
FAILED = json.dumps({"type": "result", "subtype": "error_during_execution", "is_error": True, "result": "boom", "session_id": "s1"})
GRADED = [INIT, TOOL, TOOL_OK, TEXT, RESULT]


def result(text: str) -> str:
    return json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": text, "session_id": "x"})


def spawn_sequence(replies: list[list[str]], calls: list | None = None, procs: list | None = None):
    """A fake CLI answering each spawn with the next set of lines; the last one repeats. `procs` keeps what it was given on stdin."""
    queue = list(replies)

    async def spawn(args, cwd, env):
        if calls is not None:
            calls.append(args)
        lines = queue.pop(0) if len(queue) > 1 else queue[0]
        p = FakeProc(list(lines))
        if procs is not None:
            procs.append(p)
        return p

    return spawn


def test_education_end_to_end(config):
    calls: list = []
    procs: list = []
    replies = [
        [result("```json\n" + json.dumps([{**QUESTION, "topic_id": 9}]) + "\n```")],   # Generate: the reply names another topic
        [result(json.dumps([QUESTION]))],                                                # Generate: one question for the asked topic
        [FAILED],                                                                        # the first answer's turn fails in the CLI
        GRADED,                                                                          # every later turn: the tutor grades and explains
    ]

    async def main():
        app = build(config, spawn_fn=spawn_sequence(replies, calls, procs))
        await app.state.runner.start()
        store = app.state.store
        registry = app.state.registry
        start_d = config.education.start_difficulty
        async with client_for(app) as c:
            shell = (await c.get("/api/shell")).json()
            edu = next(m for m in shell["modules"] if m["name"] == "education")
            assert edu["hue"] == "#7a9fd6" and edu["order"] == 2 and edu["agent"]["skills"] == ["question-gen", "quiz", "explain", "plan"]
            r = await c.post("/api/education/action/add_topic", json={"name": "Physics", "description": ""})
            assert r.status_code == 200, r.text
            tid = r.json()["id"]
            assert (await c.post("/api/education/action/add_topic", json={"name": "physics"})).status_code == 409
            assert (await c.post("/api/education/action/add_topic", json={"name": " "})).status_code == 400
            blank = (await c.get("/api/education/blank")).json()
            assert blank["due"] == 0 and blank["topics"][0]["difficulty"] == start_d == 5 and blank["topics"][0]["recent"] == []
            # a question has definitions, a premise and at least one part, each with a title, a prompt and a rubric; a title is used once per topic
            assert "at least one part" in add_question(store, tid, "No parts", "tag", DEFS, "s", [], "nightly", False)["error"]
            assert validate_question(store, tid, "One part", "tag", DEFS, "s", PARTS[:1]) is None
            assert "(b) needs a title" in add_question(store, tid, "No title", "tag", DEFS, "s", [PARTS[0], {"prompt": "x", "rubric": "r"}], "nightly", False)["error"]
            assert "definitions and premise" in add_question(store, tid, "No definitions", "tag", " ", "s", PARTS, "nightly", False)["error"]
            qid = add_question(
                store, tid, "Why is the sky blue?", "Rayleigh scattering", DEFS, "Sunlight is a mix of colours.",
                PARTS + [{"title": "Fourth", "prompt": "d", "rubric": "r"}], "nightly", False,
            )["id"]
            assert "error" in add_question(store, tid, "Why is the sky blue?", "again", DEFS, "s", PARTS, "nightly", False)
            left = (await c.get("/api/education/left")).json()
            row = left["groups"][0]["rows"][0]
            assert left["chips"] == ["active", "completed"] and left["chip"] == "active"
            assert left["groups"][0]["label"] == "due" and row["id"] == qid and row["leading"] == {"pct": 0} and "done" not in row
            assert (await c.get("/api/education/left?chip=completed")).json()["groups"] == []
            n = next(x for x in (await c.get("/api/home/numbers")).json() if x["module"] == "education")
            assert n["value"] == 1 and n["label"] == "due"
            home = (await c.get("/api/home/left")).json()
            assert next(g for g in home["groups"] if g["module"] == "education")["count"] == 1
            item = (await c.get(f"/api/education/item/{qid}")).json()
            assert [a["verb"] for a in item["actions"]] == ["delete"] and [p["label"] for p in item["parts"]] == ["a", "b", "c", "d"]
            assert [p["title"] for p in item["parts"]] == ["Pinned output", "Low temperature", "Smallest gradient", "Fourth"]
            assert item["definitions"] == DEFS and item["premise"] == "Sunlight is a mix of colours." and item["kind"] == f"Physics · d{start_d}" and item["tags"] == []
            assert item["text"].startswith("Why is the sky blue?") and "rubric" not in json.dumps(item) and "note" not in json.dumps(item)
            # opening a question on the page makes it the tutor's context
            ctx = registry.get("education").context(store, registry)
            assert f'Open on the page: Q{qid} "Why is the sky blue?"' in ctx and DEFS in ctx and "(a) Pinned output:" in ctx and "not answered" in ctx
            # Generate: a reply that names another topic is a 502; the next lands one question with definitions and part titles
            r = await c.post("/api/education/action/generate", json={})
            assert r.status_code == 502 and "no question for topic" in r.text
            r = await c.post("/api/education/action/generate", json={})
            assert r.status_code == 200, r.text
            gid = r.json()["id"]
            g = store.one("SELECT * FROM questions WHERE id = ?", (gid,))
            assert g["title"] == "Why softmax saturates" and g["definitions"] == DEFS and g["premise"] == "A classifier ends in the softmax above."
            assert g["topic_tag"] == "softmax temperature" and g["source"] == "session" and g["opened_at"] is None and g["tags"] == "[]"
            assert [(p["title"], p["rubric"]) for p in store.query("SELECT title, rubric FROM question_parts WHERE question_id = ? ORDER BY n", (gid,))] == [(p["title"], p["rubric"]) for p in PARTS]
            assert "otto-read" in " ".join(calls[-1]) and "--no-session-persistence" in calls[-1]
            # an answer is a turn in the tutor's session: stored, the question started, the tutor briefed with the rubric
            r = await c.post("/api/education/action/answer", json={"id": qid, "n": 1, "answer": "because the exponential dominates"})
            assert r.status_code == 200, r.text
            assert r.json()["id"] == qid and r.json()["n"] == 1 and "queued" in r.json()
            await settle(app)
            p = store.one("SELECT * FROM question_parts WHERE question_id = ? AND n = 1", (qid,))
            assert p["answer"] == "because the exponential dominates" and p["answered_at"] and p["graded_at"] is None
            assert store.one("SELECT started_at FROM questions WHERE id = ?", (qid,))["started_at"]
            brief = procs[-1].stdin.data.decode()
            assert PARTS[0]["rubric"] in brief and "because the exponential dominates" in brief and DEFS in brief and "first answer to this part" in brief
            args = calls[-1]
            assert "--session-id" in args and "mcp__otto__education_grade" in args[args.index("--allowedTools") + 1]
            # that turn failed in the CLI: the session row is retired, the answer is kept, the part waits for its grade
            assert (await c.get("/api/session/education")).json()["sessions"] == []
            item = (await c.get(f"/api/education/item/{qid}")).json()
            assert item["parts"][0]["answered_at"] and item["parts"][0]["score"] is None
            assert "your grade through education_grade is awaited" in registry.get("education").context(store, registry)
            # the next submit opens a fresh tab; the tutor grades through its tool and the pane shows the explanation
            r = await c.post("/api/education/action/answer", json={"id": qid, "n": 1, "answer": "because the exponential dominates"})
            assert r.status_code == 200, r.text
            await settle(app)
            sid = r.json()["session"]
            assert [t["id"] for t in (await c.get("/api/session/education")).json()["sessions"]] == [sid]
            s = (await c.get(f"/api/session/education/{sid}")).json()
            assert [(t["role"], t.get("tool"), t.get("status")) for t in s["turns"]] == [("user", None, None), ("tool", "education_grade", "done"), ("model", None, None)]
            assert s["turns"][0]["text"] == "(a) Pinned output\nbecause the exponential dominates" and s["busy"] is False
            out = grade(store, qid, 1, 100, "right")
            assert out == {"question_id": qid, "part": 1, "verdict": "correct", "score": 100, "remaining": 3}
            item = (await c.get(f"/api/education/item/{qid}")).json()
            assert item["parts"][0]["score"] == 100 and item["parts"][0]["verdict"] == "correct" and [a["verb"] for a in item["actions"]] == ["delete"]
            ctx = registry.get("education").context(store, registry)
            assert "graded: correct 100/100 — right" in ctx and PARTS[0]["rubric"] in ctx and PARTS[1]["rubric"] not in ctx
            # a graded part takes a new answer: the brief carries the earlier grade and the turn resumes the session
            r = await c.post("/api/education/action/answer", json={"id": qid, "n": 1, "answer": "again"})
            assert r.status_code == 200, r.text
            await settle(app)
            brief = procs[-1].stdin.data.decode()
            assert "Scored 100/100, correct. Your note then: right" in brief and "because the exponential dominates" in brief and "again" in brief
            assert "--resume" in calls[-1]
            p = store.one("SELECT * FROM question_parts WHERE question_id = ? AND n = 1", (qid,))
            assert p["answer"] == "again" and p["answered_at"] and p["graded_at"] is None and p["score"] is None and p["note"] is None
            item = (await c.get(f"/api/education/item/{qid}")).json()
            assert item["parts"][0]["score"] is None and item["parts"][0]["answered_at"]
            assert grade(store, qid, 1, 90, "close")["verdict"] == "partial"
            assert (await c.post("/api/education/action/answer", json={"id": qid, "n": 2, "answer": " "})).status_code == 400
            assert (await c.post("/api/education/action/answer", json={"id": qid, "n": 9, "answer": "x"})).status_code == 404
            assert (await c.post("/api/education/action/answer", json={"id": 999, "n": 1, "answer": "x"})).status_code == 404
            # Complete quiz needs every part graded; the mean is kept as soon as it is, the difficulty moves at completion only
            assert (await c.post("/api/education/action/complete", json={"id": qid})).status_code == 409
            grade(store, qid, 2, 100, "ok")
            grade(store, qid, 3, 100, "ok")
            out = grade(store, qid, 4, 90, "nearly")
            assert out["remaining"] == 0 and out["question_score"] == 95
            assert "error" in grade(store, qid, 9, 50, "")
            q = store.one("SELECT * FROM questions WHERE id = ?", (qid,))
            assert q["completed_at"] is None and q["score"] == 95
            assert store.scalar("SELECT difficulty FROM topics WHERE id = ?", (tid,)) == start_d
            item = (await c.get(f"/api/education/item/{qid}")).json()
            assert [a["verb"] for a in item["actions"]] == ["complete", "delete"] and item["actions"][0]["primary"]
            r = await c.post("/api/education/action/complete", json={"id": qid})
            assert r.status_code == 200 and r.json() == {"id": qid, "score": 95, "topic_difficulty": start_d + 1}
            assert store.scalar("SELECT difficulty FROM topics WHERE id = ?", (tid,)) == start_d + 1
            assert (await c.post("/api/education/action/complete", json={"id": qid})).status_code == 409
            assert (await c.post("/api/education/action/answer", json={"id": qid, "n": 1, "answer": "late"})).status_code == 409
            item = (await c.get(f"/api/education/item/{qid}")).json()
            assert item["status"] == "completed" and item["actions"] == [] and item["kind"] == f"Physics · d{start_d} · 95"
            # a revision after completion recomputes the mean and never moves the difficulty again
            assert grade(store, qid, 4, 60, "revised")["question_score"] == 88
            assert store.scalar("SELECT difficulty FROM topics WHERE id = ?", (tid,)) == start_d + 1
            # LEFT: the completed tab lists it by day with its score; the active tab holds the generated one
            left = (await c.get("/api/education/left?chip=completed")).json()
            assert left["chip"] == "completed" and [r["id"] for g in left["groups"] for r in g["rows"]] == [qid] and left["showing"] == "1 / 1"
            assert left["groups"][0]["rows"][0]["leading"] == {"pct": 88}
            left = (await c.get("/api/education/left")).json()
            assert [r["id"] for g in left["groups"] for r in g["rows"]] == [gid]
            t = (await c.get("/api/education/blank")).json()["topics"][0]
            assert (t["completed"], t["asked"], t["average"], t["recent"]) == (1, 2, 88, [88])
            assert next(x for x in (await c.get("/api/home/numbers")).json() if x["module"] == "education")["value"] == 1
            # search reads title, setup, tags and part titles, within the tab
            assert (await c.get("/api/education/left?chip=completed&query=sky")).json()["showing"] == "1 / 1"
            assert (await c.get("/api/education/left?query=sky")).json()["groups"] == []
            assert (await c.get("/api/education/left?query=gradient")).json()["showing"] == "1 / 1"
            assert (await c.get("/api/education/left?chip=completed&query=zzz")).json()["groups"] == []
            # tags, on a completed question too: trimmed, unique, searchable
            r = await c.post("/api/education/action/tags", json={"id": qid, "tags": [" hard ", "hard", "", "bootstrap"]})
            assert r.status_code == 200 and r.json()["tags"] == ["hard", "bootstrap"]
            assert (await c.get(f"/api/education/item/{qid}")).json()["tags"] == ["hard", "bootstrap"]
            assert (await c.get("/api/education/left?chip=completed&query=bootstrap")).json()["showing"] == "1 / 1"
            assert (await c.post("/api/education/action/tags", json={"id": qid, "tags": "x"})).status_code == 400
            # delete: an active question goes with its parts, its feedback keeps its words; a completed one stays
            store.execute("INSERT INTO education_feedback(ts, topic_id, question_id, text) VALUES (?, ?, ?, ?)", (now_iso(), tid, gid, "too easy"))
            assert (await c.post("/api/education/action/delete", json={"id": qid})).status_code == 409
            assert (await c.post("/api/education/action/delete", json={"id": gid})).status_code == 200
            assert store.scalar("SELECT COUNT(*) FROM question_parts WHERE question_id = ?", (gid,)) == 0
            assert store.one("SELECT question_id, text FROM education_feedback") == {"question_id": None, "text": "too easy"}
            assert (await c.get(f"/api/education/item/{gid}")).status_code == 404
            assert next(x for x in (await c.get("/api/home/numbers")).json() if x["module"] == "education")["value"] == 0
            # retire and return
            assert (await c.post("/api/education/action/retire_topic", json={"id": tid})).status_code == 200
            assert (await c.get("/api/education/blank")).json()["topics"] == []
            assert (await c.post("/api/education/action/generate", json={})).status_code == 409
            assert (await c.post("/api/education/action/add_topic", json={"name": "Physics"})).json()["id"] == tid
            verbs = [e["verb"] for e in (await c.get("/api/events?module=education")).json()["events"]]
            assert list(reversed(verbs)) == [
                "added topic", "failed", "generated", "answered", "failed", "answered", "graded", "answered", "graded", "graded", "graded", "graded",
                "completed", "graded", "deleted", "retired topic", "added topic",
            ]
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_education_tool_split(config):
    async def main():
        app = build(config)
        read = {t.name for t in await app.state.mcp_read.list_tools()}
        full = {t.name for t in await app.state.mcp_full.list_tools()}
        app.state.store.close()
        return read, full

    read, full = run(main())
    reads = {"education_topics", "education_questions", "education_question", "education_feedback"}
    writes = {"education_add_topic", "education_add_question", "education_grade", "education_record_feedback"}
    assert reads <= read and not (writes & read)
    assert reads | writes <= full


def test_generate_task(config, monkeypatch):
    reply = json.dumps([                                       # the malformed ones first: after a topic is served, its later elements are "not asked for"
        {**QUESTION, "title": "No parts", "parts": []},
        {**QUESTION, "title": "No title", "parts": [PARTS[0], {"prompt": "x", "rubric": "r"}, PARTS[2]]},
        {**QUESTION, "topic_id": 9, "title": "Wrong topic"},
        QUESTION,
        {**QUESTION, "title": "Second for the same topic"},
    ])
    lines = [result("```json\n" + reply + "\n```")]

    async def main():
        app = build(config, spawn_fn=fake_spawn(lines))
        await app.state.runner.start()
        st = app.state
        store = st.store
        monkeypatch.setattr(st.claude, "budget", lambda: {"used": 0, "max": 3, "window": "02:00-05:00", "in_window": True})
        task = st.registry.get("education").tasks["generate"]

        async def run_once():
            job = st.runner.submit("education.generate", "education", "education", "scheduled", task)
            return await job.done

        assert str(await run_once()) == "no topics"
        store.execute("INSERT INTO topics(name, difficulty, created_at) VALUES ('Physics', 7, ?)", (now_iso(),))
        out = await run_once()
        assert out.startswith("1 new question(s) for Physics") and "4 rejected" in out
        q = store.one("SELECT * FROM questions")
        assert q["title"] == "Why softmax saturates" and q["definitions"] == DEFS and q["difficulty"] == 7 and q["source"] == "nightly" and q["started_at"] is None
        assert [(p["title"], p["rubric"]) for p in store.query("SELECT title, rubric FROM question_parts ORDER BY n")] == [(p["title"], p["rubric"]) for p in PARTS]
        assert store.cursor("education.generate")
        logs = " ".join(r["message"] for r in store.query("SELECT message FROM job_logs"))
        assert "at least one part" in logs and "(b) needs a title, a prompt and a rubric" in logs and "topic 9 not asked for" in logs
        # a budget refusal ends as skipped, not failed
        monkeypatch.setattr(st.claude, "budget", lambda: {"used": 3, "max": 3, "window": "02:00-05:00", "in_window": True})
        assert "budget" in str(await run_once())
        # unanswered questions never hold the night back: the run goes and writes anyway
        monkeypatch.setattr(st.claude, "budget", lambda: {"used": 0, "max": 5, "window": "02:00-05:00", "in_window": True})
        for i in range(config.education.per_night):
            add_question(store, 1, f"filler {i}", "tag", DEFS, "p", PARTS, "nightly", False)
        assert str(await run_once()).startswith("1 new question(s) for Physics")
        assert [r["status"] for r in store.query("SELECT status FROM jobs ORDER BY id")] == ["skipped", "done", "skipped", "done"]
        assert store.scalar("SELECT COUNT(*) FROM events WHERE verb = 'failed'") == 0
        await st.runner.drain(1)
        store.close()

    run(main())


V1 = """
CREATE TABLE topics (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE,
  description TEXT,
  difficulty  INTEGER NOT NULL CHECK (difficulty BETWEEN 1 AND 5),
  created_at  TEXT NOT NULL,
  retired_at  TEXT
);
CREATE TABLE questions (
  id         INTEGER PRIMARY KEY,
  topic_id   INTEGER NOT NULL REFERENCES topics(id),
  title      TEXT NOT NULL,
  premise    TEXT NOT NULL,
  difficulty INTEGER NOT NULL CHECK (difficulty BETWEEN 1 AND 5),
  source     TEXT NOT NULL CHECK (source IN ('nightly', 'session')),
  created_at TEXT NOT NULL,
  started_at TEXT,
  graded_at  TEXT,
  skipped_at TEXT,
  score      INTEGER, topic_tag TEXT,
  UNIQUE (topic_id, title)
);
CREATE INDEX questions_created ON questions(created_at);
CREATE TABLE question_parts (
  question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  n           INTEGER NOT NULL,
  text        TEXT NOT NULL,
  score       INTEGER CHECK (score BETWEEN 0 AND 100),
  note        TEXT,
  graded_at   TEXT, rubric TEXT, answer TEXT, answered_at TEXT, verdict TEXT CHECK (verdict IN ('correct', 'partial', 'incorrect')),
  PRIMARY KEY (question_id, n)
);
CREATE TABLE education_feedback (
  id          INTEGER PRIMARY KEY,
  ts          TEXT NOT NULL,
  topic_id    INTEGER REFERENCES topics(id),
  question_id INTEGER REFERENCES questions(id),
  text        TEXT NOT NULL
);
INSERT INTO topics VALUES (1, 'Physics', NULL, 3, '2026-09-09T00:00:00+00:00', NULL);
INSERT INTO questions(id, topic_id, title, premise, difficulty, source, created_at, started_at, graded_at, skipped_at, score, topic_tag)
  VALUES (1, 1, 'Old shape', 'premise', 3, 'nightly', '2026-09-09T00:00:00+00:00', '2026-09-09T01:00:00+00:00', '2026-09-09T02:00:00+00:00', NULL, 80, 'tag'),
         (2, 1, 'Skipped one', 'premise', 4, 'nightly', '2026-09-10T00:00:00+00:00', NULL, NULL, '2026-09-10T01:00:00+00:00', NULL, NULL),
         (3, 1, 'Still open', 'premise', 5, 'session', '2026-09-11T00:00:00+00:00', NULL, NULL, NULL, NULL, NULL);
INSERT INTO question_parts(question_id, n, text, score, note, graded_at, rubric, answer, answered_at, verdict)
  VALUES (1, 1, 'Explain why the sky is blue and not violet at noon', 80, 'close', '2026-09-09T02:00:00+00:00', 'r', 'a', '2026-09-09T01:00:00+00:00', 'partial'),
         (2, 1, 'ask', NULL, NULL, NULL, 'r', NULL, NULL, NULL),
         (3, 1, 'ask', NULL, NULL, NULL, 'r', NULL, NULL, NULL);
INSERT INTO education_feedback VALUES (1, '2026-09-10T02:00:00+00:00', 1, 2, 'too easy');
"""


def test_setup_migrates_v1(config):
    """A v1 database is reshaped at boot, once: the 1 to 10 scale (d becomes 2d-1), skipped questions gone, graded_at is completed_at,
    the new columns present; its questions still serve, a part without a title showing the start of its prompt."""
    config.data.db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.data.db)
    conn.executescript(V1)
    conn.close()
    for _ in range(2):
        setup(config)
    conn = sqlite3.connect(config.data.db)
    conn.execute("PRAGMA foreign_keys=ON")
    ddl = {r[0]: r[1] for r in conn.execute("SELECT name, sql FROM sqlite_master WHERE type = 'table'")}
    assert "BETWEEN 1 AND 10" in ddl["topics"] and "BETWEEN 1 AND 10" in ddl["questions"] and "skipped_at" not in ddl["questions"]
    columns = {r[1] for r in conn.execute("PRAGMA table_info(questions)")}
    assert {"definitions", "tags", "opened_at", "completed_at"} <= columns and "graded_at" not in columns
    assert "title" in {r[1] for r in conn.execute("PRAGMA table_info(question_parts)")}
    assert conn.execute("SELECT difficulty FROM topics").fetchone() == (5,)
    assert conn.execute("SELECT id, difficulty, completed_at, score, tags FROM questions ORDER BY id").fetchall() == [
        (1, 5, "2026-09-09T02:00:00+00:00", 80, "[]"), (3, 9, None, None, "[]"),
    ]
    assert conn.execute("SELECT question_id FROM question_parts ORDER BY question_id").fetchall() == [(1,), (3,)]
    assert conn.execute("SELECT question_id, text FROM education_feedback").fetchone() == (None, "too easy")
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.close()

    async def main():
        app = build(config)
        async with client_for(app) as c:
            item = (await c.get("/api/education/item/1")).json()
            assert item["kind"] == "Physics · d5 · 80" and item["status"] == "completed" and item["definitions"] is None and item["tags"] == []
            assert item["parts"] == [{
                "n": 1, "label": "a", "title": "Explain why the sky is blue…", "text": "Explain why the sky is blue and not violet at noon",
                "answer": "a", "answered_at": "2026-09-09T01:00:00+00:00", "verdict": "partial", "score": 80, "graded_at": "2026-09-09T02:00:00+00:00",
            }]
            left = (await c.get("/api/education/left?chip=completed")).json()
            assert left["groups"][0]["rows"][0]["leading"] == {"pct": 80}
            assert [r["id"] for g in (await c.get("/api/education/left")).json()["groups"] for r in g["rows"]] == [3]
        app.state.store.close()

    run(main())


def test_unbound_acronyms():
    parts = [{"title": "Merging pairs", "prompt": "Why merge the most frequent pair?", "rubric": "r"}]
    assert unbound_acronyms("Tokenization and BPE", "subword merges", "LLMs", "**Alphabet** the 256 bytes", "Merge pairs.", parts) == ["BPE", "LLM"]
    assert unbound_acronyms("Tokenization and BPE", "subword merges", "Agentic AI", "**Byte-pair encoding (BPE)** merges pairs.", "Start.", parts) == []


def test_labels_run_past_z():
    assert [label(n) for n in (1, 2, 26, 27, 28, 52, 53)] == ["a", "b", "z", "aa", "ab", "az", "ba"]
