-- A topic is one of the owner's domains. A question is one shared setup (definitions, then a premise) with lettered
-- parts; the owner answers parts on the page, the tutor grades them in the session, and the owner completes the quiz.
CREATE TABLE IF NOT EXISTS education_topics (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE,
  description TEXT,                                            -- one line on what the owner wants from it, optional
  difficulty  INTEGER NOT NULL CHECK (difficulty BETWEEN 1 AND 10),  -- 1-2 introduction, 3-5 intro course, 6-8 advanced/masters, 9-10 expert
  created_at  TEXT NOT NULL,
  retired_at  TEXT
);

CREATE TABLE IF NOT EXISTS education_questions (
  id           INTEGER PRIMARY KEY,
  topic_id     INTEGER NOT NULL REFERENCES education_topics(id),
  title        TEXT NOT NULL,                                  -- 3 to 8 words naming what the question is about
  topic_tag    TEXT,                                           -- the facet within the topic, 2 to 5 words; NULL on v0 rows
  definitions  TEXT,                                           -- every relation and variable the parts draw on: markdown, math in LaTeX; NULL on rows older than v2
  premise      TEXT NOT NULL,                                  -- the scenario every part draws on: markdown, math in LaTeX
  difficulty   INTEGER NOT NULL CHECK (difficulty BETWEEN 1 AND 10),
  source       TEXT NOT NULL CHECK (source IN ('nightly', 'session')),  -- session: on the owner's demand, from the page or the tutor
  tags         TEXT NOT NULL DEFAULT '[]',                     -- the owner's labels, a JSON array of strings
  created_at   TEXT NOT NULL,
  opened_at    TEXT,                                           -- last time the page opened it; the latest one is the tutor's context
  started_at   TEXT,                                           -- the first answer
  completed_at TEXT,                                           -- the owner pressed Complete quiz; every part was scored
  score        INTEGER,                                        -- mean of the part scores once every part is scored
  deleted_at   TEXT,                                           -- thrown away by the owner: off every list, kept so the generator never re-asks it
  UNIQUE (topic_id, title)
);
CREATE INDEX IF NOT EXISTS education_questions_created ON education_questions(created_at);

CREATE TABLE IF NOT EXISTS education_question_parts (
  question_id INTEGER NOT NULL REFERENCES education_questions(id) ON DELETE CASCADE,
  n           INTEGER NOT NULL,                                -- 1-based; shown as (a), (b), ...
  title       TEXT,                                            -- 2 to 5 words naming the part; NULL on rows older than v2
  text        TEXT NOT NULL,                                   -- the ask, markdown
  rubric      TEXT,                                            -- grading guidance; never shown before the part is graded; NULL on v0 rows
  answer      TEXT,                                            -- the owner's latest answer, typed on the page; a new one clears the grade below
  answered_at TEXT,
  verdict     TEXT CHECK (verdict IN ('correct', 'partial', 'incorrect')),
  score       INTEGER CHECK (score BETWEEN 0 AND 100),
  note        TEXT,                                            -- the tutor's record of the grade; the explanation itself is in the session
  graded_at   TEXT,
  PRIMARY KEY (question_id, n)
);

CREATE TABLE IF NOT EXISTS education_feedback (
  id          INTEGER PRIMARY KEY,
  ts          TEXT NOT NULL,
  topic_id    INTEGER REFERENCES education_topics(id),
  question_id INTEGER REFERENCES education_questions(id),      -- kept when the question is deleted; the words still describe it
  text        TEXT NOT NULL                                    -- the owner's words, unchanged
);
