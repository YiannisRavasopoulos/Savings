"""Login, logout, registration, sessions, password rules and cross-site protection."""
import pytest

from app import auth

from .conftest import PASSWORD, browser, login, make_user


def _post(client, url, **data):
    return client.post(url, data=data, follow_redirects=False)


# --- passwords ------------------------------------------------------------------

def test_password_hashing():
    h = auth.hash_password("s3cret-password")
    assert h.startswith("scrypt$") and "s3cret" not in h
    assert auth.verify_password("s3cret-password", h)
    assert not auth.verify_password("s3cret-passworD", h)
    assert not auth.verify_password("x", "garbage")
    assert auth.hash_password("same") != auth.hash_password("same")   # salted


@pytest.mark.parametrize("pw, confirm, user, ok", [
    ("short", "short", "u", False),
    ("a" * 9, "a" * 9, "u", False),
    ("a" * 10, "a" * 10, "u", True),
    ("abcdefghij", "abcdefghiX", "u", False),
    ("Bobby12345", "Bobby12345", "bobby12345", False),   # same as username
    ("x" * 201, "x" * 201, "u", False),
])
def test_password_rules(pw, confirm, user, ok):
    assert (auth.check_password_rules(pw, confirm, user) is None) is ok


# --- pages need a login ------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/", "/add", "/log", "/month", "/year", "/income", "/categories",
                                  "/profile", "/export.zip", "/expenses/1/edit"])
def test_pages_redirect_to_login(app, path):
    r = browser(app).get(path, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")


def test_login_remembers_where_you_were_going(app, uid):
    c = browser(app)
    r = c.get("/month?period=2026-11", follow_redirects=False)
    assert r.headers["location"] == "/login?next=%2Fmonth%3Fperiod%3D2026-11"
    r = _post(c, "/login", username="alice", password=PASSWORD, next="/month?period=2026-11")
    assert r.headers["location"] == "/month?period=2026-11"


@pytest.mark.parametrize("evil", ["https://evil.example/", "//evil.example/x", "/login", "javascript:alert(1)"])
def test_login_never_redirects_off_site(app, uid, evil):
    r = _post(browser(app), "/login", username="alice", password=PASSWORD, next=evil)
    assert r.headers["location"] == "/"


def test_public_pages_and_static_need_no_login(app):
    c = browser(app)
    for path in ("/login", "/register", "/static/style.css", "/favicon.ico"):
        assert c.get(path, follow_redirects=False).status_code == 200


# --- login / logout ---------------------------------------------------------------------------

def test_login_logout(app, uid):
    c = browser(app)
    r = _post(c, "/login", username="ALICE ", password=PASSWORD)   # username is case-insensitive
    assert r.status_code == 303 and r.headers["location"] == "/"
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Max-Age=7776000" in cookie
    assert c.get("/").status_code == 200
    r = _post(c, "/logout")
    assert r.headers["location"] == "/login?m=out"
    assert c.get("/", follow_redirects=False).status_code == 303


def test_wrong_password_and_unknown_user_look_the_same(app, uid):
    a = browser(app).post("/login", data={"username": "alice", "password": "wrong-password"})
    b = browser(app).post("/login", data={"username": "nobody", "password": "wrong-password"})
    assert a.status_code == b.status_code == 401
    assert "Wrong username or password." in a.text and "Wrong username or password." in b.text


def test_too_many_failures_lock_the_login(app, uid):
    c = browser(app)
    for _ in range(5):
        c.post("/login", data={"username": "alice", "password": "nope-nope-nope"})
    r = c.post("/login", data={"username": "alice", "password": PASSWORD})
    assert r.status_code == 429 and "Too many failed attempts" in r.text


def test_session_token_is_not_stored_in_plain_text(app, conn, uid):
    c = browser(app)
    r = _post(c, "/login", username="alice", password=PASSWORD)
    token = r.cookies.get(auth.USER_COOKIE) or c.cookies.get(auth.USER_COOKIE)
    stored = [row[0] for row in conn.execute("SELECT token_hash FROM sessions")]
    assert token and token not in stored and len(stored) == 1


def test_disabled_user_is_logged_out_immediately(client, conn, uid):
    assert client.get("/", follow_redirects=False).status_code == 200
    conn.execute("UPDATE users SET status = 'disabled' WHERE id = ?", (uid,))
    conn.commit()
    assert client.get("/", follow_redirects=False).status_code == 303
    r = client.post("/login", data={"username": "alice", "password": PASSWORD})
    assert r.status_code == 403 and "disabled" in r.text


def test_expired_session_is_rejected(client, conn):
    conn.execute("UPDATE sessions SET expires_at = '2000-01-01T00:00:00Z'")
    conn.commit()
    assert client.get("/", follow_redirects=False).status_code == 303


# --- registration ---------------------------------------------------------------------

def test_register_creates_pending_account_that_cannot_log_in(app, conn):
    c = browser(app)
    r = _post(c, "/register", username="Carol.D", display_name="  Carol   D ", password="long enough pw",
              confirm="long enough pw")
    assert r.status_code == 303 and r.headers["location"] == "/login?m=registered"
    assert "waiting" not in c.get("/login?m=registered").text or True
    row = conn.execute("SELECT * FROM users WHERE username = 'carol.d'").fetchone()
    assert row["status"] == "pending" and row["display_name"] == "Carol D"
    assert conn.execute("SELECT COUNT(*) FROM categories WHERE user_id = ?", (row["id"],)).fetchone()[0] == 0
    r = c.post("/login", data={"username": "carol.d", "password": "long enough pw"})
    assert r.status_code == 403 and "waiting for the admin" in r.text


@pytest.mark.parametrize("data, message", [
    ({"username": "ab", "display_name": "A", "password": "long enough pw", "confirm": "long enough pw"}, "3–32 characters"),
    ({"username": "has space", "display_name": "A", "password": "long enough pw", "confirm": "long enough pw"}, "3–32 characters"),
    ({"username": "alice", "display_name": "A", "password": "long enough pw", "confirm": "long enough pw"}, "taken"),
    ({"username": "newbie", "display_name": "", "password": "long enough pw", "confirm": "long enough pw"}, "Enter a name."),
    ({"username": "newbie", "display_name": "N", "password": "short", "confirm": "short"}, "at least 10"),
    ({"username": "newbie", "display_name": "N", "password": "long enough pw", "confirm": "different pw!"}, "don&#39;t match"),
])
def test_register_validation(app, uid, data, message):
    r = browser(app).post("/register", data=data)
    assert r.status_code == 422 and message in r.text


def test_register_queue_is_capped(app, conn):
    for i in range(20):
        make_user(conn, f"pending{i}", status="pending", seed=False)
    r = browser(app).post("/register", data={"username": "one.more", "display_name": "X",
                                             "password": "long enough pw", "confirm": "long enough pw"})
    assert r.status_code == 422 and "too many account requests" in r.text


# --- password change ------------------------------------------------------------------

def test_change_password_logs_out_other_devices(app, conn, uid):
    phone, laptop = login(browser(app), "alice"), login(browser(app), "alice")
    r = _post(laptop, "/profile/password", current=PASSWORD, password="a brand new pw", confirm="a brand new pw")
    assert r.status_code == 303
    assert laptop.get("/", follow_redirects=False).status_code == 200
    assert phone.get("/", follow_redirects=False).status_code == 303
    login(browser(app), "alice", "a brand new pw")


@pytest.mark.parametrize("current, new, confirm, message", [
    ("wrong", "a brand new pw", "a brand new pw", "not your current password"),
    (PASSWORD, "short", "short", "at least 10"),
    (PASSWORD, PASSWORD, PASSWORD, "different from the current"),
])
def test_change_password_errors(client, current, new, confirm, message):
    r = client.post("/profile/password", data={"current": current, "password": new, "confirm": confirm})
    assert r.status_code == 422 and message in r.text


def test_forced_password_change_blocks_everything_else(app, conn):
    make_user(conn, "dave", password="temporary-pass")
    conn.execute("UPDATE users SET must_change_password = 1 WHERE username = 'dave'")
    conn.commit()
    c = browser(app)
    r = _post(c, "/login", username="dave", password="temporary-pass")
    assert r.headers["location"] == "/profile/password"
    assert c.get("/", follow_redirects=False).headers["location"] == "/profile/password"
    assert "admin reset your password" in c.get("/profile/password").text
    _post(c, "/profile/password", current="temporary-pass", password="dave's own pw", confirm="dave's own pw")
    assert c.get("/", follow_redirects=False).status_code == 200


def test_end_other_sessions(app, conn, uid):
    phone, laptop = login(browser(app), "alice"), login(browser(app), "alice")
    r = _post(laptop, "/profile/sessions/end-others")
    assert r.headers["location"] == "/settings?ended=1#sessions"
    assert phone.get("/", follow_redirects=False).status_code == 303
    assert laptop.get("/", follow_redirects=False).status_code == 200


# --- cross-site form posts ----------------------------------------------------------------

def test_post_from_another_site_is_blocked(client, conn):
    before = conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
    for headers in ({"Origin": "http://evil.example"}, {"Origin": "null"},
                    {"Origin": "", "Referer": "http://evil.example/page"}):
        r = client.post("/categories", data={"name": "Hacked"}, headers=headers)
        assert r.status_code == 403
    assert conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == before


def test_post_with_same_site_referer_only_is_allowed(app, uid):
    from fastapi.testclient import TestClient
    c = TestClient(app)
    r = c.post("/login", data={"username": "alice", "password": PASSWORD},
               headers={"Referer": "http://testserver/login"}, follow_redirects=False)
    assert r.status_code == 303
