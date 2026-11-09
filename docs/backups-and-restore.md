# Backups and restore

[← Savings](../README.md) · [All docs](README.md)

## Backups

The backup runs inside the app container, as a background thread that starts and stops with the
web server. Once a day at `BACKUP_TIME` it writes:

- `backups/db/spending-YYYY-MM-DD.sqlite`: a consistent snapshot made with SQLite's online
  backup API, so it's safe while the app is running. It is integrity-checked after writing.
- `backups/csv/spending-export-YYYY-MM-DD.zip`: the CSV export, built from that snapshot.

Then it deletes files in both folders older than `BACKUP_RETENTION_DAYS`.

**Missed backups are caught up.** If the PC was off at `BACKUP_TIME`, the app notices when it
starts and makes a backup right away. It checks whether there is a snapshot from the most recent
scheduled day or later. A normal restart doesn't make extra copies, and two runs on the same day
just overwrite that day's files. Each run is logged:

```sh
docker logs -f savings 2>&1 | grep backup
```

To make a backup right now, use **Back up now** in the admin app, or:

```sh
docker compose exec app python -m app.backup --now
```

These backups live on the same disk as the database. Copy `Savings Server Data/backups/`
somewhere else now and then (another disk, another machine).

## Restore

```sh
scripts/restore.sh                               # list available snapshots
scripts/restore.sh spending-2026-11-03.sqlite    # restore one
```

The script:

1. stops the app container (which also pauses the backup schedule),
2. checks the snapshot (integrity check, and that it really is a spending database),
3. keeps a copy of the current DB as `db/spending.db.before-restore-<timestamp>`,
4. swaps the snapshot in as `db/spending.db`,
5. starts the app again.

If the check fails, the current database is left untouched. To undo a restore, run the same steps
by hand with the `before-restore` copy. Delete old `before-restore` copies yourself when you no
longer need them.
