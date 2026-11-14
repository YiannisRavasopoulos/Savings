from datetime import date

import pytest

from app.period import period_bounds, period_for_date, range_label, shift_period


# --- period_for_date, S = 28 ------------------------------------------------

@pytest.mark.parametrize("d, expected", [
    (date(2026, 11, 27), (2026, 11)),  # day before S
    (date(2026, 11, 28), (2026, 12)),  # on S -> next period
    (date(2026, 11, 29), (2026, 12)),  # day after S
    (date(2026, 10, 28), (2026, 11)),  # first day of "November 2026"
    (date(2026, 11, 1), (2026, 11)),
    (date(2026, 11, 30), (2026, 12)),
])
def test_for_date_s28(d, expected):
    assert period_for_date(d, 28) == expected


def test_for_date_s28_year_boundary():
    assert period_for_date(date(2026, 12, 27), 28) == (2026, 12)
    assert period_for_date(date(2026, 12, 28), 28) == (2027, 1)
    assert period_for_date(date(2026, 12, 31), 28) == (2027, 1)
    assert period_for_date(date(2027, 1, 1), 28) == (2027, 1)
    assert period_for_date(date(2027, 1, 27), 28) == (2027, 1)
    assert period_for_date(date(2027, 1, 28), 28) == (2027, 2)


def test_for_date_february_and_leap_years():
    assert period_for_date(date(2027, 2, 27), 28) == (2027, 2)
    assert period_for_date(date(2027, 2, 28), 28) == (2027, 3)   # non-leap last day
    assert period_for_date(date(2028, 2, 28), 28) == (2028, 3)
    assert period_for_date(date(2028, 2, 29), 28) == (2028, 3)   # leap day
    assert period_for_date(date(2028, 2, 29), 1, "start") == (2028, 2)


# --- period_for_date, S = 1 "that same month" (calendar months) -----------------

@pytest.mark.parametrize("d, expected", [
    (date(2026, 10, 31), (2026, 10)),
    (date(2026, 11, 1), (2026, 11)),
    (date(2026, 11, 2), (2026, 11)),
    (date(2026, 11, 30), (2026, 11)),
    (date(2026, 12, 31), (2026, 12)),
    (date(2027, 1, 1), (2027, 1)),
])
def test_for_date_s1(d, expected):
    assert period_for_date(d, 1, "start") == expected


# --- other S values: before / on / after ---------------------------------------

@pytest.mark.parametrize("s", [2, 10, 15, 25])
def test_for_date_around_start_day(s):
    assert period_for_date(date(2026, 6, s - 1), s) == (2026, 6)
    assert period_for_date(date(2026, 6, s), s) == (2026, 7)
    assert period_for_date(date(2026, 6, s + 1), s) == (2026, 7)


# --- period_bounds ---------------------------------------------------------------

def test_bounds_s28_spec_examples():
    assert period_bounds(2026, 11, 28) == (date(2026, 10, 28), date(2026, 11, 27))
    assert period_bounds(2027, 1, 28) == (date(2026, 12, 28), date(2027, 1, 27))
    assert period_bounds(2026, 12, 28) == (date(2026, 11, 28), date(2026, 12, 27))


def test_bounds_s28_february_and_march():
    assert period_bounds(2027, 2, 28) == (date(2027, 1, 28), date(2027, 2, 27))
    # March starts on 28 Feb; in a leap year 29 Feb is inside March's period.
    assert period_bounds(2027, 3, 28) == (date(2027, 2, 28), date(2027, 3, 27))
    assert period_bounds(2028, 3, 28) == (date(2028, 2, 28), date(2028, 3, 27))


def test_bounds_s1_calendar_months():
    assert period_bounds(2026, 11, 1, "start") == (date(2026, 11, 1), date(2026, 11, 30))
    assert period_bounds(2026, 12, 1, "start") == (date(2026, 12, 1), date(2026, 12, 31))
    assert period_bounds(2027, 1, 1, "start") == (date(2027, 1, 1), date(2027, 1, 31))
    assert period_bounds(2027, 2, 1, "start") == (date(2027, 2, 1), date(2027, 2, 28))
    assert period_bounds(2028, 2, 1, "start") == (date(2028, 2, 1), date(2028, 2, 29))  # leap
    assert period_bounds(2100, 2, 1, "start") == (date(2100, 2, 1), date(2100, 2, 28))  # not leap


def test_bounds_s2_january():
    assert period_bounds(2027, 1, 2) == (date(2026, 12, 2), date(2027, 1, 1))


@pytest.mark.parametrize("s", [1, 2, 15, 27, 28])
def test_periods_tile_without_gaps_or_overlaps(s):
    """Every day 2025-2029 is in exactly one period, and both functions agree."""
    y, m = 2025, 1
    start, _ = period_bounds(y, m, s)
    d = start
    for _ in range(60):
        start, end = period_bounds(y, m, s)
        assert start == d
        assert period_for_date(start, s) == (y, m)
        assert period_for_date(end, s) == (y, m)
        d = date.fromordinal(end.toordinal() + 1)
        y, m = shift_period(y, m, 1)


@pytest.mark.parametrize("bad", [0, 32, -1, "28", True])
def test_invalid_start_day(bad):
    with pytest.raises(ValueError):
        period_for_date(date(2026, 1, 1), bad)
    with pytest.raises(ValueError):
        period_bounds(2026, 1, bad)


def test_shift_period_across_years():
    assert shift_period(2026, 12, 1) == (2027, 1)
    assert shift_period(2027, 1, -1) == (2026, 12)
    assert shift_period(2026, 5, -17) == (2024, 12)


def test_range_label():
    assert range_label(date(2026, 10, 28), date(2026, 11, 27)) == "28 Oct – 27 Nov 2026"
    assert range_label(date(2026, 12, 28), date(2027, 1, 27)) == "28 Dec 2026 – 27 Jan 2027"


def test_timezone_from_env_with_a_safe_default():
    from app import config
    assert config._zone("Europe/Berlin").key == "Europe/Berlin"
    assert config._zone("").key == "Europe/Athens" and config._zone(None).key == "Europe/Athens"
    assert config._zone("Not/AZone").key == "Europe/Athens"
