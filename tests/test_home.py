"""Home dashboard and navigation. S = 28, today = 2026-11-04 -> period "November 2026"
(2026-10-28 .. 2026-11-27, 31 days; 24 days left counting today).

Income 2000.00 from 2026-01-01. Budgets: Dining out 100.00, Transport 50.00, Date 200.00.
November expenses: Dining out 90.00 (90 %), Transport 60.00 (120 %), Entertainment 30.00 (15 %)
  spent 180.00, left over 1820.00, per day 1820.00 / 24 = 75.833… -> 75.83 (rounded down)
October expense: Dining out 25.00 (2026-10-27, previous period)
"""
import json
import re
from datetime import date

import pytest

from app import summary

from .conftest import add_budget, category_id

TODAY = date(2026, 11, 4)


@pytest.fixture(autouse=True)
def _today(monkeypatch):
    monkeypatch.setattr("app.config.today", lambda: TODAY)   # "future-dated" is relative to today


@pytest.fixture
def dash_conn(conn, uid):
    ids = {n: category_id(conn, n) for n in ("Dining out", "Transport", "Entertainment")}
    for name, cents in (("Dining out", 10000), ("Transport", 5000), ("Entertainment", 20000)):
        add_budget(conn, ids[name], cents, "2026-01-01")
    conn.executemany(
        "INSERT INTO expenses (date, description, category_id, amount_cents) VALUES (?, ?, ?, ?)",
        [("2026-10-27", "Old", ids["Dining out"], 2500),
         ("2026-10-30", "Pizza", ids["Dining out"], 9000),
         ("2026-11-01", "Fuel", ids["Transport"], 6000),
         ("2026-11-03", "Cinema", ids["Entertainment"], 3000)])
    conn.execute("INSERT INTO regular_income (user_id, amount_cents, effective_from) VALUES (?, 200000, '2026-01-01')", (uid,))
    conn.commit()
    return conn


def test_dashboard_numbers(dash_conn, uid):
    d = summary.dashboard(dash_conn, uid, TODAY)
    assert d["label"] == "November 2026"
    assert (d["s"]["spent"], d["s"]["left"]) == (18000, 182000)
    assert (d["days_total"], d["days_left"]) == (31, 24)
    assert d["per_day"] == 7583
    assert [c["name"] for c in d["watch"]] == ["Transport", "Dining out", "Entertainment"]   # 120 %, 90 %, 15 %
    assert d["charts"]["categories"] == {"labels": ["Dining out", "Transport", "Entertainment"], "amounts": [90.0, 60.0, 30.0],
                                         "future": [0.0, 0.0, 0.0]}
    assert [r["description"] for r in d["recent"]] == ["Cinema", "Fuel", "Pizza", "Old"]


def test_dashboard_trend_last_six_periods(dash_conn, uid):
    trend = summary.dashboard(dash_conn, uid, TODAY)["charts"]["trend"]
    assert trend["labels"] == ["Jun", "Jul", "Aug", "Sep", "Oct", "Nov"]
    assert trend["spent_past"] == [0, 0, 0, 0, 25.0, 180.0]
    assert trend["spent_future"] == [0] * 6
    assert trend["regular"] == [2000.0] * 6 and trend["extra"] == [0] * 6


def test_future_dated_expense_is_counted_tagged_and_split_out(client, dash_conn, uid):
    dash_conn.execute("INSERT INTO expenses (date, description, category_id, amount_cents) VALUES "
                      "('2026-11-20', 'Concert', ?, 4000)", (category_id(dash_conn, "Entertainment"),))
    dash_conn.execute("INSERT INTO extra_income (user_id, date, description, amount_cents) "
                      "VALUES (?, '2026-11-02', 'Bonus', 30000)", (uid,))
    dash_conn.commit()
    d = summary.dashboard(dash_conn, uid, TODAY)
    assert d["s"]["spent"] == 22000 and d["s"]["future"] == 4000          # still counted in totals
    assert d["charts"]["categories"] == {"labels": ["Dining out", "Entertainment", "Transport"],
                                         "amounts": [90.0, 70.0, 60.0], "future": [0.0, 40.0, 0.0]}
    trend = d["charts"]["trend"]
    assert (trend["spent_past"][-1], trend["spent_future"][-1]) == (180.0, 40.0)
    assert (trend["regular"][-1], trend["extra"][-1]) == (2000.0, 300.0)
    assert d["recent"][0]["description"] == "Concert" and d["recent"][0]["future"]
    assert not d["recent"][1]["future"]

    home = client.get("/").text
    assert re.search(r"Concert <span class=\"tag tag-future\"[^>]*>future</span>", home)
    assert home.count("tag-future") == 1
    log = client.get("/log?year=2026&month=11").text
    assert re.search(r"Concert <span class=\"tag tag-future\"[^>]*>future</span>", log)
    assert log.count("row-future") == 1


def test_dashboard_trend_marks_year_change(conn, uid):
    labels = summary.dashboard(conn, uid, date(2027, 2, 10))["charts"]["trend"]["labels"]
    assert labels == ["Sep", "Oct", "Nov", "Dec", "Jan 27", "Feb"]


def test_dashboard_overspent_and_last_day(dash_conn, uid):
    dash_conn.execute("DELETE FROM regular_income")
    dash_conn.commit()
    d = summary.dashboard(dash_conn, uid, date(2026, 11, 27))
    assert d["s"]["left"] == -18000 and d["per_day"] == 0 and d["days_left"] == 1


def test_home_page(client, dash_conn, monkeypatch):
    monkeypatch.setattr("app.config.today", lambda: TODAY)
    page = client.get("/").text
    assert "November 2026" in page and "€1,820.00" in page
    assert "€75.83 a day for the 24 days left" in page
    assert 'id="chart-categories"' in page and 'id="chart-trend"' in page
    data = json.loads(re.search(r'id="dashboard-data">(.*?)</script>', page, re.S).group(1))
    assert data["categories"]["amounts"] == [90.0, 60.0, 30.0]
    assert "Cinema" in page and "/expenses/" in page


def test_home_empty_state(client):
    page = client.get("/").text
    assert "No spending yet this period." in page and "Nothing logged yet." in page
    assert 'id="chart-categories"' not in page


def test_main_toolbar_has_home_month_budget_trends_year(client):
    import re
    page = client.get("/log").text
    nav = re.search(r'<nav class="nav desk-only" id="main-nav".*?</nav>', page, re.S).group(0)
    assert re.findall(r'href="([^"]+)"', nav) == ["/", "/month", "/budget", "/trends", "/year"]
    assert 'href="/log?period=' in client.get("/month").text          # Log: from Month...
    assert 'href="/log"' in client.get("/").text                     # ...and from Home


PAGES = ["/", "/month", "/budget", "/year", "/trends", "/add", "/log", "/income", "/settings", "/profile",
         "/categories", "/request", "/plans"]


@pytest.mark.parametrize("path", PAGES)
def test_pc_burger_menu_and_settings_button_on_every_page(client, path):
    import re
    page = client.get(path).text
    burger = re.search(r'<details class="burger desk-only".*?</details>', page, re.S).group(0)
    assert re.findall(r'href="([^"]+)"', burger) == ["/add", "/income#add-income", "/plans", "/recurring"]
    assert ">Add expense<" in burger and "Settings" not in burger
    header = re.search(r'<header class="topbar">.*?</header>', page, re.S).group(0)
    assert header.index('id="burger-menu"') < header.index('class="brand"')       # ☰ top left
    assert re.search(r'class="settings-btn desk-only[^"]*" href="/settings"', header)   # Settings top right
    assert header.rindex("settings-btn") > header.index("whoami")


@pytest.mark.parametrize("path", PAGES)
def test_phone_tab_bar_with_centre_action_button(client, path):
    import re
    page = client.get(path).text
    bar = re.search(r'<nav class="tabbar mobile-only".*?</nav>', page, re.S).group(0)
    tabs = re.findall(r'class="tab[ "][^>]*href="([^"]+)"|class="tab-action"', bar)
    assert tabs == ["/", "/month", "/budget", "", "/trends", "/year", "/settings"]   # three either side of the action button
    sheet = re.search(r'<div class="action-sheet">.*?</div>', bar, re.S).group(0)
    assert re.findall(r'href="([^"]+)"', sheet) == ["/add", "/income#add-income", "/plans", "/recurring", "/settings"]
    assert "speed-dial" not in page and "swipe" not in page


def test_active_tab_is_marked_in_both_navigations(client):
    page = client.get("/trends").text
    assert '<a class="tab active" href="/trends" data-tab="3" aria-current="page">' in page
    assert '<a href="/trends" data-tab="3" class="active" aria-current="page">' in page
    settings = client.get("/settings").text
    assert 'class="settings-btn desk-only active"' in settings
    assert '<a class="tab active" href="/settings" data-tab="5" aria-current="page">' in settings
    budget = client.get("/budget").text
    assert '<a class="tab active" href="/budget" data-tab="2" aria-current="page">' in budget


def test_no_navigation_when_logged_out(app):
    from .conftest import browser
    page = browser(app).get("/login").text
    assert "tabbar" not in page and "burger-menu" not in page and "settings-btn" not in page


def test_settings_page_is_profile_plus_request(client):
    page = client.get("/settings").text
    for section in ("Account", "Regular income", "Categories and budgets", "Budget period",
                    "Appearance", "Logged-in devices", "Your data", "Request from admin"):
        assert f">{section}</h2>" in page, section
    assert 'href="/categories"' in page            # categories: reached from inside Settings
    assert 'action="/request"' in page and 'action="/logout"' in page
    assert page.index('id="request"') > page.index("Your data")


@pytest.mark.parametrize("old, new", [("/profile", "/settings"), ("/request", "/settings#request")])
def test_old_pages_redirect_into_settings(client, old, new):
    assert client.get(old, follow_redirects=False).headers["location"] == new


@pytest.mark.parametrize("path, back", [("/categories", "/settings"), ("/settings", "/"), ("/add", "/"),
                                        ("/income", "/"), ("/log", "/")])
def test_back_links(client, path, back):
    assert f'class="back-link" href="{back}"' in client.get(path).text


def test_no_back_link_on_main_tabs(client):
    for path in ("/", "/month", "/budget", "/trends", "/year"):
        assert 'class="back-link"' not in client.get(path).text


def test_app_name_and_icons(client):
    page = client.get("/").text
    assert "<title>Home · Savings</title>" in page
    assert '<img src="/static/icons/icon-192.png' in page and ">Savings</a>" in page
    assert 'rel="apple-touch-icon"' in page and 'rel="manifest"' in page
    fav = client.get("/favicon.ico")
    assert fav.status_code == 200 and fav.headers["content-type"] == "image/x-icon"
    manifest = client.get("/static/manifest.json").json()
    assert manifest["name"] == "Savings"
    for icon in manifest["icons"]:
        assert client.get(icon["src"]).status_code == 200
    assert client.get("/static/icons/apple-touch-icon.png").status_code == 200


def test_no_budget_alert_banners_on_home(client, dash_conn):
    page = client.get("/").text            # Transport is over budget, but Home shows no warning banner
    assert "Budget alerts" not in page and "over budget" not in page


def test_pc_menu_is_layered_above_the_toolbar(client):
    import re
    css = client.get("/static/style.css").text
    z = lambda sel: int(re.search(re.escape(sel) + r" \{[^}]*z-index: (\d+)", css).group(1))
    # the ☰ menu opens from the top bar: the top bar's layer must be above the sticky toolbar
    # (both are their own layers because of the page-transition names), or the toolbar hides
    # the menu's first item, Add expense
    assert z(".topbar") > z(".nav")
    assert z(".topbar") < z(".tabbar")      # the phone's open ⚡ sheet still dims the top bar


# --- Savings vs budget (A: balance, B: per category, C: pace) --------------------------------
# Day 8 of 31. Allowed by today = budget * 8 // 31: Dining out 2580, Transport 1290, Entertainment 5161.

def test_budget_balance_prorates_budgets_to_today(dash_conn, uid):
    vb = summary.dashboard(dash_conn, uid, TODAY)["vs_budget"]
    assert (vb["day"], vb["days"]) == (8, 31)
    by = {c["name"]: c["balance"] for c in vb["categories"]}
    assert by == {"Dining out": 2580 - 9000, "Transport": 1290 - 6000, "Entertainment": 5161 - 3000}
    assert [c["name"] for c in vb["categories"]] == ["Dining out", "Transport", "Entertainment"]   # worst first
    assert vb["balance"] == -8969 and vb["allowed"] == 9031
    assert vb["planned"] == 200000 - 35000
    assert vb["projected"] == vb["planned"] + vb["balance"] == 156031


def test_budget_balance_fixed_and_unbudgeted_spending(dash_conn, uid):
    ids = {n: category_id(dash_conn, n) for n in ("Entertainment", "Groceries", "Dining out")}
    dash_conn.execute("INSERT INTO recurring_expenses (user_id, description, category_id, amount_cents, every_months,"
                      " start_date) VALUES (?, 'Streaming', ?, 1500, 1, '2026-11-02')", (uid, ids["Entertainment"]))
    rid = dash_conn.execute("SELECT max(id) FROM recurring_expenses").fetchone()[0]
    dash_conn.executemany(
        "INSERT INTO expenses (date, description, category_id, amount_cents, one_off, recurring_id) VALUES (?, ?, ?, ?, ?, ?)",
        [("2026-11-02", "Concert", ids["Entertainment"], 25000, 1, None),    # one-off beyond the budget
         ("2026-11-02", "Streaming", ids["Entertainment"], 1500, 0, rid),    # recurring
         ("2026-11-20", "Booked dinner", ids["Dining out"], 1000, 0, None),  # future-dated
         ("2026-11-03", "Market", ids["Groceries"], 4000, 0, None)])         # no budget
    dash_conn.commit()
    vb = summary.dashboard(dash_conn, uid, TODAY)["vs_budget"]
    by = {c["name"]: c for c in vb["categories"]}
    ent = by["Entertainment"]   # fixed 26500 > budget 20000: nothing left for day-to-day, 6500 over
    assert (ent["fixed"], ent["flexible"], ent["allowed"], ent["daily"]) == (26500, 0, 0, 3000)
    assert ent["balance"] == -3000 - 6500
    din = by["Dining out"]      # the future-dated dinner comes off the budget, not the pace
    assert (din["fixed"], din["flexible"], din["allowed"]) == (1000, 9000, 9000 * 8 // 31)
    assert din["balance"] == 9000 * 8 // 31 - 9000
    assert by["Groceries"]["balance"] == -4000       # unbudgeted: all of it is damage
    pace = vb["pace"]
    assert pace["actual"][7] == 220.0 and pace["actual"][8] is None   # 90 + 60 + 30 + 40, fixed left out
    assert pace["allowed"][-1] == (9000 + 5000 + 0) / 100


def test_budget_pace_daily_spending_against_what_each_day_had_available(dash_conn, uid):
    """Each day has the daily rate plus what carried over: spend less and the next day has more."""
    vb = summary.dashboard(dash_conn, uid, TODAY)["vs_budget"]
    pace, days, day = vb["pace"], vb["days"], vb["day"]
    flexible = sum(c["flexible"] for c in vb["categories"])
    rate = flexible / days
    assert pace["rate"] == round(rate) / 100
    assert len(pace["spent"]) == len(pace["available"]) == days
    assert all(x is None for x in pace["spent"][day:] + pace["available"][day:])     # after today: nothing yet
    carry = 0
    for i in range(day):
        assert pace["available"][i] == round(rate + carry) / 100
        carry += rate - pace["spent"][i] * 100
    # the daily bars add up to the cumulative line, and the carry ends where the balance is
    assert round(sum(pace["spent"][:day]), 2) == pace["actual"][day - 1] == vb["daily"] / 100
    assert abs((rate * day - vb["daily"]) - carry) < 1e-6


def test_budget_pace_carries_over_both_ways(conn, uid, monkeypatch):
    """A 31-day period, budget 310.00: a 10.00 rate. Day 1 spends 4 (6 carried), day 2 spends 25
    (available 16, so 9 overspent), day 3 has 10 - 9 = 1."""
    from .conftest import add_budget
    cid = conn.execute("SELECT id FROM categories WHERE user_id = ? ORDER BY sort_order LIMIT 1", (uid,)).fetchone()[0]
    add_budget(conn, cid, 31000, "2026-01-01")
    conn.executemany("INSERT INTO expenses (date, description, category_id, amount_cents) VALUES (?, '', ?, ?)",
                     [("2026-10-28", cid, 400), ("2026-10-29", cid, 2500)])
    conn.commit()
    ms = summary.month_summary(conn, uid, 2026, 11)           # 28 Oct - 27 Nov: 31 days
    pace = summary.budget_balance(conn, uid, ms, date(2026, 10, 30))["pace"]
    assert pace["rate"] == 10.0
    assert pace["spent"][:3] == [4.0, 25.0, 0.0]
    assert pace["available"][:3] == [10.0, 16.0, 1.0]
    assert pace["spent"][3] is None and pace["available"][3] is None


def test_budget_balance_last_day_is_budget_minus_spent(dash_conn, uid):
    vb = summary.dashboard(dash_conn, uid, date(2026, 11, 27))["vs_budget"]
    assert {c["name"]: c["balance"] for c in vb["categories"]} == {
        "Dining out": 1000, "Transport": -1000, "Entertainment": 17000}
    assert vb["projected"] == vb["planned"] + vb["balance"] == 200000 - 18000


def test_savings_vs_budget_lives_on_the_budget_page_not_home(client, dash_conn):
    home = client.get("/").text
    assert 'data-home="vsbudget"' not in home and 'data-home="pace"' not in home
    assert "Savings vs budget" not in home and 'id="chart-budget-pace"' not in home
    data = json.loads(re.search(r'id="dashboard-data">(.*?)</script>', home, re.S).group(1))
    assert "budget_pace" not in data
    assert "Savings vs budget" not in client.get("/settings").text          # not in Home layout either
    page = client.get("/budget").text
    assert "damage so far, behind budget" in page and "€1,560.31" in page
    data = json.loads(re.search(r'id="budget-pace-data">(.*?)</script>', page, re.S).group(1))
    assert len(data["allowed"]) == 31 and len(data["spent"]) == len(data["available"]) == 31
    assert "Each day gets the daily rate (€" in page


def test_budget_explanation_is_behind_learn_how(client, dash_conn):
    page = client.get("/budget").text
    learn = page[page.index('<details class="vb-learn">'):]
    assert "<summary>Learn how</summary>" in learn and "day 8 of 31" in learn and "€90.31" in learn
    assert '<details class="vb-learn" open' not in page                       # closed until pressed
    assert "Full period:" not in page and "Green: under pace" not in page    # the old always-on text is gone


# --- Budget page: you against your plan ------------------------------------------------------

def test_budget_page_current_period(client, dash_conn):
    page = client.get("/budget").text
    assert "<h1>Budget</h1>" in page and 'class="pp-pick"' in page          # period picker
    assert "-€89.69" in page and "On track to save" in page and "<summary>Learn how</summary>" in page
    assert 'id="chart-budget-pace"' in page and 'id="budget-pace-data"' in page
    assert "<th>Total</th>" in page and "Allowed by today" in page
    assert "Budget track record" in page


def test_budget_page_finished_period_reads_as_an_outcome(client, dash_conn):
    page = client.get("/budget?period=2026-10").text                     # October: Dining out 25.00 of 100.00
    assert "+€75.00" in page and "saved, under budget" in page and "saved so far" not in page
    assert "Saved <strong" in page and "On track to save" not in page
    assert "over the whole period" in page


def test_budget_page_upcoming_period(client, dash_conn):
    page = client.get("/budget?period=2027-02").text
    assert "This period hasn't started yet." in page and 'id="chart-budget-pace"' not in page


def test_budget_page_without_budgets(client):
    page = client.get("/budget").text
    assert "Set budgets on your categories" in page and 'id="chart-budget-pace"' not in page



# --- period picker: ‹ November 2026 ▾ › with a month grid ---------------------------------------

def test_period_picker_steps_and_jumps(client, dash_conn):
    page = client.get("/month?period=2026-09").text
    assert 'href="/month?period=2026-08" aria-label="Previous period"' in page
    assert 'href="/month?period=2026-10" aria-label="Next period"' in page
    assert "<strong>September 2026</strong>" in page and 'name="month"' not in page and ">Go<" not in page
    assert 'href="/month?period=2026-09" class="pp-m is-sel" aria-current="true">Sep<' in page
    assert 'href="/month?period=2026-11" class="pp-m is-now">Nov<' in page              # today's period
    assert 'class="pp-year" data-year="2026">' in page and 'data-year="2025" hidden' in page
    assert '· <a href="/month?period=2026-11">This month</a>' in page                     # away: a way back
    assert "This month</a></p>" not in client.get("/month").text                      # already there


def test_period_picker_keeps_the_log_filter(client, dash_conn):
    cid = category_id(dash_conn, "Transport")
    page = client.get(f"/log?period=2026-11&category={cid}").text
    assert f'href="/log?period=2026-03&amp;category={cid}" class="pp-m">Mar<' in page
    assert f'href="/log?period=2026-10&amp;category={cid}" aria-label="Previous period"' in page


def test_year_stepper(client, dash_conn):
    page = client.get("/year?year=2025").text
    assert 'href="/year?year=2024" aria-label="Previous year"' in page and '<a href="/year">This year</a>' in page
    assert 'name="year"' not in page and ">Go<" not in page
