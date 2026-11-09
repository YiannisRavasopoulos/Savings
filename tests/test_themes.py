import re
from pathlib import Path

import pytest

from app import main, web

from .conftest import browser, login, make_user

STATIC = Path(main.BASE_DIR) / "static"
VAR_DEF = re.compile(r"(--[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{6})")


def theme_vars(name: str) -> dict[str, str]:
    return dict(VAR_DEF.findall((STATIC / "themes" / f"{name}.css").read_text()))


def used_vars() -> set[str]:
    text = "".join((STATIC / f).read_text() for f in ("style.css", "splash.css", "app.js"))
    return set(re.findall(r"var\((--[a-z0-9-]+)\)", text)) | set(re.findall(r'v\("(--[a-z0-9-]+)"\)', text))


def test_style_css_has_no_hardcoded_colours():
    css = (STATIC / "style.css").read_text() + (STATIC / "splash.css").read_text()
    assert not re.findall(r"#[0-9a-fA-F]{3,6}\b", css)


def test_light_theme_defines_every_colour_used():
    # variables style.css declares itself (layout values such as the splash letters' offsets) aren't theme colours
    local = set(re.findall(r"(--[a-z0-9-]+)\s*:", (STATIC / "style.css").read_text() + (STATIC / "splash.css").read_text()))
    missing = used_vars() - set(theme_vars("light")) - local
    assert not missing


@pytest.mark.parametrize("name", web.available_themes())
def test_every_theme_only_overrides_known_colours(name):
    assert set(theme_vars(name)) <= set(theme_vars("light"))


def test_dark_theme_overrides_everything():
    assert set(theme_vars("dark")) == set(theme_vars("light"))


# --- readability: WCAG contrast ratios --------------------------------------------

def _lum(hex_colour: str) -> float:
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


PAIRS = [  # (foreground, background, minimum ratio)
    ("--text", "--bg", 7), ("--text", "--surface", 7), ("--text", "--th-bg", 7),
    ("--text", "--btn-bg", 7), ("--text-muted", "--surface", 4.5),
    ("--link", "--surface", 4.5), ("--link", "--bg", 4.5),
    ("--accent-text", "--accent", 4.5),
    ("--danger", "--surface", 4.5), ("--amber-text", "--surface", 4.5), ("--red", "--surface", 4.5),
    ("--text", "--flash-ok-bg", 7), ("--text", "--flash-err-bg", 7),
    ("--on-red", "--red", 4.5),
    ("--on-joint", "--joint", 4.5), ("--joint", "--surface", 4.5), ("--text", "--joint-bg", 7),
]


def colours_of(name: str) -> dict[str, str]:
    return {**theme_vars("light"), **theme_vars(name)}


def test_glass_theme_is_white_only():
    css = (STATIC / "themes" / "glass.css").read_text()
    assert "color-scheme: light" in css and "color-scheme: dark" not in css and "prefers-color-scheme" not in css
    assert theme_vars("glass")["--bg"] == "#f2f2f7" and theme_vars("glass")["--surface"] == "#ffffff"


@pytest.mark.parametrize("name", ["light", "dark", "glass", "glass-dark"])
@pytest.mark.parametrize("fg, bg, minimum", PAIRS)
def test_theme_contrast(name, fg, bg, minimum):
    colours = colours_of(name)
    ratio = contrast(colours[fg], colours[bg])
    assert ratio >= minimum, f"{name}: {fg} on {bg} = {ratio:.2f}"


def test_glass_theme_turns_on_the_glass_look(client):
    assert client.post("/profile/theme", data={"theme": "glass"}, follow_redirects=False).status_code == 303
    page = client.get("/").text
    assert '<html lang="en" data-look="glass">' in page
    assert ("/static/themes/glass.css", "") in _links(page)
    assert '<option value="glass" selected>Glass</option>' in client.get("/settings").text
    client.post("/profile/theme", data={"theme": "dark"})
    assert 'data-look="glass"' not in client.get("/").text


def test_glass_look_keeps_text_on_solid_colours():
    css = (STATIC / "style.css").read_text()
    glass = css[css.index('/* ---------- Glass look'):]
    assert "select" in glass and "option" not in glass          # open dropdown lists stay solid (PC fix)
    assert "@supports not" in glass                              # no blur available: solid panels


@pytest.mark.parametrize("name", ["light", "dark", "glass", "glass-dark"])
def test_accent_is_green(name):
    colours = colours_of(name)
    r, g, b = (int(colours["--accent"][i:i + 2], 16) for i in (1, 3, 5))
    assert g > r and g > b


# --- picker ---------------------------------------------------------------------

def _links(page: str) -> list[str]:
    return re.findall(r'<link rel="stylesheet" href="([^"?]+)[^"]*"(?: media="([^"]+)")?', page)


def test_default_theme_is_auto(client):
    page = client.get("/").text
    assert _links(page) == [("/static/themes/light.css", ""),
                            ("/static/themes/dark.css", "(prefers-color-scheme: dark)"),
                            ("/static/style.css", ""), ("/static/splash.css", "")]


@pytest.mark.parametrize("theme, links", [
    ("light", [("/static/themes/light.css", ""), ("/static/style.css", ""), ("/static/splash.css", "")]),
    ("dark", [("/static/themes/light.css", ""), ("/static/themes/dark.css", ""), ("/static/style.css", ""), ("/static/splash.css", "")]),
])
def test_pick_theme(client, conn, app, theme, links):
    r = client.post("/profile/theme", data={"theme": theme}, follow_redirects=False)
    assert r.status_code == 303
    assert _links(client.get("/month").text) == links
    assert conn.execute("SELECT theme FROM users WHERE username = 'alice'").fetchone()[0] == theme
    assert 'selected>' in client.get("/settings").text


def test_theme_is_per_user_and_survives_restart(client, conn, data_dir):
    client.post("/profile/theme", data={"theme": "dark"})
    fresh = main.create_app(env={"APP_DATA_DIR": str(data_dir)}, run_backups=False)
    again = login(browser(fresh), "alice")
    assert ("/static/themes/dark.css", "") in _links(again.get("/").text)
    make_user(conn, "bob")
    bob = login(browser(fresh), "bob")
    assert ("/static/themes/dark.css", "(prefers-color-scheme: dark)") in _links(bob.get("/").text)   # bob: auto


@pytest.mark.parametrize("bad", ["", "neon", "../style", "light.css"])
def test_unknown_theme_rejected(client, bad):
    r = client.post("/profile/theme", data={"theme": bad})
    assert r.status_code == 422


def test_assets_are_versioned(client):
    page = client.get("/").text
    assert re.search(r'/static/style\.css\?v=\d+', page)
    assert client.get("/static/themes/dark.css").status_code == 200


def test_management_command_and_health_check_are_in_place():
    import subprocess
    root = STATIC.parent.parent
    compose = (root / "docker-compose.yml").read_text()
    assert "healthcheck:" in compose and "favicon.ico" in compose and '"${RESTART:-unless-stopped}"' in compose
    cli = root / "savings"
    if cli.exists():                       # a source checkout or an installed server (not the bare image)
        assert subprocess.run(["bash", "-n", str(cli)]).returncode == 0
        out = subprocess.run(["bash", str(cli), "help"], capture_output=True, text=True).stdout
        for cmd in ("status", "check", "backup", "restore", "update", "autostart", "autocheck", "uninstall"):
            assert f"savings {cmd}" in out, cmd


# --- full screen on iPhone ------------------------------------------------------

@pytest.mark.parametrize("theme, colour, translucent", [
    ("light", "#ffffff", False), ("dark", "#1b1f1c", True), ("glass", "#f2f2f7", False),
    ("glass-dark", "#000000", True)])
def test_status_bar_matches_the_theme(client, theme, colour, translucent):
    client.post("/profile/theme", data={"theme": theme})
    page = client.get("/").text
    assert f'<meta name="theme-color" content="{colour}">' in page
    assert ('<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">' in page) is translucent
    assert "#2e7d32" not in re.search(r"<head>.*?</head>", page, re.S).group(0).split("manifest")[1]


def test_auto_theme_status_bar_follows_the_phone(client):
    page = client.get("/").text
    assert '<meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)">' in page
    assert '<meta name="theme-color" content="#1b1f1c" media="(prefers-color-scheme: dark)">' in page
    assert 'matchMedia("(prefers-color-scheme: dark)").matches' in page and "black-translucent" in page


def test_layout_respects_the_safe_areas():
    css = (STATIC / "style.css").read_text()
    assert "padding: env(safe-area-inset-top)" in css                     # top bar clears the Dynamic Island
    assert "height: env(safe-area-inset-top)" in css                      # status bar strip while scrolling
    assert "env(safe-area-inset-left)" in css and "env(safe-area-inset-right)" in css   # landscape


def test_glass_dark_theme(client):
    css = (STATIC / "themes" / "glass-dark.css").read_text()
    assert "color-scheme: dark" in css and "prefers-color-scheme" not in css
    assert set(theme_vars("glass-dark")) == set(theme_vars("dark"))          # sets every colour, like Dark
    assert theme_vars("glass-dark")["--accent"] == theme_vars("light")["--accent"]   # the app's green
    client.post("/profile/theme", data={"theme": "glass-dark"})
    page = client.get("/").text
    assert '<html lang="en" data-look="glass" data-glass="dark">' in page
    assert '<option value="glass-dark" selected>Glass Dark</option>' in client.get("/settings").text
    client.post("/profile/theme", data={"theme": "glass"})
    assert 'data-glass="dark"' not in client.get("/").text and 'data-look="glass"' in client.get("/").text


def test_glass_background_is_pinned_to_the_screen():
    """iPhone Safari ignores background-attachment: fixed; the glow layer is a fixed pseudo-element."""
    css = (STATIC / "style.css").read_text()
    assert "background-attachment" not in css
    assert 'html[data-look="glass"]::before {\n  content: ""; position: fixed;' in css
    assert 'html[data-glass="dark"]::before {' in css
