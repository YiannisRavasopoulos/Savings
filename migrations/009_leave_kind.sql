-- Why a membership ends, so the app can say "Bob is leaving" vs "Bob is being removed".
ALTER TABLE joint_members ADD COLUMN leave_kind TEXT
  CHECK (leave_kind IS NULL OR leave_kind IN ('left', 'removed', 'closed'));
UPDATE joint_members SET leave_kind = 'left' WHERE leaves_after IS NOT NULL;
