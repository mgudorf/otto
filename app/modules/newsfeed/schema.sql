-- Searches the agent writes, entries the nightly run returns, tags on either.
CREATE TABLE IF NOT EXISTS newsfeed_searches (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE,
  prompt      TEXT NOT NULL,                -- the owner's words: what to look for, where, what to skip
  every_days  INTEGER NOT NULL,
  cap         INTEGER NOT NULL,             -- new entries one run may add
  created_at  TEXT NOT NULL,
  next_run    TEXT NOT NULL,                -- local YYYY-MM-DD; due on the first nightly run on or after it
  last_run    TEXT,
  last_result TEXT
);

CREATE TABLE IF NOT EXISTS newsfeed_items (
  id           INTEGER PRIMARY KEY,
  search_id    INTEGER REFERENCES newsfeed_searches(id) ON DELETE SET NULL,   -- kept after its search is killed
  text         TEXT NOT NULL,
  url          TEXT NOT NULL UNIQUE,
  summary      TEXT,
  starts_at    TEXT,                        -- local YYYY-MM-DD or YYYY-MM-DDTHH:MM when it happens on a day
  follow_up_at TEXT,                        -- local YYYY-MM-DD; an accepted entry past it joins the next run's prompt, once
  follows      INTEGER,                     -- the entry this one followed up on
  found_at     TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'accepted', 'dismissed')),
  decided_at   TEXT
);
CREATE INDEX IF NOT EXISTS newsfeed_items_found ON newsfeed_items(found_at);
CREATE INDEX IF NOT EXISTS newsfeed_items_search ON newsfeed_items(search_id);

CREATE TABLE IF NOT EXISTS newsfeed_tags (
  kind TEXT NOT NULL CHECK (kind IN ('search', 'item')),
  ref  INTEGER NOT NULL,
  tag  TEXT NOT NULL,
  PRIMARY KEY (kind, ref, tag)
);
