"""Shared (joint) categories, with a patched "today".

No joint periods: joining, leaving, removing and share changes take effect on the day they
happen, and each expense is split by the shares in effect on its own date. Budgets are personal.

Main scenario: Alice (moderator, own periods from the 28th) creates "Home" on 4 Nov 2026 with her
own budget €600. Bob (own periods from the 1st) accepts the same day with his own budget €250, so
from 4 Nov expenses are split 50/50.
"""
from datetime import date

import pytest

from app import joint

from .conftest import add_budget, browser, category_id, login, make_user


def _post(c, url, **data):
    return c.post(url, data=data, follow_redirects=False)


def _today(monkeypatch, d):
    monkeypatch.setattr("app.config.today", lambda: d)


def _uid(conn, name):
    return conn.execute("SELECT id FROM users WHERE username = ?", (name,)).fetchone()[0]


def _split(conn, cid, d):
    named = {}
    for u, bp in joint.split_at(conn, cid, d).items():
        row = conn.execute("SELECT username FROM users WHERE id = ?", (u,)).fetchone()
        named[row[0] if row else u] = bp
    return named


def _shares(conn, eid):
    return {r[0]: r[1] for r in conn.execute(
        "SELECT u.username, s.cents FROM expense_shares s JOIN users u ON u.id = s.user_id WHERE s.expense_id = ?", (eid,))}


def _expense(user, cid, day, amount, description="x", **extra):
    return _post(user, "/add", date=day, description=description, category_id=str(cid), amount=amount, notes="", **extra)


def _invite_and_accept(owner, member, conn, cid, username, **accept):
    _post(owner, f"/shared/{cid}/invite", username=username)
    inv = conn.execute("SELECT id FROM joint_invites WHERE user_id = ?", (_uid(conn, username),)).fetchone()[0]
    return _post(member, f"/shared/invites/{inv}/accept", agree="1", **accept)


@pytest.fixture
def home(app, client, conn, uid, monkeypatch):
    _today(monkeypatch, date(2026, 11, 4))
    r = _post(client, "/categories", name="Home", budget="600", budget_from="2026-01-01", joint="1")
    cid = int(r.headers["location"].rsplit("/", 1)[1])
    make_user(conn, "bob")
    conn.execute("UPDATE users SET period_start_day = 1 WHERE username = 'bob'")
    conn.commit()
    bob = login(browser(app), "bob")
    r = _invite_and_accept(client, bob, conn, cid, "bob", budget="250")
    assert r.headers["location"] == f"/shared/{cid}?done=joined"
    return {"cid": cid, "alice": client, "bob": bob}


# --- the maths -----------------------------------------------------------------------------

@pytest.mark.parametrize("total, weights, first, expected", [
    (1001, {1: 5000, 2: 5000}, [2], {1: 500, 2: 501}),            # tie for the leftover cent -> payer (2)
    (1001, {1: 5000, 2: 5000}, [1], {1: 501, 2: 500}),
    (1000, {1: 1, 2: 1, 3: 1}, [3], {1: 333, 2: 333, 3: 334}),
    (10000, {1: 7000, 2: 3000}, [], {1: 7000, 2: 3000}),
    (999, {1: 6667, 2: 3333}, [2], {1: 666, 2: 333}),
    (10000, {1: 1, 2: 1, 3: 1}, [1], {1: 3334, 2: 3333, 3: 3333}),
])
def test_largest_remainder(total, weights, first, expected):
    parts = joint.largest_remainder(total, weights, first)
    assert parts == expected and sum(parts.values()) == total


# --- creating, inviting, accepting ----------------------------------------------------------------

def test_create_shared_category(client, conn, uid, monkeypatch):
    _today(monkeypatch, date(2026, 11, 4))
    r = _post(client, "/categories", name="Trips", budget="300", budget_from="2026-01-01", joint="1")
    cid = int(r.headers["location"].rsplit("/", 1)[1])
    cat = conn.execute("SELECT * FROM categories WHERE id = ?", (cid,)).fetchone()
    assert (cat["is_joint"], cat["user_id"]) == (1, uid)
    m = joint.membership(conn, cid, uid)
    assert (m["role"], m["joined_from"]) == ("moderator", "2000-01-01")      # history fits
    assert _split(conn, cid, date(2026, 11, 4)) == {"alice": 10000}
    assert [tuple(r) for r in conn.execute("SELECT user_id, monthly_budget_cents FROM category_budgets "
                                           "WHERE category_id = ?", (cid,))] == [(uid, 30000)]   # her own
    page = client.get("/categories").text
    assert 'class="cat-card cat-joint' in page and 'class="joint-badge">Moderator<' in page
    assert "Edit name &amp; your budget" in page


def test_invitation_explains_joining(home, app, conn):
    make_user(conn, "carol")
    _post(home["alice"], f"/shared/{home['cid']}/invite", username="carol")
    page = login(browser(app), "carol").get("/").text
    assert "invited you to share" in page and "“Home”" in page
    assert "You join <strong>today</strong>" in page
    assert "<strong>33.33%</strong> (an equal split among 3)" in page
    assert 'name="budget"' in page and "binding" not in page


@pytest.mark.parametrize("username, message", [
    ("", "Type the person"), ("nobody", "no active account called"), ("alice", "already in it"), ("bob", "already a member"),
])
def test_invite_errors(home, username, message):
    r = home["alice"].post(f"/shared/{home['cid']}/invite", data={"username": username})
    assert r.status_code == 422 and message in r.text


def test_accept_needs_agreement_and_decline_works(app, client, conn, monkeypatch):
    _today(monkeypatch, date(2026, 11, 4))
    cid = int(_post(client, "/categories", name="Car", budget="", budget_from="", joint="1").headers["location"].rsplit("/", 1)[1])
    make_user(conn, "dave")
    dave = login(browser(app), "dave")
    _post(client, f"/shared/{cid}/invite", username="dave")
    inv = conn.execute("SELECT id FROM joint_invites").fetchone()[0]
    assert _post(dave, f"/shared/invites/{inv}/accept", back="/categories").headers["location"] == "/categories?invite=agree"
    assert _post(dave, f"/shared/invites/{inv}/accept", agree="1", budget="abc").headers["location"] == "/categories?invite=budget"
    assert joint.membership(conn, cid, _uid(conn, "dave")) is None
    assert _post(dave, f"/shared/invites/{inv}/decline", back="/").headers["location"] == "/?invite=declined"
    assert conn.execute("SELECT COUNT(*) FROM joint_invites").fetchone()[0] == 0


def test_after_accepting(home, conn):
    bob = _uid(conn, "bob")
    m = joint.membership(conn, home["cid"], bob)
    assert (m["role"], m["joined_from"], m["leaves_after"]) == ("member", "2026-11-04", None)
    assert _split(conn, home["cid"], date(2026, 11, 3)) == {"alice": 10000}
    assert _split(conn, home["cid"], date(2026, 11, 4)) == {"alice": 5000, "bob": 5000}
    assert [tuple(r) for r in conn.execute("SELECT user_id, monthly_budget_cents, effective_from FROM category_budgets "
                                           "WHERE category_id = ? AND user_id = ?", (home["cid"], bob))] == [(bob, 25000, "2026-11-04")]


# --- logging and splitting -------------------------------------------------------------------------

def test_cannot_log_before_joining(home):
    r = home["bob"].post("/add", data={"date": "2026-11-03", "description": "early", "category_id": str(home["cid"]),
                                       "amount": "5", "notes": ""})
    assert r.status_code == 422 and "You joined on 04 Nov 2026" in r.text


def test_expense_is_split_by_share(home, conn, monkeypatch):
    """Bob pays €10.01 on 5 Nov (50/50): 500.5 each -> the leftover cent goes to the payer."""
    _today(monkeypatch, date(2026, 11, 10))
    assert _expense(home["bob"], home["cid"], "2026-11-05", "10,01", "Groceries").status_code == 303
    e = conn.execute("SELECT * FROM expenses").fetchone()
    assert e["user_id"] == _uid(conn, "bob")
    assert _shares(conn, e["id"]) == {"alice": 500, "bob": 501}
    assert "€5.00" in home["alice"].get("/month?period=2026-11").text      # Alice: 28 Oct – 27 Nov
    assert "€5.01" in home["bob"].get("/month?period=2026-11").text        # Bob: 1 – 30 Nov
    log = home["alice"].get("/log?period=2026-11").text
    assert "Paid by Bob" in log and "your share" in log and f"/expenses/{e['id']}/edit" not in log
    assert home["alice"].get(f"/expenses/{e['id']}/edit").status_code == 404
    page = home["alice"].get(f"/shared/{home['cid']}").text
    assert "Paid by Bob" in page and "€10.01" in page


def test_editing_a_shared_expense_resplits(home, conn, monkeypatch):
    _today(monkeypatch, date(2026, 11, 10))
    _expense(home["bob"], home["cid"], "2026-11-05", "10")
    eid = conn.execute("SELECT id FROM expenses").fetchone()[0]
    _post(home["bob"], f"/expenses/{eid}/edit", date="2026-11-05", description="x", category_id=str(home["cid"]),
          amount="30", notes="")
    assert _shares(conn, eid) == {"alice": 1500, "bob": 1500}
    groceries = category_id(conn, "Groceries", _uid(conn, "bob"))
    _post(home["bob"], f"/expenses/{eid}/edit", date="2026-11-05", description="x", category_id=str(groceries),
          amount="30", notes="")
    assert _shares(conn, eid) == {"bob": 3000}


def test_rearranged_shares_apply_from_today(home, conn, monkeypatch):
    _today(monkeypatch, date(2026, 11, 10))
    alice, bob = _uid(conn, "alice"), _uid(conn, "bob")
    _expense(home["bob"], home["cid"], "2026-11-05", "100", "before")
    r = home["alice"].post(f"/shared/{home['cid']}/shares", data={f"share_{alice}": "70", f"share_{bob}": "20"})
    assert r.status_code == 422 and "add up to 90.00%" in r.text and 'id="dlg-alert"' in r.text
    r = _post(home["alice"], f"/shared/{home['cid']}/shares", **{f"share_{alice}": "70", f"share_{bob}": "30"})
    assert r.headers["location"] == f"/shared/{home['cid']}?done=shares"
    assert _split(conn, home["cid"], date(2026, 11, 9)) == {"alice": 5000, "bob": 5000}
    assert _split(conn, home["cid"], date(2026, 11, 10)) == {"alice": 7000, "bob": 3000}
    _expense(home["alice"], home["cid"], "2026-11-10", "100", "after")
    before = conn.execute("SELECT id FROM expenses WHERE description = 'before'").fetchone()[0]
    after = conn.execute("SELECT id FROM expenses WHERE description = 'after'").fetchone()[0]
    assert _shares(conn, before) == {"alice": 5000, "bob": 5000}       # earlier expenses keep their split
    assert _shares(conn, after) == {"alice": 7000, "bob": 3000}


# --- budgets are personal -------------------------------------------------------------------------

def test_each_member_has_their_own_budget(home, conn, monkeypatch):
    _today(monkeypatch, date(2026, 11, 10))
    _expense(home["bob"], home["cid"], "2026-11-05", "100")
    alice_row = home["alice"].get("/month?period=2026-11").text.split(f"category={home['cid']}\">Home</a>")[1].split("</tr>")[0]
    bob_row = home["bob"].get("/month?period=2026-11").text.split(f"category={home['cid']}\">Home</a>")[1].split("</tr>")[0]
    assert "€600.00" in alice_row and "€50.00" in alice_row and "€550.00" in alice_row
    assert "€250.00" in bob_row and "€50.00" in bob_row and "€200.00" in bob_row
    # budgets are private: neither sees the other's on the shared page
    assert "€250.00" not in home["alice"].get(f"/shared/{home['cid']}").text
    assert "€600.00" not in home["bob"].get(f"/shared/{home['cid']}").text


def test_member_sets_own_budget_but_cannot_rename(home, conn, monkeypatch):
    _today(monkeypatch, date(2026, 11, 10))
    r = _post(home["bob"], f"/categories/{home['cid']}/edit", name="Mine", budget="300", budget_from="2026-12-01")
    assert r.status_code == 303
    assert conn.execute("SELECT name FROM categories WHERE id = ?", (home["cid"],)).fetchone()[0] == "Home"
    bob = _uid(conn, "bob")
    assert ("2026-12-01", 30000) in [tuple(r) for r in conn.execute(
        "SELECT effective_from, monthly_budget_cents FROM category_budgets WHERE category_id = ? AND user_id = ?",
        (home["cid"], bob))]
    assert "Only the moderator can rename" in home["bob"].get("/categories").text
    # Alice's own budget is untouched; she can rename
    assert _post(home["alice"], f"/categories/{home['cid']}/edit", name="House", budget="", budget_from="").status_code == 303
    assert conn.execute("SELECT name FROM categories WHERE id = ?", (home["cid"],)).fetchone()[0] == "House"


def test_total_budget_card_includes_my_shared_budget(home, conn, uid, monkeypatch):
    """Alice, 'November 2026' (28 Oct – 27 Nov): Groceries €200 + Home €600 = €800.
    She spent €40 on groceries and her half of Bob's €100 = €90."""
    _today(monkeypatch, date(2026, 11, 10))
    groceries = category_id(conn, "Groceries")
    _post(home["alice"], f"/categories/{groceries}/edit", name="Groceries", budget="200", budget_from="2026-01-01")
    _expense(home["alice"], groceries, "2026-11-02", "40")
    _expense(home["bob"], home["cid"], "2026-11-05", "100")
    card = home["alice"].get("/categories").text.split('class="budget-total"')[1].split("</section>")[0]
    assert "€800.00" in card and "(incl. 1 shared, your part)" in card
    assert "€90.00 · 11%" in card and "€710.00 left in your budgets" in card


def test_shared_plan_uses_my_share_and_my_budget(home, conn, uid, monkeypatch):
    from app import forecast
    _today(monkeypatch, date(2026, 11, 10))
    conn.execute("INSERT INTO planned_purchases (user_id, name, amount_cents, category_id) VALUES (?, 'Sofa', 80000, ?)",
                 (uid, home["cid"]))
    conn.commit()
    fc = {"ready": True, "today": date(2026, 11, 10), "cushion": 0, "income_now": 0, "typical": 0, "category_typical": {},
          "periods": [{"start": date(2026, 10, 28), "end": date(2026, 11, 27), "label": "November 2026",
                       "saved_typical": 50000, "saved_cautious": 50000}]}
    (r,) = forecast.place_plans(conn, uid, fc, conn.execute("SELECT * FROM planned_purchases").fetchall())
    assert r["shared"] and r["my_price"] == 40000                 # 50 % of €800
    assert r["confident"]["label"] == "November 2026"
    assert r["category"] == {"budget": 60000, "usual": 0, "over": -20000}   # her own €600 budget


# --- leaving, removing, handing over, closing -------------------------------------------------------

def test_leaving_is_immediate_and_archives_it_for_the_leaver(home, conn, monkeypatch):
    _today(monkeypatch, date(2026, 11, 10))
    _expense(home["bob"], home["cid"], "2026-11-05", "10")
    r = _post(home["bob"], f"/shared/{home['cid']}/leave")
    assert r.headers["location"] == "/categories?done=left&name=Home"
    m = joint.membership(conn, home["cid"], _uid(conn, "bob"))
    assert (m["leaves_after"], m["leave_kind"]) == ("2026-11-09", "left")
    assert _split(conn, home["cid"], date(2026, 11, 10)) == {"alice": 10000}
    eid = conn.execute("SELECT id FROM expenses").fetchone()[0]
    assert _shares(conn, eid) == {"alice": 500, "bob": 500}               # history stays
    page = home["bob"].get(r.headers["location"]).text
    assert "You left “Home”" in page and "Home (left)" in page and "archived for you" in page
    assert home["bob"].get(f"/shared/{home['cid']}").status_code == 404
    r = home["bob"].post("/add", data={"date": "2026-11-10", "description": "late", "category_id": str(home["cid"]),
                                       "amount": "5", "notes": ""})
    assert r.status_code == 422
    assert "Home (left)" in home["bob"].get("/month?period=2026-11").text   # his €5 stays in his month


def test_remove_member_and_proportional_redistribution(home, app, conn, monkeypatch):
    """Carol joins on 6 Nov (equal thirds); 10 Nov: 60/30/10; removing Carol on 12 Nov -> 66.67/33.33."""
    make_user(conn, "carol")
    carol_c = login(browser(app), "carol")
    _today(monkeypatch, date(2026, 11, 6))
    _invite_and_accept(home["alice"], carol_c, conn, home["cid"], "carol")
    a, b, c = (_uid(conn, n) for n in ("alice", "bob", "carol"))
    assert _split(conn, home["cid"], date(2026, 11, 6)) == {"alice": 3334, "bob": 3333, "carol": 3333}
    _today(monkeypatch, date(2026, 11, 10))
    _post(home["alice"], f"/shared/{home['cid']}/shares", **{f"share_{a}": "60", f"share_{b}": "30", f"share_{c}": "10"})
    _today(monkeypatch, date(2026, 11, 12))
    r = home["alice"].post(f"/shared/{home['cid']}/members/{c}/remove")
    assert "Member removed" in r.text and "Carol has been removed" in r.text
    assert _split(conn, home["cid"], date(2026, 11, 11)) == {"alice": 6000, "bob": 3000, "carol": 1000}
    assert _split(conn, home["cid"], date(2026, 11, 12)) == {"alice": 6667, "bob": 3333}


def test_only_moderator_manages(home):
    for url, data in ((f"/shared/{home['cid']}/invite", {"username": "alice"}), (f"/shared/{home['cid']}/close", {})):
        r = home["bob"].post(url, data=data)
        assert r.status_code == 403 and "Only the moderator" in r.text


def test_moderator_must_hand_over_before_leaving(home, conn, monkeypatch):
    _today(monkeypatch, date(2026, 11, 10))
    r = home["alice"].post(f"/shared/{home['cid']}/leave")
    assert r.status_code == 409 and "hand over moderation" in r.text
    bob = _uid(conn, "bob")
    assert "done=handover" in _post(home["alice"], f"/shared/{home['cid']}/handover", member=str(bob)).headers["location"]
    assert conn.execute("SELECT user_id FROM categories WHERE id = ?", (home["cid"],)).fetchone()[0] == bob
    assert joint.membership(conn, home["cid"], bob)["role"] == "moderator"
    assert _post(home["alice"], f"/shared/{home['cid']}/leave").status_code == 303


def test_close_archives_it_for_everyone_and_frees_the_name(home, conn, uid, monkeypatch):
    _today(monkeypatch, date(2026, 11, 10))
    _expense(home["alice"], home["cid"], "2026-11-05", "8")
    r = _post(home["alice"], f"/shared/{home['cid']}/close")
    assert r.headers["location"] == "/categories?done=closed&name=Home"
    cat = conn.execute("SELECT name, archived FROM categories WHERE id = ?", (home["cid"],)).fetchone()
    assert tuple(cat) == ("Home (archived)", 1)
    assert {m["leaves_after"] for m in joint.members(conn, home["cid"])} == {"2026-11-09"}
    assert home["alice"].get(f"/shared/{home['cid']}").status_code == 404
    assert "archived for you" in home["bob"].get("/categories").text
    # the name is free again
    assert _post(home["alice"], "/categories", name="Home", budget="", budget_from="").status_code == 303


def test_personal_actions_refused_for_shared(home):
    for action in ("archive", "delete"):
        r = home["alice"].post(f"/categories/{home['cid']}/{action}", data={"expected": "0"})
        assert r.status_code == 409 and "managed from their own page" in r.text


# --- privacy ---------------------------------------------------------------------------------------

def test_outsiders_see_nothing(home, app, conn, monkeypatch):
    _today(monkeypatch, date(2026, 11, 10))
    _expense(home["bob"], home["cid"], "2026-11-05", "42", "BOB-SECRET")
    make_user(conn, "eve")
    eve = login(browser(app), "eve")
    assert eve.get(f"/shared/{home['cid']}").status_code == 404
    for path in ("/", "/log?period=2026-11", "/month?period=2026-11", "/categories", "/trends"):
        page = eve.get(path).text
        assert "BOB-SECRET" not in page, path
        assert f"/shared/{home['cid']}" not in page and "cat-joint" not in page, path
    r = eve.post("/add", data={"date": "2026-11-05", "description": "x", "category_id": str(home["cid"]),
                               "amount": "1", "notes": ""})
    assert r.status_code == 422


def test_members_only_see_the_shared_category(home, conn, monkeypatch):
    _today(monkeypatch, date(2026, 11, 10))
    groceries = category_id(conn, "Groceries", _uid(conn, "bob"))
    _expense(home["bob"], groceries, "2026-11-05", "9", "BOB-PRIVATE")
    for path in ("/log?period=2026-11", f"/shared/{home['cid']}", "/"):
        assert "BOB-PRIVATE" not in home["alice"].get(path).text


def test_others_notes_and_one_off_stay_private(home, conn, monkeypatch):
    import csv, io, zipfile
    _today(monkeypatch, date(2026, 11, 10))
    _post(home["bob"], "/add", date="2026-11-05", description="Shared groceries", category_id=str(home["cid"]),
          amount="20", notes="BOB-PRIVATE-NOTE", one_off="1")
    log = home["alice"].get("/log?period=2026-11").text
    assert "Shared groceries" in log and "BOB-PRIVATE-NOTE" not in log and "one-off" not in log
    with zipfile.ZipFile(io.BytesIO(home["alice"].get("/export.zip").content)) as zf:
        rows = list(csv.DictReader(io.StringIO(zf.read("expenses.csv").decode("utf-8-sig"))))
    row = next(r for r in rows if r["description"] == "Shared groceries")
    assert row["notes"] == "" and row["one_off"] == "" and row["my_cost_cents"] == "1000"
    budgets = zipfile.ZipFile(io.BytesIO(home["alice"].get("/export.zip").content)).read("category_budgets.csv").decode()
    assert "25000" not in budgets                                                      # Bob's own budget stays his


# --- account deletion --------------------------------------------------------------------------------

def test_deleting_the_moderator_hands_over(home, conn, monkeypatch):
    from app import db
    _today(monkeypatch, date(2026, 11, 10))
    _expense(home["bob"], home["cid"], "2026-11-05", "10", "BOBS")
    _expense(home["alice"], home["cid"], "2026-11-06", "20", "ALICES")
    with conn:
        db.delete_user(conn, _uid(conn, "alice"))
    bob = _uid(conn, "bob")
    assert conn.execute("SELECT user_id FROM categories WHERE id = ?", (home["cid"],)).fetchone()[0] == bob
    assert joint.membership(conn, home["cid"], bob)["role"] == "moderator"
    assert [r[0] for r in conn.execute("SELECT description FROM expenses")] == ["BOBS"]
    assert _split(conn, home["cid"], date(2026, 11, 10)) == {"bob": 10000}
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_max_members(home, conn):
    for i in range(6):                                   # 2 members + 6 invites = 8
        make_user(conn, f"user{i}")
        assert "done=invited" in _post(home["alice"], f"/shared/{home['cid']}/invite", username=f"user{i}").headers["location"]
    make_user(conn, "one.more")
    r = home["alice"].post(f"/shared/{home['cid']}/invite", data={"username": "one.more"})
    assert r.status_code == 422 and "at most 8 members" in r.text


# --- turning a personal category into a shared one ----------------------------------------------

@pytest.fixture
def transport(client, conn, uid, monkeypatch):
    """Alice's personal "Transport" (own periods from the 28th) on 4 Nov 2026: 10 Oct €30, 2 Nov €20, budget €100."""
    _today(monkeypatch, date(2026, 11, 4))
    cid = category_id(conn, "Transport")
    _post(client, f"/categories/{cid}/edit", name="Transport", budget="100", budget_from="2026-01-01")
    _expense(client, cid, "2026-10-10", "30", "Train")
    _expense(client, cid, "2026-11-02", "20", "Bus")
    return cid


def test_turn_into_shared_keeps_history(client, conn, uid, transport):
    assert "€30.00" in client.get("/month?period=2026-10").text
    r = _post(client, f"/categories/{transport}/share", agree="1")
    assert r.headers["location"] == f"/shared/{transport}?done=converted"
    assert conn.execute("SELECT is_joint FROM categories WHERE id = ?", (transport,)).fetchone()[0] == 1
    m = joint.membership(conn, transport, uid)
    assert (m["role"], m["joined_from"]) == ("moderator", "2000-01-01")
    assert sorted(r[0] for r in conn.execute("SELECT cents FROM expense_shares")) == [2000, 3000]
    assert "€30.00" in client.get("/month?period=2026-10").text
    assert "€100.00" in client.get(f"/shared/{transport}").text            # her budget stays hers


def test_turned_category_shares_from_joining_day(app, client, conn, uid, transport, monkeypatch):
    _post(client, f"/categories/{transport}/share", agree="1")
    make_user(conn, "bob")
    bob = login(browser(app), "bob")
    _today(monkeypatch, date(2026, 11, 6))
    _invite_and_accept(client, bob, conn, transport, "bob")
    _expense(bob, transport, "2026-11-07", "50", "Fuel")
    eid = conn.execute("SELECT id FROM expenses WHERE description = 'Fuel'").fetchone()[0]
    assert _shares(conn, eid) == {"alice": 2500, "bob": 2500}
    assert sorted(r[0] for r in conn.execute(
        "SELECT s.cents FROM expense_shares s JOIN expenses e ON e.id = s.expense_id WHERE e.description IN ('Train', 'Bus')")) == [2000, 3000]


def test_turn_into_shared_needs_confirmation(client, conn, transport):
    r = client.post(f"/categories/{transport}/share", data={})
    assert r.status_code == 422 and "Tick the box" in r.text and f'data-reopen="dlg-share-{transport}"' in r.text
    assert conn.execute("SELECT is_joint FROM categories WHERE id = ?", (transport,)).fetchone()[0] == 0


def test_turn_into_shared_refusals(app, client, conn, uid, transport):
    gifts = category_id(conn, "Gifts")
    _post(client, f"/categories/{gifts}/archive")
    r = client.post(f"/categories/{gifts}/share", data={"agree": "1"})
    assert r.status_code == 409 and "Unarchive it first" in r.text
    _post(client, f"/categories/{transport}/share", agree="1")
    assert client.post(f"/categories/{transport}/share", data={"agree": "1"}).status_code == 409
    make_user(conn, "bob")
    assert login(browser(app), "bob").post(f"/categories/{transport}/share", data={"agree": "1"}).status_code == 404


def test_closed_unused_shared_category_can_be_deleted(home, app, conn, monkeypatch):
    _today(monkeypatch, date(2026, 11, 10))
    cid = home["cid"]
    assert home["bob"].post(f"/categories/{cid}/delete-closed").status_code == 409      # still in use
    _post(home["alice"], f"/shared/{cid}/close")
    page = home["bob"].get("/categories").text
    assert f"dlg-delete-closed-{cid}" in page and "never had any expenses" in page
    make_user(conn, "eve")
    assert login(browser(app), "eve").post(f"/categories/{cid}/delete-closed").status_code == 404
    r = _post(home["bob"], f"/categories/{cid}/delete-closed")                         # any former member
    assert r.headers["location"].startswith("/categories?done=deleted")
    assert conn.execute("SELECT COUNT(*) FROM categories WHERE id = ?", (cid,)).fetchone()[0] == 0
    for t in ("joint_members", "joint_splits", "category_budgets"):
        assert conn.execute(f"SELECT COUNT(*) FROM {t} WHERE category_id = ?", (cid,)).fetchone()[0] == 0
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_closed_shared_category_with_expenses_stays(home, conn, monkeypatch):
    _today(monkeypatch, date(2026, 11, 10))
    _expense(home["bob"], home["cid"], "2026-11-05", "10")
    _post(home["alice"], f"/shared/{home['cid']}/close")
    assert f"dlg-delete-closed-{home['cid']}" not in home["alice"].get("/categories").text
    r = home["alice"].post(f"/categories/{home['cid']}/delete-closed")
    assert r.status_code == 409 and "part of its members&#39; history" in r.text
    assert conn.execute("SELECT COUNT(*) FROM categories WHERE id = ?", (home["cid"],)).fetchone()[0] == 1


def test_shared_category_is_purple_everywhere(home, conn, monkeypatch):
    _today(monkeypatch, date(2026, 11, 10))
    _expense(home["bob"], home["cid"], "2026-11-05", "100", "Groceries")
    month = home["alice"].get("/month?period=2026-11").text
    assert '<tr class="row-joint">' in month
    year = home["alice"].get("/year?year=2026").text
    assert '<tr class="row-joint">' in year
    page = home["alice"].get("/").text
    assert '<li class="is-joint">' in page and '<span class="joint-text">paid by Bob</span>' in page
    log = home["alice"].get("/log?period=2026-11").text
    assert '<tr class="row-joint">' in log and 'class="small joint-text">Paid by Bob<' in log
    assert "split-note" not in log                         # only in a shared category's own view


def test_log_split_note_in_shared_category_view(app, client, conn, uid, monkeypatch):
    """Alice's "Car" before Bob joins (legacy, 100 % hers), then 50/50, then 70/30."""
    _today(monkeypatch, date(2026, 11, 2))
    cid = int(_post(client, "/categories", name="Car", budget="", budget_from="", joint="1").headers["location"].rsplit("/", 1)[1])
    _expense(client, cid, "2026-11-01", "40", "Old fuel")
    make_user(conn, "bob")
    bob = login(browser(app), "bob")
    _today(monkeypatch, date(2026, 11, 4))
    _invite_and_accept(client, bob, conn, cid, "bob")
    _expense(bob, cid, "2026-11-04", "10,01", "Wash")
    _today(monkeypatch, date(2026, 11, 6))
    a, b = _uid(conn, "alice"), _uid(conn, "bob")
    _post(client, f"/shared/{cid}/shares", **{f"share_{a}": "70", f"share_{b}": "30"})
    _expense(client, cid, "2026-11-06", "20", "Tyres")
    page = client.get(f"/log?period=2026-11&category={cid}").text
    notes = page.count('class="split-note"')
    assert notes == 2                                       # not on "Old fuel"
    assert '<span class="split-part split-me">You 50% · €5.00</span> · <span class="split-part">Bob 50% · €5.01</span>' in page
    assert '<span class="split-part split-me">You 70% · €14.00</span> · <span class="split-part">Bob 30% · €6.00</span>' in page
    assert "of €20.00" in page
    bob_page = bob.get(f"/log?period=2026-11&category={cid}").text
    assert '<span class="split-part split-me">You 30% · €6.00</span> · <span class="split-part">Alice 70% · €14.00</span>' in bob_page
