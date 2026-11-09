#!/usr/bin/env bash
# "Savings Admin" launcher: make sure the tracker is running, then open the admin pages.
# The admin port is published on 127.0.0.1 only, so this works on this PC and nowhere else.
set -e
cd "$(dirname "$(readlink -f "$0")")"
port="$(sed -n 's/^ADMIN_PORT=//p' .env 2>/dev/null | tr -d '"')"
url="http://localhost:${port:-8091}"
docker compose up -d >/dev/null 2>&1 || true
for _ in $(seq 1 20); do
  curl -fs -o /dev/null "$url/login" && break
  sleep 0.5
done
xdg-open "$url" >/dev/null 2>&1 &
