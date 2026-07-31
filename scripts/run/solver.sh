#!/bin/bash
#   nohup bash scripts/run/solver.sh > solver.log 2>&1 &
set -euo pipefail
cd "$(dirname "$0")/../.." || exit 1

free_port() {
    local port="${1:-8790}"
    if command -v fuser >/dev/null 2>&1; then
        fuser -k "${port}/tcp" 2>/dev/null || true
    fi
    if command -v lsof >/dev/null 2>&1; then
        lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | xargs -r kill -9 2>/dev/null || true
    fi
    # ss → pid
    local pids
    pids=$(ss -tlnp 2>/dev/null | grep ":${port} " | grep -oP 'pid=\K[0-9]+' | sort -u || true)
    for p in $pids; do
        kill -9 "$p" 2>/dev/null || true
    done
}

if [[ ! -x .venv/bin/python ]]; then
    echo "[solver] создаю .venv…"
    python3 -m venv .venv || {
        echo "[solver] нужен: apt-get install -y python3-venv python3-pip"
        exit 1
    }
fi

PY=.venv/bin/python

if ! "$PY" -m pip --version >/dev/null 2>&1; then
    echo "[solver] ensurepip…"
    "$PY" -m ensurepip --upgrade || true
fi
if ! "$PY" -m pip --version >/dev/null 2>&1; then
    echo "[solver] pip в venv нет → apt-get install -y python3-venv python3-pip"
    exit 1
fi

need_install=0
"$PY" -c "import fastapi, uvicorn, cv2, PIL" 2>/dev/null || need_install=1
"$PY" -c "import torch" 2>/dev/null || need_install=1

if [[ "$need_install" -eq 1 ]]; then
    echo "[solver] ставлю deps (CPU torch)…"
    "$PY" -m pip install -U pip
    "$PY" -m pip install -r requirements.txt
    "$PY" -m pip install torch --index-url https://download.pytorch.org/whl/cpu
fi

echo "[solver] wrapper pid $$ — $PY"
"$PY" -c "import fastapi, torch; print('[solver] fastapi', fastapi.__version__, 'torch', torch.__version__)"

while true; do
    echo "[solver] free :8790"
    free_port 8790
    sleep 1
    set +e
    "$PY" server.py
    code=$?
    set -e
    echo "[solver] exit $code — рестарт через 5с"
    sleep 5
done
