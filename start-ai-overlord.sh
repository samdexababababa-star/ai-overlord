#!/usr/bin/env bash
# AI Overlord — one-click launcher for Linux
set -euo pipefail
cd "$(dirname "$0")"
exec python3 launch.py "$@"
