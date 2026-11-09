# Changelog

What changed in each release of **Savings** (the server and web app) and of the **KDE widget**.
Since Savings 1.3.0 they're **released separately**, each with its own version: Savings in
`VERSION` (`savings-X.Y.Z.tar.gz`), the widget in its package (`savings-widget-X.Y.Z.tar.gz`),
each with its own installer. Before that, the widget came inside the Savings archive.
Newest first. Versions follow `major.minor.patch`: a new **minor** version adds features, a
**patch** only fixes things, and a new **major** version would mean you have to do something by
hand when upgrading (none so far).

To upgrade, unpack the new archive and run its `./install.sh`. Your data, settings and backups
are kept.

Widget sections say which Savings they need. A widget that's too old for its server says so:
"Your Savings server is newer than this widget".

---

## Unreleased

### Changed

- **The KDE widget is no longer inside the Savings archive.** It's released on its own
  (`savings-widget-X.Y.Z.tar.gz`, with its own installer), so it can be updated without a new
  Savings release. Installing or uninstalling Savings doesn't touch an installed widget. The old
  `--no-widget` installer option is still accepted and does nothing.
- **Settings → KDE widget:** the install steps point to the widget's own download.

## Widget 1.5.1 · unreleased

- **Version check:** if the Savings server is newer than the widget understands, the widget
  says "Your Savings server is newer than this widget. Update the widget." instead of breaking.
- **Installer:** never replaces a newer installed widget with an older one (use `--force` to
  downgrade on purpose), and says so when the same version is already installed.
- Works with Savings 1.1.0 and later (the Budget tab needs 1.1.0; older servers show a note).

---

## Savings 1.2.0 · widget 1.5.0 · 2026-11-09

Widget unchanged.

### New

- **Backups in the admin app:** every backup (daily, catch-up after a missed one, Back up now, or
  from the command line) is recorded in the activity log with its files and size, and so is any
  failure, with the error. The log has a **Backups** filter; backup rows are tinted green, failed
  ones red. The admin home shows the **Last backup** in a highlighted box (green when it worked,
  red when it failed). Backups before this version weren't logged, so the box says "None
  recorded yet" until the next one runs.

---

## Savings 1.1.0 · widget 1.5.0 · 2026-11-09

### New

- **Budget page** (new tab between Month and Trends): you against your plan, for any period.
  - **Savings vs budget:** how far ahead (green, *saved*) or behind (red, *damage*) your budgets
    you are right now, on a bar centred on zero, with what you're **on track to save** this
    period. Budgets are spread evenly over the period, so you see it mid-month, not only at the
    end. Bills, one-offs and future-dated expenses don't set the pace; spending in a category
    without a budget counts as damage. **Learn how** explains it with your own numbers.
  - **By category:** each category's balance as a bar from the centre, biggest damage first.
  - **Budget pace:** a day-by-day chart of your spending against the budget's even spread,
    shaded green under it and red over it.
  - **Details** table and the **Budget track record** (moved here from Trends, which now only
    compares you with your own past).
  - Past periods read as an outcome ("Saved €X this period").
- **New period picker** on Month, Budget, Log and Income: `‹ November 2026 ▾ ›`. Tap the name
  for a 12-month grid; **This month** jumps back. Year uses `‹ 2026 ›` with **This year**.
- **Themes:** **Glass** (white, iOS-style frosted glass over a soft green and light purple glow)
  and **Glass Dark** (dark frosted glass over a graphite gradient with a green glow). Both have
  large bold titles, grey-filled fields, green-tinted buttons, toggle switches and a segmented
  control.
- **Phone:** the bottom bar is a floating, see-through pill with **Home · Month · Budget · ⚡ ·
  Trends · Year · Settings** (Settings has a wrench icon).
- **iPhone full screen:** the page reaches the top edge. As a home-screen app with a dark theme
  it draws behind the status bar and Dynamic Island; the browser's bar takes the theme's colour.
- **KDE widget 1.5.0:** a toolbar with **Overview** and **Budget** tabs. Budget shows savings vs
  budget, the categories and the pace chart, with its own **Learn how**. A new setting,
  Appearance → **Open on**, picks the tab the popup opens on. Needs Savings 1.1.0 for the Budget
  tab (older servers show a note).

### Fixed

- **Dropdowns on a PC:** "Choose…" lists (Add expense category, Request from admin, …) could
  open with unreadable rows. They're readable in every theme now.
- **Phone:** tapping ⚡ no longer shifts the bottom bar up, and open menus dim the whole page
  again.
- **iPhone:** the Glass backgrounds now show their glow on iPhone too (they used to stretch over
  the whole page and fade to grey).

### Changed

- **Home** no longer shows Savings vs budget; it lives on the Budget page.
- **Trends** no longer has the Budget track record (see Budget).

---

## Savings 1.0.0 · widget 1.4.1 · 2026-11-05

First release.

- Self-hosted spending tracker for your home network: **Home · Month · Trends · Year**, Log,
  Income, Categories with budgets, Recurring expenses, Planned purchases with a savings forecast,
  CSV import and export.
- Accounts with an admin app (this PC only), shared categories between people, daily backups
  and restore.
- Phone layout with a bottom bar, quick add and home-screen app support; Light and Dark themes;
  animations and splash screens.
- **KDE widget 1.4.1:** what's left in your panel, with a popup of panels and charts, and
  desktop notifications.
