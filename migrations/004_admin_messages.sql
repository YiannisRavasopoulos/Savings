-- Messages from users to the admin ("Request from admin"). Users can only send; only the admin
-- reads them. The sender's username and name are copied in, so a message still says who sent it
-- after that account is deleted (user_id then becomes NULL).
CREATE TABLE admin_messages (
  id           INTEGER PRIMARY KEY,
  user_id      INTEGER REFERENCES users(id) ON DELETE SET NULL,
  username     TEXT    NOT NULL,
  display_name TEXT    NOT NULL,
  subject      TEXT    NOT NULL CHECK (subject IN
                 ('budgets', 'categories', 'income', 'account', 'bug', 'idea', 'other')),
  body         TEXT    NOT NULL CHECK (length(body) BETWEEN 1 AND 1000),
  created_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX idx_admin_messages_created ON admin_messages(created_at);
CREATE INDEX idx_admin_messages_user ON admin_messages(user_id, created_at);
