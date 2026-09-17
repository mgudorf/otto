"""Database module: both executors, run/explain/save through the app, the tables by module with their schemas, and the tool split."""

import dataclasses
import sqlite3

import httpx
import pytest

from app.config import Database
from app.daemon import build
from app.modules.database import query
from tests.conftest import run


def client_for(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


ENDLESS = "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT COUNT(*) FROM c"


def test_read_refuses_writes(store):
    conn = store.read_only()
    assert conn.execute("SELECT 1").fetchone() == (1,)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        conn.execute("INSERT INTO app_cursors(key, value) VALUES ('k', 'v')")
    assert "readonly" in query.read(store, "INSERT INTO app_cursors(key, value) VALUES ('k', 'v')", 10, 1)["error"]
    assert store.scalar("SELECT COUNT(*) FROM app_cursors") == 0
    assert query.read(store, ENDLESS, 10, 0.1)["error"].startswith("interrupted")
    assert query.read(store, "   ", 10, 1)["error"] == "empty statement"
    assert query.read(store, "SELECT 1; SELECT 2", 10, 1)["rows"] == [[2]]  # the last statement that returned rows
    assert conn.execute("SELECT 1").fetchone() == (1,)  # still usable after an interruption


def test_statements_split_on_real_ends():
    assert query.statements("select ';'; select 2") == ["select ';';", "select 2"]
    assert query.statements("  \n ") == []


def test_execute_writes(store):
    r = query.execute(store, "insert into app_cursors(key, value) values ('a', '1'), ('b', '2')", 10, 5)
    assert r["changed"] == 2 and r["ddl"] is False and r["columns"] == []
    r = query.execute(store, "update app_cursors set value = '9'; select key, value from app_cursors order by key", 10, 5)
    assert r["changed"] == 2 and r["statements"] == 2 and r["rows"] == [["a", "9"], ["b", "9"]]
    r = query.execute(store, "create table t(x); drop table t", 10, 5)
    assert r["ddl"] is True and r["changed"] == 0
    # a failure stops the script where it broke and names the statement; what already ran stays
    r = query.execute(store, "delete from app_cursors where key = 'a'; select nope from nothing", 10, 5)
    assert r["error"].startswith("statement 2:") and r["changed"] == 1
    assert store.scalar("SELECT COUNT(*) FROM app_cursors") == 1
    # the owner's own transaction is the way to make a script all-or-nothing
    r = query.execute(store, "begin; delete from app_cursors; select nope from nothing; commit", 10, 5)
    assert "error" in r
    query.execute(store, "rollback", 10, 5)
    assert store.scalar("SELECT COUNT(*) FROM app_cursors") == 1
    assert query.execute(store, ENDLESS, 10, 0.1)["error"].startswith("interrupted")
    assert query.execute(store, "  ", 10, 5)["error"] == "empty statement"
    assert store.scalar("SELECT value FROM app_cursors WHERE key = 'b'") == "9"  # connection still usable


def test_owners_come_from_the_schemas():
    owners = query.owners()
    assert owners["app_events"] == "app" and owners["second_brain_items"] == "second_brain" and owners["newsfeed_items"] == "newsfeed"
    assert owners["second_brain_fts"] == "second_brain" and "scratch" not in owners


def test_database_run_explain_save(config):
    config = dataclasses.replace(config, database=Database(max_rows=2, max_seconds=5))

    async def main():
        app = build(config)
        await app.state.runner.start()
        async with client_for(app) as c:
            for text in ("a", "b", "c"):
                await c.post("/api/second_brain/action/capture", json={"kind": "note", "text": text})
            r = (await c.post("/api/database/action/run", json={"sql": "select id, text from second_brain_items order by id"})).json()
            assert r["columns"] == ["id", "text"] and r["total"] == 2 and r["truncated"] is True and r["rows"][0][1] == "a"
            r = (await c.post("/api/database/action/run", json={"sql": "delete from second_brain_items where text = 'c'"})).json()
            assert r["changed"] == 1 and r["columns"] == []
            assert app.state.store.scalar("SELECT COUNT(*) FROM second_brain_items") == 2
            r = (await c.post("/api/database/action/explain", json={"sql": "select * from second_brain_items where id = 1;"})).json()
            assert r["lines"] and "second_brain_items" in r["lines"][0]
            # LEFT: the tables under their modules, app first then rail order; shadow tables and sqlite_* stay hidden
            left = (await c.get("/api/database/left")).json()
            names = [m["name"] for m in left["modules"]]
            assert names[0] == "app" and names.index("email") < names.index("second_brain") < names.index("database") and "other" not in names
            modules = {m["name"]: m for m in left["modules"]}
            brain = {t["name"]: t["rows"] for t in modules["second_brain"]["tables"]}
            assert brain == {"second_brain_fts": 2, "second_brain_items": 2, "second_brain_suggestions": 0, "second_brain_tags": 0} and modules["second_brain"]["rows"] == 4
            tables = {t["name"] for m in left["modules"] for t in m["tables"]}
            assert "second_brain_fts_data" not in tables and "sqlite_sequence" not in tables
            assert all(t["name"].startswith(f"{m['name']}_") for m in left["modules"] for t in m["tables"])
            # one table's schema
            t = (await c.get("/api/database/table/second_brain_items")).json()
            assert t["module"] == "second_brain" and t["rows"] == 2 and t["sql"].startswith("CREATE TABLE") and "second_brain_items" in t["sql"]
            assert [x["name"] for x in t["columns"]] == ["id", "kind", "text", "created_at", "updated_at", "done_at"]
            assert t["columns"][0] == {"name": "id", "type": "INTEGER", "notnull": False, "default": None, "pk": True}
            assert t["columns"][1]["notnull"] is True and [i["name"] for i in t["indexes"]] == ["second_brain_items_created"]
            assert {x["name"] for x in t["triggers"]} == {"second_brain_items_ad", "second_brain_items_ai", "second_brain_items_au"}
            assert (await c.get("/api/database/table/second_brain_fts_data")).status_code == 404
            assert (await c.get("/api/database/table/nope")).status_code == 404
            # saved queries
            qid = (await c.post("/api/database/action/save", json={"name": "recent", "sql": "select * from second_brain_items"})).json()["id"]
            saved = (await c.get("/api/database/left")).json()["saved"]
            assert len(saved) == 1 and saved[0]["name"] == "recent" and saved[0]["id"] == qid and saved[0]["sql"].startswith("select")
            assert (await c.post("/api/database/action/save", json={"name": "recent", "sql": "select id from second_brain_items"})).json()["id"] == qid
            assert (await c.post("/api/database/action/save", json={"name": "", "sql": "x"})).status_code != 200
            assert (await c.post("/api/database/action/delete", json={"id": qid})).status_code == 200
            assert (await c.get("/api/database/left")).json()["saved"] == []
            blank = (await c.get("/api/database/blank")).json()
            assert blank["db"] == "otto.db" and blank["size_bytes"] > 0 and blank["tables"] == len(tables)
            db = next(n for n in (await c.get("/api/home/numbers")).json() if n["module"] == "database")
            assert db["label"] == "database" and db["value"].endswith("B")
            ev = (await c.get("/api/events?module=database")).json()
            assert [e["verb"] for e in ev["events"]][:4] == ["deleted", "saved", "saved", "wrote"]
            assert "1 rows: delete from second_brain_items" in next(e["text"] for e in ev["events"] if e["verb"] == "wrote")
            ctx = app.state.registry.get("database").context(app.state.store, app.state.registry)
            assert "\napp:\n" in ctx and "\nsecond_brain:\n  second_brain_fts (2): text\n  second_brain_items (2): id, kind, text" in ctx
            # a table no schema owns shows under `other`, last
            assert (await c.post("/api/database/action/run", json={"sql": "create table scratch(x)"})).json()["ddl"] is True
            left = (await c.get("/api/database/left")).json()
            assert left["modules"][-1] == {"name": "other", "rows": 0, "tables": [{"name": "scratch", "module": "other", "rows": 0}]}
            assert (await c.get("/api/database/table/scratch")).json()["module"] == "other"
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_database_tools_split(config):
    async def main():
        app = build(config)
        read = {t.name for t in await app.state.mcp_read.list_tools()}
        full = {t.name for t in await app.state.mcp_full.list_tools()}
        # The agent drafts and saves; only the owner's editor reaches query.execute.
        assert {t for t in full if t.startswith("db_")} == {"db_schema", "db_query", "db_explain", "db_save_query"}
        assert {"db_schema", "db_query", "db_explain"} <= read and "db_save_query" not in read
        app.state.store.close()

    run(main())
