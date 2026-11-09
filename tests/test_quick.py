"""Phone quick add: data for the sheet, saving an expense or income."""
import re
from datetime import date

import pytest

from .conftest import browser, category_id, login, make_user

TODAY = date(2026, 11, 5)


@pytest.fixture(autouse=True)
def _today(monkeypatch):
    monkeypatch.setattr("app.config.today", lambda: TODAY)


def _exp(conn, name, day="2026-11-01", created="2026-11-01T10:00:00Z"):
    conn.execute("INSERT INTO expenses (date, description, category_id, amount_cents, created_at) "
                 "VALUES (?, 'x', ?, 100, ?)", (day, category_id(conn, name), created))


def test_data_most_used_first_and_last_used_preselected(client, conn):
    for n in range(3):
        _exp(conn, "Transport", created=f"2026-11-0{n + 1}T10:00:00Z")
    for n in range(2):
        _exp(conn, "Dining out", created=f"2026-10-2{n}T10:00:00Z")
    _exp(conn, "Health", created="2026-11-04T09:00:00Z")                   # used most recently
    _exp(conn, "Gifts", day="2026-06-01", created="2026-06-01T09:00:00Z")  # too long ago to count
    conn.commit()
    d = client.get("/quick-add/data").json()
    names = {c["id"]: c["name"] for c in d["categories"]}
    top = [names[i] for i in d["top"]]
    assert top[:3] == ["Transport", "Dining out", "Health"] and len(top) == 5 and "Gifts" not in top[:3]
    assert names[d["last"]] == "Health"
    assert (d["today"], d["yesterday"]) == ("2026-11-05", "2026-11-04")


def test_data_without_history_uses_your_order(client, conn):
    d = client.get("/quick-add/data").json()
    names = {c["id"]: c["name"] for c in d["categories"]}
    assert [names[i] for i in d["top"]] == ["Groceries", "Housing", "Utilities", "Transport", "Dining out"]
    assert names[d["last"]] == "Groceries"


def test_save_expense_empty_description_uses_category(client, conn):
    r = client.post("/quick-add", data={"kind": "expense", "amount": "12,50", "category_id": str(category_id(conn, "Groceries")),
                                        "date": "2026-11-05", "description": ""})
    assert r.status_code == 200
    j = r.json()
    assert j["message"] == "Saved €12.50 · Groceries"
    row = conn.execute("SELECT id, description, amount_cents, date, user_id FROM expenses").fetchone()
    assert (row["description"], row["amount_cents"], row["date"]) == ("Groceries", 1250, "2026-11-05")
    assert "undo" not in j and j["kind"] == "expense" and j["cents"] == 1250
    log = conn.execute("SELECT detail FROM activity_log WHERE kind = 'expense.added'").fetchone()[0]
    assert log.endswith("(quick add)") and "12" not in log.split("dated")[0]


def test_save_income(client, conn):
    j = client.post("/quick-add", data={"kind": "income", "amount": "50", "date": "2026-11-04", "description": ""}).json()
    assert j["message"] == "Saved €50.00 income"
    row = conn.execute("SELECT id, description, amount_cents, date FROM extra_income").fetchone()
    assert (row["description"], row["amount_cents"], row["date"]) == ("Extra income", 5000, "2026-11-04")
    assert "undo" not in j and j["kind"] == "income"


@pytest.mark.parametrize("data, field", [
    ({"amount": "", "category_id": "CAT", "date": "2026-11-05"}, "amount"),
    ({"amount": "0", "category_id": "CAT", "date": "2026-11-05"}, "amount"),
    ({"amount": "5", "category_id": "", "date": "2026-11-05"}, "category_id"),
    ({"amount": "5", "category_id": "999999", "date": "2026-11-05"}, "category_id"),
    ({"amount": "5", "category_id": "CAT", "date": "x"}, "date"),
    ({"kind": "income", "amount": "-3", "date": "2026-11-05"}, "amount"),
])
def test_errors_as_json(client, conn, data, field):
    data = {k: (str(category_id(conn, "Groceries")) if v == "CAT" else v) for k, v in data.items()}
    r = client.post("/quick-add", data=data)
    assert r.status_code == 422 and field in r.json()["errors"]
    assert conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 0


def test_cannot_use_someone_elses_category(app, client, conn):
    make_user(conn, "bob")
    bob_cat = category_id(conn, "Groceries", conn.execute("SELECT id FROM users WHERE username='bob'").fetchone()[0])
    r = client.post("/quick-add", data={"amount": "5", "category_id": str(bob_cat), "date": "2026-11-05"})
    assert r.status_code == 422
    assert login(browser(app), "bob").get("/quick-add/data").json()["categories"][0]["id"] == bob_cat


def test_sheet_only_wired_to_the_phone_menu(client):
    page = client.get("/").text
    sheet = re.search(r'<div class="action-sheet">.*?</div>', page, re.S).group(0)
    burger = re.search(r'<div class="burger-panel">.*?</div>', page, re.S).group(0)
    assert 'href="/add" data-quick-add' in sheet and "data-quick-add" not in burger
    assert 'id="quick-add"' in page and "/static/quick.js" in page
    assert client.get("/static/quick.js").status_code == 200


def test_logged_out_pages_have_no_sheet(app):
    page = browser(app).get("/login").text
    assert "quick-add" not in page and "quick.js" not in page
    assert browser(app).get("/quick-add/data", follow_redirects=False).status_code == 303


def test_no_saved_banners_at_all(client):
    page = client.get("/").text
    assert "qa-toast" not in page and "Undo" not in page                    # quick add: no bar
    assert "qa-toast" not in client.get("/static/quick.js").text
    css = client.get("/static/style.css").text
    assert ".saved-flash { position: absolute; width: 1px;" in css         # full forms: hidden even without animations
