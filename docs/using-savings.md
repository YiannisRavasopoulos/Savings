# Using Savings

[← Savings](../README.md) · [All docs](README.md)

## Budget periods

A "month" is a budget period. Set it in **Settings → Budget period** with one sentence:

> My pay for a month arrives on day **P** of **that same month** / **the month before**.

A period runs from one payday up to the day before the next payday, and it's named after the
month the pay is for. Days 29–31 mean the last day in months that are shorter.

| You get paid… | Day | Of… | "November 2026" is |
|---|---|---|---|
| on the 1st (calendar months) | 1 | that same month | 1 Nov – 30 Nov |
| on the 5th, for that month | 5 | that same month | 5 Nov – 4 Dec |
| on the 28th, for the next month | 28 | the month before | 28 Oct – 27 Nov |
| on the last day, for the next month | 31 | the month before | 31 Oct – 29 Nov |

Pay from the month before must arrive on the 20th or later (settings made by older versions keep
working). The settings page shows today's period as you change the values. Changing it re-groups
all past entries into the new periods; income and budget history keep their dates.

The Year view for year Y shows the twelve periods labelled Jan–Dec Y: paid on the 28th of the month
before, that is 28 Dec (Y−1) to 27 Dec Y; paid on the 5th of that same month, 5 Jan Y to 4 Jan (Y+1). The page shows the exact range. Averages are taken only over periods
that have at least one expense. Periods that haven't started yet are left blank.

**Regular income** and **category budgets** both have a history, and both work the same way: a
period uses the latest amount whose "effective from" date is on or before the period's last day. A
new amount applies from the period that contains its date onwards. Earlier periods keep the old
amount, so changing your income or a budget never rewrites past months. Entering the same date
again replaces that amount, which is how you fix a typo. A category with no budget entry for a
period has a budget of €0 there.

In **Categories**, each category's **Edit** pop-up shows its budget for the current period and its
budget history. To change the budget, enter an amount and a "From" date (today by default). To give
a budget to months you are entering after the fact, pick a "From" date in or before the first of
those periods.

Every entry in a category's budget history, and every regular income amount in **Settings**, has its
own **Edit** and **Delete**:

- **Edit** changes the amount and/or the date. A date that already has an entry is refused; edit
  or delete that entry instead.
- **Delete** first tells you what the affected months fall back to: the previous entry, or €0.

### Managing categories

The **Categories** page (Settings → Categories and budgets → Manage categories) lists every category with its budget and how many expenses
use it. Add, Edit and Delete open pop-ups, ↑/↓ reorder, and Archive hides a category from the Add
form while keeping its history (it gets "(archived)" added to its name; see below).

What depends on a category, and how that's handled:

- **Renaming** keeps all its expenses, since they point to the category, not its name. Renaming
  onto a name that already exists is refused, with a hint to merge instead.
- **Deleting a category with expenses** asks what to do with them:
  - **Move them to another category**, then delete it. This is how you merge two categories.
    Totals don't change.
  - **Delete the expenses too.** You must type the category's name to confirm. Only a backup can
    bring them back.
  - **Archive instead**, which keeps everything.
- **Budget history** of a deleted category is removed with it.
- **Your last active category** can't be archived or deleted, because the Add form would be
  empty.
- If the category changed in another tab (expenses added, or the category already deleted), the
  action is refused with an error pop-up rather than guessing.

An expense's **amount** is what it costs you. To split a cost with other people, use a **shared
category** (see [Shared categories](shared-categories.md)): each member is charged their share.

## Using it from your phone

The server must be reachable from the phone: either on the same Wi‑Fi, or through your VPN
(WireGuard, Tailscale, …).

1. Find the server's address: `hostname -I` on the server for the LAN IP, or its VPN/Tailscale IP.
2. On the phone, open `http://<that-ip>:8090/`.
3. Use "Add to Home Screen" for one-tap access.

**Offline page:** when the home-screen app can't reach the server (off Wi-Fi or VPN), it shows a
"Can't reach Savings" page with a **Try again** button. It also retries automatically when the
connection comes back. Only that page is stored on the phone, never your data. Browsers allow
this only over **HTTPS** (or on `localhost`), so it starts working once the app is served over
HTTPS (see [Security notes](accounts-and-admin.md#security-notes)). Over plain `http://<ip>:8090` the phone shows its usual error page instead.

The home page is a dashboard for the current period: how much is left (and per day), income vs
spent, a doughnut of spending by category, the budgets closest to their limit, the last 6 periods,
and recent expenses.

**Future-dated expenses** (dated after today) count in the period's totals and budgets as planned
spending. They carry a **future** tag in the Log and in Home's recent list. In the charts they are
drawn hatched: a light wash of the colour with thin diagonal stripes and a solid outline. In the
doughnut that's a slice in the category's own colour, and in the Spent bars (Home and Year) a
segment on top of the solid part.

**Income bars** in the Spent vs income charts stack **regular income** (green) with **extra
income** on top in its own colour (amber), so unexpected income stands out. Faded and extra
segments only appear in the legend when there is some.

Navigation:

- **On a PC** (screen 700px wide or more):
  - the toolbar under the top bar has **Home · Month · Budget · Trends · Year**;
  - the **☰ menu** (top left) opens **Add expense**, **Add income** and **Plan a purchase**;
  - **⚙ Settings** is its own button (top right).
- **On a phone** (narrower than 700px, in the browser or opened from the home-screen icon):
  - a floating bar holds **Home · Month · Budget · ⚡ · Trends · Year · Settings** (three either
    side of the centre button). It's a rounded pill inset from the screen edges, with a frosted,
    see-through background, so the page shows through softly as you scroll;
  - the green **⚡** centre button opens **Add expense**, **Add income**, **Plan a purchase** and
    **Settings**. Tap outside or press it again to close.
  - The bar sits above the home indicator on iPhones.
  - **Full screen:** the page reaches the top edge. In Safari, the strip above the page takes the
    top bar's colour. As a home-screen app with a dark look (Dark, Glass Dark, or Auto with the
    phone in dark mode), the page also draws behind the status bar and Dynamic Island. The top bar keeps
    clear of them, and a strip keeps the clock readable while you scroll. iOS shows white status
    icons in that mode, so the light themes (Light, Glass) keep the standard status bar.
- **Choosing a period** (Month, Budget, Log, Income): **‹ November 2026 ▾ ›**. The arrows step one
  period. Tap the name for a 12-month grid with **‹ year ›**: the current period is outlined, the
  one you're viewing is filled, and **This month** jumps back. When you're looking at another
  period, a **This month** link also shows next to the dates. The Log keeps its category filter
  while you move. **Year** uses the same **‹ 2026 ›** with a **This year** link.
  - **Quick add:** ⚡ → **Add expense** opens a sheet over the page you're on instead of the full
    form:
    - the amount field is focused, with the number keypad open;
    - your 5 most-used categories from the last 90 days are buttons, with the one you used last
      already picked and the rest under "More categories…";
    - the date is today by default, with a Yesterday button or any date;
    - the description is optional: left empty, it becomes the category's name (e.g. "Groceries").

    The **Expense / Income** switch at the top adds extra income the same way (description
    "Extra income" if left empty). After **Save** the page refreshes and the red or green effect
    confirms it (see [Animations](appearance.md#animations)). To take one back, delete it from the Log. **More details ›** opens the full form for notes
    or a one-off mark. On a PC, the ☰ menu's Add expense still opens the full page.
- **Settings** (one page): account, regular income, a link to **Categories and budgets**, budget
  period, appearance, logged-in devices, your data, **Request from admin**, and Log out.
- **Log** (every expense, with edit and delete): from Home ("Full log ›") or Month ("Log ›").
- **Back:** pages outside the toolbar have a "‹" link back to where they're opened from.

If it doesn't load, check the server's firewall allows the port from your LAN/VPN (for example
`sudo ufw allow from 192.168.0.0/24 to any port 8090`).

## Recurring expenses

Settings → **Recurring expenses** (also in the ☰ / ⚡ menus) holds rent, subscriptions and bills
that repeat. Each one has a description, category, amount, how often (monthly, every 3 or 6 months,
or yearly), a first payment date and an optional last one.

- **Each payment is an ordinary expense** on its date, tagged **↻ recurring** in your Log (the tag
  links back to the rule). You can edit or delete any single payment like any other expense, and a
  deleted payment isn't re-created.
- **Created ahead, up to the end of your current period**, so the rest of this period's payments
  are already in your totals as **future**-dated expenses. When a new period starts, its payments
  are added the next time you open the app (no background job needed).
- **A first payment in the past** adds the payments since then too, which is handy when you start
  tracking something you've been paying for a while.
- **Short months:** a payment on the 29th–31st falls on the month's last day when the month is
  shorter, and goes back to the 31st where the month has one.
- **Editing** (description, category, amount, notes, last payment) replaces the payments dated
  **after today**, including any of them you'd edited by hand. Payments up to today stay as they
  were. To change the schedule itself, delete the rule and set up a new one.
- **Pause** removes payments dated after today and adds no new ones. **Resume** carries on from
  today: payments missed while paused aren't added.
- **Delete** removes payments dated after today and keeps the ones already made (they lose the
  recurring tag).
- **On hold:** if the category is archived, or you've left the shared category, no new payments are
  added, and the page says why.
- Shared categories work too: each payment is split between the members as usual.

## Importing expenses from CSV

Settings → Your data → **Import expenses from CSV** brings in past expenses from a bank export or a
spreadsheet. You see a **preview** of every row (ready, possible duplicate, skipped, or the
problem with it) and **nothing is saved until you press Import**.

- **Columns** come from the header row (names are case-insensitive, other columns are ignored):
  - required: **date** and **amount**;
  - optional: **description**, **category**, **notes** and **one_off** (yes/1).

  Common bank names like *booking date*, *payee*, *value* and *memo* are recognised. Commas,
  semicolons or tabs all work, as does UTF-8 or Windows text.
- **Dates:** 2026-10-05, or day first: 05/10/2026, 05.10.2026, 05-10-2026.
- **Amounts:** 12.50, 12,50 or €1.234,56.
- **Bank exports:** if any amount is negative, negatives are the spending (imported as positive)
  and positive amounts (money in) are skipped.
- **Categories** are matched by name to your categories and the shared ones you're in.
  - Rows without a category use **Category for rows without one**, if you pick it.
  - Unknown names are a problem, unless you tick **Create missing categories**, which adds them
    with no budget.
- **Duplicates:** a row with the same date, amount and description as an expense you already have
  is flagged and skipped, unless you tick **Import possible duplicates too**.
- This app's own `expenses.csv` (from Download my data) can be imported back. Rows someone else
  paid in a shared category are skipped.
- **Limits:** 5000 rows and 2 MB per file. The activity log records how many were imported and
  their date range, never amounts or descriptions.

## Export

Settings → **Download my data** (`/export.zip`) gives a zip named `spending-export-YYYY-MM-DD.zip`
with **your own** data: `expenses.csv` (including category name and `my_cost_cents`),
`extra_income.csv`, `categories.csv`, `category_budgets.csv` (budget history, with the category
name), `regular_income.csv` and `recurring_expenses.csv`.

The daily backup's CSV zip contains **everyone's** data, with a `user_id` column, plus
`users.csv` (usernames, names, status and dates, but never password hashes) and
`admin_messages.csv`.
Amounts are integer **cents** (`1250` = €12.50). Files are UTF-8 with a BOM so Excel opens them
correctly.
