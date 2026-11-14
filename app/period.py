"""Budget periods. The only place that knows how dates map to "months".

A user's periods come from one sentence: "my pay for a month arrives on day P of
[that same month | the month before]".

  * P is the payday, 1-31. In a month without that day (31 in April, 30 in February) the payday
    is that month's last day.
  * A period runs from one payday up to the day before the next payday.
  * It is named after the month the pay is FOR:
        naming "start" ("that same month"):  pay on 5 Nov  -> "November" = 5 Nov - 4 Dec
        naming "end"   ("the month before"): pay on 28 Oct -> "November" = 28 Oct - 27 Nov
  * P = 1 with "that same month" gives plain calendar months.

"The month before" needs a payday from the 20th on (MONTH_BEFORE_MIN_DAY) for new settings;
settings saved by older versions (e.g. day 10, the month before) keep working as they were.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

MONTH_NAMES = [None, "January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]
MONTH_ABBR = [None, "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct",
              "Nov", "Dec"]
NAMINGS = ("start", "end")              # "that same month", "the month before"
DEFAULT_PAYDAY = 28
DEFAULT_NAMING = "end"
MONTH_BEFORE_MIN_DAY = 20
MAX_PAYDAY = 31


def _check_payday(payday: int) -> None:
    if not isinstance(payday, int) or isinstance(payday, bool) or not 1 <= payday <= MAX_PAYDAY:
        raise ValueError(f"payday must be 1-{MAX_PAYDAY}, got {payday!r}")


def _check_naming(naming: str) -> None:
    if naming not in NAMINGS:
        raise ValueError(f"period naming must be one of {NAMINGS}, got {naming!r}")


def shift_period(year: int, month: int, delta: int) -> tuple[int, int]:
    """Move delta periods forward (or back if negative)."""
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def payday_in(year: int, month: int, payday: int) -> date:
    """The payday in that calendar month: day `payday`, or the month's last day if it's shorter."""
    return date(year, month, min(payday, calendar.monthrange(year, month)[1]))


def period_bounds(year: int, month: int, payday: int,
                  naming: str = DEFAULT_NAMING) -> tuple[date, date]:
    """Return (first_day, last_day) of the period named (year, month), both inclusive."""
    _check_payday(payday)
    _check_naming(naming)
    if not 1 <= month <= 12:
        raise ValueError(f"month must be 1-12, got {month!r}")
    first = (year, month) if naming == "start" else shift_period(year, month, -1)
    nxt = shift_period(*first, 1)
    return payday_in(*first, payday), payday_in(*nxt, payday) - timedelta(days=1)


def period_for_date(d: date, payday: int, naming: str = DEFAULT_NAMING) -> tuple[int, int]:
    """Return (year, month) of the period that contains d."""
    _check_payday(payday)
    _check_naming(naming)
    # the calendar month whose payday starts the period containing d
    first = (d.year, d.month) if d >= payday_in(d.year, d.month, payday) else shift_period(d.year, d.month, -1)
    return first if naming == "start" else shift_period(*first, 1)


def naming_allowed(payday: int, naming: str) -> bool:
    """The rule for new settings: pay from the month before arrives on the 20th or later."""
    return naming == "start" or payday >= MONTH_BEFORE_MIN_DAY


@dataclass(frozen=True)
class PeriodRule:
    """A user's period settings. Pass this around instead of a bare payday."""
    payday: int = DEFAULT_PAYDAY
    naming: str = DEFAULT_NAMING

    def __post_init__(self):
        _check_payday(self.payday)
        _check_naming(self.naming)

    @classmethod
    def lenient(cls, payday, naming) -> "PeriodRule":
        """From stored values; anything invalid falls back to the defaults."""
        p = payday if isinstance(payday, int) and 1 <= payday <= MAX_PAYDAY else DEFAULT_PAYDAY
        return cls(p, naming if naming in NAMINGS else DEFAULT_NAMING)

    @property
    def start_day(self) -> int:          # older name, kept for callers that only need the day
        return self.payday

    def for_date(self, d: date) -> tuple[int, int]:
        return period_for_date(d, self.payday, self.naming)

    def bounds(self, year: int, month: int) -> tuple[date, date]:
        return period_bounds(year, month, self.payday, self.naming)

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
