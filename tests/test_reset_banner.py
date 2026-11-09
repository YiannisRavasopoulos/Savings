"""The purple "period resets soon" banner: last 3 days before the user's own period resets.
Alice's own periods start on the 28th."""
from datetime import date

import pytest

from app import summary


def _today(monkeypatch, d):
    monkeypatch.setattr("app.config.today", lambda: d)


@pytest.mark.parametrize("today, days", [(date(2026, 11, 24), None), (date(2026, 11, 25), 3),
                                         (date(2026, 11, 26), 2), (date(2026, 11, 27), 1),
                                         (date(2026, 11, 28), None)])
def test_window(conn, uid, today, days):
    r = summary.reset_notice(conn, uid, today)
    if days is None:
        assert r is None
    else:
        assert r == {"resets": date(2026, 11, 28), "days": days, "key": "2026-11-28"}


def test_banner_on_home_and_categories(client, monkeypatch):
    _today(monkeypatch, date(2026, 11, 26))
    for path in ("/", "/categories"):
        page = client.get(path).text
        assert 'class="reset-banner"' in page and 'data-key="2026-11-28"' in page
        assert "Your budget period resets on 28 Nov 2026</strong>\n    (in 2 days)" in page
    _today(monkeypatch, date(2026, 11, 27))
    assert "(tomorrow)" in client.get("/").text
    _today(monkeypatch, date(2026, 11, 20))
    assert 'class="reset-banner"' not in client.get("/").text


def test_shared_categories_dont_trigger_it(client, conn, uid, monkeypatch):
    _today(monkeypatch, date(2026, 11, 4))
    client.post("/categories", data={"name": "Home", "budget": "", "budget_from": "", "joint": "1"})
    assert summary.reset_notice(conn, uid, date(2026, 11, 29)) is None    # own period just reset
