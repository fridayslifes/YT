#!/usr/bin/env python3
"""tools/sprite_aligner.py — Automated Sprite Prep & Normalization Engine.

Based on Danny Why's cutout-cartoon-shorts skill (§4):
1. Hole-fills silhouette mask and applies Euclidean Distance Transform (cv2.DIST_L2)
   to find the largest inscribed disc (the head radius and center).
2. Rescales all character poses to match a uniform target head radius (zero size pops).
3. Locates feet ground anchor in bottom 3.5% of opaque rows (zero vertical float).
4. Aligns edited pose pairs via ECC affine registration (cv2.findTransformECC).
5. Trims alpha bounding box + 12px margin.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sprite_aligner")


def trim_alpha_box(img_rgba: np.ndarray, margin: int = 12) -> Tuple[np.ndarray, Tuple[int, int, int, int]]:
    """Trims an RGBA image to its non-zero alpha bounding box with padding."""
    if img_rgba.shape[2] < 4:
        raise ValueError("Image must have an alpha channel (RGBA)")

    alpha = img_rgba[:, :, 3]
    coords = cv2.findNonZero((alpha > 10).astype(np.uint8))
    if coords is None:
        return img_rgba, (0, 0, img_rgba.shape[1], img_rgba.shape[0])

    x, y, w, h = cv2.boundingRect(coords)
    h_img, w_img = img_rgba.shape[:2]

    x1 = max(0, x - margin)
    y1 = max(0, y - margin)
    x2 = min(w_img, x + w + margin)
    y2 = min(h_img, y + h + margin)

    return img_rgba[y1:y2, x1:x2].copy(), (x1, y1, x2 - x1, y2 - y1)


def detect_head_disc(img_rgba: np.ndarray) -> Tuple[int, int, float]:
    """Detects head center (hx, hy) and radius via hole-filled Euclidean Distance Transform."""
    alpha = img_rgba[:, :, 3]
    h, w = alpha.shape[:2]

    a8 = (alpha > 128).astype(np.uint8)
    ff = a8.copy()
    mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
    cv2.floodFill(ff, mask, (0, 0), 2)
    solid = np.where(ff == 2, 0, 1).astype(np.uint8)

    dt = cv2.distanceTransform(solid, cv2.DIST_L2, 5)
    hy, hx = np.unravel_index(dt.argmax(), dt.shape)
    head_radius = float(dt[hy, hx])

    return int(hx), int(hy), head_radius


def detect_feet_anchor(img_rgba: np.ndarray) -> Tuple[int, int]:
    """Finds world feet anchor point in the bottom 3.5% of opaque rows."""
    alpha = img_rgba[:, :, 3]
    h, w = alpha.shape[:2]

    opaque_rows = np.where(np.any(alpha > 128, axis=1))[0]
    if len(opaque_rows) == 0:
        return w // 2, h

    min_y = opaque_rows[0]
    max_y = opaque_rows[-1]
    total_h = max_y - min_y

    threshold_y = max_y - max(1, int(total_h * 0.035))
    foot_pts = np.where(alpha[threshold_y:max_y + 1, :] > 128)

    if len(foot_pts[1]) > 0:
        fx = int(np.mean(foot_pts[1]))
        fy = int(max_y)
    else:
        fx = w // 2
        fy = int(max_y)

    return fx, fy


def align_pose_pair_ecc(
    img_a: np.ndarray,
    img_b: np.ndarray,
    head_mask_radius_multiplier: float = 1.3,
) -> Tuple[np.ndarray, np.ndarray]:
    """Calculates ECC affine warp to perfectly align pose B's head to pose A."""
    hx_a, hy_a, r_a = detect_head_disc(img_a)

    gray_a = cv2.cvtColor(img_a, cv2.COLOR_RGBA2GRAY)
    gray_b = cv2.cvtColor(img_b, cv2.COLOR_RGBA2GRAY)

    h, w = gray_a.shape[:2]
    head_mask = np.zeros((h, w), dtype=np.uint8)
    cv2.circle(head_mask, (hx_a, hy_a), int(r_a * head_mask_radius_multiplier), 255, -1)

    warp = np.eye(2, 3, dtype=np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 500, 1e-6)

    try:
        _, warp = cv2.findTransformECC(gray_b, gray_a, warp, cv2.MOTION_AFFINE, criteria, head_mask, 5)
    except cv2.error as exc:
        logger.warning(f"ECC alignment failed to converge: {exc}; using identity.")
        warp = np.eye(2, 3, dtype=np.float32)

    aligned_b = cv2.warpAffine(img_b, warp, (w, h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_CONSTANT)
    return aligned_b, warp


def normalize_sprite_set(
    input_paths: List[Path],
    output_dir: Path,
    target_head_radius: Optional[float] = None,
) -> Dict[str, Dict]:
    """Normalizes an entire character pose set: trims, rescales to uniform head size, and anchors feet."""
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {}

    loaded = []
    head_radii = []

    for p in input_paths:
        img = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
        if img is None:
            continue
        if img.shape[2] == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
        trimmed, bbox = trim_alpha_box(img, margin=14)
        hx, hy, r = detect_head_disc(trimmed)
        loaded.append({"path": p, "img": trimmed, "hx": hx, "hy": hy, "r": r, "bbox": bbox})
        head_radii.append(r)

    if not loaded:
        return {}

    median_r = target_head_radius if target_head_radius is not None else float(np.median(head_radii))
    logger.info(f"Target uniform head radius: {median_r:.1f}px (from {len(loaded)} poses)")

    for item in loaded:
        scale = median_r / max(1.0, item["r"])
        img = item["img"]
        new_w = max(1, int(img.shape[1] * scale))
        new_h = max(1, int(img.shape[0] * scale))
        rescaled = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

        hx = int(item["hx"] * scale)
        hy = int(item["hy"] * scale)
        fx, fy = detect_feet_anchor(rescaled)

        out_path = output_dir / item["path"].name
        cv2.imwrite(str(out_path), rescaled)

        manifest[item["path"].stem] = {
            "file": str(out_path),
            "width": new_w,
            "height": new_h,
            "head_center": [hx, hy],
            "head_radius": round(median_r, 1),
            "feet_anchor": [fx, fy],
            "scale_factor": round(scale, 4),
        }
        logger.info(f"  ✓ Normalized {item['path'].name}: {new_w}x{new_h} | scale: {scale:.3f} | feet: ({fx}, {fy})")

    manifest_path = output_dir / "sprites_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Danny Why Sprite Normalizer (§4)")
    parser.add_argument("inputs", nargs="+", help="Input sprite PNGs")
    parser.add_argument("--out-dir", type=Path, default=Path("public/sprites"), help="Output directory")
    parser.add_argument("--target-radius", type=float, default=None, help="Target head radius (defaults to median)")
    args = parser.parse_args()

    files = [Path(p) for p in args.inputs]
    normalize_sprite_set(files, args.out_dir, target_head_radius=args.target_radius)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
