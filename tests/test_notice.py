"""Savings 1.7.0: a server notice from DATA_DIR/notice.json (e.g. cerberus-ups during a power outage)."""
import json
import os
import time

import pytest

from app import notice

from .conftest import browser


def write(data_dir, **kw):
    body = {"level": "warning", "title": "Server on battery", "text": "Shutting down in about 2 minutes.",
            "created": time.time(), "expires": time.time() + 600}
    body.update(kw)
    path = data_dir / "notice.json"
    path.write_text(json.dumps(body) if not isinstance(kw.get("raw"), str) else kw["raw"])
    # make sure the cache sees a change even within the same mtime tick
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    return path


# --- reading the file ----------------------------------------------------------------------------

def test_no_file_no_notice(data_dir):
    assert notice.current(data_dir) is None


def test_valid_notice(data_dir):
    write(data_dir, level="danger")
    assert notice.current(data_dir) == {"level": "danger", "title": "Server on battery",
                                        "text": "Shutting down in about 2 minutes."}


def test_expired_notice_is_ignored(data_dir):
    write(data_dir, expires=time.time() - 1)
    assert notice.current(data_dir) is None


def test_notice_expires_by_itself(data_dir):
    write(data_dir, expires=time.time() + 60)
    assert notice.current(data_dir) is not None
    assert notice.current(data_dir, now=time.time() + 61) is None


@pytest.mark.parametrize("raw", ["not json", "[]", '"text"', "{}", '{"title": "x"}', '{"expires": "soon", "title": "x"}',
                                 '{"expires": 9999999999}'])
def test_invalid_files_are_ignored(data_dir, raw):
    (data_dir / "notice.json").write_text(raw)
    assert notice.current(data_dir) is None


def test_oversized_file_is_ignored(data_dir):
    write(data_dir, text="x" * 5000)
    assert notice.current(data_dir) is None


def test_long_text_is_cut_and_unknown_level_is_warning(data_dir):
    write(data_dir, title="t" * 200, text="y" * 1000, level="party")
    n = notice.current(data_dir)
    assert len(n["title"]) == notice.MAX_TITLE and len(n["text"]) == notice.MAX_TEXT
    assert n["level"] == "warning"


def test_changes_are_picked_up(data_dir):
    write(data_dir, title="first")
    assert notice.current(data_dir)["title"] == "first"
    write(data_dir, title="second")
    assert notice.current(data_dir)["title"] == "second"
    (data_dir / "notice.json").unlink()
    assert notice.current(data_dir) is None


# --- pages and the endpoint -----------------------------------------------------------------------

def test_banner_on_pages(client, data_dir):
    write(data_dir, level="danger", title="Server shutting down")
    page = client.get("/").text
    assert 'class="server-notice danger"' in page and "Server shutting down" in page
    assert 'id="server-notice"' in page and " hidden>" not in page.split('id="server-notice"')[1][:200]


def test_banner_is_hidden_without_notice(client):
    page = client.get("/").text
    assert 'id="server-notice"' in page                      # present (for live updates) but hidden
    assert "hidden>" in page.split('id="server-notice"')[1][:200]


def test_banner_on_login_page(app, data_dir):
    write(data_dir)
    page = browser(app).get("/login").text
    assert "Server on battery" in page


def test_notice_text_is_escaped(client, data_dir):
    write(data_dir, title="<script>alert(1)</script>", text="<b>x</b>")
    page = client.get("/").text
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page


def test_endpoint_without_login(app, data_dir):
    c = browser(app)
    r = c.get("/notice.json", follow_redirects=False)
    assert r.status_code == 200 and r.json() == {"notice": None}
    assert r.headers["cache-control"] == "no-store"
    write(data_dir, level="danger")
    assert c.get("/notice.json").json()["notice"]["level"] == "danger"


def test_endpoint_exposes_only_the_notice(app, data_dir):
    write(data_dir, created=123, secret="nope")
    n = browser(app).get("/notice.json").json()["notice"]
    assert set(n) == {"level", "title", "text"}
