#!/usr/bin/env bash
# Savings installer: sets up the Savings server (Docker). The KDE panel widget is a separate
# release (savings-widget-X.Y.Z.tar.gz) with its own installer.
#
#   ./install.sh                 ask for each setting (Enter keeps the suggestion)
#   ./install.sh --yes           use the suggestions / the options given, ask nothing
#
# Options (all optional):
#   --install-dir DIR     where the server's files go           (default ~/Savings/server)
#   --data-dir DIR        the data folder: database + backups    (default ~/Savings/data)
#                         An existing Savings data folder is used as it is ("plugged in").
#   --port N              the app's port on your network          (default 8090)
#   --admin-port N        the admin app's port, this PC only      (default 8091)
#   --tz ZONE             timezone, e.g. Europe/Berlin            (default: this PC's)
#   --backup-time HH:MM   daily backup time                       (default 03:30)
#   --retention DAYS      keep backups this many days             (default 30)
#   --name NAME           container name                          (default savings)
#   --no-launchers        don't add app-menu launchers
#   --no-boot             don't check that Docker starts at boot
#   --no-autocheck        don't set up the daily checkup
#
# Afterwards, manage it with the "savings" command (savings help): status, check, backup,
# restore, update, autostart, autocheck, logs, uninstall.
#
# Run it again to upgrade: your settings (.env) and data are kept.
set -euo pipefail

here="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
version="$(cat "$here/server/VERSION" 2>/dev/null || echo "?")"

# ---------- defaults & options ----------
INSTALL_DIR="$HOME/Savings/server"
DATA_DIR="$HOME/Savings/data"
PORT=8090
ADMIN_PORT=8091
TZ_NAME="$(timedatectl show -p Timezone --value 2>/dev/null || true)"
[ -z "$TZ_NAME" ] && [ -f /etc/timezone ] && TZ_NAME="$(cat /etc/timezone)"
[ -z "$TZ_NAME" ] && TZ_NAME="$(readlink /etc/localtime 2>/dev/null | sed -n 's|.*/zoneinfo/||p')"
[ -z "$TZ_NAME" ] && TZ_NAME="Europe/Athens"
BACKUP_TIME="03:30"
RETENTION=30
NAME="savings"
ASK=1; LAUNCHERS=1; BOOT=1; AUTOCHECK=1

while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y) ASK=0 ;;
    --install-dir) INSTALL_DIR="$2"; shift ;;
    --data-dir) DATA_DIR="$2"; shift ;;
    --port) PORT="$2"; shift ;;
    --admin-port) ADMIN_PORT="$2"; shift ;;
    --tz) TZ_NAME="$2"; shift ;;
    --backup-time) BACKUP_TIME="$2"; shift ;;
    --retention) RETENTION="$2"; shift ;;
    --name) NAME="$2"; shift ;;
    --no-widget) ;;   # accepted for older scripts: the widget is no longer part of this release
    --no-launchers) LAUNCHERS=0 ;;
    --no-boot) BOOT=0 ;;
    --no-autocheck) AUTOCHECK=0 ;;
    -h|--help) sed -n '2,28p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
  shift
done

say()  { printf '%s\n' "$*"; }
step() { printf '\n\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }
ask() {   # ask VAR "Question" — keeps the current value on Enter
  local var="$1" q="$2" cur="${!1}" ans
  [ "$ASK" = 1 ] || return 0
  read -r -p "$q [$cur]: " ans || true
  [ -n "$ans" ] && printf -v "$var" '%s' "$ans"
  return 0
}
yesno() {   # yesno "Question" default(y/n)
  local q="$1" def="${2:-y}" ans
  [ "$ASK" = 1 ] || { [ "$def" = y ]; return; }
  read -r -p "$q [$( [ "$def" = y ] && echo Y/n || echo y/N )]: " ans || true
  ans="${ans:-$def}"; [[ "$ans" =~ ^[Yy] ]]
}
abspath() { local p="${1/#\~/$HOME}"; case "$p" in /*) ;; *) p="$PWD/$p" ;; esac; printf '%s' "${p%/}"; }
port_busy() { command -v ss >/dev/null 2>&1 && ss -ltnH 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$1\$"; }

say "Savings $version installer"
[ -d "$here/server" ] || die "The server files aren't next to this script (expected $here/server)."

# ---------- requirements ----------
step "Checking requirements"
command -v docker >/dev/null 2>&1 || die "Docker isn't installed. Install Docker Engine (https://docs.docker.com/engine/install/) and run this again."
docker compose version >/dev/null 2>&1 || die "The Docker Compose plugin is missing (the 'docker compose' command). Install it and run this again."
if ! docker info >/dev/null 2>&1; then
  die "Docker is installed but this user can't use it. Start Docker, or add yourself to the docker group:
       sudo usermod -aG docker \"\$USER\"   (then log out and in)"
fi
say "Docker $(docker version --format '{{.Server.Version}}' 2>/dev/null) with Compose $(docker compose version --short 2>/dev/null)"
command -v curl >/dev/null 2>&1 || warn "curl isn't installed: the final check that the app answers is skipped."

# ---------- settings ----------
step "Settings"
existing_env=""
if [ -f "$(abspath "$INSTALL_DIR")/.env" ]; then
  existing_env="$(abspath "$INSTALL_DIR")/.env"
fi
ask INSTALL_DIR "Install the server in"
INSTALL_DIR="$(abspath "$INSTALL_DIR")"
if [ -f "$INSTALL_DIR/.env" ]; then
  existing_env="$INSTALL_DIR/.env"
  say "Found an existing installation in $INSTALL_DIR: upgrading it, keeping its settings."
  val() { sed -n "s/^$1=//p" "$existing_env" | tail -1 | sed 's/^"\(.*\)"$/\1/'; }
  DATA_DIR="$(val DATA_DIR)"; PORT="$(val PORT || echo "$PORT")"; ADMIN_PORT="$(val ADMIN_PORT || echo "$ADMIN_PORT")"
  TZ_NAME="$(val TZ)"; BACKUP_TIME="$(val BACKUP_TIME)"; RETENTION="$(val BACKUP_RETENTION_DAYS)"
  NAME="$(val CONTAINER_NAME)"
  : "${PORT:=8090}" "${ADMIN_PORT:=8091}" "${TZ_NAME:=Europe/Athens}" "${BACKUP_TIME:=03:30}" "${RETENTION:=30}" "${NAME:=savings}"
  case "$DATA_DIR" in /*) ;; *) DATA_DIR="$INSTALL_DIR/$DATA_DIR" ;; esac
else
  ask DATA_DIR "Data folder (database and backups; an existing Savings data folder is used as it is)"
  ask PORT "Port for the app on your network"
  ask ADMIN_PORT "Port for the admin app (this PC only)"
  ask TZ_NAME "Timezone"
  ask BACKUP_TIME "Daily backup time (HH:MM)"
  ask RETENTION "Keep backups for how many days"
fi
DATA_DIR="$(abspath "$DATA_DIR")"

safe_path() { [[ "$1" != *[\"\$\`\|\\]* && "$1" != *$'\n'* ]]; }
safe_path "$INSTALL_DIR" || die "The install folder can't contain \" \$ \` | \\ or line breaks."
safe_path "$DATA_DIR" || die "The data folder can't contain \" \$ \` | \\ or line breaks."
[[ "$TZ_NAME" =~ ^[A-Za-z0-9_+/-]+$ ]] || die "Timezone looks wrong: '$TZ_NAME' (e.g. Europe/Berlin)."
[[ "$NAME" =~ ^[a-z0-9][a-z0-9_.-]*$ ]] || die "Container name may use lowercase letters, digits, . _ - (got '$NAME')."
[[ "$PORT" =~ ^[0-9]+$ && "$PORT" -ge 1 && "$PORT" -le 65535 ]] || die "Port must be a number from 1 to 65535 (got '$PORT')."
[[ "$ADMIN_PORT" =~ ^[0-9]+$ && "$ADMIN_PORT" -ge 1 && "$ADMIN_PORT" -le 65535 ]] || die "Admin port must be a number from 1 to 65535."
[ "$PORT" != "$ADMIN_PORT" ] || die "The app and the admin app need different ports."
[[ "$BACKUP_TIME" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]] || die "Backup time must look like 03:30 (got '$BACKUP_TIME')."
[[ "$RETENTION" =~ ^[0-9]+$ && "$RETENTION" -ge 1 ]] || die "Backup retention must be a whole number of days."
[ -e "/usr/share/zoneinfo/$TZ_NAME" ] || warn "Timezone '$TZ_NAME' isn't known on this PC; the app falls back to Europe/Athens if it doesn't know it either."
case "$DATA_DIR/" in "$INSTALL_DIR/"*) die "Keep the data folder outside the install folder, so upgrades never touch it.";; esac

running_here=""
docker ps --format '{{.Names}}' | grep -qx "$NAME" && running_here=1
if [ -z "$running_here" ]; then
  port_busy "$PORT" && die "Port $PORT is already in use. Pick another with --port."
  port_busy "$ADMIN_PORT" && die "Port $ADMIN_PORT is already in use. Pick another with --admin-port."
fi

if [ -f "$DATA_DIR/db/spending.db" ]; then
  data_note="existing Savings data found: it will be used as it is (and upgraded if needed)"
elif [ -d "$DATA_DIR" ] && [ -n "$(ls -A "$DATA_DIR" 2>/dev/null)" ]; then
  data_note="folder exists but has no Savings database: a new one is created inside it"
else
  data_note="new, empty"
fi

say ""
say "  Server files : $INSTALL_DIR"
say "  Data folder  : $DATA_DIR ($data_note)"
say "  App          : port $PORT (your network)      Admin: port $ADMIN_PORT (this PC only)"
say "  Timezone     : $TZ_NAME      Backups: daily at $BACKUP_TIME, kept $RETENTION days"
say "  Container    : $NAME"
yesno "Go ahead?" y || { say "Cancelled. Nothing was changed."; exit 0; }

# ---------- files ----------
step "Installing the server files"
new_data=0; [ -d "$DATA_DIR" ] || new_data=1
mkdir -p "$INSTALL_DIR" "$DATA_DIR"
[ "$new_data" = 1 ] && chmod 700 "$DATA_DIR"          # your finances: readable by you only
# copy everything except a .env that's already there (your settings) and old caches
( cd "$here/server" && tar --exclude='./.env' --exclude='__pycache__' -cf - . ) | ( cd "$INSTALL_DIR" && tar -xf - )
cp "$here/uninstall.sh" "$INSTALL_DIR/uninstall.sh" 2>/dev/null || true
chmod +x "$INSTALL_DIR"/*.sh "$INSTALL_DIR"/scripts/*.sh 2>/dev/null || true

if [ -z "$existing_env" ]; then
  q() { printf '"%s"' "$1"; }
  sed -e "s|^DATA_DIR=.*|DATA_DIR=$(q "$DATA_DIR")|" \
      -e "s|^PORT=.*|PORT=$PORT|" \
      -e "s|^ADMIN_PORT=.*|ADMIN_PORT=$ADMIN_PORT|" \
      -e "s|^TZ=.*|TZ=$TZ_NAME|" \
      -e "s|^BACKUP_TIME=.*|BACKUP_TIME=$BACKUP_TIME|" \
      -e "s|^BACKUP_RETENTION_DAYS=.*|BACKUP_RETENTION_DAYS=$RETENTION|" \
      -e "s|^PUID=.*|PUID=$(id -u)|" \
      -e "s|^PGID=.*|PGID=$(id -g)|" \
      -e "s|^CONTAINER_NAME=.*|CONTAINER_NAME=$NAME|" \
      -e "s|^COMPOSE_PROJECT_NAME=.*|COMPOSE_PROJECT_NAME=$NAME|" \
      -e "s|^IMAGE=.*|IMAGE=$NAME:$version|" \
      "$INSTALL_DIR/.env.example" > "$INSTALL_DIR/.env"
  chmod 600 "$INSTALL_DIR/.env"
  say "Settings written to $INSTALL_DIR/.env"
else
  say "Kept your settings in $INSTALL_DIR/.env"
fi

# ---------- start ----------
step "Building and starting the server (the first build downloads Python and Chart.js; it can take a few minutes)"
( cd "$INSTALL_DIR" && docker compose up -d --build --remove-orphans )

if command -v curl >/dev/null 2>&1; then
  printf 'Waiting for the app to answer'
  ok=""
  for _ in $(seq 1 60); do
    if curl -fs -o /dev/null "http://localhost:$PORT/login" 2>/dev/null; then ok=1; break; fi
    printf '.'; sleep 1
  done
  echo
  [ -n "$ok" ] || die "The app didn't answer on port $PORT. See: docker logs $NAME"
  say "The app is up."
fi

# ---------- start on boot ----------
if [ "$BOOT" = 1 ]; then
  step "Start on boot"
  say "The container restarts by itself whenever Docker runs (restart: unless-stopped)."
  if command -v systemctl >/dev/null 2>&1; then
    if [ "$(systemctl is-enabled docker 2>/dev/null || true)" = "enabled" ]; then
      say "Docker starts at boot: nothing to do."
    else
      warn "Docker isn't set to start at boot."
      if yesno "Enable it now? (runs: sudo systemctl enable docker)" y && [ "$ASK" = 1 ]; then
        sudo systemctl enable docker && say "Done: Docker (and so Savings) starts at boot."
      else
        say "To do it later: sudo systemctl enable docker"
      fi
    fi
  fi
fi

# ---------- the "savings" command ----------
step "The savings command"
bin="$HOME/.local/bin"
mkdir -p "$bin"
if [ -e "$bin/savings" ] && [ "$(readlink -f "$bin/savings")" != "$INSTALL_DIR/savings" ]; then
  if [ -L "$bin/savings" ] && yesno "$bin/savings points to another Savings install ($(readlink -f "$bin/savings")). Point it here instead?" y; then
    ln -sfn "$INSTALL_DIR/savings" "$bin/savings"
  else
    warn "Left $bin/savings alone; use $INSTALL_DIR/savings directly."
  fi
else
  ln -sfn "$INSTALL_DIR/savings" "$bin/savings"
fi
case ":$PATH:" in
  *":$bin:"*) say "Manage Savings with: savings help   (status, check, backup, restore, update, logs…)" ;;
  *) say "Manage Savings with: $bin/savings help   (add $bin to your PATH to type just 'savings')" ;;
esac

if [ "$AUTOCHECK" = 1 ] && command -v systemctl >/dev/null 2>&1; then
  if yesno "Run a daily checkup (desktop notification only if something's wrong)?" y; then
    "$INSTALL_DIR/savings" autocheck on || warn "Couldn't set up the daily checkup; later: savings autocheck on"
  fi
fi

# ---------- launchers ----------
if [ "$LAUNCHERS" = 1 ] && [ -x "$INSTALL_DIR/scripts/install-launchers.sh" ]; then
  step "App-menu launchers"
  "$INSTALL_DIR/scripts/install-launchers.sh"
fi

# ---------- done ----------
ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
step "Checkup"
"$INSTALL_DIR/savings" check || true
step "Savings $version is installed"
say "  This PC          : http://localhost:$PORT"
[ -n "$ip" ] && say "  Phones / others  : http://$ip:$PORT   (same Wi-Fi or VPN)"
say "  Admin (this PC)  : http://localhost:$ADMIN_PORT"
say ""
say "Next:"
say "  1. Open the admin app and create the admin login (first visit only)."
say "  2. Open the app, choose 'Request an account', then approve it in the admin app."
say "  3. On KDE Plasma, the panel widget is a separate download (savings-widget-X.Y.Z.tar.gz):"
say "     install it with its own ./install.sh, then connect it in Savings → Settings → KDE widget."
say ""
say "Everyday: savings status · savings check · savings backup · savings logs · savings help"
say "Upgrade: run the installer of a newer version. Uninstall: savings uninstall (keeps your data)."
