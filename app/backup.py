"""Backups: once a day write a SQLite snapshot and a CSV zip, then prune old ones.

The daily schedule runs as a background thread of the web app (see main.create_app).
`python -m app.backup --now` makes one backup immediately.
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
import threading
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import audit, config, db, export

_DATED = re.compile(r"^spending-(?:export-)?(\d{4}-\d{2}-\d{2})\.(?:sqlite|zip)$")


def log(msg: str) -> None:
    print(f"[backup {config.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def snapshot(src_path: Path, dest: Path) -> None:
    """Consistent copy via SQLite's online backup API, written atomically."""
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.unlink(missing_ok=True)
    src = sqlite3.connect(src_path.resolve().as_uri() + "?mode=ro", uri=True)
    dst = sqlite3.connect(tmp)
    try:
        src.backup(dst)
        check = dst.execute("PRAGMA integrity_check").fetchone()[0]
        if check != "ok":
            raise RuntimeError(f"snapshot integrity check failed: {check}")
    finally:
        dst.close()
        src.close()
    os.replace(tmp, dest)


def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def prune(folder: Path, today: date, keep_days: int) -> list[str]:
    """Delete dated backup files older than keep_days."""
    cutoff = today - timedelta(days=keep_days)
    removed = []
    for f in sorted(folder.iterdir()):
        m = _DATED.match(f.name)
        if m and date.fromisoformat(m.group(1)) < cutoff:
            f.unlink()
            removed.append(f.name)
    return removed


# Every backup run is also recorded in the admin's activity log (group "Backups"), so the admin app
# shows when backups happened, which kind, and any failure.
REASONS = {"daily": "Daily backup", "catchup": "Catch-up backup (the scheduled one was missed)",
           "manual": "Backup made now"}


def record(cfg: config.Config, kind: str, detail: str, actor: str = "System") -> None:
    """Add a backup.<kind> entry to the activity log. Never raises: a backup isn't undone by this."""
    try:
        if not cfg.db_path.exists():
            return
        conn = db.connect(cfg.db_path)
        try:
            with conn:
                audit.log(conn, None, f"backup.{kind}", detail, actor_name=actor)
        finally:
            conn.close()
    except Exception as e:      # noqa: BLE001 - logging must not break a backup
        log(f"could not record the backup in the activity log: {e}")


def record_failure(cfg: config.Config, reason: str, error: BaseException, actor: str = "System") -> None:
    msg = str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__
    record(cfg, "failed", f"{REASONS.get(reason, 'Backup')} FAILED: {msg[:200]}", actor)


def run_once(cfg: config.Config, day: date, reason: str = "daily", actor: str = "System") -> None:
    db.ensure_data_dirs(cfg.data_dir)
    if not cfg.db_path.exists():
        log(f"no database at {cfg.db_path} yet, skipping")
        return
    snap = cfg.backups_db / f"spending-{day.isoformat()}.sqlite"
    snapshot(cfg.db_path, snap)
    log(f"snapshot written: {snap} ({snap.stat().st_size} bytes)")

    # Build the CSVs from the snapshot just taken, so both backups match exactly.
    conn = db.connect(snap)
    try:
        data = export.build_zip(conn)
    finally:
        conn.close()
    zip_path = cfg.backups_csv / export.zip_name(day)
    _write_atomic(zip_path, data)
    log(f"csv export written: {zip_path} ({len(data)} bytes)")

    conn = db.connect(cfg.db_path)
    try:
        with conn:
            trimmed = audit.prune(conn, day)
        if trimmed:
            log(f"removed {trimmed} activity log entr{'y' if trimmed == 1 else 'ies'} older than {audit.RETENTION_DAYS} days")
    finally:
        conn.close()

    n_removed = 0
    for folder in (cfg.backups_db, cfg.backups_csv):
        removed = prune(folder, day, cfg.retention_days)
        if removed:
            n_removed += len(removed)
            log(f"removed {len(removed)} old file(s) from {folder}: {', '.join(removed)}")

    detail = (f"{REASONS.get(reason, 'Backup')}: {snap.name} ({snap.stat().st_size / 1024:.1f} KB) "
              f"and CSV export {zip_path.name}")
    if n_removed:
        detail += f"; removed {n_removed} file{'' if n_removed == 1 else 's'} older than {cfg.retention_days} days"
    record(cfg, reason, detail, actor)


def next_run(now: datetime, at) -> datetime:
    target = now.replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
    if target <= now:
        target = (now + timedelta(days=1)).replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
    return target


def last_slot(now: datetime, at) -> date:
    """Date of the most recent scheduled run time at or before `now`."""
    today_slot = now.replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
    return now.date() if now >= today_slot else now.date() - timedelta(days=1)


def latest_snapshot_date(folder: Path) -> date | None:
    if not folder.is_dir():
        return None
    dates = [date.fromisoformat(m.group(1)) for f in folder.iterdir()
             if (m := _DATED.match(f.name)) and f.suffix == ".sqlite"]
    return max(dates, default=None)


def catch_up_needed(cfg: config.Config, now: datetime) -> bool:
    """True if the last scheduled backup was missed (e.g. the PC was off at that time)."""
    latest = latest_snapshot_date(cfg.backups_db)
    return latest is None or latest < last_slot(now, cfg.backup_time)


def scheduler(cfg: config.Config, stop: threading.Event) -> None:
    """Daily backup loop. Runs in a background thread of the web app until `stop` is set."""
    log(f"scheduler started: daily at {cfg.backup_time:%H:%M} {config.TZ.key}, "
        f"keeping {cfg.retention_days} days")
    if catch_up_needed(cfg, config.now()):
        latest = latest_snapshot_date(cfg.backups_db)
        log(f"last scheduled backup was missed (latest snapshot: {latest or 'none'}), running one now")
        try:
            run_once(cfg, config.today(), reason="catchup")
            log("catch-up run finished OK")
        except Exception as e:
            log("catch-up run FAILED:\n" + traceback.format_exc())
            record_failure(cfg, "catchup", e)
    while not stop.is_set():
        target = next_run(config.now(), cfg.backup_time)
        log(f"next run at {target:%Y-%m-%d %H:%M %Z}")
        target_utc = target.astimezone(timezone.utc)
        while (remaining := (target_utc - datetime.now(timezone.utc)).total_seconds()) > 0:
            if stop.wait(min(remaining, 60)):
                log("scheduler stopped")
                return
        try:
            run_once(cfg, target.date())
            log("run finished OK")
        except Exception as e:
            log("run FAILED:\n" + traceback.format_exc())
            record_failure(cfg, "daily", e)


def main(argv: list[str]) -> int:
    """Manual backup: `python -m app.backup --now`. The daily schedule runs inside the app."""
    if argv != ["--now"]:
        print("Usage: python -m app.backup --now", file=sys.stderr)
        return 2
    cfg = config.load()
    try:
        run_once(cfg, config.today(), reason="manual", actor="Command line")
    except Exception as e:
        record_failure(cfg, "manual", e, actor="Command line")
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
