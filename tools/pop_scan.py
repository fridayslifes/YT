#!/usr/bin/env python3
"""tools/pop_scan.py — Frame-to-Frame Pop Scanner & Contact Sheet Pre-Render QA.

Based on Danny Why's cutout-cartoon-shorts skill (§10):
1. Ingests video or preview MP4.
2. Computes mean frame-to-frame difference on downsampled, blurred frames (270x480).
3. Calculates rolling median over a sliding temporal window (e.g., 30 frames).
4. Flags frames exceeding 2.2x the local median to identify visual pops, cuts, or glitches.
5. Generates a multi-frame contact sheet grid at key beat intervals.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("pop_scan")


def scan_video_for_pops(
    video_path: Path,
    threshold_ratio: float = 2.2,
    window_size: int = 31,
    min_diff_floor: float = 2.5,
) -> Tuple[List[Dict], List[float]]:
    """Scans video for unintended frame-to-frame pops or jumps exceeding threshold_ratio x local median."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    logger.info(f"Scanning {video_path.name} ({total_frames} frames @ {fps:.1f} fps)...")

    diffs: List[float] = [0.0]
    prev_gray: Optional[np.ndarray] = None

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Downsample to 270x480 (or 480x270 for landscape) and blur
        small = cv2.resize(frame, (480, 270), interpolation=cv2.INTER_AREA)
        blurred = cv2.GaussianBlur(small, (5, 5), 0)
        gray = cv2.cvtColor(blurred, cv2.COLOR_BGR2GRAY)

        if prev_gray is not None:
            # Mean L1 absolute difference
            diff = float(np.mean(cv2.absdiff(gray, prev_gray)))
            diffs.append(diff)
        prev_gray = gray

    cap.release()

    # Calculate rolling median
    n = len(diffs)
    half_w = window_size // 2
    medians = np.zeros(n, dtype=np.float32)
    diffs_arr = np.array(diffs, dtype=np.float32)

    for i in range(n):
        w_start = max(0, i - half_w)
        w_end = min(n, i + half_w + 1)
        medians[i] = float(np.median(diffs_arr[w_start:w_end]))

    # Flag spikes
    flags: List[Dict] = []
    in_spike = False
    spike_peak_idx = 0
    spike_peak_diff = 0.0

    for i in range(1, n):
        med = max(0.5, medians[i])
        ratio = diffs[i] / med
        if ratio >= threshold_ratio and diffs[i] >= min_diff_floor:
            if not in_spike:
                in_spike = True
                spike_peak_idx = i
                spike_peak_diff = diffs[i]
            else:
                if diffs[i] > spike_peak_diff:
                    spike_peak_idx = i
                    spike_peak_diff = diffs[i]
        else:
            if in_spike:
                sec = spike_peak_idx / fps
                med_val = max(0.5, medians[spike_peak_idx])
                flags.append({
                    "frame": spike_peak_idx,
                    "time_sec": round(sec, 3),
                    "timecode": f"{int(sec // 60):02d}:{sec % 60:05.2f}",
                    "diff": round(spike_peak_diff, 2),
                    "local_median": round(float(med_val), 2),
                    "ratio": round(float(spike_peak_diff / med_val), 2),
                })
                in_spike = False

    if in_spike:
        sec = spike_peak_idx / fps
        med_val = max(0.5, medians[spike_peak_idx])
        flags.append({
            "frame": spike_peak_idx,
            "time_sec": round(sec, 3),
            "timecode": f"{int(sec // 60):02d}:{sec % 60:05.2f}",
            "diff": round(spike_peak_diff, 2),
            "local_median": round(float(med_val), 2),
            "ratio": round(float(spike_peak_diff / med_val), 2),
        })

    logger.info(f"Scan complete: {len(flags)} visual transitions / spikes detected.")
    return flags, diffs


def generate_contact_sheet(
    video_path: Path,
    timestamps: List[float],
    output_image: Path,
    cols: int = 4,
    thumb_w: int = 360,
    thumb_h: int = 202,
) -> Path:
    """Extracts frames at specific timestamps and packs them into a clean contact sheet grid."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video: {video_path}")

    thumbs: List[np.ndarray] = []
    for t in timestamps:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ret, frame = cap.read()
        if not ret:
            frame = np.zeros((thumb_h, thumb_w, 3), dtype=np.uint8)
        else:
            frame = cv2.resize(frame, (thumb_w, thumb_h), interpolation=cv2.INTER_AREA)

        # Overlay timecode
        tc = f"{int(t // 60):02d}:{t % 60:04.1f}"
        cv2.rectangle(frame, (4, thumb_h - 24), (85, thumb_h - 4), (0, 0, 0), -1)
        cv2.putText(frame, tc, (8, thumb_h - 9), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 229, 255), 1, cv2.LINE_AA)
        thumbs.append(frame)

    cap.release()

    rows = int(np.ceil(len(thumbs) / float(cols)))
    grid_h = rows * thumb_h
    grid_w = cols * thumb_w
    grid = np.zeros((grid_h, grid_w, 3), dtype=np.uint8)

    for idx, th in enumerate(thumbs):
        r = idx // cols
        c = idx % cols
        grid[r * thumb_h:(r + 1) * thumb_h, c * thumb_w:(c + 1) * thumb_w] = th

    output_image.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_image), grid)
    logger.info(f"✓ Contact sheet written: {output_image} ({len(thumbs)} frames, {grid_w}x{grid_h})")
    return output_image


def main() -> int:
    parser = argparse.ArgumentParser(description="Danny Why Pop Scanner (§10)")
    parser.add_argument("video", type=Path, help="Input MP4 video file")
    parser.add_argument("--threshold", type=float, default=2.2, help="Ratio above median to flag")
    parser.add_argument("--contact-sheet", type=Path, default=None, help="Generate contact sheet path")
    parser.add_argument("--sheet-interval", type=float, default=15.0, help="Interval in seconds for contact sheet")
    args = parser.parse_args()

    flags, _ = scan_video_for_pops(args.video, threshold_ratio=args.threshold)
    print("\nVisual Transitions / Pop Scan Results:")
    for f in flags:
        print(f"  • Frame {f['frame']} ({f['timecode']}): diff={f['diff']:.1f} (ratio={f['ratio']:.1f}x median)")

    if args.contact_sheet:
        cap = cv2.VideoCapture(str(args.video))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        dur = n_frames / fps
        times = list(np.arange(0.5, dur, args.sheet_interval))
        generate_contact_sheet(args.video, times, args.contact_sheet)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
