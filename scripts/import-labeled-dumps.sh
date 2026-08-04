#!/usr/bin/env bash
# Импорт размеченных дампов solver → kapcha/dataset/labeled
#
# Ожидает рядом с png файл .txt (5 цифр) ИЛИ правку в .json поле "gold":
#   dumps/20260804/120001_bot_29655_c0.355_low.png
#   dumps/20260804/120001_bot_29655_c0.355_low.txt   →  content: 29655
#   # или в .json: "gold": "29655"
#
# Usage:
#   bash kapcha-solver/scripts/import-labeled-dumps.sh
#   bash kapcha-solver/scripts/import-labeled-dumps.sh dumps/20260804
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$ROOT/.." && pwd)"
LABELED="$REPO/kapcha/dataset/labeled"
SRC="${1:-$ROOT/dumps}"

mkdir -p "$LABELED"
imported=0
skipped=0

while IFS= read -r -d '' png; do
    stem="${png%.png}"
    gold=""
    if [[ -f "${stem}.txt" ]]; then
        gold="$(tr -d ' \n\r\t' < "${stem}.txt")"
    elif [[ -f "${stem}.json" ]]; then
        gold="$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('gold') or '')" "${stem}.json" 2>/dev/null || true)"
    fi
    if [[ ! "$gold" =~ ^[0-9]{5}$ ]]; then
        skipped=$((skipped + 1))
        continue
    fi
    # следующий свободный 4-digit id в labeled
    n=1
    while [[ -e "$LABELED/$(printf '%04d' "$n").png" ]]; do
        n=$((n + 1))
    done
    id="$(printf '%04d' "$n")"
    cp "$png" "$LABELED/${id}.png"
    printf '%s\n' "$gold" > "$LABELED/${id}.txt"
    imported=$((imported + 1))
    echo "+ $id ← $(basename "$png") gold=$gold"
done < <(find "$SRC" -type f -name '*.png' -print0 2>/dev/null)

echo "[import] imported=$imported skipped_no_gold=$skipped → $LABELED"
