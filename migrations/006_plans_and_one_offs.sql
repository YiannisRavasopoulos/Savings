-- 1. "One-off" expenses (a car repair, a new laptop...) are real spending but not typical, so the
--    savings forecast leaves them out of "what a normal period costs".
ALTER TABLE expenses ADD COLUMN one_off INTEGER NOT NULL DEFAULT 0 CHECK (one_off IN (0, 1));

-- 2. Planned purchases. The forecast suggests when each can be bought comfortably; earlier
--    plans (lower sort_order) get first claim on projected savings.
CREATE TABLE planned_purchases (
  id           INTEGER PRIMARY KEY,
  user_id      INTEGER NOT NULL REFERENCES users(id),
  name         TEXT    NOT NULL,
  amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
  saved_cents  INTEGER NOT NULL DEFAULT 0 CHECK (saved_cents >= 0),   -- already set aside for it
  category_id  INTEGER REFERENCES categories(id) ON DELETE SET NULL,
  notes        TEXT    NOT NULL DEFAULT '',
  sort_order   INTEGER NOT NULL DEFAULT 0,
  created_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX idx_planned_purchases_user ON planned_purchases(user_id, sort_order);
