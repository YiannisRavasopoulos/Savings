#!/usr/bin/env bash
# Build the Savings widget release to give to friends: release/savings-widget-<version>.tar.gz (+ .sha256)
#
#   packaging/widget/make-release.sh             check, build the widget, scan, pack
#   packaging/widget/make-release.sh --verify    ...and then unpack it fresh and install, reinstall, (refuse to)
#                                 downgrade, force and remove it
#                                 in a throwaway home folder (this PC's Plasma isn't touched)
#
# Options:
#   --verify       also test the packed release with its own install.sh / uninstall.sh (needs kpackagetool6)
#   --no-build     use dist/savings-<version>.plasmoid as it is instead of rebuilding it
#   --strict       treat warnings as errors
#   -h, --help     this help
#
# What it checks
#   errors (stop the build): missing tools or files, a bad version in package/metadata.json, shell
#     scripts that don't parse, an invalid widget package (wrong type or id, missing QML or icon,
#     files that differ from package/), and anything personal in the release: words from
#     .release-denylist (a local list that's never shipped), widget tokens, Plasma configs, keys,
#     absolute home paths, developer-only files (this script, build-widget.sh, the README) or
#     mentions of them in INSTALL.md. With --verify: installing, upgrading or removing fails.
#   warnings (reported, build continues unless --strict): no .release-denylist, overwriting a
#     release with the same version, a widget package older than its source (--no-build).
# Exit codes: 0 built (maybe with warnings), 1 an error stopped it, 2 wrong usage.
set -uo pipefail
root="$(cd "$(dirname "$(readlink -f "$0")")/../../widget" && pwd)"   # the widget source
cd "$root"
outdir="$root/../release"         # where finished packages go (shared with the app, gitignored)
pk=../packaging/widget            # the installer that ships in the release
work="$root/tmp/release"          # scratch space, removed afterwards
ID="local.savings.widget"         # the id install.sh / uninstall.sh look for

# ---------- output ----------
if [ -t 1 ]; then R=$'\033[1;31m'; Y=$'\033[1;33m'; G=$'\033[1;32m'; B=$'\033[1m'; N=$'\033[0m'; else R= Y= G= B= N=; fi
errors=0; warnings=0
step()  { printf '\n%s==>%s %s\n' "$G" "$N" "$*"; }
ok()    { printf '  %s✓%s %s\n' "$G" "$N" "$*"; }
warn()  { printf '  %s! warning:%s %s\n' "$Y" "$N" "$*"; warnings=$((warnings + 1)); }
err()   { printf '  %s✗ error:%s %s\n' "$R" "$N" "$*"; errors=$((errors + 1)); }
detail(){ sed "s|$work/||; s|^|      |" | cut -c1-170; }
cleanup(){ rm -rf "$work"; rmdir "$root/tmp" 2>/dev/null; true; }
stop_if_errors() {
  if [ "$errors" -gt 0 ]; then
    printf '\n%sRelease NOT built:%s %d error(s), %d warning(s). Fix the errors above and run it again.\n' "$R" "$N" "$errors" "$warnings"
    cleanup; exit 1
  fi
}

# ---------- options ----------
verify=0; strict=0; build=1
while [ $# -gt 0 ]; do
  case "$1" in
    --verify) verify=1 ;;
    --strict) strict=1 ;;
    --no-build) build=0 ;;
    -h|--help) sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
  shift
done

printf '%sSavings widget release builder%s\n' "$B" "$N"

# ---------- 1. preflight ----------
step "Checking tools and project"
for t in python3 tar sha256sum grep sed find; do
  command -v "$t" >/dev/null 2>&1 && ok "$t" || err "$t is not installed"
done
if [ "$verify" = 1 ]; then
  command -v kpackagetool6 >/dev/null 2>&1 && ok "kpackagetool6" || err "--verify needs kpackagetool6 (KDE Plasma 6), which isn't installed"
fi
version="$(python3 -c 'import json; print(json.load(open("package/metadata.json"))["KPlugin"]["Version"])' 2>/dev/null)"
if [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then ok "version $version (package/metadata.json)"
else err "the version in package/metadata.json must look like 1.2.3 (got '${version:-missing}')"; fi
# what friends get: the .plasmoid, the installer and uninstaller, the install guide and the licence.
# Not shipped: package/ (it's inside the .plasmoid), the README (developer docs), the build scripts.
INSTALLER=($pk/install.sh $pk/uninstall.sh $pk/INSTALL.md LICENSE)
missing=0
for f in "${INSTALLER[@]}" package/metadata.json build-widget.sh; do [ -e "$f" ] || { err "missing: $f"; missing=1; }; done
[ "$missing" = 0 ] && ok "all release files present"
for f in $pk/install.sh $pk/uninstall.sh build-widget.sh; do
  [ -e "$f" ] && { bash -n "$f" 2>/dev/null || err "shell script doesn't parse: $f (run: bash -n $f)"; }
done
[ "$errors" = 0 ] && ok "shell scripts parse"
deny=.release-denylist; [ -f "$deny" ] || deny=../.release-denylist   # shared with the app, at the repo root
[ -f "$deny" ] && ok ".release-denylist found" || warn "no .release-denylist: personal words can't be checked (only the generic checks run)"
stop_if_errors

# ---------- 2. widget ----------
step "Widget package"
widget="$root/dist/savings-$version.plasmoid"
if [ "$build" = 1 ]; then
  if out="$(./build-widget.sh 2>&1)"; then ok "built: $(printf '%s' "$out" | sed -n 's/^Built //p')"
  else err "the widget didn't build:"; printf '%s\n' "$out" | sed 's/^/      /'; fi
elif [ -f "$widget" ] && [ -n "$(find package -newer "$widget" -type f 2>/dev/null | head -1)" ]; then
  warn "$(basename "$widget") is older than package/; drop --no-build to rebuild it"
fi
[ -f "$widget" ] || { err "no widget package: dist/$(basename "$widget")"; stop_if_errors; }
if res="$(python3 - "$widget" "$ID" package 2>&1 <<'PY'
import json, pathlib, re, sys, zipfile
path, want_id, src = sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3])
z = zipfile.ZipFile(path); names = set(z.namelist())
problems = []
if z.testzip() is not None: problems.append("the zip is damaged")
m = json.loads(z.read("metadata.json")); k = m.get("KPlugin", {})
if m.get("KPackageStructure") != "Plasma/Applet": problems.append("KPackageStructure isn't Plasma/Applet")
if k.get("Id") != want_id: problems.append(f"id is {k.get('Id')!r}, the installer expects {want_id!r}")
if not k.get("Name"): problems.append("no Name")
if "contents/ui/main.qml" not in names: problems.append("no contents/ui/main.qml")
icon = k.get("Icon", "")
if icon.endswith(".png") and f"contents/icons/{icon}" not in names: problems.append(f"icon contents/icons/{icon} missing")
cfg = z.read("contents/config/config.qml").decode() if "contents/config/config.qml" in names else ""
for page in re.findall(r'source:\s*"([^"]+\.qml)"', cfg):
    if f"contents/ui/{page}" not in names: problems.append(f"settings page {page} missing")
srcfiles = {p.relative_to(src).as_posix() for p in src.rglob("*") if p.is_file()}
if names != srcfiles: problems.append("files differ from package/: " + ", ".join(sorted(names ^ srcfiles))[:150])
else:
    for n in names:
        if z.read(n) != (src / n).read_bytes(): problems.append(f"{n} differs from package/ (rebuild it)")
if problems: print("; ".join(problems)); sys.exit(1)
print(f"{len(names)} files, {sum(n.endswith('.qml') for n in names)} QML")
PY
)"; then ok "$(basename "$widget") is a valid Plasma widget ($res)"
else err "$(basename "$widget") isn't a valid widget package: $res"; fi
stop_if_errors

# A released widget version never changes; and every release has its CHANGELOG.md entry
# (shared with the app, at the repo root; the app and the widget are released separately).
if res="$(python3 ../packaging/release-checks.py widget "$widget" ../release 2>&1)"; then
  [ "$res" = same ] && ok "matches the widget $version already released" || ok "widget $version is a new version"
else err "$res"; fi
res="$(python3 ../packaging/release-checks.py changelog ../CHANGELOG.md widget "$version" 2>&1)"; rc=$?
case $rc in 0) ok "CHANGELOG.md has a section for widget $version" ;; 3) warn "$res" ;; *) err "$res" ;; esac
stop_if_errors

# ---------- 3. stage ----------
step "Collecting the files"
name="savings-widget-$version"
stage="$work/$name"
rm -rf "$work"; mkdir -p "$stage" "$outdir"
cp "$pk/install.sh" "$pk/uninstall.sh" "$pk/INSTALL.md" LICENSE "$widget" "$stage/" \
  && chmod 755 "$stage"/*.sh && chmod 644 "$stage"/INSTALL.md "$stage"/LICENSE "$stage"/*.plasmoid \
  || err "copying the files failed"
stop_if_errors
ok "$(find "$stage" -type f | wc -l) files ($(du -sh "$stage" | cut -f1) unpacked)"

# ---------- 4. scan ----------
step "Scanning for personal data"
peek="$work/peek"; mkdir -p "$peek"
python3 -c "import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$stage/$(basename "$widget")" "$peek"
scan() {   # scan "label" command...
  local label="$1"; shift
  local hits; hits="$("$@" 2>/dev/null || true)"
  if [ -n "$hits" ]; then err "$label:"; printf '%s\n' "$hits" | detail; else ok "no $label"; fi
}
scan "files that must not ship (Plasma configs, keys, .env, databases)" \
  find "$stage" "$peek" \( -name '*appletsrc' -o -name 'plasmawindowedrc' -o -name '*.key' -o -name '.env' \
       -o -name '*.db' -o -name '*.sqlite' -o -name '.release-denylist' \) -print
if [ -f "$deny" ]; then
  grep -v '^\s*#' "$deny" | sed '/^\s*$/d' > "$work/patterns"
  scan "personal words (from .release-denylist)" grep -rIinE -f "$work/patterns" "$stage" "$peek"
fi
scan "widget tokens" grep -rIEn 'svw_[A-Za-z0-9_-]{30,}' "$stage" "$peek"
scan "absolute home paths" grep -rIn '/home/[a-z]' "$stage" "$peek"
scan "developer-only files" find "$stage" \( -name 'make-release.sh' -o -name 'release-checks.py' -o -name 'build-widget.sh' -o -name 'README.md' \
       -o -name 'package' -o -name 'dist' -o -name '.gitignore' \) -print
scan "developer-only mentions in INSTALL.md" grep -In -E 'make-release|build-widget|savings-docker|~/savings|dist/|package/' "$stage/INSTALL.md"
rm -rf "$peek" "$work/patterns"
stop_if_errors

# ---------- 5. pack ----------
step "Packing"
out="$outdir/$name.tar.gz"
[ -f "$out" ] && warn "release/$name.tar.gz already exists and is replaced (bump the version in package/metadata.json for a new release)"
if [ "$strict" = 1 ] && [ "$warnings" -gt 0 ]; then err "--strict: $warnings warning(s) count as errors"; stop_if_errors; fi
# neutral metadata: no owner names (tar would otherwise record this PC's username), sorted entries
tar --owner=0 --group=0 --numeric-owner --sort=name -czf "$out" -C "$work" "$name" \
  && ( cd "$outdir" && sha256sum "$name.tar.gz" > "$name.tar.gz.sha256" ) || err "packing failed"
owners="$(tar -tvzf "$out" | awk '$2 != "0/0" {print "      " $2 "  " $6}' | head -5)"
[ -z "$owners" ] || { err "the archive records file owners:"; printf '%s\n' "$owners"; }
stop_if_errors
ok "archive metadata: no owner names"
ok "release/$name.tar.gz ($(du -h "$out" | cut -f1))"
ok "sha256 $(cut -c1-16 "$out.sha256")…"

# ---------- 6. verify ----------
tests="not run (add --verify)"
if [ "$verify" = 1 ]; then
  step "Verifying the packed release (in a throwaway home folder)"
  check="$work/check"; mkdir -p "$check/home"
  tar -xzf "$out" -C "$check"
  # a separate home: kpackagetool6 installs into $XDG_DATA_HOME, so this PC's widgets aren't touched
  sandbox() { env HOME="$check/home" XDG_DATA_HOME="$check/home/.local/share" XDG_CONFIG_HOME="$check/home/.config" \
                  XDG_CACHE_HOME="$check/home/.cache" "$@"; }
  installed() { sandbox kpackagetool6 -t Plasma/Applet -l 2>/dev/null | grep -qx "$ID"; }
  meta="$check/home/.local/share/plasma/plasmoids/$ID/metadata.json"
  if (cd "$check/$name" && sandbox ./install.sh --yes >"$check/log" 2>&1) && installed && grep -q "\"$version\"" "$meta" 2>/dev/null; then
    ok "install.sh installs it (version $version)"
  else err "install.sh failed:"; sed 's/^/      /' "$check/log"; fi
  if (cd "$check/$name" && sandbox ./install.sh --yes >"$check/log" 2>&1) && grep -q "already installed" "$check/log" && installed; then
    ok "running it again with the same version changes nothing"
  else err "install.sh over the same version misbehaved:"; sed 's/^/      /' "$check/log"; fi
  # pretend a newer widget is installed: an older package must leave it alone, unless --force
  sed -i 's/"Version": *"[^"]*"/"Version": "99.0.0"/' "$meta"
  if (cd "$check/$name" && sandbox ./install.sh --yes >"$check/log" 2>&1) && grep -q "is newer than this one" "$check/log" \
     && grep -q '"99.0.0"' "$meta"; then
    ok "never replaces a newer installed widget with an older one"
  else err "install.sh downgraded a newer widget:"; sed 's/^/      /' "$check/log"; fi
  if (cd "$check/$name" && sandbox ./install.sh --yes --force >"$check/log" 2>&1) && grep -q upgraded "$check/log" \
     && grep -q "\"$version\"" "$meta"; then
    ok "install.sh --force installs it anyway (and upgrading works)"
  else err "install.sh --force failed:"; sed 's/^/      /' "$check/log"; fi
  if (cd "$check/$name" && sandbox ./uninstall.sh --yes >"$check/log" 2>&1) && ! installed && [ ! -e "$meta" ]; then
    ok "uninstall.sh removes it"
  else err "uninstall.sh failed:"; sed 's/^/      /' "$check/log"; fi
  if [ "$errors" -gt 0 ]; then
    tests="FAILED"; rm -f "$out" "$out.sha256"
    printf '  (the broken release was removed from release/)\n'
    stop_if_errors
  fi
  tests="install, same-version, no-downgrade, --force, remove passed"
fi
cleanup

# ---------- summary ----------
printf '\n%sRelease built:%s release/%s.tar.gz\n' "$G" "$N" "$name"
printf '  widget %s · verify: %s · %d warning(s)\n' "$version" "$tests" "$warnings"
printf '  send it with its checksum file; the friend runs: tar xf %s.tar.gz && cd %s && ./install.sh\n' "$name" "$name"
exit 0
