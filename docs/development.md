# Development

[← Savings](../README.md) · [All docs](README.md)

Run everything in Docker, against a throwaway data folder inside this repo. **Never** run it
against the real one. Use a separate Compose project and container name, so a dev `up` can't
replace the real `savings` container:

```sh
mkdir -p tmp/devdata
export COMPOSE_PROJECT_NAME=savings-dev CONTAINER_NAME=savings-dev \
       DATA_DIR=./tmp/devdata PORT=18080         # shell vars override .env
docker compose build
docker compose run --rm app pytest
docker compose up -d                             # http://localhost:18080/
docker compose down
```

Settings such as `BACKUP_TIME` reach the container only through `.env`. For a one-off test, pass
them with `docker compose run -e BACKUP_TIME=...`.

Layout:

- `app/period.py`: the only place that knows how dates map to budget periods
- `app/summary.py`: month and year numbers
- `app/main.py`: routes
- `app/backup.py`, `app/restore.py`, `app/export.py`
- `migrations/NNN_*.sql`: applied on startup in order and tracked in `schema_version`. To change
  the schema, add a new numbered file. Never edit an applied one.

Chart.js (4.5.0, pinned) is downloaded during `docker build` into `app/static/vendor/` inside the
image. The running app doesn't need internet access.
