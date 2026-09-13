CREATE TABLE IF NOT EXISTS feedback_items (
  id          INTEGER PRIMARY KEY,
  created_at  TEXT NOT NULL,
  page        TEXT NOT NULL,
  item_module TEXT,
  item_id     TEXT,
  item_text   TEXT,
  text        TEXT NOT NULL,                 -- the owner's words, verbatim
  status      TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'filed', 'failed')),
  kind        TEXT CHECK (kind IN ('bug', 'defect', 'gap', 'roadmap')),
  title       TEXT,
  summary     TEXT,
  tags        TEXT,                          -- JSON list
  ref         TEXT,                          -- existing docs/ file the note belongs in
  draft       TEXT,                          -- markdown body ready for that file
  filed_at    TEXT,
  job_id      INTEGER,
  error       TEXT,
  cleared_at  TEXT                       -- stamped by `python -m app.modules.feedback clear` once a work session has read the row
);
CREATE INDEX IF NOT EXISTS feedback_items_status ON feedback_items(status, created_at);
