CREATE TABLE IF NOT EXISTS finance_entries (
  id         INTEGER PRIMARY KEY,
  kind       TEXT NOT NULL CHECK (kind IN ('account', 'recurring', 'holding', 'budget')),
  name       TEXT NOT NULL,
  amount     INTEGER NOT NULL,                 -- cents
  cadence    TEXT CHECK (cadence IN ('monthly', 'yearly', 'weekly')),
  note       TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  ended_at   TEXT
);
CREATE INDEX IF NOT EXISTS finance_entries_updated ON finance_entries(updated_at);

CREATE TABLE IF NOT EXISTS finance_amounts (
  entry_id INTEGER NOT NULL REFERENCES finance_entries(id) ON DELETE CASCADE,
  ts       TEXT NOT NULL,
  amount   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS finance_amounts_entry ON finance_amounts(entry_id, ts);
