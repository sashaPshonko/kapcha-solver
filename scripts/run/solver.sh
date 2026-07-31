#!/bin/bash
# Как sellbot/502: цикл + сервер в foreground. nohup снаружи.
#   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
#   nohup bash scripts/run/solver.sh > solver.log 2>&1 &
cd "$(dirname "$0")/../.." || exit 1

if [[ ! -x .venv/bin/python ]]; then
    echo "[solver] нет .venv — сделай:"
    echo "  python3 -m venv .venv"
    echo "  .venv/bin/pip install -r requirements.txt"
    exit 1
fi

PY=.venv/bin/python
echo "[solver] wrapper pid $$ — cwd $(pwd) py=$PY"
echo "[solver] :8790"

while true; do
    "$PY" server.py
    code=$?
    echo "[solver] exit $code — рестарт через 5с"
    sleep 5
done
