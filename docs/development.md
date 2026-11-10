# Development

[← Savings](../README.md) · [All docs](README.md)

This page is for working on the code. To just use Savings, install a release instead:
[Installing and running](install.md). See also [CONTRIBUTING.md](../CONTRIBUTING.md).

## Quick start

Fork the repository, clone your fork, and run everything in Docker against a **throwaway data
folder** inside the repo. Never point a development copy at real data. Use a separate Compose
project and container name, so a dev `up` can't replace an installed `savings` container:

```sh
git clone <your fork> savings && cd savings
cp .env.example .env                             # check PUID/PGID against: id -u ; id -g
mkdir -p tmp/devdata                             # tmp/ is gitignored
export COMPOSE_PROJECT_NAME=savings-dev CONTAINER_NAME=savings-dev \
       DATA_DIR=./tmp/devdata PORT=18080 ADMIN_PORT=18081   # shell vars override .env
docker compose build
docker compose run --rm app pytest               # the whole suite must pass
docker compose up -d --build                     # app: http://localhost:18080/
                                                 # admin: http://localhost:18081/
docker compose down
```

After changing the code, run `docker compose up -d --build` again. Settings such as `BACKUP_TIME`
reach the container only through `.env` (or the shell variables above). For a one-off test, pass
them with `docker compose run -e BACKUP_TIME=...`.

On first start the app creates the database and the `db/` and `backups/` subfolders:

```
tmp/devdata/
├── db/spending.db
└── backups/
    ├── db/              ← daily SQLite snapshots
    └── csv/             ← daily CSV export zips
```

The data folder must exist before `up`. Otherwise `docker compose` stops with
`bind source path does not exist`, which is deliberate: Docker would quietly create it owned by
root.

## What's in the repository

The repository is the **source**. Releases are built from it and published on the Releases page;
built archives are never committed (`release/` is gitignored).

- `app/`: the server (Flask). `app/period.py` is the only place that knows how dates map to
  budget periods; `app/summary.py` has the month and year numbers; `app/main.py` the routes;
  `app/backup.py`, `app/restore.py` and `app/export.py` the backups.
- `migrations/NNN_*.sql`: applied on startup in order and tracked in `schema_version`. To change
  the schema, add a new numbered file. Never edit a released one.
- `tests/`: the test suite.
- `savings`, `scripts/`, `desktop/`, `open-savings-*.sh`: the `savings` command, restore and
  launcher helpers that the release installs.
- `widget/`: the KDE Plasma widget's source, released separately. See
  [widget/README.md](../widget/README.md).
- `packaging/`: what turns the source into releases (maintainer only, see
  [packaging/README.md](../packaging/README.md)). `packaging/app/` and `packaging/widget/` each
  hold a `make-release.sh` and the `install.sh`, `uninstall.sh` and `INSTALL.md` that ship
  **inside** that release. They only work from an unpacked release; run from a clone, the
  installers say so and stop.

Chart.js (4.5.0, pinned) is downloaded during `docker build` into `app/static/vendor/` inside the
image. The running app doesn't need internet access.

## Launchers on your PC (KDE)

`scripts/install-launchers.sh` adds **Savings** and **Savings Admin** to the app menu for this
folder (the files in `desktop/` are templates with `@DIR@`). Run it again if you move the folder;
`--remove` takes them out. The installer does this for installed copies.
