-- "My pay for a month arrives on day P of [that same month | the month before]".
--
-- payday replaces period_start_day and also allows 29-31 (a month without that day uses its last
-- day). period_start_day stays, kept in step by the app (capped at 28), so an older Savings still
-- runs on this database. The rule "pay from the month before arrives on the 20th or later" is
-- checked by the app for new settings; settings older versions allowed keep working.
ALTER TABLE users ADD COLUMN payday INTEGER NOT NULL DEFAULT 28 CHECK (payday BETWEEN 1 AND 31);
UPDATE users SET payday = period_start_day;

-- Start day 1 always meant calendar months; in the general rule that is "day 1 of that same month".
UPDATE users SET period_naming = 'start' WHERE payday = 1;

-- Something that only knows period_start_day (an older Savings after a rollback, a script) sets it:
-- follow it the way those versions meant it: day 1 = calendar months, and leaving day 1 (without
-- choosing a naming) goes back to the default, "the month before".
CREATE TRIGGER users_start_day_follows_update AFTER UPDATE OF period_start_day ON users
WHEN NEW.period_start_day IS NOT OLD.period_start_day AND NEW.payday IS OLD.payday
BEGIN
  UPDATE users SET payday = NEW.period_start_day,
                   period_naming = CASE WHEN NEW.period_start_day = 1 THEN 'start'
                                        WHEN OLD.payday = 1 AND NEW.period_naming IS OLD.period_naming THEN 'end'
                                        ELSE period_naming END
  WHERE id = NEW.id;
END;

CREATE TRIGGER users_start_day_follows_insert AFTER INSERT ON users
WHEN NEW.period_start_day IS NOT 28 AND NEW.payday = 28
BEGIN
  UPDATE users SET payday = NEW.period_start_day,
                   period_naming = CASE WHEN NEW.period_start_day = 1 THEN 'start' ELSE period_naming END
  WHERE id = NEW.id;
END;
