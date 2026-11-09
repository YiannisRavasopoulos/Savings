"""Categories page: add, edit (name + budget), reorder, archive and delete.

What depends on a category, and how each action handles it:
  * expenses.category_id   ON DELETE RESTRICT. A category with expenses can only be deleted
                           after its expenses are moved to another category or deleted, in
                           the same transaction.
  * category_budgets       ON DELETE CASCADE. Its budget history goes with it.
  * the Add form           needs at least one active category, so the last active one can't
                           be archived or deleted.
Anything we refuse is explained in an error pop-up.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request

from . import audit, config, db, forms, joint, period, summary
from .money import format_eur, parse_amount
from .web import NOW_SQL, current_period, get_conn, redirect, render, user_id

router = APIRouter(prefix="/categories")

MAX_NAME = 50

# Success messages, chosen by code so the URL can't inject arbitrary text.
MESSAGES = {
    "added": "Category “{name}” added.",
    "saved": "“{name}” saved.",
    "archived": "Archived as “{name}”. Its entries stay in your history, and the old name is free to reuse.",
    "unarchived": "“{name}” is active again.",
    "deleted": "Category “{name}” deleted.",
    "moved": "Category deleted. {n} expense{s} moved to “{name}”.",
    "purged": "Category “{name}” and its {n} expense{s} deleted.",
    "budget_edited": "Budget of “{name}” updated.",
    "budget_deleted": "Budget entry of “{name}” deleted.",
    "shared": "“{name}” is now a shared category.",
    "left": "You left “{name}”. It's archived for you: its past expenses stay in your history, and new "
            "ones are split among the remaining members.",
    "closed": "“{name}” is closed and archived for everyone. Its history stays.",
}

INVITE_MESSAGES = {
    "gone": {"text": "That invitation no longer exists (it may have expired or been cancelled).", "error": True},
    "agree": {"text": "To accept, tick “I understand and agree” first.", "error": True},
    "full": {"text": "That shared category is already full.", "error": True},
    "declined": {"text": "Invitation declined.", "error": False},
    "budget": {"text": "That budget amount wasn't valid; the invitation is still waiting.", "error": True},
}
SHARED_ELSEWHERE = "Shared categories are managed from their own page (Categories → Shared → Open)."

GONE_BUDGET = "That budget entry no longer exists. It may have been changed in another tab."


class Refused(Exception):
    """An action we won't do; the message is shown to the user in a pop-up."""
    status = 409


class Missing(Refused):
    """Not one of this user's categories (deleted, or someone else's): looks like 404."""
    status = 404


# --- data ------------------------------------------------------------------------

def _category(conn, uid: int, category_id: int) -> sqlite3.Row:
    """One of this user's categories. Someone else's id looks exactly like a missing one."""
    row = conn.execute("SELECT * FROM categories WHERE id = ? AND user_id = ?", (category_id, uid)).fetchone()
    if row is None:
        raise Missing("That category no longer exists. It may have been deleted in another tab.")
    return row


def _usage(conn, category_id: int) -> dict:
    n, total, first, last = conn.execute(
        f"SELECT COUNT(*), COALESCE(SUM(e.amount_cents), 0),"
        f" MIN(e.date), MAX(e.date) FROM expenses e WHERE e.category_id = ?",
        (category_id,),
    ).fetchone()
    budgets = conn.execute("SELECT COUNT(*) FROM category_budgets WHERE category_id = ?",
                           (category_id,)).fetchone()[0]
    return {"n": n, "total": total, "first": first, "last": last, "budgets": budgets}


def _active_count(conn, uid: int) -> int:
    return conn.execute("SELECT COUNT(*) FROM categories WHERE user_id = ? AND archived = 0 AND is_joint = 0",
                        (uid,)).fetchone()[0]


def _check_not_last_active(conn, cat: sqlite3.Row, doing: str) -> None:
    if not cat["archived"] and _active_count(conn, cat["user_id"]) == 1:
        raise Refused(f"“{cat['name']}” is your only active category, so it can't be {doing}: "
                      "the Add form would have nothing to choose from. Add or unarchive another "
                      "category first.")


def _clean_name(conn, uid: int, raw: str, exclude_id: int | None = None) -> str:
    name = " ".join((raw or "").split())   # trim and collapse inner whitespace
    if not name:
        raise ValueError("Enter a name.")
    if len(name) > MAX_NAME:
        raise ValueError(f"Keep it under {MAX_NAME} characters.")
    clash = conn.execute("SELECT name FROM categories WHERE user_id = ? AND name = ? COLLATE NOCASE "
                         "AND id IS NOT ?", (uid, name, exclude_id)).fetchone()
    if clash:
        if exclude_id is None:
            raise ValueError(f"“{clash[0]}” already exists.")
        raise ValueError(f"“{clash[0]}” already exists. To combine the two, delete this category "
                         f"and choose “Move its expenses” to “{clash[0]}”.")
    return name


def _set_budget(conn, category_id: int, cents: int, effective_from: str, user_id: int) -> None:
    """The user's own budget for a category. Same category + date again replaces that amount."""
    conn.execute(
        "INSERT INTO category_budgets (category_id, user_id, monthly_budget_cents, effective_from) "
        "VALUES (?, ?, ?, ?) ON CONFLICT(category_id, user_id, effective_from) "
        "DO UPDATE SET monthly_budget_cents = excluded.monthly_budget_cents",
        (category_id, user_id, cents, effective_from))


def _budget_category(conn, uid: int, category_id: int) -> sqlite3.Row:
    """A category whose budget this user may set: one of their own, or a shared one they're in."""
    row = conn.execute("SELECT * FROM categories WHERE id = ?", (category_id,)).fetchone()
    if row is not None and (row["user_id"] == uid and not row["is_joint"]
                            or row["is_joint"] and joint.status(joint.membership(conn, row["id"], uid),
                                                                config.today()) != "left"):
        return row
    raise Missing("That category no longer exists. It may have been deleted in another tab.")


ARCHIVED = " (archived)"


def _archived_name(conn, uid: int, cat) -> str:
    base, n = cat["name"] + ARCHIVED, 2
    name = base
    while conn.execute("SELECT 1 FROM categories WHERE user_id = ? AND name = ? COLLATE NOCASE AND id != ?",
                       (uid, name, cat["id"])).fetchone():
        name, n = f"{base} {n}", n + 1
    return name


def _unarchived_name(conn, uid: int, cat) -> str:
    import re
    base = re.sub(r" \(archived\)( \d+)?$", "", cat["name"])
    name, n = base, 2
    while conn.execute("SELECT 1 FROM categories WHERE user_id = ? AND name = ? COLLATE NOCASE AND id != ?",
                       (uid, name, cat["id"])).fetchone():
        name, n = f"{base} ({n})", n + 1
    return name


def _parse_budget(raw_amount: str, raw_from: str, errors: dict) -> tuple[int | None, str | None]:
    """Blank amount = no budget change. Returns (cents, iso date) or (None, None)."""
    if not raw_amount.strip():
        return None, None
    cents = effective = None
    try:
        cents = parse_amount(raw_amount)
    except ValueError as e:
        errors["budget"] = str(e)
    try:
        effective = forms.parse_date(raw_from).isoformat()
    except ValueError:
        errors["budget_from"] = "Enter a valid date."
    return cents, effective


# --- page --------------------------------------------------------------------------

def budget_overview(conn, uid: int, year: int, month: int, cats) -> dict:
    """Total of everything you've budgeted for the period: your active categories' budgets plus
    your part of each shared category's budget, against income and your spending in them."""
    ms = summary.month_summary(conn, uid, year, month)
    _, end = period.period_bounds(year, month, summary.get_start_day(conn, uid))
    personal_ids = {c["id"] for c in cats if not c["archived"]}
    shared_ids = {c["id"] for c in ms["categories"] if c["joint"]
                  and joint.membership(conn, c["id"], uid) and joint.is_member_on(joint.membership(conn, c["id"], uid), end)}
    counted = [c for c in ms["categories"] if c["id"] in personal_ids or c["id"] in shared_ids]
    total = sum(c["budget"] for c in counted)
    spent = sum(c["spent"] for c in counted)
    income = ms["regular"]
    return {
        "total": total,
        "n_budgeted": sum(1 for c in counted if c["budget"] > 0),
        "n_active": len(personal_ids) + len(shared_ids),
        "n_shared": len(shared_ids),
        "income": income,
        "unbudgeted": income - total,
        "income_pct": summary.budget_pct(total, income),          # share of income that is budgeted
        "income_status": "red" if income and total > income else "",
        "spent": spent,
        "spent_pct": summary.budget_pct(spent, total),
        "spent_status": summary.budget_status(spent, total),
        "range": ms["range"],
    }


def render_page(request: Request, conn, status_code: int = 200, *, errors=None, values=None,
                reopen: str | None = None, alert: str | None = None):
    uid = user_id(request)
    y, m = current_period(conn, uid)
    current_end = period.period_bounds(y, m, summary.get_start_day(conn, uid))[1]
    cats = db.all_categories(conn, uid, current_end)
    usage = {c["id"]: _usage(conn, c["id"]) for c in cats}
    personal = [c for c in cats if not c["is_joint"]]
    today = config.today()
    start, end = period.period_bounds(y, m, summary.get_start_day(conn, uid))
    shared = []
    for c in cats:
        if not c["is_joint"]:
            continue
        mem = joint.membership(conn, c["id"], uid)
        st = joint.status(mem, today)
        spent = conn.execute("SELECT COALESCE(SUM(amount_cents), 0) FROM expenses WHERE category_id = ? "
                             "AND date BETWEEN ? AND ?", (c["id"], start.isoformat(), end.isoformat())).fetchone()[0]
        shared.append({"c": c, "status": st, "membership": mem, "is_mod": c["role"] == "moderator" and st != "left",
                       "share_bp": joint.split_at(conn, c["id"], today).get(uid, 0) if st != "left" else 0,
                       "my_budget": c["budget"], "spent": spent,
                       "deletable": bool(c["archived"]) and _usage(conn, c["id"])["n"] == 0})
    editable = personal + [x["c"] for x in shared if x["status"] != "left"]
    invite_msg = INVITE_MESSAGES.get(request.query_params.get("invite", ""))
    message = None
    code = request.query_params.get("done")
    if code in MESSAGES and status_code == 200:
        n = int(request.query_params.get("n") or 0)
        message = MESSAGES[code].format(name=request.query_params.get("name", ""), n=n,
                                        s="" if n == 1 else "s", date=request.query_params.get("date", ""))
    return render(
        request, "categories.html", status_code, active="categories",
        categories=personal, shared=shared, editable=editable, usage=usage, history=db.budget_history(conn, uid),
        notice_title={"left": "You left", "closed": "Category closed"}.get(request.query_params.get("done")),
        active_count=sum(1 for c in personal if not c["archived"]),
        overview=budget_overview(conn, uid, y, m, personal),
        moderated={x["c"]["id"] for x in shared if x["is_mod"]},
        invites=joint.pending_invites(conn, uid, today), invite_msg=invite_msg, back="/categories",
        reset=summary.reset_notice(conn, uid, today),
        default_start_day=summary.get_start_day(conn, uid),
        current_label=period.period_label(y, m), today=config.today().isoformat(),
        errors=errors or {}, values=values or {}, reopen=reopen, alert=alert, message=message,
    )


def done(code: str, name: str = "", n: int = 0, when: str = ""):
    return redirect("/categories?" + urlencode({"done": code, "name": name, "n": n, "date": when}))


@router.get("")
def categories_page(request: Request, conn=Depends(get_conn)):
    return render_page(request, conn)


@router.post("")
async def add_category(request: Request, conn=Depends(get_conn)):
    form = await request.form()
    raw = {k: (form.get(k) or "").strip() for k in ("name", "budget", "budget_from", "joint")}
    uid = user_id(request)
    errors: dict = {}
    try:
        name = _clean_name(conn, uid, raw["name"])
    except ValueError as e:
        errors["name"] = str(e)
    cents, effective = _parse_budget(raw["budget"], raw["budget_from"], errors)
    is_joint = raw["joint"] == "1"
    if errors:
        return render_page(request, conn, 422, errors=errors, values=raw, reopen="dlg-add")
    with conn:
        cur = conn.execute(
            "INSERT INTO categories (user_id, name, sort_order, is_joint) "
            "VALUES (?, ?, (SELECT COALESCE(MAX(sort_order), 0) + 1 FROM categories WHERE user_id = ?), ?)",
            (uid, name, uid, 1 if is_joint else 0))
        cid = cur.lastrowid
        if cents:
            _set_budget(conn, cid, cents, effective, uid)
        if is_joint:
            # The creator is the moderator, a member "since always" with 100 %.
            begin = joint.BEGINNING.isoformat()
            conn.execute("INSERT INTO joint_members (category_id, user_id, role, joined_from, committed_until) "
                         "VALUES (?, ?, 'moderator', ?, ?)", (cid, uid, begin, begin))
            joint.write_split(conn, cid, joint.BEGINNING, {uid: joint.FULL})
            joint.log(conn, cid, uid, "created", f"Created the shared category “{name}”")
        else:
            audit.log(conn, uid, "category.added", f"Added the category “{name}”", category_id=cid)
    if is_joint:
        return redirect(f"/shared/{cid}")
    return done("added", name)


@router.post("/{category_id}/edit")
async def edit_category(request: Request, category_id: int, conn=Depends(get_conn)):
    """Rename (owner / moderator) and set your own budget (anyone who uses the category)."""
    form = await request.form()
    raw = {k: (form.get(k) or "").strip() for k in ("name", "budget", "budget_from")}
    uid = user_id(request)
    try:
        cat = _budget_category(conn, uid, category_id)
    except Refused as e:
        return render_page(request, conn, e.status, alert=str(e))
    can_rename = cat["user_id"] == uid
    errors: dict = {}
    name = cat["name"]
    if can_rename:
        try:
            name = _clean_name(conn, uid, raw["name"], exclude_id=category_id)
        except ValueError as e:
            errors["name"] = str(e)
    cents, effective = _parse_budget(raw["budget"], raw["budget_from"], errors)
    if errors:
        return render_page(request, conn, 422, errors=errors, values=raw, reopen=f"dlg-edit-{category_id}")
    with conn:
        if can_rename:
            conn.execute("UPDATE categories SET name = ? WHERE id = ?", (name, category_id))
        if cents is not None:
            _set_budget(conn, category_id, cents, effective, uid)
        if name != cat["name"]:
            audit.log(conn, uid, "shared.renamed" if cat["is_joint"] else "category.renamed",
                      f"Renamed “{cat['name']}” to “{name}”", category_id=category_id)
        if cents is not None:
            audit.log(conn, uid, "category.budget", f"Set their budget for “{name}”", category_id=category_id,
                      effective=date.fromisoformat(effective))
    return done("saved", name)


@router.post("/{category_id}/move")
async def move_category(request: Request, category_id: int, conn=Depends(get_conn)):
    step = -1 if (await request.form()).get("direction") == "up" else 1
    uid = user_id(request)
    ids = [r[0] for r in conn.execute("SELECT id FROM categories WHERE user_id = ? AND is_joint = 0 "
                                      "ORDER BY sort_order, name", (uid,))]
    if category_id not in ids:
        return render_page(request, conn, 404, alert="That category no longer exists. "
                                                     "It may have been deleted in another tab.")
    i = ids.index(category_id)
    j = i + step
    if 0 <= j < len(ids):
        ids[i], ids[j] = ids[j], ids[i]
        with conn:
            conn.executemany("UPDATE categories SET sort_order = ? WHERE id = ?",
                             [(n, cid) for n, cid in enumerate(ids, start=1)])
    return redirect(f"/categories#cat-{category_id}")


@router.post("/{category_id}/archive")
def toggle_archive(request: Request, category_id: int, conn=Depends(get_conn)):
    try:
        cat = _category(conn, user_id(request), category_id)
        if cat["is_joint"]:
            raise Refused(SHARED_ELSEWHERE)
        if not cat["archived"]:
            _check_not_last_active(conn, cat, "archived")
    except Refused as e:
        return render_page(request, conn, e.status, alert=str(e))
    uid = user_id(request)
    # Archiving renames it "<name> (archived)" so the name is free to reuse; unarchiving restores
    # the name, or "<name> (2)" if it has been taken meanwhile.
    new_name = _unarchived_name(conn, uid, cat) if cat["archived"] else _archived_name(conn, uid, cat)
    with conn:
        conn.execute("UPDATE categories SET archived = 1 - archived, name = ? WHERE id = ?", (new_name, category_id))
        audit.log(conn, uid, "category.unarchived" if cat["archived"] else "category.archived",
                  f"{'Unarchived' if cat['archived'] else 'Archived'} “{cat['name']}” (now “{new_name}”)",
                  category_id=category_id)
    return done("unarchived" if cat["archived"] else "archived", new_name)


@router.post("/{category_id}/delete-closed")
def delete_closed_shared(request: Request, category_id: int, conn=Depends(get_conn)):
    """Remove a closed shared category that never had an expense. Any former member may do it:
    with no expenses, nobody's history depends on it."""
    uid = user_id(request)
    cat = conn.execute("SELECT c.* FROM categories c JOIN joint_members m ON m.category_id = c.id "
                       "WHERE c.id = ? AND m.user_id = ? AND c.is_joint = 1", (category_id, uid)).fetchone()
    try:
        if cat is None:
            raise Missing("That category no longer exists. It may have been deleted in another tab.")
        if not cat["archived"]:
            raise Refused(f"“{cat['name']}” is still in use. Only a closed shared category can be deleted.")
        n = _usage(conn, category_id)["n"]
        if n:
            raise Refused(f"“{cat['name']}” has {n} expense(s), which are part of its members' history, "
                          "so it can't be deleted.")
    except Refused as e:
        return render_page(request, conn, e.status, alert=str(e))
    with conn:
        conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))   # members, splits, budgets cascade
        audit.log(conn, uid, "category.deleted", f"Deleted the closed, unused shared category “{cat['name']}”")
    return done("deleted", cat["name"])


@router.post("/{category_id}/delete")
async def delete_category(request: Request, category_id: int, conn=Depends(get_conn)):
    form = await request.form()
    action = form.get("action") or ""
    uid = user_id(request)
    try:
        cat = _category(conn, uid, category_id)
        if cat["is_joint"]:
            raise Refused(SHARED_ELSEWHERE)
        _check_not_last_active(conn, cat, "deleted")
        usage = _usage(conn, category_id)
        try:
            expected = int(form.get("expected") or -1)
        except ValueError:
            expected = -1
        if expected != usage["n"]:
            raise Refused(f"“{cat['name']}” now has {usage['n']} expense(s), which changed since you "
                          "opened the delete dialog (maybe in another tab). Nothing was deleted; "
                          "please review and try again.")
    except Refused as e:
        return render_page(request, conn, e.status, alert=str(e))

    dialog = f"dlg-delete-{category_id}"
    if usage["n"] == 0:
        with conn:
            conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))  # budgets cascade
            audit.log(conn, uid, "category.deleted", f"Deleted the unused category “{cat['name']}”")
        return done("deleted", cat["name"])

    if action == "move":
        try:
            target_id = int(form.get("target") or 0)
        except ValueError:
            target_id = 0
        target = conn.execute("SELECT id, name FROM categories WHERE id = ? AND user_id = ? AND is_joint = 0",
                              (target_id, uid)).fetchone()
        if target is None or target_id == category_id:
            return render_page(request, conn, 422, errors={"target": "Choose where the expenses should go."},
                               values={"action": "move"}, reopen=dialog)
        with conn:
            conn.execute(f"UPDATE expenses SET category_id = ?, updated_at = {NOW_SQL} "
                         "WHERE category_id = ?", (target_id, category_id))
            conn.execute("UPDATE planned_purchases SET category_id = ? WHERE category_id = ?",
                         (target_id, category_id))
            conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
            audit.log(conn, uid, "category.deleted", f"Deleted “{cat['name']}” and moved its {usage['n']} "
                      f"expense(s) to “{target['name']}”", category_id=target_id)
        return done("moved", target["name"], usage["n"])

    if action == "delete_entries":
        typed = " ".join((form.get("confirm") or "").split())
        if typed.casefold() != cat["name"].casefold():
            return render_page(request, conn, 422,
                               errors={"confirm": f"Type “{cat['name']}” exactly to confirm."},
                               values={"action": "delete_entries", "confirm": typed}, reopen=dialog)
        with conn:
            conn.execute("DELETE FROM expenses WHERE category_id = ?", (category_id,))
            conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
            audit.log(conn, uid, "category.deleted", f"Deleted “{cat['name']}” together with its {usage['n']} expense(s)")
        return done("purged", cat["name"], usage["n"])

    return render_page(request, conn, 422, errors={"action": "Choose what happens to the expenses."},
                       reopen=dialog)


# --- budget history entries ------------------------------------------------------------

def _own_budget(conn, uid: int, category_id: int, budget_id: int):
    """One of this user's own budget entries (any category they use), with the category name."""
    return conn.execute(
        "SELECT b.*, c.name FROM category_budgets b JOIN categories c ON c.id = b.category_id "
        "WHERE b.id = ? AND b.category_id = ? AND b.user_id = ?", (budget_id, category_id, uid)).fetchone()


@router.post("/{category_id}/budgets/{budget_id}/edit")
async def edit_budget(request: Request, category_id: int, budget_id: int, conn=Depends(get_conn)):
    uid = user_id(request)
    row = _own_budget(conn, uid, category_id, budget_id)
    if row is None:
        return render_page(request, conn, 404, alert=GONE_BUDGET)
    form = await request.form()
    raw = {k: (form.get(k) or "").strip() for k in ("budget", "budget_from")}
    errors: dict = {}
    if not raw["budget"]:
        errors["budget"] = "Enter an amount (0 for no budget)."
        cents = effective = None
    else:
        cents, effective = _parse_budget(raw["budget"], raw["budget_from"], errors)
    if not errors:
        clash = conn.execute("SELECT 1 FROM category_budgets WHERE category_id = ? AND user_id = ? "
                             "AND effective_from = ? AND id != ?", (category_id, uid, effective, budget_id)).fetchone()
        if clash:
            errors["budget_from"] = ("This category already has a budget starting on that date. "
                                     "Edit or delete that one instead.")
    if errors:
        return render_page(request, conn, 422, errors=errors, values=raw, reopen=f"dlg-budget-edit-{budget_id}")
    with conn:
        conn.execute("UPDATE category_budgets SET monthly_budget_cents = ?, effective_from = ? WHERE id = ?",
                     (cents, effective, budget_id))
        audit.log(conn, uid, "category.budget", f"Changed a budget entry of “{row['name']}”",
                  category_id=category_id, effective=date.fromisoformat(effective))
    return done("budget_edited", row["name"])


@router.post("/{category_id}/budgets/{budget_id}/delete")
def delete_budget(request: Request, category_id: int, budget_id: int, conn=Depends(get_conn)):
    uid = user_id(request)
    row = _own_budget(conn, uid, category_id, budget_id)
    if row is None:
        return render_page(request, conn, 404, alert=GONE_BUDGET)
    with conn:
        conn.execute("DELETE FROM category_budgets WHERE id = ?", (budget_id,))
        audit.log(conn, uid, "category.budget",
                  f"Removed the budget entry of “{row['name']}” from "
                  f"{date.fromisoformat(row['effective_from']):%d %b %Y}", category_id=category_id)
    return done("budget_deleted", row["name"])


# --- turning a personal category into a shared one ------------------------------------------

@router.post("/{category_id}/share")
async def turn_into_shared(request: Request, category_id: int, conn=Depends(get_conn)):
    """Make a personal category shared. Its history stays exactly as it was (100 % yours); sharing
    with others starts when they join, at a following joint period."""
    form = await request.form()
    uid, today = user_id(request), config.today()
    try:
        cat = _category(conn, uid, category_id)
        if cat["is_joint"]:
            raise Refused("It's already shared.")
        if cat["archived"]:
            raise Refused(f"“{cat['name']}” is archived. Unarchive it first if you want to share it.")
        _check_not_last_active(conn, cat, "turned into a shared category")
    except Refused as e:
        return render_page(request, conn, e.status, alert=str(e))
    if form.get("agree") != "1":
        return render_page(request, conn, 422, errors={"agree": "Tick the box to confirm."},
                           reopen=f"dlg-share-{category_id}")
    with conn:
        conn.execute("UPDATE categories SET is_joint = 1 WHERE id = ?", (category_id,))
        begin = joint.BEGINNING.isoformat()          # membership covers all its history
        conn.execute("INSERT INTO joint_members (category_id, user_id, role, joined_from, committed_until) "
                     "VALUES (?, ?, 'moderator', ?, ?)", (category_id, uid, begin, begin))
        joint.write_split(conn, category_id, joint.BEGINNING, {uid: joint.FULL})
        joint.reallocate_category(conn, category_id)
        joint.log(conn, category_id, uid, "created",
                  f"Turned the personal category “{cat['name']}” into a shared one")
    return redirect(f"/shared/{category_id}?done=converted")
