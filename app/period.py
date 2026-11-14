"""Budget periods. The only place that knows how dates map to "months".

A user's periods are set by a start day S (1-28) and a naming rule:

  * naming "end" (default): a period is named after the month it ENDS in.
        S > 1: (year, month) runs from day S of the previous month to day S-1 of `month`.
               e.g. S=28, (2026, 11) = 2026-10-28 .. 2026-11-27  (paid late in October for November)
  * naming "start": a period is named after the month it STARTS in.
        S > 1: (year, month) runs from day S of `month` to day S-1 of the next month.
               e.g. S=5, (2026, 11) = 2026-11-05 .. 2026-12-04   (paid on 5 November for November)
  * S = 1: the plain calendar month with either naming, e.g. (2026, 11) = 2026-11-01 .. 2026-11-30.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

MONTH_NAMES = [None, "January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]
MONTH_ABBR = [None, "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct",
              "Nov", "Dec"]
NAMINGS = ("end", "start")
DEFAULT_START_DAY = 28
DEFAULT_NAMING = "end"


def _check_start_day(start_day: int) -> None:
    if not isinstance(start_day, int) or not 1 <= start_day <= 28:
        raise ValueError(f"period start day must be 1-28, got {start_day!r}")


def _check_naming(naming: str) -> None:
    if naming not in NAMINGS:
        raise ValueError(f"period naming must be one of {NAMINGS}, got {naming!r}")


def shift_period(year: int, month: int, delta: int) -> tuple[int, int]:
    """Move delta periods forward (or back if negative)."""
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def period_for_date(d: date, start_day: int, naming: str = DEFAULT_NAMING) -> tuple[int, int]:
    """Return (year, month) of the period that contains d."""
    _check_start_day(start_day)
    _check_naming(naming)
    if start_day == 1:
        return d.year, d.month
    if naming == "start":
        return (d.year, d.month) if d.day >= start_day else shift_period(d.year, d.month, -1)
    return (d.year, d.month) if d.day < start_day else shift_period(d.year, d.month, 1)


def period_bounds(year: int, month: int, start_day: int,
                  naming: str = DEFAULT_NAMING) -> tuple[date, date]:
    """Return (first_day, last_day) of the period, both inclusive."""
    _check_start_day(start_day)
    _check_naming(naming)
    if not 1 <= month <= 12:
        raise ValueError(f"month must be 1-12, got {month!r}")
    if start_day == 1:
        return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
    if naming == "start":
        next_year, next_month = shift_period(year, month, 1)
        return date(year, month, start_day), date(next_year, next_month, start_day - 1)
    prev_year, prev_month = shift_period(year, month, -1)
    return date(prev_year, prev_month, start_day), date(year, month, start_day - 1)


@dataclass(frozen=True)
class PeriodRule:
    """A user's period settings. Pass this around instead of a bare start day."""
    start_day: int = DEFAULT_START_DAY
    naming: str = DEFAULT_NAMING

    def __post_init__(self):
        _check_start_day(self.start_day)
        _check_naming(self.naming)

    @classmethod
    def lenient(cls, start_day, naming) -> "PeriodRule":
        """From stored values; anything invalid falls back to the defaults."""
        s = start_day if isinstance(start_day, int) and 1 <= start_day <= 28 else DEFAULT_START_DAY
        return cls(s, naming if naming in NAMINGS else DEFAULT_NAMING)

    def for_date(self, d: date) -> tuple[int, int]:
        return period_for_date(d, self.start_day, self.naming)

    def bounds(self, year: int, month: int) -> tuple[date, date]:
        return period_bounds(year, month, self.start_day, self.naming)

    def current_bounds(self, today: date) -> tuple[date, date]:
        return self.bounds(*self.for_date(today))


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
