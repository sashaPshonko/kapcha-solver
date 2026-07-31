#!/bin/bash
# Как sellbot/502: цикл + сервер в foreground. nohup снаружи.
#   nohup bash scripts/run/solver.sh > solver.log 2>&1 &
cd "$(dirname "$0")/../.." || exit 1

if [[ -x .venv/bin/python ]]; then
    PY=.venv/bin/python
elif [[ -x ../kapcha/train/.venv/bin/python ]]; then
    PY=../kapcha/train/.venv/bin/python
else
    PY=python3
fi

echo "[solver] wrapper pid $$ — cwd $(pwd) py=$PY"
echo "[solver] :8790"

while true; do
    "$PY" server.py
    code=$?
    echo "[solver] exit $code — рестарт через 5с"
    sleep 5
done
