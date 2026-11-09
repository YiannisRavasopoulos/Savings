# Installing and running

[← Savings](../README.md) · [All docs](README.md)

## Setup

1. **Create the data folder first, next to this folder**, as your normal user:

   ```sh
   mkdir "../Savings Server Data"
   ```

   The layout you end up with:

   ```
   <parent>/
   ├── <server folder>/         ← this folder (the server files)
   └── Savings Server Data/     ← live data (the app creates the subfolders)
       ├── db/spending.db
       └── backups/
           ├── db/              ← daily SQLite snapshots
           └── csv/             ← daily CSV export zips
   ```

   If the folder is missing, `docker compose` refuses to start with
   `bind source path does not exist`. That's deliberate. Otherwise Docker would quietly create
   it owned by root.

2. Create your `.env`:

   ```sh
   cp .env.example .env
   ```

   Check `PUID`/`PGID` against `id -u` and `id -g` so files in the data folder belong to you.

3. Start it:

   ```sh
   ./start-savings-server.sh        # = docker compose up -d --build, then opens the browser
   ```

   On first start the app creates the database and the `db/` and `backups/` subfolders.

4. **Create the admin account.** On this PC, open `http://localhost:8091/` (or the
   "Savings Admin" launcher) and choose an admin username and password.

5. **Create your own account.** Open `http://<server-ip>:8090/`, tap *Request one* on the login
   page and register. Then approve the request in the admin app and log in. (Or create the user
   directly in the admin app; it shows a one-time temporary password.)

6. In **Settings**, set your regular income (with an "effective from" date) and the period start
   day if it isn't 28. In **Categories**, adjust the default categories (Groceries, Housing,
   Utilities, Transport, Dining out, Health, Shopping, Entertainment, Subscriptions, Gifts, Travel,
   Other) and set budgets.

To update after changing the code: `./start-savings-server.sh` again.

### Launchers (KDE)

- `desktop/savings.desktop` ("Savings", green icon) runs `open-savings-client.sh`.
- `desktop/savings-admin.desktop` ("Savings Admin", blue icon with a gear) runs
  `open-savings-admin.sh` and opens the admin app.

Both start the container if it isn't running (for example after you stopped it from the tray),
wait until the page answers, then open it in your browser. Install them and pin them:

```sh
scripts/install-launchers.sh
```

Then find them in the app menu, right-click and choose *Pin to Task Manager*. The script fills in
this folder's real path (the files in `desktop/` are templates with `@DIR@`), so run it again if
you move the folder. `scripts/install-launchers.sh --remove` takes them out.

`start-savings-server.sh` is for after code changes: it rebuilds the image, then opens the page.

### The `savings` command

`./savings` in this folder manages the server; the installer also links it as `savings` on your
PATH. `savings help` lists everything. The main commands:
- **Overview and checkup:** `status`, and `check` (server, Docker health check, app and admin
  answering, database integrity, backup age, disk space, start-at-boot; exit code 1 on problems).
- **Running it:** `start` / `stop` / `restart` and `logs [-f]`.
- **Backups:** `backup` (now), `backups` (list) and `restore <name>`.
- **Updating:** `update` rebuilds, restarts and runs a checkup.
- **Automation:** `autostart on|off` (start with Docker at boot) and `autocheck on|off`. The latter
  is a daily systemd user timer that runs `check --notify` and shows a desktop notification only
  when something's wrong.

`docker-compose.yml` also has a Docker **health check**: every 2 minutes it checks that the app
answers, so `docker ps` and `savings status` show *healthy* or *unhealthy*.

### Starting on boot

This works the same way as the Jellyfin stack on this machine. Everything runs in one container,
`savings`: the web app, with the daily backup as a background thread inside it. It has
`restart: unless-stopped` and Docker starts at boot, so after the first `up -d` it comes back by
itself after every reboot. No systemd unit or login script is needed.

Keep in mind:

- `docker compose stop` (or stopping it from a tray widget) counts as "stopped on purpose": it stays down after a reboot
  until you run `./start-savings-server.sh` again. `docker compose down` removes them entirely.
  `scripts/restore.sh` starts everything again itself.
- Docker itself must be enabled at boot. Check with `systemctl is-enabled docker`. Jellyfin
  coming back after reboots suggests it already is.
- If you move `DATA_DIR` to a disk that's mounted late (USB, network share), the container will
  fail to start at boot if the folder isn't there yet. Keep it on a disk that's mounted from
  `/etc/fstab`.

Ports on this machine: Jellyfin uses 8096 and 8920, and Syncthing uses 8384, 22000 and 21027.
Savings uses **8090** (the app) and **8091** (admin, localhost only). Change `PORT` /
`ADMIN_PORT` in `.env` if that ever clashes with something.

## `.env` options

| Variable | Default | Meaning |
|---|---|---|
| `DATA_DIR` | `"../Savings Server Data"` | Host folder mounted at `/data` in the container. Keep the quotes. |
| `PORT` | `8090` | Host port for the web UI. (Jellyfin on this machine uses 8096 and 8920.) |
| `ADMIN_PORT` | `8091` | Port of the admin app. Published on `127.0.0.1` only, so it can't be reached from other devices. |
| `BACKUP_TIME` | `03:30` | Daily backup time, 24h. |
| `BACKUP_RETENTION_DAYS` | `30` | Backups older than this many days are deleted. |
| `PUID`, `PGID` | `1000` | User/group the container runs as. |
| `TZ` | `Europe/Athens` | Timezone, e.g. `Europe/Berlin`. An unknown name falls back to the default. |

The timezone is **Europe/Athens** unless `.env` sets `TZ=` (e.g. `TZ=Europe/Berlin`). It decides what "today" is and when the backup runs.

### Moving the data to another disk

Stop the app, move the folder, point `DATA_DIR` at it and start again:

```sh
docker compose down
mv "../Savings Server Data" "/mnt/bigdisk/Savings Server Data"
# in .env:
DATA_DIR="/mnt/bigdisk/Savings Server Data"
docker compose up -d
```

`DATA_DIR` can be an absolute path or a path relative to this folder.
