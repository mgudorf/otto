CREATE TABLE IF NOT EXISTS email_messages (
  n             INTEGER PRIMARY KEY,          -- stable rowid for FTS; survives VACUUM
  id            TEXT NOT NULL UNIQUE,         -- Gmail message id
  thread_id     TEXT,
  from_name     TEXT NOT NULL DEFAULT '',
  from_addr     TEXT NOT NULL DEFAULT '',
  to_addr       TEXT NOT NULL DEFAULT '',
  subject       TEXT NOT NULL DEFAULT '',
  snippet       TEXT NOT NULL DEFAULT '',
  internal_date TEXT NOT NULL,                -- UTC ISO
  labels        TEXT NOT NULL DEFAULT '[]',   -- JSON list of Gmail label ids
  synced_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS email_messages_date ON email_messages(internal_date);

CREATE TABLE IF NOT EXISTS email_bodies (      -- fetched on first open, through the read client
  message_id  TEXT PRIMARY KEY REFERENCES email_messages(id) ON DELETE CASCADE,
  text        TEXT NOT NULL,                  -- text/plain parts, else the html as text, else the snippet
  html        TEXT,                           -- text/html parts through body.sanitize(); NULL when there are none
  attachments TEXT NOT NULL DEFAULT '[]'      -- JSON list of filenames; the files themselves are never fetched
);

CREATE TABLE IF NOT EXISTS email_triage (
  message_id TEXT PRIMARY KEY REFERENCES email_messages(id) ON DELETE CASCADE,
  priority   TEXT NOT NULL CHECK (priority IN ('high', 'normal', 'low')),
  reason     TEXT NOT NULL DEFAULT '',
  ts         TEXT NOT NULL,
  source     TEXT NOT NULL                    -- scheduled | session
);

CREATE VIRTUAL TABLE IF NOT EXISTS email_fts USING fts5(from_name, from_addr, subject, snippet, content='email_messages', content_rowid='n');
CREATE TRIGGER IF NOT EXISTS email_messages_ai AFTER INSERT ON email_messages BEGIN
  INSERT INTO email_fts(rowid, from_name, from_addr, subject, snippet) VALUES (new.n, new.from_name, new.from_addr, new.subject, new.snippet);
END;
CREATE TRIGGER IF NOT EXISTS email_messages_ad AFTER DELETE ON email_messages BEGIN
  INSERT INTO email_fts(email_fts, rowid, from_name, from_addr, subject, snippet) VALUES ('delete', old.n, old.from_name, old.from_addr, old.subject, old.snippet);
END;
CREATE TRIGGER IF NOT EXISTS email_messages_au AFTER UPDATE OF from_name, from_addr, subject, snippet ON email_messages BEGIN
  INSERT INTO email_fts(email_fts, rowid, from_name, from_addr, subject, snippet) VALUES ('delete', old.n, old.from_name, old.from_addr, old.subject, old.snippet);
  INSERT INTO email_fts(rowid, from_name, from_addr, subject, snippet) VALUES (new.n, new.from_name, new.from_addr, new.subject, new.snippet);
END;
