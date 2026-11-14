import pytest

from app import summary


def _post(client, url, **data):
    return client.post(url, data=data, follow_redirects=False)


def test_settings_page_has_the_profile_sections(client):
    page = client.get("/settings").text
    assert "My pay for a month arrives on" in page and 'href="/categories"' in page and "/export.zip" in page
    assert "alice" in page and "this device" in page
    assert client.get("/profile", follow_redirects=False).headers["location"] == "/settings"


def test_start_day(client, conn, uid):
    assert _post(client, "/profile/start-day", payday="25").status_code == 303
    assert summary.get_start_day(conn, uid) == 25
    for bad in ("0", "32", "x", ""):
        r = _post(client, "/profile/start-day", payday=bad)
        assert r.status_code == 422 and "Enter a day from 1 to 31." in r.text
    assert summary.get_start_day(conn, uid) == 25


def test_regular_income_history(client, conn, uid):
    _post(client, "/profile/regular-income", income_amount="2000", income_from="2026-01-01")
    _post(client, "/profile/regular-income", income_amount="2100", income_from="2026-06-01")
    _post(client, "/profile/regular-income", income_amount="2150", income_from="2026-06-01")  # fix typo
    rows = conn.execute("SELECT effective_from, amount_cents FROM regular_income WHERE user_id = ? ORDER BY 1", (uid,)).fetchall()
    assert [tuple(r) for r in rows] == [("2026-01-01", 200000), ("2026-06-01", 215000)]
    r = _post(client, "/profile/regular-income", income_amount="abc", income_from="")
    assert r.status_code == 422 and r.text.count('class="error"') == 2


# --- regular income: edit / delete ----------------------------------------------------

def _incomes(conn, uid):
    return [tuple(r) for r in conn.execute(
        "SELECT effective_from, amount_cents FROM regular_income WHERE user_id = ? ORDER BY 1", (uid,))]


def _income_id(conn, uid, day):
    return conn.execute("SELECT id FROM regular_income WHERE user_id = ? AND effective_from = ?",
                        (uid, day)).fetchone()[0]


def _setup_incomes(client):
    _post(client, "/profile/regular-income", income_amount="2000", income_from="2026-01-01")
    _post(client, "/profile/regular-income", income_amount="2200", income_from="2026-10-28")


def test_edit_income_amount_and_date(client, conn, uid):
    _setup_incomes(client)
    iid = _income_id(conn, uid, "2026-10-28")
    page = client.get("/settings").text
    assert f'data-open="dlg-income-edit-{iid}"' in page and f'id="dlg-income-delete-{iid}"' in page
    r = _post(client, f"/profile/regular-income/{iid}/edit", income_amount="2250,50", income_from="2026-11-28")
    assert r.headers["location"] == "/settings?income=edited#income"
    assert _incomes(conn, uid) == [("2026-01-01", 200000), ("2026-11-28", 225050)]
    assert "Income amount updated." in client.get("/settings?income=edited").text
    # S = 28: November (28 Oct–27 Nov) now falls back to 2000, December gets the new amount
    assert "€2,000.00" in client.get("/month?period=2026-11").text
    assert "€2,250.50" in client.get("/month?period=2026-12").text


def test_edit_income_onto_existing_date_is_refused(client, conn, uid):
    _setup_incomes(client)
    iid = _income_id(conn, uid, "2026-10-28")
    r = client.post(f"/profile/regular-income/{iid}/edit", data={"income_amount": "1", "income_from": "2026-01-01"})
    assert r.status_code == 422 and "already an amount starting on that date" in r.text
    assert f'data-reopen="dlg-income-edit-{iid}"' in r.text
    assert _incomes(conn, uid) == [("2026-01-01", 200000), ("2026-10-28", 220000)]


@pytest.mark.parametrize("amount, day, message", [("", "2026-01-01", "Enter an amount."),
                                                  ("abc", "2026-01-01", "Enter a number"),
                                                  ("10", "nope", "Enter a valid date.")])
def test_edit_income_validation(client, conn, uid, amount, day, message):
    _setup_incomes(client)
    iid = _income_id(conn, uid, "2026-10-28")
    r = client.post(f"/profile/regular-income/{iid}/edit", data={"income_amount": amount, "income_from": day})
    assert r.status_code == 422 and message in r.text
    assert _incomes(conn, uid)[1] == ("2026-10-28", 220000)


def test_edit_keeps_same_date(client, conn, uid):
    _setup_incomes(client)
    iid = _income_id(conn, uid, "2026-10-28")
    _post(client, f"/profile/regular-income/{iid}/edit", income_amount="2300", income_from="2026-10-28")
    assert _incomes(conn, uid)[1] == ("2026-10-28", 230000)


def test_delete_income_explains_the_effect(client, conn, uid):
    _setup_incomes(client)
    page = client.get("/settings").text
    assert "use <strong>€2,000.00</strong> (from 1 Jan 2026) instead" in page     # deleting the newer one
    assert "have <strong>no regular income (€0)</strong>" in page                  # deleting the oldest one
    assert "until 28 Oct 2026 when €2,200.00 starts" in page
    iid = _income_id(conn, uid, "2026-10-28")
    r = _post(client, f"/profile/regular-income/{iid}/delete")
    assert r.headers["location"] == "/settings?income=deleted#income"
    assert _incomes(conn, uid) == [("2026-01-01", 200000)]
    assert "€2,000.00" in client.get("/month?period=2026-11").text


def test_income_of_another_user_or_deleted_shows_error_popup(client, app, conn, uid):
    from .conftest import browser, login, make_user
    _setup_incomes(client)
    iid = _income_id(conn, uid, "2026-01-01")
    make_user(conn, "bob")
    bob = login(browser(app), "bob")
    for url, data in ((f"/profile/regular-income/{iid}/edit", {"income_amount": "1", "income_from": "2026-01-01"}),
                      (f"/profile/regular-income/{iid}/delete", {})):
        r = bob.post(url, data=data)
        assert r.status_code == 404 and "no longer exists" in r.text and 'id="dlg-alert"' in r.text
    assert _incomes(conn, uid)[0] == ("2026-01-01", 200000)
    assert "€2,000.00" not in bob.get("/settings").text
