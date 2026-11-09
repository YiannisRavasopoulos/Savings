"""Budget periods. The only place that knows how dates map to "months".

With start day S (1-28), the period labelled (year, month):
  * S > 1: runs from day S of the previous month to day S-1 of `month`.
           e.g. S=28, (2026, 11) = 2026-10-28 .. 2026-11-27
  * S = 1: is the plain calendar month, e.g. (2026, 11) = 2026-11-01 .. 2026-11-30.
In both cases the period is named after the month (and year) it ends in.
"""
from __future__ import annotations

import calendar
from datetime import date

MONTH_NAMES = [None, "January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]
MONTH_ABBR = [None, "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct",
              "Nov", "Dec"]


def _check_start_day(start_day: int) -> None:
    if not isinstance(start_day, int) or not 1 <= start_day <= 28:
        raise ValueError(f"period start day must be 1-28, got {start_day!r}")


def shift_period(year: int, month: int, delta: int) -> tuple[int, int]:
    """Move delta periods forward (or back if negative)."""
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def period_for_date(d: date, start_day: int) -> tuple[int, int]:
    """Return (year, month) of the period that contains d."""
    _check_start_day(start_day)
    if start_day == 1 or d.day < start_day:
        return d.year, d.month
    return shift_period(d.year, d.month, 1)


def period_bounds(year: int, month: int, start_day: int) -> tuple[date, date]:
    """Return (first_day, last_day) of the period, both inclusive."""
    _check_start_day(start_day)
    if not 1 <= month <= 12:
        raise ValueError(f"month must be 1-12, got {month!r}")
    if start_day == 1:
        return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
    prev_year, prev_month = shift_period(year, month, -1)
    return date(prev_year, prev_month, start_day), date(year, month, start_day - 1)


def period_key(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def period_label(year: int, month: int) -> str:
    return f"{MONTH_NAMES[month]} {year}"


def range_label(start: date, end: date) -> str:
    """e.g. '28 Oct – 27 Nov 2026' or '28 Dec 2026 – 27 Jan 2027'."""
    left = f"{start.day} {MONTH_ABBR[start.month]}"
    if start.year != end.year:
        left += f" {start.year}"
    return f"{left} – {end.day} {MONTH_ABBR[end.month]} {end.year}"
