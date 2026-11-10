#!/usr/bin/env python3
"""tools/picture_book_engine.py — Tactile Living Picture-Book & Scrapbook Video Engine (v7.0).

Implements the SOTA Magnates Media, Vox & LEMMiNO documentary style:
1. Multi-image tactile scrapbook spread: Open antique oxblood leather journal on dark walnut desk.
2. Living Motion Plates (2.5D Parallax): Continuous internal scale push-in & drift inside photo frames (Zero static JPEGs).
3. Real-time animated vector elements: Dynamic cartography route unrolling (when opted in) & word-locked highlighter sweeps.
4. Authentic 1-by-1 physical page-flip transitions with triple-layer foley (Riser + Swoosh + Paper + Desk Thud).
5. 3-Tier Layered Cinematic Sound Design:
   - Tier 1 (Espresso): Continuous sub-bass suspense drone & analog room tone (-22 dBFS).
   - Tier 2 (Milk): Two-act score with dynamic breathing and mid-side vocal ducking.
   - Tier 3 (Cream): Frame-accurate stereo Foley with spatial panning matching on-screen evidence.
6. Local Kokoro-82M ONNX neural narration with Shure SM7B broadcast chain and room acoustic presence.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import logging
import math
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap
from typing import Any, Dict, List, Optional, Tuple
import wave

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from tools import build_video  # noqa: E402
from tools.errors import MissingInputError, RenderingError  # noqa: E402
from tools.pop_scan import generate_contact_sheet, scan_video_for_pops  # noqa: E402
from tools.production_ledger import record_ledger_event  # noqa: E402
from tools.sound_architect import (  # noqa: E402
    DECIBEL_BUDGET,
    build_triple_layer_page_flip_sfx,
    db_to_linear,
    detect_speech_pauses,
    ensure_documentary_foley_pack,
    generate_continuous_drone_bed,
    get_cue_decibel,
    get_cue_linear_gain,
    snap_cue_to_breath_pause,
)

# ---------------------------------------------------------------------------
# Path Configuration & System Constants
# ---------------------------------------------------------------------------
TOOLS_DIR = REPO_ROOT / "tools"
ASSETS_DIR = REPO_ROOT / "assets"
SFX_DIR = ASSETS_DIR / "audio" / "sfx"
EMOJI_DIR = ASSETS_DIR / "emojis"
BGM_FILE_1 = ASSETS_DIR / "audio" / "bgm" / "echoes_mystery.mp3"
BGM_FILE_2 = ASSETS_DIR / "audio" / "bgm" / "vertigo_tension.mp3"
KOKORO_MODEL = TOOLS_DIR / "kokoro_models" / "kokoro-v1.0.onnx"
KOKORO_VOICES = TOOLS_DIR / "kokoro_models" / "voices-v1.0.bin"
OUTPUT_DIR = REPO_ROOT / "output"

FONT_PATH = str(TOOLS_DIR / "fonts" / "BeVietnamPro-Medium.ttf")
FONT_BOLD = str(TOOLS_DIR / "fonts" / "BeVietnamPro-Bold.ttf")

WIDTH = 1920
HEIGHT = 1080

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("picture_book_engine")


def _encode_h264_mp4(src_raw: Path, dst_mp4: Path, bitrate: str = "14M", extra_args: Optional[List[str]] = None) -> None:
    """Encodes raw video stream to H.264 MP4."""
    ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
    enc = "h264_videotoolbox" if sys.platform == "darwin" else "libx264"
    cmd = [ffmpeg_bin, "-y", "-i", str(src_raw), "-c:v", enc]
    if enc == "h264_videotoolbox":
        cmd.extend(["-b:v", bitrate, "-pix_fmt", "yuv420p"])
    else:
        cmd.extend(["-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p"])
    if extra_args:
        cmd.extend(extra_args)
    cmd.append(str(dst_mp4))
    proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0 or not dst_mp4.exists() or dst_mp4.stat().st_size == 0:
        err_msg = proc.stderr[-240:].strip() if proc.stderr else "unknown error"
        raise RenderingError(stage="render", artifact=dst_mp4, cause=f"ffmpeg encode failed ({enc}): {err_msg}")


# ---------------------------------------------------------------------------
# Data Model: StoryElement (Unified with Forensic Series & Project Scenes)
# ---------------------------------------------------------------------------
@dataclass
class StoryElement:
    scene_id: str
    act: str
    title: str
    text: str
    highlighter_phrase: str
    timestamp_text: str
    location_text: str
    exhibit_code: str
    stamp_text: str
    hero_image: str
    cutout_image: str
    secondary_trigger_word: str
    sound_cues: List[Dict[str, Any]] = field(default_factory=list)
    speech_chunks: List[Tuple[str, float, float]] = field(default_factory=list)
    left_emoji: Optional[str] = None
    right_emoji: Optional[str] = None
    case_header: str = "ARCHIVAL CASE DOSSIER"
    render_flight_map: bool = False


def story_elements_from_project(project_data: Dict[str, Any]) -> List[StoryElement]:
    """Converts a schema v2 project.json dictionary into StoryElement instances."""
    scenes = project_data.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("project contains no scenes for picture_book_engine")

    project_title = str(project_data.get("title") or project_data.get("topic") or "Archival Study").strip()
    project_id = str(project_data.get("id") or "ARCHIVE").strip()
    case_header = str(project_data.get("case_header") or f"DOSSIER {project_id}: {project_title[:24].upper()}").strip()

    elements: List[StoryElement] = []
    for idx, sc in enumerate(scenes):
        if not isinstance(sc, dict):
            raise ValueError(f"scene[{idx}] must be a dict")
        scene_id = str(sc.get("id") or f"s{idx + 1:02d}").strip()
        text = str(sc.get("text") or "").strip()
        if not text:
            raise ValueError(f"scene[{idx}] text must be non-empty")

        words = [w.strip(".,!?\"'():;") for w in text.split() if w.strip(".,!?\"'():;")]
        hl_default = " ".join(words[:3]) if len(words) >= 3 else (words[0] if words else "")
        trig_default = words[min(len(words) - 1, max(0, len(words) // 2))] if words else ""

        img_rel = str(sc.get("image") or f"images/{scene_id}.jpg")
        hero_name = Path(img_rel).name
        cutout_rel = str(sc.get("cutout_image") or hero_name)
        cutout_name = Path(cutout_rel).name

        elements.append(
            StoryElement(
                scene_id=scene_id,
                act=str(sc.get("act") or f"SCENE {idx + 1:02d}"),
                title=str(sc.get("title") or sc.get("plate_label") or f"{project_title} ({idx + 1})"),
                text=text,
                highlighter_phrase=str(sc.get("highlighter_phrase") or hl_default),
                timestamp_text=str(sc.get("timestamp_text") or f"ENTRY {idx + 1:02d}"),
                location_text=str(sc.get("location_text") or project_title[:28]),
                exhibit_code=str(sc.get("exhibit_code") or sc.get("plate_label") or f"EXHIBIT {idx + 1:02d}"),
                stamp_text=str(sc.get("stamp") or sc.get("stamp_text") or "VERIFIED"),
                hero_image=hero_name,
                cutout_image=cutout_name,
                secondary_trigger_word=str(sc.get("secondary_trigger_word") or trig_default),
                sound_cues=list(sc.get("sound_cues") or []),
                speech_chunks=list(sc.get("speech_chunks") or []),
                left_emoji=sc.get("left_emoji"),
                right_emoji=sc.get("right_emoji"),
                case_header=str(sc.get("case_header") or case_header),
                render_flight_map=bool(sc.get("render_flight_map", False)),
            )
        )
    return elements


# ---------------------------------------------------------------------------
# Visual Element & Tactile Compositing Utilities
# ---------------------------------------------------------------------------
def overlay_3d_emoji(target_bgr: np.ndarray, emoji_name: str, cx: int, cy: int, size: int = 140) -> np.ndarray:
    """Overlays a prominent Microsoft Fluent 3D Emoji with realistic ambient drop shadow."""
    png_path = EMOJI_DIR / f"{emoji_name}_3d.png"
    if not png_path.exists():
        return target_bgr

    emoji_rgba = cv2.imread(str(png_path), cv2.IMREAD_UNCHANGED)
    if emoji_rgba is None or emoji_rgba.shape[2] != 4:
        return target_bgr

    emoji_resized = cv2.resize(emoji_rgba, (size, size), interpolation=cv2.INTER_LANCZOS4)
    alpha = emoji_resized[:, :, 3].astype(np.float32) / 255.0
    bgr = emoji_resized[:, :, :3].astype(np.float32)

    # Ambient drop shadow
    shadow_mask = np.zeros((size + 30, size + 30), dtype=np.uint8)
    shadow_mask[15:15 + size, 15:15 + size] = (emoji_resized[:, :, 3] * 0.55).astype(np.uint8)
    shadow_mask = cv2.GaussianBlur(shadow_mask, (25, 25), 0)

    th, tw = target_bgr.shape[:2]
    sx1 = cx - (size + 30) // 2 + 6
    sy1 = cy - (size + 30) // 2 + 14
    sx2 = sx1 + size + 30
    sy2 = sy1 + size + 30

    if sx1 >= 0 and sy1 >= 0 and sx2 <= tw and sy2 <= th:
        s_factor = 1.0 - (shadow_mask.astype(np.float32) / 255.0)
        target_bgr[sy1:sy2, sx1:sx2] = np.clip(target_bgr[sy1:sy2, sx1:sx2].astype(np.float32) * s_factor[..., None], 0, 255).astype(np.uint8)

    # Composite emoji
    x1 = cx - size // 2
    y1 = cy - size // 2
    x2 = x1 + size
    y2 = y1 + size

    if x1 >= 0 and y1 >= 0 and x2 <= tw and y2 <= th:
        roi = target_bgr[y1:y2, x1:x2].astype(np.float32)
        target_bgr[y1:y2, x1:x2] = np.clip(roi * (1.0 - alpha[..., None]) + bgr * alpha[..., None], 0, 255).astype(np.uint8)

    return target_bgr


def draw_frosted_scotch_tape(
    canvas: np.ndarray,
    cx: int,
    cy: int,
    width: int = 80,
    height: int = 26,
    angle_deg: float = -22.0,
) -> np.ndarray:
    """Draws realistic translucent matte Scotch tape with soft specular highlights and torn edges."""
    tape = np.full((height, width, 4), (220, 235, 245, 175), dtype=np.uint8)
    tape[2:4, :] = (255, 255, 255, 210)
    noise = np.random.normal(0, 10, (height, width)).astype(np.float32)
    tape[:, :, 3] = np.clip(tape[:, :, 3].astype(np.float32) + noise, 120, 210).astype(np.uint8)

    rad = math.radians(angle_deg)
    cos_a, sin_a = abs(math.cos(rad)), abs(math.sin(rad))
    rot_w = int(width * cos_a + height * sin_a) + 6
    rot_h = int(width * sin_a + height * cos_a) + 6

    M = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), angle_deg, 1.0)
    M[0, 2] += (rot_w - width) / 2.0
    M[1, 2] += (rot_h - height) / 2.0

    rot_t = cv2.warpAffine(tape, M, (rot_w, rot_h), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
    x1 = cx - rot_w // 2
    y1 = cy - rot_h // 2
    x2, y2 = x1 + rot_w, y1 + rot_h

    c_h, c_w = canvas.shape[:2]
    if x2 <= c_w and y2 <= c_h and x1 >= 0 and y1 >= 0:
        a = rot_t[:, :, 3].astype(np.float32) / 255.0
        bgr = rot_t[:, :, :3].astype(np.float32)
        roi = canvas[y1:y2, x1:x2].astype(np.float32)
        canvas[y1:y2, x1:x2] = np.clip(roi * (1.0 - a[..., None]) + bgr * a[..., None], 0, 255).astype(np.uint8)

    return canvas


def draw_brass_pushpin(canvas: np.ndarray, cx: int, cy: int, radius: int = 14) -> np.ndarray:
    """Draws a tactile metallic brass pushpin with directional drop shadow and specular glint."""
    cv2.circle(canvas, (cx + 3, cy + 5), radius + 1, (15, 18, 24), -1)
    cv2.circle(canvas, (cx, cy), radius, (38, 165, 215), -1, cv2.LINE_AA)
    cv2.circle(canvas, (cx, cy), radius - 3, (28, 130, 180), -1, cv2.LINE_AA)
    cv2.circle(canvas, (cx - radius // 3, cy - radius // 3), radius // 3, (120, 220, 255), -1, cv2.LINE_AA)
    return canvas


def draw_rubber_stamp(
    canvas: np.ndarray,
    text: str,
    cx: int,
    cy: int,
    angle_deg: float = -14.0,
    color_bgr: Tuple[int, int, int] = (30, 30, 195),
) -> np.ndarray:
    """Draws an official archival weathered rubber stamp with double border and ink splatter."""
    text = text.upper()
    font_scale = 0.72
    thickness = 2
    (tw, th), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)

    pad_x, pad_y = 20, 14
    s_w = tw + pad_x * 2
    s_h = th + pad_y * 2 + baseline

    stamp_mat = np.zeros((s_h, s_w, 4), dtype=np.uint8)
    cv2.rectangle(stamp_mat, (2, 2), (s_w - 3, s_h - 3), (*color_bgr, 230), 2)
    cv2.rectangle(stamp_mat, (6, 6), (s_w - 7, s_h - 7), (*color_bgr, 210), 1)
    cv2.putText(stamp_mat, text, (pad_x, s_h - pad_y - baseline // 2), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (*color_bgr, 240), thickness, cv2.LINE_AA)

    noise = np.random.uniform(0.68, 1.0, (s_h, s_w)).astype(np.float32)
    stamp_mat[:, :, 3] = (stamp_mat[:, :, 3].astype(np.float32) * noise).astype(np.uint8)

    rad = math.radians(angle_deg)
    cos_a, sin_a = abs(math.cos(rad)), abs(math.sin(rad))
    rot_w = int(s_w * cos_a + s_h * sin_a) + 10
    rot_h = int(s_w * sin_a + s_h * cos_a) + 10

    M = cv2.getRotationMatrix2D((s_w / 2.0, s_h / 2.0), angle_deg, 1.0)
    M[0, 2] += (rot_w - s_w) / 2.0
    M[1, 2] += (rot_h - s_h) / 2.0

    rot_s = cv2.warpAffine(stamp_mat, M, (rot_w, rot_h), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
    x1 = cx - rot_w // 2
    y1 = cy - rot_h // 2
    x2, y2 = x1 + rot_w, y1 + rot_h

    c_h, c_w = canvas.shape[:2]
    if x2 <= c_w and y2 <= c_h and x1 >= 0 and y1 >= 0:
        a = rot_s[:, :, 3].astype(np.float32) / 255.0
        bgr = rot_s[:, :, :3].astype(np.float32)
        roi = canvas[y1:y2, x1:x2].astype(np.float32)
        canvas[y1:y2, x1:x2] = np.clip(roi * (1.0 - a[..., None]) + bgr * a[..., None], 0, 255).astype(np.uint8)

    return canvas


def draw_highlighter_bar(
    canvas: np.ndarray,
    x: int,
    y: int,
    w: int,
    h: int,
    progress: float = 1.0,
) -> np.ndarray:
    """Overlays dynamic fluorescent yellow highlighter sweep across text."""
    if progress <= 0.0 or w <= 0 or h <= 0:
        return canvas
    cur_w = int(w * max(0.0, min(1.0, progress)))
    if cur_w <= 0:
        return canvas

    c_h, c_w = canvas.shape[:2]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(c_w, x + cur_w), min(c_h, y + h)

    if x2 > x1 and y2 > y1:
        roi = canvas[y1:y2, x1:x2].astype(np.float32)
        yellow = np.array([25, 235, 255], dtype=np.float32)
        alpha = 0.38
        canvas[y1:y2, x1:x2] = np.clip(roi * (1.0 - alpha) + yellow * alpha, 0, 255).astype(np.uint8)

    return canvas


def draw_gold_embossed_seal(canvas: np.ndarray, cx: int, cy: int, radius: int = 40) -> np.ndarray:
    """Draws an ornate 3D gold embossed notary seal with star serrations."""
    c_h, c_w = canvas.shape[:2]
    pad = radius + 15
    sx1 = max(0, cx - pad)
    sy1 = max(0, cy - pad)
    sx2 = min(c_w, cx + pad)
    sy2 = min(c_h, cy + pad)

    seal = np.zeros((sy2 - sy1, sx2 - sx1, 4), dtype=np.uint8)
    scx, scy = cx - sx1, cy - sy1

    num_teeth = 32
    outer_r = radius
    inner_r = max(2, radius - 6)
    pts = []
    for i in range(num_teeth * 2):
        a = i * math.pi / num_teeth
        r = outer_r if (i % 2 == 0) else inner_r
        pts.append([int(scx + r * math.cos(a)), int(scy + r * math.sin(a))])
    pts_arr = np.array(pts, np.int32)
    cv2.fillPoly(seal, [pts_arr], (40, 160, 215, 245))
    cv2.polylines(seal, [pts_arr], True, (25, 120, 175, 255), 1, cv2.LINE_AA)
    if radius > 14:
        cv2.circle(seal, (scx, scy), radius - 10, (50, 185, 240, 255), 2, cv2.LINE_AA)
        cv2.circle(seal, (scx, scy), radius - 14, (30, 140, 195, 255), 1, cv2.LINE_AA)

    alpha = seal[:, :, 3].astype(np.float32) / 255.0
    bgr = seal[:, :, :3].astype(np.float32)
    roi = canvas[sy1:sy2, sx1:sx2].astype(np.float32)
    canvas[sy1:sy2, sx1:sx2] = np.clip(roi * (1.0 - alpha[..., None]) + bgr * alpha[..., None], 0, 255).astype(np.uint8)
    return canvas


def composite_plate_with_shadow(
    canvas: np.ndarray,
    plate: np.ndarray,
    center_x: int,
    center_y: int,
    angle_deg: float = 0.0,
    shadow_blur: int = 24,
    shadow_alpha: float = 0.50,
) -> np.ndarray:
    """Rotates and composites a rectangular plate onto canvas with realistic elevation drop shadow."""
    h, w = plate.shape[:2]
    rad = math.radians(angle_deg)
    cos_a, sin_a = abs(math.cos(rad)), abs(math.sin(rad))
    rot_w = int(w * cos_a + h * sin_a) + 8
    rot_h = int(w * sin_a + h * cos_a) + 8

    M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle_deg, 1.0)
    M[0, 2] += (rot_w - w) / 2.0
    M[1, 2] += (rot_h - h) / 2.0

    rot_plate = cv2.warpAffine(plate, M, (rot_w, rot_h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))

    mask = np.full((h, w), 255, dtype=np.uint8)
    rot_mask = cv2.warpAffine(mask, M, (rot_w, rot_h), flags=cv2.INTER_LINEAR, borderValue=0)

    c_h, c_w = canvas.shape[:2]
    sx1 = center_x - rot_w // 2 + 10
    sy1 = center_y - rot_h // 2 + 16
    sx2, sy2 = sx1 + rot_w, sy1 + rot_h

    if sx2 <= c_w and sy2 <= c_h and sx1 >= 0 and sy1 >= 0:
        shadow_patch = cv2.GaussianBlur(rot_mask, (shadow_blur | 1, shadow_blur | 1), 0)
        s_factor = 1.0 - (shadow_patch.astype(np.float32) / 255.0) * shadow_alpha
        roi = canvas[sy1:sy2, sx1:sx2].astype(np.float32)
        canvas[sy1:sy2, sx1:sx2] = np.clip(roi * s_factor[..., None], 0, 255).astype(np.uint8)

    x1 = center_x - rot_w // 2
    y1 = center_y - rot_h // 2
    x2, y2 = x1 + rot_w, y1 + rot_h

    if x2 <= c_w and y2 <= c_h and x1 >= 0 and y1 >= 0:
        alpha_m = (rot_mask > 20).astype(np.float32)[..., None]
        roi = canvas[y1:y2, x1:x2].astype(np.float32)
        plate_f = rot_plate.astype(np.float32)
        canvas[y1:y2, x1:x2] = np.clip(roi * (1.0 - alpha_m) + plate_f * alpha_m, 0, 255).astype(np.uint8)

    return canvas


# ---------------------------------------------------------------------------
# Interactive Archival Cartography & Flight Route Map Engine
# ---------------------------------------------------------------------------
def cubic_bezier(
    p0: Tuple[float, float],
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
    t: float,
) -> Tuple[float, float]:
    u = 1.0 - t
    x = (u**3) * p0[0] + 3 * (u**2) * t * p1[0] + 3 * u * (t**2) * p2[0] + (t**3) * p3[0]
    y = (u**3) * p0[1] + 3 * (u**2) * t * p1[1] + 3 * u * (t**2) * p2[1] + (t**3) * p3[1]
    return (x, y)


def render_cartography_flight_map(
    progress: float,
    time_sec: float,
    width: int = 580,
    height: int = 420,
) -> np.ndarray:
    """Renders a vintage 1971 archival aeronautical cartography chart of Puget Sound."""
    canvas = np.full((height, width, 3), (218, 230, 238), dtype=np.uint8)

    # Water bodies
    puget_poly = np.array([
        [int(0.25 * width), 0],
        [int(0.48 * width), 0],
        [int(0.52 * width), int(0.25 * height)],
        [int(0.46 * width), int(0.48 * height)],
        [int(0.38 * width), int(0.70 * height)],
        [int(0.28 * width), int(0.85 * height)],
        [int(0.18 * width), height],
        [0, height],
        [0, int(0.35 * height)],
    ], np.int32)
    cv2.fillPoly(canvas, [puget_poly], (215, 195, 175))

    # Grid lines
    for gx in range(40, width, 50):
        cv2.line(canvas, (gx, 0), (gx, height), (195, 205, 215), 1)
    for gy in range(40, height, 50):
        cv2.line(canvas, (0, gy), (width, gy), (195, 205, 215), 1)

    # Waypoints: Portland (PDX) to Seattle-Tacoma (SEA)
    pdx = (int(0.55 * width), int(0.82 * height))
    sea = (int(0.48 * width), int(0.20 * height))
    p0 = pdx
    p1 = (int(0.60 * width), int(0.60 * height))
    p2 = (int(0.42 * width), int(0.40 * height))
    p3 = sea

    num_pts = 60
    spline = [cubic_bezier(p0, p1, p2, p3, i / float(num_pts)) for i in range(num_pts + 1)]
    active_idx = int(progress * num_pts)

    for i in range(active_idx):
        pt1 = (int(spline[i][0]), int(spline[i][1]))
        pt2 = (int(spline[i + 1][0]), int(spline[i + 1][1]))
        cv2.line(canvas, pt1, pt2, (40, 45, 195), 2, cv2.LINE_AA)

    # Plane icon
    if active_idx < len(spline):
        cur_pos = spline[active_idx]
        cur_x, cur_y = int(cur_pos[0]), int(cur_pos[1])
        cv2.circle(canvas, (cur_x, cur_y), 6, (30, 30, 220), -1, cv2.LINE_AA)
        cv2.circle(canvas, (cur_x, cur_y), 10, (50, 50, 220), 1, cv2.LINE_AA)

    # Waypoint labels
    cv2.putText(canvas, "PORTLAND (PDX)", (pdx[0] - 80, pdx[1] + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (30, 40, 60), 1, cv2.LINE_AA)
    cv2.putText(canvas, "SEATTLE (SEA-TAC)", (sea[0] - 40, sea[1] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (30, 40, 60), 1, cv2.LINE_AA)
    cv2.putText(canvas, "FLIGHT 305 ROUTE V-23", (14, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (40, 45, 120), 1, cv2.LINE_AA)

    return canvas


# ---------------------------------------------------------------------------
# Dynamic Camera Trajectory & Viewport Renderer
# ---------------------------------------------------------------------------
def smoothstep(edge0: float, edge1: float, x: float) -> float:
    t = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def get_scene_camera_trajectory(
    scene_id: str,
    t_norm: float,
    is_last_scene: bool = False,
    width: int = 1920,
    height: int = 1080,
) -> Tuple[float, float, float, float]:
    """Calculates smooth dynamic virtual camera viewport (cam_cx, cam_cy, zoom, angle_deg) scaled to dimensions."""
    is_vertical = height > width
    if is_vertical:
        cx_mid = width * 0.50
        cy_top = height * 0.38
        cy_bot = height * 0.62
        cy_mid = height * 0.50
        if is_last_scene:
            s = smoothstep(0.0, 0.90, t_norm)
            return cx_mid, cy_bot + (cy_mid - cy_bot) * s, 1.18 - 0.14 * s, 0.4 - s * 0.4
        if t_norm < 0.35:
            s = smoothstep(0.0, 0.35, t_norm)
            return cx_mid, cy_top + s * (height * 0.02), 1.12 + s * 0.04, -0.5 + s * 0.2
        elif t_norm < 0.75:
            s = smoothstep(0.35, 0.75, t_norm)
            return cx_mid, (cy_top + height * 0.02) + (cy_bot - (cy_top + height * 0.02)) * s, 1.16 + 0.06 * s, -0.3 + s * 0.8
        else:
            s = smoothstep(0.75, 0.94, t_norm)
            return cx_mid, cy_bot + (cy_mid - cy_bot) * s, 1.22 - 0.16 * s, 0.5 - s * 0.5

    sx = width / 1920.0
    sy = height / 1080.0
    if is_last_scene:
        s = smoothstep(0.0, 0.90, t_norm)
        cx = (700.0 + (960.0 - 700.0) * s) * sx
        cy = (580.0 + (540.0 - 580.0) * s) * sy
        z = 1.38 - (1.38 - 1.02) * s
        rot = 0.6 - s * 0.6
        return cx, cy, z, rot

    if t_norm < 0.35:
        s = smoothstep(0.0, 0.35, t_norm)
        return (560.0 + s * 25.0) * sx, (500.0 - s * 10.0) * sy, 1.28 + s * 0.04, -0.8 + s * 0.2
    elif t_norm < 0.75:
        s = smoothstep(0.35, 0.75, t_norm)
        cx = (585.0 + (1380.0 - 585.0) * s) * sx
        cy = (490.0 + (510.0 - 490.0) * s) * sy
        z = 1.32 + (1.44 - 1.32) * s
        rot = -0.6 + s * 1.4
        return cx, cy, z, rot
    else:
        s = smoothstep(0.75, 0.94, t_norm)
        cx = (1380.0 - (1380.0 - 960.0) * s) * sx
        cy = (510.0 + (540.0 - 510.0) * s) * sy
        z = 1.44 - (1.44 - 1.08) * s
        rot = 0.8 - s * 0.8
        return cx, cy, z, rot


def render_camera_viewport(
    plate: np.ndarray,
    cam_cx: float,
    cam_cy: float,
    zoom: float,
    angle_deg: float = 0.0,
    out_w: int = 1920,
    out_h: int = 1080,
) -> np.ndarray:
    """Renders a smooth cinematic camera viewport transformation with sub-pixel interpolation."""
    M = cv2.getRotationMatrix2D((cam_cx, cam_cy), angle_deg, zoom)
    M[0, 2] += (out_w / 2.0) - cam_cx
    M[1, 2] += (out_h / 2.0) - cam_cy
    return cv2.warpAffine(plate, M, (out_w, out_h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT_101)


# ---------------------------------------------------------------------------
# Picture-Book Spread Compositor (Full-Bleed, Multi-Image Collage, 16:9 & 9:16)
# ---------------------------------------------------------------------------
def build_scene_base_spread(
    element: StoryElement,
    images_dir: Path,
    cutouts_dir: Path,
    width: int = 1920,
    height: int = 1080,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Constructs the high-resolution tactile physical base canvas with wood, leather, parchment, and text."""
    is_vertical = height > width
    scale = max(0.30, min(width, height) / 1080.0)

    # 1. Base Desk Canvas (Rich Dark Walnut with Planks & Cinematic Warm Spotlight)
    desk = np.full((height, width, 3), (24, 34, 48), dtype=np.float32)
    y_grid, x_grid = np.ogrid[:height, :width]
    plank_seams = 1.0 - 0.18 * np.exp(- ((y_grid % max(40, int(220 * scale))) ** 2) / (2 * (2.5 ** 2)))
    wood_grain = np.sin(x_grid * 0.04 + np.sin(y_grid * 0.02) * 5.0) * 3.0
    desk = desk * plank_seams[..., None] + wood_grain[..., None]

    cx_light, cy_light = width // 2, height // 2
    dist_sq = (x_grid - cx_light) ** 2 + (y_grid - cy_light) ** 2
    spot_r = max(160.0, 650.0 * scale)
    spotlight = np.exp(- dist_sq / (2.0 * (spot_r ** 2)))
    desk += spotlight[..., None] * np.array([18.0, 32.0, 45.0], dtype=np.float32)
    desk = np.clip(desk, 0, 255).astype(np.uint8)

    # 2. Hardcover Antique Oxblood Leather Book (94% width, 92% height)
    book_w = int(width * 0.94)
    book_h = int(height * 0.92)
    bx = (width - book_w) // 2
    by = (height - book_h) // 2

    shadow_layer = np.zeros((height, width), dtype=np.uint8)
    cv2.rectangle(shadow_layer, (bx + 8, by + 16), (min(width - 1, bx + book_w + 14), min(height - 1, by + book_h + 20)), 160, -1)
    shadow_blur = cv2.GaussianBlur(shadow_layer, (41, 41), 0)
    desk_arr = desk.astype(np.float32)
    s_factor = (1.0 - (shadow_blur.astype(np.float32) / 255.0) * 0.65)[..., None]
    canvas = (desk_arr * s_factor).clip(0, 255).astype(np.uint8)

    leather = np.full((book_h, book_w, 3), (28, 22, 58), dtype=np.uint8)
    leather_noise = np.random.normal(0, 3.0, (book_h, book_w, 1)).astype(np.float32)
    leather = np.clip(leather.astype(np.float32) + leather_noise, 0, 255).astype(np.uint8)

    cv2.rectangle(leather, (10, 10), (book_w - 10, book_h - 10), (55, 175, 212), 2, cv2.LINE_AA)
    cv2.rectangle(leather, (16, 16), (book_w - 16, book_h - 16), (40, 140, 175), 1, cv2.LINE_AA)

    page_inset_x = max(10, int(round(26 * scale)))
    page_inset_y = max(10, int(round(22 * scale)))
    pw = book_w - page_inset_x * 2
    ph = book_h - page_inset_y * 2
    px = bx + page_inset_x
    py = by + page_inset_y

    pages = np.full((ph, pw, 3), (222, 236, 246), dtype=np.float32)
    p_noise = np.random.normal(0, 3.5, (ph, pw, 1)).astype(np.float32)
    pages = np.clip(pages + p_noise, 0, 255)

    if is_vertical:
        # Horizontal fold crease for portrait dossier spread
        sph = ph // 2
        y_spine = np.arange(ph, dtype=np.float32)
        spine_dist = np.abs(y_spine - sph)
        spine_shadow = 1.0 - 0.32 * np.exp(- (spine_dist ** 2) / (2 * (max(12.0, 45.0 * scale) ** 2)))
        pages = (pages * spine_shadow[:, None, None]).astype(np.uint8)
        cv2.line(pages, (0, sph), (pw, sph), (120, 135, 150), 1)
        spw = pw
    else:
        spw = pw // 2
        x_spine = np.arange(pw, dtype=np.float32)
        spine_dist = np.abs(x_spine - spw)
        spine_shadow = 1.0 - 0.42 * np.exp(- (spine_dist ** 2) / (2 * (max(12.0, 55.0 * scale) ** 2)))
        pages = (pages * spine_shadow[None, :, None]).astype(np.uint8)
        cv2.line(pages, (spw - 1, 0), (spw - 1, ph), (120, 135, 150), 1)
        cv2.line(pages, (spw + 1, 0), (spw + 1, ph), (120, 135, 150), 1)

    leather[page_inset_y:page_inset_y + ph, page_inset_x:page_inset_x + pw] = pages
    canvas[by:by + book_h, bx:bx + book_w] = leather

    # 4. Story Text, Drop Cap & Investigation Memo Card
    pil_canvas = Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_canvas)

    try:
        font_chapter = ImageFont.truetype(FONT_BOLD, max(12, int(round(22 * scale))))
        font_drop = ImageFont.truetype(FONT_BOLD, max(28, int(round(68 * scale))))
        font_body = ImageFont.truetype(FONT_PATH, max(11, int(round(21 * scale))))
    except Exception:
        font_chapter = ImageFont.load_default()
        font_drop = ImageFont.load_default()
        font_body = ImageFont.load_default()

    pad_left = max(18, int(round(55 * scale)))
    ch_text = f"CHAPTER — {element.act.upper()}"
    draw.text((px + pad_left, py + int(round(36 * scale))), ch_text, font=font_chapter, fill=(155, 55, 30))

    clean_text = element.text.replace("*", "").strip()
    drop_char = clean_text[0] if clean_text else "O"
    remainder = clean_text[1:] if len(clean_text) > 1 else ""

    draw.text((px + pad_left, py + int(round(76 * scale))), drop_char, font=font_drop, fill=(130, 25, 25))

    lines = textwrap.wrap(remainder, width=38)
    cur_y = py + int(round(88 * scale))
    line_step = max(14, int(round(30 * scale)))
    for idx_l, line in enumerate(lines[:5]):
        x_indent = px + int(round(115 * scale)) if idx_l < 2 else px + pad_left
        draw.text((x_indent, cur_y), line, font=font_body, fill=(35, 32, 28))
        cur_y += line_step

    canvas = cv2.cvtColor(np.array(pil_canvas), cv2.COLOR_RGB2BGR)

    # Tactile Memo Card
    card_w = max(120, int(spw * 0.84))
    card_h = max(70, int(round((140 if is_vertical else 190) * scale)))
    memo = np.full((card_h, card_w, 3), (230, 242, 250), dtype=np.uint8)
    cv2.rectangle(memo, (2, 2), (card_w - 3, card_h - 3), (160, 185, 205), 1)
    f_sc = max(0.28, 0.44 * scale)
    cv2.putText(memo, f"SUBJECT: {element.title[:30]}", (14, int(card_h * 0.24)), cv2.FONT_HERSHEY_SIMPLEX, f_sc, (25, 35, 85), 1, cv2.LINE_AA)
    cv2.putText(memo, f"TIME: {element.timestamp_text}", (14, int(card_h * 0.46)), cv2.FONT_HERSHEY_SIMPLEX, f_sc * 0.92, (80, 75, 70), 1, cv2.LINE_AA)
    cv2.putText(memo, f"LOCATION: {element.location_text}", (14, int(card_h * 0.68)), cv2.FONT_HERSHEY_SIMPLEX, f_sc * 0.92, (80, 75, 70), 1, cv2.LINE_AA)
    cv2.putText(memo, element.exhibit_code[:36], (14, int(card_h * 0.88)), cv2.FONT_HERSHEY_SIMPLEX, f_sc, (140, 30, 30), 1, cv2.LINE_AA)

    if is_vertical:
        memo_cx = px + (pw // 2)
        memo_cy = py + int(ph * 0.36)
        rx = px
        center_rx = px + (pw // 2)
        exhibit_cy = py + int(ph * 0.68)
    else:
        memo_cx = px + (spw // 2) - int(round(10 * scale))
        memo_cy = py + ph - int(round(135 * scale))
        rx = px + spw
        center_rx = rx + (spw // 2)
        exhibit_cy = py + int(ph * 0.44)

    canvas = composite_plate_with_shadow(canvas, memo, memo_cx, memo_cy, angle_deg=2.5, shadow_blur=max(5, int(18 * scale)), shadow_alpha=0.48)
    canvas = draw_brass_pushpin(canvas, memo_cx - (card_w // 2) + 14, memo_cy - (card_h // 2) + 12, radius=max(6, int(12 * scale)))

    hl_info = None
    if element.highlighter_phrase:
        hl_info = {"x": memo_cx - (card_w // 2) + 12, "y": memo_cy - int(10 * scale), "w": int(card_w * 0.85), "h": max(10, int(24 * scale))}

    is_flight_map = bool(element.render_flight_map)

    # Load hero main image
    hero_p = images_dir / element.hero_image
    if not hero_p.exists():
        hero_p = cutouts_dir / element.hero_image
    main_src = cv2.imread(str(hero_p)) if hero_p.exists() else None

    # Load secondary cutout
    cutout_p = cutouts_dir / element.cutout_image
    if not cutout_p.exists():
        cutout_p = images_dir / element.cutout_image
    framed_p2 = None
    if cutout_p.exists():
        src_cut = cv2.imread(str(cutout_p))
        if src_cut is not None:
            p2_w = max(90, int(round(380 * scale)))
            p2_h = max(80, int(round(340 * scale)))
            p2 = cv2.resize(src_cut, (p2_w, p2_h))
            pad_b = max(20, int(round(46 * scale)))
            pad_s = max(10, int(round(26 * scale)))
            framed_p2 = np.full((p2_h + pad_b, p2_w + pad_s, 3), (245, 248, 252), dtype=np.uint8)
            ins = pad_s // 2
            framed_p2[ins:ins + p2_h, ins:ins + p2_w] = p2
            cv2.putText(
                framed_p2,
                element.cutout_image[:30].replace(".png", "").replace(".jpg", "").replace("_", " ").upper(),
                (ins + 2, p2_h + int(pad_b * 0.78)),
                cv2.FONT_HERSHEY_SIMPLEX,
                max(0.26, 0.40 * scale),
                (120, 35, 35),
                1,
                cv2.LINE_AA,
            )

    main_w = max(140, int(round((620 if is_vertical else 510) * scale)))
    main_h = max(110, int(round((460 if is_vertical else 410) * scale)))

    meta: Dict[str, Any] = {
        "hl_info": hl_info,
        "is_scene01": is_flight_map,
        "main_src": main_src,
        "main_label": element.exhibit_code,
        "main_dims": (main_w, main_h),
        "main_pos": (center_rx - int(round(30 * scale)), exhibit_cy),
        "secondary_plate": framed_p2,
        "secondary_pos": (center_rx + int(round(85 * scale)), py + int(ph * (0.78 if is_vertical else 0.68))),
        "target_ang": 4.8,
        "tape_pos": (center_rx + int(round(160 * scale)), py + int(ph * (0.78 if is_vertical else 0.68)) - int(round(140 * scale))),
        "tape_ang": 25.0,
        "stamp_text": element.stamp_text,
        "stamp_pos": (center_rx + int(round(110 * scale)), py + int(round((ph * 0.54) if is_vertical else (140 * scale)))),
    }

    if is_flight_map:
        mw = max(140, int(spw * 0.90))
        mh = max(110, int(ph * (0.34 if is_vertical else 0.58)))
        mx = rx + (spw - mw) // 2
        my = py + (int(ph * 0.52) if is_vertical else int(round(35 * scale)))
        meta["map_coords"] = (mx, my, mw, mh)
        meta["secondary_pos"] = (center_rx, py + ph - int(round(140 * scale)))
        meta["tape_pos"] = (center_rx + int(round(120 * scale)), py + ph - int(round(220 * scale)))
        meta["tape_ang"] = 22.0
        meta["stamp_pos"] = (center_rx + int(round(120 * scale)), my + int(round(80 * scale)))

    # Telemetry Badge (Top-Right) — uses element.case_header from project metadata
    badge_w = max(120, int(spw * (0.64 if is_vertical else 0.52)))
    badge_h = max(38, int(round(75 * scale)))
    badge = np.full((badge_h, badge_w, 3), (32, 28, 26), dtype=np.uint8)
    cv2.rectangle(badge, (1, 1), (badge_w - 2, badge_h - 2), (214, 180, 100), 1)
    header_str = (element.case_header or element.exhibit_code or "ARCHIVAL CASE DOSSIER")[:34]
    cv2.putText(badge, header_str, (10, int(badge_h * 0.30)), cv2.FONT_HERSHEY_SIMPLEX, max(0.26, 0.40 * scale), (214, 180, 100), 1, cv2.LINE_AA)
    cv2.putText(badge, element.title[:28], (10, int(badge_h * 0.60)), cv2.FONT_HERSHEY_SIMPLEX, max(0.28, 0.42 * scale), (240, 240, 240), 1, cv2.LINE_AA)
    cv2.putText(badge, f"LOC: {element.location_text[:28]}", (10, int(badge_h * 0.86)), cv2.FONT_HERSHEY_SIMPLEX, max(0.24, 0.36 * scale), (180, 180, 180), 1, cv2.LINE_AA)
    badge_cx = rx + spw - (badge_w // 2) - int(round(30 * scale))
    badge_cy = py + int(round(55 * scale))
    canvas = composite_plate_with_shadow(canvas, badge, badge_cx, badge_cy, angle_deg=1.2, shadow_blur=max(5, int(14 * scale)), shadow_alpha=0.40)

    # Gold Seal
    seal_r = max(16, int(round(36 * scale)))
    canvas = draw_gold_embossed_seal(canvas, bx + book_w - int(round(65 * scale)), by + book_h - int(round(65 * scale)), radius=seal_r)

    emoji_sz = max(48, int(round(140 * scale)))
    if element.left_emoji:
        canvas = overlay_3d_emoji(canvas, element.left_emoji, px + int(spw * 0.85), py + ph - int(round(85 * scale)), size=emoji_sz)
    if element.right_emoji:
        canvas = overlay_3d_emoji(canvas, element.right_emoji, rx + int(round(80 * scale)), py + ph - int(round(100 * scale)), size=emoji_sz)

    return canvas, meta


# ---------------------------------------------------------------------------
# Dynamic 30FPS Scene Video Clip Generator (With Living Motion Plates)
# ---------------------------------------------------------------------------
def render_dynamic_scene_clip(
    element: StoryElement,
    images_dir: Path,
    cutouts_dir: Path,
    dur: float,
    words: List[Dict[str, Any]],
    output_mp4: Path,
    is_first_scene: bool = False,
    is_last_scene: bool = False,
    fps: int = 30,
    width: int = WIDTH,
    height: int = HEIGHT,
) -> Path:
    """Renders a dynamic 30fps scene video clip with living 2.5D motion plates, real-time vectors, and virtual camera motion."""
    if output_mp4.exists() and output_mp4.stat().st_size > 500000:
        logger.info(f"  ✓ Reusing cached living motion clip: {output_mp4.name} ({dur:.2f}s)")
        return output_mp4

    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    total_frames = max(1, int(round(dur * fps)))
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    tmp_raw = output_mp4.with_suffix(".raw.mp4")
    out = cv2.VideoWriter(str(tmp_raw), fourcc, fps, (width, height))

    pre_pad = 0.0 if is_first_scene else 0.55

    hl_time = pre_pad + 0.5
    if element.highlighter_phrase:
        hl_target = element.highlighter_phrase.lower().split()[0].strip(".,!?\"'")
        for w in words:
            w_str = str(w.get("word") or w.get("text") or "").lower()
            if hl_target and hl_target in w_str:
                hl_time = pre_pad + float(w.get("start", 0.0))
                break

    sec_drop_time = pre_pad + min(2.0, dur * 0.45)
    if element.secondary_trigger_word:
        trig_target = element.secondary_trigger_word.lower().strip(".,!?\"'")
        for w in words:
            w_str = str(w.get("word") or w.get("text") or "").lower()
            if trig_target and trig_target in w_str:
                sec_drop_time = pre_pad + float(w.get("start", 0.0))
                break

    actual_drop_time = max(pre_pad + 0.25, sec_drop_time)

    base_canvas, meta = build_scene_base_spread(element, images_dir, cutouts_dir, width, height)
    hl_info = meta["hl_info"]
    is_s01 = meta["is_scene01"]
    sec_plate = meta["secondary_plate"]
    stamp_text = meta["stamp_text"]
    scale = max(0.30, min(width, height) / 1080.0)

    np.random.seed(int(sum(ord(c) for c in element.scene_id)))
    particles = []
    for _ in range(45):
        particles.append({
            "x0": np.random.uniform(width * 0.1, width * 0.9),
            "y0": np.random.uniform(height * 0.1, height * 0.9),
            "vx": np.random.uniform(6.0, 18.0),
            "vy": np.random.uniform(-14.0, -4.0),
            "r": max(1, int(np.random.randint(2, 4) * scale)),
            "alpha": np.random.uniform(0.35, 0.75),
        })

    for f in range(total_frames):
        t_sec = f / float(fps)
        t_norm = t_sec / max(0.001, float(dur))
        frame = base_canvas.copy()

        if hl_info and t_sec >= hl_time:
            sweep_progress = max(0.0, min(1.0, (t_sec - hl_time) / 0.35))
            cur_w = int(hl_info["w"] * sweep_progress)
            if cur_w > 4:
                frame = draw_highlighter_bar(frame, hl_info["x"], hl_info["y"], cur_w, hl_info["h"])

        if is_s01 and "map_coords" in meta:
            flight_progress = max(0.0, min(1.0, (t_sec - 1.0) / 7.5)) if t_sec >= 1.0 else 0.0
            mx, my, mw, mh = meta["map_coords"]
            map_bgr = render_cartography_flight_map(flight_progress, max(0.0, t_sec), width=mw, height=mh)
            frame = composite_plate_with_shadow(
                canvas=frame,
                plate=map_bgr,
                center_x=mx + mw // 2,
                center_y=my + mh // 2,
                angle_deg=0.0,
                shadow_blur=max(5, int(16 * scale)),
                shadow_alpha=0.45,
            )
            frame = draw_brass_pushpin(frame, mx + 16, my + 16, radius=max(6, int(12 * scale)))
            frame = draw_brass_pushpin(frame, mx + mw - 16, my + 16, radius=max(6, int(12 * scale)))

        elif meta.get("main_src") is not None:
            m_src = meta["main_src"]
            m_label = meta["main_label"]
            pB_w, pB_h = meta["main_dims"]
            right_cx, right_cy = meta["main_pos"]

            s_dyn = 1.00 + 0.08 * t_norm
            h_s, w_s = m_src.shape[:2]
            crop_w = max(2, int(w_s / s_dyn))
            crop_h = max(2, int(h_s / s_dyn))
            x_shift = int(math.sin(t_norm * math.pi) * 8.0)
            y_shift = int((1.0 - t_norm) * 6.0)
            cx_s = w_s // 2 + x_shift
            cy_s = h_s // 2 + y_shift
            x1 = max(0, min(w_s - crop_w, cx_s - crop_w // 2))
            y1 = max(0, min(h_s - crop_h, cy_s - crop_h // 2))
            crop_patch = m_src[y1:y1 + crop_h, x1:x1 + crop_w]
            pB = cv2.resize(crop_patch, (pB_w, pB_h), interpolation=cv2.INTER_LANCZOS4)

            pad_b = max(20, int(round(50 * scale)))
            pad_s = max(12, int(round(30 * scale)))
            ins = pad_s // 2
            framed_B = np.full((pB_h + pad_b, pB_w + pad_s, 3), (242, 246, 250), dtype=np.uint8)
            framed_B[ins:ins + pB_h, ins:ins + pB_w] = pB
            cv2.putText(
                framed_B,
                m_label[:34],
                (ins + 3, pB_h + int(pad_b * 0.76)),
                cv2.FONT_HERSHEY_SIMPLEX,
                max(0.28, 0.44 * scale),
                (45, 55, 70),
                1,
                cv2.LINE_AA,
            )
            frame = composite_plate_with_shadow(
                frame, framed_B, right_cx, right_cy, angle_deg=1.6, shadow_blur=max(5, int(22 * scale)), shadow_alpha=0.46
            )
            frame = draw_brass_pushpin(frame, right_cx - (pB_w // 2) + 16, right_cy - (pB_h // 2) + 12, radius=max(6, int(13 * scale)))

        if t_sec >= actual_drop_time and sec_plate is not None:
            cx, cy = meta["secondary_pos"]
            ang = meta["target_ang"]
            tx, ty = meta["tape_pos"]

            dt_drop = t_sec - actual_drop_time
            if dt_drop < 0.22:
                norm = dt_drop / 0.22
                bounce_dy = int((1.0 - norm) * -24 * scale)
                cur_ang = ang + (1.0 - norm) * 4.0
            else:
                bounce_dy = 0
                cur_ang = ang

            frame = composite_plate_with_shadow(frame, sec_plate, cx, cy + bounce_dy, angle_deg=cur_ang, shadow_blur=max(5, int(20 * scale)), shadow_alpha=0.55)
            frame = draw_frosted_scotch_tape(
                frame, tx, ty + bounce_dy, width=max(24, int(70 * scale)), height=max(10, int(24 * scale)), angle_deg=meta["tape_ang"]
            )

            if stamp_text and t_sec >= sec_drop_time:
                sx, sy = meta["stamp_pos"]
                frame = draw_rubber_stamp(frame, stamp_text, sx, sy, angle_deg=-15.0)

            if is_s01 and t_sec >= actual_drop_time:
                frame = overlay_3d_emoji(frame, "dollar", cx - int(180 * scale), cy + bounce_dy, size=max(48, int(130 * scale)))

        cam_cx, cam_cy, zoom, rot = get_scene_camera_trajectory(
            element.scene_id, t_norm, is_last_scene=is_last_scene, width=width, height=height
        )
        viewport = render_camera_viewport(frame, cam_cx, cam_cy, zoom, rot, width, height)

        spot_r = max(160.0, 650.0 * scale)
        for p in particles:
            px_p = int((p["x0"] + t_sec * p["vx"]) % width)
            py_p = int((p["y0"] + t_sec * p["vy"]) % height)
            dist = math.hypot(px_p - width / 2.0, py_p - height / 2.0)
            if dist < spot_r:
                p_alpha = (1.0 - (dist / spot_r)) * p["alpha"]
                color = np.array([215, 235, 255], dtype=np.float32)
                r_p = p["r"]
                y1_p, y2_p = max(0, py_p - r_p), min(height, py_p + r_p)
                x1_p, x2_p = max(0, px_p - r_p), min(width, px_p + r_p)
                if x2_p > x1_p and y2_p > y1_p:
                    roi_p = viewport[y1_p:y2_p, x1_p:x2_p].astype(np.float32)
                    viewport[y1_p:y2_p, x1_p:x2_p] = np.clip(roi_p * (1.0 - p_alpha) + color * p_alpha, 0, 255).astype(np.uint8)

        out.write(viewport)

    out.release()
    _encode_h264_mp4(tmp_raw, output_mp4, bitrate="14M")
    tmp_raw.unlink(missing_ok=True)
    return output_mp4


# ---------------------------------------------------------------------------
# Audio Synthesis & Multi-Layer Forensic Mixing (Local Kokoro-82M ONNX)
# ---------------------------------------------------------------------------
def synthesize_noir_narration(
    elements: List[StoryElement],
    cache_dir: Path,
    voice: str = "kokoro",
) -> Tuple[List[Path], List[float], List[List[Dict[str, Any]]]]:
    """Synthesizes humanized documentary noir narration using local Kokoro-82M ONNX."""
    from kokoro_onnx import Kokoro

    validated_voice = build_video._validate_kokoro_voice(voice)
    kokoro = Kokoro(str(KOKORO_MODEL), str(KOKORO_VOICES))
    whisper_model = None
    try:
        from faster_whisper import WhisperModel
        whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    except Exception:
        whisper_model = None

    if validated_voice == "kokoro":
        v_adam = kokoro.get_voice_style("am_adam")
        v_george = kokoro.get_voice_style("bm_george")
        doc_voice = (v_adam * 0.68 + v_george * 0.32).astype(np.float32)
    else:
        doc_voice = kokoro.get_voice_style(validated_voice)

    scene_audio_files: List[Path] = []
    scene_durations: List[float] = []
    scene_words: List[List[Dict[str, Any]]] = []

    eq_filter = (
        "highpass=f=75,"
        "equalizer=f=145:t=q:w=1.0:g=+2.8,"
        "equalizer=f=2900:t=q:w=1.4:g=+1.2,"
        "equalizer=f=3800:t=q:w=1.6:g=-1.8,"
        "lowpass=f=13500,"
        "deesser=i=0.5:m=0.4:f=0.5:s=o,"
        "acompressor=threshold=-16dB:ratio=2.2:attack=15:release=160,"
        "aecho=0.8:0.88:20:0.18,"
        "alimiter=limit=-1.2dB"
    )

    for el in elements:
        clean_text = el.text.replace("*", "")
        wav_path = cache_dir / f"forensic_{el.scene_id}.wav"
        raw_tmp = cache_dir / f"raw_forensic_{el.scene_id}.wav"

        needs_build = True
        if wav_path.exists():
            try:
                with wave.open(str(wav_path), "rb") as cur_wf:
                    if cur_wf.getframerate() == 48000 and cur_wf.getnchannels() == 2:
                        needs_build = False
            except Exception:
                needs_build = True

        if needs_build:
            chunks = el.speech_chunks
            if chunks:
                all_samples = []
                last_sr = 24000
                for chunk_text, spd, pause_after in chunks:
                    s_chunk, sr = kokoro.create(chunk_text, voice=doc_voice, speed=spd)
                    all_samples.append(s_chunk)
                    last_sr = sr
                    if pause_after > 0.0:
                        all_samples.append(np.zeros(int(pause_after * sr), dtype=np.float32))
                samples = np.concatenate(all_samples)
                sr = last_sr
            else:
                samples, sr = kokoro.create(clean_text, voice=doc_voice, speed=0.90)

            with wave.open(str(raw_tmp), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sr)
                audio_int16 = (samples * 32767.0).clip(-32768, 32767).astype(np.int16)
                wf.writeframes(audio_int16.tobytes())

            cmd = [
                "ffmpeg", "-y", "-i", str(raw_tmp),
                "-af", eq_filter,
                "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le",
                str(wav_path)
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            raw_tmp.unlink(missing_ok=True)

        with wave.open(str(wav_path), "rb") as wf:
            dur = wf.getnframes() / float(wf.getframerate())

        json_path = wav_path.with_suffix(".json")
        words: List[Dict[str, Any]] = []
        if json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    words = json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                raise MissingInputError(
                    stage="narration_timings",
                    artifact=json_path,
                    cause=f"Corrupt word timings json: {exc}",
                ) from exc

        if not words:
            if whisper_model is not None:
                segments, _ = whisper_model.transcribe(str(wav_path), word_timestamps=True)
                for s in segments:
                    for w in s.words:
                        words.append({"word": w.word.strip(), "start": round(w.start, 2), "end": round(w.end, 2)})
            else:
                audio_arr = build_video.decode_audio(wav_path)
                est = build_video._estimate_word_timings(clean_text, audio_arr)
                words = [{"word": str(w.get("text", "")), "start": float(w.get("start", 0.0)), "end": float(w.get("end", 0.0))} for w in est]
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(words, f, indent=2)

        scene_audio_files.append(wav_path)
        is_first = (len(scene_durations) == 0)
        is_last = (len(scene_durations) == len(elements) - 1)
        pre_pad = 0.0 if is_first else 0.55
        post_pad = 2.00 if is_last else 0.80
        scene_clip_dur = round(pre_pad + dur + post_pad, 2)
        scene_durations.append(scene_clip_dur)
        scene_words.append(words)
        logger.info(f"  [{el.scene_id}] {dur:.2f}s speech -> {scene_clip_dur:.2f}s clip (pre={pre_pad:.2f}s, post={post_pad:.2f}s)")

    return scene_audio_files, scene_durations, scene_words


def assemble_master_voice_track(
    scene_audios: List[Path],
    speech_starts: List[float],
    total_duration: float,
    output_wav: Path,
    sample_rate: int = 48000,
) -> Path:
    """Assembles the master narration audio track by placing each scene's speech at its exact timeline start."""
    total_samples = int(total_duration * sample_rate)
    master_buf = np.zeros((total_samples, 2), dtype=np.int16)

    for sa, start_sec in zip(scene_audios, speech_starts):
        with wave.open(str(sa), "rb") as wf:
            n_frames = wf.getnframes()
            raw_bytes = wf.readframes(n_frames)
            data = np.frombuffer(raw_bytes, dtype=np.int16)
            if wf.getnchannels() == 2:
                data = data.reshape(-1, 2)
            else:
                data = np.column_stack([data, data])

            start_idx = int(start_sec * sample_rate)
            end_idx = min(total_samples, start_idx + len(data))
            n_copy = end_idx - start_idx
            if n_copy > 0:
                master_buf[start_idx:end_idx] = data[:n_copy]

    with wave.open(str(output_wav), "wb") as out_wf:
        out_wf.setnchannels(2)
        out_wf.setsampwidth(2)
        out_wf.setframerate(sample_rate)
        out_wf.writeframes(master_buf.tobytes())

    return output_wav


# ---------------------------------------------------------------------------
# Master Video Production & 3-Tier Layered Audio Mixer
# ---------------------------------------------------------------------------
def _resolve_project_dir(project_slug: str, project_dir: Optional[Path] = None) -> Path:
    if project_dir is not None:
        return Path(project_dir)
    for parent in (REPO_ROOT / "projects", REPO_ROOT / "shorts", REPO_ROOT / "long_form"):
        cand = parent / project_slug
        if cand.exists() and (cand / "project.json").exists():
            return cand
    for parent in (REPO_ROOT / "projects", REPO_ROOT / "shorts", REPO_ROOT / "long_form"):
        cand = parent / project_slug
        if cand.exists():
            return cand
    return REPO_ROOT / "projects" / project_slug


def produce_picture_book_video(
    elements: Optional[List[StoryElement]] = None,
    project_slug: str = "",
    output_mp4: Optional[Path] = None,
    *,
    project_dir: Optional[Path] = None,
    project_data: Optional[Dict[str, Any]] = None,
    generate_images: bool = False,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> Path:
    """Produces the complete broadcast-quality Living Picture-Book Documentary film."""
    if not project_slug and not project_dir:
        raise MissingInputError(
            stage="produce_picture_book_video",
            artifact="project_slug",
            cause="Either project_slug or project_dir must be provided",
        )
    if not project_slug and project_dir:
        project_slug = project_dir.name
    resolved_dir = _resolve_project_dir(project_slug, project_dir)
    if project_data is None and (resolved_dir / "project.json").exists():
        try:
            project_data = json.loads((resolved_dir / "project.json").read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise MissingInputError(
                stage="picture_book",
                artifact=resolved_dir / "project.json",
                cause=f"Corrupt or unreadable project.json: {exc}",
            ) from exc

    if elements is None:
        if project_data and isinstance(project_data.get("scenes"), list) and project_data["scenes"]:
            elements = story_elements_from_project(project_data)
        else:
            raise MissingInputError(
                stage="picture_book",
                artifact=resolved_dir / "project.json",
                cause=f"produce_picture_book_video requires project.json scenes for '{project_slug}'",
            )

    fmt_type = (project_data or {}).get("format", "long")
    render_w = width or (1080 if fmt_type == "short" else WIDTH)
    render_h = height or (1920 if fmt_type == "short" else HEIGHT)
    voice = (project_data or {}).get("voice", "kokoro")

    images_dir = resolved_dir / "images"
    cutouts_dir = images_dir / "cutouts"
    videos_dir = resolved_dir / "videos"
    cache_dir = resolved_dir / "cache"
    output_dir = REPO_ROOT / "output"

    for d in [images_dir, videos_dir, cache_dir, output_dir]:
        d.mkdir(parents=True, exist_ok=True)

    if output_mp4 is None:
        suffix = "9x16" if render_h > render_w else "16x9"
        output_mp4 = output_dir / f"{project_slug}_living_picture_book_{suffix}.mp4"

    logger.info(f"=== PRODUCING LIVING PICTURE-BOOK FILM: {project_slug} ({render_w}x{render_h}) ===")
    logger.info(f"Total Scenes: {len(elements)}")

    logger.info("=== STEP 1: KOKORO-82M NEURAL NARRATION SYNTHESIS & NOIR CHUNKING ===")
    scene_audios, scene_durs, scene_words = synthesize_noir_narration(elements, cache_dir, voice=voice)

    logger.info("=== STEP 2: RENDERING 30FPS LIVING PICTURE-BOOK SCENE CLIPS ===")
    raw_clips: List[Path] = []
    for idx, el in enumerate(elements):
        clip_p = videos_dir / f"living_book_{el.scene_id}.mp4"
        dur = scene_durs[idx]
        words = scene_words[idx]
        is_first = (idx == 0)
        is_last = (idx == len(elements) - 1)

        render_dynamic_scene_clip(
            element=el,
            images_dir=images_dir,
            cutouts_dir=cutouts_dir,
            dur=dur,
            words=words,
            output_mp4=clip_p,
            is_first_scene=is_first,
            is_last_scene=is_last,
            fps=30,
            width=render_w,
            height=render_h,
        )
        raw_clips.append(clip_p)
        logger.info(f"  ✓ Rendered living motion clip: {clip_p.name} ({dur:.2f}s)")

    logger.info("=== STEP 3: 1X1 PAGE-FLIP TIMELINE STITCH ===")
    trans_dur = 0.55 if len(raw_clips) > 1 else 0.0
    timeline_offsets: List[float] = [0.0]
    speech_starts: List[float] = [0.0]
    cur_offset = 0.0

    visual_timeline = cache_dir / "visual_timeline_living_book.mp4"
    if len(raw_clips) == 1:
        shutil.copy2(raw_clips[0], visual_timeline)
    else:
        filter_parts = []
        cur_v = "[0:v]"
        for i in range(len(raw_clips) - 1):
            dur_a = scene_durs[i]
            cur_offset += dur_a - trans_dur
            timeline_offsets.append(round(cur_offset, 3))
            speech_starts.append(round(cur_offset + trans_dur, 3))
            next_v = f"[{i+1}:v]"
            out_v = f"[v{i+1}]"
            filter_parts.append(f"{cur_v}{next_v}xfade=transition=squeezeh:duration={trans_dur}:offset={cur_offset:.2f}{out_v}")
            cur_v = out_v

        full_filter = ";".join(filter_parts)
        enc = "h264_videotoolbox" if sys.platform == "darwin" else "libx264"
        cmd_stitch = ["ffmpeg", "-y"]
        for rc in raw_clips:
            cmd_stitch.extend(["-i", str(rc)])
        cmd_stitch.extend(["-filter_complex", full_filter, "-map", cur_v, "-c:v", enc])
        if enc == "h264_videotoolbox":
            cmd_stitch.extend(["-b:v", "14M", "-pix_fmt", "yuv420p", str(visual_timeline)])
        else:
            cmd_stitch.extend(["-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p", str(visual_timeline)])
        proc = subprocess.run(cmd_stitch, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if proc.returncode != 0 or not visual_timeline.exists() or visual_timeline.stat().st_size == 0:
            raise RenderingError(
                stage="stitch_clips",
                artifact=str(visual_timeline),
                cause=f"Failed to stitch living book clips with {enc} (returncode={proc.returncode})",
            )

    logger.info("=== STEP 4: 3-TIER CALIBRATED DECIBEL-BUDGET AUDIO MIXING ===")
    total_voice_dur = max(1.0, sum(scene_durs) - max(0, len(scene_durs) - 1) * trans_dur)

    master_voice = cache_dir / "master_voice_living.wav"
    assemble_master_voice_track(
        scene_audios=scene_audios,
        speech_starts=speech_starts,
        total_duration=total_voice_dur,
        output_wav=master_voice,
    )

    drone_bed_wav = cache_dir / "drone_bed_continuous.wav"
    generate_continuous_drone_bed(duration_sec=total_voice_dur + 2.0, output_wav=drone_bed_wav)

    master_sfx = cache_dir / "master_sfx_living.wav"
    sfx_inputs: List[str] = []
    amix_filters: List[str] = []
    sfx_count = 0

    ensure_documentary_foley_pack()

    for i in range(1, len(elements)):
        trans_start = timeline_offsets[i]
        sfx_count = build_triple_layer_page_flip_sfx(
            cue_time=0.0,
            current_time=trans_start,
            sfx_inputs=sfx_inputs,
            amix_filters=amix_filters,
            sfx_count=sfx_count,
        )

    for idx, el in enumerate(elements):
        words = scene_words[idx]
        sp_start = speech_starts[idx]
        wav_path = scene_audios[idx]
        scene_pauses = detect_speech_pauses(wav_path)

        for cue in el.sound_cues:
            sfx_f = SFX_DIR / f"{cue['name']}.mp3"
            if not sfx_f.exists():
                sfx_f = SFX_DIR / f"{cue['name']}.wav"
            if sfx_f.exists():
                target_word = cue.get("word_trigger", "").lower().strip(".,!?\"'")
                word_offset = None
                if target_word:
                    for w in words:
                        w_clean = str(w.get("word") or w.get("text") or "").lower().strip(".,!?\"'")
                        if target_word in w_clean or (w_clean and w_clean in target_word):
                            word_offset = float(w.get("start", 0.0))
                            break
                        if target_word == "twenty" and ("20" in w_clean or "$20" in w_clean):
                            word_offset = float(w.get("start", 0.0))
                            break

                raw_offset = word_offset if word_offset is not None else cue.get("offset", 0.5)
                cue_db = get_cue_decibel(cue["name"])
                is_climax = cue_db >= DECIBEL_BUDGET["climax_blast"] - 0.5
                if is_climax:
                    snapped_offset = snap_cue_to_breath_pause(raw_offset, scene_pauses, search_window_sec=1.0)
                else:
                    snapped_offset = raw_offset

                offset = sp_start + snapped_offset
                vol = get_cue_linear_gain(cue["name"])
                sfx_inputs.extend(["-i", str(sfx_f)])
                delay_ms = int(offset * 1000)

                pan_zone = cue.get("pan", "right")
                if pan_zone == "left":
                    pan_filter = "pan=stereo|c0=0.75*c0|c1=0.25*c0"
                elif pan_zone == "center":
                    pan_filter = "volume=1.0"
                else:
                    pan_filter = "pan=stereo|c0=0.25*c0|c1=0.75*c0"

                amix_filters.append(f"[{sfx_count+1}:a]adelay={delay_ms}|{delay_ms},{pan_filter},volume={vol:.3f}[sfx{sfx_count}]")
                sfx_count += 1

    if sfx_count > 0:
        sfx_mix_filter = ";".join(amix_filters) + ";" + "".join(f"[sfx{i}]" for i in range(sfx_count)) + f"amix=inputs={sfx_count}:normalize=0[sfx_out]"
        cmd_sfx = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo:d={total_voice_dur:.2f}"]
        cmd_sfx.extend(sfx_inputs)
        cmd_sfx.extend(["-filter_complex", sfx_mix_filter, "-map", "[sfx_out]", "-c:a", "pcm_s16le", str(master_sfx)])
        subprocess.run(cmd_sfx, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    else:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo:d={total_voice_dur:.2f}", "-c:a", "pcm_s16le", str(master_sfx)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
        )

    full_bgm_wav = cache_dir / "master_bgm_crossfade.wav"
    if BGM_FILE_1.exists() and BGM_FILE_2.exists() and total_voice_dur > 20.0:
        cmd_bgm = [
            "ffmpeg", "-y",
            "-i", str(BGM_FILE_1),
            "-i", str(BGM_FILE_2),
            "-filter_complex",
            "[0:a]atrim=0:140,asetpts=PTS-STARTPTS[a1];[1:a]atrim=0:150,asetpts=PTS-STARTPTS[a2];[a1][a2]acrossfade=d=8:c1=tri:c2=tri[bgm_full]",
            "-map", "[bgm_full]",
            "-t", f"{total_voice_dur:.2f}",
            "-c:a", "pcm_s16le",
            str(full_bgm_wav),
        ]
        subprocess.run(cmd_bgm, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    elif BGM_FILE_1.exists():
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(BGM_FILE_1), "-t", f"{total_voice_dur:.2f}", "-c:a", "pcm_s16le", str(full_bgm_wav)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
        )
    else:
        shutil.copy2(drone_bed_wav, full_bgm_wav)

    mixed_audio = cache_dir / "mixed_audio_living.wav"
    drone_vol = round(db_to_linear(DECIBEL_BUDGET["ambient_bed"]), 3)
    audio_filter = (
        "[0:a]volume=1.0[voice];"
        "[1:a]volume=1.0[sfx];"
        "[2:a]volume=0.18[bgm];"
        f"[3:a]volume={drone_vol}[drone];"
        "[voice][bgm]sidechaincompress=threshold=0.08:ratio=4.0:attack=15:release=320[ducked_bgm];"
        "[voice][sfx][ducked_bgm][drone]amix=inputs=4:normalize=0[mixed]"
    )
    cmd_mix = [
        "ffmpeg", "-y",
        "-i", str(master_voice),
        "-i", str(master_sfx),
        "-i", str(full_bgm_wav),
        "-i", str(drone_bed_wav),
        "-filter_complex", audio_filter,
        "-map", "[mixed]",
        "-t", f"{total_voice_dur:.2f}",
        str(mixed_audio),
    ]
    subprocess.run(cmd_mix, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    logger.info("=== STEP 5: FINAL BROADCAST MUX & LOUDNORM (-14.0 LUFS) ===")
    cmd_mux = [
        "ffmpeg", "-y",
        "-i", str(visual_timeline),
        "-i", str(mixed_audio),
        "-c:v", "copy",
        "-af", "loudnorm=I=-14.0:TP=-1.5:LRA=7.0",
        "-c:a", "aac",
        "-b:a", "320k",
        "-ar", "48000",
        "-ac", "2",
        "-shortest",
        str(output_mp4),
    ]
    subprocess.run(cmd_mux, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    cmd_probe = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration,size,bit_rate:stream=width,height,codec_name,sample_rate",
        "-of", "json",
        str(output_mp4),
    ]
    probe_res = subprocess.run(cmd_probe, capture_output=True, text=True, check=True)
    probe_data = json.loads(probe_res.stdout)
    fmt = probe_data.get("format", {})
    dur_final = float(fmt.get("duration", 0.0))
    size_mb = float(fmt.get("size", 0.0)) / (1024 * 1024)

    logger.info(f"✓ Master Living Picture-Book Film Rendered: {output_mp4}")
    logger.info(f"  Duration: {dur_final:.2f}s ({dur_final / 60:.2f} mins) | Size: {size_mb:.2f} MB")

    logger.info("=== STEP 6: PRE-RELEASE POP SCAN & CONTACT SHEET QA ===")
    flags, diffs = scan_video_for_pops(output_mp4)
    contact_sheet = REPO_ROOT / "output" / f"{project_slug}_contact_sheet.jpg"
    n_samples = min(18, max(6, len(elements)))
    ts_list = [f.get("time_sec", f["frame"] / 30.0) for f in flags[:n_samples]] if flags else [i * (dur_final / float(n_samples)) for i in range(n_samples)]
    generate_contact_sheet(output_mp4, ts_list, contact_sheet, cols=min(6, n_samples))

    doc_title = str((project_data or {}).get("title") or (elements[0].title if elements else project_slug))
    doc_topic = str((project_data or {}).get("topic") or doc_title)
    doc_id = str((project_data or {}).get("id") or "LV-01-FORENSIC")

    record_ledger_event(
        slug=project_slug,
        stage="render",
        status="PASS",
        details={
            "video_id": doc_id,
            "title": doc_title,
            "topic": doc_topic,
            "output_file": str(output_mp4),
            "scenes": len(elements),
            "notes": f"Living Picture Book v7.0; {len(elements)} scenes; duration: {dur_final:.1f}s; {size_mb:.1f} MB; -14 LUFS",
        },
        evidence={"duration": dur_final, "size_mb": size_mb, "lufs": -14.0},
    )

    return output_mp4


def main() -> int:
    parser = argparse.ArgumentParser(description="FrameForge Living Picture-Book Engine v7.0")
    parser.add_argument("--slug", type=str, required=True, help="Project slug")
    parser.add_argument("--output", type=Path, default=None, help="Output MP4 path")
    args = parser.parse_args()

    produce_picture_book_video(
        project_slug=args.slug,
        output_mp4=args.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
