"""Education: topics, questions and grading end to end, and the read/write tool split."""

from app.daemon import build
from app.modules.education.tools import add_question, grade
from tests.conftest import run
from tests.test_app import client_for


def test_education_end_to_end(config):
    async def main():
        app = build(config)
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
            # a question has 3 to 5 parts and a title used once per topic
            assert "error" in add_question(store, tid, "Too short", "p", ["a", "b"], 3, "nightly", False)
            qid = add_question(store, tid, "Why is the sky blue?", "Sunlight is a mix of colours.", ["p1", "p2", "p3", "p4"], 3, "nightly", False)["id"]
            assert "error" in add_question(store, tid, "Why is the sky blue?", "again", ["a", "b", "c"], 3, "nightly", False)
            left = (await c.get("/api/education/left")).json()
            row = left["groups"][0]["rows"][0]
            assert left["groups"][0]["label"] == "due" and row["id"] == qid and row["leading"] == {"pct": 0} and row["done"] is False
            n = next(x for x in (await c.get("/api/home/numbers")).json() if x["module"] == "education")
            assert n["value"] == 1 and n["label"] == "due"
            home = (await c.get("/api/home/left")).json()
            assert next(g for g in home["groups"] if g["module"] == "education")["count"] == 1
            item = (await c.get(f"/api/education/item/{qid}")).json()
            assert [a["verb"] for a in item["actions"]] == ["start", "skip"] and len(item["parts"]) == 4
            assert item["text"].startswith("Why is the sky blue?") and item["kind"] == "Physics · d3"
            assert (await c.post("/api/education/action/start", json={"id": qid})).status_code == 200
            item = (await c.get(f"/api/education/item/{qid}")).json()
            assert item["status"] == "started" and [a["verb"] for a in item["actions"]] == ["skip"]
            assert f"Started question Q{qid}" in app.state.registry.get("education").context(store, app.state.registry)
            # part by part; the last part completes the question and moves the topic's difficulty once
            for part, score in enumerate((100, 90, 90, 80), 1):
                out = grade(store, config, qid, part, score, "ok")
                assert "error" not in out, out
            assert out["remaining"] == 0 and out["question_score"] == 90 and out["topic_difficulty"] == start_d + 1
            assert "error" in grade(store, config, qid, 9, 50, "")
            assert grade(store, config, qid, 4, 60, "revised")["question_score"] == 85
            assert store.scalar("SELECT difficulty FROM topics WHERE id = ?", (tid,)) == start_d + 1
            left = (await c.get("/api/education/left")).json()
            assert left["groups"][0]["label"] != "due" and left["groups"][0]["rows"][0]["leading"] == {"pct": 85}
            t = (await c.get("/api/education/blank")).json()["topics"][0]
            assert (t["graded"], t["asked"], t["average"], t["recent"]) == (1, 1, 85, [85])
            assert next(x for x in (await c.get("/api/home/numbers")).json() if x["module"] == "education")["value"] == 0
            # search, skip, retire and return
            assert (await c.get("/api/education/left?query=sky")).json()["showing"] == "1 / 1"
            assert (await c.get("/api/education/left?query=zzz")).json()["groups"] == []
            q2 = add_question(store, tid, "Second", "premise", ["a", "b", "c"], 3, "session", True)["id"]
            assert (await c.get(f"/api/education/item/{q2}")).json()["status"] == "started"
            assert (await c.post("/api/education/action/skip", json={"id": q2})).status_code == 200
            assert (await c.post("/api/education/action/skip", json={"id": q2})).status_code == 409
            rows = [r for g in (await c.get("/api/education/left")).json()["groups"] for r in g["rows"]]
            assert next(r for r in rows if r["id"] == q2)["done"] is True
            assert (await c.post("/api/education/action/retire_topic", json={"id": tid})).status_code == 200
            assert (await c.get("/api/education/blank")).json()["topics"] == []
            assert (await c.post("/api/education/action/add_topic", json={"name": "Physics"})).json()["id"] == tid
            ev = (await c.get("/api/events?module=education")).json()
            assert [e["verb"] for e in ev["events"]][:4] == ["added topic", "retired topic", "skipped", "graded"]
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
