"""Offline page for the home-screen app (service worker)."""
from .conftest import browser


def test_service_worker_is_public_and_versioned(app, client):
    r = browser(app).get("/sw.js")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/javascript")
    assert r.headers["cache-control"] == "no-cache" and r.headers["service-worker-allowed"] == "/"
    assert f'const VERSION = "{app.state.static_v}"' in r.text
    assert 'caches.match("/offline")' in r.text and 'mode !== "navigate"' in r.text


def test_offline_page_is_public_and_has_no_personal_data(app, client):
    r = browser(app).get("/offline")
    assert r.status_code == 200 and "Can't reach Savings" in r.text and 'id="retry"' in r.text
    assert "Alice" not in client.get("/offline").text


def test_pages_register_the_service_worker(app, client):
    assert 'navigator.serviceWorker.register("/sw.js")' in client.get("/").text
    assert "window.isSecureContext" in browser(app).get("/login").text


def test_no_recurring_catch_up_for_static_or_sw(app, client, conn, monkeypatch):
    calls = []
    monkeypatch.setattr("app.recurring.catch_up", lambda *a: calls.append(a))
    client.get("/sw.js")
    client.get("/static/style.css")
    assert calls == []
    client.get("/")
    assert len(calls) == 1
