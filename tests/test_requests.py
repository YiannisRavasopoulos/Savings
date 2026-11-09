"""Request from admin: users send, only the admin reads."""
import pytest

from app import export

from .conftest import browser, login, make_user
from .test_admin import _admin, _alert, adm, admin_app  # noqa: F401  (fixtures)


def _post(c, url, **data):
    return c.post(url, data=data, follow_redirects=False)


def test_menu_has_request_page(client):
    page = client.get("/settings").text
    assert 'action="/request"' in page and 'id="request"' in page and "Request from admin" in page
    assert client.get("/request", follow_redirects=False).headers["location"] == "/settings#request"
    page = client.get("/request").text
    assert "Something isn&#39;t working" in page and 'name="message"' in page


def test_send_message(client, conn, uid):
    r = _post(client, "/request", subject="categories", message="  Please add a Pets category.\r\nThanks!  ")
    assert r.headers["location"] == "/settings?sent=1#request"
    page = client.get("/settings?sent=1").text
    assert "Sent. The admin will see your message." in page
    assert "Pets" not in page                      # users don't get a history
    row = conn.execute("SELECT * FROM admin_messages").fetchone()
    assert (row["user_id"], row["username"], row["display_name"], row["subject"]) == (uid, "alice", "Alice", "categories")
    assert row["body"] == "Please add a Pets category.\nThanks!"


@pytest.mark.parametrize("subject, message, error", [
    ("", "hello there", "Choose a subject."),
    ("weather", "hello there", "Choose a subject."),
    ("other", "  ", "Write a short message."),
    ("other", "ok", "Write a short message."),
    ("other", "x" * 1001, "Keep it under 1000 characters (it&#39;s 1001)."),
])
def test_message_validation_keeps_what_was_typed(client, conn, subject, message, error):
    r = client.post("/request", data={"subject": subject, "message": message})
    assert r.status_code == 422 and error in r.text
    assert conn.execute("SELECT COUNT(*) FROM admin_messages").fetchone()[0] == 0
    if message.strip() and len(message) < 50:
        assert message.strip() in r.text


def test_daily_limit(client, conn):
    for i in range(10):
        assert _post(client, "/request", subject="other", message=f"message {i}").status_code == 303
    r = client.post("/request", data={"subject": "other", "message": "one too many"})
    assert r.status_code == 422 and "10 messages in the last 24 hours" in r.text
    assert conn.execute("SELECT COUNT(*) FROM admin_messages").fetchone()[0] == 10


def test_request_needs_login_and_same_site(app, client):
    assert browser(app).get("/request", follow_redirects=False).status_code == 303
    r = client.post("/request", data={"subject": "other", "message": "hello admin"},
                    headers={"Origin": "http://evil.example"})
    assert r.status_code == 403


def test_admin_sees_and_deletes_messages(adm, client, conn):
    _post(client, "/request", subject="bug", message="The <b>chart</b> is empty")
    page = adm.get("/").text
    assert "Something isn&#39;t working" in page and "Alice" in page and "(alice)" in page
    assert "The &lt;b&gt;chart&lt;/b&gt; is empty" in page          # shown as text, not HTML
    assert 'id="messages"' in page and 'class="adm-badge">1<' in page
    mid = conn.execute("SELECT id FROM admin_messages").fetchone()[0]
    r = _post(adm, f"/messages/{mid}/delete")
    assert r.headers["location"] == "/?done=message_deleted#messages"
    assert conn.execute("SELECT COUNT(*) FROM admin_messages").fetchone()[0] == 0
    r = adm.post(f"/messages/{mid}/delete")
    assert r.status_code == 404 and "no longer exists" in _alert(r.text)


def test_messages_survive_account_deletion(adm, client, conn, uid):
    _post(client, "/request", subject="account", message="Please delete my account")
    _post(adm, f"/users/{uid}/delete", confirm="alice")
    row = conn.execute("SELECT user_id, username FROM admin_messages").fetchone()
    assert tuple(row) == (None, "alice")
    assert "alice, account deleted" in adm.get("/").text


def test_other_users_never_see_messages(app, client, conn):
    _post(client, "/request", subject="income", message="ALICE-PRIVATE-NOTE")
    make_user(conn, "bob")
    bob = login(browser(app), "bob")
    for path in ("/", "/request", "/profile", "/categories"):
        assert "ALICE-PRIVATE-NOTE" not in bob.get(path).text


def test_full_backup_export_includes_messages_user_export_does_not(client, conn):
    import csv, io, zipfile
    _post(client, "/request", subject="idea", message="Dark mode for admin")
    with zipfile.ZipFile(io.BytesIO(export.build_zip(conn))) as zf:
        rows = list(csv.DictReader(io.StringIO(zf.read("admin_messages.csv").decode("utf-8-sig"))))
    assert rows[0]["body"] == "Dark mode for admin"
    with zipfile.ZipFile(io.BytesIO(client.get("/export.zip").content)) as zf:
        assert "admin_messages.csv" not in zf.namelist()


# --- swipe navigation was replaced by the phone tab bar ---------------------------------

def test_swipe_script_is_gone(client):
    assert "swipe.js" not in client.get("/month").text and "data-swipe-pages" not in client.get("/").text
    assert client.get("/static/swipe.js").status_code == 404


# --- "Delete my account" request --------------------------------------------------------

def test_delete_account_option_is_last_and_red(client, monkeypatch):
    import html, re
    from datetime import date
    monkeypatch.setattr("app.config.today", lambda: date(2026, 11, 4))
    page = client.get("/settings").text
    options = re.findall(r'<option value="([^"]*)"', page.split('id="f-subject"')[1].split("</select>")[0])
    assert options[-1] == "delete_account"
    assert '<option value="delete_account" class="option-danger">Delete my account</option>' in page
    text = html.unescape(re.search(r'data-delete-text="([^"]*)"', page).group(1))
    assert text == ('Please delete my Savings account "alice" (Alice) and all of its data: expenses, '
                    "categories, budgets and income. I understand this can't be undone.\nRequested on 4 Nov 2026.")
    assert 'id="delete-note" hidden' in page


def test_delete_account_request_is_sent(client, conn, uid):
    r = _post(client, "/request", subject="delete_account", message="Please delete my Savings account")
    assert r.headers["location"] == "/settings?sent=1#request"
    assert conn.execute("SELECT subject FROM admin_messages").fetchone()[0] == "delete_account"


def test_failed_delete_request_keeps_red_state(client):
    r = client.post("/request", data={"subject": "delete_account", "message": ""})
    assert r.status_code == 422
    assert 'class="subject-danger"' in r.text
    assert 'id="delete-note" hidden' not in r.text and 'id="delete-note"' in r.text


def test_admin_sees_delete_request_in_red_with_shortcut(adm, client, conn, uid):
    _post(client, "/request", subject="delete_account", message="Please delete my Savings account")
    _post(client, "/request", subject="idea", message="Not a deletion")
    page = adm.get("/").text
    assert 'class="adm-subject adm-subject-danger">Delete my account<' in page
    assert f'data-open="dlg-delete-{uid}">Delete account…</button>' in page
    assert page.count("Delete account…") == 1          # only on the deletion request
    assert f'id="dlg-delete-{uid}"' in page
    # once the account is gone, the shortcut disappears but the message stays
    _post(adm, f"/users/{uid}/delete", confirm="alice")
    page = adm.get("/").text
    assert "Delete account…" not in page and "account deleted" in page


def test_placeholders_cannot_be_chosen(client, conn):
    """Disabled, so they can't be picked, but not hidden: a hidden selected placeholder made the
    open list unreadable on a PC (Settings → Request, Add expense)."""
    from .conftest import category_id
    page = client.get("/settings").text
    assert '<option value="" disabled selected>Choose…</option>' in page
    assert '<option value="" disabled selected>Choose…</option>' in client.get("/add").text
    conn.execute("INSERT INTO expenses (date, category_id, amount_cents) VALUES ('2026-11-01', ?, 100)",
                 (category_id(conn, "Groceries"),))   # "Move to…" only exists for a category with expenses
    conn.commit()
    assert '<option value="" disabled selected>Move to…</option>' in client.get("/categories").text
    # a submitted form without a choice sends no value at all: still a clear error
    r = client.post("/request", data={"message": "hello admin"})
    assert r.status_code == 422 and "Choose a subject." in r.text
    # with a value chosen, the placeholder is no longer the selected one
    r = client.post("/request", data={"subject": "", "message": "x"})
    assert '<option value="" disabled selected>' in r.text
    r = client.post("/request", data={"subject": "idea", "message": "x"})
    assert '<option value="" disabled>' in r.text and '<option value="idea" selected>' in r.text


def _msg(client, conn):
    _post(client, "/request", subject="bug", message="Totals look wrong")
    return conn.execute("SELECT id FROM admin_messages ORDER BY id DESC").fetchone()[0]


def _prio(conn, mid):
    return conn.execute("SELECT priority FROM admin_messages WHERE id = ?", (mid,)).fetchone()[0]


def test_admin_grades_message_priority(adm, client, conn):
    mid = _msg(client, conn)
    page = adm.get("/").text
    assert page.count('class="adm-prio-bar') == 5 and "is-on" not in page   # ungraded
    r = _post(adm, f"/messages/{mid}/priority", priority="4")
    assert r.headers["location"] == f"/?done=priority_set#msg-{mid}" and _prio(conn, mid) == 4
    page = adm.get("/").text
    assert "Priority 4/5" in page and page.count(" is-on") == 4
    assert 'value="4" class="adm-prio-bar adm-prio-4 is-on"' in page
    _post(adm, f"/messages/{mid}/priority", priority="2")
    assert _prio(conn, mid) == 2
    _post(adm, f"/messages/{mid}/priority", priority="2")            # same level again clears it
    assert _prio(conn, mid) == 0
    for bad in ("6", "-1", "x", ""):
        assert _post(adm, f"/messages/{mid}/priority", priority=bad).status_code == 422
    assert _post(adm, "/messages/9999/priority", priority="3").status_code == 404
    kinds = [r[0] for r in conn.execute("SELECT detail FROM activity_log WHERE kind = 'admin.message_priority'")]
    assert kinds == ["Set a message's priority to 4 of 5", "Set a message's priority to 2 of 5",
                     "Cleared a message's priority"]


def test_users_cannot_grade_or_see_priority(client, conn):
    mid = _msg(client, conn)
    assert client.post(f"/messages/{mid}/priority", data={"priority": "5"}).status_code == 404
    assert _prio(conn, mid) == 0


@pytest.mark.parametrize("level", [0, 1, 2])
def test_low_priority_message_deletes_with_simple_confirm(adm, client, conn, level):
    mid = _msg(client, conn)
    conn.execute("UPDATE admin_messages SET priority = ? WHERE id = ?", (level, mid))
    conn.commit()
    page = adm.get("/").text
    assert f"dlg-del-msg-{mid}" not in page and 'confirm("Delete this message?")' in page
    assert _post(adm, f"/messages/{mid}/delete").status_code == 303
    assert conn.execute("SELECT COUNT(*) FROM admin_messages").fetchone()[0] == 0


@pytest.mark.parametrize("level", [3, 4, 5])
def test_important_message_needs_warning_confirmation(adm, client, conn, level):
    mid = _msg(client, conn)
    _post(adm, f"/messages/{mid}/priority", priority=str(level))
    page = adm.get("/").text
    assert f'data-open="dlg-del-msg-{mid}"' in page and "Delete an important message?" in page
    assert f"priority {level} of 5" in page and 'name="confirm_important" value="1"' in page
    r = _post(adm, f"/messages/{mid}/delete")                         # without the warning's confirmation
    assert r.status_code == 409 and "Confirm in the warning" in _alert(r.text)
    assert _prio(conn, mid) == level
    r = _post(adm, f"/messages/{mid}/delete", confirm_important="1")
    assert r.status_code == 303 and conn.execute("SELECT COUNT(*) FROM admin_messages").fetchone()[0] == 0
    detail = conn.execute("SELECT detail FROM activity_log WHERE kind = 'admin.message_deleted'").fetchone()[0]
    assert detail == f"Deleted a message from a user (priority {level} of 5)"
