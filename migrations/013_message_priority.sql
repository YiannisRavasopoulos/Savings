-- The admin can grade each message from users: 0 = not graded, 1 (least important) .. 5 (most).
ALTER TABLE admin_messages ADD COLUMN priority INTEGER NOT NULL DEFAULT 0 CHECK (priority BETWEEN 0 AND 5);
