#!/usr/bin/env bash
# Start backend + Electron with Vite hot reload.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=/dev/null
source .venv/bin/activate

cleanup() {
  jobs -p | xargs -r kill 2>/dev/null || true
}
trap cleanup EXIT

python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8765 &
BACKEND_PID=$!

cd frontend
OVERLORD_NO_BACKEND=1 npx --yes concurrently -k -n VITE,ELEC -c cyan,magenta \
  "npm run dev" \
  "npx wait-on http://localhost:5173 && npx electron ."
wait "$BACKEND_PID" || true
