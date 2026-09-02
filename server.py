#!/usr/bin/env python3
"""HTTP captcha solver for FunTime bots (DigitCNN v5).

  POST /api/solve  { "pngBase64": "..." }  →  { "ok": true, "pred": "34941", ... }
  GET  /api/health

Conf = min(digit_conf). Reject when below KAPCHA_MIN_CONF (default 0.55).
Dump PNG+JSON under dumps/YYYYMMDD/ unless request has dump=false (client solves).
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from model_infer import load_model, pick_device, predict_png_bytes

ROOT = Path(__file__).resolve().parent
CKPT = ROOT / "model" / "best.pt"
DUMPS = ROOT / "dumps"
HOST = os.environ.get("KAPCHA_HOST", "127.0.0.1")
PORT = int(os.environ.get("KAPCHA_PORT", "8799"))
MIN_CONF = float(os.environ.get("KAPCHA_MIN_CONF", "0.40"))

_model = None
_device = None
_ready = False
_load_error: str | None = None
_metrics: dict[str, Any] = {}


def try_load() -> None:
    global _model, _device, _ready, _load_error, _metrics
    if _ready:
        return
    try:
        if not CKPT.exists():
            raise FileNotFoundError(f"missing ckpt {CKPT}")
        _device = pick_device()
        _model = load_model(CKPT, _device)
        meta = CKPT.parent / "best_metrics.json"
        if meta.exists():
            _metrics = json.loads(meta.read_text(encoding="utf-8"))
        _ready = True
        _load_error = None
    except Exception as e:
        _ready = False
        _load_error = f"{type(e).__name__}: {e}"


def _safe_token(s: str | None, fallback: str = "anon") -> str:
    t = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(s or "").strip())[:32]
    return t or fallback


def dump_solve(
    png: bytes,
    *,
    pred: str,
    conf: float,
    digit_conf: list[float],
    ok: bool,
    ms: int,
    username: str | None,
    fingerprint: str | None,
) -> str | None:
    """Write PNG + JSON sidecar; return relative path stem or None on failure."""
    try:
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        out_dir = DUMPS / day
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%H%M%S_%f")[:-3]
        user = _safe_token(username)
        stem = f"{ts}_{user}_{pred}_c{conf:.3f}"
        if not ok:
            stem += "_low"
        png_path = out_dir / f"{stem}.png"
        meta_path = out_dir / f"{stem}.json"
        png_path.write_bytes(png)
        meta_path.write_text(
            json.dumps(
                {
                    "pred": pred,
                    "conf": round(conf, 4),
                    "digit_conf": [round(c, 4) for c in digit_conf],
                    "ok": ok,
                    "low_conf": not ok,
                    "ms": ms,
                    "username": username,
                    "fingerprint": fingerprint,
                    "ckpt": CKPT.name,
                    "min_conf": MIN_CONF,
                    "png": png_path.name,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return f"{day}/{stem}"
    except Exception:
        return None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try_load()
    yield


app = FastAPI(title="kapcha-solver", version="1.1", lifespan=lifespan)


class SolveIn(BaseModel):
    pngBase64: str = Field(..., min_length=32)
    username: str | None = None
    fingerprint: str | None = None
    dump: bool = True


@app.get("/api/health")
def health() -> dict[str, Any]:
    if not _ready:
        try_load()
    return {
        "ready": _ready,
        "error": _load_error,
        "ckpt": str(CKPT.name),
        "device": str(_device) if _device is not None else None,
        "min_conf": MIN_CONF,
        "exact_match": _metrics.get("exact_match"),
        "char_accuracy": _metrics.get("char_accuracy"),
    }


@app.post("/api/solve")
def solve(body: SolveIn) -> dict[str, Any]:
    if not _ready:
        try_load()
    if not _ready or _model is None or _device is None:
        raise HTTPException(503, detail=_load_error or "model not ready")

    raw = body.pngBase64
    if "," in raw[:80]:
        raw = raw.split(",", 1)[1]
    try:
        png = base64.b64decode(raw, validate=False)
    except Exception as e:
        raise HTTPException(400, detail=f"bad base64: {e}") from e
    if len(png) < 100:
        raise HTTPException(400, detail="png too small")

    t0 = time.perf_counter()
    try:
        pred, digit_conf = predict_png_bytes(_model, png, _device)
    except Exception as e:
        raise HTTPException(422, detail=f"predict failed: {type(e).__name__}: {e}") from e
    ms = int((time.perf_counter() - t0) * 1000)

    if len(pred) != 5 or not pred.isdigit():
        raise HTTPException(422, detail=f"bad pred {pred!r}")

    # gate by weakest digit — mean hides one bad crop
    conf = min(digit_conf) if digit_conf else 0.0
    ok = conf >= MIN_CONF
    dump_id = None
    if body.dump:
        dump_id = dump_solve(
            png,
            pred=pred,
            conf=conf,
            digit_conf=digit_conf,
            ok=ok,
            ms=ms,
            username=body.username,
            fingerprint=body.fingerprint,
        )

    return {
        "ok": ok,
        "pred": pred,
        "conf": round(conf, 4),
        "digit_conf": [round(c, 4) for c in digit_conf],
        "ms": ms,
        "ckpt": CKPT.name,
        "username": body.username,
        "fingerprint": body.fingerprint,
        "low_conf": not ok,
        "dump": dump_id,
        "min_conf": MIN_CONF,
    }


if __name__ == "__main__":
    import uvicorn

    # app-объект, не "server:app" — иначе двойной импорт и странности с портом
    uvicorn.run(app, host=HOST, port=PORT, reload=False)
