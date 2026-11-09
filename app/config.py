"""Settings read from the environment, plus the app's timezone."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TZ = "Europe/Athens"


def _zone(name: str | None) -> ZoneInfo:
    """The timezone from TZ in .env (e.g. Europe/Berlin); the default if it's empty or unknown."""
    try:
        return ZoneInfo((name or "").strip() or DEFAULT_TZ)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TZ)


TZ = _zone(os.environ.get("TZ"))


def now() -> datetime:
    return datetime.now(TZ)


def today() -> date:
    return now().date()


@dataclass(frozen=True)
class Config:
    data_dir: Path
    backup_time: time = time(3, 30)
    retention_days: int = 30

    @property
    def db_path(self) -> Path:
        return self.data_dir / "db" / "spending.db"

    @property
    def backups_db(self) -> Path:
        return self.data_dir / "backups" / "db"

    @property
    def backups_csv(self) -> Path:
        return self.data_dir / "backups" / "csv"


def load(env: dict | None = None) -> Config:
    env = os.environ if env is None else env
    raw_time = env.get("BACKUP_TIME", "03:30").strip() or "03:30"
    try:
        hh, mm = raw_time.split(":")
        backup_time = time(int(hh), int(mm))
    except ValueError:
        raise SystemExit(f"BACKUP_TIME must be HH:MM, got {raw_time!r}")
    try:
        retention = int(env.get("BACKUP_RETENTION_DAYS", "30") or 30)
    except ValueError:
        raise SystemExit("BACKUP_RETENTION_DAYS must be a whole number")
    if retention < 1:
        raise SystemExit("BACKUP_RETENTION_DAYS must be at least 1")
    return Config(
        data_dir=Path(env.get("APP_DATA_DIR", "/data")),
        backup_time=backup_time,
        retention_days=retention,
    )
