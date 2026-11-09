import csv
import io
import zipfile

from app import db, export

from .conftest import add_budget, category_id, make_user


def _read_zip(data: bytes) -> dict[str, list[dict]]:
    out = {}
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            text = zf.read(name).decode("utf-8-sig")
            out[name] = list(csv.DictReader(io.StringIO(text)))
    return out


def test_export_round_trip(client, conn, uid):
    eat = category_id(conn, "Dining out")
    conn.execute(
        "INSERT INTO expenses (date, description, category_id, amount_cents, notes) "
        "VALUES ('2026-11-03', 'Souvlaki, \"extra\" pita', ?, 1250, 'line1\nline2 €')", (eat,))
    conn.execute("INSERT INTO expenses (date, description, category_id, amount_cents) "
                 "VALUES ('2026-11-04', 'Ψωμί', ?, 120)", (eat,))
    conn.execute("INSERT INTO extra_income (user_id, date, description, amount_cents) VALUES (?, '2026-11-01', 'Refund', 2500)", (uid,))
    conn.execute("INSERT INTO regular_income (user_id, amount_cents, effective_from) VALUES (?, 210000, '2026-01-01')", (uid,))
    # Someone else's data must never appear in alice's download.
    bob = make_user(conn, "bob")
    conn.execute("INSERT INTO expenses (date, description, category_id, amount_cents) VALUES ('2026-11-04', 'BOBS', ?, 999)",
                 (category_id(conn, "Dining out", bob),))
    conn.execute("INSERT INTO extra_income (user_id, date, description, amount_cents) VALUES (?, '2026-11-01', 'BOBS', 1)", (bob,))
    add_budget(conn, eat, 8000, "2026-01-01")
    add_budget(conn, eat, 9000, "2026-11-28")
    conn.commit()

    r = client.get("/export.zip")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert "spending-export-" in r.headers["content-disposition"]

    tables = _read_zip(r.content)
    assert sorted(tables) == ["categories.csv", "category_budgets.csv", "expenses.csv",
                              "extra_income.csv", "recurring_expenses.csv", "regular_income.csv"]   # no users.csv for a user

    exp = tables["expenses.csv"]
    assert [e["description"] for e in exp] == ['Souvlaki, "extra" pita', "Ψωμί"]
    assert exp[0]["notes"] == "line1\nline2 €"
    assert (exp[0]["category"], exp[0]["amount_cents"], exp[0]["my_cost_cents"], exp[0]["paid_by_me"]) == \
           ("Dining out", "1250", "1250", "1")
    assert exp[1]["my_cost_cents"] == "120" and "their_part_cents" not in exp[0]

    # Every row of every table matches the database exactly.
    for name, sql, args in export.queries(uid):
        db_rows = [{k: "" if v is None else str(v) for k, v in dict(row).items()}
                   for row in conn.execute(sql, args)]
        assert tables[f"{name}.csv"] == db_rows, name

    assert len(tables["categories.csv"]) == len(db.DEFAULT_CATEGORIES)
    assert [(b["category"], b["monthly_budget_cents"], b["effective_from"]) for b in tables["category_budgets.csv"]] == \
           [("Dining out", "8000", "2026-01-01"), ("Dining out", "9000", "2026-11-28")]


def test_full_export_covers_everyone_without_secrets(conn, uid):
    bob = make_user(conn, "bob")
    conn.execute("INSERT INTO expenses (date, category_id, amount_cents) VALUES ('2026-11-01', ?, 100)",
                 (category_id(conn, "Gifts", bob),))
    conn.commit()
    tables = _read_zip(export.build_zip(conn))
    assert [u["username"] for u in tables["users.csv"]] == ["alice", "bob"]
    assert "password_hash" not in tables["users.csv"][0]
    assert len(tables["categories.csv"]) == 2 * len(db.DEFAULT_CATEGORIES) and len(tables["expenses.csv"]) == 1


def test_user_export_has_only_own_rows(client, conn, uid):
    bob = make_user(conn, "bob")
    conn.execute("INSERT INTO expenses (date, description, category_id, amount_cents) VALUES ('2026-11-01', 'BOBS', ?, 1)",
                 (category_id(conn, "Gifts", bob),))
    conn.execute("INSERT INTO regular_income (user_id, amount_cents, effective_from) VALUES (?, 1, '2026-01-01')", (bob,))
    conn.commit()
    tables = _read_zip(client.get("/export.zip").content)
    assert len(tables["categories.csv"]) == len(db.DEFAULT_CATEGORIES)
    assert "BOBS" not in str(tables)
    assert {r["user_id"] for t in tables.values() for r in t if "user_id" in r} <= {str(uid)}
