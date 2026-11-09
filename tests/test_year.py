"""Year view, checked by hand. S = 1 (calendar months), today = 2026-06-15.

Periods Jul..Dec 2026 haven't started -> blank (None).
Expenses: Jan Food 100.00 | Mar Food 50.00, Fun 30.00 | Jun Fun 20.00
Periods with data: Jan, Mar, Jun -> 3 (Feb, Apr, May are 0 but don't count for averages)

  Food:  total 150.00, avg 150/3 = 50.00
  Fun:   total  50.00, avg 50/3 = 16.666… -> 16.67
  Spent: total 200.00, avg 200/3 = 66.666… -> 66.67
Regular income 1000.00 from 2025-12-01 -> 1000.00 in each of Jan..Jun
  total 6000.00 ; avg over data periods (1000*3)/3 = 1000.00
Extra income: Feb 300.00 (Feb has no expenses) -> total 300.00, avg over data periods 0/3 = 0.00
Total income total 6300.00 ; left over total 6300 - 200 = 6100.00
  left over avg = (900 + 920 + 980)/3 = 933.33
"""
from datetime import date

import pytest

from app import summary


@pytest.fixture
def year_conn(conn, uid):
    conn.execute("UPDATE users SET period_start_day = 1 WHERE id = ?", (uid,))
    conn.execute("DELETE FROM categories WHERE user_id = ?", (uid,))
    conn.executemany("INSERT INTO categories (user_id, name, sort_order) VALUES (?, ?, ?)",
                     [(uid, "Food", 1), (uid, "Fun", 2), (uid, "Unused", 3)])
    cid = {r["name"]: r["id"] for r in conn.execute("SELECT id, name FROM categories")}
    conn.executemany("INSERT INTO expenses (date, category_id, amount_cents) VALUES (?, ?, ?)",
                     [("2026-01-10", cid["Food"], 10000),
                      ("2026-03-05", cid["Food"], 5000),
                      ("2026-03-06", cid["Fun"], 3000),
                      ("2026-06-01", cid["Fun"], 2000)])
    conn.execute("INSERT INTO regular_income (user_id, amount_cents, effective_from) VALUES (?, 100000, '2025-12-01')", (uid,))
    conn.execute("INSERT INTO extra_income (user_id, date, amount_cents) VALUES (?, '2026-02-14', 30000)", (uid,))
    conn.commit()
    return conn


def test_year_rows_and_averages(year_conn, uid):
    y = summary.year_summary(year_conn, uid, 2026, date(2026, 6, 15))
    assert y["n_data"] == 3
    rows = {r["label"]: r for r in y["categories"] + y["totals"]}

    assert rows["Food"]["cells"] == [10000, 0, 5000, 0, 0, 0] + [None] * 6
    assert (rows["Food"]["total"], rows["Food"]["avg"]) == (15000, 5000)
    assert (rows["Fun"]["total"], rows["Fun"]["avg"]) == (5000, 1667)
    assert (rows["Unused"]["total"], rows["Unused"]["avg"]) == (0, 0)
    assert (rows["Total spent"]["total"], rows["Total spent"]["avg"]) == (20000, 6667)
    assert (rows["Regular income"]["total"], rows["Regular income"]["avg"]) == (600000, 100000)
    assert (rows["Extra income"]["total"], rows["Extra income"]["avg"]) == (30000, 0)
    assert rows["Total income"]["total"] == 630000
    assert (rows["Left over"]["total"], rows["Left over"]["avg"]) == (610000, 93333)
    assert [p["future"] for p in y["periods"]] == [False] * 6 + [True] * 6


def test_year_without_data_has_no_average(conn, uid):
    y = summary.year_summary(conn, uid, 2030, date(2030, 12, 31))
    assert y["n_data"] == 0
    assert all(r["avg"] is None for r in y["categories"] + y["totals"])


def test_year_with_s28_starts_in_previous_december(year_conn, uid):
    year_conn.execute("UPDATE users SET period_start_day = 28 WHERE id = ?", (uid,))
    food_id = year_conn.execute("SELECT id FROM categories WHERE user_id = ? AND name = 'Food'", (uid,)).fetchone()[0]
    year_conn.execute("INSERT INTO expenses (date, category_id, amount_cents) VALUES ('2025-12-28', ?, 700)", (food_id,))
    y = summary.year_summary(year_conn, uid, 2026, date(2026, 6, 15))
    assert y["range"] == "28 Dec 2025 – 27 Dec 2026"
    food = next(r for r in y["categories"] if r["label"] == "Food")
    assert food["cells"][0] == 10700   # 28 Dec 2025 + 10 Jan 2026 both in "January 2026"


def test_round_div_half_up():
    assert summary.round_div(5, 2) == 3
    assert summary.round_div(-5, 2) == -3
    assert summary.round_div(5000, 3) == 1667


def test_year_page_renders(client, year_conn):
    page = client.get("/year?year=2026").text
    assert "Spent vs total income" in page
    assert "chart.umd.min.js" in page
    assert "€16.67" in page


def test_chart_js_is_served_locally(client):
    r = client.get("/static/vendor/chart.umd.min.js")
    assert r.status_code == 200
    assert "Chart" in r.text[:2000]


def test_year_chart_splits_future_spending_and_extra_income(year_conn, uid, monkeypatch):
    monkeypatch.setattr("app.config.today", lambda: date(2026, 6, 15))
    year_conn.execute("INSERT INTO expenses (date, category_id, amount_cents) "
                      "SELECT '2026-06-20', id, 1500 FROM categories WHERE name = 'Food'")
    year_conn.commit()
    ch = summary.year_summary(year_conn, uid, 2026, date(2026, 6, 15))["chart"]
    assert ch["spent_past"] == [100.0, 0, 80.0, 0, 0, 20.0] + [None] * 6
    assert ch["spent_future"] == [0, 0, 0, 0, 0, 15.0] + [None] * 6
    assert ch["regular"] == [1000.0] * 6 + [None] * 6
    assert ch["extra"] == [0, 300.0, 0, 0, 0, 0] + [None] * 6
