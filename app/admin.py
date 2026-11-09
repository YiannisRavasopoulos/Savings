"""Admin app: a separate web app on its own port (8091), published only on this PC's localhost.

It has its own login (the admin account is not a user), its own look, and manages accounts:
approve/reject registrations, create users, reset passwords, disable/enable, end sessions and
delete users (after an automatic safety snapshot). It also shows backups and can run one now.
"""
from __future__ import annotations

import re
import sqlite3
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from . import audit, auth, backup, config, db
from .account import SUBJECTS
from .web import BASE_DIR, get_conn, redirect, templates

PRIORITY_MAX = 5     # importance bars per message
PRIORITY_WARN = 2    # deleting a message graded above this asks for confirmation in a warning

MESSAGES = {
    "setup": "Admin account created. Welcome!",
    "approved": "“{name}” approved. They can log in now.",
    "rejected": "Request from “{name}” rejected and removed.",
    "created": "Account “{name}” created.",
    "disabled": "“{name}” disabled and logged out everywhere.",
    "enabled": "“{name}” enabled again.",
    "sessions": "“{name}” logged out of all devices.",
    "deleted": "“{name}” and all their data deleted. A safety snapshot was saved first.",
    "backup": "Backup written.",
    "log_cleared": "Activity log cleared. Everything in it was saved first as {name}.",
    "password": "Admin password changed.",
    "message_deleted": "Message deleted.",
    "priority_set": "Priority updated.",
}

LOG_CSV_COLUMNS = ("when", "who", "type", "what", "takes_effect", "kind", "actor_id", "category_id", "created_at_utc")
LOG_FILE_RE = re.compile(r"activity-log-\d{8}-\d{6}(-\d+)?\.csv")


def _log_filter(q) -> tuple[str, list, str]:
    """WHERE clause for the activity log's Type filter."""
    group = q.get("group") if q.get("group") in audit.GROUPS else ""
    return ("kind LIKE ?", [group + ".%"], group) if group else ("", [], "")


def _local(created_at: str):
    from datetime import datetime, timezone
    return datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone(config.TZ)


def _log_csv(rows) -> bytes:
    import csv, io
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(LOG_CSV_COLUMNS)
    for r in rows:
        w.writerow((_local(r["created_at"]).strftime("%Y-%m-%d %H:%M:%S"), r["actor_name"],
                    audit.GROUPS.get(r["kind"].split(".")[0], r["kind"].split(".")[0]), r["detail"],
                    r["effective_from"] or "", r["kind"], "" if r["actor_id"] is None else r["actor_id"],
                    "" if r["category_id"] is None else r["category_id"], r["created_at"]))
    return out.getvalue().encode("utf-8-sig")       # BOM, so spreadsheets read the quotes and accents right


def _log_filename(folder=None) -> str:
    """activity-log-YYYYMMDD-HHMMSS.csv (local time); -2, -3 ... if that second is already taken."""
    base = "activity-log-" + config.now().strftime("%Y%m%d-%H%M%S")
    name, n = base + ".csv", 2
    while folder is not None and (folder / name).exists():
        name, n = f"{base}-{n}.csv", n + 1
    return name


def render(request: Request, name: str, status_code: int = 200, **ctx):
    ctx.setdefault("static_v", request.app.state.static_v)
    return templates.TemplateResponse(request, f"admin/{name}", ctx, status_code=status_code)


def _admin_exists(conn) -> bool:
    return conn.execute("SELECT 1 FROM admin_account WHERE id = 1").fetchone() is not None


def _set_cookie(response, token: str) -> None:
    response.set_cookie(auth.ADMIN_COOKIE, token, max_age=auth.ADMIN_SESSION_HOURS * 3600,
                        httponly=True, samesite="strict", path="/")


def done(code: str, name: str = ""):
    return redirect("/?" + urlencode({"done": code, "name": name}))


# --- dashboard data ------------------------------------------------------------------

def _users(conn):
    return conn.execute(
        "SELECT u.*,"
        " (SELECT COUNT(*) FROM expenses e WHERE e.user_id = u.id) AS n_expenses,"
        " (SELECT COUNT(*) FROM sessions s WHERE s.user_id = u.id AND s.expires_at > strftime('%Y-%m-%dT%H:%M:%SZ','now')) AS n_sessions "
        "FROM users u ORDER BY u.status = 'pending' DESC, u.username").fetchall()


def _system(cfg, conn) -> dict:
    backups = sorted(cfg.backups_db.glob("*.sqlite"), key=lambda p: p.stat().st_mtime, reverse=True) \
        if cfg.backups_db.is_dir() else []
    return {
        "db_size": cfg.db_path.stat().st_size if cfg.db_path.exists() else 0,
        "schema": conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0],
        "version": (BASE_DIR.parent / "VERSION").read_text().strip() if (BASE_DIR.parent / "VERSION").exists() else "dev",
        "timezone": config.TZ.key,
        "backup_time": cfg.backup_time.strftime("%H:%M"),
        "retention": cfg.retention_days,
        "backups": [{"name": p.name, "size": p.stat().st_size} for p in backups[:8]],
        "n_backups": len(backups),
        "last_backup": _last_backup(conn),
    }


def _last_backup(conn) -> dict | None:
    """The latest backup entry in the activity log (written, or failed)."""
    r = conn.execute("SELECT kind, detail, actor_name, created_at FROM activity_log WHERE kind LIKE 'backup.%' "
                     "ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
    if not r:
        return None
    return {"failed": r["kind"] == "backup.failed", "detail": r["detail"], "who": r["actor_name"],
            "when": _local(r["created_at"]).strftime("%d %b %Y %H:%M")}


def render_home(request: Request, conn, status_code: int = 200, *, alert=None, errors=None,
                values=None, reopen=None, temp=None):
    message = None
    code = request.query_params.get("done")
    if code in MESSAGES and status_code == 200 and not temp:
        message = MESSAGES[code].format(name=request.query_params.get("name", ""))
    users = _users(conn)
    messages = conn.execute("SELECT * FROM admin_messages ORDER BY created_at DESC, id DESC").fetchall()
    return render(request, "home.html", status_code, users=users, messages=messages, subjects=SUBJECTS, priority_max=PRIORITY_MAX, priority_warn=PRIORITY_WARN,
                  deletable_ids={u["id"] for u in users if u["status"] != "pending"},
                  pending=[u for u in users if u["status"] == "pending"],
                  system=_system(request.app.state.cfg, conn), message=message, alert=alert,
                  errors=errors or {}, values=values or {}, reopen=reopen, temp=temp)


def _user(conn, user_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


GONE = "That account no longer exists. Someone may have changed it in the meantime."


# --- app ------------------------------------------------------------------------------

def create_admin_app(env: dict | None = None) -> FastAPI:
    cfg = config.load(env)
    db.init(cfg)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.cfg = cfg
    app.state.throttle = auth.Throttle()
    app.state.static_v = str(int(max(p.stat().st_mtime for p in (BASE_DIR / "static").rglob("*") if p.is_file())))
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS") and not auth.same_origin(request.headers):
            return Response("Request blocked: it didn't come from this site's own pages.", status_code=403)
        path = request.url.path
        if path.startswith("/static/") or path == "/favicon.ico":
            return await call_next(request)
        conn = db.connect(cfg.db_path)
        try:
            exists = _admin_exists(conn)
            logged_in = auth.admin_session_valid(conn, request.cookies.get(auth.ADMIN_COOKIE))
        finally:
            conn.close()
        if not exists:
            return await call_next(request) if path == "/setup" else redirect("/setup")
        if path == "/setup":
            return redirect("/")
        if not logged_in and path != "/login":
            return redirect("/login")
        return await call_next(request)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return FileResponse(BASE_DIR / "static" / "icons" / "admin-192.png", media_type="image/png")

    # --- first run / login -------------------------------------------------------------

    @app.get("/setup")
    def setup_page(request: Request):
        return render(request, "setup.html", errors={}, values={})

    @app.post("/setup")
    async def setup(request: Request, conn=Depends(get_conn)):
        form = await request.form()
        username = (form.get("username") or "").strip().lower()
        password, confirm = form.get("password") or "", form.get("confirm") or ""
        errors = {}
        if msg := auth.check_username(username):
            errors["username"] = msg
        if msg := auth.check_password_rules(password, confirm, username):
            errors["password"] = msg
        if errors:
            return render(request, "setup.html", 422, errors=errors, values={"username": username})
        with conn:
            conn.execute("INSERT OR IGNORE INTO admin_account (id, username, password_hash) VALUES (1, ?, ?)",
                         (username, auth.hash_password(password)))
            audit.admin(conn, "setup", f"Created the admin account “{username}”")
        response = done("setup")
        _set_cookie(response, auth.create_admin_session(conn))
        return response

    @app.get("/login")
    def login_page(request: Request):
        return render(request, "login.html", error=None, values={})

    @app.post("/login")
    async def login(request: Request, conn=Depends(get_conn)):
        form = await request.form()
        username = (form.get("username") or "").strip().lower()
        password = form.get("password") or ""
        throttle = request.app.state.throttle
        if wait := throttle.locked_for("admin"):
            return render(request, "login.html", 429, values={"username": username},
                          error=f"Too many failed attempts. Try again in {wait // 60 + 1} minute(s).")
        row = conn.execute("SELECT * FROM admin_account WHERE id = 1").fetchone()
        ok = auth.verify_password(password, row["password_hash"]) and username == row["username"]
        if not ok:
            throttle.fail("admin")
            with conn:
                audit.admin(conn, "login_failed", "Failed admin login")
            return render(request, "login.html", 401, values={"username": username},
                          error="Wrong username or password.")
        throttle.success("admin")
        with conn:
            audit.admin(conn, "login", "Admin logged in")
        response = redirect("/")
        _set_cookie(response, auth.create_admin_session(conn))
        return response

    @app.post("/logout")
    def logout(request: Request, conn=Depends(get_conn)):
        auth.end_admin_session(conn, request.cookies.get(auth.ADMIN_COOKIE))
        response = redirect("/login")
        response.delete_cookie(auth.ADMIN_COOKIE, path="/")
        return response

    # --- dashboard ------------------------------------------------------------------------

    @app.get("/")
    def home(request: Request, conn=Depends(get_conn)):
        return render_home(request, conn)

    @app.post("/users")
    async def create_user(request: Request, conn=Depends(get_conn)):
        form = await request.form()
        raw = {"username": (form.get("username") or "").strip().lower(),
               "display_name": " ".join((form.get("display_name") or "").split())}
        errors = {}
        if msg := auth.check_username(raw["username"]):
            errors["username"] = msg
        elif conn.execute("SELECT 1 FROM users WHERE username = ?", (raw["username"],)).fetchone():
            errors["username"] = "That username is taken."
        if not raw["display_name"] or len(raw["display_name"]) > 60:
            errors["display_name"] = "Enter a name (up to 60 characters)."
        if errors:
            return render_home(request, conn, 422, errors=errors, values=raw, reopen="dlg-create")
        temp = auth.temporary_password()
        with conn:
            cur = conn.execute(
                "INSERT INTO users (username, display_name, password_hash, status, must_change_password, approved_at) "
                "VALUES (?, ?, ?, 'active', 1, strftime('%Y-%m-%dT%H:%M:%SZ','now'))",
                (raw["username"], raw["display_name"], auth.hash_password(temp)))
            db.seed_user(conn, cur.lastrowid)
            audit.admin(conn, "user_created", f"Created the account “{raw['username']}”")
        return render_home(request, conn, temp={"username": raw["username"], "password": temp, "created": True})

    def _act(conn, user_id: int, allowed: tuple[str, ...], doing: str):
        """The user, if it exists and is in one of the allowed states; else an error message."""
        row = _user(conn, user_id)
        if row is None:
            return None, GONE
        if row["status"] not in allowed:
            return None, f"“{row['username']}” is {row['status']}, so it can't be {doing}."
        return row, None

    @app.post("/users/{user_id}/approve")
    def approve(request: Request, user_id: int, conn=Depends(get_conn)):
        row, err = _act(conn, user_id, ("pending",), "approved")
        if err:
            return render_home(request, conn, 409, alert=err)
        with conn:
            conn.execute("UPDATE users SET status = 'active', approved_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') "
                         "WHERE id = ?", (user_id,))
            db.seed_user(conn, user_id)
            audit.admin(conn, "approved", f"Approved the account request of “{row['username']}”")
        return done("approved", row["username"])

    @app.post("/users/{user_id}/reject")
    def reject(request: Request, user_id: int, conn=Depends(get_conn)):
        row, err = _act(conn, user_id, ("pending",), "rejected")
        if err:
            return render_home(request, conn, 409, alert=err)
        with conn:
            db.delete_user(conn, user_id)   # a pending request has no data yet
            audit.admin(conn, "rejected", f"Rejected the account request of “{row['username']}”")
        return done("rejected", row["username"])

    @app.post("/users/{user_id}/disable")
    def disable(request: Request, user_id: int, conn=Depends(get_conn)):
        row, err = _act(conn, user_id, ("active",), "disabled")
        if err:
            return render_home(request, conn, 409, alert=err)
        with conn:
            conn.execute("UPDATE users SET status = 'disabled' WHERE id = ?", (user_id,))
            audit.admin(conn, "disabled", f"Disabled “{row['username']}”")
        auth.end_all_sessions(conn, user_id)
        return done("disabled", row["username"])

    @app.post("/users/{user_id}/enable")
    def enable(request: Request, user_id: int, conn=Depends(get_conn)):
        row, err = _act(conn, user_id, ("disabled",), "enabled")
        if err:
            return render_home(request, conn, 409, alert=err)
        with conn:
            conn.execute("UPDATE users SET status = 'active' WHERE id = ?", (user_id,))
            audit.admin(conn, "enabled", f"Enabled “{row['username']}”")
        return done("enabled", row["username"])

    @app.post("/users/{user_id}/end-sessions")
    def end_sessions(request: Request, user_id: int, conn=Depends(get_conn)):
        row, err = _act(conn, user_id, ("active", "disabled"), "logged out")
        if err:
            return render_home(request, conn, 409, alert=err)
        auth.end_all_sessions(conn, user_id)
        with conn:
            audit.admin(conn, "sessions_ended", f"Logged “{row['username']}” out of all devices")
        return done("sessions", row["username"])

    @app.post("/users/{user_id}/reset-password")
    def reset_password(request: Request, user_id: int, conn=Depends(get_conn)):
        row, err = _act(conn, user_id, ("active", "disabled"), "reset")
        if err:
            return render_home(request, conn, 409, alert=err)
        temp = auth.temporary_password()
        with conn:
            conn.execute("UPDATE users SET password_hash = ?, must_change_password = 1 WHERE id = ?",
                         (auth.hash_password(temp), user_id))
            audit.admin(conn, "password_reset", f"Reset the password of “{row['username']}”")
        auth.end_all_sessions(conn, user_id)
        return render_home(request, conn, temp={"username": row["username"], "password": temp, "created": False})

    @app.post("/users/{user_id}/delete")
    async def delete(request: Request, user_id: int, conn=Depends(get_conn)):
        form = await request.form()
        row, err = _act(conn, user_id, ("active", "disabled"), "deleted")
        if err:
            return render_home(request, conn, 404 if err == GONE else 409, alert=err)
        typed = (form.get("confirm") or "").strip().lower()
        if typed != row["username"]:
            return render_home(request, conn, 422, errors={"confirm": f"Type “{row['username']}” exactly to confirm."},
                               reopen=f"dlg-delete-{user_id}")
        # Safety net first: a full snapshot that the daily retention never deletes.
        stamp = config.now().strftime("%Y%m%d-%H%M%S")
        safe_name = re.sub(r"[^a-z0-9._-]", "_", row["username"])
        try:
            backup.snapshot(cfg.db_path, cfg.backups_db / f"before-delete-{safe_name}-{stamp}.sqlite")
        except Exception as e:   # no snapshot, no delete
            return render_home(request, conn, 500, alert=f"Couldn't write the safety snapshot ({e}); nothing was deleted.")
        with conn:
            db.delete_user(conn, user_id)
            audit.admin(conn, "user_deleted", f"Deleted the account “{row['username']}” and its data "
                        f"(snapshot before-delete-{safe_name}-{stamp}.sqlite)")
        return done("deleted", row["username"])

    # --- messages from users -----------------------------------------------------------------

    GONE = "That message no longer exists. It may have been deleted already."

    @app.post("/messages/{message_id}/priority")
    async def set_priority(request: Request, message_id: int, conn=Depends(get_conn)):
        """Grade a message 1-5. Picking the level it already has clears the grade (0)."""
        form = await request.form()
        try:
            level = int(form.get("priority", ""))
        except ValueError:
            level = -1
        if not 0 <= level <= PRIORITY_MAX:
            return render_home(request, conn, 422, alert=f"Priority must be between 1 and {PRIORITY_MAX}.")
        with conn:
            row = conn.execute("SELECT priority FROM admin_messages WHERE id = ?", (message_id,)).fetchone()
            if row is None:
                return render_home(request, conn, 404, alert=GONE)
            new = 0 if level == row["priority"] else level
            conn.execute("UPDATE admin_messages SET priority = ? WHERE id = ?", (new, message_id))
            audit.admin(conn, "message_priority",
                        f"Set a message's priority to {new} of {PRIORITY_MAX}" if new else "Cleared a message's priority")
        return redirect(f"/?done=priority_set#msg-{message_id}")

    @app.post("/messages/{message_id}/delete")
    async def delete_message(request: Request, message_id: int, conn=Depends(get_conn)):
        form = await request.form()
        with conn:
            row = conn.execute("SELECT priority FROM admin_messages WHERE id = ?", (message_id,)).fetchone()
            if row is None:
                return render_home(request, conn, 404, alert=GONE)
            # Important messages (above PRIORITY_WARN) need the warning dialog's explicit confirmation.
            if row["priority"] > PRIORITY_WARN and form.get("confirm_important") != "1":
                return render_home(request, conn, 409, alert=(
                    f"This message is marked priority {row['priority']} of {PRIORITY_MAX}. "
                    "Confirm in the warning to delete it."))
            conn.execute("DELETE FROM admin_messages WHERE id = ?", (message_id,))
            audit.admin(conn, "message_deleted", "Deleted a message from a user"
                        + (f" (priority {row['priority']} of {PRIORITY_MAX})" if row["priority"] else ""))
        return redirect("/?done=message_deleted#messages")

    # --- activity log -------------------------------------------------------------------------

    def _log_dir():
        return cfg.data_dir / "backups" / "activity-log"

    @app.get("/log")
    def activity_log(request: Request, conn=Depends(get_conn)):
        q = request.query_params
        where, args, group = _log_filter(q)
        try:
            before = int(q.get("before") or 0)
        except ValueError:
            before = 0
        if before:
            where = (where + " AND " if where else "") + "id < ?"
            args = args + [before]
        sql = "SELECT * FROM activity_log" + (" WHERE " + where if where else "") + " ORDER BY id DESC LIMIT 101"
        rows = conn.execute(sql, args).fetchall()
        more = len(rows) > 100
        entries = [{**dict(r), "when": _local(r["created_at"]).strftime("%d %b %Y %H:%M"), "group": r["kind"].split(".")[0]}
                   for r in rows[:100]]
        folder = _log_dir()
        saved = sorted((p for p in folder.glob("activity-log-*.csv") if LOG_FILE_RE.fullmatch(p.name)),
                       key=lambda p: p.name, reverse=True) if folder.is_dir() else []
        cleared = q.get("done") == "log_cleared"
        name = q.get("name") or ""
        counts = {g: 0 for g in audit.GROUPS}
        for k, n in conn.execute("SELECT substr(kind, 1, instr(kind, '.') - 1), COUNT(*) FROM activity_log GROUP BY 1"):
            if k in counts:
                counts[k] = n
        return render(request, "log.html", entries=entries, groups=audit.GROUPS, group=group, counts=counts,
                      next_before=rows[99]["id"] if more else None,
                      total=conn.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0],
                      retention=audit.RETENTION_DAYS,
                      export_query=urlencode({"group": group}) if group else "",
                      saved=[{"name": p.name, "kb": max(1, round(p.stat().st_size / 1024))} for p in saved[:20]],
                      message=MESSAGES["log_cleared"].format(name=name) if cleared and LOG_FILE_RE.fullmatch(name) else None)

    @app.get("/log.csv")
    def export_log(request: Request, conn=Depends(get_conn)):
        where, args, _ = _log_filter(request.query_params)
        rows = conn.execute("SELECT * FROM activity_log" + (" WHERE " + where if where else "") + " ORDER BY id", args)
        return Response(_log_csv(rows), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{_log_filename()}"'})

    @app.post("/log/clear")
    def clear_log(request: Request, conn=Depends(get_conn)):
        import os
        folder = _log_dir()
        folder.mkdir(parents=True, exist_ok=True)
        with conn:     # one transaction: what's saved is exactly what's deleted
            last = conn.execute("SELECT COALESCE(MAX(id), 0) FROM activity_log").fetchone()[0]
            rows = conn.execute("SELECT * FROM activity_log WHERE id <= ? ORDER BY id", (last,)).fetchall()
            name = _log_filename(folder)
            tmp = folder / (name + ".part")
            with open(tmp, "wb") as f:
                f.write(_log_csv(rows))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, folder / name)
            conn.execute("DELETE FROM activity_log WHERE id <= ?", (last,))
            audit.admin(conn, "log_cleared", f"Cleared the activity log ({len(rows)} entries, saved as {name})")
        return redirect("/log?" + urlencode({"done": "log_cleared", "name": name}))

    @app.get("/log/saved/{name}")
    def saved_log(name: str):
        path = _log_dir() / name
        if not LOG_FILE_RE.fullmatch(name) or not path.is_file():
            return Response("Not found", status_code=404)
        return FileResponse(path, media_type="text/csv", filename=name)

    # --- system ---------------------------------------------------------------------------

    @app.post("/backup-now")
    def backup_now(request: Request, conn=Depends(get_conn)):
        try:
            backup.run_once(cfg, config.today(), reason="manual", actor="Admin")   # logs itself
        except Exception as e:
            backup.record_failure(cfg, "manual", e, actor="Admin")
            return render_home(request, conn, 500, alert=f"Backup failed: {e}")
        return done("backup")

    @app.post("/password")
    async def admin_password(request: Request, conn=Depends(get_conn)):
        form = await request.form()
        row = conn.execute("SELECT * FROM admin_account WHERE id = 1").fetchone()
        current, new, confirm = (form.get(k) or "" for k in ("current", "password", "confirm"))
        errors = {}
        if not auth.verify_password(current, row["password_hash"]):
            errors["current"] = "That's not the current admin password."
        elif msg := auth.check_password_rules(new, confirm, row["username"]):
            errors["password"] = msg
        if errors:
            return render_home(request, conn, 422, errors=errors, reopen="dlg-password")
        with conn:
            conn.execute("UPDATE admin_account SET password_hash = ? WHERE id = 1", (auth.hash_password(new),))
            conn.execute("DELETE FROM admin_sessions")   # every admin browser must log in again...
            audit.admin(conn, "password_changed", "Changed the admin password")
        response = done("password")
        _set_cookie(response, auth.create_admin_session(conn))   # ...except this one
        return response

    return app
