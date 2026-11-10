#!/usr/bin/env python3
"""FrameForge Cinematic Photobook Parallax Engine (tools/photobook_engine.py).

Deconstructs and renders documentary-style 3D multi-plane parallax scenes
inspired by MagnatesMedia, LEMMiNO, and Aperture:

Core Architectural Features:
  1. Multi-Plane Z-Space Composition:
     - Far Plane (Z-Far, ~3,000px): Inpainted environment / sky, moves slowly, scaled up to prevent edge clip.
     - Mid Plane (Z-Mid, ~1,000px): Primary hero subject (portrait, architecture, archival document).
     - Near Plane (Z-Near, ~200px): Foreground occluders (window frames, silhouetted branches, dust/rain).
  2. Smooth S-Curve Camera Trajectories (After Effects F9 Cubic Easing):
     - `magnates_drift`: Lateral tracking with subtle continuous push-in and foreground whip.
     - `lemmino_reveal`: Low-angle slow dolly-in with elevation shift and chiaroscuro lighting.
     - `archival_zoom`: Subtle documentary Ken Burns push-in with micro-rotation (0.5-1.0 deg).
     - `vertigo_reveal`: Hitchcock dolly-zoom (camera pushes while field-of-view widens).
  3. Archival 35mm Color Grading & Film Chemistry:
     - `magnates_amber`: High-contrast warm tungsten amber and deep rich shadows.
     - `lemmino_noir`: Moody deep cyan/navy shadows, desaturated midtones, silver highlights.
     - `archival_sepia`: 19th-century historical parchment tint with aged paper contrast.
     - `portra_35mm`: Kodak Portra 400 photorealism, soft highlight roll-off.
  4. Organic Film Effects:
     - Per-frame procedural 35mm film grain.
     - Optical cosine-fourth lens vignetting.
     - Volumetric floating dust motes with independent 1/Z parallax drift.
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np

from tools.errors import RenderingError

# ---------------------------------------------------------------------------
# COLOR PROFILES & FILM GRADES
# ---------------------------------------------------------------------------

STYLE_GRADES: Dict[str, Dict[str, Tuple[float, float, float]]] = {
    "magnates_amber": {
        "shadows": (0.85, 0.90, 1.05),     # Deep warm navy/sepia shadows (BGR)
        "midtones": (0.90, 1.08, 1.25),    # Rich amber/orange midtones
        "highlights": (0.95, 1.15, 1.30),  # Golden tungsten glow
    },
    "lemmino_noir": {
        "shadows": (1.15, 1.05, 0.85),     # Moody deep cyan/navy shadows
        "midtones": (0.98, 0.98, 0.95),    # Desaturated cool midtones
        "highlights": (1.10, 1.05, 0.98),  # Silver highlights
    },
    "archival_sepia": {
        "shadows": (0.75, 0.85, 0.95),     # Warm aged paper shadows
        "midtones": (0.80, 0.95, 1.15),    # Vintage sepia parchment
        "highlights": (0.88, 1.02, 1.20),  # Soft warm cream highlights
    },
    "portra_35mm": {
        "shadows": (0.95, 0.97, 1.02),     # Clean Kodak Portra 400 base
        "midtones": (1.00, 1.02, 1.05),    # Balanced natural skin warmth
        "highlights": (0.98, 1.03, 1.06),  # Soft highlight roll-off
    },
}

TRAJECTORY_PRESETS: List[str] = [
    "magnates_drift",
    "lemmino_reveal",
    "archival_zoom",
    "vertigo_reveal",
]


# ---------------------------------------------------------------------------
# DATA STRUCTURES
# ---------------------------------------------------------------------------

@dataclass
class PhotobookLayer:
    """Represents a discrete plane in the 3D parallax stack."""
    image: np.ndarray          # BGR or BGRA numpy array
    z_depth: float             # Virtual distance along Z axis (e.g. 200 = near, 1000 = mid, 3000 = far)
    scale: float = 1.0         # Baseline scaling factor
    offset_x: float = 0.0      # Base horizontal offset (pixels)
    offset_y: float = 0.0      # Base vertical offset (pixels)
    is_foreground: bool = False
    is_background: bool = False


# ---------------------------------------------------------------------------
# PROCEDURAL FILM CHEMISTRY (GRAIN, VIGNETTE, VOLUMETRIC DUST)
# ---------------------------------------------------------------------------

def apply_optical_vignette(img: np.ndarray, strength: float = 0.45) -> np.ndarray:
    """Applies a smooth cosine-fourth optical lens falloff vignette."""
    h, w = img.shape[:2]
    cx, cy = w / 2.0, h / 2.0
    max_radius = math.hypot(cx, cy)

    y_coords, x_coords = np.ogrid[:h, :w]
    distances = np.hypot(x_coords - cx, y_coords - cy) / max_radius
    # Smoothstep cosine-like falloff
    vignette = 1.0 - strength * (distances ** 2.2)
    vignette = np.clip(vignette, 0.0, 1.0)[..., None]
    return (img.astype(np.float32) * vignette).astype(np.uint8)


def generate_film_grain(h: int, w: int, intensity: float = 12.0) -> np.ndarray:
    """Generates 35mm organic Gaussian film grain with middle-grey distribution."""
    grain = np.random.normal(0.0, intensity, (h, w, 1)).astype(np.float32)
    return grain


def apply_color_grade(img: np.ndarray, style: str) -> np.ndarray:
    """Applies authentic 3-way color grading (shadows, midtones, highlights)."""
    if style not in STYLE_GRADES:
        return img

    palette = STYLE_GRADES[style]
    img_f = img.astype(np.float32) / 255.0
    luminance = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    luminance = luminance[..., None]

    # Split into 3 tonal bands
    shadow_weight = np.clip(1.0 - luminance * 2.0, 0.0, 1.0)
    highlight_weight = np.clip((luminance - 0.5) * 2.0, 0.0, 1.0)
    midtone_weight = np.clip(1.0 - shadow_weight - highlight_weight, 0.0, 1.0)

    sh_mult = np.array(palette["shadows"], dtype=np.float32)
    mid_mult = np.array(palette["midtones"], dtype=np.float32)
    hi_mult = np.array(palette["highlights"], dtype=np.float32)

    grade = (
        img_f * shadow_weight * sh_mult
        + img_f * midtone_weight * mid_mult
        + img_f * highlight_weight * hi_mult
    )
    return np.clip(grade * 255.0, 0.0, 255.0).astype(np.uint8)


# ---------------------------------------------------------------------------
# S-CURVE EASING & TRAJECTORY CALCULATOR
# ---------------------------------------------------------------------------

def s_curve_ease(t: float) -> float:
    """Smoothstep quintic S-curve easing (After Effects F9 smooth curve)."""
    t_clamped = max(0.0, min(1.0, t))
    return t_clamped * t_clamped * t_clamped * (t_clamped * (t_clamped * 6.0 - 15.0) + 10.0)


def compute_camera_transform(
    preset: str,
    progress: float,
    z_depth: float,
    reference_z: float = 1000.0,
) -> Tuple[float, float, float, float]:
    """Computes (pan_x, pan_y, scale_delta, rotation_deg) for a given plane depth."""
    # Parallax speed multiplier: Closer layers (low Z) move faster than distant layers (high Z)
    parallax_factor = reference_z / max(100.0, z_depth)
    e = s_curve_ease(progress)

    pan_x = 0.0
    pan_y = 0.0
    zoom = 1.0
    rot = 0.0

    if preset == "magnates_drift":
        # Slow lateral pan to the left, subject drifts right, subtle push-in
        pan_x = (e - 0.5) * 120.0 * parallax_factor
        pan_y = (math.sin(e * math.pi) - 0.5) * 15.0 * parallax_factor
        zoom = 1.0 + (e * 0.08 * parallax_factor)
        rot = (e - 0.5) * 0.6

    elif preset == "lemmino_reveal":
        # Dramatic low-angle push-in with rising elevation
        pan_x = (math.cos(e * math.pi * 0.5) - 1.0) * 40.0 * parallax_factor
        pan_y = (1.0 - e) * 80.0 * parallax_factor
        zoom = 1.0 + (e * 0.12 * parallax_factor)
        rot = (0.5 - e) * 0.4

    elif preset == "archival_zoom":
        # Classic slow documentary Ken Burns push-in
        pan_x = (e - 0.5) * 35.0 * parallax_factor
        pan_y = (e - 0.5) * 20.0 * parallax_factor
        zoom = 1.0 + (e * 0.06 * parallax_factor)
        rot = 0.0

    elif preset == "vertigo_reveal":
        # Hitchcock Dolly-Zoom: Camera pushes in while background compresses
        if z_depth > reference_z:
            # Background expands faster
            zoom = 1.0 + (e * 0.18 * parallax_factor)
        else:
            # Foreground zooms gently
            zoom = 1.0 + (e * 0.04 * parallax_factor)
        pan_x = (e - 0.5) * 25.0 * parallax_factor
        pan_y = (e - 0.5) * 10.0 * parallax_factor
        rot = (e - 0.5) * 0.5

    else:
        # Default gentle push
        zoom = 1.0 + (e * 0.05 * parallax_factor)

    return pan_x, pan_y, zoom, rot


# ---------------------------------------------------------------------------
# AUTOMATIC LAYER DECOMPOSITION (FOR SINGLE-IMAGE INPUT)
# ---------------------------------------------------------------------------

def decompose_single_image(src_bgr: np.ndarray, target_w: int, target_h: int) -> List[PhotobookLayer]:
    """Decomposes a single 2D image into 3 distinct parallax planes.

    Far Plane: Inpainted/blurred extended environment plate (Z=3000).
    Mid Plane: Sharp focal subject with soft feathered alpha (Z=1000).
    Near Plane: Contextual foreground framing silhouette/vignette (Z=200).
    """
    h_orig, w_orig = src_bgr.shape[:2]

    # Resize to target aspect
    resized_bgr = cv2.resize(src_bgr, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)

    # 1. Background Plane (Z=3000): Extended and slightly softened
    bg_plate = cv2.resize(resized_bgr, (int(target_w * 1.30), int(target_h * 1.30)), interpolation=cv2.INTER_LINEAR)
    # Slight blur to push it into the distance
    bg_plate = cv2.GaussianBlur(bg_plate, (7, 7), 2.0)
    bg_layer = PhotobookLayer(image=bg_plate, z_depth=3000.0, scale=1.0, is_background=True)

    # 2. Midground Subject Plane (Z=1000): Central subject with soft radial alpha
    # Build feathered elliptical alpha mask centered on upper-middle third (safe zone)
    mask = np.zeros((target_h, target_w), dtype=np.float32)
    center_x, center_y = target_w // 2, int(target_h * 0.44)
    axis_x, axis_y = int(target_w * 0.42), int(target_h * 0.40)
    cv2.ellipse(mask, (center_x, center_y), (axis_x, axis_y), 0, 0, 360, 1.0, -1)
    mask = cv2.GaussianBlur(mask, (101, 101), 45.0)

    # Combine BGR + Alpha
    b, g, r = cv2.split(resized_bgr)
    a = (mask * 255.0).astype(np.uint8)
    mid_bgra = cv2.merge([b, g, r, a])
    mid_layer = PhotobookLayer(image=mid_bgra, z_depth=1000.0, scale=1.0)

    # 3. Foreground Near Plane (Z=200): Subtle cinematic corner framing vignette
    fg_mask = np.zeros((target_h, target_w, 4), dtype=np.uint8)
    # Dark corner occlusion
    cv2.circle(fg_mask, (0, 0), int(target_w * 0.45), (10, 12, 18, 160), -1)
    cv2.circle(fg_mask, (target_w, 0), int(target_w * 0.35), (10, 12, 18, 130), -1)
    fg_mask = cv2.GaussianBlur(fg_mask, (121, 121), 60.0)
    fg_layer = PhotobookLayer(image=fg_mask, z_depth=200.0, scale=1.0, is_foreground=True)

    return [bg_layer, mid_layer, fg_layer]


# ---------------------------------------------------------------------------
# CORE COMPOSITOR & VIDEO RENDERER
# ---------------------------------------------------------------------------

def render_photobook_scene(
    layers: List[PhotobookLayer],
    output_path: Path,
    style: str = "magnates_amber",
    trajectory: str = "magnates_drift",
    duration: float = 3.5,
    fps: int = 30,
    width: int = 1080,
    height: int = 1920,
) -> bool:
    """Renders a multi-plane 3D parallax photobook scene to MP4."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    width = (width // 2) * 2
    height = (height // 2) * 2
    num_frames = int(round(duration * fps))

    # Initialize video writer via ffmpeg pipe or OpenCV VideoWriter
    tmp_raw_mp4 = output_path.with_suffix(".raw.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(tmp_raw_mp4), fourcc, float(fps), (width, height))

    if not writer.isOpened():
        raise RuntimeError(f"Failed to open video writer for {tmp_raw_mp4}")

    try:
        # Pre-generate floating dust particle coordinates
        num_dust = 35
        dust_x = np.random.uniform(0, width, num_dust)
        dust_y = np.random.uniform(0, height, num_dust)
        dust_z = np.random.uniform(150, 2500, num_dust)
        dust_speed = np.random.uniform(0.3, 1.2, num_dust)

        # Precompute vignette mask, pre-graded layers, and rolled 35mm grain buffer once per clip
        cx_v, cy_v = width / 2.0, height / 2.0
        max_rad = math.hypot(cx_v, cy_v)
        y_c, x_c = np.ogrid[:height, :width]
        dist_v = np.hypot(x_c - cx_v, y_c - cy_v) / max_rad
        vignette_mask = np.clip(1.0 - 0.38 * (dist_v ** 2.2), 0.0, 1.0).astype(np.float32)[..., None]

        sorted_layers = []
        for lyr in sorted(layers, key=lambda item: item.z_depth, reverse=True):
            img_src = lyr.image
            if img_src.shape[2] == 4:
                graded_bgr = apply_color_grade(img_src[:, :, :3], style)
                graded_img = np.dstack([graded_bgr, img_src[:, :, 3]])
            else:
                graded_img = apply_color_grade(img_src, style)
            sorted_layers.append(
                PhotobookLayer(
                    image=graded_img,
                    z_depth=lyr.z_depth,
                    scale=lyr.scale,
                    offset_x=lyr.offset_x,
                    offset_y=lyr.offset_y,
                    is_foreground=lyr.is_foreground,
                    is_background=lyr.is_background,
                )
            )

        grain_base = np.random.normal(0.0, 10.0, (height, width)).astype(np.int16)

        for frame_idx in range(num_frames):
            p = frame_idx / max(1, num_frames - 1)
            frame_canvas = np.zeros((height, width, 3), dtype=np.uint8)

            for layer in sorted_layers:
                pan_x, pan_y, zoom, rot = compute_camera_transform(trajectory, p, layer.z_depth)
                total_scale = layer.scale * zoom

                img = layer.image
                lh, lw = img.shape[:2]
                cx, cy = lw / 2.0, lh / 2.0

                M = cv2.getRotationMatrix2D((cx, cy), rot, total_scale)
                M[0, 2] += (width / 2.0 - cx) + pan_x + layer.offset_x
                M[1, 2] += (height / 2.0 - cy) + pan_y + layer.offset_y

                if img.shape[2] == 4:
                    warped = cv2.warpAffine(
                        img, M, (width, height),
                        flags=cv2.INTER_LINEAR,
                        borderMode=cv2.BORDER_CONSTANT,
                        borderValue=(0, 0, 0, 0),
                    )
                    bgr_plane = warped[:, :, :3].astype(np.uint16)
                    alpha_u16 = warped[:, :, 3:4].astype(np.uint16)
                    frame_canvas = ((bgr_plane * alpha_u16 + frame_canvas.astype(np.uint16) * (255 - alpha_u16)) // 255).astype(np.uint8)
                else:
                    frame_canvas = cv2.warpAffine(
                        img, M, (width, height),
                        flags=cv2.INTER_LINEAR,
                        borderMode=cv2.BORDER_REFLECT,
                    )

            # Render 3D Volumetric Dust Particles directly onto frame
            for d_idx in range(num_dust):
                d_par = 1000.0 / dust_z[d_idx]
                curr_x = int((dust_x[d_idx] + p * 40.0 * dust_speed[d_idx] * d_par) % width)
                curr_y = int((dust_y[d_idx] - p * 25.0 * dust_speed[d_idx] * d_par) % height)
                d_size = max(1, int(round(2.0 * d_par)))
                cv2.circle(frame_canvas, (curr_x, curr_y), d_size, (200, 210, 230), -1)

            frame_vignette = (frame_canvas.astype(np.float32) * vignette_mask).astype(np.int16)
            rolled_grain = np.roll(grain_base, shift=(frame_idx * 37, frame_idx * 53), axis=(0, 1))[..., None]
            frame_final = np.clip(frame_vignette + rolled_grain, 0, 255).astype(np.uint8)

            writer.write(frame_final)

    finally:
        writer.release()

    # Re-encode to broadcast H.264 MP4 with BT.709 tags via ffmpeg
    success = reencode_broadcast_mp4(tmp_raw_mp4, output_path, fps=fps)
    if tmp_raw_mp4.exists():
        tmp_raw_mp4.unlink(missing_ok=True)
    return success


def reencode_broadcast_mp4(src_path: Path, dst_path: Path, fps: int = 30) -> bool:
    """Encodes to pristine 14 Mbps H.264 MP4."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise RenderingError(
            stage="render",
            artifact=dst_path,
            cause="ffmpeg binary is missing on PATH",
        )

    enc = "h264_videotoolbox" if sys.platform == "darwin" else "libx264"
    cmd = [
        ffmpeg_bin, "-y",
        "-i", str(src_path),
        "-c:v", enc,
    ]
    if enc == "h264_videotoolbox":
        cmd.extend(["-b:v", "14M", "-profile:v", "high", "-pix_fmt", "yuv420p"])
    else:
        cmd.extend(["-crf", "17", "-preset", "fast", "-pix_fmt", "yuv420p"])

    cmd.extend([
        "-colorspace", "bt709",
        "-color_trc", "bt709",
        "-color_primaries", "bt709",
        "-r", str(fps),
        str(dst_path),
    ])

    proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0 or not dst_path.exists() or dst_path.stat().st_size == 0:
        err_msg = proc.stderr[-240:].strip() if proc.stderr else "unknown error"
        raise RenderingError(
            stage="render",
            artifact=dst_path,
            cause=f"ffmpeg encode failed ({enc}): {err_msg}",
        )
    return True


# ---------------------------------------------------------------------------
# CLI INTERFACE
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="FrameForge Cinematic Photobook Parallax Engine")
    ap.add_argument("--image", "-i", type=Path, help="Input single image to decompose into 3D parallax")
    ap.add_argument("--bg", type=Path, help="Explicit Far background plate (Z=3000)")
    ap.add_argument("--subject", type=Path, help="Explicit Midground hero subject (Z=1000)")
    ap.add_argument("--fg", type=Path, help="Explicit Near foreground occluder (Z=200)")
    ap.add_argument("--style", "-s", type=str, default="magnates_amber", choices=list(STYLE_GRADES.keys()), help="35mm color grade")
    ap.add_argument("--trajectory", "-t", type=str, default="magnates_drift", choices=TRAJECTORY_PRESETS, help="Camera move preset")
    ap.add_argument("--duration", "-d", type=float, default=3.5, help="Clip duration in seconds")
    ap.add_argument("--fps", type=int, default=30, help="Frame rate")
    ap.add_argument("--width", type=int, default=1080, help="Output width (default: 1080)")
    ap.add_argument("--height", type=int, default=1920, help="Output height (default: 1920)")
    ap.add_argument("--output", "-o", type=Path, required=True, help="Output MP4 path")

    args = ap.parse_args()

    layers: List[PhotobookLayer] = []

    if args.image:
        if not args.image.exists():
            print(f"Error: Input image not found: {args.image}", file=sys.stderr)
            return 1
        img = cv2.imread(str(args.image))
        if img is None:
            print(f"Error: Failed to read image: {args.image}", file=sys.stderr)
            return 1
        layers = decompose_single_image(img, args.width, args.height)

    elif args.bg and args.subject:
        if not args.bg.exists() or not args.subject.exists():
            print("Error: Background or Subject file missing", file=sys.stderr)
            return 1
        bg_img = cv2.imread(str(args.bg))
        subj_img = cv2.imread(str(args.subject), cv2.IMREAD_UNCHANGED)
        layers.append(PhotobookLayer(image=bg_img, z_depth=3000.0, is_background=True))
        layers.append(PhotobookLayer(image=subj_img, z_depth=1000.0))
        if args.fg and args.fg.exists():
            fg_img = cv2.imread(str(args.fg), cv2.IMREAD_UNCHANGED)
            layers.append(PhotobookLayer(image=fg_img, z_depth=200.0, is_foreground=True))
    else:
        print("Error: Must provide either --image or both --bg and --subject", file=sys.stderr)
        ap.print_help()
        return 1

    print(f"🎬 Rendering Cinematic Photobook [{args.style} | {args.trajectory} | {args.duration}s @ {args.fps}fps]...")
    ok = render_photobook_scene(
        layers=layers,
        output_path=args.output,
        style=args.style,
        trajectory=args.trajectory,
        duration=args.duration,
        fps=args.fps,
        width=args.width,
        height=args.height,
    )

    if ok:
        print(f"✅ Rendered successfully: {args.output}")
        return 0
    else:
        print(f"❌ Render failed: {args.output}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
