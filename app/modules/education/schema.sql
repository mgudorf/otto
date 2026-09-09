-- A topic is one of the owner's domains. Questions are asked once each; parts are graded one at a time.
CREATE TABLE IF NOT EXISTS topics (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE,
  description TEXT,                                            -- one line on what the owner wants from it, optional
  difficulty  INTEGER NOT NULL CHECK (difficulty BETWEEN 1 AND 5),
  created_at  TEXT NOT NULL,
  retired_at  TEXT
);

CREATE TABLE IF NOT EXISTS questions (
  id         INTEGER PRIMARY KEY,
  topic_id   INTEGER NOT NULL REFERENCES topics(id),
  title      TEXT NOT NULL,
  premise    TEXT NOT NULL,                                    -- the setup; any equation is introduced here
  difficulty INTEGER NOT NULL CHECK (difficulty BETWEEN 1 AND 5),
  source     TEXT NOT NULL CHECK (source IN ('nightly', 'session')),
  created_at TEXT NOT NULL,
  started_at TEXT,                                             -- at most one open question is started
  graded_at  TEXT,                                             -- set when the last part is scored
  skipped_at TEXT,
  score      INTEGER,                                          -- mean of the part scores
  UNIQUE (topic_id, title)
);
CREATE INDEX IF NOT EXISTS questions_created ON questions(created_at);

CREATE TABLE IF NOT EXISTS question_parts (
  question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  n           INTEGER NOT NULL,
  text        TEXT NOT NULL,
  score       INTEGER CHECK (score BETWEEN 0 AND 100),
  note        TEXT,                                            -- the tutor's one line on the answer
  graded_at   TEXT,
  PRIMARY KEY (question_id, n)
);

CREATE TABLE IF NOT EXISTS education_feedback (
  id          INTEGER PRIMARY KEY,
  ts          TEXT NOT NULL,
  topic_id    INTEGER REFERENCES topics(id),
  question_id INTEGER REFERENCES questions(id),
  text        TEXT NOT NULL                                    -- the owner's words, unchanged
);
