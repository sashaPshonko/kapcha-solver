#!/bin/bash
# Останавливает solver полностью (обёртка + python + порт 8790).
cd "$(dirname "$0")/../.." || exit 1
ROOT="$(pwd)"

echo "[solver] killing wrappers / server…"
pkill -9 -f "$ROOT/scripts/run/solver.sh" 2>/dev/null || true
pkill -9 -f "$ROOT/server.py" 2>/dev/null || true
pkill -9 -f "uvicorn server:app" 2>/dev/null || true

if command -v fuser >/dev/null 2>&1; then
    fuser -k 8790/tcp 2>/dev/null || true
else
    # fallback without psmisc
    pids=$(ss -tlnp 2>/dev/null | awk '/:8790/ {print}' | grep -oP 'pid=\K[0-9]+' | sort -u)
    for p in $pids; do
        kill -9 "$p" 2>/dev/null || true
    done
fi

sleep 1
if ss -tlnp 2>/dev/null | grep -q ':8790'; then
    echo "[solver] WARN: 8790 still busy:"
    ss -tlnp | grep 8790 || true
else
    echo "[solver] 8790 free"
fi
