"""Captcha foreground cleanup + 5-digit crop helpers (v3).

1) soft ink (bg wipe)
2) inpaint thin linear/circular noise (blackhat ∩ thin ink + conservative rings)
3) thickness keep
4) 5 crops + per-crop enhance
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

DIGITS = 5


def load_bgr(path: Path | str) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(path)
    if img.ndim == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.shape[2] == 4:
        return img[:, :, :3]
    return img


def soft_ink_mask(bgr: np.ndarray) -> np.ndarray:
    blur = cv2.medianBlur(bgr, 3)
    hsv = cv2.cvtColor(blur, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(blur, cv2.COLOR_BGR2LAB)
    s = hsv[:, :, 1].astype(np.int32)
    a = lab[:, :, 1].astype(np.float32)
    bb = lab[:, :, 2].astype(np.float32)
    chroma = np.sqrt((a - 128.0) ** 2 + (bb - 128.0) ** 2)
    dist = np.linalg.norm(blur.astype(np.float32) - 255.0, axis=2)
    raw = ((s > 18) & (dist > 22)) | (chroma > 12) | (dist > 45)
    m = (raw.astype(np.uint8)) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((2, 2), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2)))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    keep = np.zeros_like(m)
    h, w = m.shape
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        if area < 25:
            continue
        if area > 0.85 * h * w:
            continue
        keep[labels == i] = 255
    return keep


def _linear_blackhat(gray: np.ndarray) -> np.ndarray:
    acc = np.zeros_like(gray, np.float32)
    for ang in range(0, 180, 10):
        canvas = np.zeros((21, 21), np.uint8)
        cv2.line(canvas, (10, 1), (10, 19), 1, 1)
        M = cv2.getRotationMatrix2D((10, 10), ang, 1.0)
        rot = cv2.warpAffine(canvas, M, (21, 21))
        rot = (rot > 0).astype(np.uint8)
        if rot.sum() < 4:
            continue
        bh = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, rot)
        acc = np.maximum(acc, bh.astype(np.float32))
    return np.clip(acc, 0, 255).astype(np.uint8)


def thin_noise_mask(bgr: np.ndarray) -> np.ndarray:
    """Mask of thin linear/circular noise safe-ish to inpaint."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    ink = soft_ink_mask(bgr)
    dist = cv2.distanceTransform(ink, cv2.DIST_L2, 5)
    bh = _linear_blackhat(gray)
    thin = ((bh >= 28) & (ink > 0) & (dist <= 2.0)).astype(np.uint8) * 255
    circ = cv2.HoughCircles(
        cv2.GaussianBlur(gray, (9, 9), 0),
        cv2.HOUGH_GRADIENT,
        dp=1.5,
        minDist=50,
        param1=110,
        param2=50,
        minRadius=16,
        maxRadius=70,
    )
    if circ is not None:
        for x, y, r in np.round(circ[0]).astype(int):
            ring = np.zeros_like(thin)
            cv2.circle(ring, (x, y), int(r), 255, 2)
            ring = cv2.bitwise_and(ring, ((dist <= 2.2) & (ink > 0)).astype(np.uint8) * 255)
            thin = cv2.bitwise_or(thin, ring)
    return thin


def thickness_boost(mask: np.ndarray) -> np.ndarray:
    if mask.max() == 0:
        return mask
    dist = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    core = (dist >= 0.9).astype(np.uint8) * 255
    core = cv2.dilate(core, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)), iterations=1)
    out = cv2.bitwise_and(mask, core)
    if (out > 0).mean() < 0.025:
        return mask
    return cv2.morphologyEx(out, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))


def ink_mask(bgr: np.ndarray) -> np.ndarray:
    return thickness_boost(soft_ink_mask(bgr))


def clean_captcha_bgr(bgr: np.ndarray) -> np.ndarray:
    geom = thin_noise_mask(bgr)
    work = cv2.inpaint(bgr, geom, 3, cv2.INPAINT_TELEA) if geom.max() else bgr.copy()
    mask = ink_mask(work)
    out = np.full_like(work, 255)
    out[mask > 0] = work[mask > 0]
    return out


def clean_captcha_pil(image: Image.Image) -> Image.Image:
    rgb = np.array(image.convert("RGB"))
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    cleaned = clean_captcha_bgr(bgr)
    return Image.fromarray(cv2.cvtColor(cleaned, cv2.COLOR_BGR2RGB))


def enhance_crop(bgr: np.ndarray) -> np.ndarray:
    if bgr.size == 0:
        return bgr
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    dist = np.linalg.norm(bgr.astype(np.float32) - 255.0, axis=2)
    s = hsv[:, :, 1]
    a = lab[:, :, 1].astype(np.float32)
    bb = lab[:, :, 2].astype(np.float32)
    chroma = np.sqrt((a - 128.0) ** 2 + (bb - 128.0) ** 2)
    keep = ((dist > 28) & ((s > 20) | (chroma > 12) | (dist > 55))).astype(np.uint8) * 255
    keep = cv2.morphologyEx(keep, cv2.MORPH_CLOSE, np.ones((2, 2), np.uint8))
    out = np.full_like(bgr, 255)
    out[keep > 0] = bgr[keep > 0]
    lab2 = cv2.cvtColor(out, cv2.COLOR_BGR2LAB)
    l, aa, bb2 = cv2.split(lab2)
    l2 = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4)).apply(l)
    out = cv2.cvtColor(cv2.merge([l2, aa, bb2]), cv2.COLOR_LAB2BGR)
    out[keep == 0] = (255, 255, 255)
    return out


def digit_centers(mask: np.ndarray) -> tuple[int, int, list[int]]:
    h, w = mask.shape
    row = (mask > 0).sum(axis=1)
    if row.max() <= 0:
        return 0, h, [w * (2 * i + 1) // (2 * DIGITS) for i in range(DIGITS)]
    thr = max(1, int(row.max() * 0.10))
    ys = np.where(row >= thr)[0]
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    band = mask[y0:y1]
    col = (band > 0).sum(axis=0).astype(np.float32)
    if col.sum() < 10:
        return y0, y1, [w * (2 * i + 1) // (2 * DIGITS) for i in range(DIGITS)]
    col = cv2.GaussianBlur(col.reshape(1, -1), (1, 41), 0).ravel()
    total = float(col.sum())
    csum = np.cumsum(col)
    centers: list[int] = []
    for i in range(DIGITS):
        target = total * (i + 0.5) / DIGITS
        centers.append(int(np.searchsorted(csum, target)))
    if max(centers) - min(centers) < w * 0.35:
        centers = [w * (2 * i + 1) // (2 * DIGITS) for i in range(DIGITS)]
    return y0, y1, centers


def extract_digit_crops(
    bgr: np.ndarray,
    label: str | None = None,
    crop_w: int = 96,
    crop_h: int = 128,
) -> list[tuple[np.ndarray, str | None]]:
    cleaned = clean_captcha_bgr(bgr)
    mask = ink_mask(cleaned)
    if (mask > 0).mean() < 0.02:
        mask = soft_ink_mask(bgr)
        cleaned = bgr
    y0, y1, centers = digit_centers(mask)
    h, w = cleaned.shape[:2]
    half = max(crop_w // 2, w // 11)
    crops: list[tuple[np.ndarray, str | None]] = []
    band = cleaned[max(0, y0 - 6) : min(h, y1 + 6)]
    for i, cx in enumerate(centers):
        x0 = max(0, cx - half)
        x1 = min(w, cx + half)
        patch = band[:, x0:x1]
        if patch.size == 0:
            patch = np.full((crop_h, crop_w, 3), 255, np.uint8)
        patch = enhance_crop(patch)
        patch = cv2.resize(patch, (crop_w, crop_h), interpolation=cv2.INTER_AREA)
        dig = label[i] if label and i < len(label) else None
        crops.append((patch, dig))
    return crops


def predict_string_from_crops(digit_ids: list[int]) -> str:
    return "".join(str(d) for d in digit_ids)
