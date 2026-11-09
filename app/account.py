"""Login, registration (approved by the admin), logout and the Settings page
(profile sections plus "Request from admin")."""
from __future__ import annotations

from datetime import date
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request

from . import audit, auth, config, forms
from .money import parse_amount
from .web import available_themes, get_conn, redirect, render, user_id, valid_theme

router = APIRouter()

MAX_PENDING = 20          # stop registration spam from filling the admin's queue
MAX_DISPLAY_NAME = 60


def _safe_next(target: str | None) -> str:
    """Only allow redirects to our own pages after login."""
    if not target or not target.startswith("/") or target.startswith("//"):
        return "/"
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or target.startswith("/login"):
        return "/"
    return target


def _set_cookie(response, token: str) -> None:
    response.set_cookie(auth.USER_COOKIE, token, max_age=auth.SESSION_DAYS * 86400,
                        httponly=True, samesite="lax", path="/")


def _clean_display_name(raw: str) -> str:
    name = " ".join((raw or "").split())
    if not name:
        raise ValueError("Enter a name.")
    if len(name) > MAX_DISPLAY_NAME:
        raise ValueError(f"Keep it under {MAX_DISPLAY_NAME} characters.")
    return name


# --- login / logout -----------------------------------------------------------------

@router.get("/login")
def login_page(request: Request):
    if request.state.user:
        return redirect("/")
    notice = {"registered": "Thanks! Your account request was sent. You can log in once the admin "
                            "has approved it.",
              "out": "You're logged out."}.get(request.query_params.get("m", ""))
    return render(request, "login.html", values={}, error=None, notice=notice,
                  next=_safe_next(request.query_params.get("next")))


@router.post("/login")
async def login(request: Request, conn=Depends(get_conn)):
    form = await request.form()
    username = (form.get("username") or "").strip().lower()
    password = form.get("password") or ""
    nxt = _safe_next(form.get("next"))
    throttle = request.app.state.login_throttle
    client = request.client.host if request.client else "?"
    keys = (f"user:{username}", f"ip:{client}")

    def fail(message: str, status: int = 401):
        return render(request, "login.html", status, values={"username": username}, error=message,
                      notice=None, next=nxt)

    wait = max(throttle.locked_for(k) for k in keys)
    if wait:
        return fail(f"Too many failed attempts. Try again in {wait // 60 + 1} minute(s).", 429)

    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    ok = auth.verify_password(password, row["password_hash"] if row else auth._DUMMY_HASH)
    if not row or not ok:
        for k in keys:
            throttle.fail(k)
        with conn:
            audit.log(conn, row["id"] if row else None, "account.login_failed",
                      f"Failed login for “{username[:40]}” from {client}", actor_name=row["display_name"] if row else "Unknown")
        return fail("Wrong username or password.")
    if row["status"] == "pending":
        return fail("Your account is waiting for the admin's approval.", 403)
    if row["status"] == "disabled":
        return fail("This account has been disabled. Ask the admin.", 403)

    for k in keys:
        throttle.success(k)
    token = auth.create_session(conn, row["id"], request.headers.get("user-agent", ""))
    with conn:
        audit.log(conn, row["id"], "account.login", f"Logged in from {client}")
    response = redirect("/profile/password" if row["must_change_password"] else nxt)
    _set_cookie(response, token)
    return response


@router.post("/logout")
def logout(request: Request, conn=Depends(get_conn)):
    auth.end_session(conn, request.cookies.get(auth.USER_COOKIE))
    response = redirect("/login?m=out")
    response.delete_cookie(auth.USER_COOKIE, path="/")
    return response


# --- registration --------------------------------------------------------------------

@router.get("/register")
def register_page(request: Request):
    if request.state.user:
        return redirect("/")
    return render(request, "register.html", values={}, errors={})


@router.post("/register")
async def register(request: Request, conn=Depends(get_conn)):
    form = await request.form()
    raw = {"username": (form.get("username") or "").strip().lower(),
           "display_name": form.get("display_name") or ""}
    password, confirm = form.get("password") or "", form.get("confirm") or ""
    errors = {}
    if msg := auth.check_username(raw["username"]):
        errors["username"] = msg
    elif conn.execute("SELECT 1 FROM users WHERE username = ?", (raw["username"],)).fetchone():
        errors["username"] = "That username is taken."
    try:
        display = _clean_display_name(raw["display_name"])
    except ValueError as e:
        errors["display_name"] = str(e)
    if msg := auth.check_password_rules(password, confirm, raw["username"]):
        errors["password"] = msg
    if not errors and conn.execute("SELECT COUNT(*) FROM users WHERE status = 'pending'").fetchone()[0] >= MAX_PENDING:
        errors["form"] = "There are too many account requests waiting already. Ask the admin."
    if errors:
        return render(request, "register.html", 422, values=raw, errors=errors)
    with conn:
        cur = conn.execute("INSERT INTO users (username, display_name, password_hash, status) "
                           "VALUES (?, ?, ?, 'pending')", (raw["username"], display, auth.hash_password(password)))
        audit.log(conn, cur.lastrowid, "account.registered", f"Requested an account as “{raw['username']}”")
    return redirect("/login?m=registered")


# --- profile --------------------------------------------------------------------------

def render_profile(request: Request, conn, status_code: int = 200, errors=None, values=None,
                   reopen: str | None = None, alert: str | None = None, new_token: dict | None = None):
    from .api import widget_tokens
    uid = user_id(request)
    token = request.cookies.get(auth.USER_COOKIE)
    sessions = [dict(s) | {"current": auth.is_current(s, token)} for s in conn.execute(
        "SELECT token_hash, created_at, last_seen_at, user_agent FROM sessions "
        "WHERE user_id = ? ORDER BY last_seen_at DESC", (uid,))]
    return render(
        request, "settings.html", status_code, active="settings", subjects=SUBJECTS,
        danger_subjects=DANGER_SUBJECTS,
        delete_text=delete_request_text(request.state.user, config.today()),
        sent=request.query_params.get("sent") == "1",
        incomes=conn.execute("SELECT * FROM regular_income WHERE user_id = ? ORDER BY effective_from DESC",
                             (uid,)).fetchall(),
        themes=available_themes(), sessions=sessions,
        errors=errors or {}, values=values or {}, reopen=reopen, alert=alert,
        saved=request.query_params.get("saved") == "1",
        income_msg=INCOME_MESSAGES.get(request.query_params.get("income", "")),
        ended=request.query_params.get("ended"),
        today=config.today().isoformat(),
        widget_tokens=widget_tokens(conn, uid), new_token=new_token,
        server_url=str(request.base_url).rstrip("/"), revoked=request.query_params.get("revoked") == "1",
    )


def _saved():
    return redirect("/settings?saved=1")


INCOME_MESSAGES = {"added": "Income amount added.", "edited": "Income amount updated.",
                   "deleted": "Income amount deleted."}


def _income_done(code: str):
    return redirect(f"/settings?income={code}#income")


def _parse_income(form, errors: dict) -> tuple[dict, int | None, str | None]:
    raw = {k: (form.get(k) or "").strip() for k in ("income_amount", "income_from")}
    amount = effective = None
    try:
        amount = parse_amount(raw["income_amount"])
    except ValueError as e:
        errors["income_amount"] = str(e)
    try:
        effective = forms.parse_date(raw["income_from"]).isoformat()
    except ValueError:
        errors["income_from"] = "Enter a valid date."
    return raw, amount, effective


def _own_income(conn, uid: int, income_id: int):
    return conn.execute("SELECT * FROM regular_income WHERE id = ? AND user_id = ?",
                        (income_id, uid)).fetchone()


GONE_INCOME = "That income amount no longer exists. It may have been deleted in another tab."


@router.get("/settings")
def settings_page(request: Request, conn=Depends(get_conn)):
    return render_profile(request, conn)


@router.get("/profile")
def old_profile_page():
    return redirect("/settings")


# --- request from admin (send-only; the admin app lists the messages) -----------------

# key -> label, in the order shown in the dropdown
SUBJECTS = {
    "budgets": "Budgets",
    "categories": "Categories",
    "income": "Income",
    "account": "Account or login",
    "bug": "Something isn't working",
    "idea": "Idea or suggestion",
    "other": "Other",
    "delete_account": "Delete my account",
}
DANGER_SUBJECTS = {"delete_account"}


def delete_request_text(user, today) -> str:
    """The message pre-filled when a user picks "Delete my account"."""
    from .web import _fmt_day
    return (f"Please delete my Savings account \"{user['username']}\" ({user['display_name']}) and all "
            f"of its data: expenses, categories, budgets and income. I understand this can't be undone.\n"
            f"Requested on {_fmt_day(today.isoformat())}.")
MESSAGE_MIN = 3
MESSAGE_MAX = 1000
MESSAGES_PER_DAY = 10


@router.get("/request")
def old_request_page():
    return redirect("/settings#request")


@router.post("/request")
async def send_request(request: Request, conn=Depends(get_conn)):
    user = request.state.user
    form = await request.form()
    subject = (form.get("subject") or "").strip()
    body = (form.get("message") or "").strip().replace("\r\n", "\n")
    errors = {}
    if subject not in SUBJECTS:
        errors["subject"] = "Choose a subject."
    if len(body) < MESSAGE_MIN:
        errors["message"] = "Write a short message."
    elif len(body) > MESSAGE_MAX:
        errors["message"] = f"Keep it under {MESSAGE_MAX} characters (it's {len(body)})."
    sent_today = conn.execute(
        "SELECT COUNT(*) FROM admin_messages WHERE user_id = ? "
        "AND created_at >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-1 day')", (user["id"],)).fetchone()[0]
    if not errors and sent_today >= MESSAGES_PER_DAY:
        errors["request_form"] = (f"You've sent {MESSAGES_PER_DAY} messages in the last 24 hours. "
                                  "Please wait a bit before sending more.")
    if errors:
        return render_profile(request, conn, 422, errors=errors, values={"subject": subject, "message": body})
    with conn:
        conn.execute("INSERT INTO admin_messages (user_id, username, display_name, subject, body) "
                     "VALUES (?, ?, ?, ?, ?)", (user["id"], user["username"], user["display_name"], subject, body))
        audit.log(conn, user["id"], "account.request_sent", f"Sent a request to the admin: {SUBJECTS[subject]}")
    return redirect("/settings?sent=1#request")


@router.post("/profile/name")
async def set_name(request: Request, conn=Depends(get_conn)):
    raw = (await request.form()).get("display_name") or ""
    try:
        name = _clean_display_name(raw)
    except ValueError as e:
        return render_profile(request, conn, 422, errors={"display_name": str(e)}, values={"display_name": raw})
    with conn:
        old = request.state.user["display_name"]
        conn.execute("UPDATE users SET display_name = ? WHERE id = ?", (name, user_id(request)))
        if name != old:
            audit.log(conn, user_id(request), "account.renamed", f"Changed display name from “{old}” to “{name}”")
    return _saved()


@router.post("/profile/start-day")
async def set_start_day(request: Request, conn=Depends(get_conn)):
    raw = ((await request.form()).get("start_day") or "").strip()
    try:
        value = int(raw)
        if not 1 <= value <= 28:
            raise ValueError
    except ValueError:
        return render_profile(request, conn, 422, errors={"start_day": "Enter a day from 1 to 28."},
                              values={"start_day": raw})
    with conn:
        conn.execute("UPDATE users SET period_start_day = ? WHERE id = ?", (value, user_id(request)))
        audit.log(conn, user_id(request), "account.start_day", f"Set the budget period start day to {value}")
    return _saved()


@router.post("/profile/theme")
async def set_theme(request: Request, conn=Depends(get_conn)):
    theme = ((await request.form()).get("theme") or "").strip()
    if valid_theme(theme) != theme:
        return render_profile(request, conn, 422, errors={"theme": "Pick one of the listed themes."})
    with conn:
        conn.execute("UPDATE users SET theme = ? WHERE id = ?", (theme, user_id(request)))
    return _saved()


@router.post("/profile/regular-income")
async def add_regular_income(request: Request, conn=Depends(get_conn)):
    errors: dict = {}
    raw, amount, effective = _parse_income(await request.form(), errors)
    if errors:
        return render_profile(request, conn, 422, errors=errors, values=raw)
    # Same effective date again replaces that row's amount (fixes typos).
    with conn:
        conn.execute("INSERT INTO regular_income (user_id, amount_cents, effective_from) VALUES (?, ?, ?) "
                     "ON CONFLICT(user_id, effective_from) DO UPDATE SET amount_cents = excluded.amount_cents",
                     (user_id(request), amount, effective))
        audit.log(conn, user_id(request), "income.regular_set",
                  f"Set a regular income amount from {date.fromisoformat(effective):%d %b %Y}")
    return _income_done("added")


@router.post("/profile/regular-income/{income_id}/edit")
async def edit_regular_income(request: Request, income_id: int, conn=Depends(get_conn)):
    uid = user_id(request)
    if _own_income(conn, uid, income_id) is None:
        return render_profile(request, conn, 404, alert=GONE_INCOME)
    errors: dict = {}
    raw, amount, effective = _parse_income(await request.form(), errors)
    dialog = f"dlg-income-edit-{income_id}"
    if not errors:
        clash = conn.execute("SELECT 1 FROM regular_income WHERE user_id = ? AND effective_from = ? AND id != ?",
                             (uid, effective, income_id)).fetchone()
        if clash:
            errors["income_from"] = ("There is already an amount starting on that date. Edit or delete "
                                     "that one instead.")
    if errors:
        return render_profile(request, conn, 422, errors=errors, values=raw, reopen=dialog)
    with conn:
        conn.execute("UPDATE regular_income SET amount_cents = ?, effective_from = ? WHERE id = ? AND user_id = ?",
                     (amount, effective, income_id, uid))
        audit.log(conn, uid, "income.regular_edited",
                  f"Edited a regular income amount (now from {date.fromisoformat(effective):%d %b %Y})")
    return _income_done("edited")


@router.post("/profile/regular-income/{income_id}/delete")
def delete_regular_income(request: Request, income_id: int, conn=Depends(get_conn)):
    uid = user_id(request)
    if _own_income(conn, uid, income_id) is None:
        return render_profile(request, conn, 404, alert=GONE_INCOME)
    with conn:
        row = _own_income(conn, uid, income_id)
        conn.execute("DELETE FROM regular_income WHERE id = ? AND user_id = ?", (income_id, uid))
        audit.log(conn, uid, "income.regular_deleted",
                  f"Deleted the regular income amount from {date.fromisoformat(row['effective_from']):%d %b %Y}")
    return _income_done("deleted")


@router.post("/profile/sessions/end-others")
def end_other_sessions(request: Request, conn=Depends(get_conn)):
    n = auth.end_other_sessions(conn, user_id(request), request.cookies.get(auth.USER_COOKIE))
    with conn:
        audit.log(conn, user_id(request), "account.sessions_ended", f"Logged out {n} other device(s)")
    return redirect(f"/settings?ended={n}#sessions")


# --- password ------------------------------------------------------------------------

@router.get("/profile/password")
def password_page(request: Request):
    return render(request, "password.html", active="settings", errors={},
                  forced=bool(request.state.user["must_change_password"]))


@router.post("/profile/password")
async def change_password(request: Request, conn=Depends(get_conn)):
    user = request.state.user
    form = await request.form()
    current, new, confirm = (form.get(k) or "" for k in ("current", "password", "confirm"))
    errors = {}
    if not auth.verify_password(current, user["password_hash"]):
        errors["current"] = "That's not your current password."
    elif msg := auth.check_password_rules(new, confirm, user["username"]):
        errors["password"] = msg
    elif new == current:
        errors["password"] = "Choose a password different from the current one."
    if errors:
        return render(request, "password.html", 422, active="settings", errors=errors,
                      forced=bool(user["must_change_password"]))
    with conn:
        conn.execute("UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
                     (auth.hash_password(new), user["id"]))
        audit.log(conn, user["id"], "account.password_changed", "Changed their password")
    # A new password logs out every other device.
    auth.end_other_sessions(conn, user["id"], request.cookies.get(auth.USER_COOKIE))
    return redirect("/settings?saved=1")
