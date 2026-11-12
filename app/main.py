"""User app: Home · Add · Log · Month · Year · Income · Categories · Profile.

Every page except login/register needs a logged-in, approved user, and every query is limited
to that user's own data: expenses are reached through categories.user_id, income through
user_id. Looking up someone else's id answers 404, exactly like an id that doesn't exist.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import asynccontextmanager
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import account, audit, auth, backup, config, db, export, forms, joint, period, recurring, summary
from . import categories as category_routes
from . import plans as plan_routes
from . import import_routes, recurring_routes
from . import api as api_routes
from . import quick as quick_routes
from . import shared as shared_routes
from .web import BASE_DIR, NOW_SQL, current_period, get_conn, redirect, render, templates, user_id

router = APIRouter()

# Pages reachable without logging in.
PUBLIC_PATHS = ("/login", "/register", "/static/", "/favicon.ico", "/sw.js", "/offline")
# Pages a user who must change their password may still use.
PASSWORD_CHANGE_PATHS = ("/profile/password", "/logout")


def period_of(conn, uid: int, iso_date: str) -> str:
    y, m = summary.get_period_rule(conn, uid).for_date(date.fromisoformat(iso_date))
    return period.period_key(y, m)


def resolve_period(conn, uid: int, params) -> tuple[int, int]:
    """From ?period=YYYY-MM or ?year=&month=, falling back to the current period."""
    try:
        if params.get("period"):
            y, m = (int(x) for x in params["period"].split("-"))
        elif params.get("year") and params.get("month"):
            y, m = int(params["year"]), int(params["month"])
        else:
            return current_period(conn, uid)
        if 1 <= m <= 12 and 2000 <= y <= 2100:
            return y, m
    except ValueError:
        pass
    return current_period(conn, uid)


def period_ctx(conn, uid: int, y: int, m: int) -> dict:
    start, end = summary.get_period_rule(conn, uid).bounds(y, m)
    return {
        "year": y,
        "month": m,
        "key": period.period_key(y, m),
        "label": period.period_label(y, m),
        "range": period.range_label(start, end),
        "start": start,
        "end": end,
        "prev": period.period_key(*period.shift_period(y, m, -1)),
        "next": period.period_key(*period.shift_period(y, m, 1)),
        "current": period.period_key(*current_period(conn, uid)),
        "years": list(range(min(y, config.today().year) - 5, max(y, config.today().year) + 2)),
    }


def _valid_iso(text: str | None) -> str | None:
    try:
        return forms.parse_date(text).isoformat() if text else None
    except ValueError:
        return None


@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(BASE_DIR / "static" / "icons" / "favicon.ico", media_type="image/x-icon")


# Offline support for the home-screen app (service worker + a page with no personal data).
@router.get("/sw.js", include_in_schema=False)
def service_worker(request: Request):
    body = templates.env.get_template("pwa/sw.js").render(v=request.app.state.static_v)
    return Response(body, media_type="text/javascript",
                    headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


@router.get("/offline", include_in_schema=False)
def offline_page(request: Request):
    body = templates.env.get_template("pwa/offline.html").render(v=request.app.state.static_v)
    return HTMLResponse(body, headers={"Cache-Control": "no-cache"})


# --- Home: dashboard ---------------------------------------------------------------

@router.get("/")
def home(request: Request, conn=Depends(get_conn)):
    uid = user_id(request)
    d = summary.dashboard(conn, uid, config.today())
    from .categories import INVITE_MESSAGES
    return render(request, "home.html", active="home", d=d, invites=joint.pending_invites(conn, uid, config.today()),
                  reset=summary.reset_notice(conn, uid, config.today()),
                  invite_msg=INVITE_MESSAGES.get(request.query_params.get("invite", "")), back="/")


def _joint_rules(conn, uid: int, cats, clean: dict, errors: dict) -> None:
    """Extra check when the chosen category is shared: you must be a member on the expense's date."""
    if errors or "category_id" not in clean:
        return
    cat = next((c for c in cats if c["id"] == clean["category_id"]), None)
    if cat is not None and cat["is_joint"]:
        reason = joint.can_log_on(conn, cat["id"], uid, date.fromisoformat(clean["date"]))
        if reason:
            errors["date"] = reason


def _log_expense_edit(conn, uid: int, old, new: dict) -> None:
    """Admin log entry for an edit: which fields changed, never amounts or descriptions."""
    if old["category_id"] != new["category_id"]:
        audit.log(conn, uid, "expense.moved",
                  f"Moved an expense (dated {date.fromisoformat(old['date']):%d %b %Y}) from "
                  f"{audit.category_name(conn, old['category_id'])} to {audit.category_name(conn, new['category_id'])}",
                  category_id=new["category_id"])
        return
    changes = []
    if old["amount_cents"] != new["amount_cents"]:
        changes.append("amount")
    if old["description"] != new["description"]:
        changes.append("description")
    if old["notes"] != new["notes"]:
        changes.append("notes")
    if old["one_off"] != new["one_off"]:
        changes.append("one-off mark")
    if old["date"] != new["date"]:
        changes.append(f"date {date.fromisoformat(old['date']):%d %b %Y} → {date.fromisoformat(new['date']):%d %b %Y}")
    if changes:
        audit.log(conn, uid, "expense.edited",
                  f"Edited {joint.describe_expense(conn, old)}: changed " + ", ".join(changes),
                  category_id=new["category_id"])


# --- Add expense ------------------------------------------------------------------

@router.get("/add")
def add_page(request: Request, conn=Depends(get_conn)):
    q = request.query_params
    day = _valid_iso(q.get("date")) or config.today().isoformat()
    cats = db.active_categories(conn, user_id(request))
    values = forms.empty_expense(day)
    # pre-fill from a planned purchase ("Bought it" on the Plans page)
    values["description"] = (q.get("description") or "")[:forms.MAX_TEXT]
    values["amount"] = (q.get("amount") or "")[:20]
    values["one_off"] = "1" if q.get("one_off") == "1" else ""
    if q.get("category_id") in {str(c["id"]) for c in cats}:
        values["category_id"] = q.get("category_id")
    return render(request, "add.html", active="add", values=values, errors={}, categories=cats,
                  saved=q.get("saved") == "1", from_plan=q.get("from_plan") == "1")


@router.post("/add")
async def add_expense(request: Request, conn=Depends(get_conn)):
    form = await request.form()
    uid = user_id(request)
    cats = db.active_categories(conn, uid)
    clean, errors, raw = forms.validate_expense(form, {c["id"] for c in cats})
    _joint_rules(conn, uid, cats, clean, errors)
    if errors:
        return render(request, "add.html", 422, active="add", values=raw, errors=errors,
                      categories=cats, saved=False)
    with conn:
        cur = conn.execute(
            "INSERT INTO expenses (user_id, date, description, category_id, amount_cents, notes, one_off) "
            "VALUES (:uid, :date, :description, :category_id, :amount_cents, :notes, :one_off)",
            {**clean, "uid": uid},
        )
        joint.reallocate_expense(conn, cur.lastrowid)
        audit.log(conn, uid, "expense.added", "Added " + joint.describe_expense(conn, clean),
                  category_id=clean["category_id"])
    return redirect(f"/add?saved=1&date={clean['date']}&amt={clean['amount_cents']}")


# --- Log ------------------------------------------------------------------------

def _split_notes(conn, uid: int, cat_id: int, rows) -> dict:
    """For a shared category's Log view: each split expense's parts, {expense id: [part, ...]}.
    Expenses with a single part (logged before anyone else joined) get no note."""
    cat = conn.execute("SELECT is_joint FROM categories WHERE id = ?", (cat_id,)).fetchone()
    if not cat or not cat["is_joint"] or not rows:
        return {}
    ids = [r["id"] for r in rows]
    parts: dict[int, list] = {}
    for s in conn.execute(
            f"SELECT s.expense_id, s.user_id, s.cents, u.display_name FROM expense_shares s JOIN users u ON u.id = s.user_id "
            f"WHERE s.expense_id IN ({','.join('?' * len(ids))}) ORDER BY s.cents DESC, u.display_name", ids):
        parts.setdefault(s["expense_id"], []).append(s)
    notes = {}
    for r in rows:
        ps = parts.get(r["id"], [])
        if len(ps) < 2:
            continue
        split = joint.split_at(conn, cat_id, date.fromisoformat(r["date"]))
        notes[r["id"]] = [{"name": "You" if p["user_id"] == uid else p["display_name"], "me": p["user_id"] == uid,
                           "pct": split.get(p["user_id"], 0) / 100, "cents": p["cents"]}
                          for p in sorted(ps, key=lambda p: (p["user_id"] != uid, -p["cents"], p["display_name"]))]
    return notes


@router.get("/log")
def log_page(request: Request, conn=Depends(get_conn)):
    uid = user_id(request)
    y, m = resolve_period(conn, uid, request.query_params)
    p = period_ctx(conn, uid, y, m)
    try:
        cat_id = int(request.query_params.get("category") or 0) or None
    except ValueError:
        cat_id = None
    # Every expense that costs this user something: their own, and others' in shared categories.
    sql = (
        "SELECT e.*, CASE WHEN c.is_joint = 1 AND jm.leaves_after IS NOT NULL AND jm.leaves_after < ? "
        "THEN c.name || ' (left)' ELSE c.name END AS category, c.is_joint, s.cents AS my_cost, e.user_id = ? AS mine, "
        "u.display_name AS paid_by, e.date > ? AS future "
        "FROM expenses e JOIN expense_shares s ON s.expense_id = e.id AND s.user_id = ? "
        "JOIN categories c ON c.id = e.category_id JOIN users u ON u.id = e.user_id "
        "LEFT JOIN joint_members jm ON jm.category_id = c.id AND jm.user_id = s.user_id "
        "WHERE e.date BETWEEN ? AND ?"
    )
    args = [config.today().isoformat(), uid, config.today().isoformat(), uid, p["start"].isoformat(), p["end"].isoformat()]
    if cat_id:
        sql += " AND e.category_id = ?"
        args.append(cat_id)
    rows = conn.execute(sql + " ORDER BY e.date DESC, e.id DESC", args).fetchall()
    totals = {
        "amount": sum(r["amount_cents"] for r in rows),
        "mine": sum(r["my_cost"] for r in rows),
    }
    splits = _split_notes(conn, uid, cat_id, rows) if cat_id else {}
    return render(request, "log.html", active="log", p=p, rows=rows, totals=totals, splits=splits,
                  categories=db.all_categories(conn, uid, p["end"]), cat_id=cat_id,
                  extra=f"&category={cat_id}" if cat_id else "")


def _get_expense(conn, uid: int, expense_id: int) -> sqlite3.Row:
    # Only the person who paid (logged) an expense can open, change or delete it.
    row = conn.execute("SELECT e.* FROM expenses e WHERE e.id = ? AND e.user_id = ?", (expense_id, uid)).fetchone()
    if row is None:
        raise HTTPException(404, "Expense not found")
    return row


@router.get("/expenses/{expense_id}/edit")
def edit_expense_page(request: Request, expense_id: int, conn=Depends(get_conn)):
    uid = user_id(request)
    row = _get_expense(conn, uid, expense_id)
    return render(request, "expense_edit.html", active="log", expense_id=expense_id,
                  values=forms.expense_values(row), errors={},
                  categories=db.categories_for_select(conn, uid, row["category_id"]),
                  back=period_of(conn, uid, row["date"]))


@router.post("/expenses/{expense_id}/edit")
async def edit_expense(request: Request, expense_id: int, conn=Depends(get_conn)):
    uid = user_id(request)
    row = _get_expense(conn, uid, expense_id)
    form = await request.form()
    cats = db.categories_for_select(conn, uid, row["category_id"])
    clean, errors, raw = forms.validate_expense(form, {c["id"] for c in cats})
    _joint_rules(conn, uid, cats, clean, errors)
    if errors:
        return render(request, "expense_edit.html", 422, active="log", expense_id=expense_id,
                      values=raw, errors=errors, categories=cats,
                      back=period_of(conn, uid, row["date"]))
    with conn:
        conn.execute(
            "UPDATE expenses SET date = :date, description = :description, category_id = :category_id, "
            "amount_cents = :amount_cents, notes = :notes, "
            f"one_off = :one_off, updated_at = {NOW_SQL} WHERE id = :id",
            {**clean, "id": expense_id},
        )
        joint.reallocate_expense(conn, expense_id)
        _log_expense_edit(conn, uid, row, clean)
    return redirect(f"/log?period={period_of(conn, uid, clean['date'])}")


@router.post("/expenses/{expense_id}/delete")
def delete_expense(request: Request, expense_id: int, conn=Depends(get_conn)):
    uid = user_id(request)
    row = _get_expense(conn, uid, expense_id)
    with conn:
        conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        audit.log(conn, uid, "expense.deleted", "Deleted " + joint.describe_expense(conn, row),
                  category_id=row["category_id"])
    return redirect(f"/log?period={period_of(conn, uid, row['date'])}")


# --- Extra income ---------------------------------------------------------------

def _income_list(conn, uid: int, p) -> tuple[list, int]:
    rows = conn.execute(
        "SELECT * FROM extra_income WHERE user_id = ? AND date BETWEEN ? AND ? ORDER BY date DESC, id DESC",
        (uid, p["start"].isoformat(), p["end"].isoformat()),
    ).fetchall()
    return rows, sum(r["amount_cents"] for r in rows)


@router.get("/income")
def income_page(request: Request, conn=Depends(get_conn)):
    uid = user_id(request)
    y, m = resolve_period(conn, uid, request.query_params)
    p = period_ctx(conn, uid, y, m)
    rows, total = _income_list(conn, uid, p)
    day = _valid_iso(request.query_params.get("date")) or config.today().isoformat()
    return render(request, "income.html", active="income", p=p, rows=rows, total=total,
                  values=forms.empty_income(day), errors={},
                  saved=request.query_params.get("saved") == "1")


@router.post("/income")
async def add_income(request: Request, conn=Depends(get_conn)):
    uid = user_id(request)
    form = await request.form()
    clean, errors, raw = forms.validate_income(form)
    if errors:
        p = period_ctx(conn, uid, *current_period(conn, uid))
        rows, total = _income_list(conn, uid, p)
        return render(request, "income.html", 422, active="income", p=p, rows=rows, total=total,
                      values=raw, errors=errors, saved=False)
    with conn:
        conn.execute(
            "INSERT INTO extra_income (user_id, date, description, amount_cents, notes) "
            "VALUES (:user_id, :date, :description, :amount_cents, :notes)",
            {**clean, "user_id": uid},
        )
        audit.log(conn, uid, "income.extra_added",
                  f"Added extra income (dated {date.fromisoformat(clean['date']):%d %b %Y})")
    return redirect(f"/income?period={period_of(conn, uid, clean['date'])}&saved=1&date={clean['date']}"
                    f"&amt={clean['amount_cents']}")


def _get_income(conn, uid: int, income_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM extra_income WHERE id = ? AND user_id = ?",
                       (income_id, uid)).fetchone()
    if row is None:
        raise HTTPException(404, "Income entry not found")
    return row


@router.get("/income/{income_id}/edit")
def edit_income_page(request: Request, income_id: int, conn=Depends(get_conn)):
    uid = user_id(request)
    row = _get_income(conn, uid, income_id)
    return render(request, "income_edit.html", active="income", income_id=income_id,
                  values=forms.income_values(row), errors={}, back=period_of(conn, uid, row["date"]))


@router.post("/income/{income_id}/edit")
async def edit_income(request: Request, income_id: int, conn=Depends(get_conn)):
    uid = user_id(request)
    row = _get_income(conn, uid, income_id)
    form = await request.form()
    clean, errors, raw = forms.validate_income(form)
    if errors:
        return render(request, "income_edit.html", 422, active="income", income_id=income_id,
                      values=raw, errors=errors, back=period_of(conn, uid, row["date"]))
    with conn:
        conn.execute(
            "UPDATE extra_income SET date = :date, description = :description, "
            f"amount_cents = :amount_cents, notes = :notes, updated_at = {NOW_SQL} "
            "WHERE id = :id AND user_id = :user_id",
            {**clean, "id": income_id, "user_id": uid},
        )
        audit.log(conn, uid, "income.extra_edited",
                  f"Edited extra income (dated {date.fromisoformat(row['date']):%d %b %Y})")
    return redirect(f"/income?period={period_of(conn, uid, clean['date'])}")


@router.post("/income/{income_id}/delete")
def delete_income(request: Request, income_id: int, conn=Depends(get_conn)):
    uid = user_id(request)
    row = _get_income(conn, uid, income_id)
    with conn:
        conn.execute("DELETE FROM extra_income WHERE id = ? AND user_id = ?", (income_id, uid))
        audit.log(conn, uid, "income.extra_deleted",
                  f"Deleted extra income (dated {date.fromisoformat(row['date']):%d %b %Y})")
    return redirect(f"/income?period={period_of(conn, uid, row['date'])}")


# --- Month and Year views ----------------------------------------------------------

@router.get("/month")
def month_page(request: Request, conn=Depends(get_conn)):
    uid = user_id(request)
    y, m = resolve_period(conn, uid, request.query_params)
    return render(request, "month.html", active="month", p=period_ctx(conn, uid, y, m),
                  s=summary.month_summary(conn, uid, y, m))


@router.get("/budget")
def budget_page(request: Request, conn=Depends(get_conn)):
    """You against your plan: savings vs budget for any period, its pace, and the track record."""
    uid = user_id(request)
    y, m = resolve_period(conn, uid, request.query_params)
    ms = summary.month_summary(conn, uid, y, m)
    today = config.today()
    return render(request, "budget.html", active="budget", p=period_ctx(conn, uid, y, m),
                  vb=summary.budget_balance(conn, uid, ms, today), r=summary.budget_record(conn, uid, today))


@router.get("/year")
def year_page(request: Request, conn=Depends(get_conn)):
    uid = user_id(request)
    try:
        year = int(request.query_params.get("year") or 0)
    except ValueError:
        year = 0
    if not 2000 <= year <= 2100:
        year = current_period(conn, uid)[0]
    return render(request, "year.html", active="year", this_year=current_period(conn, uid)[0],
                  y=summary.year_summary(conn, uid, year, config.today()))


@router.get("/trends")
def trends_page(request: Request, conn=Depends(get_conn)):
    try:
        n = int(request.query_params.get("n") or 12)
    except ValueError:
        n = 12
    if n not in summary.TREND_RANGES:
        n = 12
    return render(request, "trends.html", active="trends",
                  t=summary.trends(conn, user_id(request), config.today(), n))


# --- Export (own data) -------------------------------------------------------------

@router.get("/export.zip")
def export_zip(request: Request, conn=Depends(get_conn)):
    data = export.build_zip(conn, user_id(request))
    name = export.zip_name(config.today())
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


# --- app factory ------------------------------------------------------------------

def create_app(env: dict | None = None, run_backups: bool = True) -> FastAPI:
    cfg = config.load(env)
    db.init(cfg)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # The daily backup runs in a background thread for as long as the server runs.
        stop = threading.Event()
        thread = None
        if run_backups:
            thread = threading.Thread(target=backup.scheduler, args=(cfg, stop),
                                      name="backup-scheduler", daemon=True)
            thread.start()
        app.state.backup_thread = thread
        try:
            yield
        finally:
            stop.set()
            if thread:
                thread.join(timeout=10)

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.cfg = cfg
    app.state.login_throttle = auth.Throttle()
    # Appended to CSS/JS URLs so browsers fetch fresh files after an update.
    app.state.static_v = str(int(max(p.stat().st_mtime for p in (BASE_DIR / "static").rglob("*") if p.is_file())))
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
    app.include_router(account.router)
    app.include_router(router)
    app.include_router(category_routes.router)
    app.include_router(plan_routes.router)
    app.include_router(recurring_routes.router)
    app.include_router(import_routes.router)
    app.include_router(quick_routes.router)
    app.include_router(api_routes.router)
    app.include_router(shared_routes.router)

    @app.middleware("http")
    async def require_login(request: Request, call_next):
        # 0. The KDE widget's API: a device token only (cookies are ignored, so no cross-site risk).
        if request.url.path.startswith("/api/"):
            conn = db.connect(cfg.db_path)
            try:
                u = auth.device_token_user(conn, request.headers.get("authorization"))
                if u is not None and request.method == "GET":
                    recurring.catch_up(conn, u["id"], config.today())
            finally:
                conn.close()
            if u is None:
                return JSONResponse({"error": "Not connected: create a widget token in Settings → KDE widget."},
                                    status_code=401)
            if u["must_change_password"]:
                return JSONResponse({"error": "Change your password in the app first."}, status_code=403)
            request.state.user = u
            return await call_next(request)
        # 1. Forms must be submitted from our own pages (blocks cross-site form posts).
        if request.method not in ("GET", "HEAD", "OPTIONS") and not auth.same_origin(request.headers):
            return Response("Request blocked: it didn't come from this site's own pages.", status_code=403)
        # 2. Who is this?
        path = request.url.path
        conn = db.connect(cfg.db_path)
        try:
            request.state.user = auth.session_user(conn, request.cookies.get(auth.USER_COOKIE))
            # Recurring expenses: create any payments that have come due (cheap when there are none).
            u = request.state.user
            if (u is not None and request.method == "GET" and not u["must_change_password"]
                    and not path.startswith(("/static/", "/favicon.ico", "/sw.js"))):
                recurring.catch_up(conn, u["id"], config.today())
        finally:
            conn.close()
        user = request.state.user
        if user is None and not path.startswith(PUBLIC_PATHS):
            target = path + (f"?{request.url.query}" if request.url.query else "")
            return redirect("/login" + ("" if target == "/" else f"?next={quote(target, safe='')}"))
        # 3. After an admin password reset, nothing else until the password is changed.
        if user is not None and user["must_change_password"] and not path.startswith(
                PASSWORD_CHANGE_PATHS + ("/static/", "/favicon.ico", "/sw.js", "/offline")):
            return redirect("/profile/password")
        return await call_next(request)

    return app
