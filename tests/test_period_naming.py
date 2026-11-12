"""Periods named after the month they START in (paid on the 5th for that month).

With S = 5 and naming "start", "November 2026" = 5 Nov - 4 Dec 2026.
"""
from datetime import date

import pytest

from app import recurring, summary
from app.period import PeriodRule, period_bounds, period_for_date, shift_period


def _post(client, url, **data):
    return client.post(url, data=data, follow_redirects=False)


# --- period_for_date / period_bounds with naming="start" -------------------------------

@pytest.mark.parametrize("d, expected", [
    (date(2026, 11, 4), (2026, 10)),   # day before payday -> still October's money
    (date(2026, 11, 5), (2026, 11)),   # payday -> November
    (date(2026, 11, 30), (2026, 11)),
    (date(2026, 12, 4), (2026, 11)),   # last day of "November"
    (date(2026, 12, 5), (2026, 12)),
    (date(2027, 1, 4), (2026, 12)),    # across the year boundary
    (date(2027, 1, 5), (2027, 1)),
])
def test_for_date_start_naming_s5(d, expected):
    assert period_for_date(d, 5, "start") == expected


def test_bounds_start_naming():
    assert period_bounds(2026, 11, 5, "start") == (date(2026, 11, 5), date(2026, 12, 4))
    assert period_bounds(2026, 12, 5, "start") == (date(2026, 12, 5), date(2027, 1, 4))
    assert period_bounds(2026, 12, 2, "start") == (date(2026, 12, 2), date(2027, 1, 1))
    assert period_bounds(2027, 1, 28, "start") == (date(2027, 1, 28), date(2027, 2, 27))
    # "February" with S = 28 ends on 27 March in both leap and non-leap years
    assert period_bounds(2027, 2, 28, "start") == (date(2027, 2, 28), date(2027, 3, 27))
    assert period_bounds(2028, 2, 28, "start") == (date(2028, 2, 28), date(2028, 3, 27))


def test_start_naming_is_end_naming_shifted_by_one_month():
    for s in (2, 5, 15, 28):
        for y, m in ((2026, 1), (2026, 11), (2026, 12), (2028, 2)):
            assert period_bounds(y, m, s, "start") == period_bounds(*shift_period(y, m, 1), s, "end")


@pytest.mark.parametrize("d", [date(2026, 1, 1), date(2026, 11, 5), date(2028, 2, 29), date(2026, 12, 31)])
def test_s1_is_the_calendar_month_with_either_naming(d):
    assert period_for_date(d, 1, "start") == period_for_date(d, 1, "end") == (d.year, d.month)
    assert period_bounds(2026, 11, 1, "start") == period_bounds(2026, 11, 1, "end")


@pytest.mark.parametrize("naming", ["end", "start"])
@pytest.mark.parametrize("s", [1, 2, 5, 15, 27, 28])
def test_periods_tile_without_gaps_or_overlaps(s, naming):
    """Every day 2025-2029 is in exactly one period, and both functions agree."""
    y, m = 2025, 1
    d = period_bounds(y, m, s, naming)[0]
    for _ in range(60):
        start, end = period_bounds(y, m, s, naming)
        assert start == d
        assert period_for_date(start, s, naming) == (y, m)
        assert period_for_date(end, s, naming) == (y, m)
        d = date.fromordinal(end.toordinal() + 1)
        y, m = shift_period(y, m, 1)


@pytest.mark.parametrize("bad", ["", "begin", None, "START"])
def test_invalid_naming(bad):
    with pytest.raises(ValueError):
        period_for_date(date(2026, 1, 1), 5, bad)
    with pytest.raises(ValueError):
        period_bounds(2026, 1, 5, bad)
    with pytest.raises(ValueError):
        PeriodRule(5, bad)


def test_rule_lenient_falls_back_to_defaults():
    assert PeriodRule.lenient(5, "start") == PeriodRule(5, "start")
    assert PeriodRule.lenient(99, "weird") == PeriodRule(28, "end")
    assert PeriodRule.lenient(None, None) == PeriodRule()


# --- the whole app with a "paid on the 5th for this month" user ---------------------------

@pytest.fixture
def paid_on_5th(conn, uid):
    cid = conn.execute("SELECT id FROM categories WHERE user_id = ? ORDER BY sort_order LIMIT 1",
                       (uid,)).fetchone()[0]
    conn.executemany(
        "INSERT INTO expenses (date, description, category_id, amount_cents) VALUES (?, '', ?, ?)",
        [("2026-11-04", cid, 1000),    # October's money
         ("2026-11-05", cid, 2000),    # November
         ("2026-12-04", cid, 3000),    # November (last day)
         ("2026-12-05", cid, 4000)])   # December
    conn.execute("INSERT INTO extra_income (user_id, date, description, amount_cents) VALUES (?, '2026-11-05', 'Salary', 150000)",
                 (uid,))
    conn.execute("UPDATE users SET period_start_day = 5, period_naming = 'start' WHERE id = ?", (uid,))
    conn.commit()
    return conn


def test_month_summary_uses_start_naming(paid_on_5th, uid):
    s = summary.month_summary(paid_on_5th, uid, 2026, 11)
    assert (s["start"], s["end"]) == (date(2026, 11, 5), date(2026, 12, 4))
    assert s["range"] == "5 Nov – 4 Dec 2026"
    assert s["spent"] == 5000          # 20.00 + 30.00
    assert s["extra"] == 150000        # the salary on the 5th counts for November


def test_year_view_with_start_naming(paid_on_5th, uid):
    y = summary.year_summary(paid_on_5th, uid, 2026, date(2026, 12, 10))
    assert y["range"] == "5 Jan 2026 – 4 Jan 2027"
    assert y["periods"][10]["range"] == "5 Nov – 4 Dec 2026"       # November
    assert y["periods"][11]["future"] is False                       # December started on 5 Dec


def test_pages_show_start_naming(client, paid_on_5th, monkeypatch):
    monkeypatch.setattr("app.config.today", lambda: date(2026, 11, 20))
    assert "5 Nov – 4 Dec 2026" in client.get("/month?period=2026-11").text
    home = client.get("/").text
    assert "November 2026" in home
    settings = client.get("/profile").text
    assert "Today is in “November 2026”: 5 Nov – 4 Dec 2026." in settings
    assert 'value="start" checked' in settings


def test_recurring_horizon_follows_naming(paid_on_5th, uid):
    assert recurring.horizon(paid_on_5th, uid, date(2026, 11, 20)) == date(2026, 12, 4)
    assert recurring.horizon(paid_on_5th, uid, date(2026, 11, 4)) == date(2026, 11, 4)


# --- settings form -------------------------------------------------------------------------

def test_save_start_day_and_naming(client, conn, uid):
    assert summary.get_period_rule(conn, uid) == PeriodRule(28, "end")      # default for existing users
    assert _post(client, "/profile/start-day", start_day="5", period_naming="start").status_code == 303
    assert summary.get_period_rule(conn, uid) == PeriodRule(5, "start")
    kinds = [r[0] for r in conn.execute("SELECT kind FROM activity_log WHERE actor_id = ? ORDER BY id", (uid,))]
    assert kinds[-2:] == ["account.start_day", "account.period_naming"]


def test_old_form_without_naming_keeps_the_current_naming(client, conn, uid):
    _post(client, "/profile/start-day", start_day="5", period_naming="start")
    assert _post(client, "/profile/start-day", start_day="10").status_code == 303
    assert summary.get_period_rule(conn, uid) == PeriodRule(10, "start")


def test_invalid_naming_is_refused(client, conn, uid):
    r = _post(client, "/profile/start-day", start_day="5", period_naming="sideways")
    assert r.status_code == 422 and "Choose how periods are named." in r.text
    assert summary.get_period_rule(conn, uid) == PeriodRule(28, "end")


def test_database_refuses_invalid_naming(conn, uid):
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE users SET period_naming = 'sideways' WHERE id = ?", (uid,))
