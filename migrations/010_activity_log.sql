-- App-wide activity log, shown in the admin app: who did what, when, and (for scheduled changes)
-- from when it takes effect. It records actions, not money: no amounts, descriptions or notes.
-- Names are copied in, so entries stay readable after an account is deleted.
CREATE TABLE activity_log (
  id             INTEGER PRIMARY KEY,
  actor_id       INTEGER,                 -- users.id, or NULL for the admin / the system (no FK: outlives accounts)
  actor_name     TEXT    NOT NULL,
  kind           TEXT    NOT NULL,        -- e.g. expense.added, category.archived, shared.left, admin.approved
  detail         TEXT    NOT NULL,
  category_id    INTEGER,                 -- the category concerned, if any (no FK: outlives categories)
  effective_from TEXT,                    -- for scheduled changes: the day it takes effect
  created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX idx_activity_log_created ON activity_log(id DESC);
CREATE INDEX idx_activity_log_actor ON activity_log(actor_id, id DESC);
