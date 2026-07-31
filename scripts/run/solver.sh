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

need_install=0
"$PY" -c "import fastapi, uvicorn, cv2, PIL" 2>/dev/null || need_install=1
"$PY" -c "import torch" 2>/dev/null || need_install=1

if [[ "$need_install" -eq 1 ]]; then
    echo "[solver] ставлю deps (CPU torch, без CUDA)…"
    "$PY" -m pip install -U pip
    "$PY" -m pip install -r requirements.txt
    # лёгкая CPU-сборка — CUDA torch на VPS жрёт диск и не нужен
    "$PY" -m pip install torch --index-url https://download.pytorch.org/whl/cpu
fi

echo "[solver] wrapper pid $$ — $PY"
echo "[solver] :8790"
"$PY" -c "import fastapi, torch; print('[solver] fastapi', fastapi.__version__, 'torch', torch.__version__)"

while true; do
    set +e
    "$PY" server.py
    code=$?
    set -e
    echo "[solver] exit $code — рестарт через 5с"
    sleep 5
done
