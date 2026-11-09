## What changed

<!-- One topic per pull request. What does it change for people using Savings or the widget? -->

## How it was tested

<!-- e.g. "docker compose run --rm app pytest: all passed", plus anything checked by hand
     (phone and PC, light and dark themes for anything visual). -->

## Checklist

- [ ] Tests added or updated, and the whole suite passes
- [ ] Changelog line under `## Unreleased` (app) or the widget's unreleased section
- [ ] No real data, tokens, `.env` or databases in the change
- [ ] If `/api/summary` changed: fields were only added (or `API_VERSION` and the widget's `apiVersion` were raised together)
