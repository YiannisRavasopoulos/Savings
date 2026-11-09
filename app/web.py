"""Shared web helpers: templates, DB connection per request, rendering."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from . import config, db, period, summary
from .money import cents_to_input, format_eur

BASE_DIR = Path(__file__).resolve().parent
THEMES_DIR = BASE_DIR / "static" / "themes"
NOW_SQL = "strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"


def _fmt_day(iso) -> str:
    d = iso if isinstance(iso, date) else date.fromisoformat(iso)
    return f"{d.day} {period.MONTH_ABBR[d.month]} {d.year}"


def _fmt_pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.0f}%"


templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.filters.update(eur=format_eur, amount_input=cents_to_input, day=_fmt_day, pct=_fmt_pct)
templates.env.globals.update(month_abbr=period.MONTH_ABBR)

def available_themes() -> list[str]:
    """Theme names = the .css files in static/themes/ (light first; it is the base)."""
    names = sorted(p.stem for p in THEMES_DIR.glob("*.css"))
    return sorted(names, key=lambda n: n != "light")


def valid_theme(theme: str | None) -> str:
    return theme if theme == "auto" or theme in available_themes() else "auto"


def get_conn(request: Request):
    conn = db.connect(request.app.state.cfg.db_path)
    try:
        yield conn
    finally:
        conn.close()


def user_id(request: Request) -> int:
    """The logged-in user's id. The auth middleware guarantees there is one on protected pages."""
    return request.state.user["id"]


def render(request: Request, name: str, status_code: int = 200, **ctx):
    user = getattr(request.state, "user", None)
    ctx.setdefault("user", user)
    ctx.setdefault("theme", valid_theme(user["theme"]) if user else "auto")
    ctx.setdefault("static_v", request.app.state.static_v)
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def current_period(conn, uid: int) -> tuple[int, int]:
    return period.period_for_date(config.today(), summary.get_start_day(conn, uid))
