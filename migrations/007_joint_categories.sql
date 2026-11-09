-- Joint (shared) categories.
--
-- * Every expense now has its own owner (expenses.user_id = who paid / logged it). Until now the
--   owner was implied by the category, which no longer works once several people share one.
-- * expense_shares: what each person's cost of an expense is. A personal expense has one row
--   (the owner, amount − their part). A joint expense has one row per member, split by the
--   shares in effect for its joint period. Every personal total sums these rows.
--   Personal rows are maintained by the triggers below; joint rows by the app (app/joint.py).
-- * A joint category has its own period start day, members (one moderator), invitations and a
--   history of share splits (each split applies from a joint period start, so changes never
--   rewrite the past).

ALTER TABLE expenses ADD COLUMN user_id INTEGER REFERENCES users(id);
UPDATE expenses SET user_id = (SELECT user_id FROM categories WHERE categories.id = expenses.category_id);
CREATE INDEX idx_expenses_user ON expenses(user_id, date);

ALTER TABLE categories ADD COLUMN is_joint INTEGER NOT NULL DEFAULT 0 CHECK (is_joint IN (0, 1));
ALTER TABLE categories ADD COLUMN joint_start_day INTEGER
  CHECK (joint_start_day IS NULL OR joint_start_day BETWEEN 1 AND 28);

CREATE TABLE expense_shares (
  expense_id INTEGER NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
  user_id    INTEGER NOT NULL,
  cents      INTEGER NOT NULL,
  PRIMARY KEY (expense_id, user_id)
);
CREATE INDEX idx_expense_shares_user ON expense_shares(user_id);
INSERT INTO expense_shares (expense_id, user_id, cents)
  SELECT id, user_id, amount_cents - COALESCE(their_part_cents, 0) FROM expenses WHERE user_id IS NOT NULL;

CREATE TABLE joint_members (
  category_id     INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
  user_id         INTEGER NOT NULL REFERENCES users(id),
  role            TEXT    NOT NULL CHECK (role IN ('moderator', 'member')),
  joined_from     TEXT    NOT NULL,   -- first day of membership (a joint period start)
  committed_until TEXT    NOT NULL,   -- can't leave / be removed before the end of this day
  leaves_after    TEXT,               -- last day of membership, once leaving is scheduled
  PRIMARY KEY (category_id, user_id)
);
CREATE INDEX idx_joint_members_user ON joint_members(user_id);

CREATE TABLE joint_invites (
  id          INTEGER PRIMARY KEY,
  category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
  user_id     INTEGER NOT NULL REFERENCES users(id),
  invited_by  INTEGER NOT NULL,
  created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  expires_at  TEXT    NOT NULL,
  UNIQUE (category_id, user_id)
);
CREATE INDEX idx_joint_invites_user ON joint_invites(user_id);

CREATE TABLE joint_splits (
  category_id    INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
  effective_from TEXT    NOT NULL,     -- a joint period start
  user_id        INTEGER NOT NULL,
  share_bp       INTEGER NOT NULL CHECK (share_bp BETWEEN 0 AND 10000),   -- 1 bp = 0.01 %
  PRIMARY KEY (category_id, effective_from, user_id)
);

-- Keep the owner and the personal allocation of every expense up to date.
CREATE TRIGGER expenses_after_insert AFTER INSERT ON expenses BEGIN
  UPDATE expenses SET user_id = (SELECT user_id FROM categories WHERE id = NEW.category_id)
    WHERE id = NEW.id AND user_id IS NULL;
  INSERT OR REPLACE INTO expense_shares (expense_id, user_id, cents)
    SELECT e.id, e.user_id, e.amount_cents - COALESCE(e.their_part_cents, 0)
    FROM expenses e JOIN categories c ON c.id = e.category_id
    WHERE e.id = NEW.id AND c.is_joint = 0 AND e.user_id IS NOT NULL;
END;

CREATE TRIGGER expenses_after_update
AFTER UPDATE OF category_id, amount_cents, their_part_cents, user_id, date ON expenses BEGIN
  DELETE FROM expense_shares WHERE expense_id = NEW.id;
  INSERT OR REPLACE INTO expense_shares (expense_id, user_id, cents)
    SELECT NEW.id, NEW.user_id, NEW.amount_cents - COALESCE(NEW.their_part_cents, 0)
    FROM categories c WHERE c.id = NEW.category_id AND c.is_joint = 0 AND NEW.user_id IS NOT NULL;
END;
