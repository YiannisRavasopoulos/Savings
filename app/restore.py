"""Swap a snapshot from /data/backups/db in as the live database.

Called by scripts/restore.sh while the app is stopped:
    python -m app.restore spending-YYYY-MM-DD.sqlite
    python -m app.restore --list
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys

from . import config
from .backup import snapshot


def available(cfg: config.Config) -> list[str]:
    if not cfg.backups_db.is_dir():
        return []
    return sorted(p.name for p in cfg.backups_db.glob("spending-*.sqlite"))


def restore(cfg: config.Config, name: str) -> str | None:
    """Returns the name of the safety copy of the old DB (None if there was no DB)."""
    if os.path.basename(name) != name or not name.endswith(".sqlite"):
        raise SystemExit(f"Give a snapshot file name from {cfg.backups_db}, e.g. spending-2026-11-03.sqlite")
    snap = cfg.backups_db / name
    if not snap.is_file():
        raise SystemExit(f"Snapshot not found: {snap}")

    check = sqlite3.connect(snap.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise SystemExit(f"Snapshot {name} failed the integrity check; nothing changed.")
        if not check.execute("SELECT 1 FROM sqlite_master WHERE name = 'expenses'").fetchone():
            raise SystemExit(f"{name} doesn't look like a spending database; nothing changed.")
    finally:
        check.close()

    live = cfg.db_path
    kept = None
    if live.exists():
        kept = f"spending.db.before-restore-{config.now():%Y%m%d-%H%M%S}"
        snapshot(live, live.with_name(kept))
        print(f"Kept a copy of the current database as {live.with_name(kept)}")

    tmp = live.with_name("spending.db.restoring")
    shutil.copyfile(snap, tmp)
    os.replace(tmp, live)
    for suffix in ("-wal", "-shm"):
        stale = live.with_name(live.name + suffix)
        if stale.exists():
            stale.unlink()
    print(f"Restored {snap} -> {live}")
    return kept


def main(argv: list[str]) -> int:
    cfg = config.load()
    if not argv or argv[0] == "--list":
        names = available(cfg)
        print("Available snapshots:" if names else f"No snapshots in {cfg.backups_db}")
        for n in names:
            print(f"  {n}")
        return 0 if argv else 1
    restore(cfg, argv[0])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
