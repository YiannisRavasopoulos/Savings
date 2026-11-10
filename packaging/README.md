# Packaging and releasing

This folder turns the source into the two releases people download from the **Releases** page on
GitHub. It's for the maintainer. Nothing here is meant to be run from a clone: to install
Savings, download a release.

```
packaging/
├── app/                 Savings (the server)          → release/savings-X.Y.Z.tar.gz
│   ├── make-release.sh  builds it
│   ├── install.sh       ┐
│   ├── uninstall.sh     ├ ship at the top of the release, next to server/
│   └── INSTALL.md       ┘
├── widget/              the KDE Plasma widget          → release/savings-widget-X.Y.Z.tar.gz
│   ├── make-release.sh  builds it (from ../widget/)
│   ├── install.sh       ┐
│   ├── uninstall.sh     ├ ship next to the .plasmoid
│   └── INSTALL.md       ┘
└── release-checks.py    version and changelog checks used by both builders and by CI
```

Finished archives and their `.sha256` files go to `release/` at the top of the repository. It's
gitignored: archives never go into git, only onto the Releases page.

Savings and the widget are released **separately**, each with its own version. Release only the
one that changed.

## The changelog

`CHANGELOG.md` (at the top of the repository) lists what changed in each version, written for
the people who install Savings, not for developers. Each GitHub release's description is copied
from it, and it ships inside the Savings release.

**While working:** for every change people would notice, add a line under the right heading:

```markdown
## Unreleased                         ← Savings changes not released yet

### New                               ← new features
### Fixed                             ← bugs fixed
### Changed                           ← behaviour that's different now

## Widget 1.5.2 · unreleased          ← widget changes not released yet (its next version)
```

Create a heading when it's missing. Leave out sections with nothing in them. Newest goes at the
top, right under the `---` line.

**When releasing:** rename the heading to the version and today's date, exactly like this:

```markdown
## Savings 1.4.0 · 2026-12-01
## Widget 1.5.2 · 2026-12-01
```

The release builders look for exactly that heading and refuse to build without it.

## Which version number?

Versions are `MAJOR.MINOR.PATCH`, e.g. `1.3.0`:

- only fixes → raise **PATCH**: `1.3.0` → `1.3.1`
- new features → raise **MINOR** and reset PATCH: `1.3.1` → `1.4.0`
- upgrading needs people to do something by hand → raise **MAJOR**: `1.4.0` → `2.0.0`

A released version is never reused: once `1.3.0` is out, any change means a new number.

## Releasing Savings

1. **Version:** write the new version into `VERSION`.
2. **Changelog:** rename `## Unreleased` to `## Savings X.Y.Z · YYYY-MM-DD`.
3. **Build and check:**

   ```sh
   packaging/app/make-release.sh --verify
   ```

   It checks the version and changelog, scans the archive for personal data (`.release-denylist`,
   never committed), tokens, home paths and developer-only files, builds the server from a fresh
   unpack and runs every test. Anything wrong stops it; nothing half-built is left behind.
   Result: `release/savings-X.Y.Z.tar.gz` and `.sha256`.
4. **Commit and push:** `git commit -am "Savings X.Y.Z"` then `git push`.
5. **Publish** (see below) with tag `vX.Y.Z` and title `Savings X.Y.Z`.
6. **Update your own server:** run `./install.sh` from the new release (or `savings update`).

## Releasing the widget

1. **Version:** change `"Version"` in `widget/package/metadata.json`.
2. **Changelog:** rename `## Widget X.Y.Z · unreleased` to `## Widget X.Y.Z · YYYY-MM-DD`.
3. **Build and check:**

   ```sh
   packaging/widget/make-release.sh --verify
   ```

   Besides the scans, it installs, reinstalls, (refuses to) downgrade and removes the widget in a
   throwaway home folder; your own panel isn't touched. It also refuses to release changed
   content under a version that's already out. Result: `release/savings-widget-X.Y.Z.tar.gz` and
   `.sha256`.
4. **Commit and push:** `git commit -am "Widget X.Y.Z"` then `git push`.
5. **Publish** (see below) with tag `widget-vX.Y.Z` and title `Savings widget X.Y.Z`.

## Publishing on GitHub

Use **one** of these two ways for each release, not both (the second would fail: the release
already exists).

**By hand, in the browser:**

1. On the repository page, click **Releases** (right side), then **Draft a new release**.
2. **Choose a tag:** type the tag (`v1.3.0` or `widget-v1.5.1`) and pick *Create new tag on
   publish*. Target: `main`.
3. **Release title:** `Savings 1.3.0` or `Savings widget 1.5.1`.
4. **Description:** paste that version's changelog section. This prints it:

   ```sh
   python3 packaging/release-checks.py notes CHANGELOG.md app 1.3.0
   python3 packaging/release-checks.py notes CHANGELOG.md widget 1.5.1
   ```

5. Drag the `.tar.gz` and its `.sha256` from `release/` into the box at the bottom.
6. Click **Publish release**.

**Automatically, by pushing the tag:**

```sh
git tag v1.3.0 && git push origin v1.3.0                # Savings
git tag widget-v1.5.1 && git push origin widget-v1.5.1  # widget
```

`.github/workflows/release.yml` then builds the archive on GitHub's machines, checks that the
tag matches the version and the changelog, and publishes the release with the changelog section
as its description. Follow it under the repository's **Actions** tab.

## If something goes wrong

- **"CHANGELOG.md has no section for this release":** the heading isn't exactly
  `## Savings X.Y.Z · YYYY-MM-DD` (or `## Widget …`). Check the version and the `·`.
- **"already exists and is replaced":** you're rebuilding a version you already built. Fine
  before it's published; after publishing, raise the version instead.
- **A mistake in a published release:** don't change its files. Fix it and release the next
  version (e.g. `1.3.1`). You can edit a release's description on GitHub at any time.
