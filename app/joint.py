"""Shared (joint) categories: membership, share splits and how a shared expense is divided.

There are no joint periods: everything is date-based and takes effect on the day it happens.

* Membership: a member counts from `joined_from` through `leaves_after` (inclusive), or
  indefinitely. Accepting an invitation makes you a member from that day; leaving or being
  removed ends your membership the day before (so from that day on you're out). The creator
  of a shared category is a member from the beginning (2000-01-01), so their history fits.
* Shares: `joint_splits` holds complete splits (summing to 100 %), each effective from a date.
  An expense uses the split in effect on its own date, so later changes never touch it.
  - When someone joins: everyone gets an equal split from that day.
  - When someone leaves: their share is redistributed in proportion to the others' shares.
  - The moderator can rearrange the shares; that applies from the day it's saved.
* Budgets are personal: each member has their own budget for a shared category.
* An expense of amount A is divided with the largest remainder method, so the parts are whole
  cents and add up to exactly A. Ties for a leftover cent go to the payer first.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta


FULL = 10_000            # 100.00 % in basis points
MAX_MEMBERS = 8
INVITE_DAYS = 14


BEGINNING = date(2000, 1, 1)      # creators are members "since always"


def _d(iso: str | None) -> date | None:
    return date.fromisoformat(iso) if iso else None


# --- membership ----------------------------------------------------------------------------

def category(conn, cid: int):
    return conn.execute("SELECT * FROM categories WHERE id = ? AND is_joint = 1", (cid,)).fetchone()


def members(conn, cid: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT m.*, u.username, u.display_name FROM joint_members m JOIN users u ON u.id = m.user_id "
        "WHERE m.category_id = ? ORDER BY m.role = 'moderator' DESC, m.joined_from, u.username", (cid,)).fetchall()


def membership(conn, cid: int, uid: int):
    return conn.execute("SELECT * FROM joint_members WHERE category_id = ? AND user_id = ?", (cid, uid)).fetchone()


def is_member_on(m, d: date) -> bool:
    return _d(m["joined_from"]) <= d and (m["leaves_after"] is None or d <= _d(m["leaves_after"]))


def status(m, today: date) -> str:
    """'active', or 'left' once the membership has ended."""
    if m is None:
        return "left"
    if m["leaves_after"] and today > _d(m["leaves_after"]):
        return "left"
    return "active"


def current_member_count(conn, cid: int, today: date) -> int:
    return sum(1 for m in members(conn, cid) if status(m, today) != "left")


# --- splits -----------------------------------------------------------------------------------

def split_at(conn, cid: int, d: date) -> dict[int, int]:
    """The split (user_id -> basis points) in effect on day d."""
    row = conn.execute("SELECT MAX(effective_from) FROM joint_splits WHERE category_id = ? AND effective_from <= ?",
                       (cid, d.isoformat())).fetchone()
    if not row or row[0] is None:
        return {}
    return dict(conn.execute("SELECT user_id, share_bp FROM joint_splits WHERE category_id = ? AND effective_from = ?",
                             (cid, row[0])).fetchall())


def largest_remainder(total: int, weights: dict[int, int], first: list[int] = ()) -> dict[int, int]:
    """Divide `total` (integer) in proportion to `weights`; parts are integers summing to total.
    Leftover units go to the largest remainders; ties go to ids in `first`, then by id."""
    wsum = sum(weights.values())
    if wsum <= 0:
        return {k: 0 for k in weights}
    base = {k: total * w // wsum for k, w in weights.items()}
    rem = {k: total * w % wsum for k, w in weights.items()}
    left = total - sum(base.values())
    order = sorted(weights, key=lambda k: (-rem[k], 0 if k in first else 1, k))
    for k in order[:left]:
        base[k] += 1
    return base


def write_split(conn, cid: int, at: date, split: dict[int, int]) -> None:
    conn.execute("DELETE FROM joint_splits WHERE category_id = ? AND effective_from = ?", (cid, at.isoformat()))
    conn.executemany("INSERT INTO joint_splits (category_id, effective_from, user_id, share_bp) VALUES (?, ?, ?, ?)",
                     [(cid, at.isoformat(), u, bp) for u, bp in split.items()])


def _members_on(conn, cid: int, d: date) -> list[sqlite3.Row]:
    return [m for m in members(conn, cid) if is_member_on(m, d)]


def rebuild_from(conn, cid: int, at: date) -> None:
    """Recompute the split at every membership-change date from `at` on.

    For each date where membership changes: equal split if someone joins that day, otherwise the
    previous split rescaled to the remaining members. Redundant splits are dropped. Custom splits
    set by the moderator are kept unless the members change at that same date.
    """
    ms = members(conn, cid)
    dates = {_d(m["joined_from"]) for m in ms} | {_d(m["leaves_after"]) + timedelta(days=1) for m in ms if m["leaves_after"]}
    dates |= {_d(r[0]) for r in conn.execute("SELECT DISTINCT effective_from FROM joint_splits WHERE category_id = ?",
                                             (cid,))}
    dates.add(at)                                  # e.g. a member removed outright (account deleted)
    for d in sorted(x for x in dates if x >= at):
        active = [m for m in ms if is_member_on(m, d)]
        ids = {m["user_id"] for m in active}
        mods = [m["user_id"] for m in active if m["role"] == "moderator"]
        previous = split_at(conn, cid, d - timedelta(days=1))
        existing = dict(conn.execute("SELECT user_id, share_bp FROM joint_splits WHERE category_id = ? AND effective_from = ?",
                                     (cid, d.isoformat())).fetchall())
        if not ids:
            conn.execute("DELETE FROM joint_splits WHERE category_id = ? AND effective_from = ?", (cid, d.isoformat()))
            continue
        if existing and set(existing) == ids:
            continue                                   # a valid split already (e.g. set by the moderator)
        if any(_d(m["joined_from"]) == d for m in active) or not (set(previous) & ids):
            new = largest_remainder(FULL, {u: 1 for u in ids}, mods)          # equal split
        else:
            # proportional: start from the split meant for this period (e.g. set by the moderator) when
            # it covers everyone still here (someone left), otherwise from the one before it
            base = existing if existing and set(existing) >= ids else previous
            new = largest_remainder(FULL, {u: base.get(u, 0) for u in ids}, mods)
            if sum(base.get(u, 0) for u in ids) == 0:
                new = largest_remainder(FULL, {u: 1 for u in ids}, mods)
        if new == previous:
            conn.execute("DELETE FROM joint_splits WHERE category_id = ? AND effective_from = ?", (cid, d.isoformat()))
        else:
            write_split(conn, cid, d, new)
    reallocate_category(conn, cid)


# --- dividing expenses ----------------------------------------------------------------------------

def reallocate_expense(conn, expense_id: int) -> None:
    e = conn.execute("SELECT e.*, c.is_joint FROM expenses e JOIN categories c ON c.id = e.category_id "
                     "WHERE e.id = ?", (expense_id,)).fetchone()
    if e is None or not e["is_joint"]:
        return
    split = split_at(conn, e["category_id"], _d(e["date"])) or {e["user_id"]: FULL}
    parts = largest_remainder(e["amount_cents"], split, [e["user_id"]])
    conn.execute("DELETE FROM expense_shares WHERE expense_id = ?", (expense_id,))
    conn.executemany("INSERT INTO expense_shares (expense_id, user_id, cents) VALUES (?, ?, ?)",
                     [(expense_id, u, c) for u, c in parts.items()])


def reallocate_category(conn, cid: int) -> None:
    for (eid,) in conn.execute("SELECT id FROM expenses WHERE category_id = ?", (cid,)).fetchall():
        reallocate_expense(conn, eid)


# --- which categories a user sees -------------------------------------------------------------

# Categories a user can see: their own personal ones + joint ones they are (or were) a member of.
VISIBLE_SQL = ("((c.user_id = :uid AND c.is_joint = 0) OR c.id IN "
               "(SELECT category_id FROM joint_members WHERE user_id = :uid))")


def can_log_on(conn, cid: int, uid: int, d: date) -> str | None:
    """None if uid may log an expense dated d in joint category cid, else the reason why not."""
    m = membership(conn, cid, uid)
    if m is None:
        return "You're not a member of this shared category."
    if d < _d(m["joined_from"]):
        return f"You joined on {_d(m['joined_from']):%d %b %Y}; pick a date from then on."
    if m["leaves_after"] and d > _d(m["leaves_after"]):
        return "You've left this shared category, so you can't add expenses to it."
    return None


def pending_invites(conn, uid: int, today: date) -> list[dict]:
    """Invitations waiting for uid, with what accepting would mean."""
    out = []
    for r in conn.execute(
            "SELECT i.*, c.name, u.display_name AS moderator FROM joint_invites i "
            "JOIN categories c ON c.id = i.category_id JOIN users u ON u.id = i.invited_by "
            "WHERE i.user_id = ? AND i.expires_at >= ? ORDER BY i.created_at", (uid, today.isoformat())).fetchall():
        n = current_member_count(conn, r["category_id"], today) + 1
        out.append({"id": r["id"], "category_id": r["category_id"], "name": r["name"], "moderator": r["moderator"],
                    "members_then": n, "share_pct": round(100 / n, 2), "expires": r["expires_at"]})
    return out


# --- activity log ----------------------------------------------------------------------------------

def log(conn, cid: int, actor_id: int | None, kind: str, detail: str, effective: date | None = None) -> None:
    """Record an action on a shared category in the admin's activity log. Caller commits."""
    from . import audit
    prefix = "" if kind.startswith(("expense.", "category.")) else "shared."
    audit.log(conn, actor_id, prefix + kind, detail, category_id=cid, effective=effective)


def is_joint(conn, cid: int | None) -> bool:
    return bool(cid) and conn.execute("SELECT is_joint FROM categories WHERE id = ?", (cid,)).fetchone() == (1,)


def describe_expense(conn, e) -> str:
    """'an expense in “Home” (dated 05 Dec 2026)': no amount or description, on purpose."""
    from .audit import category_name
    return f"an expense in {category_name(conn, e['category_id'])} (dated {_d(e['date']):%d %b %Y})"
