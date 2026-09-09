"""Database module: the read-only connection, run/explain/save through the app, and the tool split."""

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


def test_read_only_refuses_writes(store):
    conn = store.read_only()
    assert conn.execute("SELECT 1").fetchone() == (1,)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        conn.execute("INSERT INTO cursors(key, value) VALUES ('k', 'v')")
    assert "readonly" in query.run(store, "INSERT INTO cursors(key, value) VALUES ('k', 'v')", 10, 1)["error"]
    assert store.scalar("SELECT COUNT(*) FROM cursors") == 0
    endless = "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT COUNT(*) FROM c"
    assert query.run(store, endless, 10, 0.1)["error"].startswith("interrupted")
    assert query.run(store, "SELECT 1; SELECT 2", 10, 1)["error"]
    assert query.run(store, "   ", 10, 1)["error"] == "empty statement"
    assert conn.execute("SELECT 1").fetchone() == (1,)  # still usable after an interruption


def test_database_run_explain_save(config):
    config = dataclasses.replace(config, database=Database(max_rows=2, max_seconds=5))

    async def main():
        app = build(config)
        await app.state.runner.start()
        async with client_for(app) as c:
            for text in ("a", "b", "c"):
                await c.post("/api/memory/action/capture", json={"kind": "note", "text": text})
            r = (await c.post("/api/database/action/run", json={"sql": "select id, text from memories order by id"})).json()
            assert r["columns"] == ["id", "text"] and r["total"] == 2 and r["truncated"] is True and r["rows"][0][1] == "a"
            r = (await c.post("/api/database/action/run", json={"sql": "delete from memories"})).json()
            assert "readonly" in r["error"]
            assert app.state.store.scalar("SELECT COUNT(*) FROM memories") == 3
            r = (await c.post("/api/database/action/explain", json={"sql": "select * from memories where id = 1;"})).json()
            assert r["lines"] and "memories" in r["lines"][0]
            left = (await c.get("/api/database/left")).json()
            tables = {x["text"]: x["stampText"] for x in left["groups"][0]["rows"]}
            assert tables["memories"] == "3" and "memories_fts" in tables and "memories_fts_data" not in tables and "sqlite_sequence" not in tables
            qid = (await c.post("/api/database/action/save", json={"name": "recent", "sql": "select * from memories"})).json()["id"]
            saved = (await c.get("/api/database/left")).json()["groups"][1]
            assert saved["count"] == 1 and saved["rows"][0]["text"] == "recent" and saved["rows"][0]["query_id"] == qid and saved["rows"][0]["sql"].startswith("select")
            assert (await c.post("/api/database/action/save", json={"name": "recent", "sql": "select id from memories"})).json()["id"] == qid
            assert (await c.post("/api/database/action/save", json={"name": "", "sql": "x"})).status_code != 200
            assert (await c.post("/api/database/action/delete", json={"id": qid})).status_code == 200
            assert (await c.get("/api/database/left")).json()["groups"][1]["count"] == 0
            blank = (await c.get("/api/database/blank")).json()
            assert blank["db"] == "otto.db" and blank["size_bytes"] > 0 and blank["tables"] == len(tables)
            db = next(n for n in (await c.get("/api/home/numbers")).json() if n["module"] == "database")
            assert db["label"] == "database" and db["value"].endswith("B")
            ev = (await c.get("/api/events?module=database")).json()
            assert [e["verb"] for e in ev["events"]][:3] == ["deleted", "saved", "saved"]
            assert "memories (3): id, kind, text" in app.state.registry.get("database").context(app.state.store, app.state.registry)
        await app.state.runner.drain(1)
        app.state.store.close()

    run(main())


def test_database_tools_split(config):
    async def main():
        app = build(config)
        read = {t.name for t in await app.state.mcp_read.list_tools()}
        full = {t.name for t in await app.state.mcp_full.list_tools()}
        assert {"db_schema", "db_query", "db_explain"} <= read and "db_save_query" not in read
        assert {"db_schema", "db_query", "db_explain", "db_save_query"} <= full
        app.state.store.close()

    run(main())
