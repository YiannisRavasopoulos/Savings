"""Month and year numbers. All period boundaries come from period.py."""
from __future__ import annotations

import sqlite3
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from .db import BUDGET_AS_OF_SQL
from .joint import VISIBLE_SQL
from .period import MONTH_ABBR, period_bounds, period_key, range_label

# What an expense costs each person lives in expense_shares (one row per person): a personal
# expense costs its owner the full amount; a shared one costs each member their share. Every
# personal total is SUM(s.cents) over the user's own rows.
# A shared category the user has left shows as "<name> (left)" for them (bind :today; needs `jm`).
LEFT_NAME_SQL = ("CASE WHEN c.is_joint = 1 AND jm.leaves_after IS NOT NULL AND jm.leaves_after < :today "
                 "THEN c.name || ' (left)' ELSE c.name END")


def _today_iso() -> str:
    from .config import today
    return today().isoformat()


# Joins an expense `e` to the user's own cost row `s` (bind :uid).
MY_SHARE_JOIN = "JOIN expense_shares s ON s.expense_id = e.id AND s.user_id = :uid"


def get_start_day(conn: sqlite3.Connection, user_id: int) -> int:
    row = conn.execute("SELECT period_start_day FROM users WHERE id = ?", (user_id,)).fetchone()
    s = row[0] if row else 28
    return s if 1 <= s <= 28 else 28


def regular_income_for(conn: sqlite3.Connection, user_id: int, period_end: date) -> int:
    """Latest regular income whose effective_from <= the period's last day (0 if none)."""
    row = conn.execute(
        "SELECT amount_cents FROM regular_income WHERE user_id = ? AND effective_from <= ? "
        "ORDER BY effective_from DESC LIMIT 1",
        (user_id, period_end.isoformat()),
    ).fetchone()
    return row[0] if row else 0


def budget_pct(spent: int, budget: int) -> float | None:
    return None if budget <= 0 else spent * 100 / budget


def budget_status(spent: int, budget: int) -> str:
    """'' below 85 %, 'amber' for 85-100 %, 'red' above 100 %. Integer maths, no rounding."""
    if budget <= 0:
        return ""
    if spent > budget:
        return "red"
    if spent * 100 >= 85 * budget:
        return "amber"
    return ""


def round_div(total: int, n: int) -> int:
    """total / n rounded half away from zero, in whole cents."""
    return int((Decimal(total) / n).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def month_summary(conn: sqlite3.Connection, user_id: int, year: int, month: int) -> dict:
    start_day = get_start_day(conn, user_id)
    start, end = period_bounds(year, month, start_day)
    args = (start.isoformat(), end.isoformat())

    # Budget = the user's own budget entry in effect on the period's last day. Spent = the user's
    # own cost rows (their share for shared categories).
    rows = conn.execute(
        f"SELECT c.id, {LEFT_NAME_SQL} AS name, c.archived, c.is_joint, {BUDGET_AS_OF_SQL} AS budget,"
        f" (SELECT COALESCE(SUM(s.cents), 0) FROM expenses e {MY_SHARE_JOIN}"
        f"   WHERE e.category_id = c.id AND e.date BETWEEN :start AND :end) AS spent,"
        f" (SELECT COUNT(*) FROM expenses e {MY_SHARE_JOIN}"
        f"   WHERE e.category_id = c.id AND e.date BETWEEN :start AND :end) AS n,"
        f" (SELECT COALESCE(SUM(s.cents), 0) FROM expenses e {MY_SHARE_JOIN}"
        f"   WHERE e.category_id = c.id AND e.date BETWEEN :start AND :end AND e.date > :today) AS future,"
        f" jm.joined_from, jm.leaves_after "
        f"FROM categories c LEFT JOIN joint_members jm ON jm.category_id = c.id AND jm.user_id = :uid "
        f"WHERE {VISIBLE_SQL} ORDER BY c.is_joint, c.sort_order, c.name",
        {"asof": end.isoformat(), "start": start.isoformat(), "end": end.isoformat(), "uid": user_id,
         "today": _today_iso()},
    ).fetchall()
    categories = []
    for r in rows:
        outside = r["is_joint"] and ((r["leaves_after"] and r["leaves_after"] < start.isoformat())
                                     or (r["joined_from"] and r["joined_from"] > end.isoformat()))
        if (r["archived"] or outside) and not r["n"]:
            continue  # archived / not a member during this period, and unused: hide
        budget = r["budget"]          # always the user's own budget, shared categories included
        categories.append({
            "id": r["id"],
            "name": r["name"],
            "archived": bool(r["archived"]),
            "joint": bool(r["is_joint"]),
            "budget": budget,
            "spent": r["spent"],
            "future": r["future"],    # part of `spent` dated after today (still counted)
            "left": budget - r["spent"],
            "pct": budget_pct(r["spent"], budget),
            "status": budget_status(r["spent"], budget),
            "n": r["n"],
        })

    extra = conn.execute(
        "SELECT COALESCE(SUM(amount_cents), 0) FROM extra_income WHERE user_id = ? AND date BETWEEN ? AND ?",
        (user_id, *args),
    ).fetchone()[0]
    regular = regular_income_for(conn, user_id, end)
    spent = sum(c["spent"] for c in categories)
    budget = sum(c["budget"] for c in categories)
    return {
        "year": year,
        "month": month,
        "start": start,
        "end": end,
        "range": range_label(start, end),
        "regular": regular,
        "extra": extra,
        "income": regular + extra,
        "spent": spent,
        "future": sum(c["future"] for c in categories),
        "left": regular + extra - spent,
        "budget": budget,
        "budget_pct": budget_pct(spent, budget),
        "budget_status": budget_status(spent, budget),
        "n_expenses": sum(c["n"] for c in categories),
        "categories": categories,
    }


def year_summary(conn: sqlite3.Connection, user_id: int, year: int, today: date) -> dict:
    """The 12 periods labelled Jan..Dec of `year`.

    Periods that haven't started yet (start > today) are None and shown blank.
    Averages are over the periods that have at least one expense.
    """
    start_day = get_start_day(conn, user_id)
    periods, months = [], []
    for m in range(1, 13):
        start, end = period_bounds(year, m, start_day)
        future = start > today
        periods.append({"month": m, "label": MONTH_ABBR[m], "key": period_key(year, m),
                        "range": range_label(start, end), "future": future})
        months.append(None if future else month_summary(conn, user_id, year, m))

    data_idx = [i for i, ms in enumerate(months) if ms and ms["n_expenses"] > 0]

    def row(label, values, **extra):
        total = sum(v for v in values if v is not None)
        avg = round_div(sum(values[i] for i in data_idx), len(data_idx)) if data_idx else None
        return {"label": label, "cells": values, "total": total, "avg": avg, **extra}

    def per_month(key):
        return [None if ms is None else ms[key] for ms in months]

    category_rows = []
    for c in conn.execute(f"SELECT c.id, c.name, c.archived, c.is_joint FROM categories c WHERE {VISIBLE_SQL} "
                          "ORDER BY c.is_joint, c.sort_order, c.name", {"uid": user_id}):
        values = []
        for ms in months:
            if ms is None:
                values.append(None)
            else:
                values.append(next((x["spent"] for x in ms["categories"] if x["id"] == c["id"]), 0))
        used = any(v for v in values)
        if c["archived"] and not used:
            continue
        category_rows.append(row(c["name"], values, joint=bool(c["is_joint"])))

    totals = [
        row("Total spent", per_month("spent"), cls="strong"),
        row("Regular income", per_month("regular")),
        row("Extra income", per_month("extra")),
        row("Total income", per_month("income"), cls="strong"),
        row("Left over", per_month("left"), cls="strong"),
    ]
    return {
        "year": year,
        "range": range_label(period_bounds(year, 1, start_day)[0],
                             period_bounds(year, 12, start_day)[1]),
        "periods": periods,
        "categories": category_rows,
        "totals": totals,
        "n_data": len(data_idx),
        "chart": {
            "labels": [p["label"] for p in periods],
            **_bar_series(months),
        },
    }


def _bar_series(months: list) -> dict:
    """Spent-vs-income bar data in euros: spent split into happened / future-dated, income into
    regular / extra. A period that hasn't started (None) stays blank."""
    def series(fn):
        return [None if ms is None else fn(ms) / 100 for ms in months]
    return {
        "spent_past": series(lambda ms: ms["spent"] - ms["future"]),
        "spent_future": series(lambda ms: ms["future"]),
        "regular": series(lambda ms: ms["regular"]),
        "extra": series(lambda ms: ms["extra"]),
    }


# --- Savings vs budget (Home) --------------------------------------------------------------
#
# Day-to-day spending is compared with the budget spread evenly over the period ("allowed by
# today"). Fixed spending (one-offs, expenses made by a recurring rule, and anything dated after
# today) doesn't set the pace: it simply comes off that category's budget up front, and only the
# part beyond the budget counts as damage. A category without a budget allows nothing, so all of
# its spending is damage. On the last day of a period the balance is exactly budget - spent.

FIXED_SQL = "(e.one_off = 1 OR e.recurring_id IS NOT NULL OR e.date > :today)"


def budget_balance(conn: sqlite3.Connection, user_id: int, ms: dict, today: date) -> dict:
    """Ahead (+) or behind (-) budget for the period summarised in `ms`, per category and in
    total, plus the cumulative day-to-day spending curve for the pace chart."""
    start, end = ms["start"], ms["end"]
    days = (end - start).days + 1
    day = max(1, min(days, (today - start).days + 1))           # today counts as a day used
    args = {"uid": user_id, "start": start.isoformat(), "end": end.isoformat(), "today": today.isoformat()}
    fixed = dict(conn.execute(
        f"SELECT e.category_id, SUM(s.cents) FROM expenses e {MY_SHARE_JOIN} "
        f"WHERE e.date BETWEEN :start AND :end AND {FIXED_SQL} GROUP BY e.category_id", args).fetchall())

    cats = []
    for c in ms["categories"]:
        if c["budget"] <= 0 and c["spent"] == 0:
            continue
        fx = fixed.get(c["id"], 0)
        daily = c["spent"] - fx                                   # day-to-day spending so far
        flexible = max(0, c["budget"] - fx)                       # budget left for day-to-day
        allowed = flexible * day // days
        over_fixed = max(0, fx - c["budget"])
        cats.append({"id": c["id"], "name": c["name"], "joint": c["joint"], "budget": c["budget"],
                     "spent": c["spent"], "fixed": fx, "daily": daily, "flexible": flexible,
                     "allowed": allowed, "balance": allowed - daily - over_fixed})
    cats.sort(key=lambda c: (c["balance"], c["name"]))            # biggest damage first

    flexible = sum(c["flexible"] for c in cats)
    balance = sum(c["balance"] for c in cats)
    rest = sum(c["flexible"] - c["allowed"] for c in cats)          # day-to-day budget still to come
    projected = ms["income"] - ms["spent"] - rest                    # if you keep to budget from here

    # pace chart: cumulative day-to-day spending (to today) vs the even spread of the budget
    per_day = dict(conn.execute(
        f"SELECT e.date, SUM(s.cents) FROM expenses e {MY_SHARE_JOIN} "
        f"WHERE e.date BETWEEN :start AND :end AND NOT {FIXED_SQL} GROUP BY e.date", args).fetchall())
    actual, total = [], 0
    for i in range(days):
        total += per_day.get(date.fromordinal(start.toordinal() + i).isoformat(), 0)
        actual.append(total / 100 if i < day else None)
    return {
        "categories": cats,
        "budget": sum(c["budget"] for c in cats),
        "balance": balance,
        "planned": ms["income"] - sum(c["budget"] for c in cats),    # income - budgets
        "projected": projected,
        "day": day, "days": days,
        "finished": today > end, "upcoming": today < start,
        "allowed": sum(c["allowed"] for c in cats),
        "daily": sum(c["daily"] for c in cats),
        "fixed": sum(c["fixed"] for c in cats),
        "scale": max([abs(c["balance"]) for c in cats] + [1]),
        "pace": {"labels": [str(i) for i in range(1, days + 1)], "actual": actual,
                 "allowed": [round(flexible * (i + 1) / days) / 100 for i in range(days)]},
    }


def dashboard(conn: sqlite3.Connection, user_id: int, today: date, history: int = 6) -> dict:
    """Numbers for the home page: the current period plus the last `history` periods."""
    from .period import period_for_date, period_label, shift_period

    start_day = get_start_day(conn, user_id)
    year, month = period_for_date(today, start_day)
    cur = month_summary(conn, user_id, year, month)

    days_left = (cur["end"] - today).days + 1          # today counts as a day left
    per_day = cur["left"] // days_left if cur["left"] > 0 else 0   # rounded down: never overstated

    spent_categories = sorted((c for c in cur["categories"] if c["spent"] > 0),
                              key=lambda c: c["spent"], reverse=True)
    # Categories with a budget, closest to (or over) their limit first.
    watch = sorted((c for c in cur["categories"] if c["budget"] > 0),
                   key=lambda c: c["spent"] / c["budget"], reverse=True)[:5]

    vb = budget_balance(conn, user_id, cur, today)

    trend = []
    for back in range(history - 1, -1, -1):
        y, m = shift_period(year, month, -back)
        ms = cur if back == 0 else month_summary(conn, user_id, y, m)
        trend.append({"label": f"{MONTH_ABBR[m]}" + (f" {y % 100:02d}" if m == 1 else ""),
                      "key": period_key(y, m), "ms": ms})

    recent = conn.execute(
        f"SELECT e.id, e.date, e.description, e.user_id = :uid AS mine, c.name AS category, c.is_joint,"
        f" s.cents AS my_cost, u.display_name AS paid_by, e.date > :today AS future "
        f"FROM expenses e {MY_SHARE_JOIN} JOIN categories c ON c.id = e.category_id JOIN users u ON u.id = e.user_id "
        "ORDER BY e.date DESC, e.id DESC LIMIT 5", {"uid": user_id, "today": today.isoformat()}
    ).fetchall()

    return {
        "label": period_label(year, month),
        "key": period_key(year, month),
        "s": cur,
        "days_left": days_left,
        "days_total": (cur["end"] - cur["start"]).days + 1,
        "per_day": per_day,
        "watch": watch,
        "recent": recent,
        "vs_budget": vb,            # for the widget's Budget tab (the app shows it on the Budget page)
        "charts": {
            "categories": {
                "labels": [c["name"] for c in spent_categories],
                "amounts": [c["spent"] / 100 for c in spent_categories],
                "future": [c["future"] / 100 for c in spent_categories],
            },
            "trend": {
                "labels": [t["label"] for t in trend],
                **_bar_series([t["ms"] for t in trend]),
            },
        },
    }


# --- Trends -------------------------------------------------------------------------------

TREND_RANGES = (6, 12, 24)
CHANGE_MIN_CENTS = 1000      # "biggest changes" ignores differences under €10 ...
CHANGE_MIN_PCT = 15          # ... or under 15 % of the usual amount
PACE_HISTORY = 6             # typical pace = average of up to this many previous periods


def _daily_cumulative(conn, user_id: int, start: date, end: date, days: int) -> list[int]:
    """Cumulative 'my cost' at the end of day 1..days of a period (stays flat past its end)."""
    per_day = dict(conn.execute(
        f"SELECT e.date, SUM(s.cents) FROM expenses e {MY_SHARE_JOIN} "
        "WHERE e.date BETWEEN :start AND :end GROUP BY e.date",
        {"uid": user_id, "start": start.isoformat(), "end": end.isoformat()}).fetchall())
    out, total = [], 0
    for i in range(days):
        d = date.fromordinal(start.toordinal() + i)
        if d <= end:
            total += per_day.get(d.isoformat(), 0)
        out.append(total)
    return out


def trends(conn: sqlite3.Connection, user_id: int, today: date, n: int = 12) -> dict:
    """Everything on the Trends page. The current period is "so far": it is shown in the charts
    but left out of every average and comparison. Periods before the first expense are skipped."""
    from .period import period_for_date, shift_period

    start_day = get_start_day(conn, user_id)
    cur_key = period_for_date(today, start_day)
    first = conn.execute(f"SELECT MIN(e.date) FROM expenses e {MY_SHARE_JOIN}", {"uid": user_id}).fetchone()[0]
    keys = [shift_period(*cur_key, -k) for k in range(n - 1, -1, -1)]
    if first is not None:
        first_key = period_for_date(date.fromisoformat(first), start_day)
        keys = [k for k in keys if k >= first_key]
    result = {"n": n, "ranges": TREND_RANGES, "empty": first is None or not keys}
    if result["empty"]:
        return result

    months = [month_summary(conn, user_id, y, m) for y, m in keys]
    labels = [f"{MONTH_ABBR[m]} {y % 100:02d}" for y, m in keys]
    current, complete = months[-1], months[:-1]
    result.update(labels=labels, current_label=labels[-1], n_complete=len(complete),
                  range=range_label(months[0]["start"], current["end"]))

    # 2. savings rate: left over as % of income
    def rate(ms):
        return round(ms["left"] * 100 / ms["income"], 1) if ms["income"] > 0 else None
    rates = [rate(ms) for ms in months]
    known = [r for r in rates[:-1] if r is not None]
    result["savings"] = {
        "values": rates,
        "avg": round(sum(known) / len(known), 1) if known else None,
        "current": rates[-1],
        "enough": len(known) >= 2,
    }

    # 3. category trends: my cost per category per period, top 5 shown by default
    def spent_in(ms, cid):
        return next((c["spent"] for c in ms["categories"] if c["id"] == cid), 0)
    cats = conn.execute(f"SELECT c.id, c.name, c.is_joint FROM categories c WHERE {VISIBLE_SQL} "
                        "ORDER BY c.is_joint, c.sort_order, c.name", {"uid": user_id}).fetchall()
    series = []
    for c in cats:
        values = [spent_in(ms, c["id"]) for ms in months]
        if sum(values):
            series.append({"id": c["id"], "name": c["name"], "values": values, "total": sum(values),
                           "joint": bool(c["is_joint"])})
    series.sort(key=lambda s: s["total"], reverse=True)
    for i, s in enumerate(series):
        s["visible"] = i < 5
    result["categories"] = {"series": series, "enough": sum(1 for ms in months if ms["n_expenses"]) >= 2}

    # 4. biggest changes: last complete period vs the average of the (up to) 3 before it
    changes = []
    if len(complete) >= 2:
        last, base_months = complete[-1], complete[-4:-1]
        for s in series:
            spent = spent_in(last, s["id"])
            base = round_div(sum(spent_in(ms, s["id"]) for ms in base_months), len(base_months))
            diff = spent - base
            big = abs(diff) >= CHANGE_MIN_CENTS and (base == 0 or abs(diff) * 100 >= CHANGE_MIN_PCT * base)
            if big:
                changes.append({"name": s["name"], "id": s["id"], "joint": s["joint"], "spent": spent, "base": base, "diff": diff,
                                "pct": None if base == 0 else diff * 100 / base})
        changes.sort(key=lambda c: abs(c["diff"]), reverse=True)
        result["changes_period"] = labels[-2]
        result["changes_base"] = labels[max(0, len(labels) - 2 - len(base_months)):len(labels) - 2]
    result["changes"] = changes[:6]
    result["changes_enough"] = len(complete) >= 2

    # 5. spending pace: this period day by day vs the typical curve of previous periods
    days = (current["end"] - current["start"]).days + 1
    day_now = (today - current["start"]).days + 1
    now_curve = _daily_cumulative(conn, user_id, current["start"], current["end"], days)
    history = [ms for ms in complete if ms["n_expenses"]][-PACE_HISTORY:]
    pace = {"enough": bool(history), "day": day_now, "days": days,
            "labels": [str(i) for i in range(1, days + 1)],
            "current": [v / 100 if i < day_now else None for i, v in enumerate(now_curve)]}
    if history:
        curves = [_daily_cumulative(conn, user_id, ms["start"], ms["end"], days) for ms in history]
        typical = [round_div(sum(c[i] for c in curves), len(curves)) for i in range(days)]
        spent_now, usual_now = now_curve[day_now - 1], typical[day_now - 1]
        pace.update(typical=[v / 100 for v in typical], spent_now=spent_now, usual_now=usual_now,
                    diff=spent_now - usual_now, pct=None if usual_now == 0 else (spent_now - usual_now) * 100 / usual_now,
                    n_history=len(history))
    result["pace"] = pace

    result["chart"] = {
        "labels": labels,
        "savings": rates, "savings_avg": result["savings"]["avg"],
        "categories": [{"name": s["name"], "values": [v / 100 for v in s["values"]], "hidden": not s["visible"]}
                       for s in series],
        "pace": {k: pace.get(k) for k in ("labels", "current", "typical")},
    }
    return result


# --- Budget track record (Budget page) -----------------------------------------------------

RECORD_PERIODS = 12


def budget_record(conn: sqlite3.Connection, user_id: int, today: date, n: int = RECORD_PERIODS) -> dict:
    """How often each category ended a period within its budget, over the finished periods among
    the last `n` (from the first expense on). Sorted by the share within, lowest first."""
    from .period import period_for_date, shift_period

    start_day = get_start_day(conn, user_id)
    cur = period_for_date(today, start_day)
    first = conn.execute(f"SELECT MIN(e.date) FROM expenses e {MY_SHARE_JOIN}", {"uid": user_id}).fetchone()[0]
    keys = [shift_period(*cur, -k) for k in range(n - 1, 0, -1)]          # finished periods only
    keys = [k for k in keys if first is not None and k >= period_for_date(date.fromisoformat(first), start_day)]
    complete = [month_summary(conn, user_id, y, m) for y, m in keys]
    cats = conn.execute(f"SELECT c.id, c.name, c.is_joint FROM categories c WHERE {VISIBLE_SQL} "
                        "ORDER BY c.is_joint, c.sort_order, c.name", {"uid": user_id}).fetchall()
    record = []
    for c in cats:
        with_budget = within = 0
        for ms in complete:
            row = next((x for x in ms["categories"] if x["id"] == c["id"]), None)
            if row and row["budget"] > 0:
                with_budget += 1
                within += row["spent"] <= row["budget"]
        if with_budget:
            record.append({"name": c["name"], "id": c["id"], "joint": bool(c["is_joint"]), "within": within, "of": with_budget,
                           "pct": within * 100 / with_budget})
    record.sort(key=lambda r: (r["pct"], r["name"]))
    return {"record": record, "enough": bool(complete), "n_complete": len(complete),
            "range": range_label(complete[0]["start"], complete[-1]["end"]) if complete else ""}


# --- "your period resets soon" banner ---------------------------------------------------------------

RESET_NOTICE_DAYS = 3


def reset_notice(conn: sqlite3.Connection, user_id: int, today: date) -> dict | None:
    """Shown during the last 3 days before the user's own period resets."""
    from datetime import timedelta
    from .period import period_for_date

    s = get_start_day(conn, user_id)
    _, end = period_bounds(*period_for_date(today, s), s)
    resets = end + timedelta(days=1)
    days = (resets - today).days                                   # 1, 2 or 3 -> show
    if days > RESET_NOTICE_DAYS:
        return None
    return {"resets": resets, "days": days, "key": resets.isoformat()}

