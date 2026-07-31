#!/bin/bash
# Останавливает обёртку solver.sh и python server.py в kapcha-solver.
cd "$(dirname "$0")/../.." || exit 1
ROOT="$(pwd)"

pkill -f "$ROOT/scripts/run/solver.sh" 2>/dev/null || true
pkill -f "$ROOT/server.py" 2>/dev/null || true
echo "[solver] stop sent"
