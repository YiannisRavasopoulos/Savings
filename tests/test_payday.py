"""Savings 1.5.0: "My pay for a month arrives on day P of [that same month | the month before]".

Paydays 1-31 (a month without day P uses its last day), a period runs from one payday to the day
before the next, and "the month before" needs the 20th or later for new settings.
"""
from datetime import date

import pytest

from app import db, summary
from app.period import PeriodRule, naming_allowed, period_bounds, period_for_date, payday_in, shift_period

from .conftest import make_user
from .test_db import _migrations_upto


def _post(client, url, **data):
    return client.post(url, data=data, follow_redirects=False)


def _rule(conn, uid):
    return summary.get_period_rule(conn, uid)


# --- paydays 29-31 ---------------------------------------------------------------------------------

def test_payday_in_uses_the_last_day_of_shorter_months():
    assert payday_in(2027, 2, 31) == date(2027, 2, 28)
    assert payday_in(2028, 2, 31) == date(2028, 2, 29)     # leap year
    assert payday_in(2027, 4, 31) == date(2027, 4, 30)
    assert payday_in(2027, 1, 31) == date(2027, 1, 31)
    assert payday_in(2027, 2, 29) == date(2027, 2, 28)


def test_payday_31_that_same_month():
    assert period_bounds(2027, 1, 31, "start") == (date(2027, 1, 31), date(2027, 2, 27))
    assert period_bounds(2027, 2, 31, "start") == (date(2027, 2, 28), date(2027, 3, 30))
    assert period_bounds(2028, 2, 31, "start") == (date(2028, 2, 29), date(2028, 3, 30))
    assert period_bounds(2027, 4, 31, "start") == (date(2027, 4, 30), date(2027, 5, 30))
    assert period_for_date(date(2027, 2, 27), 31, "start") == (2027, 1)
    assert period_for_date(date(2027, 2, 28), 31, "start") == (2027, 2)


def test_payday_30_the_month_before():
    # pay for March arrives on "the 30th" of February = 28 Feb (29 Feb in a leap year)
    assert period_bounds(2027, 3, 30, "end") == (date(2027, 2, 28), date(2027, 3, 29))
    assert period_bounds(2028, 3, 30, "end") == (date(2028, 2, 29), date(2028, 3, 29))
    assert period_bounds(2026, 12, 30, "end") == (date(2026, 11, 30), date(2026, 12, 29))
    assert period_bounds(2027, 1, 30, "end") == (date(2026, 12, 30), date(2027, 1, 29))


@pytest.mark.parametrize("naming", ["start", "end"])
@pytest.mark.parametrize("p", range(1, 32))
def test_every_payday_tiles_2025_to_2029(p, naming):
    """Every day is in exactly one period, periods are contiguous, and both functions agree."""
    y, m = 2025, 1
    d = period_bounds(y, m, p, naming)[0]
    for _ in range(60):
        start, end = period_bounds(y, m, p, naming)
        assert start == d and start <= end
        assert period_for_date(start, p, naming) == (y, m) == period_for_date(end, p, naming)
        d = date.fromordinal(end.toordinal() + 1)
        y, m = shift_period(y, m, 1)


@pytest.mark.parametrize("p", range(1, 32))
def test_the_month_before_is_that_same_month_shifted(p):
    for y, m in ((2026, 1), (2026, 3), (2026, 12), (2028, 3)):
        assert period_bounds(y, m, p, "end") == period_bounds(*shift_period(y, m, -1), p, "start")


# --- the 20th rule ------------------------------------------------------------------------------------

def test_naming_allowed():
    assert naming_allowed(5, "start") and naming_allowed(1, "start")
    assert naming_allowed(20, "end") and naming_allowed(31, "end")
    assert not naming_allowed(19, "end") and not naming_allowed(1, "end")


def test_settings_form_enforces_the_20th(client, conn, uid):
    r = _post(client, "/profile/start-day", payday="15", period_naming="end")
    assert r.status_code == 422 and "Pay from the month before must arrive on the 20th or later." in r.text
    assert _rule(conn, uid) == PeriodRule(28, "end")                          # unchanged
    assert _post(client, "/profile/start-day", payday="20", period_naming="end").status_code == 303
    assert _rule(conn, uid) == PeriodRule(20, "end")
    assert _post(client, "/profile/start-day", payday="31", period_naming="end").status_code == 303
    assert _rule(conn, uid) == PeriodRule(31, "end")
    # older Savings still sees a valid start day (capped at 28)
    assert conn.execute("SELECT period_start_day FROM users WHERE id = ?", (uid,)).fetchone()[0] == 28


def test_older_settings_keep_working(client, conn, uid):
    """Day 10 of the month before was allowed before 1.5.0: it stays, until the user changes it."""
    conn.execute("UPDATE users SET payday = 10, period_naming = 'end' WHERE id = ?", (uid,))
    conn.commit()
    assert _rule(conn, uid).bounds(2026, 11) == (date(2026, 10, 10), date(2026, 11, 9))
    assert _post(client, "/profile/start-day", payday="10", period_naming="end").status_code == 303
    assert _post(client, "/profile/start-day", payday="11", period_naming="end").status_code == 422
    assert _post(client, "/profile/start-day", payday="10", period_naming="start").status_code == 303
    assert _rule(conn, uid) == PeriodRule(10, "start")


def test_settings_page_offers_the_sentence(client):
    page = client.get("/settings").text
    assert "My pay for a month arrives on" in page
    assert '<option value="start">that same month</option>' in page
    assert '<option value="end" selected>the month before</option>' in page
    assert "So “" in page


def test_preview_says_calendar_months_for_day_1(client, conn, uid, monkeypatch):
    monkeypatch.setattr("app.config.today", lambda: date(2026, 11, 14))
    _post(client, "/profile/start-day", payday="1", period_naming="start")
    assert "So “November 2026” = 1 Nov – 30 Nov 2026. (calendar months)" in client.get("/settings").text


# --- migration 018 and the bridge to older versions -----------------------------------------------------

def test_migration_018_keeps_everyone_where_they_were(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.migrate(conn, _migrations_upto(tmp_path, 17))
    ids = {name: make_user(conn, name) for name in ("one", "ten", "twentyeight", "fivestart")}
    conn.executemany("UPDATE users SET period_start_day = ?, period_naming = ? WHERE id = ?",
                     [(1, "end", ids["one"]), (10, "end", ids["ten"]), (28, "end", ids["twentyeight"]),
                      (5, "start", ids["fivestart"])])
    conn.commit()
    old = {n: PeriodRule.lenient(*conn.execute("SELECT period_start_day, period_naming FROM users WHERE id = ?",
                                               (i,)).fetchone()) for n, i in ids.items()}
    assert db.migrate(conn) == [18]
    for name, uid in ids.items():
        new = _rule(conn, uid)
        for y, m in ((2026, 1), (2026, 11), (2026, 12), (2028, 2)):
            if name == "one":       # 1.4.0 treated day 1 as calendar months whatever the naming
                assert new.bounds(y, m) == (date(y, m, 1), payday_in(y, m, 31))
            else:
                assert new.bounds(y, m) == period_bounds(y, m, old[name].payday, old[name].naming)
    assert _rule(conn, ids["one"]) == PeriodRule(1, "start")
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_older_savings_writing_period_start_day_is_followed(conn, uid):
    conn.execute("UPDATE users SET period_start_day = 15 WHERE id = ?", (uid,))
    assert _rule(conn, uid) == PeriodRule(15, "end")
    conn.execute("UPDATE users SET period_start_day = 1 WHERE id = ?", (uid,))
    assert _rule(conn, uid) == PeriodRule(1, "start")          # day 1 meant calendar months there
    conn.execute("UPDATE users SET period_start_day = 28 WHERE id = ?", (uid,))
    assert _rule(conn, uid) == PeriodRule(28, "end")           # leaving day 1 -> the default again


def test_new_users_get_the_default(conn):
    uid = make_user(conn, "newbie")
    assert _rule(conn, uid) == PeriodRule(28, "end")
