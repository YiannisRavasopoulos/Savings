"""Passwords, sessions, login throttling and the cross-site request check.

* Passwords: scrypt (stdlib hashlib), random 16-byte salt, stored as "scrypt$n$r$p$salt$hash".
* Sessions: a random token in an HttpOnly, SameSite=Lax cookie. Only its sha256 is stored, so a
  leaked database (or backup) can't be used to log in.
* Forms: every POST must come from the same origin (Origin or Referer header must match Host).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

MIN_PASSWORD = 10
MAX_PASSWORD = 200
USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,32}$")

SESSION_DAYS = 90
ADMIN_SESSION_HOURS = 12
USER_COOKIE = "savings_session"
ADMIN_COOKIE = "savings_admin"   # cookies ignore ports, so the two apps need different names

_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}


# --- passwords ----------------------------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **_SCRYPT)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${b64(salt)}${b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        got = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), dklen=len(expected),
                             n=int(n), r=int(r), p=int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, expected)


# A real hash of a random password: used so that "no such user" takes as long as "wrong password".
_DUMMY_HASH = hash_password(secrets.token_hex(16))


def check_password_rules(password: str, confirm: str, username: str = "") -> str | None:
    """Returns an error message, or None if the password is acceptable."""
    if len(password) < MIN_PASSWORD:
        return f"Use at least {MIN_PASSWORD} characters."
    if len(password) > MAX_PASSWORD:
        return f"Keep it under {MAX_PASSWORD} characters."
    if username and password.casefold() == username.casefold():
        return "The password can't be the same as the username."
    if password != confirm:
        return "The two passwords don't match."
    return None


def check_username(username: str) -> str | None:
    if not USERNAME_RE.fullmatch(username):
        return "3–32 characters: lowercase letters, digits, dot, dash or underscore."
    return None


def temporary_password() -> str:
    """Readable one-time password the admin hands over; the user must change it."""
    words = secrets.token_urlsafe(12).replace("-", "x").replace("_", "y")
    return f"{words[:4]}-{words[4:8]}-{words[8:12]}"


# --- time helpers ---------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --- user sessions -----------------------------------------------------------------------

def create_session(conn: sqlite3.Connection, user_id: int, user_agent: str = "") -> str:
    token = secrets.token_urlsafe(32)
    with conn:
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at, user_agent) VALUES (?, ?, ?, ?)",
            (_token_hash(token), user_id, _iso(_now() + timedelta(days=SESSION_DAYS)), user_agent[:200]))
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (_iso(_now()), user_id))
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (_iso(_now()),))
    return token


def session_user(conn: sqlite3.Connection, token: str | None) -> sqlite3.Row | None:
    """The active user owning this session token, or None."""
    if not token:
        return None
    th = _token_hash(token)
    row = conn.execute(
        "SELECT u.*, s.token_hash AS session_hash, s.last_seen_at AS session_seen "
        "FROM sessions s JOIN users u ON u.id = s.user_id "
        "WHERE s.token_hash = ? AND s.expires_at > ? AND u.status = 'active'",
        (th, _iso(_now()))).fetchone()
    if row and row["session_seen"] < _iso(_now() - timedelta(hours=1)):
        with conn:   # update "last seen" at most once an hour
            conn.execute("UPDATE sessions SET last_seen_at = ? WHERE token_hash = ?", (_iso(_now()), th))
    return row


def end_session(conn: sqlite3.Connection, token: str | None) -> None:
    if token:
        with conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))


def end_other_sessions(conn: sqlite3.Connection, user_id: int, keep_token: str | None) -> int:
    with conn:
        cur = conn.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?",
                           (user_id, _token_hash(keep_token or "")))
    return cur.rowcount


def end_all_sessions(conn: sqlite3.Connection, user_id: int) -> int:
    with conn:
        return conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,)).rowcount


def is_current(row, token: str | None) -> bool:
    return bool(token) and row["token_hash"] == _token_hash(token)


# --- admin sessions ------------------------------------------------------------------------

def create_admin_session(conn: sqlite3.Connection) -> str:
    token = secrets.token_urlsafe(32)
    with conn:
        conn.execute("DELETE FROM admin_sessions WHERE expires_at < ?", (_iso(_now()),))
        conn.execute("INSERT INTO admin_sessions (token_hash, expires_at) VALUES (?, ?)",
                     (_token_hash(token), _iso(_now() + timedelta(hours=ADMIN_SESSION_HOURS))))
    return token


def admin_session_valid(conn: sqlite3.Connection, token: str | None) -> bool:
    if not token:
        return False
    return conn.execute("SELECT 1 FROM admin_sessions WHERE token_hash = ? AND expires_at > ?",
                        (_token_hash(token), _iso(_now()))).fetchone() is not None


def end_admin_session(conn: sqlite3.Connection, token: str | None) -> None:
    if token:
        with conn:
            conn.execute("DELETE FROM admin_sessions WHERE token_hash = ?", (_token_hash(token),))


# --- login throttling ----------------------------------------------------------------------

class Throttle:
    """After `limit` failures for a key within `window` seconds, refuse for `lockout` seconds."""

    def __init__(self, limit: int = 5, window: int = 600, lockout: int = 300):
        self.limit, self.window, self.lockout = limit, window, lockout
        self._fails: dict[str, list[float]] = {}
        self._locked: dict[str, float] = {}
        self._lock = threading.Lock()

    def locked_for(self, key: str) -> int:
        with self._lock:
            until = self._locked.get(key, 0)
            return max(0, int(until - time.monotonic()) + 1) if until > time.monotonic() else 0

    def fail(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            recent = [t for t in self._fails.get(key, []) if now - t < self.window] + [now]
            self._fails[key] = recent
            if len(recent) >= self.limit:
                self._locked[key] = now + self.lockout
                self._fails[key] = []

    def success(self, key: str) -> None:
        with self._lock:
            self._fails.pop(key, None)
            self._locked.pop(key, None)


# --- cross-site request check ------------------------------------------------------------------

def same_origin(headers) -> bool:
    """True if a state-changing request comes from a page of this same site.

    Browsers send Origin on form POSTs (and Referer otherwise); both must name our own host:port.
    A form on another website therefore can't make your browser change your data.
    """
    host = headers.get("host", "")
    source = headers.get("origin") or headers.get("referer")
    if not source or source == "null":
        return False
    return urlsplit(source).netloc == host


# --- device tokens (the KDE widget) --------------------------------------------------------

DEVICE_TOKEN_PREFIX = "svw_"


def create_device_token(conn: sqlite3.Connection, user_id: int, name: str) -> str:
    """A new token for a device; returned once, only its hash is kept."""
    token = DEVICE_TOKEN_PREFIX + secrets.token_urlsafe(32)
    conn.execute("INSERT INTO device_tokens (user_id, name, token_hash) VALUES (?, ?, ?)",
                 (user_id, name, _token_hash(token)))
    return token


def device_token_user(conn: sqlite3.Connection, header: str | None) -> sqlite3.Row | None:
    """The active user behind an 'Authorization: Bearer svw_…' header, or None."""
    if not header or not header.startswith("Bearer "):
        return None
    token = header[len("Bearer "):].strip()
    if not token.startswith(DEVICE_TOKEN_PREFIX):
        return None
    th = _token_hash(token)
    row = conn.execute(
        "SELECT u.*, t.id AS device_token_id FROM device_tokens t JOIN users u ON u.id = t.user_id "
        "WHERE t.token_hash = ? AND u.status = 'active'", (th,)).fetchone()
    if row is not None:
        with conn:   # at most once a minute, so frequent refreshes don't keep writing
            conn.execute("UPDATE device_tokens SET last_used_at = ? WHERE id = ? AND "
                         "(last_used_at IS NULL OR last_used_at < ?)",
                         (_iso(_now()), row["device_token_id"], _iso(_now() - timedelta(minutes=1))))
    return row
