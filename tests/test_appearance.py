"""Appearance on this device: text size, compact lists, privacy mode, Home layout.
(Saved in the browser; these check the hooks the browser code relies on.)"""
import re


def test_head_applies_device_prefs_before_first_paint(client):
    head = client.get("/").text.split("</head>")[0]
    assert 'localStorage.getItem("savings-prefs")' in head
    for cls in ('"text-" + prefs.text', 'root.classList.add("compact")', 'root.classList.add("privacy")'):
        assert cls in head


def test_home_sections_can_be_reordered_and_hidden(client):
    page = client.get("/").text
    wrapper = page[page.index('<div class="home-sections" id="home-sections">'):]
    assert re.findall(r'data-home="(\w+)"', wrapper) == ["hero", "stats", "where", "trend", "recent"]   # no budgets yet
    assert "el.style.order = i >= 0 ? i : 100 + natural" in page and "el.hidden = true" in page


def test_settings_device_controls(client):
    page = client.get("/settings").text
    for el in ('id="f-text"', 'id="f-compact"', 'id="f-privacy"', 'id="home-layout"', 'id="home-layout-reset"'):
        assert el in page, el
    for name in ("hero", "stats", "where", "budgets", "trend", "recent"):
        assert f'["{name}", ' in page, name


def test_styles_and_privacy_script(client):
    css = client.get("/static/style.css").text
    for rule in ("html.text-small { font-size: 87.5%; }", "html.text-large { font-size: 115%; }",
                 "html.compact th, html.compact td", ".home-sections > [hidden] { display: none !important; }",
                 "html.privacy :is(.hero-value"):
        assert rule in css, rule
    assert "font-size: 1rem;" in css.split("body {")[1].split("}")[0]      # body text follows the size setting
    js = client.get("/static/prefs.js").text
    assert 'el.classList.add("revealed")' in js and "e.preventDefault()" in js
    assert "/static/prefs.js" in client.get("/").text
