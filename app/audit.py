"""App-wide activity log for the admin: who did what, and when.

It deliberately records *actions*, not money: no amounts, expense descriptions or notes, so the
admin can follow what happens without seeing anyone's finances. Callers log inside their own
transaction, so an action and its log entry are saved together.
"""
from __future__ import annotations

from datetime import date

RETENTION_DAYS = 365      # older entries are removed by the daily backup run

# kind prefix -> label for the admin's filter
GROUPS = {
    "account": "Accounts & profile",
    "expense": "Expenses",
    "income": "Income",
    "category": "Categories & budgets",
    "shared": "Shared categories",
    "admin": "Admin actions",
    "backup": "Backups",
}


def log(conn, actor_id: int | None, kind: str, detail: str, *, category_id: int | None = None,
        effective: date | None = None, actor_name: str | None = None) -> None:
    if actor_name is None:
        if actor_id is None:
            actor_name = "System"
        else:
            row = conn.execute("SELECT display_name FROM users WHERE id = ?", (actor_id,)).fetchone()
            actor_name = row[0] if row else "Deleted account"
    conn.execute("INSERT INTO activity_log (actor_id, actor_name, kind, detail, category_id, effective_from) "
                 "VALUES (?, ?, ?, ?, ?, ?)",
                 (actor_id, actor_name, kind, detail, category_id, effective.isoformat() if effective else None))


def admin(conn, kind: str, detail: str) -> None:
    log(conn, None, f"admin.{kind}", detail, actor_name="Admin")


def category_name(conn, cid: int | None) -> str:
    row = conn.execute("SELECT name FROM categories WHERE id = ?", (cid,)).fetchone() if cid else None
    return f"“{row[0]}”" if row else "a deleted category"


def prune(conn, today: date) -> int:
    cutoff = date.fromordinal(today.toordinal() - RETENTION_DAYS).isoformat()
    return conn.execute("DELETE FROM activity_log WHERE created_at < ?", (cutoff,)).rowcount
