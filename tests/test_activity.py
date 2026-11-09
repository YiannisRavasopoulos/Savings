"""The admin's activity log: what gets recorded, that it never contains money or private text,
and the admin page that shows it."""
from datetime import date

import pytest

from .conftest import PASSWORD, browser, category_id, login, make_user
from .test_admin import ADMIN_PW, _admin, adm, admin_app  # noqa: F401  (fixtures)


def _post(c, url, **data):
    return c.post(url, data=data, follow_redirects=False)


def _log(conn):
    return [(r["actor_name"], r["kind"], r["detail"], r["effective_from"])
            for r in conn.execute("SELECT * FROM activity_log ORDER BY id")]


def _kinds(conn):
    return [r[1] for r in _log(conn)]


def test_expense_actions_are_logged_without_money(client, conn):
    cid = category_id(conn, "Groceries")
    _post(client, "/add", date="2026-11-04", description="SECRET-SHOP", category_id=str(cid), amount="123.45",
          notes="SECRET-NOTE")
    eid = conn.execute("SELECT id FROM expenses").fetchone()[0]
    _post(client, f"/expenses/{eid}/edit", date="2026-11-05", description="SECRET-SHOP-2", category_id=str(cid),
          amount="99", notes="SECRET-NOTE")
    other = category_id(conn, "Shopping")
    _post(client, f"/expenses/{eid}/edit", date="2026-11-05", description="SECRET-SHOP-2", category_id=str(other),
          amount="99", notes="SECRET-NOTE")
    _post(client, f"/expenses/{eid}/delete")
    entries = _log(conn)
    assert [e[1] for e in entries if e[1].startswith("expense.")] == ["expense.added", "expense.edited",
                                                                     "expense.moved", "expense.deleted"]
    text = " ".join(e[2] for e in entries)
    assert "Added an expense in “Groceries” (dated 04 Nov 2026)" in text
    assert "changed amount, description, date 04 Nov 2026 → 05 Nov 2026" in text
    assert "Moved an expense (dated 05 Nov 2026) from “Groceries” to “Shopping”" in text
    for secret in ("SECRET", "123", "99", "€"):
        assert secret not in text, secret
    assert all(e[0] == "Alice" for e in entries if e[1].startswith("expense."))


def test_category_income_and_profile_actions_are_logged(client, conn):
    _post(client, "/categories", name="Pets", budget="50", budget_from="2026-01-01")
    pets = category_id(conn, "Pets")
    _post(client, f"/categories/{pets}/edit", name="Pet stuff", budget="60", budget_from="2026-02-01")
    _post(client, f"/categories/{pets}/archive")
    _post(client, f"/categories/{pets}/archive")
    _post(client, f"/categories/{pets}/delete", expected="0")
    _post(client, "/income", date="2026-11-02", description="Bonus", amount="300", notes="")
    _post(client, "/profile/regular-income", income_amount="2000", income_from="2026-01-01")
    _post(client, "/profile/name", display_name="Alice B")
    _post(client, "/profile/start-day", start_day="1")
    _post(client, "/profile/password", current=PASSWORD, password="a brand new pw", confirm="a brand new pw")
    _post(client, "/request", subject="idea", message="hello admin")
    kinds = _kinds(conn)
    for k in ("category.added", "category.renamed", "category.budget", "category.archived", "category.unarchived",
              "category.deleted", "income.extra_added", "income.regular_set", "account.renamed",
              "account.start_day", "account.password_changed", "account.request_sent"):
        assert k in kinds, k
    text = " ".join(e[2] for e in _log(conn))
    assert "Renamed “Pets” to “Pet stuff”" in text and "Set their budget for “Pet stuff”" in text
    assert "2000" not in text and "300" not in text and "hello admin" not in text
    assert ("Alice", "category.budget", "Set their budget for “Pet stuff”", "2026-02-01") in _log(conn)


def test_logins_and_registrations(app, conn, uid):
    browser(app).post("/login", data={"username": "alice", "password": "wrong-password"})
    login(browser(app), "alice")
    _post(browser(app), "/register", username="newbie", display_name="Newbie", password="long enough pw",
          confirm="long enough pw")
    log = _log(conn)
    assert ("Alice", "account.login_failed") == log[0][:2] and "Failed login for “alice”" in log[0][2]
    assert any(k == "account.login" for _, k, _, _ in log)
    assert ("Newbie", "account.registered", "Requested an account as “newbie”", None) in log


def test_shared_category_actions_are_logged(app, client, conn, uid, monkeypatch):
    monkeypatch.setattr("app.config.today", lambda: date(2026, 11, 4))
    r = _post(client, "/categories", name="Home", budget="600", budget_from="2026-01-01", joint="1")
    cid = int(r.headers["location"].rsplit("/", 1)[1])
    make_user(conn, "bob")
    bob = login(browser(app), "bob")
    _post(client, f"/shared/{cid}/invite", username="bob")
    _post(bob, f"/shared/invites/{conn.execute('SELECT id FROM joint_invites').fetchone()[0]}/accept", agree="1")
    monkeypatch.setattr("app.config.today", lambda: date(2026, 12, 10))
    _post(bob, "/add", date="2026-12-05", description="PRIVATE", category_id=str(cid), amount="10", notes="")
    _post(client, f"/categories/{cid}/edit", name="Home", budget="800", budget_from="2027-01-01")
    _post(bob, f"/shared/{cid}/leave")
    log = _log(conn)
    kinds = [k for _, k, _, _ in log]
    for k in ("shared.created", "shared.invite", "shared.joined", "expense.added", "category.budget", "shared.leave"):
        assert k in kinds, k
    assert ("Bob", "shared.joined", "Accepted the invitation and joined", None) in log
    assert ("Bob", "shared.leave", "Left the shared category", None) in log
    assert "PRIVATE" not in str(log) and "800" not in str(log)


def test_admin_actions_are_logged(adm, conn, app):
    make_user(conn, "carol", status="pending", seed=False)
    carol = conn.execute("SELECT id FROM users WHERE username = 'carol'").fetchone()[0]
    _post(adm, f"/users/{carol}/approve")
    _post(adm, f"/users/{carol}/disable")
    _post(adm, f"/users/{carol}/enable")
    adm.post(f"/users/{carol}/reset-password")
    _post(adm, f"/users/{carol}/delete", confirm="carol")
    log = _log(conn)
    admin_kinds = [k for name, k, _, _ in log if name == "Admin"]
    assert admin_kinds == ["admin.setup", "admin.approved", "admin.disabled", "admin.enabled",
                           "admin.password_reset", "admin.user_deleted"]


# --- the admin page ----------------------------------------------------------------------------

def test_admin_log_page_and_filters(adm, client, conn):
    cid = category_id(conn, "Groceries")
    _post(client, "/add", date="2026-11-04", description="x", category_id=str(cid), amount="5", notes="")
    _post(client, "/categories", name="Pets", budget="", budget_from="")
    page = adm.get("/log").text
    assert 'class="active" aria-current="page">Activity log<' in page
    assert "Added an expense in “Groceries”" in page and "Added the category “Pets”" in page
    assert "Created the admin account" in page
    only_cats = adm.get("/log?group=category").text
    assert "Added the category “Pets”" in only_cats and "Added an expense" not in only_cats
    assert 'name="who"' not in page                      # no filter by person
    assert '<option value="income">Income (0)</option>' in page
    assert "No “Income” entries in the log yet." in adm.get("/log?group=income").text


def test_admin_log_paging(adm, conn):
    from app import audit
    with conn:
        for i in range(130):
            audit.log(conn, None, "account.test", f"entry {i}", actor_name="Test")
    page = adm.get("/log").text
    assert "entry 129" in page and "entry 30" in page and "entry 29" not in page
    next_link = "/log?before=" + page.split('href="/log?before=')[1].split('"')[0]
    older = adm.get(next_link).text
    assert "entry 29" in older


def test_log_is_admin_only(app, client, admin_app):
    assert client.get("/log", follow_redirects=False).status_code in (200, 303)   # the app's own Log page
    assert "Activity log" not in client.get("/log").text
    assert _admin(admin_app).get("/log", follow_redirects=False).status_code == 303   # admin login required


def test_old_entries_are_pruned(conn):
    from app import audit
    conn.execute("INSERT INTO activity_log (actor_name, kind, detail, created_at) VALUES ('X', 'account.old', 'old', '2024-01-01T00:00:00Z')")
    conn.execute("INSERT INTO activity_log (actor_name, kind, detail, created_at) VALUES ('X', 'account.new', 'new', '2026-11-01T00:00:00Z')")
    assert audit.prune(conn, date(2026, 11, 4)) == 1
    assert [r[0] for r in conn.execute("SELECT detail FROM activity_log")] == ["new"]
