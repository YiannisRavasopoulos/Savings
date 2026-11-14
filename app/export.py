"""CSV export: one CSV per table, bundled in a zip.

* build_zip(conn, user_id)  -> that user's own data (Profile → Download my data).
* build_zip(conn)           -> everyone's data plus users.csv and admin_messages.csv (the daily
                               backup). Password hashes and sessions are never exported.
"""
from __future__ import annotations

import csv
import io
import sqlite3
import zipfile
from datetime import date

VISIBLE = ("(c.user_id = :uid AND c.is_joint = 0) OR c.id IN "
           "(SELECT category_id FROM joint_members WHERE user_id = :uid)")


def queries(user_id: int | None) -> list[tuple[str, str, dict]]:
    """(file name, SQL, params) for one user's own export, or for everyone (user_id None)."""
    if user_id is not None:
        p = {"uid": user_id}
        return [
            ("expenses",   # everything that costs this user something: own expenses + shares of joint ones
             "SELECT e.id, e.date, e.description, e.category_id, c.name AS category, c.is_joint,"
             " e.amount_cents, s.cents AS my_cost_cents, e.user_id = :uid AS paid_by_me,"
             " u.display_name AS paid_by,"
             # other members only ever see date, description, amount and who paid
             " CASE WHEN e.user_id = :uid THEN e.one_off ELSE '' END AS one_off,"
             " CASE WHEN e.user_id = :uid THEN e.notes ELSE '' END AS notes,"
             " e.created_at, e.updated_at "
             "FROM expense_shares s JOIN expenses e ON e.id = s.expense_id JOIN categories c ON c.id = e.category_id "
             "JOIN users u ON u.id = e.user_id WHERE s.user_id = :uid ORDER BY e.date, e.id", p),
            ("extra_income",
             "SELECT id, user_id, date, description, amount_cents, notes, created_at, updated_at "
             "FROM extra_income WHERE user_id = :uid ORDER BY date, id", p),
            ("categories",
             "SELECT c.id, c.user_id AS owner_id, c.name, c.sort_order, c.archived, c.is_joint "
             f"FROM categories c WHERE {VISIBLE} ORDER BY c.is_joint, c.sort_order, c.id", p),
            ("category_budgets",
             "SELECT b.id, b.category_id, c.name AS category, b.monthly_budget_cents, b.effective_from "
             f"FROM category_budgets b JOIN categories c ON c.id = b.category_id WHERE b.user_id = :uid AND ({VISIBLE}) "
             "ORDER BY c.is_joint, c.sort_order, b.category_id, b.effective_from", p),
            ("regular_income",
             "SELECT id, user_id, amount_cents, effective_from FROM regular_income WHERE user_id = :uid "
             "ORDER BY effective_from", p),
            ("recurring_expenses",
             "SELECT r.id, r.description, r.category_id, c.name AS category, r.amount_cents, r.notes, r.every_months,"
             " r.start_date, r.end_date, r.active, r.created_at FROM recurring_expenses r "
             "JOIN categories c ON c.id = r.category_id WHERE r.user_id = :uid ORDER BY r.id", p),
        ]
    return [
        ("expenses",
         "SELECT e.id, e.user_id, e.date, e.description, e.category_id, c.name AS category, c.is_joint,"
         " e.amount_cents, e.one_off, e.notes, e.recurring_id, e.created_at, e.updated_at "
         "FROM expenses e JOIN categories c ON c.id = e.category_id ORDER BY e.user_id, e.date, e.id", {}),
        ("expense_shares", "SELECT expense_id, user_id, cents FROM expense_shares ORDER BY expense_id, user_id", {}),
        ("extra_income",
         "SELECT id, user_id, date, description, amount_cents, notes, created_at, updated_at "
         "FROM extra_income ORDER BY user_id, date, id", {}),
        ("categories",
         "SELECT id, user_id, name, sort_order, archived, is_joint FROM categories "
         "ORDER BY user_id, sort_order, id", {}),
        ("category_budgets",
         "SELECT b.id, b.user_id, b.category_id, c.name AS category, b.monthly_budget_cents, b.effective_from "
         "FROM category_budgets b JOIN categories c ON c.id = b.category_id "
         "ORDER BY b.user_id, c.sort_order, b.category_id, b.effective_from", {}),
        ("regular_income",
         "SELECT id, user_id, amount_cents, effective_from FROM regular_income ORDER BY user_id, effective_from", {}),
        ("recurring_expenses",
         "SELECT id, user_id, description, category_id, amount_cents, notes, every_months, start_date, end_date,"
         " next_index, active, created_at FROM recurring_expenses ORDER BY user_id, id", {}),
        ("joint_members",
         "SELECT category_id, user_id, role, joined_from, committed_until, leaves_after FROM joint_members "
         "ORDER BY category_id, user_id", {}),
        ("joint_splits",
         "SELECT category_id, effective_from, user_id, share_bp FROM joint_splits "
         "ORDER BY category_id, effective_from, user_id", {}),
        ("planned_purchases",
         "SELECT id, user_id, name, amount_cents, saved_cents, category_id, notes, sort_order, created_at "
         "FROM planned_purchases ORDER BY user_id, sort_order, id", {}),
        ("users", USERS_SQL, {}),
        ("admin_messages", MESSAGES_SQL, {}),
    ]


MESSAGES_SQL = ("SELECT id, user_id, username, display_name, subject, body, created_at "
                "FROM admin_messages ORDER BY id")
USERS_SQL = ("SELECT id, username, display_name, status, period_start_day, period_naming, theme, created_at, "
             "approved_at, last_login_at FROM users ORDER BY id")


def zip_name(day: date) -> str:
    return f"spending-export-{day.isoformat()}.zip"


def build_zip(conn: sqlite3.Connection, user_id: int | None = None) -> bytes:
    """All tables read inside one transaction, so the CSVs agree with each other."""
    own_tx = not conn.in_transaction
    if own_tx:
        conn.execute("BEGIN")
    try:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            queries_ = queries(user_id)
            for name, sql, args in queries_:
                cur = conn.execute(sql, args)
                out = io.StringIO()
                writer = csv.writer(out)
                writer.writerow([col[0] for col in cur.description])
                writer.writerows(cur)
                # UTF-8 with BOM so Excel shows €, accents and Greek correctly.
                zf.writestr(f"{name}.csv", out.getvalue().encode("utf-8-sig"))
        return buf.getvalue()
    finally:
        if own_tx:
            conn.rollback()
