-- The owner's schedules and the output of script runs. A notebook's outputs live in the notebook itself.
CREATE TABLE IF NOT EXISTS science_schedules (
  path          TEXT PRIMARY KEY,   -- file id under science.root
  every_seconds INTEGER NOT NULL,
  at            TEXT,               -- HH:MM local the first run was anchored to, NULL for one interval from when it was set
  next_run      TEXT NOT NULL,
  last_run      TEXT,
  last_status   TEXT,               -- done | failed
  last_result   TEXT
);

CREATE TABLE IF NOT EXISTS science_script_runs (
  id          INTEGER PRIMARY KEY,
  path        TEXT NOT NULL,
  started_at  TEXT NOT NULL,
  finished_at TEXT,
  status      TEXT NOT NULL,        -- running | done | failed
  exit_code   INTEGER,
  output      TEXT NOT NULL DEFAULT ''   -- stdout and stderr merged, in order
);
CREATE INDEX IF NOT EXISTS science_script_runs_path ON science_script_runs(path, id);
