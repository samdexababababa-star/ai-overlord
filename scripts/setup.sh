#!/usr/bin/env bash
# Install backend (Python venv) + frontend (npm) dependencies.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck source=/dev/null
source .venv/bin/activate
python -m pip install --upgrade pip wheel
pip install -e ./backend

cd frontend
if command -v pnpm >/dev/null 2>&1; then
  pnpm install
else
  npm install
fi

echo
echo "Setup complete."
echo "Next:  ./scripts/dev.sh"
