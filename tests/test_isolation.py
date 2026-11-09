"""Users must never see or change each other's data, including by guessing ids in URLs.

Alice owns one of everything. Bob is logged in and tries every page and action on Alice's ids.
"""
import pytest

from .conftest import add_budget, browser, category_id, login, make_user


@pytest.fixture
def alice_data(conn, uid):
    cid = category_id(conn, "Dining out", uid)
    conn.execute("INSERT INTO expenses (date, description, category_id, amount_cents) "
                 "VALUES ('2026-11-02', 'ALICE-SECRET', ?, 4242)", (cid,))
    eid = conn.execute("SELECT id FROM expenses").fetchone()[0]
    conn.execute("INSERT INTO extra_income (user_id, date, description, amount_cents) "
                 "VALUES (?, '2026-11-02', 'ALICE-BONUS', 7777)", (uid,))
    iid = conn.execute("SELECT id FROM extra_income").fetchone()[0]
    conn.execute("INSERT INTO regular_income (user_id, amount_cents, effective_from) VALUES (?, 313131, '2026-01-01')", (uid,))
    add_budget(conn, cid, 98765, "2026-01-01")
    conn.commit()
    return {"cid": cid, "eid": eid, "iid": iid}


@pytest.fixture
def bob(app, conn):
    make_user(conn, "bob")
    return login(browser(app), "bob")


SECRETS = ("ALICE-SECRET", "ALICE-BONUS", "€42.42", "€3,131.31", "€987.65", "€77.77")


@pytest.mark.parametrize("path", ["/", "/log?period=2026-11", "/month?period=2026-11", "/year?year=2026",
                                  "/income?period=2026-11", "/categories", "/profile"])
def test_bob_sees_none_of_alices_numbers(bob, alice_data, path):
    page = bob.get(path).text
    for secret in SECRETS:
        assert secret not in page, f"{secret} leaked on {path}"


def test_bob_cannot_open_alices_entries(bob, alice_data):
    assert bob.get(f"/expenses/{alice_data['eid']}/edit").status_code == 404
    assert bob.get(f"/income/{alice_data['iid']}/edit").status_code == 404


def test_bob_cannot_change_or_delete_alices_entries(bob, conn, alice_data):
    form = {"date": "2026-11-03", "description": "pwned", "category_id": str(alice_data["cid"]),
            "amount": "1", "notes": ""}
    assert bob.post(f"/expenses/{alice_data['eid']}/edit", data=form).status_code == 404
    assert bob.post(f"/expenses/{alice_data['eid']}/delete").status_code == 404
    assert bob.post(f"/income/{alice_data['iid']}/edit",
                    data={"date": "2026-11-03", "description": "pwned", "amount": "1", "notes": ""}).status_code == 404
    assert bob.post(f"/income/{alice_data['iid']}/delete").status_code == 404
    assert conn.execute("SELECT description, amount_cents FROM expenses").fetchone()[:] == ("ALICE-SECRET", 4242)
    assert conn.execute("SELECT COUNT(*) FROM extra_income").fetchone()[0] == 1


def test_bob_cannot_file_expenses_under_alices_category(bob, conn, alice_data):
    form = {"date": "2026-11-03", "description": "sneaky", "category_id": str(alice_data["cid"]),
            "amount": "5", "notes": ""}
    r = bob.post("/add", data=form)
    assert r.status_code == 422
    assert conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 1


def test_bob_cannot_move_his_expense_into_alices_category(bob, conn, alice_data):
    bob_cat = category_id(conn, "Gifts", conn.execute("SELECT id FROM users WHERE username='bob'").fetchone()[0])
    bob.post("/add", data={"date": "2026-11-03", "description": "mine", "category_id": str(bob_cat),
                           "amount": "5", "notes": ""})
    eid = conn.execute("SELECT id FROM expenses WHERE description = 'mine'").fetchone()[0]
    r = bob.post(f"/expenses/{eid}/edit", data={"date": "2026-11-03", "description": "mine",
                                               "category_id": str(alice_data["cid"]), "amount": "5",
                                               "notes": ""})
    assert r.status_code == 422
    assert conn.execute("SELECT category_id FROM expenses WHERE id = ?", (eid,)).fetchone()[0] == bob_cat


@pytest.mark.parametrize("action, data", [
    ("edit", {"name": "Pwned", "budget": "1", "budget_from": "2026-01-01"}),
    ("archive", {}),
    ("move", {"direction": "up"}),
    ("delete", {"expected": "1", "action": "delete_entries", "confirm": "Dining out"}),
])
def test_bob_cannot_touch_alices_categories(bob, conn, alice_data, action, data):
    r = bob.post(f"/categories/{alice_data['cid']}/{action}", data=data)
    assert r.status_code == 404 and "no longer exists" in r.text
    row = conn.execute("SELECT name, archived FROM categories WHERE id = ?", (alice_data["cid"],)).fetchone()
    assert tuple(row) == ("Dining out", 0)
    assert conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 1
    assert conn.execute("SELECT monthly_budget_cents FROM category_budgets").fetchone()[0] == 98765


def test_bob_cannot_merge_into_alices_category(bob, conn, alice_data):
    bob_id = conn.execute("SELECT id FROM users WHERE username='bob'").fetchone()[0]
    bob_cat = category_id(conn, "Travel", bob_id)
    conn.execute("INSERT INTO expenses (date, description, category_id, amount_cents) VALUES ('2026-11-01', 'b', ?, 1)",
                 (bob_cat,))
    conn.commit()
    r = bob.post(f"/categories/{bob_cat}/delete",
                 data={"expected": "1", "action": "move", "target": str(alice_data["cid"])})
    assert r.status_code == 422 and "Choose where the expenses should go." in r.text
    assert conn.execute("SELECT category_id FROM expenses WHERE description = 'b'").fetchone()[0] == bob_cat


def test_same_category_names_for_different_users(bob, conn, alice_data):
    r = bob.post("/categories", data={"name": "Books", "budget": "", "budget_from": ""}, follow_redirects=False)
    assert r.status_code == 303
    login_alice = conn.execute("SELECT COUNT(*) FROM categories WHERE name = 'Dining out'").fetchone()[0]
    assert login_alice == 2   # both users have their own "Dining out"


def test_settings_are_per_user(bob, client, conn, uid):
    bob.post("/profile/start-day", data={"start_day": "1"})
    assert conn.execute("SELECT period_start_day FROM users WHERE id = ?", (uid,)).fetchone()[0] == 28
    assert "28 Oct – 27 Nov 2026" in client.get("/month?period=2026-11").text
    assert "1 Nov – 30 Nov 2026" in bob.get("/month?period=2026-11").text
