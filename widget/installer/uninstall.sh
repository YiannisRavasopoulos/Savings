#!/usr/bin/env bash
# Savings widget uninstaller: removes the Savings panel widget from this user's Plasma.
#
#   ./uninstall.sh          ask first
#   ./uninstall.sh --yes    don't ask
#
# Remove the widget from your panels first. The Savings server and its data aren't touched.
set -euo pipefail
ID="local.savings.widget"

ASK=1
for a in "$@"; do
  case "$a" in
    --yes|-y) ASK=0 ;;
    -h|--help) sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $a (see --help)" >&2; exit 2 ;;
  esac
done

command -v kpackagetool6 >/dev/null 2>&1 || { echo "kpackagetool6 not found: nothing to remove (this needs KDE Plasma 6)."; exit 0; }
if ! kpackagetool6 -t Plasma/Applet -l 2>/dev/null | grep -qx "$ID"; then
  echo "The Savings widget isn't installed for this user. Nothing to do."; exit 0
fi
if [ "$ASK" = 1 ]; then
  read -r -p "Remove the Savings widget? (remove it from your panels first) [y/N]: " ans || true
  [[ "${ans:-n}" =~ ^[Yy] ]] || { echo "Nothing changed."; exit 0; }
fi
kpackagetool6 -t Plasma/Applet -r "$ID" >/dev/null && echo "Savings widget removed."
echo "Its token still works until you revoke it in Savings → Settings → KDE widget."
