"""Forgot the admin password? Remove the admin account so the next visit to the admin page
shows first-time setup again. User accounts and data are not touched.

    docker compose exec app python -m app.reset_admin
"""
from __future__ import annotations

import sys

from . import config, db


def main() -> int:
    cfg = config.load()
    conn = db.connect(cfg.db_path)
    try:
        with conn:
            n = conn.execute("DELETE FROM admin_account").rowcount
            conn.execute("DELETE FROM admin_sessions")
    finally:
        conn.close()
    print("Admin account removed. Open the admin page to create a new one." if n
          else "There was no admin account; the admin page will show first-time setup.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
