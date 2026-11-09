-- User accounts. Every user has their own categories, budgets, expenses and income.
--
-- The single-user tables are rebuilt with an owner. Rows from before accounts existed are not
-- carried over: there was no data to keep, and no user to give it to.
--
-- Ownership:
--   categories.user_id, extra_income.user_id, regular_income.user_id -> users
--   expenses and category_budgets belong to a user through their category.
-- users rows are never deleted by cascade: deleting a user removes their data explicitly first.

DROP TABLE category_budgets;
DROP TABLE expenses;
DROP TABLE extra_income;
DROP TABLE regular_income;
DROP TABLE categories;
DELETE FROM settings WHERE key IN ('period_start_day', 'theme');   -- now per user

CREATE TABLE users (
  id                   INTEGER PRIMARY KEY,
  username             TEXT    NOT NULL UNIQUE COLLATE NOCASE,
  display_name         TEXT    NOT NULL,
  password_hash        TEXT    NOT NULL,
  status               TEXT    NOT NULL DEFAULT 'pending'
                               CHECK (status IN ('pending', 'active', 'disabled')),
  must_change_password INTEGER NOT NULL DEFAULT 0 CHECK (must_change_password IN (0, 1)),
  period_start_day     INTEGER NOT NULL DEFAULT 28 CHECK (period_start_day BETWEEN 1 AND 28),
  theme                TEXT    NOT NULL DEFAULT 'auto',
  created_at           TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  approved_at          TEXT,
  last_login_at        TEXT
);

CREATE TABLE sessions (
  token_hash   TEXT    PRIMARY KEY,           -- sha256 of the cookie value; the token itself is never stored
  user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  last_seen_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  expires_at   TEXT    NOT NULL,
  user_agent   TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX idx_sessions_user ON sessions(user_id);

-- The admin is a separate login, not a user: it has no budget data of its own.
CREATE TABLE admin_account (
  id            INTEGER PRIMARY KEY CHECK (id = 1),
  username      TEXT    NOT NULL,
  password_hash TEXT    NOT NULL,
  created_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE admin_sessions (
  token_hash TEXT PRIMARY KEY,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  expires_at TEXT NOT NULL
);

CREATE TABLE categories (
  id         INTEGER PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id),
  name       TEXT    NOT NULL COLLATE NOCASE,
  sort_order INTEGER NOT NULL DEFAULT 0,
  archived   INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1)),
  UNIQUE (user_id, name)
);
CREATE INDEX idx_categories_user ON categories(user_id);

CREATE TABLE category_budgets (
  id                   INTEGER PRIMARY KEY,
  category_id          INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
  monthly_budget_cents INTEGER NOT NULL CHECK (monthly_budget_cents >= 0),
  effective_from       TEXT    NOT NULL CHECK (effective_from GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
  UNIQUE (category_id, effective_from)
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
  user_id      INTEGER NOT NULL REFERENCES users(id),
  date         TEXT    NOT NULL CHECK (date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
  description  TEXT    NOT NULL DEFAULT '',
  amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
  notes        TEXT    NOT NULL DEFAULT '',
  created_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  updated_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX idx_extra_income_user_date ON extra_income(user_id, date);

CREATE TABLE regular_income (
  id             INTEGER PRIMARY KEY,
  user_id        INTEGER NOT NULL REFERENCES users(id),
  amount_cents   INTEGER NOT NULL CHECK (amount_cents >= 0),
  effective_from TEXT    NOT NULL,
  UNIQUE (user_id, effective_from)
);
