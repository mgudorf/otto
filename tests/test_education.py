"""Education: the question format, a generated question, answers graded on the page, the tutor's tools, the nightly task, the column migration."""

import json
import sqlite3

from app.daemon import build
from app.modules.education import setup
from app.modules.education.grading import grade
from app.modules.education.questions import add_question, unbound_acronyms
from app.store import now_iso
from tests.conftest import FakeProc, fake_spawn, run
from tests.test_app import client_for

PARTS = [
    {"label": "a", "prompt": "Why does a large $z_k$ pin the output?", "rubric": "the exponential dominates the sum"},
    {"label": "b", "prompt": "What does a low temperature do?", "rubric": "sharpens toward argmax"},
    {"label": "c", "prompt": "When is the gradient smallest?", "rubric": "saturation: near one-hot outputs"},
]
QUESTION = {
    "topic_id": 1, "title": "Why softmax saturates", "topic_tag": "softmax temperature",
    "setup_markdown": "Let $z_i$ be logits and $T$ a temperature; softmax is $$p_i = \\frac{e^{z_i/T}}{\\sum_j e^{z_j/T}}$$",
    "parts": PARTS,
}
CORRECT = {"verdict": "correct", "score": 2, "explanation": "Right: $e^{z_k}$ dominates the sum."}


def result(text: str) -> str:
    return json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": text, "session_id": "x"})


def spawn_sequence(replies: list[str], calls: list | None = None):
    """A fake CLI answering each spawn with the next reply; the last one repeats."""
    queue = list(replies)

    async def spawn(args, cwd, env):
        if calls is not None:
            calls.append(args)
        reply = queue.pop(0) if len(queue) > 1 else queue[0]
        return FakeProc([result(reply)])

    return spawn


def test_education_end_to_end(config):
    calls: list = []
    replies = ["```json\n" + json.dumps([QUESTION]) + "\n```", json.dumps(CORRECT), "no json here", json.dumps(CORRECT)]

    async def main():
        app = build(config, spawn_fn=spawn_sequence(replies, calls))
        await app.state.runner.start()
        store = app.state.store
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
            assert blank["due"] == 0 and blank["topics"][0]["difficulty"] == start_d and blank["topics"][0]["recent"] == []
            # a question has 3 to 5 parts, each with a prompt and a rubric, and a title used once per topic
            assert "parts" in add_question(store, tid, "Too short", "tag", "s", PARTS[:2], "nightly", False)["error"]
            assert "(b) needs" in add_question(store, tid, "No rubric", "tag", "s", [PARTS[0], {"prompt": "x"}, PARTS[2]], "nightly", False)["error"]
            qid = add_question(
                store, tid, "Why is the sky blue?", "Rayleigh scattering", "Sunlight is a mix of colours; $\\lambda$ is a wavelength.",
                PARTS + [{"prompt": "d", "rubric": "r"}], "nightly", False,
            )["id"]
            assert "error" in add_question(store, tid, "Why is the sky blue?", "again", "s", PARTS, "nightly", False)
            left = (await c.get("/api/education/left")).json()
            row = left["groups"][0]["rows"][0]
            assert left["groups"][0]["label"] == "due" and row["id"] == qid and row["leading"] == {"pct": 0} and row["done"] is False
            n = next(x for x in (await c.get("/api/home/numbers")).json() if x["module"] == "education")
            assert n["value"] == 1 and n["label"] == "due"
            home = (await c.get("/api/home/left")).json()
            assert next(g for g in home["groups"] if g["module"] == "education")["count"] == 1
            item = (await c.get(f"/api/education/item/{qid}")).json()
            assert [a["verb"] for a in item["actions"]] == ["start", "skip"] and [p["label"] for p in item["parts"]] == ["a", "b", "c", "d"]
            assert item["text"].startswith("Why is the sky blue?") and item["kind"] == "Physics · d3" and item["topic_tag"] == "Rayleigh scattering"
            assert "rubric" not in json.dumps(item)
            # a press generates one question on the topic that has waited longest, through the generator
            r = await c.post("/api/education/action/generate", json={})
            assert r.status_code == 200, r.text
            gid = r.json()["id"]
            g = store.one("SELECT * FROM questions WHERE id = ?", (gid,))
            assert g["title"] == "Why softmax saturates" and g["topic_tag"] == "softmax temperature" and g["source"] == "session" and g["started_at"] is None
            assert [p["rubric"] for p in store.query("SELECT rubric FROM question_parts WHERE question_id = ? ORDER BY n", (gid,))] == [p["rubric"] for p in PARTS]
            # an answer on the page is graded at once, starts its question, and shows the tutor the rubric
            r = await c.post("/api/education/action/answer", json={"id": qid, "n": 1, "answer": "because the exponential dominates"})
            assert r.status_code == 200, r.text
            assert r.json() == {"id": qid, "n": 1, "verdict": "correct", "score": 100}
            p = store.one("SELECT * FROM question_parts WHERE question_id = ? AND n = 1", (qid,))
            assert p["answer"] == "because the exponential dominates" and p["verdict"] == "correct" and p["score"] == 100 and p["note"] == CORRECT["explanation"]
            item = (await c.get(f"/api/education/item/{qid}")).json()
            assert item["status"] == "started" and [a["verb"] for a in item["actions"]] == ["skip"] and item["parts"][0]["score"] == 100
            ctx = app.state.registry.get("education").context(store, app.state.registry)
            assert f"Started question Q{qid}" in ctx and "because the exponential dominates" in ctx
            assert PARTS[0]["rubric"] in ctx and PARTS[1]["rubric"] not in ctx
            assert "otto-read" in " ".join(calls[-1]) and "--no-session-persistence" in calls[-1]
            assert store.one("SELECT budgeted FROM llm_runs WHERE task = 'education.grade'")["budgeted"] == 0
            # a bad reply keeps the answer and answers 502; the retry grades it
            r = await c.post("/api/education/action/answer", json={"id": qid, "n": 2, "answer": "sharper"})
            assert r.status_code == 502, r.text
            p = store.one("SELECT * FROM question_parts WHERE question_id = ? AND n = 2", (qid,))
            assert p["answer"] == "sharper" and p["answered_at"] and p["graded_at"] is None
            assert (await c.post("/api/education/action/answer", json={"id": qid, "n": 2, "answer": "sharper"})).status_code == 200
            assert (await c.post("/api/education/action/answer", json={"id": qid, "n": 1, "answer": "again"})).status_code == 409
            assert (await c.post("/api/education/action/answer", json={"id": qid, "n": 3, "answer": " "})).status_code == 400
            assert (await c.post("/api/education/action/answer", json={"id": qid, "n": 9, "answer": "x"})).status_code == 404
            # the tutor grades the rest; the last part completes the question and moves the topic's difficulty once
            out = grade(store, config, qid, 3, 100, "ok")
            assert out["remaining"] == 1 and out["verdict"] == "correct"
            out = grade(store, config, qid, 4, 90, "nearly")
            assert out["remaining"] == 0 and out["question_score"] == 98 and out["topic_difficulty"] == start_d + 1 and out["verdict"] == "partial"
            assert "error" in grade(store, config, qid, 9, 50, "")
            assert grade(store, config, qid, 4, 60, "revised")["question_score"] == 90
            assert store.scalar("SELECT difficulty FROM topics WHERE id = ?", (tid,)) == start_d + 1
            left = (await c.get("/api/education/left")).json()
            done = next(r for g in left["groups"] for r in g["rows"] if r["id"] == qid)
            assert left["groups"][0]["label"] == "due" and done["leading"] == {"pct": 90}
            t = (await c.get("/api/education/blank")).json()["topics"][0]
            assert (t["graded"], t["asked"], t["average"], t["recent"]) == (1, 2, 90, [90])
            assert next(x for x in (await c.get("/api/home/numbers")).json() if x["module"] == "education")["value"] == 1
            # search, skip, retire and return
            assert (await c.get("/api/education/left?query=sky")).json()["showing"] == "1 / 1"
            assert (await c.get("/api/education/left?query=zzz")).json()["groups"] == []
            q2 = add_question(store, tid, "Second", "tag", "premise", PARTS, "session", True)["id"]
            assert (await c.get(f"/api/education/item/{q2}")).json()["status"] == "started"
            assert (await c.post("/api/education/action/skip", json={"id": q2})).status_code == 200
            assert (await c.post("/api/education/action/skip", json={"id": q2})).status_code == 409
            assert (await c.post("/api/education/action/answer", json={"id": q2, "n": 1, "answer": "late"})).status_code == 409
            rows = [r for g in (await c.get("/api/education/left")).json()["groups"] for r in g["rows"]]
            assert next(r for r in rows if r["id"] == q2)["done"] is True
            assert (await c.post("/api/education/action/retire_topic", json={"id": tid})).status_code == 200
            assert (await c.get("/api/education/blank")).json()["topics"] == []
            assert (await c.post("/api/education/action/generate", json={})).status_code == 409
            assert (await c.post("/api/education/action/add_topic", json={"name": "Physics"})).json()["id"] == tid
            verbs = [e["verb"] for e in (await c.get("/api/events?module=education")).json()["events"]]
            assert verbs[:7] == ["added topic", "retired topic", "skipped", "graded", "failed", "generated", "added topic"]
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
        {**QUESTION, "title": "Two parts", "parts": PARTS[:2]},
        {**QUESTION, "title": "No rubric", "parts": [PARTS[0], {"prompt": "x"}, PARTS[2]]},
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
        store.execute("INSERT INTO topics(name, difficulty, created_at) VALUES ('Physics', 3, ?)", (now_iso(),))
        out = await run_once()
        assert out.startswith("1 new question(s) for Physics") and "4 rejected" in out
        q = store.one("SELECT * FROM questions")
        assert q["title"] == "Why softmax saturates" and q["topic_tag"] == "softmax temperature" and q["source"] == "nightly" and q["started_at"] is None
        assert [p["rubric"] for p in store.query("SELECT rubric FROM question_parts ORDER BY n")] == [p["rubric"] for p in PARTS]
        assert store.cursor("education.generate")
        logs = " ".join(r["message"] for r in store.query("SELECT message FROM job_logs"))
        assert "got 2" in logs and "(b) needs a prompt and a rubric" in logs and "topic 9 not asked for" in logs
        # a budget refusal ends as skipped, not failed
        monkeypatch.setattr(st.claude, "budget", lambda: {"used": 3, "max": 3, "window": "02:00-05:00", "in_window": True})
        assert "budget" in str(await run_once())
        # a full queue never spends a run
        for i in range(config.education.queue_size):
            add_question(store, 1, f"filler {i}", "tag", "p", PARTS, "nightly", False)
        assert str(await run_once()).startswith("queue full")
        assert [r["status"] for r in store.query("SELECT status FROM jobs ORDER BY id")] == ["skipped", "done", "skipped", "skipped"]
        assert store.scalar("SELECT COUNT(*) FROM events WHERE verb = 'failed'") == 0
        await st.runner.drain(1)
        store.close()

    run(main())


def test_setup_adds_columns(config):
    """A v0 database gains the v1 columns at boot, once; its questions still serve."""
    config.data.db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.data.db)
    conn.executescript("""
        CREATE TABLE topics (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, description TEXT, difficulty INTEGER NOT NULL, created_at TEXT NOT NULL, retired_at TEXT);
        CREATE TABLE questions (id INTEGER PRIMARY KEY, topic_id INTEGER NOT NULL, title TEXT NOT NULL, premise TEXT NOT NULL, difficulty INTEGER NOT NULL,
          source TEXT NOT NULL, created_at TEXT NOT NULL, started_at TEXT, graded_at TEXT, skipped_at TEXT, score INTEGER);
        CREATE TABLE question_parts (question_id INTEGER NOT NULL, n INTEGER NOT NULL, text TEXT NOT NULL, score INTEGER, note TEXT, graded_at TEXT, PRIMARY KEY (question_id, n));
        INSERT INTO topics VALUES (1, 'Physics', NULL, 3, '2026-09-09T00:00:00+00:00', NULL);
        INSERT INTO questions VALUES (1, 1, 'Old shape', 'premise', 3, 'nightly', '2026-09-09T00:00:00+00:00', NULL, NULL, NULL, NULL);
        INSERT INTO question_parts VALUES (1, 1, 'ask', NULL, NULL, NULL);
    """)
    conn.close()
    for _ in range(2):
        setup(config)
    conn = sqlite3.connect(config.data.db)
    assert {r[1] for r in conn.execute("PRAGMA table_info(question_parts)")} >= {"rubric", "answer", "answered_at", "verdict"}
    assert "topic_tag" in {r[1] for r in conn.execute("PRAGMA table_info(questions)")}
    conn.close()

    async def main():
        app = build(config)
        async with client_for(app) as c:
            item = (await c.get("/api/education/item/1")).json()
            assert item["kind"] == "Physics · d3" and item["topic_tag"] is None and item["parts"] == [
                {"n": 1, "label": "a", "text": "ask", "answer": None, "answered_at": None, "verdict": None, "score": None, "note": None, "graded_at": None}
            ]
        app.state.store.close()

    run(main())


def test_unbound_acronyms():
    parts = [{"prompt": "Why merge the most frequent pair?", "rubric": "r"}]
    assert unbound_acronyms("Tokenization and BPE", "subword merges", "LLMs", "Start from a 256-byte alphabet and merge pairs.", parts) == ["BPE", "LLM"]
    assert unbound_acronyms("Tokenization and BPE", "subword merges", "Agentic AI", "Byte-pair encoding (BPE) merges pairs.", parts) == []
