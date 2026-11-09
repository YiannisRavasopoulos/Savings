import sqlite3
import threading
import zipfile
from datetime import date, datetime, time

import pytest
from fastapi.testclient import TestClient

from app import backup, config, db, restore
from app.main import create_app

from .conftest import category_id


def _run_scheduler(cfg, stop) -> bool:
    """Run the scheduler in a thread for up to 5 s; always stop it afterwards, so a broken test
    fails instead of leaving a thread waiting for tomorrow's backup. Returns whether it was
    still running after the 5 s."""
    t = threading.Thread(target=backup.scheduler, args=(cfg, stop), daemon=True)
    t.start()
    t.join(timeout=5)
    alive = t.is_alive()
    stop.set()
    t.join(timeout=5)
    return alive


def _count(path, table="expenses"):
    c = sqlite3.connect(path)
    try:
        return c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        c.close()


def test_run_once_writes_snapshot_and_csv(app, conn, uid):
    cfg = app.state.cfg
    conn.execute("INSERT INTO expenses (date, category_id, amount_cents) VALUES ('2026-11-01', ?, 999)", (category_id(conn, 'Other'),))
    conn.commit()
    backup.run_once(cfg, date(2026, 11, 4))
    snap = cfg.backups_db / "spending-2026-11-04.sqlite"
    assert _count(snap) == 1
    with zipfile.ZipFile(cfg.backups_csv / "spending-export-2026-11-04.zip") as zf:
        assert "expenses.csv" in zf.namelist()
    assert not list(cfg.backups_db.glob("*.tmp"))


def test_prune_keeps_retention_window(tmp_path):
    for d in ("2026-10-04", "2026-10-05", "2026-11-04"):
        (tmp_path / f"spending-{d}.sqlite").write_text("x")
    (tmp_path / "spending-export-2026-09-01.zip").write_text("x")
    (tmp_path / "notes.txt").write_text("keep me")
    removed = backup.prune(tmp_path, date(2026, 11, 4), 30)   # cutoff = 2026-10-05
    assert removed == ["spending-2026-10-04.sqlite", "spending-export-2026-09-01.zip"]
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "notes.txt", "spending-2026-10-05.sqlite", "spending-2026-11-04.sqlite"]


def test_next_run():
    tz = config.TZ
    at = time(3, 30)
    assert backup.next_run(datetime(2026, 11, 4, 1, 0, tzinfo=tz), at) == datetime(2026, 11, 4, 3, 30, tzinfo=tz)
    assert backup.next_run(datetime(2026, 11, 4, 3, 30, tzinfo=tz), at) == datetime(2026, 11, 5, 3, 30, tzinfo=tz)
    assert backup.next_run(datetime(2026, 12, 31, 23, 0, tzinfo=tz), at) == datetime(2027, 1, 1, 3, 30, tzinfo=tz)


def test_restore_swaps_snapshot_and_keeps_old_db(app, conn, uid):
    cfg = app.state.cfg
    conn.execute("INSERT INTO expenses (date, category_id, amount_cents) VALUES ('2026-11-01', ?, 100)", (category_id(conn, 'Other'),))
    conn.commit()
    backup.run_once(cfg, date(2026, 11, 3))
    conn.execute("INSERT INTO expenses (date, category_id, amount_cents) VALUES ('2026-11-02', ?, 200)", (category_id(conn, 'Other'),))
    conn.commit()
    conn.close()
    assert _count(cfg.db_path) == 2

    kept = restore.restore(cfg, "spending-2026-11-03.sqlite")
    assert _count(cfg.db_path) == 1
    assert _count(cfg.db_path.with_name(kept)) == 2


def test_restore_rejects_bad_input(app):
    cfg = app.state.cfg
    with pytest.raises(SystemExit):
        restore.restore(cfg, "../db/spending.db")
    with pytest.raises(SystemExit):
        restore.restore(cfg, "spending-1999-01-01.sqlite")
    (cfg.backups_db / "spending-2026-01-01.sqlite").write_bytes(b"not a database")
    with pytest.raises((SystemExit, sqlite3.DatabaseError)):
        restore.restore(cfg, "spending-2026-01-01.sqlite")
    assert _count(cfg.db_path) == 0   # live DB untouched


def test_scheduler_runs_when_due_and_stops(app, monkeypatch):
    """With the target time already reached, the loop runs a backup, then stops on request."""
    cfg = app.state.cfg
    stop = threading.Event()
    runs = []

    def fake_run_once(c, day, **kw):
        runs.append((day, kw.get("reason", "daily")))
        stop.set()

    monkeypatch.setattr(backup, "next_run", lambda now, at: now)
    monkeypatch.setattr(backup, "run_once", fake_run_once)
    alive = _run_scheduler(cfg, stop)
    assert not alive
    assert [day for day, _ in runs] == [config.today()]


def test_app_starts_and_stops_backup_thread(data_dir):
    app = create_app(env={"APP_DATA_DIR": str(data_dir)})
    with TestClient(app) as client:
        thread = app.state.backup_thread
        assert thread.is_alive() and thread.name == "backup-scheduler"
        assert client.get("/").status_code == 200
    thread.join(timeout=5)
    assert not thread.is_alive()


def test_manual_backup_cli(app, monkeypatch, capsys):
    monkeypatch.setenv("APP_DATA_DIR", str(app.state.cfg.data_dir))
    assert backup.main(["--now"]) == 0
    assert list(app.state.cfg.backups_db.glob("spending-*.sqlite"))
    assert backup.main([]) == 2


# --- catch-up after a missed backup (PC was off at BACKUP_TIME) ----------------------

def test_last_slot():
    tz, at = config.TZ, time(21, 0)
    assert backup.last_slot(datetime(2026, 11, 5, 10, 0, tzinfo=tz), at) == date(2026, 11, 4)
    assert backup.last_slot(datetime(2026, 11, 5, 21, 0, tzinfo=tz), at) == date(2026, 11, 5)
    assert backup.last_slot(datetime(2026, 11, 5, 23, 0, tzinfo=tz), at) == date(2026, 11, 5)
    assert backup.last_slot(datetime(2027, 1, 1, 8, 0, tzinfo=tz), at) == date(2026, 12, 31)


@pytest.mark.parametrize("existing, now, needed", [
    ([], datetime(2026, 11, 5, 10, 0), True),                               # no backups at all
    (["2026-11-03"], datetime(2026, 11, 5, 10, 0), True),                   # missed 4 Nov 21:00
    (["2026-11-04"], datetime(2026, 11, 5, 10, 0), False),                  # 4 Nov done, 5 Nov not due yet
    (["2026-11-04"], datetime(2026, 11, 5, 22, 0), True),                   # missed 5 Nov 21:00
    (["2026-11-04", "2026-11-05"], datetime(2026, 11, 5, 22, 0), False),
])
def test_catch_up_needed(tmp_path, existing, now, needed):
    cfg = config.Config(data_dir=tmp_path, backup_time=time(21, 0))
    cfg.backups_db.mkdir(parents=True)
    for d in existing:
        (cfg.backups_db / f"spending-{d}.sqlite").write_text("x")
    (cfg.backups_db / "spending-2099-01-01.sqlite.tmp").write_text("ignored")
    assert backup.catch_up_needed(cfg, now.replace(tzinfo=config.TZ)) is needed


def test_scheduler_catches_up_on_start(app, monkeypatch):
    cfg = app.state.cfg            # fresh data dir: no snapshots yet
    stop = threading.Event()
    runs = []

    def fake_run_once(c, day, **kw):
        runs.append((day, kw.get("reason")))
        stop.set()

    monkeypatch.setattr(backup, "run_once", fake_run_once)
    alive = _run_scheduler(cfg, stop)
    assert not alive
    assert runs == [(config.today(), "catchup")]


def test_scheduler_no_catch_up_when_up_to_date(app, monkeypatch):
    cfg = app.state.cfg
    backup.run_once(cfg, config.today())   # today's snapshot exists, so nothing was missed
    runs = []
    monkeypatch.setattr(backup, "run_once", lambda c, day, **kw: runs.append(day))
    stop = threading.Event()
    stop.set()
    assert not _run_scheduler(cfg, stop)
    assert runs == []


# --- every backup is recorded in the admin's activity log -------------------------------------

def _backup_log(conn):
    return conn.execute("SELECT kind, actor_name, detail FROM activity_log WHERE kind LIKE 'backup.%' ORDER BY id").fetchall()


def test_daily_backup_is_logged(app, conn):
    backup.run_once(app.state.cfg, date(2026, 11, 4))
    [(kind, who, detail)] = _backup_log(conn)
    assert (kind, who) == ("backup.daily", "System")
    assert detail.startswith("Daily backup: spending-2026-11-04.sqlite (") and "spending-export-2026-11-04.zip" in detail


def test_catch_up_and_cli_backups_are_logged(app, conn, monkeypatch):
    backup.run_once(app.state.cfg, date(2026, 11, 4), reason="catchup")
    monkeypatch.setenv("APP_DATA_DIR", str(app.state.cfg.data_dir))
    assert backup.main(["--now"]) == 0
    kinds = [(k, who) for k, who, _ in _backup_log(conn)]
    assert kinds == [("backup.catchup", "System"), ("backup.manual", "Command line")]
    assert _backup_log(conn)[0][2].startswith("Catch-up backup (the scheduled one was missed): ")


def test_failed_backup_is_logged(app, conn, monkeypatch):
    def boom(*a, **k):
        raise OSError("No space left on device")
    monkeypatch.setattr(backup, "snapshot", boom)
    with pytest.raises(OSError):
        backup.run_once(app.state.cfg, date(2026, 11, 4))
    backup.record_failure(app.state.cfg, "daily", OSError("No space left on device"))
    [(kind, who, detail)] = _backup_log(conn)
    assert (kind, who, detail) == ("backup.failed", "System", "Daily backup FAILED: No space left on device")
