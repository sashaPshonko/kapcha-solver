"""DigitCNN inference (same arch as kapcha/train DigitCNN v2 / out_digits_v5)."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from preprocess import extract_digit_crops, load_bgr

CROP_W = 96
CROP_H = 128
NUM_CLASSES = 10


class ConvBNReLU(nn.Module):
    def __init__(self, cin: int, cout: int) -> None:
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(cin, cout, 3, padding=1, bias=False),
            nn.BatchNorm2d(cout),
            nn.ReLU(inplace=True),
            nn.Conv2d(cout, cout, 3, padding=1, bias=False),
            nn.BatchNorm2d(cout),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.block(x)


class DigitCNN(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.net = nn.Sequential(
            ConvBNReLU(3, 32),
            nn.MaxPool2d(2),
            ConvBNReLU(32, 64),
            nn.MaxPool2d(2),
            ConvBNReLU(64, 128),
            nn.MaxPool2d(2),
            ConvBNReLU(128, 256),
            nn.MaxPool2d(2),
            ConvBNReLU(256, 256),
            nn.AdaptiveAvgPool2d((4, 3)),
        )
        self.drop = nn.Dropout(0.4)
        self.fc = nn.Sequential(
            nn.Linear(256 * 4 * 3, 256),
            nn.ReLU(inplace=True),
            nn.Dropout(0.3),
            nn.Linear(256, NUM_CLASSES),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = self.net(x).flatten(1)
        h = self.drop(h)
        return self.fc(h)


def pick_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def to_tensor(bgr: np.ndarray) -> torch.Tensor:
    """Same normalization as kapcha/train/digit_train.py (ImageNet mean/std)."""
    rgb = bgr[:, :, ::-1].astype(np.float32) / 255.0
    t = torch.from_numpy(np.ascontiguousarray(rgb)).permute(2, 0, 1)
    mean = torch.tensor([0.485, 0.456, 0.406], dtype=t.dtype).view(3, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225], dtype=t.dtype).view(3, 1, 1)
    return (t - mean) / std


def load_model(ckpt_path: Path, device: torch.device) -> DigitCNN:
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    model = DigitCNN().to(device)
    state = ckpt["model"] if isinstance(ckpt, dict) and "model" in ckpt else ckpt
    model.load_state_dict(state)
    model.eval()
    return model


def _shift_bgr(bgr: np.ndarray, dx: int, dy: int) -> np.ndarray:
    h, w = bgr.shape[:2]
    m = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(
        bgr,
        m,
        (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )


def _brightness_bgr(bgr: np.ndarray, delta: int) -> np.ndarray:
    out = bgr.astype(np.int16) + int(delta)
    return np.clip(out, 0, 255).astype(np.uint8)


def _tta_views(bgr: np.ndarray) -> list[np.ndarray]:
    """Identity + ±2px shift (keep cheap; brightness rarely helps)."""
    return [bgr, _shift_bgr(bgr, 2, 0), _shift_bgr(bgr, -2, 0)]


@torch.no_grad()
def predict_bgr(
    model: DigitCNN,
    bgr: np.ndarray,
    device: torch.device,
    *,
    tta: bool = True,
) -> tuple[str, list[float]]:
    """Predict 5 digits; conf per digit from (optional) TTA-averaged softmax."""
    views = _tta_views(bgr) if tta else [bgr]
    prob_sum: torch.Tensor | None = None
    n_views = 0
    for view in views:
        crops = extract_digit_crops(view, None, crop_w=CROP_W, crop_h=CROP_H)
        xs = torch.stack([to_tensor(c) for c, _ in crops]).to(device)
        logits = model(xs)
        probs = F.softmax(logits, dim=1)
        prob_sum = probs if prob_sum is None else prob_sum + probs
        n_views += 1
    assert prob_sum is not None and n_views > 0
    avg = prob_sum / n_views
    pred_ids = avg.argmax(dim=1).tolist()
    conf = avg.max(dim=1).values.tolist()
    return "".join(str(d) for d in pred_ids), [float(c) for c in conf]


def predict_png_bytes(
    model: DigitCNN,
    png_bytes: bytes,
    device: torch.device,
    *,
    tta: bool = True,
) -> tuple[str, list[float]]:
    arr = np.frombuffer(png_bytes, dtype=np.uint8)
    bgr = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
    if bgr is None:
        raise ValueError("invalid png")
    if bgr.ndim == 2:
        bgr = cv2.cvtColor(bgr, cv2.COLOR_GRAY2BGR)
    elif bgr.shape[2] == 4:
        bgr = bgr[:, :, :3]
    return predict_bgr(model, bgr, device, tta=tta)


def predict_path(
    model: DigitCNN,
    path: Path,
    device: torch.device,
    *,
    tta: bool = True,
) -> tuple[str, list[float]]:
    return predict_bgr(model, load_bgr(path), device, tta=tta)
