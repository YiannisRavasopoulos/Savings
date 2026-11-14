# Trends and Budget

[← Savings](../README.md) · [All docs](README.md)

## Trends

The **Trends** tab compares you with **your own past**, across budget periods instead of calendar
years. Everything measured against your **budgets** is on the **Budget** page instead. Everything is computed
in `app/summary.py` (`trends()`), through the same period functions as the rest of the app.

### Ground rules

- **Range:** the last *N* periods ending with the current one, where *N* is 6, 12 or 24 (the
  picker at the top; default 12). December → January is not a break.
- **Start:** periods before the period of your **first expense** are dropped, so months before
  you started logging aren't shown as zeros.
- **Current period = "so far":** it's drawn in the charts, but **never** used in an average or a
  comparison, so a half-finished month can't distort them. "Finished periods" below means every
  period in range except the current one.
- **Per-period numbers** are the Month view's numbers:
  - *spent* = your cost of all expenses dated in the period (your share for shared ones), one-offs included;
  - *income* = regular income in effect on the period's last day + extra income dated in it;
  - *left over* = income − spent.
- **Not enough data:** each section needs a minimum (below) and says so instead of drawing a
  misleading chart.

### 1. Savings rate

    savings rate = left over ÷ income × 100      (rounded to 0.1; no value if income is 0)
    average      = mean of the savings rates of the finished periods that have a value

See [saving rate][saving] and [arithmetic mean][mean].

The chart draws the current period with a dashed segment and the average as a dashed line.
**Needs** two finished periods with income.

### 2. Categories over time

A line per category showing its *spent* in each period. Only categories with spending somewhere
in the range are listed, sorted by their total over the range. The **5 largest are shown**; the
rest start hidden (tap them in the legend). **Needs** spending in at least two periods.

### 3. Biggest changes

Compares the **last finished period** (*L*) with the **average of the up-to-3 finished periods
before it** (*B*):

    usual = (spent in each period of B, summed) ÷ (number of periods in B)    (rounded to the cent)
    change = spent in L − usual
    %      = change ÷ usual × 100           ("new" when usual is 0)

The baseline is a [simple moving average][sma] of the previous periods; the percentage is the
[relative change][relchange]; "rounded to the cent" rounds [half away from zero][round].

A category is listed only if **|change| ≥ €10** and (usual is 0 **or** **|change| ≥ 15 % of
usual**), so small noise is skipped. Up to 6 are shown, largest |change| first. Increases are
red, decreases green. **Needs** two finished periods.

### 4. Spending pace

For the current period, with *d* = today's day number in it (1 = first day) and *D* = its length
in days:

    this period, day i = cumulative spent from the period's first day through day i   (i ≤ d)
    usual, day i       = average over the reference periods of their cumulative spent
                         through their own day i      (a shorter period stays flat after its end)
    reference periods  = the last 6 finished periods in range that have at least one expense

Each curve is a [running total][runtotal]; "usual" is the [mean][mean] of the reference curves
at each day. The text compares day *d*: "Day 15 of 30: you've spent €100; usually €160 by now (−38 %)", with
the percentage = (this − usual) ÷ usual × 100. Both curves are drawn as steps over days 1…*D*;
days after today are left blank. **Needs** one reference period.

## Budget: savings vs budget

How far ahead of your budgets (green, **saved**) or behind them (red, **damage**) you are. You see
it while the period is still running, not only at its end. It's **you against your plan**, where
Trends is you against your past.

- **Budget page** (tab between Month and Trends): any period, with the period picker.
  It has Savings vs budget, Budget pace, a **Details** table (budget, bills & one-offs, allowed,
  day-to-day, balance per category, with totals) and the **Budget track record**. A finished
  period reads as an outcome ("saved, under budget", "Saved €X this period"). A period that hasn't
  started says so.
- The KDE widget shows the same in its **Budget** tab.

### How it's counted

- **Fixed spending** (one-offs, expenses made by a recurring rule, and anything dated after
  today) doesn't set the pace. It comes off that category's budget straight away. Only the part
  beyond the budget counts as damage. Rent on the 1st won't paint the whole month red.
- **Day-to-day budget** = budget − fixed, spread evenly over the period:

      allowed by today = day-to-day budget × day ÷ days in the period   (today counts)
      balance          = allowed by today − day-to-day spent − fixed beyond the budget

  A category without a budget allows nothing, so everything spent in it is damage. On the last
  day the balance is exactly budget − spent.
- **On track to save** = income − spent so far − the rest of the day-to-day budget: what's left
  at the end if you keep to budget from here. Equal to planned savings (income − budgets) + the
  balance.

Worked example: Groceries has a €300 budget, it's day 10 of 30 and you've spent €150. Today's
allowance is €300 × 10 ÷ 30 = €100, so the balance is **−€50** (red): you're spending faster than
the budget allows. Spend nothing for the next few days and it turns green again once the
allowance passes €150 (day 16).

### Savings vs budget section

- **The number:** the total balance, signed and coloured (**+€84** green, **−€50** red), with
  "saved so far, ahead of budget" or "damage so far, behind budget".
- **The gauge:** a bar centred on a zero line. It fills to the right in green when you're ahead
  and to the left in red when you're behind, sized against what's allowed by today.
- **On track to save** the amount above, in green, or red if you're heading for a loss.
- **By category** (open by default, can be collapsed): one row per category with a budget or
  spending, **biggest damage first**. Each has its signed balance and a bar from the same centre
  line, scaled to the largest balance in the list, so they compare at a glance. Hover a row for
  "allowed €X by today · spent €Y (+ bills & one-offs)". The name opens that category's log.
- **Learn how** (closed until pressed): the explanation above, using this period's numbers.
- No budgets set: the section says so and links to Categories, and the pace chart is hidden.

### Budget pace section (day by day)

A chart over the days of the period, up to today:

- **Daily rate (dashed):** your day-to-day budget divided by the days in the period: what one day
  gets if you spread the budget evenly.
- **Bars, "Spent":** what you spent on each day (day-to-day only; bills, one-offs and recurring
  payments are left out, as in the balance). A bar is **red** on a day you spent more than the
  rate and **green** on a day you spent less.
- **Step line, "Available that day":** the rate plus whatever carried over from the days before.
  Spend less than what's available and the rest carries to the next day, so the line steps up;
  spend more and the next day has less, so it steps down (it can drop below the rate, or to zero
  when you're behind). Hover a day for its numbers.

How to read it: a step line above the dashed rate means you have margin to spare; below it means
you're making up for earlier days. On the last day, what's left of the last step is what you
saved from the day-to-day budget, the same number as the balance.

### Where to find it

- **Budget page:** the **Budget** tab (PC toolbar and phone bar). With privacy mode on, the
  amounts are blurred.
- **KDE widget:** the **Budget** tab in the popup's toolbar holds the gauge, the category bars and
  the pace chart, plus its own **Learn how**. Settings → Appearance → **Open on** picks which tab
  the popup opens on.

### Budget track record

At the bottom of the Budget page, for each category, over the **finished periods among the last
12** (from your first expense on) in which it **had a budget** (budget in
effect on that period's last day > 0):

    within = number of those periods where spent ≤ budget
    shown as "within <within> of <periods with a budget>"

Sorted by the share within, lowest first. The bar is red below 50 %, amber below 100 %, green at
100 %. Categories that never had a budget aren't listed.
