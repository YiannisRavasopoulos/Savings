"""A server-wide notice (for example "on battery, shutting down soon"), shown as a banner on every page.

The host writes it as DATA_DIR/notice.json (cerberus-ups does this during a power outage):

    {"level": "warning" | "danger", "title": "...", "text": "...", "created": <unix time>, "expires": <unix time>}

Savings only ever reads the file. Anything invalid, too large or past its "expires" time is ignored,
so a file left behind (for example after a crash) disappears from the pages by itself.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

FILE_NAME = "notice.json"
MAX_BYTES = 4096
MAX_TITLE = 80
MAX_TEXT = 300
LEVELS = ("warning", "danger")

_cache: dict = {"key": None, "value": None}


def _clean(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    try:
        expires = float(raw.get("expires"))
    except (TypeError, ValueError):
        return None
    title = str(raw.get("title") or "").strip()[:MAX_TITLE]
    text = str(raw.get("text") or "").strip()[:MAX_TEXT]
    if not (title or text):
        return None
    level = raw.get("level") if raw.get("level") in LEVELS else "warning"
    return {"level": level, "title": title, "text": text, "expires": expires}


def current(data_dir: Path, now: float | None = None) -> dict | None:
    """The notice to show right now, or None. Cheap: the file is re-read only when it changes."""
    path = Path(data_dir) / FILE_NAME
    try:
        st = path.stat()
    except OSError:
        return None
    if st.st_size > MAX_BYTES:
        return None
    key = (str(path), st.st_mtime_ns, st.st_size)
    if _cache["key"] != key:
        try:
            value = _clean(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, UnicodeDecodeError):
            value = None
        _cache.update(key=key, value=value)
    n = _cache["value"]
    if n is None or n["expires"] <= (time.time() if now is None else now):
        return None
    return {k: n[k] for k in ("level", "title", "text")}
