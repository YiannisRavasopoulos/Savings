import shutil
import sqlite3

import pytest

from app import db

from .conftest import add_budget, make_user


def _migrations_upto(tmp_path, last):
    d = tmp_path / f"m{last}"
    d.mkdir()
    for f in sorted(db.MIGRATIONS_DIR.glob("*.sql")):
        if int(f.name.split("_", 1)[0]) <= last:
            shutil.copy(f, d / f.name)
    return d


def _fresh(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.migrate(conn)
    return conn


def test_migrate_is_idempotent(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    assert db.migrate(conn) == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]
    assert db.migrate(conn) == []


def test_seed_user_gives_defaults_once(tmp_path):
    conn = _fresh(tmp_path)
    uid = make_user(conn, "bob", seed=False)
    db.seed_user(conn, uid)
    db.seed_user(conn, uid)
    conn.commit()
    assert [r["name"] for r in db.active_categories(conn, uid)] == db.DEFAULT_CATEGORIES


def test_category_names_unique_per_user_not_globally(tmp_path):
    conn = _fresh(tmp_path)
    a, b = make_user(conn, "ann"), make_user(conn, "ben")
    assert {r["name"] for r in db.active_categories(conn, a)} == {r["name"] for r in db.active_categories(conn, b)}
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO categories (user_id, name) VALUES (?, 'dINING out')", (a,))


def test_category_with_entries_cannot_be_deleted(tmp_path):
    conn = _fresh(tmp_path)
    uid = make_user(conn, "bob")
    cid = db.active_categories(conn, uid)[0]["id"]
    conn.execute("INSERT INTO expenses (date, category_id, amount_cents) VALUES ('2026-11-01', ?, 100)", (cid,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM categories WHERE id = ?", (cid,))


def test_user_with_data_cannot_be_deleted_by_accident(tmp_path):
    conn = _fresh(tmp_path)
    uid = make_user(conn, "bob")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM users WHERE id = ?", (uid,))


def test_delete_user_removes_everything_they_own(tmp_path):
    conn = _fresh(tmp_path)
    keep, gone = make_user(conn, "keep"), make_user(conn, "gone")
    for u in (keep, gone):
        cid = db.active_categories(conn, u)[0]["id"]
        conn.execute("INSERT INTO expenses (date, category_id, amount_cents) VALUES ('2026-11-01', ?, 100)", (cid,))
        add_budget(conn, cid, 500, "2026-01-01")
        conn.execute("INSERT INTO extra_income (user_id, date, amount_cents) VALUES (?, '2026-11-01', 5)", (u,))
        conn.execute("INSERT INTO regular_income (user_id, amount_cents, effective_from) VALUES (?, 5, '2026-01-01')", (u,))
        conn.execute("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, '2099-01-01')", (f"t{u}", u))
    conn.commit()
    with conn:
        db.delete_user(conn, gone)
    for table in ("extra_income", "regular_income", "sessions", "categories"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id = ?", (gone,)).fetchone()[0] == 0
        assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id = ?", (keep,)).fetchone()[0] > 0
    assert conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM category_budgets").fetchone()[0] == 1
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_missing_data_dir_is_an_error(tmp_path):
    with pytest.raises(SystemExit):
        db.ensure_data_dirs(tmp_path / "nope")
    assert not (tmp_path / "nope").exists()


def test_migration_002_keeps_existing_budgets(tmp_path):
    """A database created before budget history keeps its budgets for all past periods."""
    conn = db.connect(tmp_path / "t.db")
    assert db.migrate(conn, _migrations_upto(tmp_path, 1)) == [1]
    conn.execute("INSERT INTO categories (name, monthly_budget_cents) VALUES ('Food', 30000), ('Zero', 0)")
    conn.commit()
    assert db.migrate(conn, _migrations_upto(tmp_path, 2)) == [2]
    rows = [tuple(r) for r in conn.execute(
        "SELECT category_id, monthly_budget_cents, effective_from FROM category_budgets")]
    assert rows == [(1, 30000, "2000-01-01")]


def test_migration_003_upgrades_a_single_user_database(tmp_path):
    """Upgrading the real (pre-accounts) database: tables rebuilt with owners, references intact."""
    conn = db.connect(tmp_path / "t.db")
    db.migrate(conn, _migrations_upto(tmp_path, 2))
    conn.executemany("INSERT INTO categories (name, sort_order) VALUES (?, ?)", [("A", 1), ("B", 2)])
    conn.execute("INSERT INTO settings (key, value) VALUES ('theme', 'dark')")
    conn.commit()

    assert db.migrate(conn) == [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]
    cols = {t: [r[1] for r in conn.execute(f"PRAGMA table_info({t})")]
            for t in ("categories", "extra_income", "regular_income")}
    assert all("user_id" in c for c in cols.values())
    assert conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0
    assert conn.execute("SELECT key FROM settings").fetchall() == []
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_migration_005_keeps_messages_and_allows_delete_requests(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.migrate(conn, _migrations_upto(tmp_path, 4))
    uid = make_user(conn, "bob")
    conn.execute("INSERT INTO admin_messages (user_id, username, display_name, subject, body) "
                 "VALUES (?, 'bob', 'Bob', 'idea', 'keep me')", (uid,))
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO admin_messages (username, display_name, subject, body) "
                     "VALUES ('x', 'X', 'delete_account', 'y')")
    assert db.migrate(conn) == [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]
    assert [tuple(r) for r in conn.execute("SELECT user_id, subject, body FROM admin_messages")] == [(uid, "idea", "keep me")]
    conn.execute("INSERT INTO admin_messages (username, display_name, subject, body) VALUES ('x', 'X', 'delete_account', 'y')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO admin_messages (username, display_name, subject, body) VALUES ('x', 'X', 'nope', 'y')")
    # 013: existing messages start ungraded; priority stays within 0..5
    assert conn.execute("SELECT priority FROM admin_messages WHERE body = 'keep me'").fetchone()[0] == 0
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE admin_messages SET priority = 6")
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_migration_007_fills_owners_and_cost_rows(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.migrate(conn, _migrations_upto(tmp_path, 6))
    uid = make_user(conn, "bob")
    cid = conn.execute("SELECT id FROM categories WHERE user_id = ? LIMIT 1", (uid,)).fetchone()[0]
    conn.execute("INSERT INTO expenses (date, category_id, amount_cents, their_part_cents) VALUES ('2026-11-01', ?, 1000, 300)", (cid,))
    conn.commit()
    assert db.migrate(conn, _migrations_upto(tmp_path, 7)) == [7]
    assert conn.execute("SELECT user_id FROM expenses").fetchone()[0] == uid
    assert [tuple(r) for r in conn.execute("SELECT user_id, cents FROM expense_shares")] == [(uid, 700)]
    # triggers keep personal cost rows in sync from now on
    conn.execute("INSERT INTO expenses (date, category_id, amount_cents) VALUES ('2026-11-02', ?, 250)", (cid,))
    conn.execute("UPDATE expenses SET amount_cents = 2000 WHERE amount_cents = 1000")
    assert sorted(tuple(r) for r in conn.execute("SELECT user_id, cents FROM expense_shares")) == [(uid, 250), (uid, 1700)]
    conn.execute("DELETE FROM expenses WHERE amount_cents = 250")
    assert conn.execute("SELECT COUNT(*) FROM expense_shares").fetchone()[0] == 1
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_migration_008_retires_their_part_keeping_costs(tmp_path):
    """€40 with €10 "their part" -> €30 (+ note); €5 fully paid by someone else -> removed."""
    conn = db.connect(tmp_path / "t.db")
    db.migrate(conn, _migrations_upto(tmp_path, 7))
    uid = make_user(conn, "bob")
    cid = conn.execute("SELECT id FROM categories WHERE user_id = ? LIMIT 1", (uid,)).fetchone()[0]
    conn.execute("INSERT INTO expenses (date, category_id, amount_cents, their_part_cents, notes) "
                 "VALUES ('2026-11-01', ?, 4000, 1000, 'train')", (cid,))
    conn.execute("INSERT INTO expenses (date, category_id, amount_cents, their_part_cents) VALUES ('2026-11-02', ?, 500, 500)", (cid,))
    conn.execute("INSERT INTO expenses (date, category_id, amount_cents) VALUES ('2026-11-03', ?, 700)", (cid,))
    conn.commit()
    assert db.migrate(conn) == [8, 9, 10, 11, 12, 13, 14, 15, 16, 17]
    assert "their_part_cents" not in [r[1] for r in conn.execute("PRAGMA table_info(expenses)")]
    rows = [tuple(r) for r in conn.execute("SELECT amount_cents, notes FROM expenses ORDER BY date")]
    assert rows == [(3000, "train\n[Their part 10.00 of 40.00 removed; amount is now your cost.]"), (700, "")]
    assert sorted(r[0] for r in conn.execute("SELECT cents FROM expense_shares")) == [700, 3000]
    conn.execute("INSERT INTO expenses (date, category_id, amount_cents) VALUES ('2026-11-04', ?, 900)", (cid,))
    assert conn.execute("SELECT cents FROM expense_shares ORDER BY rowid DESC LIMIT 1").fetchone()[0] == 900
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_upgrade_to_personal_budgets_and_archived_names(tmp_path):
    """v10 -> v12: shared budgets become each member's part; archived names get "(archived)"."""
    import shutil
    old = tmp_path / "old"
    old.mkdir()
    for p in db.MIGRATIONS_DIR.glob("*.sql"):
        if int(p.name.split("_", 1)[0]) <= 10:
            shutil.copy(p, old / p.name)
    conn = db.connect(tmp_path / "x.db")
    db.migrate(conn, old)
    with conn:
        a = conn.execute("INSERT INTO users (username, display_name, password_hash, status) "
                         "VALUES ('a', 'A', 'x', 'active')").lastrowid
        b = conn.execute("INSERT INTO users (username, display_name, password_hash, status) "
                         "VALUES ('b', 'B', 'x', 'active')").lastrowid
        food = conn.execute("INSERT INTO categories (user_id, name) VALUES (?, 'Food')", (a,)).lastrowid
        home = conn.execute("INSERT INTO categories (user_id, name, is_joint) VALUES (?, 'Home', 1)", (a,)).lastrowid
        conn.execute("INSERT INTO categories (user_id, name, archived) VALUES (?, 'Old', 1)", (a,))
        conn.execute("INSERT INTO categories (user_id, name, archived) VALUES (?, 'Gone', 1)", (a,))
        conn.execute("INSERT INTO categories (user_id, name) VALUES (?, 'Gone (archived)')", (a,))
        conn.execute("INSERT INTO joint_members (category_id, user_id, role, joined_from, committed_until) "
                     "VALUES (?, ?, 'moderator', '2000-01-01', '2000-01-31')",
                     (home, a))
        conn.execute("INSERT INTO joint_members (category_id, user_id, role, joined_from, committed_until) "
                     "VALUES (?, ?, 'member', '2026-01-01', '2026-01-31')",
                     (home, b))
        conn.execute("INSERT INTO joint_splits (category_id, user_id, share_bp, effective_from) "
                     "VALUES (?, ?, 7000, '2026-01-01'), (?, ?, 3000, '2026-01-01')", (home, a, home, b))
        conn.execute("INSERT INTO category_budgets (category_id, monthly_budget_cents, effective_from) "
                     "VALUES (?, 20000, '2026-01-01'), (?, 60001, '2026-01-01')", (food, home))
    assert db.migrate(conn) == [11, 12, 13, 14, 15, 16, 17]
    rows = {(r[0], r[1]): r[2] for r in conn.execute("SELECT category_id, user_id, monthly_budget_cents FROM category_budgets")}
    assert rows == {(food, a): 20000, (home, a): 42000, (home, b): 18000}
    names = sorted(r[0] for r in conn.execute("SELECT name FROM categories WHERE user_id = ?", (a,)))
    gone_id = conn.execute("SELECT id FROM categories WHERE name LIKE 'Gone (archived %'").fetchone()[0]
    assert names == sorted(["Food", "Home", "Old (archived)", "Gone (archived)", f"Gone (archived {gone_id})"])
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
