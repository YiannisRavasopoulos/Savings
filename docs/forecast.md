# Planned purchases and the savings forecast

[← Savings](../README.md) · [All docs](README.md)

**☰ (PC) or ⚡ (phone) → Plan a purchase.** Add what you want to buy: name, price, optional category, and how much
you've **already set aside** for it. The page projects your savings over the next 12 periods and
suggests when each purchase can be paid for comfortably. It's a transparent projection from your
own history, not machine learning: every step is below, and the code is `app/forecast.py`.

## Step 1: history

- **History periods** = up to the **12 finished periods** before the current one, never earlier
  than the period of your first expense.
- If there are fewer than **3**, the page shows no suggestions and says how many it has.
- For each history period:

      typical spending of the period = your cost of its expenses (your share for shared ones), excluding one-offs

- **One-off** expenses (tick "One-off" on the expense form, e.g. a car repair) are real and count
  everywhere else, but they're **not what a normal period costs**, so they're left out here.

## Step 2: what a period costs, and how sure we are

Percentiles use linear interpolation over the sorted values (`p50` = [median][median], `p75` = the
value three quarters of the way up). This is the common [percentile][percentile] estimate known as
Hyndman–Fan type 7 ([sample quantiles][quantile-est]). It gives the same results as NumPy's default
[`numpy.percentile(..., method="linear")`][numpy-percentile] and Python's
[`statistics.quantiles(..., method="inclusive")`][py-quantiles]:

    typical  = p50 of the history spending       (an ordinary period)
    cautious = p75 of the history spending       (a pricier period)
    spread   = (p75 − p25) ÷ p50                 (how much your spending varies)

    (spread is the [interquartile range][iqr] divided by the median, a robust cousin of the
     [coefficient of variation][cv]: it isn't thrown off by one unusual month)

    confidence = high    if history ≥ 6 periods and spread ≤ 0.30
                 medium  if history ≥ 3 periods and spread ≤ 0.60
                 low     otherwise

The page also shows your **usual left-over range**: p25–p75 of (regular income − typical
spending) over the history periods.

## Step 3: project the next 12 periods

Period 0 is the **current** one, periods 1–11 are the ones after it.

    regular(k) = regular income in effect on period k's last day   (scheduled raises included)

    period 0:   usual_by_now = p50 over the history periods of their typical spending
                               from day 1 through day d (d = today's day in the current period)
                rest_typical  = max(0, typical  − usual_by_now)      (what's usually still to come)
                rest_cautious = max(0, cautious − usual_by_now)
                left_0        = regular(0) + extra income already received this period
                                − everything actually spent so far (one-offs included)
                                − rest

    period k≥1: left_k = regular(k) − typical      (or − cautious)

    projected savings at k = left_0 + left_1 + … + left_k     (kept separately for typical and cautious)

Projected savings are a [running total][runtotal] of the expected left-overs. Future extra
income is **not** projected because it isn't reliable. Projected savings can go
down, or below zero, if a period is expected to cost more than its income.

## Step 4: place each plan

    cushion = 10 % of the current regular income      (what should still be saved after buying)
    cost    = price − already set aside               (what has to come out of projected savings)
    need    = cost + cushion

Setting money aside for a known future purchase is the idea of a [sinking fund][sinking]; the
cushion is a small [emergency buffer][emergency]. Plans are handled **in priority order** (↑ ↓ on
the page). Each placed plan *claims* its cost from
its period onward, so lower-priority plans see less:

    available_j = projected savings at j − costs claimed by higher-priority plans at j

    a plan fits from period k  if  available_j ≥ need  for EVERY period j from k to 11

Checking every later period, not just *k*, guarantees that a lower-priority plan is never put
where it would take money a higher-priority plan relies on.

- **Best time** = the first *k* that fits using the **cautious** projection. The page also shows
  what is still saved afterwards (available at *k* after paying).
- **Could already fit** = the first *k* using the **typical** projection, shown only when it's
  earlier than the best time.
- **Possible** = it fits only with the typical projection (a pricier month would push it out of
  the 12 periods).
- **Not yet** = it fits neither way within 12 periods. The page then estimates
  `⌈need ÷ (current regular income − typical)⌉` periods of typical saving (⌈ ⌉ is the
[ceiling function][ceil]), or says you're not
  saving on average when that's ≤ 0.
- **Category check** (when the plan has a category whose budget, in effect in the suggested
  period, is > 0):

      usual = p50 of the category's typical spending over the history periods
      over  = usual + price − budget        ("would go over its budget by …" when > 0)

- **Plans in a shared category** count only **your share** of the price (the split in effect
  now), and the category check uses **your** part of its budget and your share of its usual
  spending. That's what it will cost you once it's bought and logged.

**Bought it** removes the plan and opens Add expense pre-filled with its name, price and category,
ticked as one-off.

## Worked example

This is the example the tests check (`tests/test_plans.py`). Calendar months, today is 15 June,
regular income €2,000 per month.

| | Jan | Feb | Mar | Apr | May |
|---|---|---|---|---|---|
| Typical spending | 1,000 | 1,200 | 1,100 | 1,300 | 1,000 |

March also had a €2,000 one-off repair. It's ignored here.

- **Sorted:** 1000, 1000, 1100, 1200, 1300, so typical (p50) is **1,100**, cautious (p75) is
  **1,200** and p25 is 1,000.
- **Confidence:** spread = (1200 − 1000) ÷ 1100 = 0.18, but there are only 5 periods, so
  **medium**.
- **June so far:** €600 spent by day 15. The usual by day 15 is 1,100, so the typical rest is 0
  and the cautious rest is 100. June leaves 2000 − 600 − 0 = **1,400** (typical) or 1,300
  (cautious).
- **Later months** leave 2000 − 1100 = 900 (typical) or 2000 − 1200 = 800 (cautious).
- **Projected savings, cautious:** Jun 1,300, Jul 2,100, Aug 2,900, Sep 3,700, …
- **Cushion:** 10 % of 2,000 = 200.

Two plans, in this priority order:

1. **Laptop, €2,500** (Shopping, budget €300, usually €0), nothing set aside. Need = 2,500 + 200
   = 2,700.
   - Cautious savings reach that in **August** (2,900), so that's the best time. €400 is still
     saved afterwards.
   - Typical savings also first reach it in August, so there's no "could already fit".
   - Shopping would go over its budget by 0 + 2,500 − 300 = **€2,200**.
2. **Bike, €1,000**, €300 set aside. Cost = 700, need = 900.
   - After the laptop's €2,500 claim from August, cautious availability is Jun 1,300, Jul 2,100,
     **Aug 400**, Sep 1,200, Oct 2,000, …
   - June and July fail because August would drop below 900, so the best time is **September**.
     €500 is still saved afterwards.

If you swap their priority, the bike fits in June and the laptop moves to September.

## What it needs, and what it can't know

| History | What to expect |
|---|---|
| fewer than 3 finished periods | no suggestions |
| 3–5 | rough, usually "medium" or "low" confidence |
| 6+ with steady spending | "high" confidence possible |
| 12+ | covers seasonal costs (holidays, yearly bills) |

- **Log everything,** including rent and bills. Missing expenses make every period look roomier
  than it is.
- **Set your regular income** in Settings. Without it there's nothing to fit a purchase into.
- **It can't know** prices, sales or changes in your life (a new job, a move). It only extends
  your pattern so far.

## Formula references

| Used for | Reference |
|---|---|
| Typical spending, category usual | [Median][median] |
| Cautious spending, p25, p75 | [Percentile][percentile] · [Estimating quantiles from a sample (type 7)][quantile-est] · [NumPy `percentile`, method "linear"][numpy-percentile] · [Python `statistics.quantiles`][py-quantiles] |
| Spread (confidence) | [Interquartile range][iqr] · [Coefficient of variation][cv] |
| Averages (savings rate, pace, baseline) | [Arithmetic mean][mean] · [Simple moving average][sma] |
| Biggest changes % | [Relative change][relchange] |
| Projected savings, pace curves | [Running total (cumulative sum)][runtotal] |
| Savings rate | [Saving][saving] |
| Rounding to the cent | [Rounding half away from zero][round] (Python's [`decimal.ROUND_HALF_UP`][py-decimal]) |
| Periods needed | [Ceiling function][ceil] |
| Setting money aside for a purchase | [Sinking fund][sinking] · [Emergency fund][emergency] |

[median]: https://en.wikipedia.org/wiki/Median
[percentile]: https://en.wikipedia.org/wiki/Percentile
[quantile-est]: https://en.wikipedia.org/wiki/Quantile#Estimating_quantiles_from_a_sample
[numpy-percentile]: https://numpy.org/doc/stable/reference/generated/numpy.percentile.html
[py-quantiles]: https://docs.python.org/3/library/statistics.html#statistics.quantiles
[iqr]: https://en.wikipedia.org/wiki/Interquartile_range
[cv]: https://en.wikipedia.org/wiki/Coefficient_of_variation
[mean]: https://en.wikipedia.org/wiki/Arithmetic_mean
[sma]: https://en.wikipedia.org/wiki/Moving_average#Simple_moving_average
[relchange]: https://en.wikipedia.org/wiki/Relative_change
[runtotal]: https://en.wikipedia.org/wiki/Running_total
[saving]: https://en.wikipedia.org/wiki/Saving
[round]: https://en.wikipedia.org/wiki/Rounding#Rounding_half_away_from_zero
[py-decimal]: https://docs.python.org/3/library/decimal.html#decimal.ROUND_HALF_UP
[ceil]: https://en.wikipedia.org/wiki/Floor_and_ceiling_functions
[sinking]: https://en.wikipedia.org/wiki/Sinking_fund
[emergency]: https://en.wikipedia.org/wiki/Emergency_fund
