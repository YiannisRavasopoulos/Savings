-- Retire "their part". Shared categories now handle costs split with other people, so an expense's
-- amount is simply what it costs its owner (or, in a shared category, what gets split).
--
-- Existing data keeps its exact cost:
--   * their part < amount  -> amount becomes the cost (amount − their part); a note records the original
--   * their part = amount  -> the expense cost its owner nothing, so it is removed
-- Cost rows (expense_shares) already hold amount − their part, so they don't change.

DROP TRIGGER expenses_after_insert;
DROP TRIGGER expenses_after_update;

UPDATE expenses
   SET notes = TRIM(notes || char(10) || '[Their part ' || printf('%.2f', their_part_cents / 100.0) || ' of '
                    || printf('%.2f', amount_cents / 100.0) || ' removed; amount is now your cost.]'),
       amount_cents = amount_cents - their_part_cents
 WHERE their_part_cents > 0 AND their_part_cents < amount_cents;

DELETE FROM expenses WHERE their_part_cents > 0 AND their_part_cents >= amount_cents;

ALTER TABLE expenses DROP COLUMN their_part_cents;

CREATE TRIGGER expenses_after_insert AFTER INSERT ON expenses BEGIN
  UPDATE expenses SET user_id = (SELECT user_id FROM categories WHERE id = NEW.category_id)
    WHERE id = NEW.id AND user_id IS NULL;
  INSERT OR REPLACE INTO expense_shares (expense_id, user_id, cents)
    SELECT e.id, e.user_id, e.amount_cents
    FROM expenses e JOIN categories c ON c.id = e.category_id
    WHERE e.id = NEW.id AND c.is_joint = 0 AND e.user_id IS NOT NULL;
END;

CREATE TRIGGER expenses_after_update
AFTER UPDATE OF category_id, amount_cents, user_id, date ON expenses BEGIN
  DELETE FROM expense_shares WHERE expense_id = NEW.id;
  INSERT OR REPLACE INTO expense_shares (expense_id, user_id, cents)
    SELECT NEW.id, NEW.user_id, NEW.amount_cents
    FROM categories c WHERE c.id = NEW.category_id AND c.is_joint = 0 AND NEW.user_id IS NOT NULL;
END;
