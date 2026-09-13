CREATE TABLE IF NOT EXISTS social_items (
  id         INTEGER PRIMARY KEY,
  kind       TEXT NOT NULL CHECK (kind IN ('interest', 'event')),
  text       TEXT NOT NULL,
  ref        TEXT,                              -- the listing URL for an event, an optional link on an interest
  why        TEXT,                              -- scout's one line tying the event to an interest or a category
  category   TEXT CHECK (category IN ('class', 'meet', 'biz', 'music', 'art', 'food', 'game', 'animal', 'film', 'local')),
  city       TEXT,                              -- the town it sits in, one of config social.cities
  venue      TEXT,
  starts_at  TEXT,                              -- naive local 'YYYY-MM-DDTHH:MM'; a T00:00 means the listing gave no time
  status     TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'going', 'dismissed')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK (kind = 'interest' OR (starts_at IS NOT NULL AND category IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS social_items_ref ON social_items(kind, ref, starts_at) WHERE ref IS NOT NULL;
CREATE INDEX IF NOT EXISTS social_items_starts ON social_items(starts_at);
CREATE INDEX IF NOT EXISTS social_items_created ON social_items(created_at);
