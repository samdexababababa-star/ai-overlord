#!/usr/bin/env bash
# AI Overlord — one-click launcher for macOS
# Double-click in Finder. Finder will run it in Terminal.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 launch.py "$@"
