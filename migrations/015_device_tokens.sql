-- Access tokens for the KDE widget. Each is named after the device, can read the user's own
-- summary (read-only) and open the website logged in, and can be revoked any time.
-- Only a sha256 of the token is stored; the token itself is shown once, when it's created.
CREATE TABLE device_tokens (
  id           INTEGER PRIMARY KEY,
  user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name         TEXT    NOT NULL CHECK (length(name) BETWEEN 1 AND 60),
  token_hash   TEXT    NOT NULL UNIQUE,
  created_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  last_used_at TEXT
);
CREATE INDEX idx_device_tokens_user ON device_tokens(user_id);

-- "Open Savings" in the widget: a one-time code, valid for a minute, that the browser swaps
-- for a normal login session (so the website opens already logged in). Stored hashed.
CREATE TABLE widget_login_codes (
  code_hash   TEXT    PRIMARY KEY,
  token_id    INTEGER NOT NULL REFERENCES device_tokens(id) ON DELETE CASCADE,
  expires_at  TEXT    NOT NULL
);
