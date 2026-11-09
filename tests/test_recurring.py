"""Recurring expenses. S = 1 (calendar months) unless noted; "today" is set per test."""
from datetime import date

import pytest

from app import recurring

from .conftest import browser, category_id, login, make_user

TODAY = date(2026, 11, 5)


@pytest.fixture(autouse=True)
def _today(monkeypatch):
    state = {"today": TODAY}
    monkeypatch.setattr("app.config.today", lambda: state["today"])
    return state


@pytest.fixture
def s1(conn, uid):
    conn.execute("UPDATE users SET period_start_day = 1 WHERE id = ?", (uid,))
    conn.commit()


def _add(client, conn, **over):
    data = {"description": "Rent", "category_id": str(category_id(conn, "Housing")), "amount": "800",
            "every_months": "1", "start_date": "2026-11-10", "end_date": "", "notes": ""}
    data.update(over)
    return client.post("/recurring", data=data, follow_redirects=False)


def _made(conn):
    return [(r["date"], r["amount_cents"]) for r in conn.execute(
        "SELECT date, amount_cents FROM expenses WHERE recurring_id IS NOT NULL ORDER BY date")]


def _rule(conn):
    return conn.execute("SELECT * FROM recurring_expenses").fetchone()


def test_occurrences_clamp_without_drift():
    jan31 = date(2026, 1, 31)
    assert [recurring.occurrence(jan31, 1, k) for k in range(4)] == \
        [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]
    leap = date(2028, 2, 29)
    assert [recurring.occurrence(leap, 12, k) for k in range(5)] == \
        [date(2028, 2, 29), date(2029, 2, 28), date(2030, 2, 28), date(2031, 2, 28), date(2032, 2, 29)]
    assert recurring.occurrence(date(2026, 11, 15), 3, 1) == date(2027, 2, 15)


def test_first_index_after():
    rule = {"start_date": "2026-01-31", "every_months": 1}
    assert recurring.first_index_after(rule, date(2025, 6, 1)) == 0
    assert recurring.first_index_after(rule, date(2026, 2, 28)) == 2               # Mar 31
    assert recurring.first_index_after(rule, date(2026, 2, 28), inclusive=True) == 1


def test_set_up_creates_this_periods_payment_as_future(client, conn, s1):
    r = _add(client, conn)
    assert r.headers["location"] == "/recurring?done=added"
    assert _made(conn) == [("2026-11-10", 80000)]             # up to the period's end (30 Nov), not beyond
    page = client.get("/recurring?done=added").text
    assert "Recurring expense set up." in page and "Rent" in page and "Monthly from 10 Nov 2026" in page
    assert "Next payment after today: <strong>10 Nov 2026</strong>" in page
    log = client.get("/log?year=2026&month=11").text
    assert "↻ recurring</a>" in log and "tag-future" in log
    detail = conn.execute("SELECT detail FROM activity_log WHERE kind = 'expense.recurring_added'").fetchone()[0]
    assert detail == "Set up a recurring expense in “Housing” (monthly from 10 Nov 2026)"


def test_past_start_backfills(client, conn, s1):
    _add(client, conn, start_date="2026-09-01")
    assert _made(conn) == [("2026-09-01", 80000), ("2026-10-01", 80000), ("2026-11-01", 80000)]


def test_respects_start_day_horizon(client, conn, uid):
    # S = 28: today 5 Nov is in the period 28 Oct .. 27 Nov
    _add(client, conn, start_date="2026-11-20")
    assert _made(conn) == [("2026-11-20", 80000)]
    _add(client, conn, description="Gym", start_date="2026-11-28")
    assert len(_made(conn)) == 1                                 # 28 Nov is next period: not yet


def test_catch_up_on_page_load_once(client, conn, s1, _today):
    _add(client, conn)
    _today["today"] = date(2026, 12, 2)
    client.get("/")
    client.get("/month")
    assert _made(conn) == [("2026-11-10", 80000), ("2026-12-10", 80000)]


def test_deleted_payment_is_not_recreated(client, conn, s1, _today):
    _add(client, conn)
    eid = conn.execute("SELECT id FROM expenses WHERE recurring_id IS NOT NULL").fetchone()[0]
    client.post(f"/expenses/{eid}/delete")
    client.get("/")
    assert _made(conn) == []


def test_edit_replaces_only_payments_after_today(client, conn, s1, _today):
    _add(client, conn, start_date="2026-10-03")
    _add(client, conn, description="Phone", start_date="2026-11-20", amount="20")
    assert _made(conn) == [("2026-10-03", 80000), ("2026-11-03", 80000), ("2026-11-20", 2000)]
    phone = conn.execute("SELECT id FROM recurring_expenses WHERE description = 'Phone'").fetchone()[0]
    r = client.post(f"/recurring/{phone}/edit", data={"description": "Phone", "category_id": str(category_id(conn, "Utilities")),
                                                      "amount": "25", "notes": "", "end_date": ""}, follow_redirects=False)
    assert r.headers["location"] == "/recurring?done=saved"
    rows = conn.execute("SELECT date, amount_cents, category_id FROM expenses WHERE recurring_id = ?", (phone,)).fetchall()
    assert [tuple(x) for x in rows] == [("2026-11-20", 2500, category_id(conn, "Utilities"))]
    rent = conn.execute("SELECT id FROM recurring_expenses WHERE description = 'Rent'").fetchone()[0]
    client.post(f"/recurring/{rent}/edit", data={"description": "Rent", "category_id": str(category_id(conn, "Housing")),
                                                 "amount": "900", "notes": "", "end_date": ""})
    # 3 Oct and 3 Nov are on/before today (5 Nov): left alone
    assert [x[1] for x in conn.execute("SELECT date, amount_cents FROM expenses WHERE recurring_id = ? ORDER BY date", (rent,))] \
        == [80000, 80000]
    _today["today"] = date(2026, 12, 1)
    client.get("/")
    assert conn.execute("SELECT amount_cents FROM expenses WHERE recurring_id = ? AND date = '2026-12-03'", (rent,)).fetchone()[0] == 90000


def test_end_date_stops_payments(client, conn, s1, _today):
    _add(client, conn, start_date="2026-09-15", end_date="2026-10-31")
    assert _made(conn) == [("2026-09-15", 80000), ("2026-10-15", 80000)]
    assert "<span class=\"tag\">ended</span>" in client.get("/recurring").text
    assert _add(client, conn, start_date="2026-09-15", end_date="2026-09-01").status_code == 422


def test_pause_and_resume_skip_missed_payments(client, conn, s1, _today):
    _add(client, conn)
    rid = _rule(conn)["id"]
    client.post(f"/recurring/{rid}/pause")
    assert _made(conn) == [] and _rule(conn)["active"] == 0              # 10 Nov was after today: removed
    _today["today"] = date(2027, 1, 12)
    client.get("/")
    assert _made(conn) == []                                             # paused: nothing
    assert "paused" in client.get("/recurring").text
    client.post(f"/recurring/{rid}/resume")
    assert _made(conn) == []                                             # 10 Jan was missed; next is 10 Feb
    _today["today"] = date(2027, 2, 1)
    client.get("/")
    assert _made(conn) == [("2027-02-10", 80000)]


def test_delete_keeps_past_payments(client, conn, s1):
    _add(client, conn, start_date="2026-10-01")
    _add(client, conn, description="Later", start_date="2026-11-25")
    for rid in [r[0] for r in conn.execute("SELECT id FROM recurring_expenses")]:
        assert client.post(f"/recurring/{rid}/delete", follow_redirects=False).headers["location"] == "/recurring?done=deleted"
    rows = conn.execute("SELECT date, recurring_id FROM expenses ORDER BY date").fetchall()
    assert [tuple(r) for r in rows] == [("2026-10-01", None), ("2026-11-01", None)]   # 25 Nov (future) removed


def test_archived_category_puts_rule_on_hold(client, conn, s1, _today):
    _add(client, conn, category_id=str(category_id(conn, "Subscriptions")), start_date="2026-10-10")
    conn.execute("UPDATE categories SET archived = 1 WHERE id = ?", (category_id(conn, "Subscriptions"),))
    conn.commit()
    _today["today"] = date(2026, 12, 1)
    client.get("/")
    assert _made(conn) == [("2026-10-10", 80000), ("2026-11-10", 80000)]       # no December payment
    assert "on hold" in client.get("/recurring").text


@pytest.mark.parametrize("field, value, message", [
    ("description", "", "Required."),
    ("amount", "0", "Amount must be more than zero."),
    ("every_months", "2", "Pick how often."),
    ("start_date", "nope", "Enter a valid date."),
    ("category_id", "999999", "Pick a category."),
])
def test_validation(client, conn, field, value, message):
    r = _add(client, conn, **{field: value})
    assert r.status_code == 422 and message in r.text
    assert conn.execute("SELECT COUNT(*) FROM recurring_expenses").fetchone()[0] == 0


def test_rules_are_private(app, client, conn):
    _add(client, conn, description="Flat 4B")
    rid = _rule(conn)["id"]
    make_user(conn, "bob")
    bob = login(browser(app), "bob")
    assert "Flat 4B" not in bob.get("/recurring").text
    for path in (f"/recurring/{rid}/edit",):
        assert bob.get(path).status_code == 404
    for action in ("pause", "resume", "delete", "edit"):
        assert bob.post(f"/recurring/{rid}/{action}", data={"description": "x", "category_id": "1", "amount": "1"}).status_code == 404
    assert _rule(conn)["active"] == 1


def test_menus_and_settings_link_to_recurring(client):
    assert 'href="/recurring"' in client.get("/settings").text
    assert '<a class="back-link" href="/settings">' in client.get("/recurring").text
