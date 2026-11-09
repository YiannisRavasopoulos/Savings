-- Category budgets get a history, like regular income: a period uses the latest
-- row whose effective_from <= the period's last day (no row = budget 0).
CREATE TABLE category_budgets (
  id                   INTEGER PRIMARY KEY,
  category_id          INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
  monthly_budget_cents INTEGER NOT NULL CHECK (monthly_budget_cents >= 0),
  effective_from       TEXT    NOT NULL CHECK (effective_from GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
  UNIQUE (category_id, effective_from)
);

-- Existing budgets keep applying to every past period.
INSERT INTO category_budgets (category_id, monthly_budget_cents, effective_from)
  SELECT id, monthly_budget_cents, '2000-01-01' FROM categories WHERE monthly_budget_cents > 0;

ALTER TABLE categories DROP COLUMN monthly_budget_cents;
