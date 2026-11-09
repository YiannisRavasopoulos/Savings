"""Build tmp/splash-preview/index.html from the app's splash files and open it.

Uses the real markup (app/templates/_splashes.html), styles (app/static/splash.css) and theme
colours (app/static/themes/*.css), so what you see is what the app shows.
Run: ./preview-splashes.sh            (or --no-open to only write the file)
"""
from __future__ import annotations

import html
import re
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
OUT = ROOT / "tmp" / "splash-preview"

LABELS = {
    "tumble": "Tumbling letters", "coins": "Coin rain", "piggy": "Filling up", "slots": "Slot machine",
    "typewriter": "Typewriter", "chart": "Rising chart", "vault": "Vault",
}
SPECIAL = [("christmas", "Merry Christmas!", "Christmas (24–30 Dec)"),
           ("christmas", "Happy New Year!", "New Year (31 Dec – 1 Jan)"),
           ("vault", "A new period begins", "First day of a period")]


def splash_names(base: str) -> list[str]:
    """The rotation list, read from base.html so the preview never drifts from the app."""
    m = re.search(r"SAVINGS_SPLASHES = \[([^\]]+)\]", base)
    return re.findall(r'"([a-z]+)"', m.group(1))


def build(out_dir: Path = OUT) -> Path:
    base = (APP / "templates" / "base.html").read_text()
    names = splash_names(base)
    markup = (APP / "templates" / "_splashes.html").read_text().replace("/static/icons/icon-192.png", "icon-192.png")
    light = (APP / "static" / "themes" / "light.css").read_text()
    dark = (APP / "static" / "themes" / "dark.css").read_text()
    css = (APP / "static" / "splash.css").read_text()
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(APP / "static" / "icons" / "icon-192.png", out_dir / "icon-192.png")

    buttons = "\n".join(
        f'<button data-name="{n}"><strong>{i}. {html.escape(LABELS.get(n, n))}</strong><small>{n}</small></button>'
        for i, n in enumerate(names, 1))
    specials = "\n".join(
        f'<button data-name="{n}" data-note="{html.escape(note)}"><strong>{html.escape(label)}</strong>'
        f'<small>{n} · “{html.escape(note)}”</small></button>' for n, note, label in SPECIAL)
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Savings · splash preview</title>
<style>{light}</style>
<style id="dark-theme" media="not all">{dark}</style>
<style>{css}</style>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); }}
  .list {{ max-width: 560px; margin: 0 auto; padding: 24px 16px 40px; }}
  h1 {{ font-size: 1.4rem; margin: 0 0 4px; }}
  h2 {{ font-size: 1rem; margin: 22px 0 8px; color: var(--text-muted); }}
  p {{ color: var(--text-muted); margin: 0 0 12px; }}
  .grid {{ display: grid; gap: 8px; }}
  .grid button {{ display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 14px 16px;
    font: inherit; color: var(--text); background: var(--surface); border: 1px solid var(--border); border-radius: 8px; cursor: pointer; text-align: left; }}
  .grid button:hover {{ border-color: var(--accent); }}
  .grid small {{ color: var(--text-muted); }}
  .bar {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 12px 0; }}
  .bar button, .bar label {{ font: inherit; padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border); background: var(--surface); color: var(--text); cursor: pointer; }}
  .bar .all {{ background: var(--accent); color: var(--accent-text); border-color: var(--accent); font-weight: 700; }}
  .phone {{ max-width: 430px; }}
  html.splash .list {{ visibility: hidden; }}
  html.framed.splash .splash-screen {{ left: 50%; right: auto; width: 390px; max-width: 100vw; margin-left: -195px; border-left: 1px solid var(--border); border-right: 1px solid var(--border); }}
</style>
</head>
<body>
<div class="list">
  <h1>Splash preview</h1>
  <p>Pick one: it plays exactly as in the app, then you're back here. Click a splash to skip it, like a tap in the app.</p>
  <div class="bar">
    <button class="all" id="all">▶ Play all in turn</button>
    <label><input type="checkbox" id="dark"> Dark theme</label>
    <label><input type="checkbox" id="framed"> Phone-width frame</label>
  </div>
  <h2>Rotation (daily order)</h2>
  <div class="grid">{buttons}</div>
  <h2>Special days</h2>
  <div class="grid">{specials}</div>
</div>
{markup}
<script>
  (function () {{
    var root = document.documentElement;
    function play(name, note, done) {{
      var old = document.getElementById("splash"), fresh = old.cloneNode(true);
      fresh.querySelector(".sp-note").textContent = note || "";
      root.classList.remove("splash");
      root.setAttribute("data-splash", name);
      old.replaceWith(fresh);
      void fresh.offsetWidth;
      root.classList.add("splash");
      fresh.addEventListener("click", function () {{ fresh.classList.add("splash-skip"); }});
      fresh.addEventListener("animationend", function (e) {{
        if (e.target !== fresh || e.animationName !== "splash-out") return;
        root.classList.remove("splash");
        if (done) done();
      }});
    }}
    document.querySelectorAll(".grid button").forEach(function (b) {{
      b.addEventListener("click", function () {{ play(b.dataset.name, b.dataset.note); }});
    }});
    document.getElementById("all").addEventListener("click", function () {{
      var items = [].slice.call(document.querySelectorAll(".grid button"));
      (function next(i) {{ if (i < items.length) play(items[i].dataset.name, items[i].dataset.note, function () {{ setTimeout(function () {{ next(i + 1); }}, 500); }}); }})(0);
    }});
    document.getElementById("dark").addEventListener("change", function (e) {{
      document.getElementById("dark-theme").media = e.target.checked ? "all" : "not all";
    }});
    document.getElementById("framed").addEventListener("change", function (e) {{ root.classList.toggle("framed", e.target.checked); }});
  }})();
</script>
</body>
</html>
"""
    out = out_dir / "index.html"
    out.write_text(page)
    return out


def main(argv: list[str]) -> int:
    out = build()
    print(f"Splash preview: {out}")
    if "--no-open" not in argv:
        try:
            subprocess.Popen(["xdg-open", str(out)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            webbrowser.open(out.as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
