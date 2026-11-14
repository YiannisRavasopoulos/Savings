-- Name a budget period after the month it ends in (default, as before) or the month it starts in.
ALTER TABLE users ADD COLUMN period_naming TEXT NOT NULL DEFAULT 'end'
  CHECK (period_naming IN ('end', 'start'));
