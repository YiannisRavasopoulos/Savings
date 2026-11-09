#!/usr/bin/env bash
# Remove Savings from this PC: stops and removes the server container and image, the app-menu
# launchers. Your DATA FOLDER IS KEPT unless you ask for
# --delete-data (and then type its name to confirm).
#
#   ./uninstall.sh                 remove the program, keep the data
#   ./uninstall.sh --delete-data   also delete the data folder (database and all backups)
set -euo pipefail
dir="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
delete_data=0
[ "${1:-}" = "--delete-data" ] && delete_data=1

[ -f "$dir/docker-compose.yml" ] || { echo "Run this from the Savings server folder (it isn't next to docker-compose.yml)." >&2; exit 1; }
val() { sed -n "s/^$1=//p" "$dir/.env" 2>/dev/null | tail -1 | sed 's/^"\(.*\)"$/\1/'; }
data="$(val DATA_DIR)"
case "$data" in "") data="(unknown)";; /*) ;; *) data="$dir/$data";; esac
image="$(val IMAGE)"

echo "This removes Savings from this PC:"
echo "  - the server container and image (in $dir)"
echo "  - the app-menu launchers, the savings command and the daily checkup"
if [ "$delete_data" = 1 ]; then
  echo "  - AND the data folder $data, with every expense and every backup in it"
else
  echo "Your data folder stays: $data"
fi
read -r -p "Continue? [y/N]: " ans || true
[[ "${ans:-n}" =~ ^[Yy] ]] || { echo "Cancelled."; exit 0; }

( cd "$dir" && docker compose down --rmi all --remove-orphans ) || true
[ -n "$image" ] && docker image rm "$image" >/dev/null 2>&1 || true
[ -x "$dir/scripts/install-launchers.sh" ] && "$dir/scripts/install-launchers.sh" --remove || true
[ -x "$dir/savings" ] && "$dir/savings" autocheck off >/dev/null 2>&1 || true          # the daily checkup timer
link="$HOME/.local/bin/savings"
[ -L "$link" ] && [ "$(readlink -f "$link")" = "$dir/savings" ] && rm -f "$link" && echo "Removed the savings command."

# The KDE widget is a separate release: it's removed with its own uninstall.sh.

if [ "$delete_data" = 1 ]; then
  # never delete something that isn't clearly a Savings data folder
  real="$(readlink -f "$data" 2>/dev/null || echo "$data")"
  if [ ! -d "$real" ] || [ "$real" = "/" ] || [ "$real" = "$(readlink -f "$HOME")" ] || [ ! -f "$real/db/spending.db" ]; then
    echo "Not deleting '$data': it isn't a Savings data folder (no db/spending.db). Delete it yourself if you're sure."
    delete_data=0
  fi
fi
if [ "$delete_data" = 1 ] && [ -d "$data" ]; then
  echo
  echo "To delete the data folder for good, type its name ($(basename "$data")):"
  read -r confirm || true
  if [ "$confirm" = "$(basename "$data")" ]; then
    rm -rf -- "$data" && echo "Data folder deleted."
  else
    echo "Name didn't match: the data folder was kept."
  fi
fi

echo
echo "Savings is removed. The server files are still in $dir; delete that folder to finish."
