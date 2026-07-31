#!/bin/bash
#   nohup bash scripts/run/solver.sh > solver.log 2>&1 &
set -euo pipefail
cd "$(dirname "$0")/../.." || exit 1

if [[ ! -x .venv/bin/python ]]; then
    echo "[solver] создаю .venv…"
    python3 -m venv .venv
fi

PY=.venv/bin/python
PIP=.venv/bin/pip

if ! "$PY" -c "import fastapi, uvicorn, torch, cv2" 2>/dev/null; then
    echo "[solver] ставлю requirements.txt…"
    "$PIP" install -U pip
    "$PIP" install -r requirements.txt
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
