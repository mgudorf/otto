"""The rename step at boot: an older database comes up under the current table names with its rows, indexes, triggers
and full-text search intact, once, behind a backup; the feedback CLI refuses a database the daemon has not brought up."""

import sqlite3

import pytest

from app import migrate
from app.daemon import build
from app.modules.feedback.queue import main as feedback_main

# Tables as the schemas created them before 2026-09-13, with rows: platform and module names without their prefixes.
OLD = """
CREATE TABLE jobs (id INTEGER PRIMARY KEY, task TEXT NOT NULL, module TEXT NOT NULL, resource TEXT, kind TEXT NOT NULL, status TEXT NOT NULL, queued_at TEXT NOT NULL, started_at TEXT, finished_at TEXT, result TEXT, error TEXT);
CREATE INDEX jobs_status ON jobs(status);
CREATE TABLE job_logs (id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE, ts TEXT NOT NULL, message TEXT NOT NULL);
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE memories (id INTEGER PRIMARY KEY, kind TEXT NOT NULL CHECK (kind IN ('note', 'link', 'quote', 'fact', 'task')), text TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, done_at TEXT);
CREATE INDEX memories_created ON memories(created_at);
CREATE TABLE memory_tags (memory_id INTEGER NOT NULL REFERENCES memories(id) ON DELETE CASCADE, tag TEXT NOT NULL, PRIMARY KEY (memory_id, tag));
CREATE VIRTUAL TABLE memories_fts USING fts5(text, content='memories', content_rowid='id');
CREATE TRIGGER memories_ai AFTER INSERT ON memories BEGIN INSERT INTO memories_fts(rowid, text) VALUES (new.id, new.text); END;
CREATE TRIGGER memories_ad AFTER DELETE ON memories BEGIN INSERT INTO memories_fts(memories_fts, rowid, text) VALUES ('delete', old.id, old.text); END;
CREATE TABLE feedback (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, page TEXT NOT NULL, item_module TEXT, item_id TEXT, item_text TEXT, text TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'filed', 'failed')), kind TEXT, title TEXT, summary TEXT, tags TEXT, ref TEXT, draft TEXT, filed_at TEXT, job_id INTEGER, error TEXT);
CREATE INDEX feedback_status ON feedback(status, created_at);
CREATE TABLE db_queries (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, sql TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
INSERT INTO jobs(id, task, module, kind, status, queued_at) VALUES (1, 'memory.suggest', 'memory', 'scheduled', 'done', '2026-09-01T00:00:00+00:00');
INSERT INTO job_logs(job_id, ts, message) VALUES (1, '2026-09-01T00:00:01+00:00', 'hello');
INSERT INTO settings VALUES ('ui.start_page', '"memory"');
INSERT INTO memories(id, kind, text, created_at, updated_at) VALUES (7, 'note', 'the sky is blue', '2026-09-01T00:00:00+00:00', '2026-09-01T00:00:00+00:00');
INSERT INTO memory_tags VALUES (7, 'sky');
INSERT INTO feedback(created_at, page, text, status) VALUES ('2026-09-02T00:00:00+00:00', 'memory', 'a note', 'filed');
INSERT INTO db_queries VALUES (1, 'recent', 'select * from memories', '2026-09-01T00:00:00+00:00', '2026-09-01T00:00:00+00:00');
"""


def _old_db(config):
    config.data.db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.data.db)
    conn.executescript(OLD)
    conn.close()


def _backups(config):
    return sorted((config.data.db.parent / "backups").glob("otto-*-pre-rename.db"))


def test_boot_renames_an_older_database(config):
    _old_db(config)
    app = build(config)
    store = app.state.store
    names = {r["name"] for r in store.query("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert not names & set(migrate.RENAMES)
    assert {"app_jobs", "app_job_logs", "app_settings", "memory_items", "memory_fts", "feedback_items", "database_queries"} <= names
    # the rows came along, references and the settings seed included; feedback's setup then added its column
    assert store.one("SELECT j.status, l.message FROM app_jobs j JOIN app_job_logs l ON l.job_id = j.id") == {"status": "done", "message": "hello"}
    assert store.setting("ui.start_page") == "memory" and store.setting("ui.page_size") == config.ui.page_size
    assert store.query("SELECT memory_id, tag FROM memory_tags") == [{"memory_id": 7, "tag": "sky"}]
    assert store.one("SELECT status, cleared_at FROM feedback_items") == {"status": "filed", "cleared_at": None}
    assert store.scalar("SELECT sql FROM database_queries") == "select * from memories"
    assert "memory_items" in store.scalar("SELECT sql FROM sqlite_master WHERE name = 'memory_tags'")
    # the search index was rebuilt from its rows and its triggers follow the new names
    assert store.query("SELECT rowid FROM memory_fts WHERE memory_fts MATCH 'sky'") == [{"rowid": 7}]
    store.execute("INSERT INTO memory_items(kind, text, created_at, updated_at) VALUES ('note', 'grass is green', 't', 't')")
    assert store.scalar("SELECT COUNT(*) FROM memory_fts WHERE memory_fts MATCH 'grass'") == 1
    objects = {(r["type"], r["name"]) for r in store.query("SELECT type, name FROM sqlite_master WHERE type IN ('index', 'trigger') AND sql IS NOT NULL")}
    assert {("index", "app_jobs_status"), ("index", "memory_items_created"), ("index", "feedback_items_status"), ("trigger", "memory_items_ai")} <= objects
    assert not {n for _, n in objects} & {"jobs_status", "memories_created", "feedback_status", "memories_ai", "memories_ad"}
    assert store.query("PRAGMA foreign_key_check") == []
    # one backup of the old shape, and a second boot finds nothing to do
    assert len(_backups(config)) == 1
    old = sqlite3.connect(_backups(config)[0])
    assert old.execute("SELECT text FROM memories").fetchone() == ("the sky is blue",)
    old.close()
    store.close()
    app = build(config)
    assert app.state.store.scalar("SELECT COUNT(*) FROM memory_items") == 2 and len(_backups(config)) == 1
    app.state.store.close()


def test_rename_refuses_a_filled_new_name(store, tmp_path):
    store.migrate("CREATE TABLE memories (id INTEGER PRIMARY KEY, text TEXT); INSERT INTO memories VALUES (1, 'kept');")
    store.migrate("CREATE TABLE memory_items (id INTEGER PRIMARY KEY, text TEXT); INSERT INTO memory_items VALUES (2, 'filled');")
    with pytest.raises(RuntimeError, match="both exist"):
        migrate.rename_tables(store, tmp_path / "backups")
    assert store.scalar("SELECT text FROM memories") == "kept"     # rolled back, nothing moved
    store.execute("DELETE FROM memory_items")                        # an empty one is what a schema that ran first leaves
    assert migrate.rename_tables(store, tmp_path / "backups") == []
    assert store.query("SELECT id, text FROM memory_items") == [{"id": 1, "text": "kept"}]
    with store.raw() as conn:
        assert migrate.pending(conn) == {}


def test_feedback_cli_waits_for_the_daemon(config, capsys):
    _old_db(config)
    assert feedback_main(["list", "feedback"], config) == 1
    assert "start the daemon" in capsys.readouterr().err
    build(config).state.store.close()
    assert feedback_main(["list", "feedback"], config) == 0
