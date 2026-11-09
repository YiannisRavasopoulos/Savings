#!/usr/bin/env bash
# Package the Savings Plasma widget (a client-side package; the server isn't involved).
#   ./build-widget.sh             build dist/savings-<version>.plasmoid
#   ./build-widget.sh --install   also install / upgrade it on this PC (kpackagetool6)
# Needs: python3 (standard library) to zip; kpackagetool6 (part of Plasma 6) to install.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

install=0
for a in "$@"; do
  case "$a" in
    --install) install=1 ;;
    -h|--help) sed -n '2,5p' "$0"; exit 0 ;;
    *) echo "Unknown option: $a" >&2; exit 2 ;;
  esac
done

version="$(python3 -c 'import json; print(json.load(open("package/metadata.json"))["KPlugin"]["Version"])')"
mkdir -p dist
out="dist/savings-${version}.plasmoid"
python3 - "$out" <<'PY'
import sys, zipfile, pathlib
out = pathlib.Path(sys.argv[1]); root = pathlib.Path("package")
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for p in sorted(root.rglob("*")):
        if p.is_file():
            z.write(p, p.relative_to(root).as_posix())
PY
echo "Built $out"

if [ "$install" = 1 ]; then
  if kpackagetool6 -t Plasma/Applet -l 2>/dev/null | grep -qx "local.savings.widget"; then
    kpackagetool6 -t Plasma/Applet -u "$out"
  else
    kpackagetool6 -t Plasma/Applet -i "$out"
  fi
  echo "Installed on this PC. Add it: right-click the panel → Add or Manage Widgets… → Savings."
  echo "(An already-running widget picks up the new version after: plasmashell --replace & disown, or logging out and in.)"
fi
