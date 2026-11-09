#!/usr/bin/env python3
"""Version checks for the two separate releases: scripts/make-release.sh (Savings, the server) and
widget/make-release.sh (the KDE widget). They're released independently; this keeps each one's
version honest and its changelog entry present.

  release-checks.py widget PLASMOID RELEASE_DIR...
      A widget version, once released, is fixed: if any archive in RELEASE_DIR (a widget release,
      or a Savings release from before 1.3.0, which bundled it) already contains this version,
      PLASMOID must match it file for file. Prints "new", "same" or (exit 1) what differs.

  release-checks.py changelog CHANGELOG app VERSION
  release-checks.py changelog CHANGELOG widget WIDGET_VERSION
      CHANGELOG.md must have a section for the release: "## Savings 1.3.0 · <date>" for an app
      release, "## Widget 1.5.1 · <date>" for a widget release. (Before 1.3.0 the widget shipped
      inside the app release, so older headings read "## Savings 1.2.0 · widget 1.5.0 · <date>".) Exit 1 with the reason if not. A leftover "## Unreleased"
      section is reported as a warning (exit 3).

  release-checks.py notes CHANGELOG app|widget VERSION
      Print that release's CHANGELOG section (used as the GitHub release notes).

Python standard library only.
"""
from __future__ import annotations

import io
import json
import re
import sys
import tarfile
import zipfile
from pathlib import Path


def _entries(z: zipfile.ZipFile) -> dict[str, bytes]:
    return {n: z.read(n) for n in z.namelist() if not n.endswith("/")}


def widget(plasmoid: str, *release_dirs: str) -> int:
    with zipfile.ZipFile(plasmoid) as z:
        mine = _entries(z)
    version = json.loads(mine["metadata.json"])["KPlugin"]["Version"]
    want = f"savings-{version}.plasmoid"
    for d in release_dirs:
        for archive in sorted(Path(d).glob("*.tar.gz")) if Path(d).is_dir() else []:
            with tarfile.open(archive) as t:
                for member in t.getmembers():
                    if Path(member.name).name != want:
                        continue
                    with zipfile.ZipFile(io.BytesIO(t.extractfile(member).read())) as z:
                        theirs = _entries(z)
                    if theirs == mine:
                        continue
                    changed = sorted(n for n in set(mine) | set(theirs) if mine.get(n) != theirs.get(n))
                    print(f"widget {version} was already released in {archive.name} with different files "
                          f"({', '.join(changed)[:160]}): give the widget a new version in "
                          f"widget/package/metadata.json")
                    return 1
                    # (a match in one archive and a mismatch in another can't both happen: archives
                    #  are checked the same way when they're built)
    found = any(want in m for d in release_dirs if Path(d).is_dir()
                for a in Path(d).glob("*.tar.gz") for m in tarfile.open(a).getnames())
    print("same" if found else "new")
    return 0


def changelog(path: str, kind: str, *versions: str) -> int:
    text = Path(path).read_text(encoding="utf-8") if Path(path).exists() else ""
    if not text:
        print(f"{path} not found")
        return 1
    heads = re.findall(r"^## (.+)$", text, re.M)
    if kind == "app":
        (version,) = versions
        ok = any(re.match(rf"Savings {re.escape(version)} · (widget [\d.]+ · )?\d{{4}}-\d{{2}}-\d{{2}}$", h) for h in heads)
        need = f'"## Savings {version} · YYYY-MM-DD"'
    else:
        (wv,) = versions
        ok = any(re.match(rf"Widget {re.escape(wv)} · \d{{4}}-\d{{2}}-\d{{2}}$", h)
                 or re.match(rf"Savings [\d.]+ · widget {re.escape(wv)} · ", h) for h in heads)
        need = f'"## Widget {wv} · YYYY-MM-DD"'
    if not ok:
        print(f"CHANGELOG.md has no section for this release: add {need} (rename \"## Unreleased\")")
        return 1
    if "Unreleased" in heads:
        print('CHANGELOG.md still has an "## Unreleased" section: anything in it isn\'t in this release\'s notes')
        return 3
    print("ok")
    return 0


def notes(path: str, kind: str, version: str) -> int:
    """Print the body of a release's CHANGELOG section (for the GitHub release notes)."""
    text = Path(path).read_text(encoding="utf-8")
    title = (rf"Savings {re.escape(version)} · " if kind == "app" else rf"Widget {re.escape(version)} · ")
    m = re.search(rf"^## {title}.*?$\n(.*?)(?=^## |^---$|\Z)", text, re.M | re.S)
    if not m:
        print(f"no CHANGELOG.md section for {kind} {version}", file=sys.stderr)
        return 1
    print(m.group(1).strip())
    return 0


if __name__ == "__main__":
    cmd, *args = sys.argv[1:] or ["-h"]
    if cmd == "widget" and len(args) >= 2:
        sys.exit(widget(*args))
    if cmd == "notes" and len(args) == 3:
        sys.exit(notes(*args))
    if cmd == "changelog" and len(args) == 3:
        sys.exit(changelog(*args))
    print(__doc__, file=sys.stderr)
    sys.exit(2)
