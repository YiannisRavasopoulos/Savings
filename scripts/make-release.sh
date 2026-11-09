#!/usr/bin/env bash
# Build the Savings release bundle to give to friends: release/savings-<version>.tar.gz (+ .sha256)
#
#   scripts/make-release.sh             check, scan, pack
#   scripts/make-release.sh --verify    ...and then unpack it fresh, build it and run all the tests
#
# Options:
#   --verify            also test the packed bundle: build it fresh and run this project's tests
#                       against it (the tests themselves aren't shipped; needs Docker; ~1 minute)
#   --strict            treat warnings as errors
#   -h, --help          this help
#
# What it checks
#   errors (stop the build): missing tools or files, a bad VERSION, shell scripts that don't parse,
#     no CHANGELOG.md section for this version, and anything personal in the bundle: words from .release-denylist
#     (a local list that's never shipped), widget tokens, databases, .env, backups, keys, Plasma
#     configs, absolute home paths, developer-only files (tests, this script, the splash preview,
#     the dev rebuild script) or mentions of them in the shipped docs. With --verify: the bundle
#     doesn't build or a test fails.
#   warnings (reported, build continues unless --strict): no .release-denylist, overwriting a
#     release with the same version, a leftover "## Unreleased" section in CHANGELOG.md.
# The KDE widget is NOT part of this release: it has its own, widget/make-release.sh.
# Exit codes: 0 built (maybe with warnings), 1 an error stopped it, 2 wrong usage.
set -uo pipefail
root="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
cd "$root"
outdir="$root/release"            # where finished packages go

# ---------- output ----------
if [ -t 1 ]; then R=$'\033[1;31m'; Y=$'\033[1;33m'; G=$'\033[1;32m'; B=$'\033[1m'; N=$'\033[0m'; else R= Y= G= B= N=; fi
errors=0; warnings=0
step()  { printf '\n%s==>%s %s\n' "$G" "$N" "$*"; }
ok()    { printf '  %s✓%s %s\n' "$G" "$N" "$*"; }
warn()  { printf '  %s! warning:%s %s\n' "$Y" "$N" "$*"; warnings=$((warnings + 1)); }
err()   { printf '  %s✗ error:%s %s\n' "$R" "$N" "$*"; errors=$((errors + 1)); }
detail(){ sed "s|$work/||; s|^|      |" | cut -c1-170; }
stop_if_errors() {
  if [ "$errors" -gt 0 ]; then
    printf '\n%sRelease NOT built:%s %d error(s), %d warning(s). Fix the errors above and run it again.\n' "$R" "$N" "$errors" "$warnings"
    rm -rf "$work"; exit 1
  fi
}

# ---------- options ----------
verify=0; strict=0
while [ $# -gt 0 ]; do
  case "$1" in
    --verify) verify=1 ;;
    --strict) strict=1 ;;
    -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
  shift
done
work="$root/tmp/release"

printf '%sSavings release builder%s\n' "$B" "$N"

# ---------- 1. preflight ----------
step "Checking tools and project"
for t in python3 tar sha256sum grep sed find; do
  command -v "$t" >/dev/null 2>&1 && ok "$t" || err "$t is not installed"
done
if [ "$verify" = 1 ]; then
  if ! command -v docker >/dev/null 2>&1; then err "--verify needs Docker, which isn't installed"
  elif ! docker info >/dev/null 2>&1; then err "--verify needs Docker, but this user can't reach the Docker daemon"
  else ok "docker"; fi
fi
version="$(cat VERSION 2>/dev/null | tr -d '[:space:]')"
if [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then ok "version $version"; else err "VERSION must look like 1.2.3 (got '${version:-missing}')"; fi
# what friends get: the server (code, database migrations, Docker config), the admin app, launchers,
# backup/restore tools. Not shipped: tests, the release builder, the splash preview tool, the dev
# rebuild script; the README is trimmed of its release and development sections.
ALLOW=(app migrations desktop scripts/install-launchers.sh scripts/restore.sh Dockerfile docker-compose.yml
       .dockerignore .env.example requirements.txt README.md CHANGELOG.md SECURITY.md LICENSE VERSION docs open-savings-client.sh open-savings-admin.sh
       savings)
INSTALLER=(installer/install.sh installer/uninstall.sh installer/INSTALL.md LICENSE)
missing=0
for f in "${ALLOW[@]}" "${INSTALLER[@]}"; do [ -e "$f" ] || { err "missing: $f"; missing=1; }; done
[ "$missing" = 0 ] && ok "all release files present"
for f in installer/install.sh installer/uninstall.sh scripts/install-launchers.sh scripts/restore.sh open-savings-*.sh savings; do
  bash -n "$f" 2>/dev/null || err "shell script doesn't parse: $f (run: bash -n $f)"
done
[ "$errors" = 0 ] && ok "shell scripts parse"
[ -f .release-denylist ] && ok ".release-denylist found" || warn "no .release-denylist: personal words can't be checked (only the generic checks run)"
stop_if_errors

# ---------- 2. changelog ----------
step "Changelog"
res="$(python3 scripts/release-checks.py changelog CHANGELOG.md app "$version" 2>&1)"; rc=$?
case $rc in 0) ok "CHANGELOG.md has a section for Savings $version" ;; 3) warn "$res" ;; *) err "$res" ;; esac
stop_if_errors

# ---------- 3. stage ----------
step "Collecting the files"
name="savings-$version"
stage="$work/$name"
rm -rf "$work"; mkdir -p "$stage/server" "$outdir"
tar -cf - --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache' \
    --exclude='docs/development.md' "${ALLOW[@]}" \
  | tar -xf - -C "$stage/server" || err "copying the server files failed"
# the docs for friends: without the developer pages (not shipped) or the dev-only tools
python3 - "$stage/server" <<'PY' || err "trimming the docs failed"
import pathlib, re, sys
root = pathlib.Path(sys.argv[1])
def drop_section(s, title):            # a "## title" section, up to the next "## "
    return re.sub(rf"\n## {re.escape(title)}\n.*?(?=\n## |\Z)", "\n", s, flags=re.S)
p = root / "README.md"; s = p.read_text()
for t in ("Want to contribute?", "Development"):
    s = drop_section(s, t)
p.write_text(s)
p = root / "docs" / "README.md"; s = p.read_text()
p.write_text(drop_section(s, "For developers"))
for p in (root / "docs").glob("*.md"):
    s = p.read_text()
    s = re.sub(r"  - \*\*Trying them on the PC:\*\*.*?(?=\n- \*\*|\n  - \*\*|\n\n)", "", s, flags=re.S)
    s = s.replace("   ./start-savings-server.sh        # = docker compose up -d --build, then opens the browser",
                  "   docker compose up -d --build")
    s = s.replace("`start-savings-server.sh` is for after code changes: it rebuilds the image, then opens the page.\n\n", "")
    s = s.replace("`./start-savings-server.sh`", "`docker compose up -d --build`")
    s = re.sub(r"It's a \*\*separate client-side\s+project\*\* in `widget/`, with its own README, packaging and releases\.",
               "It's released **separately** (`savings-widget-X.Y.Z.tar.gz`, with its own installer), so it can be\nupdated without a new Savings release.", s)
    p.write_text(s)
PY
cp installer/install.sh installer/uninstall.sh installer/INSTALL.md LICENSE "$stage/" \
  || err "copying the installer failed"
chmod +x "$stage"/*.sh "$stage"/server/*.sh "$stage"/server/scripts/*.sh "$stage"/server/savings 2>/dev/null
stop_if_errors
ok "$(find "$stage" -type f | wc -l) files ($(du -sh "$stage" | cut -f1) unpacked)"

# ---------- 4. scan ----------
step "Scanning for personal data"
peek="$work/peek"; mkdir -p "$peek"     # (kept empty: nothing packed inside the bundle to look into)
scan() {   # scan "label" command...
  local label="$1"; shift
  local hits; hits="$("$@" 2>/dev/null || true)"
  if [ -n "$hits" ]; then err "$label:"; printf '%s\n' "$hits" | detail; else ok "no $label"; fi
}
scan "files that must not ship (databases, .env, backups, keys, Plasma configs)" \
  find "$stage" "$peek" \( -name '.env' -o -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite-*' -o -path '*/backups/*' \
       -o -name '*.key' -o -name '*appletsrc' -o -name 'plasmawindowedrc' -o -name '.release-denylist' \) -print
if [ -f .release-denylist ]; then
  grep -v '^\s*#' .release-denylist | sed '/^\s*$/d' > "$work/patterns"
  scan "personal words (from .release-denylist)" grep -rIinE -f "$work/patterns" "$stage" "$peek"
fi
scan "widget tokens" grep -rIEn 'svw_[A-Za-z0-9_-]{30,}' "$stage" "$peek"
scan "absolute home paths" grep -rIn '/home/[a-z]' "$stage" "$peek"
scan "developer-only files" find "$stage" \( -path '*/tests' -o -name 'pytest.ini' -o -name 'make-release.sh' \
       -o -name 'preview*splash*' -o -name 'start-savings-server.sh' -o -name '.gitignore' \) -print
scan "developer-only mentions in the shipped docs" grep -rIn -E 'make-release|preview-splashes|start-savings-server|~/savings-widget|pytest|tmp/devdata' \
       "$stage/server/README.md" "$stage/INSTALL.md" "$stage/server/docs"
rm -rf "$peek" "$work/patterns"
stop_if_errors

# ---------- 5. pack ----------
step "Packing"
out="$outdir/$name.tar.gz"
[ -f "$out" ] && warn "release/$name.tar.gz already exists and is replaced (bump VERSION for a new release)"
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
  step "Verifying the packed bundle"
  check="$root/tmp/release-check"; rm -rf "$check"; mkdir -p "$check"
  tar -xzf "$out" -C "$check"
  img="savings-release-check:$version"
  if docker build -q -t "$img" "$check/$name/server" >/dev/null 2>"$check/build.log"; then
    ok "builds from a fresh unpack"
    # the tests aren't shipped: run this project's tests against the server built from the bundle
    # (hard time limit: a stuck test must fail the release, not hang it)
    if result="$(timeout 600 docker run --rm -v "$root/tests:/app/tests:ro" -v "$root/pytest.ini:/app/pytest.ini:ro" \
                 -v "$root/scripts/preview_splashes.py:/app/scripts/preview_splashes.py:ro" \
                 "$img" pytest -q --no-header -o addopts="-p no:cacheprovider" 2>&1)"; then
      tests="$(printf '%s' "$result" | tail -1)"; ok "tests: $tests"
    else
      tests="FAILED"; err "tests failed in the packed bundle:"; printf '%s\n' "$result" | grep -E "FAILED|Error|passed|failed" | head -20 | sed 's/^/      /'
    fi
    docker image rm "$img" >/dev/null 2>&1
  else
    err "the packed bundle doesn't build:"; tail -15 "$check/build.log" | sed 's/^/      /'
  fi
  rm -rf "$check"
  if [ "$errors" -gt 0 ]; then
    rm -f "$out" "$out.sha256"
    printf '  (the broken bundle was removed from release/)\n'
    stop_if_errors
  fi
fi
rm -rf "$work"

# ---------- summary ----------
printf '\n%sRelease built:%s release/%s.tar.gz\n' "$G" "$N" "$name"
printf '  Savings %s · tests %s · %d warning(s)\n' "$version" "$tests" "$warnings"
printf '  send it with its checksum file; the friend runs: tar xf %s.tar.gz && cd %s && ./install.sh\n' "$name" "$name"
exit 0
