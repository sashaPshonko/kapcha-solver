#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ -x .venv/bin/python ]]; then
    exec .venv/bin/python server.py
fi
if [[ -x ../kapcha/train/.venv/bin/python ]]; then
    exec ../kapcha/train/.venv/bin/python server.py
fi
exec python3 server.py
