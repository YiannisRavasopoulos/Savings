# Accounts and the admin app

[← Savings](../README.md) · [All docs](README.md)

## For users

- **Log in** at `http://<server-ip>:8090/`. You stay logged in for 90 days per device. **Log out**
  is at the bottom of Settings.
- **No account?** *Request one* on the login page. You can log in once the admin approves it.
- **Settings**: your display name, password, regular income, budget period (start day and naming), theme, logged-in
  devices ("Log out all other devices"), *Download my data* (your data only, as CSV) and the
  "Request from admin" form.
- Changing your password logs out your other devices.
- **Request from admin** (bottom of Settings): pick a subject (Budgets, Categories, Income,
  Account or login, Something isn't working, Idea or suggestion, Other, **Delete my account**) and write up to 1000
  characters. It's send-only: you don't see sent messages again. There's a limit of 10 per 24
  hours.
  Choosing **Delete my account** turns the subject red, shows a warning (with a link to download
  your data first) and pre-fills a deletion request naming your account. It only fills an empty
  message box.
- Everything (categories, budgets, expenses, income, settings) is per user. Nobody else can see
  or change your data.

## Admin app (this PC only)

Open `http://localhost:8091/` or the **Savings Admin** launcher. Docker publishes this port on
`127.0.0.1` only, so phones and other computers can't reach it, not even the login page. The admin
is a separate login, not a user account, and has no budget data. The first visit asks you to create
it.

- **Account requests**: approve (the user gets the default categories) or reject (the request is
  removed).
- **Users**:
  - **Create user**: shows a one-time temporary password. They must choose their own at first
    login.
  - **Reset password**: same as above, and logs them out everywhere.
  - **Log out devices**: ends all their sessions.
  - **Disable / Enable**: blocks or allows login and keeps their data.
  - **Delete**: removes the account and all of its data. You have to type the username to confirm.
    A full snapshot `backups/db/before-delete-<user>-<time>.sqlite` is saved first; daily cleanup
    never removes it.
- **Messages**: requests sent by users, newest first, with subject, sender and time (UTC). Account
  deletion requests have a red badge and a **Delete account…** button that opens the normal delete
  confirmation for that user. Delete
  a message when you're done with it. Messages from deleted accounts stay, marked "account
  deleted".
  - **Priority:** each message has 5 rising bars for grading its importance, coloured from red
    (1, least important) to green (5, most important). Click a bar to set that level. Click the
    current level again to clear it. Only the admin sees the grade, and changes are in the
    activity log.
  - **Deleting a graded message:** up to priority 2 there's the usual quick confirmation. Above 2,
    a red warning names the priority and shows the start of the message, and only its **Delete
    anyway** button deletes it.
- **System**: database size, schema version, latest snapshots, **Back up now**, and
  **Admin password**. Changing it logs out other admin browsers.

- **Activity log** (second tab): who did what and when, newest first. It shows the date a
  budget or income change takes effect, and can be filtered by type (accounts & profile, expenses,
  income, categories & budgets, shared categories, admin actions).
  - **Export CSV** downloads what the current Type filter shows (everything without a filter), named
    by the time, e.g. `activity-log-20261105-093015.csv`.
  - **Clear log…** first saves the whole log as such a file in `backups/activity-log/` in the data
    folder, then empties it. Saved files are listed under **Saved logs** for download and are
    never deleted automatically.
  - **What's recorded:**
    - account requests, logins (including failed ones), password and profile changes, and
      requests sent;
    - expenses and income added, edited, moved or deleted;
    - category and budget changes;
    - everything in shared categories (created, invites, joins, shares, budgets, leaving,
      removals, handovers, closing);
    - every admin action.
  - **Privacy:** it records *actions*, not money. There are no amounts, expense descriptions,
    notes or message text, e.g. "Alice added an expense in “Groceries” (dated 05 Dec 2026)".
  - **Retention:** entries older than 365 days are removed by the daily backup run.

**Reset the admin password** if you forget it:

```sh
docker compose exec app python -m app.reset_admin
```

That removes only the admin login. The next visit to the admin app shows first-time setup again.
User accounts and data are untouched.

## Security notes

- Passwords: at least 10 characters, and not the same as the username. They're stored as salted
  scrypt hashes, never in plain text.
- Sessions: a random token in an `HttpOnly`, `SameSite` cookie. The database stores only its
  SHA-256, so a copied database or backup can't be used to log in.
- 5 wrong passwords lock that username (and that device) for 5 minutes. A wrong password and an
  unknown username give the same message.
- Forms are only accepted from the app's own pages (`Origin`/`Referer` check), so another website
  can't submit them in your name.
- Opening someone else's expense, income or category by changing the number in the URL answers
  "not found".
