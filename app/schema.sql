-- Platform tables. Module tables live in each module's schema.sql.
-- All timestamps are UTC ISO-8601 strings, so string comparison orders them.

CREATE TABLE IF NOT EXISTS tasks (
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

CREATE TABLE IF NOT EXISTS jobs (
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
CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS jobs_queued ON jobs(queued_at);

CREATE TABLE IF NOT EXISTS job_logs (
  id      INTEGER PRIMARY KEY,
  job_id  INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  ts      TEXT NOT NULL,
  message TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL              -- JSON
);

CREATE TABLE IF NOT EXISTS cursors (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  id     INTEGER PRIMARY KEY,
  ts     TEXT NOT NULL,
  module TEXT NOT NULL,
  verb   TEXT NOT NULL,
  text   TEXT NOT NULL,
  job_id INTEGER,
  ref    TEXT
);
CREATE INDEX IF NOT EXISTS events_ts ON events(ts);

CREATE TABLE IF NOT EXISTS sessions (
  id        TEXT PRIMARY KEY,
  module    TEXT NOT NULL,
  opened_at TEXT NOT NULL,
  closed_at TEXT,
  title     TEXT,
  tags      TEXT,                  -- JSON list
  cli_started INTEGER NOT NULL DEFAULT 0   -- 1 once the CLI has created the session (then --resume)
);

CREATE TABLE IF NOT EXISTS session_turns (
  id         INTEGER PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  ts         TEXT NOT NULL,
  role       TEXT NOT NULL,        -- user | model | tool | system
  text       TEXT,
  tool       TEXT,
  status     TEXT
);

CREATE TABLE IF NOT EXISTS module_errors (
  module TEXT PRIMARY KEY,
  ts     TEXT NOT NULL,
  error  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS llm_runs (
  id         INTEGER PRIMARY KEY,
  ts         TEXT NOT NULL,
  module     TEXT NOT NULL,
  task       TEXT NOT NULL,
  job_id     INTEGER,
  status     TEXT NOT NULL,        -- done | failed | skipped
  minutes    REAL,
  session_id TEXT,
  budgeted   INTEGER NOT NULL DEFAULT 1   -- 0 for user-triggered runs (session close tagging)
);
