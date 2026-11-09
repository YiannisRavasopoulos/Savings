#!/usr/bin/env bash
# Rebuild/update the spending tracker after code changes, then open it.
# Only needed once: after that the container comes back on every boot by
# itself (restart: unless-stopped), like Jellyfin. For everyday use, the
# "Savings" taskbar launcher (open-savings-client.sh) is all you need.
set -e
cd "$(dirname "$(readlink -f "$0")")"
docker compose up -d --build --remove-orphans
port="$(sed -n 's/^PORT=//p' .env 2>/dev/null | tr -d '"')"
xdg-open "http://localhost:${port:-8090}" >/dev/null 2>&1 &
