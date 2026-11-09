"""Planned purchases: add / edit / reorder / delete, "bought it", and the savings forecast."""
from __future__ import annotations

import sqlite3
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request

from . import config, db, forecast
from .money import cents_to_input, parse_amount
from .web import get_conn, redirect, render, user_id

router = APIRouter(prefix="/plans")

MAX_NAME = 80
MAX_NOTES = 500
GONE = "That plan no longer exists. It may have been changed in another tab."
MESSAGES = {"added": "Plan added.", "saved": "Plan saved.", "deleted": "Plan deleted."}


def _plans(conn, uid: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT p.*, c.name AS category FROM planned_purchases p LEFT JOIN categories c ON c.id = p.category_id "
        "WHERE p.user_id = ? ORDER BY p.sort_order, p.id", (uid,)).fetchall()


def _own(conn, uid: int, plan_id: int):
    return conn.execute("SELECT * FROM planned_purchases WHERE id = ? AND user_id = ?", (plan_id, uid)).fetchone()


def render_page(request: Request, conn, status_code: int = 200, *, errors=None, values=None,
                reopen=None, alert=None):
    uid = user_id(request)
    plans = _plans(conn, uid)
    fc = forecast.forecast(conn, uid, config.today())
    code = request.query_params.get("done")
    return render(request, "plans.html", status_code, active="plans", fc=fc,
                  placed=forecast.place_plans(conn, uid, fc, plans),
                  categories=db.categories_for_select(conn, uid, None),
                  errors=errors or {}, values=values or {}, reopen=reopen, alert=alert,
                  message=MESSAGES.get(code) if status_code == 200 else None)


def _validate(conn, uid: int, form) -> tuple[dict, dict, dict]:
    raw = {k: (form.get(k) or "").strip() for k in ("name", "amount", "saved", "category_id", "notes")}
    clean, errors = {}, {}
    name = " ".join(raw["name"].split())
    if not name:
        errors["name"] = "What do you want to buy?"
    elif len(name) > MAX_NAME:
        errors["name"] = f"Keep it under {MAX_NAME} characters."
    clean["name"] = name
    try:
        clean["amount_cents"] = parse_amount(raw["amount"])
        if clean["amount_cents"] <= 0:
            errors["amount"] = "The price must be more than zero."
    except ValueError as e:
        errors["amount"] = str(e)
    clean["saved_cents"] = 0
    if raw["saved"]:
        try:
            clean["saved_cents"] = parse_amount(raw["saved"])
            if "amount" not in errors and clean["saved_cents"] > clean["amount_cents"]:
                errors["saved"] = "That's more than the price."
        except ValueError as e:
            errors["saved"] = str(e)
    clean["category_id"] = None
    if raw["category_id"]:
        allowed = {c["id"] for c in db.categories_for_select(conn, uid, None)}
        try:
            cid = int(raw["category_id"])
            if cid not in allowed:
                raise ValueError
            clean["category_id"] = cid
        except ValueError:
            errors["category_id"] = "Pick one of your categories (or none)."
    if len(raw["notes"]) > MAX_NOTES:
        errors["notes"] = f"Keep it under {MAX_NOTES} characters."
    clean["notes"] = raw["notes"]
    return clean, errors, raw


@router.get("")
def plans_page(request: Request, conn=Depends(get_conn)):
    return render_page(request, conn)


@router.post("")
async def add_plan(request: Request, conn=Depends(get_conn)):
    uid = user_id(request)
    clean, errors, raw = _validate(conn, uid, await request.form())
    if errors:
        return render_page(request, conn, 422, errors=errors, values=raw, reopen="dlg-plan-add")
    with conn:
        conn.execute(
            "INSERT INTO planned_purchases (user_id, name, amount_cents, saved_cents, category_id, notes, sort_order) "
            "VALUES (?, ?, ?, ?, ?, ?, (SELECT COALESCE(MAX(sort_order), 0) + 1 FROM planned_purchases WHERE user_id = ?))",
            (uid, clean["name"], clean["amount_cents"], clean["saved_cents"], clean["category_id"], clean["notes"], uid))
    return redirect("/plans?done=added")


@router.post("/{plan_id}/edit")
async def edit_plan(request: Request, plan_id: int, conn=Depends(get_conn)):
    uid = user_id(request)
    if _own(conn, uid, plan_id) is None:
        return render_page(request, conn, 404, alert=GONE)
    clean, errors, raw = _validate(conn, uid, await request.form())
    if errors:
        return render_page(request, conn, 422, errors=errors, values=raw, reopen=f"dlg-plan-edit-{plan_id}")
    with conn:
        conn.execute("UPDATE planned_purchases SET name = ?, amount_cents = ?, saved_cents = ?, category_id = ?, "
                     "notes = ? WHERE id = ? AND user_id = ?",
                     (clean["name"], clean["amount_cents"], clean["saved_cents"], clean["category_id"],
                      clean["notes"], plan_id, uid))
    return redirect("/plans?done=saved")


@router.post("/{plan_id}/move")
async def move_plan(request: Request, plan_id: int, conn=Depends(get_conn)):
    uid = user_id(request)
    ids = [r[0] for r in conn.execute("SELECT id FROM planned_purchases WHERE user_id = ? ORDER BY sort_order, id",
                                      (uid,))]
    if plan_id not in ids:
        return render_page(request, conn, 404, alert=GONE)
    i = ids.index(plan_id)
    j = i + (-1 if (await request.form()).get("direction") == "up" else 1)
    if 0 <= j < len(ids):
        ids[i], ids[j] = ids[j], ids[i]
        with conn:
            conn.executemany("UPDATE planned_purchases SET sort_order = ? WHERE id = ?",
                             [(n, pid) for n, pid in enumerate(ids, start=1)])
    return redirect(f"/plans#plan-{plan_id}")


@router.post("/{plan_id}/delete")
def delete_plan(request: Request, plan_id: int, conn=Depends(get_conn)):
    uid = user_id(request)
    if _own(conn, uid, plan_id) is None:
        return render_page(request, conn, 404, alert=GONE)
    with conn:
        conn.execute("DELETE FROM planned_purchases WHERE id = ? AND user_id = ?", (plan_id, uid))
    return redirect("/plans?done=deleted")


@router.post("/{plan_id}/bought")
def bought(request: Request, plan_id: int, conn=Depends(get_conn)):
    """Remove the plan and open Add expense pre-filled with it (marked one-off)."""
    uid = user_id(request)
    plan = _own(conn, uid, plan_id)
    if plan is None:
        return render_page(request, conn, 404, alert=GONE)
    with conn:
        conn.execute("DELETE FROM planned_purchases WHERE id = ? AND user_id = ?", (plan_id, uid))
    query = {"description": plan["name"], "amount": cents_to_input(plan["amount_cents"]), "one_off": "1",
             "from_plan": "1"}
    if plan["category_id"]:
        query["category_id"] = plan["category_id"]
    return redirect("/add?" + urlencode(query))
