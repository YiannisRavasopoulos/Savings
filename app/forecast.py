"""Savings forecast and "when can I comfortably buy this?" for planned purchases.

Everything is a transparent projection from the user's own history, not a black box:

* History: up to the last 12 finished periods since the first expense. One-off expenses are left
  out of "typical" spending (they are real, but not what a normal period costs).
* Typical spending per period = median; cautious spending = 75th percentile (a pricier period).
* Future income = regular income in effect for each period (scheduled changes included).
  Extra income is not projected; extra income already received this period does count.
* Current period: actually spent so far + the usual spending for the days that are left.
* Projected savings at period k = what's left over from now through period k.
* A plan "fits" in the first period where savings (plus what was already set aside for it,
  minus what earlier plans use) cover price + a cushion of 10 % of monthly income:
  with cautious numbers = "Confident", with typical numbers = "Likely".
"""
from __future__ import annotations

import math
import sqlite3
from datetime import date

from . import summary
from .db import BUDGET_AS_OF_SQL
from .joint import VISIBLE_SQL
from .period import MONTH_ABBR, period_bounds, period_for_date, period_key, period_label, shift_period

HISTORY = 12          # finished periods used as history
MIN_HISTORY = 3       # fewer than this: no suggestions
HORIZON = 12          # periods looked ahead, including the current one
CUSHION_PCT = 10      # money that should still be left after the purchase, % of monthly income
MY_SHARE_JOIN = "JOIN expense_shares s ON s.expense_id = e.id AND s.user_id = ?"   # the user's own cost


def percentile(values: list[int], q: float) -> float:
    """Linear-interpolation percentile (q in 0..1) of a non-empty list."""
    s = sorted(values)
    pos = (len(s) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def _period_spending(conn, uid: int, start: date, end: date, *, include_one_offs: bool) -> int:
    extra = "" if include_one_offs else " AND e.one_off = 0"
    return conn.execute(
        f"SELECT COALESCE(SUM(s.cents), 0) FROM expenses e {MY_SHARE_JOIN} "
        f"WHERE e.date BETWEEN ? AND ?{extra}", (uid, start.isoformat(), end.isoformat())).fetchone()[0]


def _by_day(conn, uid: int, start: date, end: date, day: int) -> int:
    """Typical (non-one-off) spending from the period start through day `day` of it
    (a shorter period simply counts up to its own last day)."""
    last = min(end, date.fromordinal(start.toordinal() + day - 1))
    return _period_spending(conn, uid, start, last, include_one_offs=False)


def _category_typical(conn, uid: int, bounds: list[tuple[date, date]]) -> dict[int, float]:
    out: dict[int, list[int]] = {}
    for cid, in conn.execute(f"SELECT c.id FROM categories c WHERE {VISIBLE_SQL}", {"uid": uid}):
        out[cid] = []
    for start, end in bounds:
        rows = dict(conn.execute(
            f"SELECT e.category_id, SUM(s.cents) FROM expenses e {MY_SHARE_JOIN} "
            "WHERE e.one_off = 0 AND e.date BETWEEN ? AND ? GROUP BY e.category_id",
            (uid, start.isoformat(), end.isoformat())).fetchall())
        for cid in out:
            out[cid].append(rows.get(cid, 0))
    return {cid: percentile(v, 0.5) for cid, v in out.items() if v}


def _confidence(n: int, spread: float) -> str:
    if n >= 6 and spread <= 0.30:
        return "high"
    if n >= MIN_HISTORY and spread <= 0.60:
        return "medium"
    return "low"


def forecast(conn: sqlite3.Connection, uid: int, today: date) -> dict:
    start_day = summary.get_start_day(conn, uid)
    cur = period_for_date(today, start_day)
    first = conn.execute(f"SELECT MIN(e.date) FROM expenses e {MY_SHARE_JOIN}", (uid,)).fetchone()[0]
    first_key = period_for_date(date.fromisoformat(first), start_day) if first else cur
    hist_keys = [k for k in (shift_period(*cur, -i) for i in range(HISTORY, 0, -1)) if k >= first_key]
    n = len(hist_keys)
    result = {"n_history": n, "min_history": MIN_HISTORY, "ready": n >= MIN_HISTORY}
    if not result["ready"]:
        return result

    bounds = [period_bounds(y, m, start_day) for y, m in hist_keys]
    spend = [_period_spending(conn, uid, s, e, include_one_offs=False) for s, e in bounds]
    typical, cautious = percentile(spend, 0.5), percentile(spend, 0.75)
    spread = (percentile(spend, 0.75) - percentile(spend, 0.25)) / typical if typical else 1.0
    hist_left = [summary.regular_income_for(conn, uid, e) - s for (_, e), s in zip(bounds, spend)]

    # the current period: real spending so far + the usual spending for the rest of it
    c_start, c_end = period_bounds(*cur, start_day)
    day = (today - c_start).days + 1
    spent_so_far = _period_spending(conn, uid, c_start, today, include_one_offs=True)
    usual_by_now = percentile([_by_day(conn, uid, s, e, day) for s, e in bounds], 0.5)
    extra_now = conn.execute("SELECT COALESCE(SUM(amount_cents), 0) FROM extra_income "
                             "WHERE user_id = ? AND date BETWEEN ? AND ?",
                             (uid, c_start.isoformat(), c_end.isoformat())).fetchone()[0]

    periods = []
    cum_typ = cum_cau = 0.0
    for k in range(HORIZON):
        y, m = shift_period(*cur, k)
        start, end = period_bounds(y, m, start_day)
        income = summary.regular_income_for(conn, uid, end)
        if k == 0:
            income += extra_now
            left_typ = income - spent_so_far - max(0.0, typical - usual_by_now)
            left_cau = income - spent_so_far - max(0.0, cautious - usual_by_now)
        else:
            left_typ, left_cau = income - typical, income - cautious
        cum_typ += left_typ
        cum_cau += left_cau
        periods.append({"key": period_key(y, m), "year": y, "month": m, "label": period_label(y, m),
                        "short": f"{MONTH_ABBR[m]} {y % 100:02d}", "start": start, "end": end,
                        "income": income, "left_typical": round(left_typ), "left_cautious": round(left_cau),
                        "saved_typical": round(cum_typ), "saved_cautious": round(cum_cau)})

    income_now = summary.regular_income_for(conn, uid, c_end)
    result.update(
        typical=round(typical), cautious=round(cautious), spread=spread,
        confidence=_confidence(n, spread), periods=periods, day=day,
        spent_so_far=spent_so_far, cushion=income_now * CUSHION_PCT // 100, income_now=income_now, today=today,
        left_low=round(percentile(hist_left, 0.25)), left_high=round(percentile(hist_left, 0.75)),
        category_typical=_category_typical(conn, uid, bounds),
        chart={"labels": [p["short"] for p in periods],
               "typical": [p["saved_typical"] / 100 for p in periods],
               "cautious": [p["saved_cautious"] / 100 for p in periods]},
    )
    return result


def fc_today(fc: dict) -> date:
    return fc["today"]


def place_plans(conn: sqlite3.Connection, uid: int, fc: dict, plans: list) -> list[dict]:
    """Suggest a period for each plan, in priority order. Earlier plans use up savings first."""
    out = []
    if not fc.get("ready"):
        return [{"plan": p} for p in plans]
    periods, cushion = fc["periods"], fc["cushion"]
    used_typ = [0] * len(periods)        # savings already claimed by earlier plans, per period
    used_cau = [0] * len(periods)
    from .joint import category as joint_category, largest_remainder, split_at
    for p in plans:
        price = p["amount_cents"]
        jcat = joint_category(conn, p["category_id"]) if p["category_id"] else None
        if jcat is not None:
            # In a shared category you only pay your share once it's bought and logged.
            split = split_at(conn, jcat["id"], fc_today(fc))
            price = largest_remainder(price, split).get(uid, 0) if split else price
        cost = max(0, price - p["saved_cents"])          # what still has to come out of savings
        need = cost + cushion

        def first_fit(kind, used):
            """First period from which savings stay above the cushion in every later period too,
            so a lower-priority plan never eats money a higher-priority one was counting on."""
            avail = [per[f"saved_{kind}"] - used[j] for j, per in enumerate(periods)]
            for k in range(len(periods)):
                if all(a >= need for a in avail[k:]):
                    return k
            return None

        k_cau = first_fit("cautious", used_cau)
        k_typ = first_fit("typical", used_typ)
        for used, k in ((used_cau, k_cau), (used_typ, k_typ)):
            if k is not None:
                for j in range(k, len(periods)):
                    used[j] += cost
        info = {"plan": p, "k_confident": k_cau, "k_likely": k_typ, "need": need,
                "my_price": price, "shared": jcat is not None}
        if k_cau is not None:
            per = periods[k_cau]
            info["confident"] = per
            info["after"] = per["saved_cautious"] - used_cau[k_cau]     # still saved after paying
        if k_typ is not None and (k_cau is None or k_typ < k_cau):
            info["likely"] = periods[k_typ]
        if k_cau is None and k_typ is None:
            per_period = fc["income_now"] - fc["typical"]          # what a typical period saves
            info["per_period"] = per_period
            info["periods_needed"] = math.ceil(need / per_period) if per_period > 0 else None
        # category check for the suggested period
        target = info.get("confident") or info.get("likely")
        if target and p["category_id"]:
            from .db import budget_of
            budget = budget_of(conn, p["category_id"], uid, target["end"])        # your own budget
            usual = round(fc["category_typical"].get(p["category_id"], 0))   # your share of usual spending
            if budget > 0:
                over = usual + price - budget
                info["category"] = {"budget": budget, "usual": usual, "over": over}
        out.append(info)
    return out
