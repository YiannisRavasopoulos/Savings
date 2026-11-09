#!/usr/bin/env bash
# Install the "Savings" and "Savings Admin" app-menu launchers for this folder, wherever it is.
#   scripts/install-launchers.sh            install / update them
#   scripts/install-launchers.sh --remove   remove them
set -euo pipefail
dir="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
if [ "${1:-}" = "--remove" ]; then
  # only launchers that belong to THIS folder (another Savings install may own them)
  n=0
  for f in savings savings-admin; do
    if [ -f "$apps/$f.desktop" ] && grep -q "^Exec=$dir/" "$apps/$f.desktop"; then
      rm -f "$apps/$f.desktop"; n=$((n + 1))
    fi
  done
  [ "$n" -gt 0 ] && echo "Launchers removed." || echo "No launchers for this folder to remove."
  exit 0
fi
mkdir -p "$apps"
for f in savings savings-admin; do
  sed "s|@DIR@|$dir|g" "$dir/desktop/$f.desktop" > "$apps/$f.desktop"
  chmod 644 "$apps/$f.desktop"
done
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$apps" >/dev/null 2>&1 || true
echo "Launchers installed in $apps (Savings, Savings Admin)."
