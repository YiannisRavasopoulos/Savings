# Making a release

[← Savings](../README.md) · [All docs](README.md)

Savings and the KDE widget are **released separately**, each with its own version, archive and
installer. Either can be released without the other. Their only link is the widget API
(`/api/summary`): within one API generation the server only ever adds fields, and the widget
says "update the widget" if the server's generation is newer than it understands (see
`API_VERSION` in `app/api.py`).

## Savings (server and app)

1. Raise the version in `VERSION` (`major.minor.patch`: minor for new features, patch for fixes
   only).
2. In `CHANGELOG.md`, rename **Unreleased** to `## Savings X.Y.Z · YYYY-MM-DD` and keep only the
   app's changes there. It ships in the archive, so write it for the people installing it.

```sh
scripts/make-release.sh --verify
```

This one command checks, builds and tests `release/savings-<version>.tar.gz` (plus a `.sha256`).
The archive contains `install.sh`, `uninstall.sh`, `INSTALL.md`, `LICENSE` (MIT) and the server.
It prints each step with ✓ / ! / ✗ and ends with a summary.

| Step | Checks |
|---|---|
| Tools and project | python3, tar, sha256sum (and Docker for `--verify`); `VERSION` looks like 1.2.3; every release file exists; all shell scripts parse |
| Changelog | `CHANGELOG.md` has a `## Savings <version> · <date>` section |
| Files | copies only an allow-list: never `.env`, data, backups, `tmp/`, the release builder, the widget or this PC's launchers |
| Personal data scan | words from `.release-denylist` (a local list that's never shipped); widget tokens; databases, `.env`, backups, keys, Plasma configs; absolute home paths |
| `--verify` | unpacks the archive fresh, builds it under a separate image name and runs the whole test suite (with a time limit). A failing archive is removed from `release/`. |

- **Errors** stop the build, and it exits with code 1. **Warnings** are listed and the build goes on:
  no denylist, the same version already in `release/`, or a leftover **Unreleased** section.
  `--strict` makes warnings errors too. Wrong options exit with code 2. `--help` lists everything.

Friends follow `INSTALL.md`: `./install.sh` asks for the install and data folders (an existing
data folder can be plugged in), ports, timezone and backups, then builds, starts and enables
start-at-boot, and adds the launchers. Running it again upgrades and keeps settings and data.

## The KDE widget

1. Raise the version in `widget/package/metadata.json`.
2. Add `## Widget X.Y.Z · YYYY-MM-DD` to `CHANGELOG.md`, saying which Savings it needs if that
   changed.

```sh
widget/make-release.sh --verify
```

It builds `widget/release/savings-widget-<version>.tar.gz` (plus a `.sha256`) and, with
`--verify`, installs, upgrades and removes it in a throwaway home folder. Besides its own checks
(see the widget's README) it refuses a version that was **already released with different
files**: a widget version, once out, never changes. Its installer never replaces a newer
installed widget with an older one (unless `--force`).
