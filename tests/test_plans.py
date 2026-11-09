"""Savings forecast and planned purchases, checked by hand.

S = 1 (calendar months), today = 2026-06-15 (day 15 of June's 30). Income 2,000.00/month.
Typical spending (all on the 5th, category Food): Jan 1000, Feb 1200, Mar 1100, Apr 1300, May 1000
  + a one-off 2,000.00 in March (left out of "typical").
  sorted 1000, 1000, 1100, 1200, 1300 -> median 1100, 75th pct 1200, 25th pct 1000
  spread (1200-1000)/1100 = 0.18, 5 periods -> confidence "medium"
  left over per period 1000, 800, 900, 700, 1000 -> usually 800–1000
June so far: 600.00 spent. Usual by day 15 = median of the history totals = 1100.
  typical rest of June = max(0, 1100-1100) = 0  -> June left 2000-600-0   = 1400
  cautious rest        = max(0, 1200-1100) = 100 -> June left 2000-600-100 = 1300
Later periods: typical 2000-1100 = 900, cautious 2000-1200 = 800.
  savings typical:  Jun 1400, Jul 2300, Aug 3200, Sep 4100, Oct 5000 ...
  savings cautious: Jun 1300, Jul 2100, Aug 2900, Sep 3700, Oct 4500 ...
Cushion = 10 % of 2000 = 200.

Plan A (priority 1): Laptop 2,500.00, Shopping, nothing set aside -> needs 2,700 saved.
  cautious: Aug (2900) -> "Best time: August"; still saved afterwards 2900-2500 = 400.
  typical: also Aug -> no earlier "could already fit".
  Shopping budget 300, usually 0 -> over by 0 + 2500 - 300 = 2,200.00.
Plan B (priority 2): Bike 1,000.00, 300.00 set aside -> 700 from savings, needs 900 available
  in every period from then on (after A's 2500 from August):
  cautious available: Jun 1300, Jul 2100, Aug 400, Sep 1200, Oct 2000 -> Aug fails -> September.
  still saved afterwards: 1200 - 700 = 500.
"""
import re
from datetime import date

import pytest

from app import forecast

from .conftest import add_budget, browser, login, make_user

TODAY = date(2026, 6, 15)


@pytest.fixture
def fconn(conn, uid, monkeypatch):
    monkeypatch.setattr("app.config.today", lambda: TODAY)
    conn.execute("UPDATE users SET period_start_day = 1 WHERE id = ?", (uid,))
    conn.execute("DELETE FROM categories WHERE user_id = ?", (uid,))
    conn.executemany("INSERT INTO categories (user_id, name, sort_order) VALUES (?, ?, ?)",
                     [(uid, "Food", 1), (uid, "Shopping", 2)])
    cid = {r["name"]: r["id"] for r in conn.execute("SELECT id, name FROM categories WHERE user_id = ?", (uid,))}
    rows = [(f"2026-{m:02d}-05", cid["Food"], amount * 100, 0)
            for m, amount in ((1, 1000), (2, 1200), (3, 1100), (4, 1300), (5, 1000))]
    rows += [("2026-03-20", cid["Shopping"], 200000, 1), ("2026-06-03", cid["Food"], 60000, 0)]
    conn.executemany("INSERT INTO expenses (date, category_id, amount_cents, one_off) VALUES (?, ?, ?, ?)", rows)
    conn.execute("INSERT INTO regular_income (user_id, amount_cents, effective_from) VALUES (?, 200000, '2025-01-01')", (uid,))
    add_budget(conn, cid["Shopping"], 30000, "2025-01-01")
    conn.commit()
    return conn


def _cid(conn, uid, name):
    return conn.execute("SELECT id FROM categories WHERE user_id = ? AND name = ?", (uid, name)).fetchone()[0]


def _plan(conn, uid, name, amount, saved=0, category=None, order=1):
    conn.execute("INSERT INTO planned_purchases (user_id, name, amount_cents, saved_cents, category_id, sort_order) "
                 "VALUES (?, ?, ?, ?, ?, ?)", (uid, name, amount, saved, category, order))
    conn.commit()


def test_percentile():
    assert forecast.percentile([1000, 1000, 1100, 1200, 1300], 0.5) == 1100
    assert forecast.percentile([1000, 1000, 1100, 1200, 1300], 0.75) == 1200
    assert forecast.percentile([1, 2, 3, 4], 0.5) == 2.5
    assert forecast.percentile([7], 0.9) == 7


def test_forecast_numbers(fconn, uid):
    fc = forecast.forecast(fconn, uid, TODAY)
    assert fc["ready"] and fc["n_history"] == 5
    assert (fc["typical"], fc["cautious"], fc["confidence"]) == (110000, 120000, "medium")
    assert (fc["left_low"], fc["left_high"], fc["cushion"]) == (80000, 100000, 20000)
    assert fc["day"] == 15 and fc["spent_so_far"] == 60000
    p = fc["periods"]
    assert len(p) == 12 and p[0]["label"] == "June 2026" and p[11]["label"] == "May 2027"
    assert [x["saved_typical"] for x in p[:5]] == [140000, 230000, 320000, 410000, 500000]
    assert [x["saved_cautious"] for x in p[:5]] == [130000, 210000, 290000, 370000, 450000]


def test_one_offs_are_left_out_of_typical_spending(fconn, uid):
    fconn.execute("UPDATE expenses SET one_off = 0")    # count the 2,000 March repair as normal
    fconn.commit()
    fc = forecast.forecast(fconn, uid, TODAY)
    assert fc["typical"] == 120000                       # Mar becomes 3100 -> 1000,1000,1200,1300,3100


def test_plans_are_placed_in_priority_order(fconn, uid):
    _plan(fconn, uid, "Laptop", 250000, category=_cid(fconn, uid, "Shopping"), order=1)
    _plan(fconn, uid, "Bike", 100000, saved=30000, order=2)
    fc = forecast.forecast(fconn, uid, TODAY)
    plans = fconn.execute("SELECT * FROM planned_purchases ORDER BY sort_order").fetchall()
    a, b = forecast.place_plans(fconn, uid, fc, plans)
    assert a["confident"]["label"] == "August 2026" and a["after"] == 40000 and "likely" not in a
    assert a["category"] == {"budget": 30000, "usual": 0, "over": 220000}
    assert b["confident"]["label"] == "September 2026" and b["after"] == 50000


def test_swapping_priority_changes_the_answer(fconn, uid):
    _plan(fconn, uid, "Laptop", 250000, order=2)
    _plan(fconn, uid, "Bike", 100000, saved=30000, order=1)
    fc = forecast.forecast(fconn, uid, TODAY)
    plans = fconn.execute("SELECT * FROM planned_purchases ORDER BY sort_order").fetchall()
    bike, laptop = forecast.place_plans(fconn, uid, fc, plans)
    # Bike first: June (1300 >= 900). Laptop then needs 2700 with 700 used: Aug 2900-700 = 2200 no,
    # Sep 3700-700 = 3000 yes -> September.
    assert bike["confident"]["label"] == "June 2026"
    assert laptop["confident"]["label"] == "September 2026"


def test_too_expensive_says_how_long(fconn, uid):
    _plan(fconn, uid, "Car", 5000000)                     # 50,000.00
    fc = forecast.forecast(fconn, uid, TODAY)
    (car,) = forecast.place_plans(fconn, uid, fc, fconn.execute("SELECT * FROM planned_purchases").fetchall())
    assert "confident" not in car and "likely" not in car
    # need 50,200; a typical period saves 900 -> ceil(50200/900) = 56
    assert (car["per_period"], car["periods_needed"]) == (90000, 56)


def test_likely_before_confident(fconn, uid):
    # needs 2,300 + 200 = 2,500 -> typical Aug 3200? no: Jul 2300 < 2500, Aug 3200 -> Aug;
    # make it 2,100: needs 2,300 -> typical Jul (2300), cautious Aug (2900; Jul 2100 < 2300)
    _plan(fconn, uid, "TV", 210000)
    fc = forecast.forecast(fconn, uid, TODAY)
    (tv,) = forecast.place_plans(fconn, uid, fc, fconn.execute("SELECT * FROM planned_purchases").fetchall())
    assert tv["confident"]["label"] == "August 2026" and tv["likely"]["label"] == "July 2026"


def test_not_ready_with_little_history(conn, uid, monkeypatch):
    from .conftest import category_id
    monkeypatch.setattr("app.config.today", lambda: TODAY)
    conn.execute("UPDATE users SET period_start_day = 1 WHERE id = ?", (uid,))
    conn.execute("INSERT INTO expenses (date, category_id, amount_cents) VALUES ('2026-05-02', ?, 100)",
                 (category_id(conn, "Groceries"),))
    conn.commit()
    fc = forecast.forecast(conn, uid, TODAY)
    assert not fc["ready"] and fc["n_history"] == 1


# --- pages ------------------------------------------------------------------------------

def _post(c, url, **data):
    return c.post(url, data=data, follow_redirects=False)


def test_plans_page_shows_forecast_and_suggestion(client, fconn, uid):
    _plan(fconn, uid, "Laptop", 250000, category=_cid(fconn, uid, "Shopping"))
    page = client.get("/plans").text
    assert "Projected savings" in page and ">Medium<" in page and "€800.00–€1,000.00" in page
    assert "Best time" in page and "<strong>August 2026</strong>" in page and "€400.00" in page
    assert "Shopping would go over its €300.00 budget by €2,200.00" in page
    assert 'id="forecast-data"' in page


def test_plans_page_without_history(client):
    page = client.get("/plans").text
    assert "Suggestions need at least 3 finished periods" in page and "chart.umd" not in page


def test_add_edit_reorder_delete(client, conn, uid):
    r = _post(client, "/plans", name="  New  phone ", amount="799,90", saved="100", category_id="", notes="")
    assert r.headers["location"] == "/plans?done=added"
    row = conn.execute("SELECT * FROM planned_purchases").fetchone()
    assert (row["name"], row["amount_cents"], row["saved_cents"], row["category_id"]) == ("New phone", 79990, 10000, None)
    _post(client, "/plans", name="Bike", amount="500", saved="", category_id="", notes="")
    pid = row["id"]
    from .conftest import category_id
    shop = category_id(conn, "Shopping")
    assert _post(client, f"/plans/{pid}/edit", name="Phone", amount="850", saved="0",
                 category_id=str(shop), notes="wait for sales").status_code == 303
    row = conn.execute("SELECT * FROM planned_purchases WHERE id = ?", (pid,)).fetchone()
    assert (row["name"], row["amount_cents"], row["category_id"], row["notes"]) == ("Phone", 85000, shop, "wait for sales")
    _post(client, f"/plans/{pid}/move", direction="down")
    assert [r[0] for r in conn.execute("SELECT name FROM planned_purchases ORDER BY sort_order")] == ["Bike", "Phone"]
    assert _post(client, f"/plans/{pid}/delete").headers["location"] == "/plans?done=deleted"
    assert conn.execute("SELECT COUNT(*) FROM planned_purchases WHERE id = ?", (pid,)).fetchone()[0] == 0


@pytest.mark.parametrize("data, field, message", [
    ({"name": "", "amount": "10"}, "name", "What do you want to buy?"),
    ({"name": "X", "amount": ""}, "amount", "Enter an amount."),
    ({"name": "X", "amount": "0"}, "amount", "more than zero"),
    ({"name": "X", "amount": "10", "saved": "20"}, "saved", "more than the price"),
    ({"name": "X", "amount": "10", "category_id": "99999"}, "category_id", "Pick one of your categories"),
])
def test_plan_validation_reopens_dialog(client, conn, data, field, message):
    r = client.post("/plans", data={"saved": "", "category_id": "", "notes": "", **data})
    assert r.status_code == 422 and message in r.text and 'data-reopen="dlg-plan-add"' in r.text
    assert conn.execute("SELECT COUNT(*) FROM planned_purchases").fetchone()[0] == 0


def test_bought_it_opens_prefilled_add_form(client, conn, uid):
    from .conftest import category_id
    shop = category_id(conn, "Shopping")
    _plan(conn, uid, "Headphones", 12950, category=shop)
    pid = conn.execute("SELECT id FROM planned_purchases").fetchone()[0]
    r = _post(client, f"/plans/{pid}/bought")
    assert r.headers["location"].startswith("/add?")
    assert conn.execute("SELECT COUNT(*) FROM planned_purchases").fetchone()[0] == 0
    page = client.get(r.headers["location"]).text
    assert 'value="Headphones"' in page and 'value="129.50"' in page
    assert f'<option value="{shop}" selected>' in page
    assert 'name="one_off" value="1" checked' in page and "Plan removed." in page


def test_one_off_checkbox_saved_and_tagged(client, conn):
    from .conftest import category_id
    cid = category_id(conn, "Groceries")
    form = {"date": "2026-11-04", "description": "Fridge", "category_id": str(cid), "amount": "600",
            "notes": "", "one_off": "1"}
    client.post("/add", data=form)
    eid, one_off = conn.execute("SELECT id, one_off FROM expenses").fetchone()
    assert one_off == 1
    assert "one-off" in client.get("/log?period=2026-11").text
    client.post(f"/expenses/{eid}/edit", data={**form, "one_off": ""})
    assert conn.execute("SELECT one_off FROM expenses").fetchone()[0] == 0


def test_plans_are_private_and_merge_safe(app, client, conn, uid):
    from .conftest import category_id
    shop, groc = category_id(conn, "Shopping"), category_id(conn, "Groceries")
    _plan(conn, uid, "SECRET-PLAN", 1000, category=shop)
    pid = conn.execute("SELECT id FROM planned_purchases").fetchone()[0]
    make_user(conn, "bob")
    bob = login(browser(app), "bob")
    assert "SECRET-PLAN" not in bob.get("/plans").text
    for action, data in (("edit", {"name": "x", "amount": "1"}), ("delete", {}), ("bought", {}), ("move", {"direction": "up"})):
        r = bob.post(f"/plans/{pid}/{action}", data=data)
        assert r.status_code == 404 and "no longer exists" in r.text
    # merging Shopping into Groceries moves the plan's category along
    client.post(f"/categories/{shop}/delete", data={"expected": "0"})
    assert conn.execute("SELECT category_id FROM planned_purchases").fetchone()[0] is None   # deleted: no category
    assert conn.execute("SELECT COUNT(*) FROM planned_purchases").fetchone()[0] == 1


def test_menu_has_plan_a_purchase(client):
    page = client.get("/").text
    sheet = re.search(r'<div class="action-sheet">.*?</div>', page, re.S).group(0)
    assert re.findall(r'href="([^"]+)"', sheet) == ["/add", "/income#add-income", "/plans", "/recurring", "/settings"]
    burger = re.search(r'<div class="burger-panel">.*?</div>', page, re.S).group(0)
    assert re.findall(r'href="([^"]+)"', burger) == ["/add", "/income#add-income", "/plans", "/recurring"]
