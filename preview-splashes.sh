#!/usr/bin/env bash
# Try every splash screen on this PC: builds a standalone page from the app's own splash files
# and opens it in your browser. Pick one from the list, it plays, then you're back at the list.
# Needs only python3 (standard library). No server, Docker or internet involved.
set -e
cd "$(dirname "$(readlink -f "$0")")"
python3 scripts/preview_splashes.py "$@"
