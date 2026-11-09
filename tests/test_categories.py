"""Categories page: add / edit / reorder / archive / delete, and every dependency case."""
import re

import pytest

from .conftest import category_id


def _post(client, url, **data):
    return client.post(url, data=data, follow_redirects=False)


def _budgets(conn, cid):
    return [tuple(r) for r in conn.execute(
        "SELECT effective_from, monthly_budget_cents FROM category_budgets "
        "WHERE category_id = ? ORDER BY effective_from", (cid,))]


def _expense(conn, cid, day="2026-11-01", amount=1000):
    conn.execute("INSERT INTO expenses (date, description, category_id, amount_cents) "
                 "VALUES (?, 'x', ?, ?)", (day, cid, amount))
    conn.commit()


def _count(conn, sql, *args):
    return conn.execute(sql, args).fetchone()[0]


def _alert(page):
    m = re.search(r'id="dlg-alert".*?<p>(.*?)</p>', page, re.S)
    return m.group(1) if m else None


def test_page_lists_categories_with_usage_and_dialogs(client, conn):
    _expense(conn, category_id(conn, "Dining out"), amount=1000)
    page = client.get("/categories").text
    assert "Transport" in page and "1 expense · €10.00 in total" in page
    assert 'id="dlg-add"' in page and "dlg-edit-" in page and "dlg-delete-" in page
    assert 'class="back-link" href="/settings"' in page   # reached via Settings


# --- add -------------------------------------------------------------------------

def test_add_with_and_without_budget(client, conn):
    r = _post(client, "/categories", name="  Books   and  comics ", budget="40", budget_from="2026-06-01")
    assert r.status_code == 303 and "done=added" in r.headers["location"]
    cid = category_id(conn, "Books and comics")          # whitespace tidied
    assert _budgets(conn, cid) == [("2026-06-01", 4000)]
    assert "Category “Books and comics” added." in client.get(r.headers["location"]).text
    _post(client, "/categories", name="Plain", budget="", budget_from="")
    assert _budgets(conn, category_id(conn, "Plain")) == []


@pytest.mark.parametrize("data, field", [
    ({"name": "", "budget": "", "budget_from": ""}, "Enter a name."),
    ({"name": "tRANSPORT", "budget": "", "budget_from": ""}, "“Transport” already exists."),
    ({"name": "x" * 51, "budget": "", "budget_from": ""}, "under 50 characters"),
    ({"name": "New", "budget": "abc", "budget_from": "2026-01-01"}, "Enter a number"),
    ({"name": "New", "budget": "10", "budget_from": "nope"}, "Enter a valid date."),
])
def test_add_errors_reopen_the_dialog(client, conn, data, field):
    r = client.post("/categories", data=data)
    assert r.status_code == 422
    assert field in r.text
    assert 'data-reopen="dlg-add"' in r.text
    assert _count(conn, "SELECT COUNT(*) FROM categories WHERE name = 'New'") == 0


# --- edit ------------------------------------------------------------------------

def test_edit_name_and_budget_together(client, conn):
    cid = category_id(conn, "Dining out")
    _expense(conn, cid)
    r = _post(client, f"/categories/{cid}/edit", name="Restaurants", budget="120", budget_from="2026-10-28")
    assert r.status_code == 303
    assert _count(conn, "SELECT name FROM categories WHERE id = ?", cid) == "Restaurants"
    assert _budgets(conn, cid) == [("2026-10-28", 12000)]
    assert _count(conn, "SELECT COUNT(*) FROM expenses WHERE category_id = ?", cid) == 1   # entries kept
    # blank budget = leave budgets alone
    _post(client, f"/categories/{cid}/edit", name="Restaurants", budget="", budget_from="2026-12-01")
    assert _budgets(conn, cid) == [("2026-10-28", 12000)]
    # same date again replaces the amount
    _post(client, f"/categories/{cid}/edit", name="Restaurants", budget="130", budget_from="2026-10-28")
    assert _budgets(conn, cid) == [("2026-10-28", 13000)]


def test_edit_rename_onto_existing_name_suggests_merge(client, conn):
    cid = category_id(conn, "Dining out")
    r = client.post(f"/categories/{cid}/edit", data={"name": "entertainment", "budget": "", "budget_from": ""})
    assert r.status_code == 422
    assert "delete this category" in r.text and "Move its expenses" in r.text
    assert f'data-reopen="dlg-edit-{cid}"' in r.text
    assert _count(conn, "SELECT name FROM categories WHERE id = ?", cid) == "Dining out"


def test_edit_failure_is_atomic(client, conn):
    """A bad budget must not leave a half-applied rename behind."""
    cid = category_id(conn, "Dining out")
    r = client.post(f"/categories/{cid}/edit", data={"name": "Food", "budget": "x", "budget_from": "2026-01-01"})
    assert r.status_code == 422
    assert _count(conn, "SELECT name FROM categories WHERE id = ?", cid) == "Dining out"


def test_stale_category_shows_error_popup(client):
    r = client.post("/categories/9999/edit", data={"name": "X", "budget": "", "budget_from": ""})
    assert r.status_code == 404 and "no longer exists" in _alert(r.text)
    for action in ("archive", "delete"):
        r = client.post(f"/categories/9999/{action}", data={"expected": "0"})
        assert "no longer exists" in _alert(r.text)
    r = client.post("/categories/9999/move", data={"direction": "up"})
    assert "no longer exists" in _alert(r.text)


# --- reorder / archive ----------------------------------------------------------------

def test_reorder(client, conn):
    first, second = [r[0] for r in conn.execute("SELECT id FROM categories ORDER BY sort_order LIMIT 2")]
    _post(client, f"/categories/{second}/move", direction="up")
    assert [r[0] for r in conn.execute("SELECT id FROM categories ORDER BY sort_order LIMIT 2")] == [second, first]
    _post(client, f"/categories/{second}/move", direction="up")   # already first: no-op
    assert _count(conn, "SELECT id FROM categories ORDER BY sort_order LIMIT 1") == second


def test_archive_toggle_hides_from_add_form(client, conn):
    cid = category_id(conn, "Travel")
    assert "done=archived" in _post(client, f"/categories/{cid}/archive").headers["location"]
    assert "Travel" not in client.get("/add").text
    assert "done=unarchived" in _post(client, f"/categories/{cid}/archive").headers["location"]
    assert "Travel" in client.get("/add").text


def _leave_only(conn, keep):
    conn.execute("UPDATE categories SET archived = 1 WHERE name != ?", (keep,))
    conn.commit()
    return category_id(conn, keep)


def test_cannot_archive_last_active_category(client, conn):
    cid = _leave_only(conn, "Other")
    r = client.post(f"/categories/{cid}/archive")
    assert r.status_code == 409 and "only active category" in _alert(r.text)
    assert _count(conn, "SELECT archived FROM categories WHERE id = ?", cid) == 0


# --- delete ----------------------------------------------------------------------

def test_delete_unused_category_drops_its_budget_history(client, conn):
    cid = category_id(conn, "Gifts")
    _post(client, f"/categories/{cid}/edit", name="Gifts", budget="20", budget_from="2026-01-01")
    r = _post(client, f"/categories/{cid}/delete", expected="0")
    assert r.status_code == 303 and "done=deleted" in r.headers["location"]
    assert _count(conn, "SELECT COUNT(*) FROM categories WHERE id = ?", cid) == 0
    assert _budgets(conn, cid) == []


def test_delete_with_expenses_needs_a_choice(client, conn):
    cid = category_id(conn, "Travel")
    _expense(conn, cid)
    r = client.post(f"/categories/{cid}/delete", data={"expected": "1"})
    assert r.status_code == 422 and "Choose what happens" in r.text
    assert _count(conn, "SELECT COUNT(*) FROM categories WHERE id = ?", cid) == 1


def test_delete_by_moving_expenses_merges_categories(client, conn):
    src, dst = category_id(conn, "Dining out"), category_id(conn, "Entertainment")
    _post(client, f"/categories/{src}/edit", name="Dining out", budget="50", budget_from="2026-01-01")
    _expense(conn, src, "2026-10-30", 1500)
    _expense(conn, src, "2026-11-02", 1000)
    _expense(conn, dst, "2026-11-03", 700)
    before = client.get("/month?period=2026-11").text
    assert "€32.00" in before                       # total my cost: 15 + 10 + 7

    r = _post(client, f"/categories/{src}/delete", expected="2", action="move", target=str(dst))
    assert r.status_code == 303 and "done=moved" in r.headers["location"]
    assert "2 expenses moved to “Entertainment”" in client.get(r.headers["location"]).text
    assert _count(conn, "SELECT COUNT(*) FROM categories WHERE id = ?", src) == 0
    assert _count(conn, "SELECT COUNT(*) FROM expenses WHERE category_id = ?", dst) == 3
    assert _budgets(conn, src) == []
    after = client.get("/month?period=2026-11").text
    assert "€32.00" in after                        # totals unchanged by a merge


def test_move_needs_a_valid_other_target(client, conn):
    cid = category_id(conn, "Dining out")
    _expense(conn, cid)
    for target in ("", str(cid), "9999"):
        r = client.post(f"/categories/{cid}/delete", data={"expected": "1", "action": "move", "target": target})
        assert r.status_code == 422 and "Choose where the expenses should go." in r.text
    assert _count(conn, "SELECT COUNT(*) FROM expenses WHERE category_id = ?", cid) == 1


def test_move_into_archived_category_is_allowed(client, conn):
    src, dst = category_id(conn, "Shopping"), category_id(conn, "Other")
    conn.execute("UPDATE categories SET archived = 1 WHERE id = ?", (dst,))
    _expense(conn, src)
    r = _post(client, f"/categories/{src}/delete", expected="1", action="move", target=str(dst))
    assert r.status_code == 303
    assert _count(conn, "SELECT COUNT(*) FROM expenses WHERE category_id = ?", dst) == 1


def test_delete_expenses_too_requires_typing_the_name(client, conn):
    cid = category_id(conn, "Subscriptions")
    _expense(conn, cid)
    _expense(conn, cid)
    r = client.post(f"/categories/{cid}/delete", data={"expected": "2", "action": "delete_entries", "confirm": "subs"})
    assert r.status_code == 422 and "exactly to confirm" in r.text
    assert _count(conn, "SELECT COUNT(*) FROM expenses") == 2

    r = _post(client, f"/categories/{cid}/delete", expected="2", action="delete_entries", confirm=" subscriptions ")
    assert r.status_code == 303 and "done=purged" in r.headers["location"]
    assert _count(conn, "SELECT COUNT(*) FROM expenses") == 0
    assert _count(conn, "SELECT COUNT(*) FROM categories WHERE id = ?", cid) == 0


def test_delete_refused_if_entries_changed_since_dialog_opened(client, conn):
    cid = category_id(conn, "Gifts")
    _expense(conn, cid)
    # dialog was opened when the category had 0 entries; one was added in another tab since
    r = client.post(f"/categories/{cid}/delete", data={"expected": "0"})
    assert r.status_code == 409 and "changed since you opened" in _alert(r.text)
    assert _count(conn, "SELECT COUNT(*) FROM categories WHERE id = ?", cid) == 1
    assert _count(conn, "SELECT COUNT(*) FROM expenses") == 1


def test_cannot_delete_last_active_category(client, conn):
    cid = _leave_only(conn, "Other")
    page = client.get("/categories").text
    assert "This is your only active category" in page            # dialog explains up front
    r = client.post(f"/categories/{cid}/delete", data={"expected": "0"})
    assert r.status_code == 409 and "only active category" in _alert(r.text)
    assert _count(conn, "SELECT COUNT(*) FROM categories WHERE id = ?", cid) == 1


def test_archived_category_can_be_deleted_even_if_one_active_left(client, conn):
    keep = _leave_only(conn, "Other")
    archived = category_id(conn, "Travel")
    r = _post(client, f"/categories/{archived}/delete", expected="0")
    assert r.status_code == 303
    assert _count(conn, "SELECT COUNT(*) FROM categories WHERE id = ?", keep) == 1


def test_expense_edit_page_survives_category_merge(client, conn):
    src, dst = category_id(conn, "Dining out"), category_id(conn, "Entertainment")
    _expense(conn, src)
    eid = _count(conn, "SELECT id FROM expenses")
    _post(client, f"/categories/{src}/delete", expected="1", action="move", target=str(dst))
    page = client.get(f"/expenses/{eid}/edit").text
    assert f'<option value="{dst}" selected>' in page


def test_message_text_cannot_be_injected(client):
    page = client.get("/categories?done=evil&name=<script>").text
    assert "<script>" not in page.split("<main>")[1].split("</main>")[0]
    page = client.get("/categories?done=added&name=<b>x</b>").text
    assert "&lt;b&gt;x&lt;/b&gt;" in page


# --- editing budget history entries ----------------------------------------------------

def _budget_id(conn, cid, day):
    return conn.execute("SELECT id FROM category_budgets WHERE category_id = ? AND effective_from = ?",
                        (cid, day)).fetchone()[0]


def _two_budgets(client, cid):
    _post(client, f"/categories/{cid}/edit", name="Groceries", budget="300", budget_from="2026-01-01")
    _post(client, f"/categories/{cid}/edit", name="Groceries", budget="350", budget_from="2026-10-28")


def test_budget_history_has_edit_and_delete(client, conn):
    cid = category_id(conn, "Groceries")
    _two_budgets(client, cid)
    bid = _budget_id(conn, cid, "2026-10-28")
    page = client.get("/categories").text
    assert f'data-open="dlg-budget-edit-{bid}"' in page and f'id="dlg-budget-delete-{bid}"' in page
    assert "use <strong>€300.00</strong> (from 1 Jan 2026) instead" in page
    assert "have <strong>no budget (€0)</strong>" in page
    assert "until 28 Oct 2026 when €350.00 starts" in page


def test_edit_budget_entry_amount_and_date(client, conn):
    cid = category_id(conn, "Groceries")
    _two_budgets(client, cid)
    bid = _budget_id(conn, cid, "2026-10-28")
    r = _post(client, f"/categories/{cid}/budgets/{bid}/edit", budget="400,50", budget_from="2026-11-28")
    assert r.status_code == 303 and "done=budget_edited" in r.headers["location"]
    assert "Budget of “Groceries” updated." in client.get(r.headers["location"]).text
    assert _budgets(conn, cid) == [("2026-01-01", 30000), ("2026-11-28", 40050)]
    # S = 28: November now uses 300, December the edited 400.50
    assert "€300.00" in client.get("/month?period=2026-11").text
    assert "€400.50" in client.get("/month?period=2026-12").text


def test_edit_budget_entry_to_zero_is_allowed(client, conn):
    cid = category_id(conn, "Groceries")
    _two_budgets(client, cid)
    bid = _budget_id(conn, cid, "2026-10-28")
    _post(client, f"/categories/{cid}/budgets/{bid}/edit", budget="0", budget_from="2026-10-28")
    assert _budgets(conn, cid)[1] == ("2026-10-28", 0)


@pytest.mark.parametrize("budget, day, message", [
    ("", "2026-10-28", "Enter an amount (0 for no budget)."),
    ("abc", "2026-10-28", "Enter a number"),
    ("10", "nope", "Enter a valid date."),
    ("10", "2026-01-01", "already has a budget starting on that date"),
])
def test_edit_budget_entry_errors_reopen_its_dialog(client, conn, budget, day, message):
    cid = category_id(conn, "Groceries")
    _two_budgets(client, cid)
    bid = _budget_id(conn, cid, "2026-10-28")
    r = client.post(f"/categories/{cid}/budgets/{bid}/edit", data={"budget": budget, "budget_from": day})
    assert r.status_code == 422 and message in r.text
    assert f'data-reopen="dlg-budget-edit-{bid}"' in r.text
    assert _budgets(conn, cid) == [("2026-01-01", 30000), ("2026-10-28", 35000)]


def test_delete_budget_entry(client, conn):
    cid = category_id(conn, "Groceries")
    _two_budgets(client, cid)
    bid = _budget_id(conn, cid, "2026-10-28")
    r = _post(client, f"/categories/{cid}/budgets/{bid}/delete")
    assert "done=budget_deleted" in r.headers["location"]
    assert _budgets(conn, cid) == [("2026-01-01", 30000)]
    assert "€300.00" in client.get("/month?period=2026-11").text


def test_budget_entry_of_other_category_or_user_is_refused(client, app, conn, uid):
    from .conftest import browser, login, make_user
    cid, other = category_id(conn, "Groceries"), category_id(conn, "Housing")
    _two_budgets(client, cid)
    bid = _budget_id(conn, cid, "2026-01-01")
    # right budget id, wrong category in the URL
    r = client.post(f"/categories/{other}/budgets/{bid}/delete")
    assert r.status_code == 404 and "no longer exists" in _alert(r.text)
    # someone else
    make_user(conn, "bob")
    bob = login(browser(app), "bob")
    for action, data in (("edit", {"budget": "1", "budget_from": "2026-01-01"}), ("delete", {})):
        r = bob.post(f"/categories/{cid}/budgets/{bid}/{action}", data=data)
        assert r.status_code == 404 and "no longer exists" in _alert(r.text)
    assert _budgets(conn, cid) == [("2026-01-01", 30000), ("2026-10-28", 35000)]


# --- total budget card ----------------------------------------------------------------
# S = 28 and "today" = 2026-11-04 -> current period November 2026 (28 Oct – 27 Nov).

def _card(page):
    return page.split('class="budget-total"')[1].split("</section>")[0]


@pytest.fixture
def nov(monkeypatch):
    from datetime import date
    monkeypatch.setattr("app.config.today", lambda: date(2026, 11, 4))


def test_total_budget_card(client, conn, uid, nov):
    """Budgets: Groceries 300, Housing 900, Travel 100 (archived -> excluded) = 1,200.00
    Income 2,000.00 -> 60 % budgeted, 800.00 not budgeted.
    Spent in Nov: Groceries 150 (+ Travel 50, archived, not counted) -> 150 of 1,200 = 13 %."""
    for name, amount in (("Groceries", "300"), ("Housing", "900"), ("Travel", "100")):
        _post(client, f"/categories/{category_id(conn, name)}/edit", name=name, budget=amount, budget_from="2026-01-01")
    _post(client, "/profile/regular-income", income_amount="2000", income_from="2026-01-01")
    _expense(conn, category_id(conn, "Groceries"), "2026-11-01", 15000)
    _expense(conn, category_id(conn, "Travel"), "2026-11-02", 5000)
    conn.execute("UPDATE categories SET archived = 1 WHERE name = 'Travel'")
    conn.commit()
    card = _card(client.get("/categories").text)
    assert "Total budget · November 2026" in card and "€1,200.00" in card
    assert "2 of 11 active categories have a budget" in card
    assert "60% of €2,000.00" in card and "€800.00 of your income is not budgeted." in card
    assert "€150.00 · 12%" in card or "€150.00 · 13%" in card
    assert "€1,050.00 left in your budgets" in card


def test_total_budget_card_without_income_or_budgets(client, nov):
    card = _card(client.get("/categories").text)
    assert "€0.00" in card and "no regular income set" in card and 'href="/settings#income"' in card
    assert "0 of 12 active categories" in card


def test_total_budget_card_warns_when_budgets_exceed_income(client, conn, nov):
    _post(client, f"/categories/{category_id(conn, 'Housing')}/edit", name="Housing", budget="2500", budget_from="2026-01-01")
    _post(client, "/profile/regular-income", income_amount="2000", income_from="2026-01-01")
    card = _card(client.get("/categories").text)
    assert "Budgets exceed your income by €500.00." in card
    assert 'class="red-text">125% of €2,000.00' in card


def test_total_budget_card_overspent(client, conn, nov):
    cid = category_id(conn, "Groceries")
    _post(client, f"/categories/{cid}/edit", name="Groceries", budget="100", budget_from="2026-01-01")
    _expense(conn, cid, "2026-11-01", 12000)
    card = _card(client.get("/categories").text)
    assert "Over budget by €20.00" in card and 'class="red-text">€120.00 · 120%' in card


def test_total_budget_uses_budget_in_effect_this_period(client, conn, nov):
    cid = category_id(conn, "Groceries")
    _post(client, f"/categories/{cid}/edit", name="Groceries", budget="100", budget_from="2026-01-01")
    _post(client, f"/categories/{cid}/edit", name="Groceries", budget="999", budget_from="2026-11-28")  # December
    assert "€100.00" in _card(client.get("/categories").text)
