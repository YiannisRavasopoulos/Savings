# Contributing to Savings

Thanks for helping. Bug reports, ideas, documentation fixes and code are all welcome.

## Reporting a bug or suggesting an idea

Use the **Issues** page and pick the bug or idea template. For a bug, say what you did, what you
expected and what happened, and include your Savings version (on the admin app's home page) and,
for the widget, its version. **Never paste real spending data, tokens or passwords.** For
security problems, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

## Working on the code

Everything runs in Docker, against a throwaway data folder. Never point a development copy at
your real data. [docs/development.md](docs/development.md) has the commands and the project
layout.

- **Tests:** the whole suite must pass before a change is merged:

  ```sh
  docker compose run --rm app pytest
  ```

  Add tests with your change: a route, a calculation or a template rule each get one. Tests that
  start threads (the backup scheduler) must always stop them, so a failure can't hang the suite.
- **Database changes:** add a new numbered file in `migrations/`. Never edit one that has been
  released.
- **Style:** small, readable modules; comments say *why*, not *what*. Colours live in
  `app/static/themes/` as variables; `style.css` has no hard-coded colours (a test checks this).
- **Privacy:** never commit `.env`, a database, backups or `.release-denylist`. The
  `.gitignore` covers them; don't force-add them.

## The changelog

Every change people would notice gets a line in [CHANGELOG.md](CHANGELOG.md), written for the
people installing Savings, not for developers:

- app changes go under `## Unreleased` (sections *New*, *Fixed*, *Changed*);
- widget changes go under `## Widget X.Y.Z · unreleased`, with the widget's next version.

Savings and the widget are released separately and version independently. The maintainer dates
these sections when releasing; see [docs/releasing.md](docs/releasing.md).

## Compatibility between the app and the widget

The widget only talks to `/api/summary`. Within one API generation (`API_VERSION` in
`app/api.py`) the server may **add** fields but never rename or remove them. If a change needs
that, raise `API_VERSION` and the widget's `apiVersion` together, and note it in both changelog
sections.

## Pull requests

Keep a pull request to one topic, describe what changed and how you tested it, and include the
changelog line. Screenshots help for anything visual (phone and PC, light and dark).

## AI-assisted contributions

Savings itself is built with AI assistance, so AI-assisted contributions are welcome on the same
terms as any other: you're responsible for the change, it must be tested, and the pull request
should say how it was checked.

## Code of conduct

Be kind and constructive. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
