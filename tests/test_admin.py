"""Admin app: first-run setup, login, approving/rejecting requests, managing users."""
import re

import pytest
from fastapi.testclient import TestClient

from app import auth, db
from app.admin import create_admin_app

from .conftest import PASSWORD, browser, login, make_user

ADMIN_PW = "admin password 1"


@pytest.fixture
def admin_app(app, data_dir):
    return create_admin_app(env={"APP_DATA_DIR": str(data_dir)})


def _admin(admin_app) -> TestClient:
    return TestClient(admin_app, headers={"Origin": "http://testserver"})


@pytest.fixture
def adm(admin_app):
    c = _admin(admin_app)
    r = c.post("/setup", data={"username": "boss", "password": ADMIN_PW, "confirm": ADMIN_PW}, follow_redirects=False)
    assert r.status_code == 303
    return c


def _post(c, url, **data):
    return c.post(url, data=data, follow_redirects=False)


def _temp_password(page):
    return re.search(r'class="adm-secret"><code>([^<]+)</code>', page).group(1)


def _alert(page):
    m = re.search(r'id="dlg-alert".*?<p>(.*?)</p>', page, re.S)
    return m.group(1) if m else None


# --- setup / login ------------------------------------------------------------------

def test_first_visit_goes_to_setup_and_setup_only_once(admin_app):
    c = _admin(admin_app)
    assert c.get("/", follow_redirects=False).headers["location"] == "/setup"
    r = c.post("/setup", data={"username": "boss", "password": "short", "confirm": "short"})
    assert r.status_code == 422 and "at least 10" in r.text
    _post(c, "/setup", username="boss", password=ADMIN_PW, confirm=ADMIN_PW)
    assert c.get("/").status_code == 200
    # once an admin exists, setup can't be used to take over
    other = _admin(admin_app)
    assert other.get("/setup", follow_redirects=False).headers["location"] == "/"
    _post(other, "/setup", username="evil", password="evil password", confirm="evil password")
    assert other.get("/", follow_redirects=False).headers["location"] == "/login"


def test_admin_login_logout(adm, admin_app):
    c = _admin(admin_app)
    assert c.get("/", follow_redirects=False).headers["location"] == "/login"
    assert c.post("/login", data={"username": "boss", "password": "wrong password"}).status_code == 401
    r = _post(c, "/login", username="boss", password=ADMIN_PW)
    assert r.status_code == 303 and "SameSite=strict" in r.headers["set-cookie"]
    assert c.get("/").status_code == 200
    _post(c, "/logout")
    assert c.get("/", follow_redirects=False).headers["location"] == "/login"


def test_admin_login_throttled(adm, admin_app):
    c = _admin(admin_app)
    for _ in range(5):
        c.post("/login", data={"username": "boss", "password": "nope nope nope"})
    assert c.post("/login", data={"username": "boss", "password": ADMIN_PW}).status_code == 429


def test_user_login_does_not_open_admin_and_vice_versa(adm, admin_app, client, app):
    assert _admin(admin_app).get("/", follow_redirects=False).status_code == 303   # user cookie isn't enough
    assert browser(app).post("/login", data={"username": "boss", "password": ADMIN_PW}).status_code == 401


def test_admin_blocks_cross_site_posts(adm, conn):
    make_user(conn, "victim")
    r = adm.post("/users/1/disable", headers={"Origin": "http://evil.example"})
    assert r.status_code == 403


def test_admin_port_is_published_only_on_localhost():
    compose = open("docker-compose.yml").read()
    assert '"127.0.0.1:${ADMIN_PORT:-8091}:8091"' in compose


def test_app_port_is_ipv4_only_by_default():
    """Not published on IPv6: many homes give every device a public IPv6 address."""
    compose = open("docker-compose.yml").read()
    assert '"${BIND_ADDRESS:-0.0.0.0}:${PORT:-8090}:8080"' in compose
    assert '"${PORT:-8090}:8080"' not in compose                 # the old, every-address form
    assert "\nBIND_ADDRESS=0.0.0.0\n" in open(".env.example").read()


# --- registration approval ----------------------------------------------------------------

def test_register_then_approve_then_login(adm, app, conn):
    user_app = browser(app)
    _post(user_app, "/register", username="carol", display_name="Carol", password="carol's password",
          confirm="carol's password")
    page = adm.get("/").text
    assert "Account requests" in page and "carol" in page and 'class="adm-badge">1<' in page
    cid = conn.execute("SELECT id FROM users WHERE username = 'carol'").fetchone()[0]
    r = _post(adm, f"/users/{cid}/approve")
    assert "done=approved" in r.headers["location"]
    row = conn.execute("SELECT status, approved_at FROM users WHERE id = ?", (cid,)).fetchone()
    assert row["status"] == "active" and row["approved_at"]
    assert conn.execute("SELECT COUNT(*) FROM categories WHERE user_id = ?", (cid,)).fetchone()[0] == len(db.DEFAULT_CATEGORIES)
    login(browser(app), "carol", "carol's password")
    r = adm.post(f"/users/{cid}/approve")   # twice
    assert r.status_code == 409 and "is active" in _alert(r.text)


def test_reject_removes_request(adm, conn):
    uid = make_user(conn, "spammer", status="pending", seed=False)
    assert "done=rejected" in _post(adm, f"/users/{uid}/reject").headers["location"]
    assert conn.execute("SELECT COUNT(*) FROM users WHERE id = ?", (uid,)).fetchone()[0] == 0


# --- managing users -----------------------------------------------------------------------

def test_create_user_with_temporary_password(adm, app, conn):
    r = adm.post("/users", data={"username": "erin", "display_name": "Erin"})
    temp = _temp_password(r.text)
    assert "shown only once" in r.text
    c = browser(app)
    r = _post(c, "/login", username="erin", password=temp)
    assert r.headers["location"] == "/profile/password"
    _post(c, "/profile/password", current=temp, password="erin's own pw!", confirm="erin's own pw!")
    assert c.get("/", follow_redirects=False).status_code == 200
    r = adm.post("/users", data={"username": "erin", "display_name": "Again"})
    assert r.status_code == 422 and "taken" in r.text and 'data-reopen="dlg-create"' in r.text


def test_reset_password_logs_user_out_and_forces_change(adm, app, client, conn, uid):
    r = adm.post(f"/users/{uid}/reset-password")
    temp = _temp_password(r.text)
    assert client.get("/", follow_redirects=False).status_code == 303         # logged out
    assert browser(app).post("/login", data={"username": "alice", "password": PASSWORD}).status_code == 401
    c = browser(app)
    assert _post(c, "/login", username="alice", password=temp).headers["location"] == "/profile/password"


def test_disable_and_enable(adm, client, conn, uid):
    assert "done=disabled" in _post(adm, f"/users/{uid}/disable").headers["location"]
    assert client.get("/", follow_redirects=False).status_code == 303
    assert conn.execute("SELECT COUNT(*) FROM sessions WHERE user_id = ?", (uid,)).fetchone()[0] == 0
    assert "done=enabled" in _post(adm, f"/users/{uid}/enable").headers["location"]
    assert conn.execute("SELECT status FROM users WHERE id = ?", (uid,)).fetchone()[0] == "active"


def test_end_sessions(adm, client, uid):
    assert "done=sessions" in _post(adm, f"/users/{uid}/end-sessions").headers["location"]
    assert client.get("/", follow_redirects=False).status_code == 303


def test_delete_user_needs_typed_name_and_snapshots_first(adm, app, conn, uid):
    cid = conn.execute("SELECT id FROM categories WHERE user_id = ? LIMIT 1", (uid,)).fetchone()[0]
    conn.execute("INSERT INTO expenses (date, category_id, amount_cents) VALUES ('2026-11-01', ?, 100)", (cid,))
    conn.commit()
    r = adm.post(f"/users/{uid}/delete", data={"confirm": "alic"})
    assert r.status_code == 422 and "exactly to confirm" in r.text
    assert conn.execute("SELECT COUNT(*) FROM users WHERE id = ?", (uid,)).fetchone()[0] == 1

    r = _post(adm, f"/users/{uid}/delete", confirm="ALICE")
    assert "done=deleted" in r.headers["location"]
    assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 0
    snaps = list(app.state.cfg.backups_db.glob("before-delete-alice-*.sqlite"))
    assert len(snaps) == 1
    import sqlite3
    assert sqlite3.connect(snaps[0]).execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 1


def test_actions_on_missing_user_show_error_popup(adm):
    for action in ("approve", "reject", "disable", "enable", "end-sessions", "reset-password"):
        r = adm.post(f"/users/9999/{action}")
        assert r.status_code == 409 and "no longer exists" in _alert(r.text)
    r = adm.post("/users/9999/delete", data={"confirm": "x"})
    assert r.status_code == 404


def test_backup_now_and_system_info(adm, app):
    assert "done=backup" in _post(adm, "/backup-now").headers["location"]
    page = adm.get("/").text
    assert "schema v18" in page and "spending-" in page


def test_change_admin_password(adm, admin_app):
    other = _admin(admin_app)
    _post(other, "/login", username="boss", password=ADMIN_PW)
    r = adm.post("/password", data={"current": "wrong", "password": "new admin pw!", "confirm": "new admin pw!"})
    assert r.status_code == 422 and 'data-reopen="dlg-password"' in r.text
    assert "done=password" in _post(adm, "/password", current=ADMIN_PW, password="new admin pw!",
                                    confirm="new admin pw!").headers["location"]
    assert adm.get("/", follow_redirects=False).status_code == 200           # this browser stays in
    assert other.get("/", follow_redirects=False).status_code == 303         # others are logged out


def test_reset_admin_cli(adm, admin_app, monkeypatch, data_dir):
    from app import reset_admin
    monkeypatch.setenv("APP_DATA_DIR", str(data_dir))
    assert reset_admin.main() == 0
    assert _admin(admin_app).get("/", follow_redirects=False).headers["location"] == "/setup"


def test_log_export_and_clear(adm, admin_app, app, conn, data_dir, client, monkeypatch):
    import csv, io, re
    from datetime import datetime
    from app import config
    client.post("/categories", data={"name": "Pets", "budget": "", "budget_from": ""})
    r = adm.get("/log.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert re.search(r'filename="activity-log-\d{8}-\d{6}\.csv"', r.headers["content-disposition"])
    rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows[0].keys() >= {"when", "who", "type", "what", "takes_effect"}
    assert any(x["what"] == "Added the category “Pets”" for x in rows)
    only_admin = list(csv.DictReader(io.StringIO(adm.get("/log.csv?group=admin").content.decode("utf-8-sig"))))
    assert only_admin and all(x["type"] == "Admin actions" for x in only_admin)
    page = adm.get("/log").text
    assert 'href="/log.csv"' in page and 'data-open="dlg-clear-log"' in page

    before = conn.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0]
    monkeypatch.setattr(config, "now", lambda: datetime(2026, 11, 5, 9, 30, 15, tzinfo=config.TZ))
    r = adm.post("/log/clear", follow_redirects=False)
    assert r.headers["location"] == "/log?done=log_cleared&name=activity-log-20261105-093015.csv"
    saved = data_dir / "backups" / "activity-log" / "activity-log-20261105-093015.csv"
    assert len(list(csv.DictReader(io.StringIO(saved.read_text("utf-8-sig"))))) == before
    log = [tuple(x) for x in conn.execute("SELECT kind, detail FROM activity_log")]
    assert log == [("admin.log_cleared", f"Cleared the activity log ({before} entries, saved as {saved.name})")]
    page = adm.get(r.headers["location"]).text
    assert "Everything in it was saved first as activity-log-20261105-093015.csv" in page
    assert 'href="/log/saved/activity-log-20261105-093015.csv"' in page
    assert adm.get(f"/log/saved/{saved.name}").content == saved.read_bytes()
    assert adm.get("/log/saved/..%2Fdb%2Fspending.db").status_code == 404
    # same second again -> a new name, nothing overwritten
    adm.post("/log/clear")
    assert (saved.parent / "activity-log-20261105-093015-2.csv").exists()


def test_log_export_needs_admin_login(admin_app):
    c = _admin(admin_app)
    for path in ("/log.csv", "/log/saved/activity-log-20261105-093015.csv"):
        assert c.get(path, follow_redirects=False).status_code in (303, 401, 403)
    assert c.post("/log/clear", follow_redirects=False).status_code in (303, 401, 403)


def test_backups_are_highlighted_in_the_admin(adm, app, conn):
    from app import backup
    page = adm.get("/").text
    assert 'class="adm-last-backup is-none"' in page and "None recorded yet" in page
    _post(adm, "/backup-now")
    page = adm.get("/").text
    assert 'class="adm-last-backup"' in page and "Last backup" in page and "Backup made now: spending-" in page
    assert "· Admin" in page and 'href="/log?group=backup"' in page
    log = adm.get("/log?group=backup").text
    assert '<option value="backup" selected>Backups (1)</option>' in log
    assert '<tr class="log-backup">' in log and "Made a backup now" not in log      # one entry, not two
    backup.record_failure(app.state.cfg, "daily", OSError("disk full"))
    page = adm.get("/").text
    assert 'class="adm-last-backup is-failed"' in page and "Backup failed" in page and "Daily backup FAILED: disk full" in page
    assert '<tr class="log-backup log-failed">' in adm.get("/log").text
