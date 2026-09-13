CREATE TABLE IF NOT EXISTS web_search_topics (
  id         INTEGER PRIMARY KEY,
  kind       TEXT NOT NULL CHECK (kind IN ('money', 'work', 'learn')),
  text       TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS web_search_findings (
  id         INTEGER PRIMARY KEY,
  topic_id   INTEGER,                          -- the topic that produced it; kept after the topic is removed
  kind       TEXT NOT NULL CHECK (kind IN ('money', 'work', 'learn')),
  title      TEXT NOT NULL,
  url        TEXT NOT NULL UNIQUE,
  summary    TEXT NOT NULL,
  found_at   TEXT NOT NULL,
  status     TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'agreed', 'disagreed')),
  decided_at TEXT
);
CREATE INDEX IF NOT EXISTS web_search_findings_found ON web_search_findings(found_at);
