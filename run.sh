#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ -f .env ]]; then set -a; # shellcheck disable=SC1091
  source .env
  set +a
fi
PY="${SOLVER_PYTHON:-}"
if [[ -z "$PY" ]]; then
  if [[ -x .venv/bin/python ]]; then PY=.venv/bin/python
  elif [[ -x ../kapcha/train/.venv/bin/python ]]; then PY=../kapcha/train/.venv/bin/python
  else PY=python3
  fi
fi
exec "$PY" server.py
