"""The KDE widget's side of the app.

* /api/...  : JSON for the widget, authorised by a device token ("Authorization: Bearer svw_…",
              see main.create_app). Read-only: the token owner's own summary. The widget's
              "Open Savings" just opens the site in the browser, which uses its own login cookie.
* /profile/widget-tokens: create / revoke tokens from Settings (normal browser login).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from . import account, audit, auth, config, joint, summary
from .money import format_eur
from .web import get_conn, redirect, user_id

router = APIRouter()

# /api/summary generation. Within one generation fields are only ever added (older widgets ignore
# them); renaming or removing anything means API_VERSION + 1, and widgets older than that show
# "update the widget" (widget/package/contents/ui/main.qml, apiVersion).
API_VERSION = 1
MAX_TOKENS = 20


TREND_PERIODS = (3, 6, 12)          # the widget's "Spent vs income" can show this many periods


NOTIFY_DAYS = 14          # shared-category events this recent are offered to the widget
RECURRING_DAYS = 3       # ... and recurring payments created this recently


def _notifications(conn, uid: int, today, d: dict) -> list[dict]:
    """Things the widget may turn into desktop notifications. Each has a stable id, so the widget
    shows it once: {id, type, title, body, url}. type is invite, shared, reset, recurring or budget."""
    out = []
    for i in joint.pending_invites(conn, uid, today):
        out.append({"id": f"invite-{i['id']}", "type": "invite",
                    "title": f"Invitation to “{i['name']}”",
                    "body": f"{i['moderator']} invited you to share “{i['name']}”. Open Savings to accept or decline.",
                    "url": "/"})
    since = (datetime.now(timezone.utc) - timedelta(days=NOTIFY_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for r in conn.execute(
            "SELECT l.id, l.kind, l.detail, l.actor_name, l.category_id, c.name FROM activity_log l "
            "JOIN categories c ON c.id = l.category_id "
            "JOIN joint_members jm ON jm.category_id = l.category_id AND jm.user_id = :uid "
            "WHERE l.kind LIKE 'shared.%' AND l.created_at >= :since AND l.actor_id IS NOT :uid "
            "AND substr(l.created_at, 1, 10) >= jm.joined_from "
            "AND (jm.leaves_after IS NULL OR substr(l.created_at, 1, 10) <= jm.leaves_after) "
            "ORDER BY l.id", {"uid": uid, "since": since}):
        detail = r["detail"][:1].lower() + r["detail"][1:]
        out.append({"id": f"log-{r['id']}", "type": "shared", "title": r["name"],
                    "body": f"{r['actor_name']} {detail}.", "url": f"/shared/{r['category_id']}"})
    reset = summary.reset_notice(conn, uid, today)
    if reset:
        days = reset["days"]
        out.append({"id": f"reset-{reset['key']}", "type": "reset", "title": "Your budget period resets soon",
                    "body": f"A new period starts in {days} day{'' if days == 1 else 's'} ({reset['resets']:%d %b}).",
                    "url": "/"})
    since = (datetime.now(timezone.utc) - timedelta(days=RECURRING_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for e in conn.execute(
            "SELECT e.id, e.date, e.description, e.amount_cents FROM expenses e "
            "WHERE e.user_id = ? AND e.recurring_id IS NOT NULL AND e.created_at >= ? ORDER BY e.date, e.id", (uid, since)):
        out.append({"id": f"recurring-{e['id']}", "type": "recurring", "title": f"{e['description']} added",
                    "body": f"Recurring payment of {format_eur(e['amount_cents'])}, dated "
                            f"{datetime.fromisoformat(e['date']):%d %b}.", "url": "/recurring"})
    for c in d["watch"]:
        if c["pct"] is None or c["pct"] < 90:
            continue
        over = c["spent"] > c["budget"]
        out.append({"id": f"budget-{'over' if over else '90'}-{c['id']}-{d['key']}", "type": "budget",
                    "title": f"{c['name']} is over budget" if over else f"{c['name']} is at {int(c['pct'])}% of its budget",
                    "body": f"{format_eur(c['spent'])} of {format_eur(c['budget'])} this period.",
                    "url": f"/month?period={d['key']}"})
    return out


def _vs_budget(vb: dict) -> dict:
    """Savings vs budget for the widget's Budget tab (cents; pace in euros, like the charts)."""
    return {"budget": vb["budget"], "balance": vb["balance"], "projected": vb["projected"],
            "planned": vb["planned"], "allowed": vb["allowed"], "daily": vb["daily"], "fixed": vb["fixed"],
            "day": vb["day"], "days": vb["days"],
            "categories": [{k: c[k] for k in ("name", "joint", "budget", "spent", "fixed", "daily", "allowed", "balance")}
                           for c in vb["categories"]],
            # actual/allowed: cumulative vs even spread (widgets up to 1.5.1); spent/available/rate:
            # per day vs what that day had available (widget 1.6.0+). Additive, so API_VERSION stays.
            "pace": {k: vb["pace"][k] for k in ("actual", "allowed", "spent", "available", "rate")}}


def _summary(conn, user, today, periods: int = 6) -> dict:
    uid = user["id"]
    d = summary.dashboard(conn, uid, today, history=periods)
    s = d["s"]
    return {
        "api": API_VERSION,
        "user": user["display_name"],
        "username": user["username"],
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "currency": "EUR",
        "period": {"label": d["label"], "key": d["key"], "range": s["range"],
                   "days_total": d["days_total"], "days_left": d["days_left"],
                   "day": d["days_total"] - d["days_left"] + 1},
        "left": s["left"], "per_day": d["per_day"], "income": s["income"], "spent": s["spent"],
        "future": s["future"], "budget": s["budget"], "budget_pct": s["budget_pct"],
        "budgets": [{"name": c["name"], "joint": c["joint"], "spent": c["spent"], "budget": c["budget"],
                     "pct": c["pct"], "status": c["status"]} for c in d["watch"]],
        "recent": [{"date": r["date"], "description": r["description"], "category": r["category"],
                    "joint": bool(r["is_joint"]), "cents": r["my_cost"], "mine": bool(r["mine"]),
                    "paid_by": r["paid_by"], "future": bool(r["future"])} for r in d["recent"]],
        "notifications": _notifications(conn, uid, today, d),
        "vs_budget": _vs_budget(d["vs_budget"]),
        "charts": {          # same data as the app's Home charts (euros)
            "categories": [{"name": c["name"], "joint": c["joint"], "spent": c["spent"], "future": c["future"]}
                           for c in sorted((c for c in s["categories"] if c["spent"] > 0),
                                           key=lambda c: c["spent"], reverse=True)],
            "trend": d["charts"]["trend"],
        },
    }


# --- the widget's API ------------------------------------------------------------------

@router.get("/api/summary")
def api_summary(request: Request, conn=Depends(get_conn)):
    try:
        periods = int(request.query_params.get("periods", 6))
    except ValueError:
        periods = 6
    if periods not in TREND_PERIODS:
        periods = 6
    return JSONResponse(_summary(conn, request.state.user, config.today(), periods),
                        headers={"Cache-Control": "no-store"})


# --- tokens, from Settings ---------------------------------------------------------------

def widget_tokens(conn, uid: int) -> list:
    return conn.execute("SELECT id, name, created_at, last_used_at FROM device_tokens WHERE user_id = ? "
                        "ORDER BY created_at DESC, id DESC", (uid,)).fetchall()


@router.post("/profile/widget-tokens")
async def create_token(request: Request, conn=Depends(get_conn)):
    uid = user_id(request)
    form = await request.form()
    name = " ".join((form.get("name") or "").split())
    errors = {}
    if not name:
        errors["token_name"] = "Name the device, e.g. “Office PC”."
    elif len(name) > 60:
        errors["token_name"] = "Keep it under 60 characters."
    elif len(widget_tokens(conn, uid)) >= MAX_TOKENS:
        errors["token_name"] = f"You already have {MAX_TOKENS} widget tokens. Revoke one first."
    if errors:
        return account.render_profile(request, conn, 422, errors=errors, values={"token_name": name})
    with conn:
        token = auth.create_device_token(conn, uid, name)
        audit.log(conn, uid, "account.widget_token_created", f"Connected a KDE widget (“{name}”)")
    # shown once, on this page only (never in a URL)
    return account.render_profile(request, conn, new_token={"name": name, "token": token})


@router.post("/profile/widget-tokens/{token_id}/revoke")
def revoke_token(request: Request, token_id: int, conn=Depends(get_conn)):
    uid = user_id(request)
    with conn:
        row = conn.execute("SELECT name FROM device_tokens WHERE id = ? AND user_id = ?", (token_id, uid)).fetchone()
        if row is None:
            raise HTTPException(404, "Token not found")
        conn.execute("DELETE FROM device_tokens WHERE id = ?", (token_id,))
        audit.log(conn, uid, "account.widget_token_revoked", f"Disconnected a KDE widget (“{row['name']}”)")
    return redirect("/settings?revoked=1#widget")
