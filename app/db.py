"""SQLite connection, migrations and first-run seeding."""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

# Every new account starts with these (budget 0); users rename, archive or delete them freely.
DEFAULT_CATEGORIES = [
    "Groceries", "Housing", "Utilities", "Transport", "Dining out", "Health",
    "Shopping", "Entertainment", "Subscriptions", "Gifts", "Travel", "Other",
]


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_data_dirs(data_dir: Path) -> None:
    if not data_dir.is_dir():
        raise SystemExit(
            f"Data directory {data_dir} does not exist. Create it on the host first "
            "(see README)."
        )
    for sub in ("db", "backups/db", "backups/csv"):
        (data_dir / sub).mkdir(parents=True, exist_ok=True)


def migrate(conn: sqlite3.Connection, migrations_dir: Path = MIGRATIONS_DIR) -> list[int]:
    """Apply numbered .sql files not yet recorded in schema_version."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        " version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    conn.commit()
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_version")}
    files = sorted(migrations_dir.glob("*.sql"), key=lambda p: int(p.name.split("_", 1)[0]))
    done = []
    for path in files:
        version = int(path.name.split("_", 1)[0])
        if version in applied:
            continue
        script = (
            "BEGIN;\n" + path.read_text(encoding="utf-8") + "\n"
            f"INSERT INTO schema_version (version, applied_at) "
            f"VALUES ({version}, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'));\nCOMMIT;"
        )
        try:
            conn.executescript(script)
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise
        done.append(version)
    return done


def seed_user(conn: sqlite3.Connection, user_id: int) -> None:
    """Give a new user the default categories (only if they have none). Caller commits."""
    if conn.execute("SELECT COUNT(*) FROM categories WHERE user_id = ?", (user_id,)).fetchone()[0]:
        return
    conn.executemany(
        "INSERT INTO categories (user_id, name, sort_order) VALUES (?, ?, ?)",
        [(user_id, name, i) for i, name in enumerate(DEFAULT_CATEGORIES, start=1)],
    )


def init(cfg) -> None:
    """Create folders and apply migrations. Called on app startup."""
    ensure_data_dirs(cfg.data_dir)
    conn = connect(cfg.db_path)
    try:
        migrate(conn)
        problems = conn.execute("PRAGMA foreign_key_check").fetchall()
        if problems:
            raise SystemExit(f"Database has broken references after migration: {problems[:5]}")
    finally:
        conn.close()


# Joint categories a user may log into today: member, membership started and not ended.
_JOINT_NOW = ("c.is_joint = 1 AND c.archived = 0 AND c.id IN (SELECT category_id FROM joint_members "
              "WHERE user_id = :uid AND joined_from <= :today AND (leaves_after IS NULL OR leaves_after >= :today))")


def _today() -> str:
    from .config import today
    return today().isoformat()


def active_categories(conn: sqlite3.Connection, user_id: int) -> list[sqlite3.Row]:
    """Categories offered on the Add form: own active ones, then shared ones you're a member of."""
    return conn.execute(
        "SELECT c.id, c.name, c.is_joint FROM categories c "
        f"WHERE (c.user_id = :uid AND c.is_joint = 0 AND c.archived = 0) OR ({_JOINT_NOW}) "
        "ORDER BY c.is_joint, c.sort_order, c.name",
        {"uid": user_id, "today": _today()},
    ).fetchall()


def categories_for_select(conn: sqlite3.Connection, user_id: int, include_id: int | None) -> list[sqlite3.Row]:
    """Like active_categories, plus the given one even if archived / no longer current (editing old entries)."""
    return conn.execute(
        "SELECT c.id, c.name, c.archived, c.is_joint FROM categories c "
        f"WHERE (c.user_id = :uid AND c.is_joint = 0 AND (c.archived = 0 OR c.id = :inc)) OR ({_JOINT_NOW}) "
        "OR (c.is_joint = 1 AND c.id = :inc AND c.id IN (SELECT category_id FROM joint_members WHERE user_id = :uid)) "
        "ORDER BY c.is_joint, c.sort_order, c.name",
        {"uid": user_id, "inc": include_id, "today": _today()},
    ).fetchall()


# A person's budget for category c in a period ending on :asof (their latest entry on or before
# it). Budgets are personal: in a shared category each member has their own. Bind :asof and :uid.
BUDGET_AS_OF_SQL = (
    "COALESCE((SELECT b.monthly_budget_cents FROM category_budgets b"
    " WHERE b.category_id = c.id AND b.user_id = :uid AND b.effective_from <= :asof"
    " ORDER BY b.effective_from DESC LIMIT 1), 0)"
)


def budget_of(conn, category_id: int, user_id: int, as_of: date) -> int:
    return conn.execute(f"SELECT {BUDGET_AS_OF_SQL} FROM categories c WHERE c.id = :cid",
                        {"cid": category_id, "uid": user_id, "asof": as_of.isoformat()}).fetchone()[0]


def all_categories(conn: sqlite3.Connection, user_id: int, budget_as_of: date) -> list[sqlite3.Row]:
    """Own categories, then shared ones the user is (or was) a member of. `budget` is always the
    user's own budget; `role` is their role in a shared category."""
    from .joint import VISIBLE_SQL
    return conn.execute(
        f"SELECT c.id, CASE WHEN c.is_joint = 1 AND jm.leaves_after IS NOT NULL AND jm.leaves_after < :today "
        f"THEN c.name || ' (left)' ELSE c.name END AS name, c.sort_order, c.archived, c.is_joint, c.user_id AS owner_id, "
        f"{BUDGET_AS_OF_SQL} AS budget,"
        " (SELECT COUNT(*) FROM expenses e WHERE e.category_id = c.id) AS n_entries, jm.role, jm.leaves_after "
        "FROM categories c LEFT JOIN joint_members jm ON jm.category_id = c.id AND jm.user_id = :uid "
        f"WHERE {VISIBLE_SQL} ORDER BY c.is_joint, c.sort_order, c.name",
        {"asof": budget_as_of.isoformat(), "uid": user_id, "today": _today()},
    ).fetchall()


def budget_history(conn: sqlite3.Connection, user_id: int) -> dict[int, list[sqlite3.Row]]:
    """category_id -> the user's own budget rows, newest first."""
    history: dict[int, list[sqlite3.Row]] = {}
    for row in conn.execute(
        "SELECT b.id, b.category_id, b.monthly_budget_cents, b.effective_from FROM category_budgets b "
        "WHERE b.user_id = ? ORDER BY b.category_id, b.effective_from DESC", (user_id,)
    ):
        history.setdefault(row["category_id"], []).append(row)
    return history


def delete_user(conn: sqlite3.Connection, user_id: int) -> None:
    """Remove a user and everything they own, in dependency order. Caller commits.

    Shared categories survive the user: if they moderated one, the longest-standing remaining
    member becomes moderator (and owner); with nobody left it's deleted. Their own joint expenses
    are removed and their share is redistributed to the others from the next joint period.
    """
    from datetime import date as _date
    from . import joint
    today = _date.fromisoformat(_today())
    for m in conn.execute("SELECT * FROM joint_members WHERE user_id = ?", (user_id,)).fetchall():
        cid = m["category_id"]
        cat = joint.category(conn, cid)
        others = [x for x in joint.members(conn, cid) if x["user_id"] != user_id]
        conn.execute("DELETE FROM expenses WHERE category_id = ? AND user_id = ?", (cid, user_id))
        conn.execute("DELETE FROM joint_members WHERE category_id = ? AND user_id = ?", (cid, user_id))
        current = [x for x in others if joint.status(x, today) != "left"]
        if not current and not conn.execute("SELECT 1 FROM expenses WHERE category_id = ?", (cid,)).fetchone():
            conn.execute("DELETE FROM categories WHERE id = ?", (cid,))      # nobody and nothing left
            continue
        gone = conn.execute("SELECT display_name FROM users WHERE id = ?", (user_id,)).fetchone()[0]
        joint.log(conn, cid, None, "account_deleted",
                  f"{gone}'s account was deleted by the admin; their expenses here were removed")
        if cat["user_id"] == user_id:
            heir = (current or others)[0] if (current or others) else None
            if heir is not None:
                conn.execute("UPDATE categories SET user_id = ? WHERE id = ?", (heir["user_id"], cid))
                conn.execute("UPDATE joint_members SET role = 'moderator' WHERE category_id = ? AND user_id = ?",
                             (cid, heir["user_id"]))
                joint.log(conn, cid, None, "handover", f"Moderation passed to {heir['display_name']}")
        conn.execute("DELETE FROM joint_splits WHERE category_id = ? AND effective_from > ? AND user_id = ?",
                     (cid, today.isoformat(), user_id))
        joint.rebuild_from(conn, cid, today)
    conn.execute("DELETE FROM joint_invites WHERE user_id = ? OR invited_by = ?", (user_id, user_id))
    conn.execute("DELETE FROM planned_purchases WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM recurring_expenses WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM expenses WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM expenses WHERE category_id IN (SELECT id FROM categories WHERE user_id = ?)",
                 (user_id,))
    conn.execute("DELETE FROM expense_shares WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM category_budgets WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM categories WHERE user_id = ?", (user_id,))      # budgets cascade
    conn.execute("DELETE FROM extra_income WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM regular_income WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
