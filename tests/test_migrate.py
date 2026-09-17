"""The rename step at boot: an older database comes up under the current table and module names with its rows, indexes,
triggers and full-text search intact, once, behind a backup; the feedback CLI refuses a database the daemon has not brought up."""

import sqlite3

import pytest

from app import migrate
from app.daemon import build
from app.modules.feedback.queue import main as feedback_main

# Tables as the schemas created them before 2026-09-13, with rows: platform and module names without their prefixes,
# and the module then called memory (second_brain since 2026-09-17) named in rows and columns.
OLD = """
CREATE TABLE jobs (id INTEGER PRIMARY KEY, task TEXT NOT NULL, module TEXT NOT NULL, resource TEXT, kind TEXT NOT NULL, status TEXT NOT NULL, queued_at TEXT NOT NULL, started_at TEXT, finished_at TEXT, result TEXT, error TEXT);
CREATE INDEX jobs_status ON jobs(status);
CREATE TABLE job_logs (id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE, ts TEXT NOT NULL, message TEXT NOT NULL);
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE cursors (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE sessions (id TEXT PRIMARY KEY, module TEXT NOT NULL, opened_at TEXT NOT NULL, closed_at TEXT, title TEXT, tags TEXT);
CREATE TABLE memories (id INTEGER PRIMARY KEY, kind TEXT NOT NULL CHECK (kind IN ('note', 'link', 'quote', 'fact', 'task')), text TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, done_at TEXT);
CREATE INDEX memories_created ON memories(created_at);
CREATE TABLE memory_tags (memory_id INTEGER NOT NULL REFERENCES memories(id) ON DELETE CASCADE, tag TEXT NOT NULL, PRIMARY KEY (memory_id, tag));
CREATE TABLE memory_suggestions (id INTEGER PRIMARY KEY, text TEXT NOT NULL UNIQUE, memory_ids TEXT, created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open');
CREATE VIRTUAL TABLE memories_fts USING fts5(text, content='memories', content_rowid='id');
CREATE TRIGGER memories_ai AFTER INSERT ON memories BEGIN INSERT INTO memories_fts(rowid, text) VALUES (new.id, new.text); END;
CREATE TRIGGER memories_ad AFTER DELETE ON memories BEGIN INSERT INTO memories_fts(memories_fts, rowid, text) VALUES ('delete', old.id, old.text); END;
CREATE TABLE feedback (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, page TEXT NOT NULL, item_module TEXT, item_id TEXT, item_text TEXT, text TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'filed', 'failed')), kind TEXT, title TEXT, summary TEXT, tags TEXT, ref TEXT, draft TEXT, filed_at TEXT, job_id INTEGER, error TEXT);
CREATE INDEX feedback_status ON feedback(status, created_at);
CREATE TABLE db_queries (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, sql TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE graph_nodes (tag TEXT PRIMARY KEY, count INTEGER NOT NULL, memories INTEGER NOT NULL, sessions INTEGER NOT NULL, last_seen TEXT NOT NULL);
INSERT INTO jobs(id, task, module, resource, kind, status, queued_at) VALUES (1, 'memory.suggest', 'memory', 'memory', 'scheduled', 'done', '2026-09-01T00:00:00+00:00');
INSERT INTO job_logs(job_id, ts, message) VALUES (1, '2026-09-01T00:00:01+00:00', 'hello');
INSERT INTO settings VALUES ('ui.start_page', '"memory"');
INSERT INTO settings VALUES ('modules.memory.scheduled', 'false');
INSERT INTO cursors VALUES ('memory.suggest', '2026-09-01T00:00:00+00:00');
INSERT INTO sessions(id, module, opened_at, closed_at, title, tags) VALUES ('s1', 'memory', '2026-09-01T00:00:00+00:00', '2026-09-01T00:01:00+00:00', 'one', '["sky"]');
INSERT INTO memories(id, kind, text, created_at, updated_at) VALUES (7, 'note', 'the sky is blue', '2026-09-01T00:00:00+00:00', '2026-09-01T00:00:00+00:00');
INSERT INTO memory_tags VALUES (7, 'sky');
INSERT INTO memory_suggestions(id, text, memory_ids, created_at) VALUES (1, 'look up', '[7]', '2026-09-01T00:00:00+00:00');
INSERT INTO feedback(created_at, page, text, status) VALUES ('2026-09-02T00:00:00+00:00', 'memory', 'a note', 'filed');
INSERT INTO db_queries VALUES (1, 'recent', 'select * from memories', '2026-09-01T00:00:00+00:00', '2026-09-01T00:00:00+00:00');
INSERT INTO graph_nodes VALUES ('sky', 2, 1, 1, '2026-09-01T00:00:00+00:00');
"""


def _old_db(config):
    config.data.db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.data.db)
    conn.executescript(OLD)
    conn.close()


def _backups(config, step="rename"):
    return sorted((config.data.db.parent / "backups").glob(f"otto-*-pre-{step}.db"))


def test_boot_renames_an_older_database(config):
    _old_db(config)
    app = build(config)
    store = app.state.store
    names = {r["name"] for r in store.query("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert not names & set(migrate.RENAMES)
    assert {"app_jobs", "app_job_logs", "app_settings", "second_brain_items", "second_brain_fts", "feedback_items", "database_queries"} <= names
    # the rows came along, references and the settings seed included; feedback's setup then added its column
    assert store.one("SELECT j.status, l.message FROM app_jobs j JOIN app_job_logs l ON l.job_id = j.id") == {"status": "done", "message": "hello"}
    assert store.setting("ui.page_size") == config.ui.page_size
    assert store.one("SELECT status, cleared_at FROM feedback_items") == {"status": "filed", "cleared_at": None}
    assert store.scalar("SELECT sql FROM database_queries") == "select * from memories"
    assert "second_brain_items" in store.scalar("SELECT sql FROM sqlite_master WHERE name = 'second_brain_tags'")
    # the module's old name left every row that carried it; its settings and cursor kept their values
    assert store.one("SELECT task, module, resource FROM app_jobs") == {"task": "second_brain.suggest", "module": "second_brain", "resource": "second_brain"}
    assert store.scalar("SELECT module FROM app_sessions") == "second_brain" and store.scalar("SELECT page FROM feedback_items") == "second_brain"
    assert store.cursor("second_brain.suggest") == "2026-09-01T00:00:00+00:00" and store.cursor("memory.suggest") is None
    assert store.setting("ui.start_page") == "second_brain" and store.setting("modules.second_brain.scheduled") is False
    assert not [k for k in store.all_settings() if "memory" in k]
    # the columns named after the old name were renamed in place by the modules' setup, rows kept
    assert store.query("SELECT item_id, tag FROM second_brain_tags") == [{"item_id": 7, "tag": "sky"}]
    assert store.query("SELECT id, item_ids FROM second_brain_suggestions") == [{"id": 1, "item_ids": "[7]"}]
    assert store.query("SELECT tag, items FROM graph_nodes") == [{"tag": "sky", "items": 1}]
    # the search index was rebuilt from its rows and its triggers follow the new names
    assert store.query("SELECT rowid FROM second_brain_fts WHERE second_brain_fts MATCH 'sky'") == [{"rowid": 7}]
    store.execute("INSERT INTO second_brain_items(kind, text, created_at, updated_at) VALUES ('note', 'grass is green', 't', 't')")
    assert store.scalar("SELECT COUNT(*) FROM second_brain_fts WHERE second_brain_fts MATCH 'grass'") == 1
    objects = {(r["type"], r["name"]) for r in store.query("SELECT type, name FROM sqlite_master WHERE type IN ('index', 'trigger') AND sql IS NOT NULL")}
    assert {("index", "app_jobs_status"), ("index", "second_brain_items_created"), ("index", "feedback_items_status"), ("trigger", "second_brain_items_ai")} <= objects
    assert not {n for _, n in objects} & {"jobs_status", "memories_created", "feedback_status", "memories_ai", "memories_ad"}
    assert store.query("PRAGMA foreign_key_check") == []
    with store.raw() as conn:
        assert migrate.pending(conn) == {} and migrate.pending_modules(conn) == {}
    # one backup of the old shape per step, and a second boot finds nothing to do
    assert len(_backups(config)) == 1 and len(_backups(config, "module-rename")) == 1
    old = sqlite3.connect(_backups(config)[0])
    assert old.execute("SELECT text FROM memories").fetchone() == ("the sky is blue",)
    old.close()
    store.close()
    app = build(config)
    assert app.state.store.scalar("SELECT COUNT(*) FROM second_brain_items") == 2
    assert len(_backups(config)) == 1 and len(_backups(config, "module-rename")) == 1
    app.state.store.close()


def test_rename_refuses_a_filled_new_name(store, tmp_path):
    store.migrate("CREATE TABLE memories (id INTEGER PRIMARY KEY, text TEXT); INSERT INTO memories VALUES (1, 'kept');")
    store.migrate("CREATE TABLE second_brain_items (id INTEGER PRIMARY KEY, text TEXT); INSERT INTO second_brain_items VALUES (2, 'filled');")
    with pytest.raises(RuntimeError, match="both exist"):
        migrate.rename_tables(store, tmp_path / "backups")
    assert store.scalar("SELECT text FROM memories") == "kept"     # rolled back, nothing moved
    store.execute("DELETE FROM second_brain_items")                  # an empty one is what a schema that ran first leaves
    assert migrate.rename_tables(store, tmp_path / "backups") == []
    assert store.query("SELECT id, text FROM second_brain_items") == [{"id": 1, "text": "kept"}]
    with store.raw() as conn:
        assert migrate.pending(conn) == {}


def test_feedback_cli_waits_for_the_daemon(config, capsys):
    _old_db(config)
    assert feedback_main(["list", "feedback"], config) == 1
    assert "start the daemon" in capsys.readouterr().err
    build(config).state.store.close()
    assert feedback_main(["list", "second_brain"], config) == 0
    # a row that still names a module by an old name is the same refusal: the daemon rewrites it at its next boot
    conn = sqlite3.connect(config.data.db)
    conn.execute("INSERT INTO feedback_items(created_at, page, text) VALUES ('2026-09-03T00:00:00+00:00', 'memory', 'late')")
    conn.commit()
    conn.close()
    assert feedback_main(["list", "second_brain"], config) == 1
    assert "older names" in capsys.readouterr().err
