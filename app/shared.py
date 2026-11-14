"""Pages and actions for shared (joint) categories. Rules live in app/joint.py.

Everything takes effect on the day it happens:
* the moderator invites by exact username, rearranges shares, removes members, hands over
  moderation, renames the category (Categories page) and can close it;
* members accept or decline invitations and can leave;
* budgets are personal: each member sets their own on the Categories page.
After leaving (or being removed, or a close) the category is archived for that person: its past
expenses stay in their history, and they can't add new ones.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request

from . import config, db, joint, period, summary
from .money import parse_amount
from .web import get_conn, redirect, render, user_id

router = APIRouter(prefix="/shared")

GONE = "That shared category no longer exists, or you're no longer a member of it."
MESSAGES = {
    "invited": "Invitation sent to {name}.",
    "invite_cancelled": "Invitation cancelled.",
    "shares": "New shares saved. They apply to expenses dated from today on; earlier ones keep their split.",
    "removed": "{name} has been removed. Their past expenses stay; new expenses are split among the remaining members.",
    "handover": "{name} is now the moderator.",
    "joined": "You've joined. Expenses dated from today on are split with you.",
    "converted": "It's now a shared category. Its past expenses stay 100 % yours; invite people below.",
}
TITLES = {"shares": "Shares updated", "removed": "Member removed", "joined": "Welcome"}


class Refused(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


def done(cid: int, code: str, **kw):
    return redirect(f"/shared/{cid}?" + urlencode({"done": code, **kw}))


def _load(conn, cid: int, uid: int, today: date, *, moderator: bool = False):
    """The category and the user's membership, or Refused (404) if they can't see it."""
    cat = joint.category(conn, cid)
    m = joint.membership(conn, cid, uid) if cat else None
    if cat is None or m is None or joint.status(m, today) == "left":
        raise Refused(GONE, 404)
    if moderator and m["role"] != "moderator":
        raise Refused("Only the moderator can do that.", 403)
    return cat, m


def _pct(bp: int | None) -> str:
    return "—" if bp is None else f"{bp / 100:.2f}".rstrip("0").rstrip(".")


def archive_name(conn, cat) -> str:
    """'<name> (archived)', unique among the owner's categories, so the name can be reused."""
    base, n = f"{cat['name']} (archived)", 2
    name = base
    while conn.execute("SELECT 1 FROM categories WHERE user_id = ? AND name = ? COLLATE NOCASE AND id != ?",
                       (cat["user_id"], name, cat["id"])).fetchone():
        name, n = f"{base} {n}", n + 1
    return name


# --- page ---------------------------------------------------------------------------------

def render_page(request: Request, conn, cid: int, status_code: int = 200, *, alert=None, errors=None,
                values=None, reopen=None):
    uid, today = user_id(request), config.today()
    try:
        cat, me = _load(conn, cid, uid, today)
    except Refused as e:
        return render(request, "shared_gone.html", e.status, active="categories", alert=str(e))
    # "This period" = the viewer's own current period: shared expenses count there like any other.
    start, end = summary.get_period_rule(conn, uid).current_bounds(today)
    split = joint.split_at(conn, cid, today)
    expenses = conn.execute(
        "SELECT e.*, u.display_name AS paid_by FROM expenses e JOIN users u ON u.id = e.user_id "
        "WHERE e.category_id = ? AND e.date BETWEEN ? AND ? ORDER BY e.date DESC, e.id DESC",
        (cid, start.isoformat(), end.isoformat())).fetchall()
    my_cost = conn.execute(
        "SELECT COALESCE(SUM(s.cents), 0) FROM expense_shares s JOIN expenses e ON e.id = s.expense_id "
        "WHERE s.user_id = ? AND e.category_id = ? AND e.date BETWEEN ? AND ?",
        (uid, cid, start.isoformat(), end.isoformat())).fetchone()[0]
    ms = []
    for m in joint.members(conn, cid):
        if joint.status(m, today) == "left":
            continue
        ms.append({**dict(m), "share": split.get(m["user_id"]),
                   "paid": sum(e["amount_cents"] for e in expenses if e["user_id"] == m["user_id"])})
    invites = conn.execute(
        "SELECT i.*, u.username, u.display_name FROM joint_invites i JOIN users u ON u.id = i.user_id "
        "WHERE i.category_id = ? AND i.expires_at >= ? ORDER BY i.created_at", (cid, today.isoformat())).fetchall()
    code = request.query_params.get("done")
    message = None
    if code in MESSAGES and status_code == 200:
        message = MESSAGES[code].format(name=request.query_params.get("name", ""))
    return render(
        request, "shared.html", status_code, active="categories", cat=cat, me=dict(me),
        is_mod=me["role"] == "moderator", members=ms, invites=invites, expenses=expenses,
        total=sum(e["amount_cents"] for e in expenses), my_cost=my_cost,
        my_budget=db.budget_of(conn, cid, uid, end), my_share=split.get(uid),
        period_range=period.range_label(start, end),
        others=[m for m in ms if m["user_id"] != uid],
        message=message, notice_title=TITLES.get(code), alert=alert, errors=errors or {}, values=values or {},
        reopen=reopen, pct=_pct, max_members=joint.MAX_MEMBERS,
    )


@router.get("/{cid}")
def shared_page(request: Request, cid: int, conn=Depends(get_conn)):
    return render_page(request, conn, cid)


def _act(request, conn, cid, fn, **kw):
    """Run an action; show its refusal as an error pop-up."""
    try:
        return fn()
    except Refused as e:
        return render_page(request, conn, cid, e.status, alert=str(e), **kw)


# --- moderator: invitations -----------------------------------------------------------------

@router.post("/{cid}/invite")
async def invite(request: Request, cid: int, conn=Depends(get_conn)):
    uid, today = user_id(request), config.today()
    username = ((await request.form()).get("username") or "").strip().lower()

    def go():
        _load(conn, cid, uid, today, moderator=True)
        target = conn.execute("SELECT id, display_name, status FROM users WHERE username = ?", (username,)).fetchone()
        error = None
        if not username:
            error = "Type the person's username."
        elif target is None or target["status"] != "active":
            error = f"There's no active account called “{username}”. Check the spelling with them."
        elif target["id"] == uid:
            error = "You're already in it."
        elif joint.status(joint.membership(conn, cid, target["id"]), today) != "left":
            error = f"{target['display_name']} is already a member."
        elif conn.execute("SELECT 1 FROM joint_invites WHERE category_id = ? AND user_id = ? AND expires_at >= ?",
                          (cid, target["id"], today.isoformat())).fetchone():
            error = f"{target['display_name']} already has an invitation waiting."
        else:
            pending = conn.execute("SELECT COUNT(*) FROM joint_invites WHERE category_id = ? AND expires_at >= ?",
                                   (cid, today.isoformat())).fetchone()[0]
            if joint.current_member_count(conn, cid, today) + pending >= joint.MAX_MEMBERS:
                error = f"A shared category can have at most {joint.MAX_MEMBERS} members (invitations included)."
        if error:
            return render_page(request, conn, cid, 422, errors={"username": error}, values={"username": username},
                               reopen="dlg-invite")
        with conn:
            conn.execute("DELETE FROM joint_invites WHERE category_id = ? AND user_id = ?", (cid, target["id"]))
            conn.execute("INSERT INTO joint_invites (category_id, user_id, invited_by, expires_at) VALUES (?, ?, ?, ?)",
                         (cid, target["id"], uid, (today + timedelta(days=joint.INVITE_DAYS)).isoformat()))
            joint.log(conn, cid, uid, "invite", f"Invited {target['display_name']} ({username})")
        return done(cid, "invited", name=target["display_name"])
    return _act(request, conn, cid, go)


@router.post("/{cid}/invites/{invite_id}/cancel")
def cancel_invite(request: Request, cid: int, invite_id: int, conn=Depends(get_conn)):
    uid, today = user_id(request), config.today()

    def go():
        _load(conn, cid, uid, today, moderator=True)
        with conn:
            inv = conn.execute("SELECT u.display_name FROM joint_invites i JOIN users u ON u.id = i.user_id "
                               "WHERE i.id = ? AND i.category_id = ?", (invite_id, cid)).fetchone()
            n = conn.execute("DELETE FROM joint_invites WHERE id = ? AND category_id = ?", (invite_id, cid)).rowcount
            if n:
                joint.log(conn, cid, uid, "invite_cancelled", f"Cancelled the invitation to {inv[0]}")
        if not n:
            raise Refused("That invitation no longer exists (it may have been answered).", 404)
        return done(cid, "invite_cancelled")
    return _act(request, conn, cid, go)


# --- invitee: accept / decline ----------------------------------------------------------------

@router.post("/invites/{invite_id}/accept")
async def accept(request: Request, invite_id: int, conn=Depends(get_conn)):
    uid, today = user_id(request), config.today()
    form = await request.form()
    back = form.get("back") if form.get("back") in ("/", "/categories") else "/categories"
    inv = conn.execute("SELECT * FROM joint_invites WHERE id = ? AND user_id = ? AND expires_at >= ?",
                       (invite_id, uid, today.isoformat())).fetchone()
    if inv is None:
        return redirect(back + "?invite=gone")
    if form.get("agree") != "1":
        return redirect(back + "?invite=agree")
    budget = None
    if (form.get("budget") or "").strip():
        try:
            budget = parse_amount(form.get("budget"))
        except ValueError:
            return redirect(back + "?invite=budget")
    cid = inv["category_id"]
    if joint.current_member_count(conn, cid, today) >= joint.MAX_MEMBERS:
        with conn:
            conn.execute("DELETE FROM joint_invites WHERE id = ?", (invite_id,))
        return redirect(back + "?invite=full")
    with conn:
        conn.execute("DELETE FROM joint_members WHERE category_id = ? AND user_id = ?", (cid, uid))  # an old, ended membership
        conn.execute("INSERT INTO joint_members (category_id, user_id, role, joined_from, committed_until) "
                     "VALUES (?, ?, 'member', ?, ?)", (cid, uid, today.isoformat(), today.isoformat()))
        conn.execute("DELETE FROM joint_invites WHERE id = ?", (invite_id,))
        joint.rebuild_from(conn, cid, today)
        if budget:
            from .categories import _set_budget
            _set_budget(conn, cid, budget, today.isoformat(), uid)
        joint.log(conn, cid, uid, "joined", "Accepted the invitation and joined")
    return redirect(f"/shared/{cid}?done=joined")


@router.post("/invites/{invite_id}/decline")
async def decline(request: Request, invite_id: int, conn=Depends(get_conn)):
    uid = user_id(request)
    form = await request.form()
    back = form.get("back") if form.get("back") in ("/", "/categories") else "/categories"
    with conn:
        inv = conn.execute("SELECT category_id FROM joint_invites WHERE id = ? AND user_id = ?", (invite_id, uid)).fetchone()
        n = conn.execute("DELETE FROM joint_invites WHERE id = ? AND user_id = ?", (invite_id, uid)).rowcount
        if n:
            joint.log(conn, inv[0], uid, "declined", "Declined the invitation")
    return redirect(back + ("?invite=declined" if n else "?invite=gone"))


# --- moderator: shares ------------------------------------------------------------------------

@router.post("/{cid}/shares")
async def set_shares(request: Request, cid: int, conn=Depends(get_conn)):
    uid, today = user_id(request), config.today()
    form = await request.form()

    def go():
        _load(conn, cid, uid, today, moderator=True)
        members = [m for m in joint.members(conn, cid) if joint.is_member_on(m, today)]
        split, raw, error = {}, {}, None
        for m in members:
            key = f"share_{m['user_id']}"
            raw[key] = (form.get(key) or "").strip().replace(",", ".")
            try:
                value = Decimal(raw[key] or "x")
                if value < 0 or value > 100 or value != value.quantize(Decimal("0.01")):
                    raise InvalidOperation
                split[m["user_id"]] = int(value * 100)
            except InvalidOperation:
                error = f"{m['display_name']}: enter a percentage from 0 to 100 with at most 2 decimals."
        if error is None and sum(split.values()) != joint.FULL:
            error = f"The shares add up to {sum(split.values()) / 100:.2f}%; they must add up to exactly 100%."
        if error:
            return render_page(request, conn, cid, 422, errors={"shares": error}, values=raw, reopen="dlg-shares",
                               alert=error)
        with conn:
            joint.write_split(conn, cid, today, split)
            joint.rebuild_from(conn, cid, today + timedelta(days=1))
            names = {m["user_id"]: m["display_name"] for m in members}
            joint.log(conn, cid, uid, "shares", "Set shares: " + ", ".join(
                f"{names[u]} {_pct(bp)} %" for u, bp in sorted(split.items(), key=lambda x: -x[1])), today)
        return done(cid, "shares")
    return _act(request, conn, cid, go)


# --- leaving / removing / closing ----------------------------------------------------------------

def end_membership(conn, cid: int, member_id: int, today: date, kind: str) -> None:
    """From today on the person is out: membership ends yesterday, split redone from today."""
    conn.execute("UPDATE joint_members SET leaves_after = ?, leave_kind = ? WHERE category_id = ? AND user_id = ?",
                 ((today - timedelta(days=1)).isoformat(), kind, cid, member_id))
    joint.rebuild_from(conn, cid, today)


def close_if_empty(conn, cat, today: date) -> bool:
    """With nobody left, archive the category (renamed so its name can be reused)."""
    if joint.current_member_count(conn, cat["id"], today):
        return False
    conn.execute("UPDATE categories SET archived = 1, name = ? WHERE id = ?", (archive_name(conn, cat), cat["id"]))
    conn.execute("DELETE FROM joint_invites WHERE category_id = ?", (cat["id"],))
    return True


@router.post("/{cid}/members/{member_id}/remove")
def remove_member(request: Request, cid: int, member_id: int, conn=Depends(get_conn)):
    uid, today = user_id(request), config.today()

    def go():
        _load(conn, cid, uid, today, moderator=True)
        if member_id == uid:
            raise Refused("You can't remove yourself. Hand over moderation first, or close the category.")
        m = joint.membership(conn, cid, member_id)
        if joint.status(m, today) == "left":
            raise Refused("That person isn't a member any more.", 404)
        name = conn.execute("SELECT display_name FROM users WHERE id = ?", (member_id,)).fetchone()[0]
        with conn:
            end_membership(conn, cid, member_id, today, "removed")
            joint.log(conn, cid, uid, "remove", f"Removed {name}")
        return done(cid, "removed", name=name)
    return _act(request, conn, cid, go)


@router.post("/{cid}/leave")
def leave(request: Request, cid: int, conn=Depends(get_conn)):
    uid, today = user_id(request), config.today()

    def go():
        cat, m = _load(conn, cid, uid, today)
        others = [x for x in joint.members(conn, cid) if x["user_id"] != uid and joint.status(x, today) != "left"]
        if m["role"] == "moderator" and others:
            raise Refused("As moderator, hand over moderation to another member first (or close the category).")
        with conn:
            end_membership(conn, cid, uid, today, "left")
            joint.log(conn, cid, uid, "leave", "Left the shared category")
            close_if_empty(conn, cat, today)
        return redirect("/categories?" + urlencode({"done": "left", "name": cat["name"]}))
    return _act(request, conn, cid, go)


@router.post("/{cid}/handover")
async def handover(request: Request, cid: int, conn=Depends(get_conn)):
    uid, today = user_id(request), config.today()
    form = await request.form()

    def go():
        _load(conn, cid, uid, today, moderator=True)
        try:
            target = int(form.get("member") or 0)
        except ValueError:
            target = 0
        m = joint.membership(conn, cid, target)
        if m is None or target == uid or joint.status(m, today) == "left":
            raise Refused("Choose a current member to hand over to.")
        with conn:
            conn.execute("UPDATE joint_members SET role = 'member' WHERE category_id = ? AND user_id = ?", (cid, uid))
            conn.execute("UPDATE joint_members SET role = 'moderator' WHERE category_id = ? AND user_id = ?", (cid, target))
            conn.execute("UPDATE categories SET user_id = ? WHERE id = ?", (target, cid))
            name = conn.execute("SELECT display_name FROM users WHERE id = ?", (target,)).fetchone()[0]
            joint.log(conn, cid, uid, "handover", f"Handed over moderation to {name}")
        return done(cid, "handover", name=name)
    return _act(request, conn, cid, go)


@router.post("/{cid}/close")
def close(request: Request, cid: int, conn=Depends(get_conn)):
    """Everyone leaves today; the category is archived for all, its history stays."""
    uid, today = user_id(request), config.today()

    def go():
        cat, _ = _load(conn, cid, uid, today, moderator=True)
        with conn:
            for m in joint.members(conn, cid):
                if joint.status(m, today) != "left":
                    conn.execute("UPDATE joint_members SET leaves_after = ?, leave_kind = 'closed' "
                                 "WHERE category_id = ? AND user_id = ?",
                                 ((today - timedelta(days=1)).isoformat(), cid, m["user_id"]))
            joint.rebuild_from(conn, cid, today)
            close_if_empty(conn, cat, today)
            joint.log(conn, cid, uid, "close", "Closed the shared category; it's archived for everyone")
        return redirect("/categories?" + urlencode({"done": "closed", "name": cat["name"]}))
    return _act(request, conn, cid, go)
