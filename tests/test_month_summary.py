"""Month summary on a small fixture, numbers checked by hand.

Start day S = 28, so "November 2026" = 2026-10-28 .. 2026-11-27.

Categories (budget):  Food 300.00 | Fun 100.00 | Misc 0.00 | Old 50.00 (archived) | Gone 20.00 (archived, unused)
  Food's budget history: 250.00 from 2026-01-01, 300.00 from 2026-11-27, 999.00 from 2026-11-28.
  November ends 2026-11-27, so it uses 300.00; October uses 250.00; December uses 999.00.

Expenses                       in Nov?   my cost
  2026-10-27 Food 50.00          no      (previous period)
  2026-10-28 Food  60.00         yes      60.00
  2026-11-27 Food 200.00         yes     200.00
  2026-11-28 Food 30.00          no      (next period)
  2026-11-10 Fun  120.00         yes     120.00
  2026-11-11 Old   10.00         yes      10.00

  Food: 60 + 200 = 260.00, 2 purchases, 260/300 = 86.67 %  -> amber, left 40.00
  Fun:  120.00, 1 purchase, 120/100 = 120 %                  -> red,   left -20.00
  Misc: 0.00, budget 0                                        -> no %
  Old:  10.00, 10/50 = 20 % (archived but used, so shown)
  Gone: archived and unused -> hidden
  Spent = 260 + 120 + 10 = 390.00
  Budget = 300 + 100 + 0 + 50 = 450.00 ; used = 390/450 = 86.67 % -> amber

Regular income rows: 2000.00 from 2026-01-01, 2200.00 from 2026-11-15, 2500.00 from 2026-11-28
  Latest effective_from <= 2026-11-27 is 2026-11-15 -> 2200.00
  (October 2026 period ends 2026-10-27 -> 2000.00)
Extra income: 2026-11-01 150.00 (in), 2026-10-27 99.00 (out)
  Total income = 2200 + 150 = 2350.00 ; left over = 2350 - 390 = 1960.00
"""
import pytest

from .conftest import add_budget

from app import summary


@pytest.fixture
def fixture_conn(conn, uid):
    conn.execute("DELETE FROM categories WHERE user_id = ?", (uid,))
    cats = [("Food", 1, 0), ("Fun", 2, 0), ("Misc", 3, 0), ("Old", 4, 1), ("Gone", 5, 1)]
    conn.executemany("INSERT INTO categories (user_id, name, sort_order, archived) VALUES (?, ?, ?, ?)",
                     [(uid, *c) for c in cats])
    cid = {r["name"]: r["id"] for r in conn.execute("SELECT id, name FROM categories")}
    for c, cents, day in ((cid["Food"], 25000, "2026-01-01"),   # replaced by the next row for November
                          (cid["Food"], 30000, "2026-11-27"),   # last day of November's period -> applies
                          (cid["Food"], 99900, "2026-11-28"),   # first day of December's period -> not yet
                          (cid["Fun"], 10000, "2026-01-01"),
                          (cid["Old"], 5000, "2026-01-01"),
                          (cid["Gone"], 2000, "2026-01-01")):
        add_budget(conn, c, cents, day)
    conn.executemany(
        "INSERT INTO expenses (date, description, category_id, amount_cents) VALUES (?, '', ?, ?)",
        [("2026-10-27", cid["Food"], 5000),
         ("2026-10-28", cid["Food"], 6000),
         ("2026-11-27", cid["Food"], 20000),
         ("2026-11-28", cid["Food"], 3000),
         ("2026-11-10", cid["Fun"], 12000),
         ("2026-11-11", cid["Old"], 1000)])
    conn.executemany("INSERT INTO regular_income (user_id, amount_cents, effective_from) VALUES (?, ?, ?)",
                     [(uid, 200000, "2026-01-01"), (uid, 220000, "2026-11-15"), (uid, 250000, "2026-11-28")])
    conn.executemany("INSERT INTO extra_income (user_id, date, description, amount_cents) VALUES (?, ?, '', ?)",
                     [(uid, "2026-11-01", 15000), (uid, "2026-10-27", 9900)])
    conn.execute("UPDATE users SET period_start_day = 28 WHERE id = ?", (uid,))
    conn.commit()
    return conn


def test_month_totals(fixture_conn, uid):
    s = summary.month_summary(fixture_conn, uid, 2026, 11)
    assert (s["start"].isoformat(), s["end"].isoformat()) == ("2026-10-28", "2026-11-27")
    assert s["range"] == "28 Oct – 27 Nov 2026"
    assert s["regular"] == 220000
    assert s["extra"] == 15000
    assert s["income"] == 235000
    assert s["spent"] == 39000
    assert s["left"] == 196000
    assert s["budget"] == 45000
    assert s["budget_pct"] == pytest.approx(86.666, abs=0.01)
    assert s["budget_status"] == "amber"
    assert s["n_expenses"] == 4


def test_month_categories(fixture_conn, uid):
    s = summary.month_summary(fixture_conn, uid, 2026, 11)
    by = {c["name"]: c for c in s["categories"]}
    assert list(by) == ["Food", "Fun", "Misc", "Old"]   # Gone is hidden
    assert (by["Food"]["spent"], by["Food"]["n"], by["Food"]["left"], by["Food"]["status"]) == (26000, 2, 4000, "amber")
    assert (by["Fun"]["spent"], by["Fun"]["left"], by["Fun"]["status"]) == (12000, -2000, "red")
    assert by["Fun"]["pct"] == pytest.approx(120)
    assert (by["Misc"]["spent"], by["Misc"]["pct"], by["Misc"]["status"]) == (0, None, "")
    assert (by["Old"]["spent"], by["Old"]["pct"], by["Old"]["archived"]) == (1000, 20, True)


def test_budget_change_does_not_rewrite_other_months(fixture_conn, uid):
    def food(y, m):
        s = summary.month_summary(fixture_conn, uid, y, m)
        return next(c for c in s["categories"] if c["name"] == "Food")
    assert food(2026, 10)["budget"] == 25000
    assert food(2026, 11)["budget"] == 30000
    assert food(2026, 12)["budget"] == 99900
    assert summary.month_summary(fixture_conn, uid, 2025, 12)["categories"][0]["budget"] == 0  # before any row
    # October: Food 50.00 spent on 2026-10-27 against 250.00 -> 20 %
    assert food(2026, 10)["spent"] == 5000 and food(2026, 10)["pct"] == 20


def test_income_change_does_not_rewrite_earlier_month(fixture_conn, uid):
    assert summary.month_summary(fixture_conn, uid, 2026, 10)["regular"] == 200000
    assert summary.month_summary(fixture_conn, uid, 2026, 12)["regular"] == 250000


def test_changing_start_day_moves_entries(fixture_conn, uid):
    fixture_conn.execute("UPDATE users SET period_start_day = 1 WHERE id = ?", (uid,))
    s = summary.month_summary(fixture_conn, uid, 2026, 11)
    # Calendar November: Food 200.00 (27th) + 30.00 (28th), Fun 120, Old 10 = 360.00
    assert s["spent"] == 36000
    assert s["regular"] == 250000   # Nov 30 >= 2026-11-28


@pytest.mark.parametrize("spent, budget, status", [
    (8499, 10000, ""), (8500, 10000, "amber"), (10000, 10000, "amber"),
    (10001, 10000, "red"), (500, 0, ""),
])
def test_budget_status_thresholds(spent, budget, status):
    assert summary.budget_status(spent, budget) == status


def test_month_page_renders(client, fixture_conn):
    page = client.get("/month?period=2026-11").text
    assert "28 Oct – 27 Nov 2026" in page
    assert "€1,960.00" in page and "€2,350.00" in page and "€390.00" in page
    assert 'class="red"' in page and 'class="amber"' in page
    assert "Gone" not in page


def test_left_over_negative_is_red(client, fixture_conn):
    fixture_conn.execute("DELETE FROM regular_income")
    fixture_conn.commit()
    page = client.get("/month?period=2026-11").text
    # income 150.00 - spent 390.00 = -240.00
    assert 'class="value neg">-€240.00' in page
