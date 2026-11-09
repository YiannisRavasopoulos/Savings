-- Recurring expenses (rent, subscriptions, bills). Each rule creates real, ordinary expenses on
-- its schedule, up to the end of the owner's current budget period, so upcoming ones show as
-- future-dated. Occurrence k falls on start_date + k * every_months months (the day is clamped
-- to the month's length, without drifting: a 31st stays the 31st where the month has one).
-- next_index is the first occurrence not yet created; changes only ever touch expenses dated
-- after today, so the past is never rewritten.
CREATE TABLE recurring_expenses (
  id           INTEGER PRIMARY KEY,
  user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  description  TEXT    NOT NULL CHECK (length(description) BETWEEN 1 AND 200),
  category_id  INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
  amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
  notes        TEXT    NOT NULL DEFAULT '',
  every_months INTEGER NOT NULL CHECK (every_months IN (1, 3, 6, 12)),
  start_date   TEXT    NOT NULL CHECK (start_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
  end_date     TEXT    CHECK (end_date IS NULL OR end_date >= start_date),
  next_index   INTEGER NOT NULL DEFAULT 0 CHECK (next_index >= 0),
  active       INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
  created_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX idx_recurring_user ON recurring_expenses(user_id, active);

-- The rule an expense was created from (NULL for expenses logged by hand).
ALTER TABLE expenses ADD COLUMN recurring_id INTEGER REFERENCES recurring_expenses(id) ON DELETE SET NULL;
CREATE INDEX idx_expenses_recurring ON expenses(recurring_id);
