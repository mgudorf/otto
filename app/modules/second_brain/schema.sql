CREATE TABLE IF NOT EXISTS second_brain_items (
  id         INTEGER PRIMARY KEY,
  kind       TEXT NOT NULL CHECK (kind IN ('note', 'link', 'quote', 'fact', 'task')),
  text       TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  done_at    TEXT
);
CREATE INDEX IF NOT EXISTS second_brain_items_created ON second_brain_items(created_at);

CREATE TABLE IF NOT EXISTS second_brain_tags (
  item_id INTEGER NOT NULL REFERENCES second_brain_items(id) ON DELETE CASCADE,
  tag       TEXT NOT NULL,
  PRIMARY KEY (item_id, tag)
);

CREATE TABLE IF NOT EXISTS second_brain_suggestions (
  id         INTEGER PRIMARY KEY,
  text       TEXT NOT NULL UNIQUE,
  item_ids TEXT,                          -- JSON list
  created_at TEXT NOT NULL,
  status     TEXT NOT NULL DEFAULT 'open'   -- open | accepted | dismissed
);

CREATE VIRTUAL TABLE IF NOT EXISTS second_brain_fts USING fts5(text, content='second_brain_items', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS second_brain_items_ai AFTER INSERT ON second_brain_items BEGIN
  INSERT INTO second_brain_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS second_brain_items_ad AFTER DELETE ON second_brain_items BEGIN
  INSERT INTO second_brain_fts(second_brain_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS second_brain_items_au AFTER UPDATE OF text ON second_brain_items BEGIN
  INSERT INTO second_brain_fts(second_brain_fts, rowid, text) VALUES ('delete', old.id, old.text);
  INSERT INTO second_brain_fts(rowid, text) VALUES (new.id, new.text);
END;
