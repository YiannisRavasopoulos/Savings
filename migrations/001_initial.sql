CREATE TABLE categories (
  id                   INTEGER PRIMARY KEY,
  name                 TEXT    NOT NULL UNIQUE COLLATE NOCASE,
  monthly_budget_cents INTEGER NOT NULL DEFAULT 0 CHECK (monthly_budget_cents >= 0),
  sort_order           INTEGER NOT NULL DEFAULT 0,
  archived             INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1))
);

CREATE TABLE expenses (
  id               INTEGER PRIMARY KEY,
  date             TEXT    NOT NULL CHECK (date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
  description      TEXT    NOT NULL DEFAULT '',
  category_id      INTEGER NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
  amount_cents     INTEGER NOT NULL CHECK (amount_cents > 0),
  their_part_cents INTEGER CHECK (their_part_cents IS NULL
                                  OR (their_part_cents >= 0 AND their_part_cents <= amount_cents)),
  notes            TEXT    NOT NULL DEFAULT '',
  created_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  updated_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX idx_expenses_date     ON expenses(date);
CREATE INDEX idx_expenses_category ON expenses(category_id);

CREATE TABLE extra_income (
  id           INTEGER PRIMARY KEY,
  date         TEXT    NOT NULL CHECK (date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
  description  TEXT    NOT NULL DEFAULT '',
  amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
  notes        TEXT    NOT NULL DEFAULT '',
  created_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  updated_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX idx_extra_income_date ON extra_income(date);

CREATE TABLE regular_income (
  id             INTEGER PRIMARY KEY,
  amount_cents   INTEGER NOT NULL CHECK (amount_cents >= 0),
  effective_from TEXT    NOT NULL UNIQUE
);

CREATE TABLE settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
INSERT INTO settings (key, value) VALUES ('period_start_day', '28');
