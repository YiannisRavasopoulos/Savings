import pytest

from app import forms
from app.money import cents_to_input, format_eur, parse_amount

from .conftest import category_id


# --- money parsing / formatting -------------------------------------------------

@pytest.mark.parametrize("text, cents", [
    ("12", 1200), ("12.5", 1250), ("12.50", 1250), ("12,50", 1250), ("0.01", 1),
    (",5", 50), ("€ 7", 700), ("1,234.56", 123456), ("1.234,56", 123456), ("0", 0),
    ("19.99", 1999), ("0.29", 29),  # values that are inexact as binary floats
])
def test_parse_amount(text, cents):
    assert parse_amount(text) == cents


@pytest.mark.parametrize("text", ["", "abc", "-5", "1.234", "12.345", "1e3", "12..5", ".", "1,2,3"])
def test_parse_amount_rejects(text):
    with pytest.raises(ValueError):
        parse_amount(text)


def test_format_eur():
    assert format_eur(123456) == "€1,234.56"
    assert format_eur(5) == "€0.05"
    assert format_eur(0) == "€0.00"
    assert format_eur(-1250) == "-€12.50"
    assert format_eur(None) == ""
    assert cents_to_input(1250) == "12.50"


# --- expense validation -------------------------------------------------------------

def _form(**kw):
    base = {"date": "2026-11-04", "description": "Coffee", "category_id": "1",
            "amount": "10.00", "notes": ""}
    base.update(kw)
    return base


def test_valid_expense():
    clean, errors, _ = forms.validate_expense(_form(), {1})
    assert errors == {}
    assert clean["amount_cents"] == 1000 and "their_part_cents" not in clean


@pytest.mark.parametrize("field, value", [
    ("date", ""), ("date", "2026-13-01"), ("description", ""), ("category_id", "99"),
    ("category_id", ""), ("amount", ""), ("amount", "0"), ("amount", "-3"),
])
def test_expense_field_errors(field, value):
    _, errors, raw = forms.validate_expense(_form(**{field: value}), {1})
    assert field in errors
    assert raw[field] == value  # the form is re-shown with what was typed


# --- through the web form ---------------------------------------------------------------

def test_add_page_renders(client):
    r = client.get("/add")
    assert r.status_code == 200
    assert "Add expense" in r.text and "Transport" in r.text


def test_add_expense_then_my_cost_in_log(client, conn):
    cid = category_id(conn, "Dining out")
    r = client.post("/add", data=_form(category_id=str(cid), amount="17,50",
                                    description="Pizza", date="2026-11-04"),
                    follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/add?saved=1&date=2026-11-04&amt=1750"

    page = client.get(r.headers["location"]).text
    assert "Saved." in page
    assert 'value="2026-11-04"' in page          # last-used date kept
    assert 'value="Pizza"' not in page           # rest of the form is empty

    assert conn.execute("SELECT amount_cents FROM expenses").fetchone()[0] == 1750

    log = client.get("/log?period=2026-11").text
    assert "€17.50" in log
    assert "Their part" not in log and "Their part" not in client.get("/add").text
    assert "Pizza" in log


def test_add_expense_inline_error(client, conn):
    r = client.post("/add", data=_form(amount="abc"))
    assert r.status_code == 422
    assert "Enter a number like 12.50" in r.text
    assert conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 0


def test_archived_category_not_offered_or_accepted(client, conn):
    cid = category_id(conn, "Shopping")
    conn.execute("UPDATE categories SET archived = 1 WHERE id = ?", (cid,))
    conn.commit()
    assert "Shopping" not in client.get("/add").text
    r = client.post("/add", data=_form(category_id=str(cid)))
    assert r.status_code == 422


def test_edit_and_delete_expense(client, conn):
    client.post("/add", data=_form(date="2026-11-04"))
    eid = conn.execute("SELECT id FROM expenses").fetchone()[0]
    assert client.get(f"/expenses/{eid}/edit").status_code == 200
    r = client.post(f"/expenses/{eid}/edit", data=_form(date="2026-11-28", amount="20"),
                    follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/log?period=2026-12"  # 28 Nov is in December's period
    assert conn.execute("SELECT amount_cents FROM expenses").fetchone()[0] == 2000
    r = client.post(f"/expenses/{eid}/delete", follow_redirects=False)
    assert r.status_code == 303
    assert conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 0
    assert client.get(f"/expenses/{eid}/edit").status_code == 404


def test_log_filters_by_period_and_category(client, conn):
    a, b = category_id(conn, "Entertainment"), category_id(conn, "Gifts")
    client.post("/add", data=_form(category_id=str(a), description="InPeriod", date="2026-10-28"))
    client.post("/add", data=_form(category_id=str(b), description="OtherCat", date="2026-11-27"))
    client.post("/add", data=_form(category_id=str(a), description="NextPeriod", date="2026-11-28"))
    page = client.get(f"/log?period=2026-11&category={a}").text
    assert "InPeriod" in page and "OtherCat" not in page and "NextPeriod" not in page
    page = client.get("/log?year=2026&month=11").text
    assert "InPeriod" in page and "OtherCat" in page and "NextPeriod" not in page
    assert "28 Oct – 27 Nov 2026" in page


# --- extra income -----------------------------------------------------------------------

def test_extra_income_crud(client, conn):
    data = {"date": "2026-11-02", "description": "Sold cards", "amount": "45,5", "notes": ""}
    r = client.post("/income", data=data, follow_redirects=False)
    assert r.status_code == 303
    page = client.get(r.headers["location"]).text
    assert "Saved." in page and "€45.50" in page
    iid = conn.execute("SELECT id FROM extra_income").fetchone()[0]
    r = client.post(f"/income/{iid}/edit", data={**data, "amount": "50"}, follow_redirects=False)
    assert r.status_code == 303
    assert conn.execute("SELECT amount_cents FROM extra_income").fetchone()[0] == 5000
    client.post(f"/income/{iid}/delete")
    assert conn.execute("SELECT COUNT(*) FROM extra_income").fetchone()[0] == 0


def test_extra_income_validation(client):
    r = client.post("/income", data={"date": "x", "description": "", "amount": "0", "notes": ""})
    assert r.status_code == 422
    assert r.text.count('class="error"') == 3
