#!/usr/bin/env bash
# Taskbar launcher: make sure the tracker is running, then open it in the browser.
# If the container is already up this does nothing but open the page.
set -e
cd "$(dirname "$(readlink -f "$0")")"
port="$(sed -n 's/^PORT=//p' .env 2>/dev/null | tr -d '"')"
url="http://localhost:${port:-8090}"
docker compose up -d >/dev/null 2>&1 || true
for _ in $(seq 1 20); do                      # wait up to ~10 s for the app to answer
  curl -fs -o /dev/null "$url/" && break
  sleep 0.5
done
xdg-open "$url" >/dev/null 2>&1 &
