"""Recurring expenses page: set up, edit, pause / resume and delete rules."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request

from . import audit, config, db, forms, joint, recurring
from .web import get_conn, redirect, render, user_id

router = APIRouter(prefix="/recurring")

MESSAGES = {
    "added": "Recurring expense set up.",
    "saved": "Changes saved. Payments dated after today were updated.",
    "paused": "Paused. Payments dated after today were removed.",
    "resumed": "Resumed.",
    "deleted": "Recurring expense deleted. Payments already made stay in your log.",
}
FIELDS = ("description", "category_id", "amount", "notes", "every_months", "start_date", "end_date")


def _rules(conn, uid: int, today: date) -> list[dict]:
    rows = conn.execute(
        "SELECT r.*, c.name AS category, c.is_joint, c.archived,"
        " (SELECT COUNT(*) FROM expenses e WHERE e.recurring_id = r.id) AS n_made "
        "FROM recurring_expenses r JOIN categories c ON c.id = r.category_id "
        "WHERE r.user_id = ? ORDER BY r.active DESC, r.description COLLATE NOCASE, r.id", (uid,)).fetchall()
    out = []
    for r in rows:
        nxt = recurring.next_date(r, today) if r["active"] else None
        ended = r["end_date"] is not None and nxt is None and r["active"]
        blocked = None
        if r["archived"]:
            blocked = "Its category is archived, so no new payments are added."
        elif r["is_joint"] and joint.can_log_on(conn, r["category_id"], uid, today):
            blocked = "You're no longer a member of this shared category, so no new payments are added."
        out.append({**dict(r), "next": nxt, "ended": ended, "blocked": blocked,
                    "frequency": recurring.FREQUENCIES[r["every_months"]]})
    return out


def _own(conn, uid: int, rid: int):
    row = conn.execute("SELECT * FROM recurring_expenses WHERE id = ? AND user_id = ?", (rid, uid)).fetchone()
    if row is None:
        raise HTTPException(404, "Recurring expense not found")
    return row


def _validate(conn, uid: int, form, cats, *, schedule: bool, start: str | None = None):
    raw = {f: (form.get(f) or "").strip() for f in FIELDS}
    clean, errors = {}, {}
    fake = {"date": raw["start_date"] if schedule else start, **raw}
    c2, e2, _ = forms.validate_expense(fake, {c["id"] for c in cats})
    for k in ("description", "category_id", "amount_cents", "notes"):
        if k in c2:
            clean[k] = c2[k]
    for k in ("description", "category_id", "amount", "notes"):
        if k in e2:
            errors[k] = e2[k]
    if schedule:
        try:
            clean["every_months"] = int(raw["every_months"])
            if clean["every_months"] not in recurring.FREQUENCIES:
                raise ValueError
        except ValueError:
            errors["every_months"] = "Pick how often."
        try:
            clean["start_date"] = forms.parse_date(raw["start_date"]).isoformat()
        except ValueError:
            errors["start_date"] = "Enter a valid date."
    else:
        clean["start_date"] = start
    clean["end_date"] = None
    if raw["end_date"]:
        try:
            clean["end_date"] = forms.parse_date(raw["end_date"]).isoformat()
            if clean.get("start_date") and clean["end_date"] < clean["start_date"]:
                errors["end_date"] = "The last date can't be before the first payment."
        except ValueError:
            errors["end_date"] = "Enter a valid date, or leave it empty."
    # shared category: you must be a member from the first payment on
    cat = next((c for c in cats if c["id"] == clean.get("category_id")), None)
    if cat is not None and cat["is_joint"] and clean.get("start_date") and "start_date" not in errors:
        first = max(date.fromisoformat(clean["start_date"]), config.today()) if not schedule else \
            date.fromisoformat(clean["start_date"])
        reason = joint.can_log_on(conn, cat["id"], uid, first)
        if reason:
            errors["start_date" if schedule else "category_id"] = reason
    return clean, errors, raw


def _describe(conn, clean: dict) -> str:
    freq = recurring.FREQUENCIES[clean["every_months"]].lower()
    return (f"a recurring expense in {audit.category_name(conn, clean['category_id'])} "
            f"({freq} from {date.fromisoformat(clean['start_date']):%d %b %Y})")


def render_page(request: Request, conn, status_code: int = 200, *, errors=None, values=None):
    uid = user_id(request)
    today = config.today()
    code = request.query_params.get("done")
    return render(request, "recurring.html", status_code, active="recurring", rules=_rules(conn, uid, today),
                  categories=db.active_categories(conn, uid), frequencies=recurring.FREQUENCIES,
                  errors=errors or {}, values=values or {"start_date": today.isoformat(), "every_months": "1"},
                  message=MESSAGES.get(code or ""), until=recurring.horizon(conn, uid, today), back="/settings")


@router.get("")
def page(request: Request, conn=Depends(get_conn)):
    return render_page(request, conn)


@router.post("")
async def add(request: Request, conn=Depends(get_conn)):
    uid = user_id(request)
    cats = db.active_categories(conn, uid)
    clean, errors, raw = _validate(conn, uid, await request.form(), cats, schedule=True)
    if errors:
        return render_page(request, conn, 422, errors=errors, values=raw)
    with conn:
        conn.execute(
            "INSERT INTO recurring_expenses (user_id, description, category_id, amount_cents, notes, every_months,"
            " start_date, end_date) VALUES (:uid, :description, :category_id, :amount_cents, :notes, :every_months,"
            " :start_date, :end_date)", {**clean, "uid": uid})
        audit.log(conn, uid, "expense.recurring_added", "Set up " + _describe(conn, clean),
                  category_id=clean["category_id"])
    recurring.catch_up(conn, uid, config.today())
    return redirect("/recurring?done=added")


@router.get("/{rid}/edit")
def edit_page(request: Request, rid: int, conn=Depends(get_conn)):
    uid = user_id(request)
    r = _own(conn, uid, rid)
    values = {"description": r["description"], "category_id": str(r["category_id"]),
              "amount": forms.cents_to_input(r["amount_cents"]), "notes": r["notes"], "end_date": r["end_date"] or ""}
    return render(request, "recurring_edit.html", rule=r, values=values, errors={},
                  categories=db.categories_for_select(conn, uid, r["category_id"]),
                  frequency=recurring.FREQUENCIES[r["every_months"]], back="/recurring")


@router.post("/{rid}/edit")
async def edit(request: Request, rid: int, conn=Depends(get_conn)):
    uid = user_id(request)
    r = _own(conn, uid, rid)
    cats = db.categories_for_select(conn, uid, r["category_id"])
    clean, errors, raw = _validate(conn, uid, await request.form(), cats, schedule=False, start=r["start_date"])
    if errors:
        return render(request, "recurring_edit.html", 422, rule=r, values=raw, errors=errors, categories=cats,
                      frequency=recurring.FREQUENCIES[r["every_months"]], back="/recurring")
    today = config.today()
    with conn:
        conn.execute("UPDATE recurring_expenses SET description = :description, category_id = :category_id,"
                     " amount_cents = :amount_cents, notes = :notes, end_date = :end_date WHERE id = :id",
                     {**clean, "id": rid})
        recurring.drop_future(conn, r, today)
        audit.log(conn, uid, "expense.recurring_edited",
                  "Edited " + _describe(conn, {**clean, "every_months": r["every_months"]}),
                  category_id=clean["category_id"])
    recurring.catch_up(conn, uid, today)
    return redirect("/recurring?done=saved")


@router.post("/{rid}/pause")
def pause(request: Request, rid: int, conn=Depends(get_conn)):
    uid = user_id(request)
    r = _own(conn, uid, rid)
    with conn:
        recurring.drop_future(conn, r, config.today())
        conn.execute("UPDATE recurring_expenses SET active = 0 WHERE id = ?", (rid,))
        audit.log(conn, uid, "expense.recurring_paused", "Paused " + _describe(conn, r), category_id=r["category_id"])
    return redirect("/recurring?done=paused")


@router.post("/{rid}/resume")
def resume(request: Request, rid: int, conn=Depends(get_conn)):
    uid = user_id(request)
    r = _own(conn, uid, rid)
    today = config.today()
    with conn:
        # payments missed while paused are skipped; today's, if any, is made
        k = max(r["next_index"], recurring.first_index_after(r, today, inclusive=True))
        conn.execute("UPDATE recurring_expenses SET active = 1, next_index = ? WHERE id = ?", (k, rid))
        audit.log(conn, uid, "expense.recurring_resumed", "Resumed " + _describe(conn, r), category_id=r["category_id"])
    recurring.catch_up(conn, uid, today)
    return redirect("/recurring?done=resumed")


@router.post("/{rid}/delete")
def delete(request: Request, rid: int, conn=Depends(get_conn)):
    uid = user_id(request)
    r = _own(conn, uid, rid)
    with conn:
        recurring.drop_future(conn, r, config.today())
        conn.execute("DELETE FROM recurring_expenses WHERE id = ?", (rid,))
        audit.log(conn, uid, "expense.recurring_deleted", "Deleted " + _describe(conn, r), category_id=r["category_id"])
    return redirect("/recurring?done=deleted")
