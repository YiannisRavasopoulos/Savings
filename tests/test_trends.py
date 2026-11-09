"""Trends, checked by hand. S = 1 (calendar months), today = 2026-06-15, so June is "so far".

Income 1000.00/month from 2025-01-01. Budget: Food 120.00 from 2025-01-01. Fun has no budget.
Expenses (all on the 5th unless noted):
          Jan  Feb  Mar  Apr  May  | Jun (so far)
  Food    100  100  100  100  200  | 50 on the 3rd, 30 on the 10th
  Fun      50   50   50   50    0  | 20 on the 5th
  total   150  150  150  150  200  | 100

Savings rate: Jan–Apr 85 %, May 80 %, Jun so far 90 %. Average of finished periods = (4·85 + 80)/5 = 84 %.
Biggest changes (May vs average of Feb, Mar, Apr): Food 200 vs 100 = +100.00 (+100 %),
  Fun 0 vs 50 = −50.00 (−100 %). Ordered by size: Food, Fun.
Pace: June has 30 days, today is day 15. June so far: 100.00.
  Usual by day 15 = average of Jan..May totals by day 15 = (150·4 + 200)/5 = 160.00 -> −60.00 (−37.5 %).
Track record (Jan–May): Food within 120 in Jan–Apr, over in May -> 4 of 5. Fun: no budget -> not listed.
"""
import json
import re
from datetime import date

import pytest

from app import summary

from .conftest import add_budget

TODAY = date(2026, 6, 15)


@pytest.fixture
def tconn(conn, uid):
    conn.execute("UPDATE users SET period_start_day = 1 WHERE id = ?", (uid,))
    conn.execute("DELETE FROM categories WHERE user_id = ?", (uid,))
    conn.executemany("INSERT INTO categories (user_id, name, sort_order) VALUES (?, ?, ?)",
                     [(uid, "Food", 1), (uid, "Fun", 2), (uid, "Spare", 3)])
    cid = {r["name"]: r["id"] for r in conn.execute("SELECT id, name FROM categories WHERE user_id = ?", (uid,))}
    rows = []
    for m, food, fun in ((1, 100, 50), (2, 100, 50), (3, 100, 50), (4, 100, 50), (5, 200, 0)):
        rows.append((f"2026-{m:02d}-05", cid["Food"], food * 100))
        if fun:
            rows.append((f"2026-{m:02d}-05", cid["Fun"], fun * 100))
    rows += [("2026-06-03", cid["Food"], 5000), ("2026-06-10", cid["Food"], 3000), ("2026-06-05", cid["Fun"], 2000)]
    conn.executemany("INSERT INTO expenses (date, category_id, amount_cents) VALUES (?, ?, ?)", rows)
    conn.execute("INSERT INTO regular_income (user_id, amount_cents, effective_from) VALUES (?, 100000, '2025-01-01')", (uid,))
    add_budget(conn, cid["Food"], 12000, "2025-01-01")
    conn.commit()
    return conn


def test_starts_at_first_expense_and_ends_with_current(tconn, uid):
    t = summary.trends(tconn, uid, TODAY, 12)
    assert t["labels"] == ["Jan 26", "Feb 26", "Mar 26", "Apr 26", "May 26", "Jun 26"]
    assert t["current_label"] == "Jun 26" and t["n_complete"] == 5
    t6 = summary.trends(tconn, uid, TODAY, 6)
    assert t6["labels"] == t["labels"]
    assert summary.trends(tconn, uid, date(2026, 8, 1), 6)["labels"][0] == "Mar 26"   # range cuts the start


def test_savings_rate(tconn, uid):
    s = summary.trends(tconn, uid, TODAY)["savings"]
    assert s["values"] == [85.0, 85.0, 85.0, 85.0, 80.0, 90.0]
    assert (s["avg"], s["current"], s["enough"]) == (84.0, 90.0, True)


def test_category_series(tconn, uid):
    series = summary.trends(tconn, uid, TODAY)["categories"]["series"]
    assert [(s["name"], s["values"], s["visible"]) for s in series] == [
        ("Food", [10000, 10000, 10000, 10000, 20000, 8000], True),
        ("Fun", [5000, 5000, 5000, 5000, 0, 2000], True),
    ]   # "Spare" never used -> not listed


def test_biggest_changes(tconn, uid):
    t = summary.trends(tconn, uid, TODAY)
    assert t["changes_period"] == "May 26" and t["changes_base"] == ["Feb 26", "Mar 26", "Apr 26"]
    assert [(c["name"], c["spent"], c["base"], c["diff"], c["pct"]) for c in t["changes"]] == [
        ("Food", 20000, 10000, 10000, 100.0), ("Fun", 0, 5000, -5000, -100.0)]


def test_small_changes_are_ignored(tconn, uid):
    tconn.execute("UPDATE expenses SET amount_cents = 10900 WHERE date = '2026-05-05'")   # May Food 109 vs 100: +9
    tconn.execute("INSERT INTO expenses (date, category_id, amount_cents) "
                  "SELECT '2026-05-05', id, 5000 FROM categories WHERE name = 'Fun'")  # Fun back to 50
    tconn.commit()
    assert summary.trends(tconn, uid, TODAY)["changes"] == []


def test_new_category_counts_as_change(tconn, uid):
    tconn.execute("INSERT INTO expenses (date, category_id, amount_cents) "
                  "SELECT '2026-05-20', id, 4000 FROM categories WHERE name = 'Spare'")
    tconn.commit()
    spare = next(c for c in summary.trends(tconn, uid, TODAY)["changes"] if c["name"] == "Spare")
    assert (spare["base"], spare["diff"], spare["pct"]) == (0, 4000, None)


def test_spending_pace(tconn, uid):
    p = summary.trends(tconn, uid, TODAY)["pace"]
    assert (p["day"], p["days"], p["n_history"]) == (15, 30, 5)
    assert (p["spent_now"], p["usual_now"], p["diff"], p["pct"]) == (10000, 16000, -6000, -37.5)
    assert p["current"][:15] == [0, 0, 50.0, 50.0, 70.0, 70.0, 70.0, 70.0, 70.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0]
    assert p["current"][15:] == [None] * 15                 # the future isn't drawn
    assert p["typical"][3] == 0 and p["typical"][4] == 160.0 and p["typical"][29] == 160.0


def test_budget_track_record_is_on_the_budget_page_not_trends(tconn, uid, client, monkeypatch):
    monkeypatch.setattr("app.config.today", lambda: TODAY)
    r = summary.budget_record(tconn, uid, TODAY)
    assert [(x["name"], x["within"], x["of"]) for x in r["record"]] == [("Food", 4, 5)]
    assert r["n_complete"] == 5
    assert "record" not in summary.trends(tconn, uid, TODAY)
    assert "Budget track record" not in client.get("/trends").text
    assert "Budget track record" in client.get("/budget").text and "within 4 of 5" in client.get("/budget").text


def test_no_expenses_is_empty(conn, uid):
    assert summary.trends(conn, uid, TODAY)["empty"] is True


def test_only_current_period_says_not_enough(conn, uid):
    from .conftest import add_budget, category_id
    conn.execute("INSERT INTO expenses (date, category_id, amount_cents) VALUES ('2026-06-02', ?, 500)",
                 (category_id(conn, "Groceries"),))
    conn.execute("UPDATE users SET period_start_day = 1 WHERE id = ?", (uid,))
    conn.commit()
    t = summary.trends(conn, uid, TODAY)
    assert not t["empty"] and t["labels"] == ["Jun 26"]
    assert not t["savings"]["enough"] and not t["categories"]["enough"]
    assert not t["changes_enough"] and not t["pace"]["enough"]
    assert not summary.budget_record(conn, uid, TODAY)["enough"]


# --- page ---------------------------------------------------------------------------

@pytest.fixture
def june(monkeypatch):
    monkeypatch.setattr("app.config.today", lambda: TODAY)


def test_trends_page(client, tconn, june):
    page = client.get("/trends").text
    assert "Savings rate" in page and "84.0%" in page and "90.0%" in page
    assert "+€100.00 (+100%)" in page and "-€50.00 (-100%)" in page
    assert "May 26 compared with the average of Feb 26, Mar 26, Apr 26" in page
    assert "Day 15 of 30: you've spent <strong>€100.00</strong>" in page and "(-38%)" in page
    assert "within 4 of 5" not in page            # the track record lives on the Budget page now
    data = json.loads(re.search(r'id="trends-data">(.*?)</script>', page, re.S).group(1))
    assert data["savings"] == [85.0, 85.0, 85.0, 85.0, 80.0, 90.0] and data["savings_avg"] == 84.0
    assert [c["name"] for c in data["categories"]] == ["Food", "Fun"]
    assert len(data["pace"]["labels"]) == 30
    assert 'href="/trends?n=12" class="active"' in page


def test_trends_range_picker(client, tconn, june):
    assert 'href="/trends?n=6" class="active"' in client.get("/trends?n=6").text
    assert 'href="/trends?n=12" class="active"' in client.get("/trends?n=7").text     # unknown -> default


def test_trends_page_empty(client):
    page = client.get("/trends").text
    assert "Trends appear once you've logged some expenses." in page and "chart.umd" not in page


def test_trends_is_per_user(app, client, tconn, june, conn):
    from .conftest import browser, login, make_user
    make_user(conn, "bob")
    page = login(browser(app), "bob").get("/trends").text
    assert "Trends appear once" in page and "Food" not in page
