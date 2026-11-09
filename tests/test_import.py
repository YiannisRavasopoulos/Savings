"""CSV import: preview first (nothing saved), then import."""
import re

import pytest

from app import importer

from .conftest import browser, category_id, login, make_user


def _preview(client, text, filename="x.csv", **opts):
    return client.post("/import/preview", files={"file": (filename, text.encode(), "text/csv")},
                       data={k: v for k, v in opts.items()})


def _confirm(client, text, **opts):
    return client.post("/import/confirm", data={"csv_text": text, **opts}, follow_redirects=False)


def _expenses(conn):
    return [tuple(r) for r in conn.execute(
        "SELECT e.date, e.description, c.name, e.amount_cents, e.notes, e.one_off FROM expenses e "
        "JOIN categories c ON c.id = e.category_id ORDER BY e.date, e.id")]


SIMPLE = """date,description,category,amount,notes
2026-10-03,Groceries,groceries,54.20,
05/10/2026,Train ticket,Transport,"12,50",work trip
"""


def test_preview_saves_nothing_then_import(client, conn):
    page = _preview(client, SIMPLE).text
    assert "<strong>2</strong> ready" in page and "Preview: x.csv" in page
    assert _expenses(conn) == []
    r = _confirm(client, SIMPLE)
    assert r.headers["location"] == "/import?done=1&n=2"
    assert _expenses(conn) == [("2026-10-03", "Groceries", "Groceries", 5420, "", 0),
                               ("2026-10-05", "Train ticket", "Transport", 1250, "work trip", 0)]
    assert "Imported 2 expenses" in client.get("/import?done=1&n=2").text
    detail = conn.execute("SELECT detail FROM activity_log WHERE kind = 'expense.imported'").fetchone()[0]
    assert detail == "Imported 2 expenses from a CSV file (dated 2026-10-03 to 2026-10-05)"


def test_semicolons_and_aliases_and_bank_negatives(client, conn):
    text = "Booking date;Payee;Value;Memo\n03.10.2026;Supermarket;-23,10;card\n04.10.2026;Salary;2000,00;\n"
    page = _preview(client, text, default_category_id=str(category_id(conn, "Groceries"))).text
    assert "looks like a bank export" in page and "Money in (positive amount)" in page
    _confirm(client, text, default_category_id=str(category_id(conn, "Groceries")))
    assert _expenses(conn) == [("2026-10-03", "Supermarket", "Groceries", 2310, "card", 0)]


def test_rows_without_category_need_a_default(client, conn):
    text = "date,amount\n2026-10-03,5\n"
    page = _preview(client, text).text
    assert "No category. Pick one" in page and "<strong>0</strong> ready" in page
    r = _confirm(client, text)
    assert r.status_code == 422 and "Nothing to import" in r.text
    assert _expenses(conn) == []


def test_unknown_category_and_create_missing(client, conn):
    text = "date,description,category,amount\n2026-10-03,Vet,Pets,40\n2026-10-04,Food,pets,10\n"
    assert "No category called “Pets”" in _preview(client, text).text
    page = _preview(client, text, create_missing="1").text
    assert 'New categories to create: <span class="tag">Pets</span>' in page
    _confirm(client, text, create_missing="1")
    assert [e[2] for e in _expenses(conn)] == ["Pets", "Pets"]
    assert conn.execute("SELECT COUNT(*) FROM categories WHERE name = 'Pets'").fetchone()[0] == 1


def test_duplicates_skipped_unless_asked(client, conn):
    _confirm(client, SIMPLE)
    page = _preview(client, SIMPLE).text
    assert "<strong>2</strong> possible duplicates" in page and "<strong>0</strong> ready" in page
    assert _confirm(client, SIMPLE).status_code == 422
    _confirm(client, SIMPLE, include_duplicates="1")
    assert len(_expenses(conn)) == 4


def test_row_errors_are_reported_and_left_out(client, conn):
    text = ("date,description,category,amount\n"
            "2026-13-01,Bad date,Groceries,5\n"
            "2026-10-01,Bad amount,Groceries,abc\n"
            "2026-10-02,Zero,Groceries,0\n"
            "2026-10-03,Fine,Groceries,7.5\n")
    page = _preview(client, text).text
    assert "isn&#39;t a date" in page and "Amount: " in page and "Amount is zero." in page
    assert "<strong>1</strong> ready" in page
    _confirm(client, text)
    assert _expenses(conn) == [("2026-10-03", "Fine", "Groceries", 750, "", 0)]


def test_own_export_round_trips(client, conn):
    _confirm(client, SIMPLE)
    import io
    import zipfile
    data = zipfile.ZipFile(io.BytesIO(client.get("/export.zip").content)).read("expenses.csv").decode("utf-8-sig")
    conn.execute("DELETE FROM expenses")
    conn.commit()
    assert "<strong>2</strong> ready" in _preview(client, data).text
    _confirm(client, data)
    assert [e[:4] for e in _expenses(conn)] == [("2026-10-03", "Groceries", "Groceries", 5420),
                                                ("2026-10-05", "Train ticket", "Transport", 1250)]


@pytest.mark.parametrize("text, message", [
    ("", "The file is empty."),
    ("description,amount\nx,1\n", "No “date” column found"),
    ("date,description\n2026-01-01,x\n", "No “amount” column found"),
    ("date,amount\n", "header row but no expenses"),
])
def test_whole_file_errors(client, text, message):
    r = _preview(client, text)
    assert r.status_code == 422 and message in r.text


def test_too_many_rows(client, monkeypatch):
    monkeypatch.setattr(importer, "MAX_ROWS", 3)
    r = _preview(client, "date,amount\n" + "2026-01-01,1\n" * 4)
    assert r.status_code == 422 and "more than 3 rows" in r.text


def test_cp1252_file(client, conn):
    text = "date,description,category,amount\n2026-10-03,Café,Groceries,3\n"
    client.post("/import/preview", files={"file": ("x.csv", text.encode("cp1252"), "text/csv")})
    _confirm(client, text)
    assert _expenses(conn)[0][1] == "Café"


def test_update_preview_reuses_text(client, conn):
    text = "date,description,amount\n2026-10-03,Thing,5\n"
    page = client.post("/import/preview", data={"csv_text": text, "filename": "x.csv",
                                                "default_category_id": str(category_id(conn, "Other"))}).text
    assert "<strong>1</strong> ready" in page
    assert re.search(r'<textarea name="csv_text" hidden>date,description,amount', page)


def test_import_only_into_own_categories(app, client, conn):
    make_user(conn, "bob")
    bob = login(browser(app), "bob")
    text = "date,description,category,amount\n2026-10-03,X,Groceries,5\n"
    _confirm(bob, text)
    owner = conn.execute("SELECT c.user_id FROM expenses e JOIN categories c ON c.id = e.category_id").fetchone()[0]
    assert owner == conn.execute("SELECT id FROM users WHERE username = 'bob'").fetchone()[0]


def test_settings_links_to_import(client):
    assert 'href="/import"' in client.get("/settings").text
