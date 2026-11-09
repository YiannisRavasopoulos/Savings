"""The KDE widget's API: device tokens, summary, quick add, and the widget package."""
import re
from datetime import date

import pytest

from .conftest import browser, category_id, login, make_user

TODAY = date(2026, 11, 5)


@pytest.fixture(autouse=True)
def _today(monkeypatch):
    monkeypatch.setattr("app.config.today", lambda: TODAY)


def _token(client, name="Office PC"):
    page = client.post("/profile/widget-tokens", data={"name": name}).text
    return re.search(r'id="new-token" onclick="this.select\(\)" aria-label="New widget token"', page) and \
        re.search(r'value="(svw_[^"]+)" id="new-token"', page).group(1)


def _api(app, token):
    c = browser(app)            # a plain client: no cookies, no Origin needed
    c.headers.pop("Origin", None)
    c.headers["Authorization"] = f"Bearer {token}"
    return c


def test_create_token_shows_it_once_and_stores_only_a_hash(client, conn):
    token = _token(client)
    assert token.startswith("svw_") and len(token) > 40
    row = conn.execute("SELECT name, token_hash FROM device_tokens").fetchone()
    assert row["name"] == "Office PC" and token not in row["token_hash"]
    page = client.get("/settings").text
    assert "Office PC" in page and token not in page and "not used yet" in page
    log = conn.execute("SELECT detail FROM activity_log WHERE kind = 'account.widget_token_created'").fetchone()[0]
    assert log == "Connected a KDE widget (“Office PC”)"


def test_token_name_validation(client, conn):
    r = client.post("/profile/widget-tokens", data={"name": "  "})
    assert r.status_code == 422 and "Name the device" in r.text
    assert conn.execute("SELECT COUNT(*) FROM device_tokens").fetchone()[0] == 0


def test_summary(app, client, conn):
    conn.execute("INSERT INTO expenses (date, description, category_id, amount_cents) VALUES ('2026-11-01', 'Fuel', ?, 6000)",
                 (category_id(conn, "Transport"),))
    conn.commit()
    c = _api(app, _token(client))
    r = c.get("/api/summary")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    d = r.json()
    assert d["api"] == 1 and d["user"] == "Alice" and d["currency"] == "EUR"
    assert d["period"]["label"] == "November 2026" and d["period"]["day"] == 9 and d["period"]["days_total"] == 31
    assert d["spent"] == 6000 and d["left"] == -6000
    assert d["recent"][0] == {"date": "2026-11-01", "description": "Fuel", "category": "Transport", "joint": False,
                              "cents": 6000, "mine": True, "paid_by": "Alice", "future": False}
    assert "quick" not in d
    assert conn.execute("SELECT last_used_at FROM device_tokens").fetchone()[0] is not None


def test_widget_is_read_only(app, client, conn):
    c = _api(app, _token(client))
    cid = category_id(conn, "Groceries")
    assert c.post("/api/quick-add", json={"amount": "5", "category_id": cid, "date": "2026-11-05"}).status_code in (404, 405)
    assert c.post("/quick-add", data={"amount": "5", "category_id": cid, "date": "2026-11-05"}).status_code != 200
    assert conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 0


def test_summary_has_the_chart_data(app, client, conn):
    conn.execute("INSERT INTO expenses (date, description, category_id, amount_cents) VALUES "
                 "('2026-11-01', 'a', ?, 3000), ('2026-11-20', 'b', ?, 1000), ('2026-11-02', 'c', ?, 5000)",
                 (category_id(conn, "Groceries"), category_id(conn, "Groceries"), category_id(conn, "Transport")))
    conn.commit()
    ch = _api(app, _token(client)).get("/api/summary").json()["charts"]
    assert ch["categories"] == [{"name": "Transport", "joint": False, "spent": 5000, "future": 0},
                                {"name": "Groceries", "joint": False, "spent": 4000, "future": 1000}]
    assert ch["trend"]["labels"][-1] == "Nov" and ch["trend"]["spent_past"][-1] == 80.0
    assert ch["trend"]["spent_future"][-1] == 10.0


@pytest.mark.parametrize("header", [None, "Bearer nope", "Bearer svw_wrong", "Basic abc"])
def test_api_needs_a_valid_token(app, client, header):
    c = browser(app)
    c.headers.pop("Origin", None)
    if header:
        c.headers["Authorization"] = header
    for r in (c.get("/api/summary"),):
        assert r.status_code == 401 and "widget token" in r.json()["error"]


def test_browser_session_cookie_is_not_enough_for_the_api(client):
    assert client.get("/api/summary").status_code == 401


def test_revoke(app, client, conn):
    token = _token(client)
    c = _api(app, token)
    assert c.get("/api/summary").status_code == 200
    tid = conn.execute("SELECT id FROM device_tokens").fetchone()[0]
    r = client.post(f"/profile/widget-tokens/{tid}/revoke", follow_redirects=False)
    assert r.headers["location"] == "/settings?revoked=1#widget"
    assert c.get("/api/summary").status_code == 401


def test_tokens_are_per_user(app, client, conn):
    token = _token(client, "Attic laptop")
    make_user(conn, "bob")
    bob = login(browser(app), "bob")
    tid = conn.execute("SELECT id FROM device_tokens").fetchone()[0]
    assert bob.post(f"/profile/widget-tokens/{tid}/revoke").status_code == 404
    assert "Attic laptop" not in bob.get("/settings").text
    assert _api(app, token).get("/api/summary").json()["user"] == "Alice"


def test_disabled_user_token_stops_working(app, client, conn, uid):
    c = _api(app, _token(client))
    conn.execute("UPDATE users SET status = 'disabled' WHERE id = ?", (uid,))
    conn.commit()
    assert c.get("/api/summary").status_code == 401


def test_server_does_not_ship_the_widget(app):
    assert browser(app).get("/widget/savings.plasmoid", follow_redirects=False).status_code in (303, 404)


def test_settings_section(client):
    page = client.get("/settings").text
    assert '<h2 id="widget">KDE widget</h2>' in page and "/widget/savings.plasmoid" not in page
    assert "<code>http://testserver</code>" in page


@pytest.mark.parametrize("q, n", [("", 6), ("?periods=3", 3), ("?periods=12", 12), ("?periods=7", 6), ("?periods=x", 6)])
def test_summary_trend_length(app, client, q, n):
    t = _api(app, _token(client)).get("/api/summary" + q).json()["charts"]["trend"]
    assert len(t["labels"]) == n and len(t["spent_past"]) == n


def test_budget_status_names_the_widget_relies_on(app, client, conn, uid):
    # the widget colours bars by these exact values: "red" over budget, "amber" from 85 %, "" otherwise
    from .conftest import add_budget
    for name, spent in (("Transport", 6000), ("Groceries", 9000), ("Health", 1000)):
        cid = category_id(conn, name)
        add_budget(conn, cid, 10000 if name != "Transport" else 5000, "2026-01-01")
        conn.execute("INSERT INTO expenses (date, description, category_id, amount_cents) VALUES ('2026-11-01', 'x', ?, ?)", (cid, spent))
    conn.commit()
    b = {x["name"]: x["status"] for x in _api(app, _token(client)).get("/api/summary").json()["budgets"]}
    assert b == {"Transport": "red", "Groceries": "amber", "Health": ""}


# --- notifications for the widget -------------------------------------------------------------

def _shared_home(app, client, conn, monkeypatch):
    """Alice makes the shared category "Home" and invites Bob (see test_joint)."""
    from .test_joint import _post
    monkeypatch.setattr("app.config.today", lambda: date(2026, 11, 4))
    r = _post(client, "/categories", name="Home", budget="600", budget_from="2026-01-01", joint="1")
    cid = int(r.headers["location"].rsplit("/", 1)[1])
    make_user(conn, "bob")
    bob = login(browser(app), "bob")
    _post(client, f"/shared/{cid}/invite", username="bob")
    return cid, bob


def test_invitation_and_shared_events(app, client, conn, monkeypatch):
    cid, bob = _shared_home(app, client, conn, monkeypatch)
    bob_api = _api(app, _token(bob, "Bob's PC"))
    n = [x for x in bob_api.get("/api/summary").json()["notifications"] if x["type"] == "invite"]
    assert len(n) == 1 and n[0]["title"] == "Invitation to “Home”"
    assert n[0]["body"] == "Alice invited you to share “Home”. Open Savings to accept or decline." and n[0]["url"] == "/"
    alice_api = _api(app, _token(client))
    assert [x for x in alice_api.get("/api/summary").json()["notifications"] if x["type"] == "shared"] == []   # her own actions

    inv = conn.execute("SELECT id FROM joint_invites").fetchone()[0]
    bob.post(f"/shared/invites/{inv}/accept", data={"agree": "1"})
    shared = [x for x in alice_api.get("/api/summary").json()["notifications"] if x["type"] == "shared"]
    assert [(x["title"], x["body"], x["url"]) for x in shared] == \
        [("Home", "Bob accepted the invitation and joined.", f"/shared/{cid}")]
    assert re.fullmatch(r"log-\d+", shared[0]["id"])
    assert not [x for x in bob_api.get("/api/summary").json()["notifications"] if x["type"] == "invite"]   # accepted


def test_reset_recurring_and_budget_events(app, client, conn, monkeypatch):
    from .conftest import add_budget
    monkeypatch.setattr("app.config.today", lambda: date(2026, 11, 25))   # S = 28: resets on 28 Nov
    cid = category_id(conn, "Transport")
    add_budget(conn, cid, 5000, "2026-01-01")
    conn.execute("INSERT INTO expenses (date, description, category_id, amount_cents) VALUES ('2026-11-02', 'Fuel', ?, 6000)", (cid,))
    conn.commit()
    client.post("/recurring", data={"description": "Phone", "category_id": str(category_id(conn, "Utilities")), "amount": "20",
                                    "every_months": "1", "start_date": "2026-11-26", "end_date": "", "notes": ""})
    n = {x["type"]: x for x in _api(app, _token(client)).get("/api/summary").json()["notifications"]}
    assert n["reset"]["id"] == "reset-2026-11-28" and n["reset"]["body"] == "A new period starts in 3 days (28 Nov)."
    assert n["recurring"]["title"] == "Phone added" and n["recurring"]["body"] == "Recurring payment of €20.00, dated 26 Nov."
    assert n["budget"]["title"] == "Transport is over budget" and n["budget"]["id"] == f"budget-over-{cid}-2026-11"
    assert n["budget"]["url"] == "/month?period=2026-11"


def test_summary_has_the_username(app, client):
    d = _api(app, _token(client)).get("/api/summary").json()
    assert (d["user"], d["username"]) == ("Alice", "alice")


def test_no_browser_login_handoff(app, client):
    c = _api(app, _token(client))
    assert c.post("/api/login-link").status_code in (404, 405)                 # removed
    assert browser(app).get("/auth/widget?code=x", follow_redirects=False).headers["location"].startswith("/login")


def test_summary_has_savings_vs_budget_for_the_budget_tab(app, client, conn):
    from .conftest import add_budget
    add_budget(conn, category_id(conn, "Transport"), 31000, "2026-01-01")      # 1000 a day over 31 days
    conn.execute("INSERT INTO expenses (date, description, category_id, amount_cents) VALUES ('2026-11-01', 'Fuel', ?, 6000)",
                 (category_id(conn, "Transport"),))
    conn.commit()
    vb = _api(app, _token(client)).get("/api/summary").json()["vs_budget"]
    assert (vb["day"], vb["days"], vb["budget"]) == (9, 31, 31000)
    assert vb["balance"] == 9000 - 6000 and vb["allowed"] == 9000
    assert vb["categories"] == [{"name": "Transport", "joint": False, "budget": 31000, "spent": 6000, "fixed": 0,
                                 "daily": 6000, "allowed": 9000, "balance": 3000}]
    assert len(vb["pace"]["allowed"]) == 31 and vb["pace"]["actual"][8] == 60.0 and vb["pace"]["actual"][9] is None
