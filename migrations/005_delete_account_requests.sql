-- Add the 'delete_account' subject. SQLite can't change a CHECK constraint in place, so the
-- table is rebuilt and the existing messages copied over unchanged.
CREATE TABLE admin_messages_new (
  id           INTEGER PRIMARY KEY,
  user_id      INTEGER REFERENCES users(id) ON DELETE SET NULL,
  username     TEXT    NOT NULL,
  display_name TEXT    NOT NULL,
  subject      TEXT    NOT NULL CHECK (subject IN
                 ('budgets', 'categories', 'income', 'account', 'bug', 'idea', 'other', 'delete_account')),
  body         TEXT    NOT NULL CHECK (length(body) BETWEEN 1 AND 1000),
  created_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
INSERT INTO admin_messages_new (id, user_id, username, display_name, subject, body, created_at)
  SELECT id, user_id, username, display_name, subject, body, created_at FROM admin_messages;
DROP TABLE admin_messages;
ALTER TABLE admin_messages_new RENAME TO admin_messages;
CREATE INDEX idx_admin_messages_created ON admin_messages(created_at);
CREATE INDEX idx_admin_messages_user ON admin_messages(user_id, created_at);
