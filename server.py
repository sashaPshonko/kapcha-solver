#!/usr/bin/env python3
"""HTTP captcha solver for FunTime bots (DigitCNN v5).

  POST /api/solve  { "pngBase64": "..." }  →  { "ok": true, "pred": "34941", ... }
  GET  /api/health

Auth (optional): header X-Solver-Token / Authorization: Bearer <token>
  env SOLVER_TOKEN — if set, required.
"""

from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from model_infer import load_model, pick_device, predict_png_bytes

ROOT = Path(__file__).resolve().parent
CKPT = Path(os.getenv("SOLVER_CKPT", str(ROOT / "model" / "best.pt")))
HOST = os.getenv("SOLVER_HOST", "0.0.0.0")
PORT = int(os.getenv("SOLVER_PORT", "8790"))
TOKEN = (os.getenv("SOLVER_TOKEN") or "").strip()
MIN_CONF = float(os.getenv("SOLVER_MIN_CONF", "0.0"))

app = FastAPI(title="kapcha-solver", version="1.0")

_model = None
_device = None
_ready = False
_load_error: str | None = None
_metrics: dict[str, Any] = {}


def _check_token(
    x_solver_token: str | None = None,
    authorization: str | None = None,
) -> None:
    if not TOKEN:
        return
    got = (x_solver_token or "").strip()
    if not got and authorization:
        auth = authorization.strip()
        if auth.lower().startswith("bearer "):
            got = auth[7:].strip()
    if got != TOKEN:
        raise HTTPException(401, detail="bad token")


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


@app.on_event("startup")
def _startup() -> None:
    try_load()


class SolveIn(BaseModel):
    pngBase64: str = Field(..., min_length=32)
    username: str | None = None
    fingerprint: str | None = None


@app.get("/api/health")
def health(
    x_solver_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_token(x_solver_token, authorization)
    if not _ready:
        try_load()
    return {
        "ready": _ready,
        "error": _load_error,
        "ckpt": str(CKPT.name),
        "device": str(_device) if _device is not None else None,
        "exact_match": _metrics.get("exact_match"),
        "char_accuracy": _metrics.get("char_accuracy"),
        "token_required": bool(TOKEN),
    }


@app.post("/api/solve")
def solve(
    body: SolveIn,
    x_solver_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_token(x_solver_token, authorization)
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
    conf = sum(digit_conf) / max(1, len(digit_conf))

    if len(pred) != 5 or not pred.isdigit():
        raise HTTPException(422, detail=f"bad pred {pred!r}")

    ok = conf >= MIN_CONF
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
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host=HOST, port=PORT, reload=False)
