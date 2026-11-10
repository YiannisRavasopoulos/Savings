# Installing and running

[← Savings](../README.md) · [All docs](README.md)

This page is for **using** Savings. To work on the code, see [Development](development.md).
Don't install from a copy of the code (`git clone`): download a release instead.

## Install

You need **Linux** with **Docker Engine** and the **Docker Compose plugin**, and a user that can
run `docker`. The first build needs internet (Docker downloads Python and Chart.js). After that,
Savings works offline on your network.

1. Download the latest `savings-X.Y.Z.tar.gz` (and its `.sha256`, to check it) from the
   **Releases** page.
2. Unpack it and run the installer:

   ```sh
   sha256sum -c savings-X.Y.Z.tar.gz.sha256      # optional
   tar xf savings-X.Y.Z.tar.gz
   cd savings-X.Y.Z
   ./install.sh
   ```

   It asks a few questions (press Enter to keep each suggestion): where the program goes
   (`~/Savings/server`), the data folder (`~/Savings/data`), the ports, the timezone and the
   backup time. Then it builds and starts the server, makes it start at boot and adds
   **Savings** and **Savings Admin** to your app menu. `./install.sh --help` lists the options,
   e.g. `--yes` to ask nothing.
3. Open **Savings Admin** (<http://localhost:8091>) and create the admin login.
4. Open **Savings** (`http://<this-pc's-ip>:8090/`), choose **Request an account**, and approve
   it in the admin app. Others in your household do the same from their phones.
5. In **Settings**, set your regular income and the period start day. In **Categories**, adjust
   the default categories and set budgets.

The release also contains `INSTALL.md`, the same guide in more detail.

**KDE Plasma widget (optional):** a separate download, `savings-widget-X.Y.Z.tar.gz`, with its
own `./install.sh`. See [KDE Plasma widget](widget.md).

## On your network

| | Address | Reachable from |
|---|---|---|
| **Savings** (the app) | `http://<this-pc's-ip>:8090/` | any device on your home network |
| **Savings Admin** | `http://localhost:8091/` | this PC only |

- Savings uses plain **HTTP** and is meant for your **home network**. Don't expose port 8090 to
  the internet. To use it away from home, use a VPN into your network.
- On a phone, *Add to Home Screen* makes it a full-screen app.
- If the ports clash with something else on your PC, change `PORT` / `ADMIN_PORT` in `.env`
  (below) and run `savings update`.

## The `savings` command

The installer adds a `savings` command (in `~/.local/bin`). `savings help` lists everything:

- **Overview and checkup:** `status`, and `check` (server, Docker health check, app and admin
  answering, database integrity, backup age, disk space, start-at-boot; exit code 1 on problems).
- **Running it:** `start` / `stop` / `restart` and `logs [-f]`.
- **Backups:** `backup` (now), `backups` (list) and `restore <name>`.
- **Updating:** `update` rebuilds, restarts and runs a checkup.
- **Automation:** `autostart on|off` (start with Docker at boot) and `autocheck on|off`. The latter
  is a daily systemd user timer that runs `check --notify` and shows a desktop notification only
  when something's wrong.
- **Removing it:** `uninstall` removes the program and keeps your data.

Docker also runs a **health check** every 2 minutes, so `docker ps` and `savings status` show
*healthy* or *unhealthy*.

## Starting on boot

Everything runs in one container, `savings`: the web app, with the daily backup as a background
thread inside it. Docker restarts it at boot, so no systemd unit or login script is needed.

- `savings stop` counts as "stopped on purpose": it stays down after a reboot until you run
  `savings start`.
- Docker itself must start at boot (`systemctl is-enabled docker`). The installer offers to
  enable it.
- Keep the data folder on a disk that's mounted at boot (from `/etc/fstab`). On a USB disk or
  network share that's mounted late, the container fails to start.

## Upgrading

Download the newer release and run its `./install.sh` with the same install folder. Your settings
and data are kept, and the database is upgraded automatically.

## Settings (`.env`)

The installer writes your answers to `.env` in the install folder (`~/Savings/server/.env`).
After editing it, run `savings update`.

| Variable | Default | Meaning |
|---|---|---|
| `DATA_DIR` | `~/Savings/data` | Folder with the database and backups. Absolute, or relative to the install folder. Quote it if it has spaces. |
| `PORT` | `8090` | Port of the app on your network. |
| `ADMIN_PORT` | `8091` | Port of the admin app. Published on `127.0.0.1` only, so it can't be reached from other devices. |
| `TZ` | this PC's timezone | Decides what "today" is and when the backup runs, e.g. `Europe/Berlin`. An empty or unknown name falls back to the built-in default. |
| `BACKUP_TIME` | `03:30` | Daily backup time, 24h. |
| `BACKUP_RETENTION_DAYS` | `30` | Backups older than this many days are deleted. |
| `PUID`, `PGID` | your user's | User/group the container runs as, so files in the data folder belong to you. |

### Moving the data to another disk or PC

Stop the server, move the data folder, point `DATA_DIR` at it and start again:

```sh
savings stop
mv ~/Savings/data /mnt/bigdisk/savings-data
# in ~/Savings/server/.env:
DATA_DIR=/mnt/bigdisk/savings-data
savings update
```

For a new PC: copy the data folder there, run the installer and point *Data folder* at the copy.
