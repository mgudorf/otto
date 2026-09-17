-- Rebuilt whole on every rebuild: never written by hand.
CREATE TABLE IF NOT EXISTS graph_nodes (
  tag       TEXT PRIMARY KEY,           -- lowercased, stripped
  count     INTEGER NOT NULL,           -- distinct items and sessions carrying the tag
  items     INTEGER NOT NULL,           -- of those, Second Brain items
  sessions  INTEGER NOT NULL,
  last_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS graph_edges (
  a      TEXT NOT NULL,                 -- a < b
  b      TEXT NOT NULL,
  kind   TEXT NOT NULL CHECK (kind IN ('cooccur', 'link')),
  weight INTEGER NOT NULL,              -- cooccur: shared items; link: 1
  note   TEXT,
  PRIMARY KEY (a, b, kind)
);

-- Curation overlays: the owner's decisions, applied on every rebuild.
CREATE TABLE IF NOT EXISTS graph_merges (
  alias  TEXT PRIMARY KEY,
  target TEXT NOT NULL,                 -- never itself an alias
  ts     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS graph_pruned (
  tag TEXT PRIMARY KEY,
  ts  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS graph_links (
  a    TEXT NOT NULL,                   -- a < b
  b    TEXT NOT NULL,
  note TEXT,
  ts   TEXT NOT NULL,
  PRIMARY KEY (a, b)
);
