#!/bin/bash
#   nohup bash scripts/run/solver.sh > solver.log 2>&1 &
set -euo pipefail
cd "$(dirname "$0")/../.." || exit 1

if [[ ! -x .venv/bin/python ]]; then
    echo "[solver] создаю .venv…"
    python3 -m venv .venv || {
        echo "[solver] нужен пакет: apt-get install -y python3-venv python3-pip"
        exit 1
    }
fi

PY=.venv/bin/python

# на многих VPS нет .venv/bin/pip — только python -m pip
if ! "$PY" -m pip --version >/dev/null 2>&1; then
    echo "[solver] ensurepip…"
    "$PY" -m ensurepip --upgrade || true
fi
if ! "$PY" -m pip --version >/dev/null 2>&1; then
    echo "[solver] pip в venv нет. На хосте:"
    echo "  apt-get install -y python3-venv python3-pip"
    echo "  rm -rf .venv && python3 -m venv .venv"
    exit 1
fi

if ! "$PY" -c "import fastapi, uvicorn, torch, cv2" 2>/dev/null; then
    echo "[solver] ставлю requirements.txt…"
    "$PY" -m pip install -U pip
    "$PY" -m pip install -r requirements.txt
fi

echo "[solver] wrapper pid $$ — $PY"
echo "[solver] :8790"
"$PY" -c "import fastapi; print('[solver] fastapi', fastapi.__version__)"

while true; do
    set +e
    "$PY" server.py
    code=$?
    set -e
    echo "[solver] exit $code — рестарт через 5с"
    sleep 5
done
