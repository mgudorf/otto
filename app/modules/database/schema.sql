CREATE TABLE IF NOT EXISTS db_queries (
  id         INTEGER PRIMARY KEY,
  name       TEXT NOT NULL UNIQUE,
  sql        TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
