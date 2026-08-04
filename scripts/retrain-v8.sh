#!/usr/bin/env bash
# Дообучение DigitCNN → out_digits_v8 → копирование в kapcha-solver/model/
#
# Перед запуском разметь дампы:
#   kapcha-solver/dumps/YYYYMMDD/*.png  →  скопируй в kapcha/dataset/labeled/
#   рядом .txt с 5 цифрами (имя как у png: foo.png → foo.txt с содержимым "34941")
#
# Usage (из репо):
#   bash kapcha-solver/scripts/retrain-v8.sh
#   KAPCHA_MIN_EM=0.85 bash kapcha-solver/scripts/retrain-v8.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$ROOT/.." && pwd)"
TRAIN="$REPO/kapcha/train"
DATA="$REPO/kapcha/dataset/labeled"
OUT="$TRAIN/out_digits_v8"
SOLVER_MODEL="$ROOT/model"
MIN_EM="${KAPCHA_MIN_EM:-0.85}"
EPOCHS="${KAPCHA_EPOCHS:-50}"

if [[ ! -x "$TRAIN/.venv/bin/python" ]]; then
    echo "[retrain-v8] нет $TRAIN/.venv — создай venv и поставь requirements"
    exit 1
fi

n_png=$(find "$DATA" -maxdepth 1 -name '*.png' 2>/dev/null | wc -l | tr -d ' ')
echo "[retrain-v8] labeled png: $n_png → $OUT (epochs=$EPOCHS)"

mkdir -p "$OUT"
cd "$TRAIN"
"$TRAIN/.venv/bin/python" digit_train.py \
    --data-dir "$DATA" \
    --out-dir "$OUT" \
    --epochs "$EPOCHS" \
    --batch-size 64

META="$OUT/best_metrics.json"
if [[ ! -f "$OUT/best.pt" || ! -f "$META" ]]; then
    echo "[retrain-v8] нет best.pt / best_metrics.json"
    exit 1
fi

EM="$("$TRAIN/.venv/bin/python" -c "import json; print(json.load(open('$META'))['exact_match'])")"
echo "[retrain-v8] best exact_match=$EM (need >= $MIN_EM)"

"$TRAIN/.venv/bin/python" - <<PY
import json, sys
em = float(json.load(open("$META"))["exact_match"])
need = float("$MIN_EM")
if em < need:
    print(f"[retrain-v8] EM {em:.4f} < {need} — НЕ копирую в solver (оставь v5)")
    sys.exit(2)
print(f"[retrain-v8] EM {em:.4f} ok — копирую в solver")
PY

cp "$OUT/best.pt" "$SOLVER_MODEL/best.pt"
cp "$META" "$SOLVER_MODEL/best_metrics.json"
echo "[retrain-v8] → $SOLVER_MODEL/best.pt"
echo "[retrain-v8] рестартни solver: bash scripts/run/solver.sh"
