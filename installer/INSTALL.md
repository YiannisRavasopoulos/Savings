# Savings: install guide

Savings is a private, self-hosted spending tracker. It runs on your own PC in Docker, you open it
in a browser (also from your phone, on the same Wi-Fi or a VPN). For KDE Plasma there's also a
panel widget, released separately. **Your data stays in one folder on your PC**. Nothing is sent anywhere.

## What you need

- **Linux** with **Docker Engine** and the **Docker Compose plugin** (`docker compose`).
  See <https://docs.docker.com/engine/install/>. Your user must be able to run `docker`, e.g. by
  being in the `docker` group.
- **Internet, for the first build only:** Docker downloads Python and Chart.js. After that, the
  app works offline on your network.
- **Optional:** KDE Plasma 6, for the panel widget (a separate download, see below).

## Install

```sh
tar xf savings-<version>.tar.gz
cd savings-<version>
./install.sh
```

It asks a few questions. Press Enter to keep each suggestion:

| Question | Suggestion | Notes |
|---|---|---|
| Install the server in | `~/Savings/server` | the program files |
| Data folder | `~/Savings/data` | your database and backups. **Point it at an existing Savings data folder to use that data** (e.g. moved from another PC); it's upgraded if needed. Keep it on a disk that's always mounted. |
| Ports | 8090 (app), 8091 (admin) | the admin app is only reachable from this PC |
| Timezone | this PC's | decides what "today" is |
| Backups | daily at 03:30, kept 30 days | inside the data folder |

Then it:
1. writes the settings to `.env`;
2. builds and starts the server, and makes it start at boot (Docker's restart policy; it offers
   to enable the Docker service if it isn't already);
3. adds **Savings** and **Savings Admin** to your app menu.

Non-interactive, e.g. for a second PC: `./install.sh --yes --data-dir /mnt/disk/savings-data
--port 8090`. See `./install.sh --help` for all the options.

## First steps

1. Open **Savings Admin** (<http://localhost:8091>) and create the admin login. This happens on
   the first visit only.
2. Open **Savings** (<http://localhost:8090>), choose **Request an account**, then approve it in
   the admin app. Others in your household can do the same from their phones.
3. **Widget (optional, KDE Plasma):** it's a separate download, `savings-widget-X.Y.Z.tar.gz`,
   with its own `./install.sh`, so it can be updated without reinstalling Savings. Add *Savings*
   to your panel, create a token in Savings → Settings → **KDE widget**, then right-click the
   widget → *Configure Savings…* and enter `http://localhost:8090` and the token.

The full manual is `README.md` in the server folder.

## Managing your server: the `savings` command

The installer adds a `savings` command (in `~/.local/bin`):

| Command | What it does |
|---|---|
| `savings status` | is it running and healthy; ports; last backup |
| `savings check` | full checkup: server and health check, app and admin answering, database integrity, backups recent, disk space, start-at-boot. It exits with code 1 if something's wrong. |
| `savings start` / `stop` / `restart` | start or stop the server |
| `savings logs` (`-f` to follow) | the server's log |
| `savings backup` | take a backup now |
| `savings backups` | list the backups |
| `savings restore <name>` | restore one (keeps a safety copy of the current database first) |
| `savings update` | rebuild and restart, then run a checkup |
| `savings autostart on`/`off` | start with Docker at boot (on by default) |
| `savings autocheck on`/`off` | a daily checkup that shows a desktop notification only if something's wrong (offered by the installer) |
| `savings open` / `savings admin` | open the app or the admin app |
| `savings uninstall` | remove the program (keeps your data) |

What runs by itself:
- **Backups:** the server backs itself up daily at the time you chose.
- **Start-up:** it starts with Docker at boot.
- **Health:** Docker checks every 2 minutes that the server answers.
- **Daily checkup:** if you turned it on, it runs once a day and 15 minutes after boot.

## Upgrade

Run `./install.sh` from a newer version and keep the same install folder. Your settings and data
are kept, and the database is upgraded automatically. The widget is upgraded with its own
release. If the widget ever says "Your Savings server is newer than this widget", install the
newest widget release.

## Move to another PC

Copy the **data folder** to the new PC, then run the installer there and point *Data folder* at
the copy.

## Uninstall

```sh
savings uninstall                 # removes the program, keeps your data
savings uninstall --delete-data   # also deletes the data folder (asks you to type its name)
```

## Licence

MIT, see `LICENSE`.
