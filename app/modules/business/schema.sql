CREATE TABLE IF NOT EXISTS business_items (
  id         INTEGER PRIMARY KEY,
  kind       TEXT NOT NULL CHECK (kind IN ('plan', 'person', 'event', 'document', 'lead')),
  text       TEXT NOT NULL,
  ref        TEXT,                              -- URL for a lead or captured item, absolute path for a document
  why        TEXT,                              -- scout's one-line reason, leads only
  status     TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'accepted', 'dismissed')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS business_items_ref ON business_items(kind, ref) WHERE ref IS NOT NULL;
CREATE INDEX IF NOT EXISTS business_items_created ON business_items(created_at);
