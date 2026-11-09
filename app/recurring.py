"""Recurring expenses: rules that create ordinary expenses on a schedule.

Each rule's occurrences are created up to the end of the owner's current budget period, so the
rest of this period's payments show as future-dated (tagged, hatched in the charts). Catching up
runs on the owner's page loads (see main.create_app), so nothing depends on a background job.

Changes to a rule (edit, pause, end, delete) only affect expenses dated after today: those are
removed and re-created from the new rule. Anything dated today or earlier is left alone.
"""
from __future__ import annotations

import calendar
from datetime import date

from . import audit, joint
from .period import period_bounds, period_for_date

FREQUENCIES = {1: "Monthly", 3: "Every 3 months", 6: "Every 6 months", 12: "Yearly"}
MAX_CATCH_UP = 120          # never create more than this many expenses for one rule in one go


def occurrence(start: date, every_months: int, k: int) -> date:
    """The k-th payment date (k = 0 is start). The day is clamped to the month, without drift."""
    index = start.year * 12 + (start.month - 1) + k * every_months
    y, m = index // 12, index % 12 + 1
    return date(y, m, min(start.day, calendar.monthrange(y, m)[1]))


def first_index_after(rule, d: date, inclusive: bool = False) -> int:
    """Smallest k whose payment date is after d (or on/after d with inclusive)."""
    start = date.fromisoformat(rule["start_date"])
    k = 0
    if start <= d:
        months = (d.year - start.year) * 12 + (d.month - start.month)
        k = max(0, months // rule["every_months"] - 1)
    while True:
        o = occurrence(start, rule["every_months"], k)
        if o > d or (inclusive and o == d):
            return k
        k += 1


def horizon(conn, uid: int, today: date) -> date:
    """Payments are created up to the last day of the user's current period."""
    start_day = conn.execute("SELECT period_start_day FROM users WHERE id = ?", (uid,)).fetchone()[0]
    return period_bounds(*period_for_date(today, start_day), start_day)[1]


def next_date(rule, today: date) -> date | None:
    """The next payment after today (already created as a future-dated expense or not), or None
    if the rule has ended."""
    start = date.fromisoformat(rule["start_date"])
    k = first_index_after(rule, today)
    d = occurrence(start, rule["every_months"], k)
    if rule["end_date"] and d > date.fromisoformat(rule["end_date"]):
        return None
    return d


def _usable(conn, uid: int, cid: int, d: date) -> bool:
    """May this user log an expense in the category on that day? (Archived or left: no.)"""
    c = conn.execute("SELECT user_id, is_joint, archived FROM categories WHERE id = ?", (cid,)).fetchone()
    if c is None or c["archived"]:
        return False
    if c["is_joint"]:
        return joint.can_log_on(conn, cid, uid, d) is None
    return c["user_id"] == uid


def insert_expense(conn, uid: int, values: dict, recurring_id: int | None = None) -> int:
    """Create one expense (own or shared) with its cost rows. values: date, description,
    category_id, amount_cents, notes, one_off."""
    cur = conn.execute(
        "INSERT INTO expenses (user_id, date, description, category_id, amount_cents, notes, one_off, recurring_id) "
        "VALUES (:uid, :date, :description, :category_id, :amount_cents, :notes, :one_off, :rid)",
        {"notes": "", "one_off": 0, **values, "uid": uid, "rid": recurring_id})
    joint.reallocate_expense(conn, cur.lastrowid)
    return cur.lastrowid


def catch_up(conn, uid: int, today: date) -> int:
    """Create every due payment of the user's active rules, up to the horizon. Returns how many.
    Payments that can't be logged (category archived, not a member that day) are skipped."""
    rules = conn.execute("SELECT * FROM recurring_expenses WHERE user_id = ? AND active = 1", (uid,)).fetchall()
    if not rules:
        return 0
    until = horizon(conn, uid, today)
    made = 0
    for r in rules:
        start = date.fromisoformat(r["start_date"])
        end = date.fromisoformat(r["end_date"]) if r["end_date"] else None
        due, k = [], r["next_index"]
        while len(due) < MAX_CATCH_UP:
            d = occurrence(start, r["every_months"], k)
            if d > until or (end and d > end):
                break
            due.append(d)
            k += 1
        if not due:
            continue
        with conn:
            # Claim these payments first: if another request got here at the same moment,
            # next_index has already moved and this one does nothing (no duplicates).
            if conn.execute("UPDATE recurring_expenses SET next_index = ? WHERE id = ? AND next_index = ? AND active = 1",
                            (k, r["id"], r["next_index"])).rowcount != 1:
                continue
            for d in due:
                if not _usable(conn, uid, r["category_id"], d):
                    continue
                insert_expense(conn, uid, {"date": d.isoformat(), "description": r["description"],
                                           "category_id": r["category_id"], "amount_cents": r["amount_cents"],
                                           "notes": r["notes"]}, recurring_id=r["id"])
                audit.log(conn, uid, "expense.added",
                          "Added " + joint.describe_expense(conn, {"category_id": r["category_id"], "date": d.isoformat()})
                          + " from a recurring expense", category_id=r["category_id"])
                made += 1
    return made


def drop_future(conn, rule, today: date) -> int:
    """Remove the rule's expenses dated after today and rewind next_index so they can be
    re-created from the (changed) rule. Call inside a transaction."""
    n = conn.execute("DELETE FROM expenses WHERE recurring_id = ? AND date > ?",
                     (rule["id"], today.isoformat())).rowcount
    rewind = min(rule["next_index"], first_index_after(rule, today))
    conn.execute("UPDATE recurring_expenses SET next_index = ? WHERE id = ?", (rewind, rule["id"]))
    return n
