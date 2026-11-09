#!/usr/bin/env bash
# Restore the database from a daily snapshot.
#
#   scripts/restore.sh                              # list available snapshots
#   scripts/restore.sh spending-2026-11-03.sqlite   # restore that one
#
# Stops the app (which also pauses the backup schedule), keeps a copy of the
# current database (db/spending.db.before-restore-<timestamp>), swaps the
# snapshot in, and starts the app again. The file work happens inside a
# one-off container, using the same DATA_DIR as the app.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ $# -ne 1 ]; then
  echo "Usage: scripts/restore.sh <snapshot file name>"
  docker compose run --rm --no-deps -T app python -m app.restore --list
  exit 1
fi
snapshot="$(basename "$1")"

echo "Stopping the app..."
docker compose stop app

if docker compose run --rm --no-deps -T app python -m app.restore "$snapshot"; then
  status=0
else
  status=$?
  echo "Restore failed; the current database was not replaced."
fi

echo "Starting the app..."
docker compose up -d app
exit "$status"
