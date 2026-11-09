"""Quick add (phone): a small sheet over the current page for adding an expense or extra income
in a few taps. The sheet loads its data from GET /quick-add/data and saves with POST /quick-add,
both as JSON. Without JavaScript the menu link simply opens the full Add expense page.
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from . import audit, config, db, forms, joint, recurring
from .money import format_eur
from .web import get_conn, user_id

router = APIRouter(prefix="/quick-add")

TOP_N = 5              # category buttons; the rest are under "More"
TOP_DAYS = 90          # "most used" looks at this many days back
INCOME_DESCRIPTION = "Extra income"


def _data(conn, uid: int, today: date) -> dict:
    cats = db.active_categories(conn, uid)
    ids = {c["id"] for c in cats}
    counts = conn.execute(
        "SELECT category_id, COUNT(*) AS n, MAX(created_at) AS last FROM expenses "
        "WHERE user_id = ? AND date >= ? GROUP BY category_id ORDER BY n DESC, last DESC",
        (uid, (today - timedelta(days=TOP_DAYS)).isoformat())).fetchall()
    top = [r["category_id"] for r in counts if r["category_id"] in ids][:TOP_N]
    if len(top) < TOP_N:                       # not much history yet: fill up in your own order
        top += [c["id"] for c in cats if c["id"] not in top][:TOP_N - len(top)]
    last = conn.execute(
        "SELECT category_id FROM expenses WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
        (uid,)).fetchone()
    last_id = last["category_id"] if last and last["category_id"] in ids else (top[0] if top else None)
    return {
        "categories": [{"id": c["id"], "name": c["name"], "joint": bool(c["is_joint"])} for c in cats],
        "top": top,
        "last": last_id,
        "today": today.isoformat(),
        "yesterday": (today - timedelta(days=1)).isoformat(),
    }


@router.get("/data")
def data(request: Request, conn=Depends(get_conn)):
    return JSONResponse(_data(conn, user_id(request), config.today()), headers={"Cache-Control": "no-store"})


def save_values(conn, uid: int, form, via: str = "quick add") -> tuple[int, dict]:
    """Save a quick expense or income from form-like values. Returns (HTTP status, JSON body).
    Used by the phone's quick-add sheet (via names the source in the activity log)."""
    kind = form.get("kind") or "expense"
    if kind == "income":
        values = {f: (form.get(f) or "").strip() for f in ("date", "amount", "description")}
        values["description"] = values["description"] or INCOME_DESCRIPTION
        values["notes"] = ""
        clean, errors, _ = forms.validate_income(values)
        if errors:
            return 422, {"errors": errors}
        with conn:
            conn.execute(
                "INSERT INTO extra_income (user_id, date, description, amount_cents, notes) "
                "VALUES (:uid, :date, :description, :amount_cents, '')", {**clean, "uid": uid})
            audit.log(conn, uid, "income.extra_added",
                      f"Added extra income (dated {date.fromisoformat(clean['date']):%d %b %Y}, {via})")
        return 200, {"message": f"Saved {format_eur(clean['amount_cents'])} income", "kind": "income",
                     "cents": clean["amount_cents"]}

    cats = db.active_categories(conn, uid)
    values = {f: (form.get(f) or "").strip() for f in ("date", "amount", "description", "category_id")}
    try:
        cat = next((c for c in cats if c["id"] == int(values["category_id"])), None)
    except ValueError:
        cat = None
    if not values["description"] and cat is not None:
        values["description"] = cat["name"]                 # empty description: the category's name
    values.update(notes="", one_off="")
    clean, errors, _ = forms.validate_expense(values, {c["id"] for c in cats})
    if not errors and cat["is_joint"]:
        reason = joint.can_log_on(conn, cat["id"], uid, date.fromisoformat(clean["date"]))
        if reason:
            errors["date"] = reason
    if errors:
        return 422, {"errors": errors}
    with conn:
        recurring.insert_expense(conn, uid, clean)
        audit.log(conn, uid, "expense.added", "Added " + joint.describe_expense(conn, clean) + f" ({via})",
                  category_id=clean["category_id"])
    return 200, {"message": f"Saved {format_eur(clean['amount_cents'])} · {cat['name']}", "kind": "expense",
                 "cents": clean["amount_cents"]}


@router.post("")
async def save(request: Request, conn=Depends(get_conn)):
    status, body = save_values(conn, user_id(request), await request.form())
    return JSONResponse(body, status_code=status)
