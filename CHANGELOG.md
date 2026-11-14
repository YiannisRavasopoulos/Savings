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

## Widget 1.6.1 · 2026-11-14

### Fixed

- **Budget pace** was cut off at €0: when you're behind, the amount available on a day is
  negative, and the line was squashed flat along the bottom edge. The chart now goes below €0,
  with a faint €0 line, the bars standing on it and the lowest value labelled.

---

## Savings 1.6.0 · 2026-11-14

### Changed

- **Budget pace is a day-by-day chart.** Each day shows what you spent (a bar, red above the daily
  rate, green below) against what that day had available: the daily rate plus whatever carried
  over from the days before. Spend less and the next day has more; spend more and it has less.
  It replaces the cumulative line against a straight diagonal, which read as if the whole budget
  should be spent by the last day.

### New

- The widget API sends the daily numbers too (`spent`, `available`, `rate` in the budget pace),
  next to the old ones, so older widgets keep working.

## Widget 1.6.0 · 2026-11-14

### Changed

- **Budget pace** in the Budget tab draws the new day-by-day chart (bars per day, the amount
  available that day, the daily rate). Needs Savings 1.6.0; with an older Savings it draws the
  chart as before.

---

## Savings 1.5.0 · 2026-11-14

### Changed

- **Settings → Budget period is one sentence now:** "My pay for a month arrives on day **P** of
  **that same month** / **the month before**", with a preview of today's period. It replaces the
  start day and the "starts in / ends in" choice of 1.4.0, which described the same thing in a way
  that was hard to follow. Your periods stay exactly as they were.
- **Pay from the month before must arrive on the 20th or later** for new settings, so a period
  can't end up named a month later by mistake. Settings that older versions allowed keep working.

### New

- **Paydays 29, 30 and 31.** In a month without that day, the payday is the month's last day:
  paid on "the 31st" means 31 Jan, 28 Feb (29 in a leap year), 31 Mar, 30 Apr…

---

## Savings 1.4.0 · 2026-11-14

### New

- **Budget periods can be named after the month they start in.** Paid on 5 November for November?
  Set the start day to 5 and choose *"starts in"*: "November" is then 5 Nov – 4 Dec. The default
  (named after the month it ends in, e.g. 28 Oct – 27 Nov) is unchanged, so existing accounts
  look exactly as before.

### Changed

- **Savings is published on IPv4 only.** Before, Docker also published it on IPv6, and many
  connections give every device a public IPv6 address, so Savings could be reachable from the
  internet when the router let IPv6 in. The new `BIND_ADDRESS` setting (default `0.0.0.0`)
  chooses the address; upgrades get the safe default without changing `.env`. Need IPv6 on your
  network? See *On your network* in the install guide.
- **Settings → Budget period** explains the start day in plain words and shows, as you type,
  which period today falls in. The old wording ("day S of October to day S−1 of November") read
  as if start day 1 meant 1 Oct – 31 Oct; it has always meant the calendar month.

---

## Savings 1.3.0 · 2026-11-10

**First public release.** Earlier versions (1.0.0 to 1.2.0) were shared privately; their changes
are listed below.

### Fixed

- **`savings stop`** said the server would start again at boot. It doesn't: a server you stopped
  stays stopped, even after a reboot, until `savings start`. The message now says so.

### Changed

- **The KDE widget is no longer inside the Savings archive.** It's released on its own
  (`savings-widget-X.Y.Z.tar.gz`, with its own installer), so it can be updated without a new
  Savings release. Installing or uninstalling Savings doesn't touch an installed widget. The old
  `--no-widget` installer option is still accepted and does nothing.
- **Settings → KDE widget:** the install steps point to the widget's own download.
- **Installing from a copy of the source code** (instead of a release) now stops with a clear
  message pointing to the Releases page, instead of a confusing error.
- **Installing and running guide:** rewritten around the installer, with a section on how
  Savings is reached on your network.

## Widget 1.5.1 · 2026-11-10

**First public release of the widget.** Earlier versions were shared privately. Needs Savings
1.1.0 or later.

- **Version check:** if the Savings server is newer than the widget understands, the widget
  says "Your Savings server is newer than this widget. Update the widget." instead of breaking.
- **Installer:** never replaces a newer installed widget with an older one (use `--force` to
  downgrade on purpose), and says so when the same version is already installed. Run from a copy
  of the source code instead of a release, it says so and points to the Releases page.
- The Budget tab needs Savings 1.1.0; older servers show a note instead.

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
