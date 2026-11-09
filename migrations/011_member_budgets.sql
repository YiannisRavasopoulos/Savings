-- Budgets belong to a person. A personal category's budget history is its owner's; in a shared
-- category every member keeps their own budget for it (checked in their own periods). There is
-- no shared/joint budget any more.
--
-- Existing shared budgets become each member's own budget, equal to their current part
-- (budget × current share, rounded down to the cent), so nobody's numbers jump on upgrade.

CREATE TABLE category_budgets_new (
  id                   INTEGER PRIMARY KEY,
  category_id          INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
  user_id              INTEGER NOT NULL,            -- whose budget (no FK: removed with the account)
  monthly_budget_cents INTEGER NOT NULL CHECK (monthly_budget_cents >= 0),
  effective_from       TEXT    NOT NULL CHECK (effective_from GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
  UNIQUE (category_id, user_id, effective_from)
);

-- personal categories: the owner's
INSERT INTO category_budgets_new (id, category_id, user_id, monthly_budget_cents, effective_from)
  SELECT b.id, b.category_id, c.user_id, b.monthly_budget_cents, b.effective_from
  FROM category_budgets b JOIN categories c ON c.id = b.category_id WHERE c.is_joint = 0;

-- shared categories: one row per member, their current part
INSERT INTO category_budgets_new (category_id, user_id, monthly_budget_cents, effective_from)
  SELECT b.category_id, m.user_id,
         b.monthly_budget_cents * COALESCE((
           SELECT s.share_bp FROM joint_splits s
            WHERE s.category_id = b.category_id AND s.user_id = m.user_id
              AND s.effective_from = (SELECT MAX(effective_from) FROM joint_splits
                                       WHERE category_id = b.category_id AND effective_from <= date('now'))), 0) / 10000,
         b.effective_from
  FROM category_budgets b JOIN categories c ON c.id = b.category_id
  JOIN joint_members m ON m.category_id = b.category_id
  WHERE c.is_joint = 1;

DROP TABLE category_budgets;
ALTER TABLE category_budgets_new RENAME TO category_budgets;
CREATE INDEX idx_category_budgets_user ON category_budgets(user_id, category_id, effective_from);
