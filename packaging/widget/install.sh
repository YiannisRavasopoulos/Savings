#!/usr/bin/env bash
# Savings widget installer: installs (or upgrades) the Savings panel widget for KDE Plasma 6.
#
#   ./install.sh          install it, or upgrade an installed one
#   ./install.sh --yes    the same, without asking
#   ./install.sh --force  also when the installed widget is newer (a downgrade)
#
# It installs for your user only (no sudo). It doesn't touch the Savings server.
set -euo pipefail
here="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
ID="local.savings.widget"

ASK=1; FORCE=0
for a in "$@"; do
  case "$a" in
    --yes|-y) ASK=0 ;;
    --force) FORCE=1 ;;
    -h|--help) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $a (see --help)" >&2; exit 2 ;;
  esac
done

say()  { printf '%s\n' "$*"; }
die()  { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }

plasmoid="$(ls "$here"/savings-*.plasmoid 2>/dev/null | sort -V | tail -1 || true)"
if [ -z "$plasmoid" ]; then
  # run from a git clone (packaging/widget/ in the source): that's the source, not a release
  [ -f "$here/../../widget/package/metadata.json" ] && die "This is the installer's source in a copy of the code, not a release.
  To install the widget: download savings-widget-X.Y.Z.tar.gz from the project's Releases page,
  unpack it and run its install.sh. To work on the widget: see widget/README.md."
  die "no savings-*.plasmoid next to this script"
fi
version="$(basename "$plasmoid" .plasmoid | sed 's/^savings-//')"
command -v kpackagetool6 >/dev/null 2>&1 \
  || die "kpackagetool6 not found: this needs KDE Plasma 6. You can also install $plasmoid from
       Add or Manage Widgets… → Get New → Install Widget From Local File…"

# Version of the widget already installed for this user ("" if none). Read from its metadata.json,
# so an older package never silently replaces a newer one.
installed_widget_version() {
  local dir
  dir="$(kpackagetool6 -t Plasma/Applet -s local.savings.widget 2>/dev/null | sed -n 's/^ *Path *: *//p')"
  [ -n "$dir" ] && [ -f "$dir/metadata.json" ] || return 0
  grep -o '"Version": *"[^"]*"' "$dir/metadata.json" | head -1 | sed 's/.*"\([^"]*\)"$/\1/'
}
# newer A B: true if version A is newer than version B
newer() { [ "$1" != "$2" ] && [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | tail -1)" = "$1" ]; }

if kpackagetool6 -t Plasma/Applet -l 2>/dev/null | grep -qx "$ID"; then action=upgrade; else action=install; fi
current="$(installed_widget_version)"
if [ "$action" = upgrade ] && [ -n "$current" ]; then
  if [ "$current" = "$version" ] && [ "$FORCE" = 0 ]; then
    say "The Savings widget $version is already installed. Nothing changed."; exit 0
  fi
  if newer "$current" "$version" && [ "$FORCE" = 0 ]; then
    say "The installed Savings widget ($current) is newer than this one ($version). Nothing changed."
    say "To install the older one anyway: ./install.sh --force"; exit 0
  fi
fi
if [ "$ASK" = 1 ]; then
  read -r -p "${action^} the Savings widget $version? [Y/n]: " ans || true
  [[ "${ans:-y}" =~ ^[Yy] ]] || { say "Nothing changed."; exit 0; }
fi

if [ "$action" = upgrade ]; then
  kpackagetool6 -t Plasma/Applet -u "$plasmoid" >/dev/null || die "the upgrade failed"
  say "Savings widget upgraded to $version."
  say "Restart Plasma once so the new version loads: plasmashell --replace & disown"
  say "(or log out and in). Your settings are kept."
else
  kpackagetool6 -t Plasma/Applet -i "$plasmoid" >/dev/null || die "the install failed"
  say "Savings widget $version installed."
  say ""
  say "Next:"
  say "  1. Right-click the panel → Add or Manage Widgets… → drag 'Savings' to the panel."
  say "  2. In Savings (in your browser) → Settings → KDE widget, create a token for this PC."
  say "  3. Right-click the widget → Configure Savings… and enter the server address"
  say "     (e.g. http://192.168.0.10:8090) and the token."
fi
