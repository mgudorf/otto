-- Platform tables, prefixed app_. Module tables live in each module's schema.sql under the module's own prefix;
-- an index or trigger is named after its table. A table that changes its name is a line in app/migrate.py RENAMES.
-- All timestamps are UTC ISO-8601 strings, so string comparison orders them.

CREATE TABLE IF NOT EXISTS app_tasks (
  name             TEXT PRIMARY KEY,
  module           TEXT NOT NULL,
  interval_seconds INTEGER NOT NULL,
  resource         TEXT,
  llm              INTEGER NOT NULL DEFAULT 0,
  enabled          INTEGER NOT NULL DEFAULT 1,
  last_run         TEXT,
  next_run         TEXT,
  last_status      TEXT,
  last_result      TEXT
);

CREATE TABLE IF NOT EXISTS app_jobs (
  id          INTEGER PRIMARY KEY,
  task        TEXT NOT NULL,
  module      TEXT NOT NULL,
  resource    TEXT,
  kind        TEXT NOT NULL,      -- scheduled | action | session
  status      TEXT NOT NULL,      -- queued | running | done | failed | skipped
  queued_at   TEXT NOT NULL,
  started_at  TEXT,
  finished_at TEXT,
  result      TEXT,
  error       TEXT
);
CREATE INDEX IF NOT EXISTS app_jobs_status ON app_jobs(status);
CREATE INDEX IF NOT EXISTS app_jobs_queued ON app_jobs(queued_at);

CREATE TABLE IF NOT EXISTS app_job_logs (
  id      INTEGER PRIMARY KEY,
  job_id  INTEGER NOT NULL REFERENCES app_jobs(id) ON DELETE CASCADE,
  ts      TEXT NOT NULL,
  message TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL              -- JSON
);

CREATE TABLE IF NOT EXISTS app_cursors (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_events (
  id     INTEGER PRIMARY KEY,
  ts     TEXT NOT NULL,
  module TEXT NOT NULL,
  verb   TEXT NOT NULL,
  text   TEXT NOT NULL,
  job_id INTEGER,
  ref    TEXT
);
CREATE INDEX IF NOT EXISTS app_events_ts ON app_events(ts);

CREATE TABLE IF NOT EXISTS app_sessions (
  id        TEXT PRIMARY KEY,
  module    TEXT NOT NULL,
  opened_at TEXT NOT NULL,
  closed_at TEXT,
  title     TEXT,
  tags      TEXT,                  -- JSON list
  cli_started INTEGER NOT NULL DEFAULT 0   -- 1 once the CLI has created the session (then --resume)
);

CREATE TABLE IF NOT EXISTS app_session_turns (
  id         INTEGER PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES app_sessions(id) ON DELETE CASCADE,
  ts         TEXT NOT NULL,
  role       TEXT NOT NULL,        -- user | model | tool | system
  text       TEXT,
  tool       TEXT,
  status     TEXT
);

CREATE TABLE IF NOT EXISTS app_module_errors (
  module TEXT PRIMARY KEY,
  ts     TEXT NOT NULL,
  error  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_llm_runs (
  id         INTEGER PRIMARY KEY,
  ts         TEXT NOT NULL,
  module     TEXT NOT NULL,
  task       TEXT NOT NULL,
  job_id     INTEGER,
  status     TEXT NOT NULL,        -- running | done | failed | skipped
  minutes    REAL,
  session_id TEXT,
  budgeted   INTEGER NOT NULL DEFAULT 1   -- 0 for user-triggered runs (session close tagging)
);

-- The owner's tags on any module's row. Second Brain keeps its own second_brain_tags (its tools write there);
-- every other module's tags live here. item_id is TEXT because a module's id may be a Gmail message id.
CREATE TABLE IF NOT EXISTS app_tags (
  module  TEXT NOT NULL,
  item_id TEXT NOT NULL,
  tag     TEXT NOT NULL,            -- stripped and lowercased, so one spelling is one tag
  ts      TEXT NOT NULL,
  PRIMARY KEY (module, item_id, tag)
);
CREATE INDEX IF NOT EXISTS app_tags_tag ON app_tags(tag);
