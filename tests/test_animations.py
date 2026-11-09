"""Animations: the markup and data the splash, page slides and money effects rely on.
(The animations themselves run in the browser; these check the hooks are in place.)"""
import re

from .conftest import browser, category_id


def test_head_sets_animation_state_before_first_paint(app, client):
    for page in (client.get("/").text, browser(app).get("/login").text):
        head = page.split("</head>")[0]
        assert 'localStorage.getItem("savings-animations") === "off"' in head
        assert "prefers-reduced-motion: reduce" in head and 'root.classList.add("no-anim")' in head
        assert "display-mode: standalone" in head and "navigator.standalone" in head   # splash: home-screen app only
        assert 'store.setItem("savings-splash", "1")' in head                          # once per launch
        assert 'root.setAttribute("data-splash", pick.name)' in head
        assert "skipTransition()" in head


NAMES = ["tumble", "coins", "piggy", "slots", "typewriter", "chart", "vault"]


def test_every_splash_has_markup_styles_and_a_place_in_the_rotation(app, client):
    css = client.get("/static/splash.css").text
    for page in (client.get("/").text, browser(app).get("/login").text):
        assert 'window.SAVINGS_SPLASHES = ["tumble", "coins", "piggy", "slots", "typewriter", "chart", "vault"];' in page
        assert '<link rel="stylesheet" href="/static/splash.css' in page.split("</head>")[0]
        for name in NAMES:
            assert f'<div class="sp-scene splash-{name}">' in page, name
            assert f'html[data-splash="{name}"] .splash-{name}' in css, name
            assert f'html[data-splash="{name}"] .splash-screen {{ --out:' in css, name
        assert '<div class="sp-stamp">Saved</div>' in page and '<div class="sp-note"></div>' in page
        assert 'class="sp-by"' not in page          # no author credit line
        assert "/static/fx.js" in page


def test_tumble_spells_savings(client):
    page = client.get("/").text
    block = page[page.index('<div class="sp-scene splash-tumble">'):page.index("<!-- 2. coins")]
    assert "".join(re.findall(r'--i: \d">(\w)</span>', block)) == "Savings"


def test_special_days_and_period_start_reach_the_picker(app, client, conn, uid):
    conn.execute("UPDATE users SET period_start_day = 15 WHERE id = ?", (uid,))
    conn.commit()
    head = client.get("/").text.split("</head>")[0]
    assert "window.savingsPickSplash(new Date(), 15)" in head
    assert '"Happy New Year!"' in head and '"Merry Christmas!"' in head and '"A new period begins"' in head
    assert 'return { name: "christmas", note: "Merry Christmas!" }' in head
    assert "window.savingsPickSplash(new Date(), 0)" in browser(app).get("/login").text


def test_settings_splash_picker(client):
    page = client.get("/settings").text
    assert '<select id="f-splash">' in page and 'id="splash-play"' in page
    for name in NAMES + ["rotate", "shuffle"]:
        assert f'<option value="{name}">' in page, name


def test_preview_script_builds_a_page_with_every_splash(tmp_path):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("preview", Path(__file__).resolve().parent.parent / "scripts" / "preview_splashes.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = mod.build(tmp_path)
    page = out.read_text()
    assert (tmp_path / "icon-192.png").exists() and 'src="icon-192.png"' in page and "/static/" not in page
    for name in NAMES:
        assert f'data-name="{name}"' in page and f'<div class="sp-scene splash-{name}">' in page
    assert 'data-note="Happy New Year!"' in page and 'data-note="Merry Christmas!"' in page and "Play all in turn" in page
    assert '<div class="sp-scene splash-christmas">' in page


def test_tab_links_know_their_order(client):
    page = client.get("/month").text
    for nav in (re.search(r'<nav class="nav desk-only".*?</nav>', page, re.S).group(0),
                re.search(r'<nav class="tabbar mobile-only".*?</nav>', page, re.S).group(0)):
        found = re.findall(r'href="(/[a-z]*)" data-tab="(\d)"', nav)
        assert found[:5] == [("/", "0"), ("/month", "1"), ("/budget", "2"), ("/trends", "3"), ("/year", "4")]
        assert found[5:] in ([], [("/settings", "5")])      # Settings is a tab on the phone only
    assert 'sessionStorage.setItem("savings-tab-from"' in page


def test_full_forms_carry_the_effect(client, conn):
    r = client.post("/add", data={"date": "2026-11-04", "description": "Pizza", "amount": "17,50",
                                  "category_id": str(category_id(conn, "Dining out"))}, follow_redirects=False)
    page = client.get(r.headers["location"]).text
    assert 'data-fx="damage" data-fx-cents="1750">Saved.' in page
    r = client.post("/income", data={"date": "2026-11-04", "description": "Bonus", "amount": "50"}, follow_redirects=False)
    assert r.headers["location"].endswith("&amt=5000")
    assert 'data-fx="heal" data-fx-cents="5000">Saved.' in client.get(r.headers["location"]).text
    assert 'data-fx-cents="0"' in client.get("/add?saved=1&amt=oops").text     # bad amount: no effect


def test_home_left_over_has_its_cents_for_the_counter(client):
    assert re.search(r'<div class="hero-value" data-cents="-?\d+">', client.get("/").text)


def test_quick_add_reports_the_amount(client, conn):
    j = client.post("/quick-add", data={"amount": "3", "category_id": str(category_id(conn, "Groceries")),
                                        "date": "2026-11-04"}).json()
    assert (j["kind"], j["cents"]) == ("expense", 300)


def test_settings_toggle(client):
    page = client.get("/settings").text
    assert 'id="f-animations"' in page and "Saved on this device only" in page
    assert 'localStorage.setItem("savings-animations"' in page


def test_effect_and_animation_assets(client):
    js = client.get("/static/fx.js").text
    assert "function play(kind, cents)" in js and "savings-fx" in js
    css = client.get("/static/style.css").text
    for rule in ("@view-transition { navigation: auto; }", ".fx-aura-damage", ".fx-aura-heal", "@keyframes fx-shake",
                 "@media (prefers-reduced-motion: reduce) { @view-transition { navigation: none; } }"):
        assert rule in css, rule


def test_no_style_rule_can_hide_the_page_while_a_splash_shows():
    # html gets class "splash" while a splash plays: a bare ".splash" rule would also hit <html>
    # (that once hid the whole page and the splash never ended)
    from pathlib import Path
    static = Path(__file__).resolve().parent.parent / "app" / "static"
    for name in ("style.css", "splash.css"):
        css = (static / name).read_text()
        assert not re.search(r"(^|[\s,}])\.splash(?![-\w])", css), name


def test_christmas_splash_has_its_parts(client):
    page = client.get("/").text
    block = page[page.index('<div class="sp-scene splash-christmas">'):page.index('<div class="sp-note">')]
    assert block.count("<i style=") == 16 and "sp-hat" in block
    assert "".join(re.findall(r'class="sp-bauble" style="--i: \d">(\w)</span>', block)) == "Savings"
    css = client.get("/static/splash.css").text
    assert 'html[data-splash="christmas"] .splash-christmas { display: flex; }' in css
