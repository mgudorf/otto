CREATE TABLE IF NOT EXISTS memory_items (
  id         INTEGER PRIMARY KEY,
  kind       TEXT NOT NULL CHECK (kind IN ('note', 'link', 'quote', 'fact', 'task')),
  text       TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  done_at    TEXT
);
CREATE INDEX IF NOT EXISTS memory_items_created ON memory_items(created_at);

CREATE TABLE IF NOT EXISTS memory_tags (
  memory_id INTEGER NOT NULL REFERENCES memory_items(id) ON DELETE CASCADE,
  tag       TEXT NOT NULL,
  PRIMARY KEY (memory_id, tag)
);

CREATE TABLE IF NOT EXISTS memory_suggestions (
  id         INTEGER PRIMARY KEY,
  text       TEXT NOT NULL UNIQUE,
  memory_ids TEXT,                          -- JSON list
  created_at TEXT NOT NULL,
  status     TEXT NOT NULL DEFAULT 'open'   -- open | accepted | dismissed
);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(text, content='memory_items', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS memory_items_ai AFTER INSERT ON memory_items BEGIN
  INSERT INTO memory_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS memory_items_ad AFTER DELETE ON memory_items BEGIN
  INSERT INTO memory_fts(memory_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS memory_items_au AFTER UPDATE OF text ON memory_items BEGIN
  INSERT INTO memory_fts(memory_fts, rowid, text) VALUES ('delete', old.id, old.text);
  INSERT INTO memory_fts(rowid, text) VALUES (new.id, new.text);
END;
