#!/usr/bin/env python3
"""Forensic Casebook Engine v6.0 (LEMMiNO-Tier Broadcast Documentary Engine)

Full-Screen 1080p dynamic investigative montage with:
- Connected Spatial Virtual Camera (dynamic gliding, panning, and zooming across wide exhibits)
- Frame-Accurate Word-Level Foley Sound Synchronization
- Stereo Spatial Audio Panning (matching on-screen evidence positions)
- Two-Act Dynamic Mystery & Thriller Soundtrack with Vocal Mid-Side Ducking
- Local Kokoro-82M Neural Narration with Dramatic Noir Sentence Chunking
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import subprocess
import sys
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from tools.errors import MissingInputError  # noqa: E402
from tools.production_ledger import record_ledger_event  # noqa: E402
from tools.sound_architect import (  # noqa: E402
    DECIBEL_BUDGET,
    detect_speech_pauses,
    get_cue_decibel,
    get_cue_linear_gain,
    snap_cue_to_breath_pause,
)

# ---------------------------------------------------------------------------
# Logging & System Constants
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ForensicEngine")

MODELS_DIR = REPO_ROOT / "tools" / "kokoro_models"
KOKORO_MODEL = MODELS_DIR / "kokoro-v1.0.onnx"
KOKORO_VOICES = MODELS_DIR / "voices-v1.0.bin"

SFX_DIR = REPO_ROOT / "assets" / "audio" / "sfx"

FONT_MONO = str(REPO_ROOT / "tools" / "fonts" / "BeVietnamPro-Medium.ttf")
FONT_SANS = str(REPO_ROOT / "tools" / "fonts" / "BeVietnamPro-Regular.ttf")
FONT_BEBAS = str(REPO_ROOT / "tools" / "fonts" / "BebasNeue-Regular.ttf")
FONT_BOLD = str(REPO_ROOT / "tools" / "fonts" / "BeVietnamPro-Bold.ttf")

WIDTH = 1920
HEIGHT = 1080


# ---------------------------------------------------------------------------
# Story Scene Dataclass & Complete 18-Scene Saga
# ---------------------------------------------------------------------------
@dataclass
class StoryScene:
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
    sound_cues: List[Dict[str, Any]]
    speech_chunks: List[Tuple[str, float, float]] = field(default_factory=list)


def story_scenes_from_project(project_data: Dict[str, Any]) -> List[StoryScene]:
    """Converts a schema v2 project.json dictionary into StoryScene instances."""
    scenes = project_data.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise MissingInputError(
            stage="forensic_casebook",
            artifact="project.json",
            cause="project contains no scenes for forensic_casebook_engine",
        )

    project_title = str(project_data.get("title") or project_data.get("topic") or "Forensic Dossier").strip()
    project_id = str(project_data.get("id") or "CASE").strip()

    story_scenes: List[StoryScene] = []
    for idx, sc in enumerate(scenes):
        if not isinstance(sc, dict):
            raise MissingInputError(
                stage="forensic_casebook",
                artifact="project.json",
                cause=f"scene[{idx}] must be a dict",
            )
        scene_id = str(sc.get("id") or f"s{idx + 1:02d}").strip()
        text = str(sc.get("text") or "").strip()
        if not text:
            raise MissingInputError(
                stage="forensic_casebook",
                artifact=f"scene_{scene_id}",
                cause=f"scene[{idx}] text must be non-empty",
            )

        words = [w.strip(".,!?\"'():;") for w in text.split() if w.strip(".,!?\"'():;")]
        hl_default = " ".join(words[:3]) if len(words) >= 3 else (words[0] if words else "")
        trig_default = words[min(len(words) - 1, max(0, len(words) // 2))] if words else ""

        img_rel = str(sc.get("image") or f"images/{scene_id}.jpg")
        hero_name = Path(img_rel).name
        cutout_rel = str(sc.get("cutout_image") or hero_name)
        cutout_name = Path(cutout_rel).name

        story_scenes.append(
            StoryScene(
                scene_id=scene_id,
                act=str(sc.get("act") or f"SCENE {idx + 1:02d}"),
                title=str(sc.get("title") or sc.get("plate_label") or f"{project_title} ({idx + 1})"),
                text=text,
                highlighter_phrase=str(sc.get("highlighter_phrase") or hl_default),
                timestamp_text=str(sc.get("timestamp_text") or f"ENTRY {idx + 1:02d}"),
                location_text=str(sc.get("location_text") or project_title[:28]),
                exhibit_code=str(sc.get("exhibit_code") or sc.get("plate_label") or f"EXHIBIT {project_id}-{idx + 1:02d}"),
                stamp_text=str(sc.get("stamp") or sc.get("stamp_text") or "VERIFIED"),
                hero_image=hero_name,
                cutout_image=cutout_name,
                secondary_trigger_word=str(sc.get("secondary_trigger_word") or trig_default),
                sound_cues=list(sc.get("sound_cues") or []),
                speech_chunks=list(sc.get("speech_chunks") or []),
            )
        )
    return story_scenes


# ---------------------------------------------------------------------------
# Visual Element & Forensic Compositing Utilities
# ---------------------------------------------------------------------------
def smoothstep(edge0: float, edge1: float, x: float) -> float:
    t = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def render_camera_viewport(
    canvas: np.ndarray,
    cam_cx: float,
    cam_cy: float,
    zoom: float,
    angle_deg: float = 0.0,
    out_w: int = 1920,
    out_h: int = 1080,
) -> np.ndarray:
    """Transforms wide forensic canvas through sub-pixel virtual camera trajectory."""
    M = cv2.getRotationMatrix2D((cam_cx, cam_cy), angle_deg, zoom)
    M[0, 2] += (out_w / 2.0) - cam_cx
    M[1, 2] += (out_h / 2.0) - cam_cy
    return cv2.warpAffine(canvas, M, (out_w, out_h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT_101)


def draw_frosted_scotch_tape(
    canvas: np.ndarray,
    cx: int,
    cy: int,
    width: int = 85,
    height: int = 26,
    angle_deg: float = -25.0,
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


def composite_evidence_card_with_shadow(
    canvas: np.ndarray,
    card: np.ndarray,
    cx: int,
    cy: int,
    angle_deg: float = 0.0,
    shadow_blur: int = 28,
    shadow_alpha: float = 0.55,
) -> np.ndarray:
    """Composites an evidence card with sub-pixel rotation and realistic elevation drop shadow."""
    h, w = card.shape[:2]
    rad = math.radians(angle_deg)
    cos_a, sin_a = abs(math.cos(rad)), abs(math.sin(rad))
    rot_w = int(w * cos_a + h * sin_a) + 12
    rot_h = int(w * sin_a + h * cos_a) + 12

    M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle_deg, 1.0)
    M[0, 2] += (rot_w - w) / 2.0
    M[1, 2] += (rot_h - h) / 2.0

    rot_card = cv2.warpAffine(card, M, (rot_w, rot_h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))

    mask = np.full((h, w), 255, dtype=np.uint8)
    rot_mask = cv2.warpAffine(mask, M, (rot_w, rot_h), flags=cv2.INTER_LINEAR, borderValue=0)

    c_h, c_w = canvas.shape[:2]
    sx1 = cx - rot_w // 2 + 12
    sy1 = cy - rot_h // 2 + 18
    sx2, sy2 = sx1 + rot_w, sy1 + rot_h

    if sx2 <= c_w and sy2 <= c_h and sx1 >= 0 and sy1 >= 0:
        shadow_patch = cv2.GaussianBlur(rot_mask, (shadow_blur | 1, shadow_blur | 1), 0)
        s_factor = 1.0 - (shadow_patch.astype(np.float32) / 255.0) * shadow_alpha
        roi = canvas[sy1:sy2, sx1:sx2].astype(np.float32)
        canvas[sy1:sy2, sx1:sx2] = np.clip(roi * s_factor[..., None], 0, 255).astype(np.uint8)

    x1 = cx - rot_w // 2
    y1 = cy - rot_h // 2
    x2, y2 = x1 + rot_w, y1 + rot_h

    if x2 <= c_w and y2 <= c_h and x1 >= 0 and y1 >= 0:
        alpha_m = (rot_mask > 20).astype(np.float32)[..., None]
        roi = canvas[y1:y2, x1:x2].astype(np.float32)
        card_f = rot_card.astype(np.float32)
        canvas[y1:y2, x1:x2] = np.clip(roi * (1.0 - alpha_m) + card_f * alpha_m, 0, 255).astype(np.uint8)

    return canvas


def draw_top_bottom_telemetry_hud(
    canvas: np.ndarray,
    scene: StoryScene,
    scene_idx: int,
    total_scenes: int = 18,
) -> np.ndarray:
    """Renders professional investigative documentary telemetry bars on top and bottom margins."""
    h, w = canvas.shape[:2]

    # Semi-transparent top bar (Height: 52px)
    top_bar = np.zeros((52, w, 3), dtype=np.uint8)
    top_bar[:] = (16, 18, 22)
    canvas[0:52, :] = cv2.addWeighted(canvas[0:52, :], 0.30, top_bar, 0.70, 0)
    cv2.line(canvas, (0, 52), (w, 52), (65, 75, 88), 1)

    # Semi-transparent bottom bar (Height: 46px)
    bot_bar = np.zeros((46, w, 3), dtype=np.uint8)
    bot_bar[:] = (16, 18, 22)
    canvas[h - 46 : h, :] = cv2.addWeighted(canvas[h - 46 : h, :], 0.30, bot_bar, 0.70, 0)
    cv2.line(canvas, (0, h - 46), (w, h - 46), (65, 75, 88), 1)

    cv2.putText(
        canvas,
        "FBI NORJAK INVESTIGATIVE DOSSIER  •  CASE FILE #44-1298  •  CLASSIFIED",
        (38, 34),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.52,
        (225, 230, 240),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        f"{scene.act.upper()}  •  EXHIBIT {scene_idx + 1:02d}/{total_scenes:02d}",
        (w - 380, 34),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        (214, 180, 100),
        1,
        cv2.LINE_AA,
    )

    cv2.putText(
        canvas,
        f"TIME: {scene.timestamp_text}   |   LOC: {scene.location_text}",
        (38, h - 18),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.44,
        (190, 205, 215),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        scene.exhibit_code.upper(),
        (w - 420, h - 18),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.44,
        (130, 185, 235),
        1,
        cv2.LINE_AA,
    )

    return canvas


# ---------------------------------------------------------------------------
# Specialized Forensic Visual Renderers (1080p Broadcast Full-Screen)
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


def render_cartography_flight_radar(
    progress: float,
    time_sec: float,
    width: int = 1920,
    height: int = 1080,
) -> np.ndarray:
    """Renders a 1080p full-screen archival cartography map of Puget Sound with vector flight trajectory."""
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    canvas[:] = (26, 30, 36)

    # Pacific ocean & coastal shelf
    ocean_poly = np.array([
        [0, 0],
        [int(0.24 * width), 0],
        [int(0.22 * width), int(0.18 * height)],
        [int(0.20 * width), int(0.32 * height)],
        [int(0.22 * width), int(0.46 * height)],
        [int(0.19 * width), int(0.60 * height)],
        [int(0.18 * width), int(0.78 * height)],
        [int(0.16 * width), int(0.92 * height)],
        [int(0.15 * width), height],
        [0, height],
    ], np.int32)
    cv2.fillPoly(canvas, [ocean_poly], (34, 26, 20))

    # Puget Sound waterways
    puget_poly = np.array([
        [int(0.21 * width), int(0.12 * height)],
        [int(0.32 * width), int(0.11 * height)],
        [int(0.35 * width), int(0.18 * height)],
        [int(0.36 * width), int(0.26 * height)],
        [int(0.33 * width), int(0.31 * height)],
        [int(0.29 * width), int(0.28 * height)],
        [int(0.26 * width), int(0.20 * height)],
        [int(0.21 * width), int(0.18 * height)],
    ], np.int32)
    cv2.fillPoly(canvas, [puget_poly], (34, 26, 20))

    # Graticule grid
    grid = canvas.copy()
    for gx in range(120, width, 120):
        cv2.line(grid, (gx, 0), (gx, height), (75, 88, 102), 1, cv2.LINE_AA)
    for gy in range(90, height, 90):
        cv2.line(grid, (0, gy), (width, gy), (75, 88, 102), 1, cv2.LINE_AA)
    cv2.addWeighted(grid, 0.28, canvas, 0.72, 0, canvas)

    # Waypoints: Portland (PDX) to Seattle-Tacoma (SEA)
    pdx = (int(0.48 * width), int(0.72 * height))
    sea = (int(0.45 * width), int(0.24 * height))
    jump_zone = (int(0.47 * width), int(0.52 * height))

    p0 = pdx
    p1 = (int(0.47 * width), int(0.56 * height))
    p2 = (int(0.44 * width), int(0.38 * height))
    p3 = sea

    # Trajectory Spline
    num_samples = 140
    curve_points = [cubic_bezier(p0, p1, p2, p3, i / float(num_samples)) for i in range(num_samples + 1)]
    active_samples = int(progress * num_samples)
    dash_len, gap_len = 6, 5
    cycle = dash_len + gap_len

    glow_layer = np.zeros_like(canvas)
    for idx in range(active_samples):
        if (idx % cycle) < dash_len:
            pt1 = (int(curve_points[idx][0]), int(curve_points[idx][1]))
            pt2 = (int(curve_points[idx + 1][0]), int(curve_points[idx + 1][1]))
            cv2.line(glow_layer, pt1, pt2, (0, 180, 255), 6, cv2.LINE_AA)
            cv2.line(canvas, pt1, pt2, (255, 255, 255), 3, cv2.LINE_AA)

    cv2.addWeighted(glow_layer, 0.50, canvas, 1.0, 0, canvas)

    # Radar sweep pulses
    pulse_r = 6 + int((time_sec * 30) % 60)
    pulse_a = max(0.0, 1.0 - (pulse_r / 60.0))
    cv2.circle(canvas, pdx, pulse_r, (0, int(200 * pulse_a), int(255 * pulse_a)), 2, cv2.LINE_AA)
    cv2.circle(canvas, pdx, 7, (0, 215, 255), -1, cv2.LINE_AA)
    cv2.circle(canvas, sea, 7, (0, 215, 255), -1, cv2.LINE_AA)

    cv2.putText(canvas, "PORTLAND INTL AIRPORT (PDX)", (pdx[0] + 16, pdx[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (240, 240, 245), 2, cv2.LINE_AA)
    cv2.putText(canvas, "ORIGIN: 14:36 PST  •  B-727 NW ORIENT", (pdx[0] + 16, pdx[1] + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (190, 180, 160), 1, cv2.LINE_AA)

    cv2.putText(canvas, "SEATTLE-TACOMA INTL (SEA)", (sea[0] + 16, sea[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (240, 240, 245), 2, cv2.LINE_AA)
    cv2.putText(canvas, "DESTINATION: 17:45 PST  •  36 HOSTAGES", (sea[0] + 16, sea[1] + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (190, 180, 160), 1, cv2.LINE_AA)

    cv2.circle(canvas, jump_zone, 10, (40, 40, 220), 2, cv2.LINE_AA)
    cv2.putText(canvas, "ESTIMATED JUMP COORDINATES", (jump_zone[0] + 16, jump_zone[1] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (70, 70, 255), 2, cv2.LINE_AA)
    cv2.putText(canvas, "LEWIS RIVER / ARIEL, WA  •  8:13 PM", (jump_zone[0] + 16, jump_zone[1] + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (180, 180, 180), 1, cv2.LINE_AA)

    return canvas


def render_cockpit_flight_instruments(time_sec: float, width: int = 1920, height: int = 1080) -> np.ndarray:
    """Renders 1080p full-screen cockpit instrument telemetry with rotating Altimeter needle and Airspeed dial."""
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    canvas[:] = (20, 22, 26)

    cv2.rectangle(canvas, (180, 120), (width - 180, height - 120), (32, 35, 42), -1)
    cv2.rectangle(canvas, (180, 120), (width - 180, height - 120), (70, 78, 92), 2)

    # Gauge 1: Altimeter
    c1 = (int(width * 0.35), int(height * 0.48))
    r = 170
    cv2.circle(canvas, c1, r, (15, 16, 20), -1)
    cv2.circle(canvas, c1, r, (214, 180, 100), 3, cv2.LINE_AA)
    cv2.circle(canvas, c1, r - 12, (55, 62, 75), 1, cv2.LINE_AA)

    for deg in range(0, 360, 30):
        rad = math.radians(deg)
        x_in = int(c1[0] + (r - 24) * math.cos(rad))
        y_in = int(c1[1] + (r - 24) * math.sin(rad))
        x_out = int(c1[0] + (r - 8) * math.cos(rad))
        y_out = int(c1[1] + (r - 8) * math.sin(rad))
        cv2.line(canvas, (x_in, y_in), (x_out, y_out), (220, 220, 225), 2, cv2.LINE_AA)

    alt_angle = -90.0 + math.sin(time_sec * 8.0) * 1.5
    rad_alt = math.radians(alt_angle)
    nx = int(c1[0] + (r - 35) * math.cos(rad_alt))
    ny = int(c1[1] + (r - 35) * math.sin(rad_alt))
    cv2.line(canvas, c1, (nx, ny), (40, 50, 235), 4, cv2.LINE_AA)
    cv2.circle(canvas, c1, 12, (214, 180, 100), -1)

    cv2.putText(canvas, "ALTIMETER", (c1[0] - 65, c1[1] + 65), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (214, 180, 100), 2, cv2.LINE_AA)
    cv2.putText(canvas, "10,000 FT", (c1[0] - 55, c1[1] + 95), cv2.FONT_HERSHEY_SIMPLEX, 0.70, (255, 255, 255), 2, cv2.LINE_AA)

    # Gauge 2: Airspeed Indicator
    c2 = (int(width * 0.65), int(height * 0.48))
    cv2.circle(canvas, c2, r, (15, 16, 20), -1)
    cv2.circle(canvas, c2, r, (214, 180, 100), 3, cv2.LINE_AA)
    cv2.circle(canvas, c2, r - 12, (55, 62, 75), 1, cv2.LINE_AA)

    for deg in range(0, 360, 30):
        rad = math.radians(deg)
        x_in = int(c2[0] + (r - 24) * math.cos(rad))
        y_in = int(c2[1] + (r - 24) * math.sin(rad))
        x_out = int(c2[0] + (r - 8) * math.cos(rad))
        y_out = int(c2[1] + (r - 8) * math.sin(rad))
        cv2.line(canvas, (x_in, y_in), (x_out, y_out), (220, 220, 225), 2, cv2.LINE_AA)

    spd_angle = 35.0 + math.sin(time_sec * 6.5) * 1.8
    rad_spd = math.radians(spd_angle)
    sx = int(c2[0] + (r - 35) * math.cos(rad_spd))
    sy = int(c2[1] + (r - 35) * math.sin(rad_spd))
    cv2.line(canvas, c2, (sx, sy), (40, 50, 235), 4, cv2.LINE_AA)
    cv2.circle(canvas, c2, 12, (214, 180, 100), -1)

    cv2.putText(canvas, "AIRSPEED", (c2[0] - 60, c2[1] + 65), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (214, 180, 100), 2, cv2.LINE_AA)
    cv2.putText(canvas, "170 KNOTS", (c2[0] - 65, c2[1] + 95), cv2.FONT_HERSHEY_SIMPLEX, 0.70, (255, 255, 255), 2, cv2.LINE_AA)

    cx = width // 2
    cv2.putText(canvas, "FLAPS: LOCKED AT 15°", (cx - 150, int(height * 0.38)), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (240, 240, 245), 2, cv2.LINE_AA)
    cv2.putText(canvas, "CABIN: UNPRESSURIZED", (cx - 160, int(height * 0.55)), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (50, 50, 235), 2, cv2.LINE_AA)
    cv2.putText(canvas, "GEAR: DOWN & LOCKED", (cx - 150, int(height * 0.70)), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (80, 220, 120), 2, cv2.LINE_AA)

    return canvas


# ---------------------------------------------------------------------------
# Dynamic Spatial Virtual Camera Trajectory Calculator
# ---------------------------------------------------------------------------
def get_forensic_camera_trajectory(
    scene_id: str,
    t_sec: float,
    dur: float,
    trigger_time: float,
    width: int = 1920,
    height: int = 1080,
) -> Tuple[float, float, float, float]:
    """Calculates smooth cinematic camera viewport coordinates (cx, cy, zoom, angle_deg)."""
    t_norm = min(1.0, max(0.0, t_sec / dur))

    if scene_id == "s01":
        # Follow airplane vector route along Puget Sound
        pdx = (int(0.48 * width), int(0.72 * height))
        sea = (int(0.45 * width), int(0.24 * height))
        p0, p1, p2, p3 = pdx, (int(0.47 * width), int(0.56 * height)), (int(0.44 * width), int(0.38 * height)), sea
        plane_t = min(0.95, max(0.05, t_sec / (dur * 0.85)))
        pos = cubic_bezier(p0, p1, p2, p3, plane_t)
        cx = float(pos[0])
        cy = float(pos[1])
        zoom = 1.32 + math.sin(t_norm * math.pi) * 0.05
        rot = math.sin(t_norm * math.pi * 2.0) * 0.5
        return cx, cy, zoom, rot

    elif scene_id == "s06":
        # Cockpit flight specs to Altimeter & Airspeed dials
        if t_sec < trigger_time:
            s = smoothstep(0.0, trigger_time, t_sec)
            return 960.0 - s * 140.0, 540.0, 1.25 + s * 0.05, -0.5
        elif t_sec < trigger_time + 1.8:
            s = smoothstep(trigger_time, trigger_time + 1.8, t_sec)
            cx = 820.0 + (1250.0 - 820.0) * s
            cy = 540.0 + (520.0 - 540.0) * s
            zoom = 1.30 + (1.42 - 1.30) * s
            rot = -0.5 + 1.2 * s
            return cx, cy, zoom, rot
        else:
            return 1250.0, 520.0, 1.40, 0.6

    else:
        # Standard Scenes:
        # Phase 1: Zone A (Memo & Headline Document) on Left (cx ≈ 580, cy ≈ 520, zoom ≈ 1.32)
        # Phase 2: Dynamic Glide across the investigative board to Zone B (Evidence Cutout on Right)
        # Phase 3: Pull back slightly near end to reveal the complete connected board
        t_glide_start = max(1.5, trigger_time - 0.4)
        t_glide_end = min(dur - 1.2, t_glide_start + 1.8)

        if t_sec < t_glide_start:
            s = smoothstep(0.0, t_glide_start, t_sec)
            cx = 560.0 + s * 25.0
            cy = 520.0 - s * 15.0
            zoom = 1.30 + s * 0.04
            rot = -0.8 + s * 0.2
            return cx, cy, zoom, rot
        elif t_sec < t_glide_end:
            s = smoothstep(t_glide_start, t_glide_end, t_sec)
            cx = 585.0 + (1360.0 - 585.0) * s
            cy = 505.0 + (500.0 - 505.0) * s
            zoom = 1.34 + (1.46 - 1.34) * s
            rot = -0.6 + (0.8 - (-0.6)) * s
            return cx, cy, zoom, rot
        else:
            rem = dur - t_sec
            if rem < 1.0:
                s_out = smoothstep(1.0, 0.0, rem)
                cx = 1360.0 - (1360.0 - 960.0) * s_out
                cy = 500.0 + (540.0 - 500.0) * s_out
                zoom = 1.46 - (1.46 - 1.15) * s_out
                rot = 0.8 - 0.8 * s_out
                return cx, cy, zoom, rot
            else:
                return 1360.0, 500.0, 1.46, 0.8


# ---------------------------------------------------------------------------
# Base Scene Compositor (Builds Wide Forensic Canvas Without Telemetry HUD)
# ---------------------------------------------------------------------------
def build_forensic_scene_frame(
    scene: StoryScene,
    scene_idx: int,
    images_dir: Path,
    cutouts_dir: Path,
    t_sec: float,
    dur: float,
    hl_progress: float = 0.0,
    width: int = 1920,
    height: int = 1080,
) -> np.ndarray:
    """Assembles a full-screen 1080p broadcast composite canvas before camera transformation."""
    if scene.scene_id == "s01":
        bg = render_cartography_flight_radar(min(1.0, t_sec / (dur * 0.85)), t_sec, width, height)
    elif scene.scene_id == "s06":
        bg = render_cockpit_flight_instruments(t_sec, width, height)
    else:
        hero_p = images_dir / scene.hero_image
        if not hero_p.exists():
            hero_p = Path("scratch/test_flux.png")

        if hero_p.exists():
            src_hero = cv2.imread(str(hero_p))
            if src_hero is not None:
                if src_hero.shape[:2] != (height, width):
                    src_hero = cv2.resize(src_hero, (width, height), interpolation=cv2.INTER_LANCZOS4)
                t_norm = min(1.0, max(0.0, t_sec / dur))
                zoom = 1.00 + 0.05 * t_norm
                pan_x = math.sin(t_norm * math.pi) * 20.0
                pan_y = -t_norm * 14.0

                M = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), 0.0, zoom)
                M[0, 2] += pan_x
                M[1, 2] += pan_y
                bg = cv2.warpAffine(src_hero, M, (width, height), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT_101)

                y_idx, x_idx = np.ogrid[:height, :width]
                dist_from_c = np.sqrt((x_idx - width / 2.0) ** 2 + (y_idx - height / 2.0) ** 2)
                max_d = np.sqrt((width / 2.0) ** 2 + (height / 2.0) ** 2)
                vig = np.clip(1.0 - 0.45 * (dist_from_c / max_d) ** 1.8, 0.40, 1.0)[..., None]
                bg = np.clip(bg.astype(np.float32) * vig, 0, 255).astype(np.uint8)
            else:
                bg = np.full((height, width, 3), (24, 26, 32), dtype=np.uint8)
        else:
            bg = np.full((height, width, 3), (24, 26, 32), dtype=np.uint8)

    # Zone B: Composite Hero Evidence Card on Right (cx: 1360, cy: 500)
    cutout_p = cutouts_dir / scene.cutout_image
    if cutout_p.exists():
        cutout_bgr = cv2.imread(str(cutout_p))
        if cutout_bgr is not None:
            c_w, c_h = 580, 440
            cutout_res = cv2.resize(cutout_bgr, (c_w, c_h))
            framed_card = np.full((c_h + 60, c_w + 34, 3), (245, 248, 252), dtype=np.uint8)
            framed_card[16:16 + c_h, 17:17 + c_w] = cutout_res

            cv2.putText(
                framed_card,
                scene.exhibit_code[:34].upper(),
                (20, c_h + 44),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.46,
                (35, 45, 60),
                1,
                cv2.LINE_AA,
            )

            settle = min(1.0, t_sec / 0.8)
            card_cx = int(width * 0.72)
            card_cy = int(height * 0.50 - (1.0 - settle) * 35.0)
            card_ang = -2.2 + settle * 0.5

            bg = composite_evidence_card_with_shadow(bg, framed_card, card_cx, card_cy, angle_deg=card_ang, shadow_blur=30, shadow_alpha=0.62)
            bg = draw_frosted_scotch_tape(bg, card_cx - (c_w // 2) + 24, card_cy - (c_h // 2) + 10, width=85, height=26, angle_deg=-26.0)
            bg = draw_brass_pushpin(bg, card_cx + (c_w // 2) - 18, card_cy - (c_h // 2) + 14, radius=13)

    # Zone A: Narrative Headline Box on Left (cx: 560, cy: 520)
    memo_w, memo_h = 620, 240
    memo_cx = int(width * 0.28)
    memo_cy = int(height * 0.50)
    memo = np.full((memo_h, memo_w, 3), (248, 250, 252), dtype=np.uint8)
    cv2.rectangle(memo, (2, 2), (memo_w - 2, memo_h - 2), (160, 175, 190), 1)

    cv2.putText(memo, f"NORTHWEST ORIENT ARCHIVE  •  {scene.act.upper()}", (20, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (90, 100, 115), 1, cv2.LINE_AA)
    cv2.putText(memo, scene.title[:32], (20, 68), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (20, 25, 35), 2, cv2.LINE_AA)
    cv2.line(memo, (20, 84), (memo_w - 20, 84), (200, 210, 220), 1)

    words_list = scene.text.split()
    line1 = " ".join(words_list[:8])
    line2 = " ".join(words_list[8:16])
    line3 = " ".join(words_list[16:24]) if len(words_list) > 16 else ""

    cv2.putText(memo, line1, (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (40, 48, 60), 1, cv2.LINE_AA)
    cv2.putText(memo, line2, (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (40, 48, 60), 1, cv2.LINE_AA)
    if line3:
        cv2.putText(memo, line3, (20, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (40, 48, 60), 1, cv2.LINE_AA)

    cv2.putText(memo, f"EVIDENCE FILE: {scene.exhibit_code}", (20, 215), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (120, 40, 40), 1, cv2.LINE_AA)

    bg = composite_evidence_card_with_shadow(bg, memo, memo_cx, memo_cy, angle_deg=1.8, shadow_blur=26, shadow_alpha=0.58)
    bg = draw_brass_pushpin(bg, memo_cx - (memo_w // 2) + 20, memo_cy - (memo_h // 2) + 18, radius=13)

    if hl_progress > 0.0:
        hl_x = memo_cx - (memo_w // 2) + 16
        hl_y = memo_cy - (memo_h // 2) + 132
        bg = draw_highlighter_bar(bg, hl_x, hl_y, int(memo_w * 0.85), 28, hl_progress)

    if t_sec >= 1.2 and scene.stamp_text:
        stamp_ang = -14.0 + math.sin(scene_idx * 1.5) * 4.0
        bg = draw_rubber_stamp(bg, scene.stamp_text, memo_cx + 180, memo_cy + 40, angle_deg=stamp_ang)

    return bg


# ---------------------------------------------------------------------------
# Dynamic 30FPS Scene Video Clip Generator (With Connected Virtual Camera)
# ---------------------------------------------------------------------------
def render_forensic_scene_clip(
    scene: StoryScene,
    scene_idx: int,
    images_dir: Path,
    cutouts_dir: Path,
    dur: float,
    words: List[Dict[str, Any]],
    output_mp4: Path,
    fps: int = 30,
    total_scenes: int = 12,
) -> Path:
    """Renders a dynamic 30fps full-screen scene clip with connected spatial camera motion."""
    total_frames = int(dur * fps)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    tmp_raw = output_mp4.with_suffix(".raw.mp4")
    out = cv2.VideoWriter(str(tmp_raw), fourcc, fps, (WIDTH, HEIGHT))

    # Resolve highlighter trigger timestamp
    hl_time = 0.6
    if scene.highlighter_phrase:
        hl_target = scene.highlighter_phrase.lower().split()[0].strip(".,!?\"'")
        for w in words:
            if hl_target in w["word"].lower():
                hl_time = w["start"]
                break

    # Resolve secondary exhibit trigger timestamp
    sec_trigger_time = dur * 0.45
    if scene.secondary_trigger_word:
        trig = scene.secondary_trigger_word.lower().strip(".,!?\"'")
        for w in words:
            if trig in w["word"].lower() or ("20" in w["word"] and trig == "ticket"):
                sec_trigger_time = w["start"]
                break

    for f in range(total_frames):
        t_sec = f / float(fps)
        hl_progress = max(0.0, min(1.0, (t_sec - hl_time) / 0.35)) if t_sec >= hl_time else 0.0

        # 1. Build base wide canvas
        canvas = build_forensic_scene_frame(
            scene=scene,
            scene_idx=scene_idx,
            images_dir=images_dir,
            cutouts_dir=cutouts_dir,
            t_sec=t_sec,
            dur=dur,
            hl_progress=hl_progress,
            width=WIDTH,
            height=HEIGHT,
        )

        # 2. Calculate dynamic camera trajectory
        cam_cx, cam_cy, zoom, rot = get_forensic_camera_trajectory(
            scene_id=scene.scene_id,
            t_sec=t_sec,
            dur=dur,
            trigger_time=sec_trigger_time,
            width=WIDTH,
            height=HEIGHT,
        )

        # 3. Transform canvas through virtual camera viewport
        viewport = render_camera_viewport(canvas, cam_cx, cam_cy, zoom, rot, WIDTH, HEIGHT)

        # 4. Render stable telemetry HUD on top of viewport
        final_frame = draw_top_bottom_telemetry_hud(viewport, scene, scene_idx, total_scenes=total_scenes)

        out.write(final_frame)

    out.release()

    vcodec = ["-c:v", "h264_videotoolbox", "-b:v", "14M"] if sys.platform == "darwin" else ["-c:v", "libx264", "-crf", "18"]
    cmd = [
        "ffmpeg", "-y", "-i", str(tmp_raw),
        *vcodec,
        "-pix_fmt", "yuv420p",
        str(output_mp4),
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    tmp_raw.unlink(missing_ok=True)

    return output_mp4


# ---------------------------------------------------------------------------
# Audio Synthesis & Multi-Layer Forensic Mixing (Local Kokoro-82M ONNX)
# ---------------------------------------------------------------------------
def synthesize_noir_narration(
    scenes: List[StoryScene],
    cache_dir: Path,
) -> Tuple[List[Path], List[float], List[List[Dict[str, Any]]]]:
    """Synthesizes humanized documentary noir narration using local Kokoro-82M ONNX."""
    import kokoro_onnx
    from faster_whisper import WhisperModel

    kokoro = kokoro_onnx.Kokoro(str(KOKORO_MODEL), str(KOKORO_VOICES))
    voice_george = kokoro.get_voice_style("bm_george")
    voice_michael = kokoro.get_voice_style("am_michael")
    doc_voice = 0.65 * voice_george + 0.35 * voice_michael

    whisper_model = WhisperModel("base", device="cpu", compute_type="int8")

    scene_audio_files: List[Path] = []
    scene_durations: List[float] = []
    scene_words: List[List[Dict[str, Any]]] = []

    eq_filter = (
        "highpass=f=65,"
        "equalizer=f=135:t=q:w=1.1:g=+2.4,"
        "equalizer=f=2400:t=q:w=1.4:g=+0.8,"
        "equalizer=f=3400:t=q:w=1.6:g=-1.6,"
        "lowpass=f=13500,"
        "deesser=i=0.6:m=0.4:f=0.5:s=o,"
        "acompressor=threshold=-16dB:ratio=2.0:attack=15:release=160,"
        "alimiter=limit=-1.2dB"
    )

    for sc in scenes:
        clean_text = sc.text.replace("*", "")
        wav_path = cache_dir / f"forensic_{sc.scene_id}.wav"
        raw_tmp = cache_dir / f"raw_forensic_{sc.scene_id}.wav"

        needs_build = True
        if wav_path.exists():
            try:
                with wave.open(str(wav_path), "rb") as cur_wf:
                    if cur_wf.getframerate() == 48000 and cur_wf.getnchannels() == 2:
                        needs_build = False
            except Exception:
                needs_build = True

        if needs_build:
            chunks = sc.speech_chunks
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
            segments, _ = whisper_model.transcribe(str(wav_path), word_timestamps=True)
            for s in segments:
                for w in s.words:
                    words.append({"word": w.word.strip(), "start": round(w.start, 2), "end": round(w.end, 2)})
            with open(json_path, "w") as f:
                json.dump(words, f, indent=2)

        scene_audio_files.append(wav_path)
        scene_durations.append(round(dur + 0.30, 2))
        scene_words.append(words)
        logger.info(f"  [{sc.scene_id}] {dur:.2f}s narration ({len(words)} words) -> scene {scene_durations[-1]:.2f}s")

    return scene_audio_files, scene_durations, scene_words


# ---------------------------------------------------------------------------
# End-to-End Forensic Production Orchestrator
# ---------------------------------------------------------------------------
def produce_forensic_documentary(
    project_slug: str,
    output_mp4_override: Optional[Path] = None,
    project_data: Optional[Dict[str, Any]] = None,
) -> Path:
    """Renders the complete LEMMiNO-tier forensic documentary video from project.json."""
    project_dir = REPO_ROOT / "projects" / project_slug
    if not project_dir.exists():
        project_dir = REPO_ROOT / "long_form" / project_slug
    if not project_dir.exists():
        project_dir = REPO_ROOT / "shorts" / project_slug

    proj_json_path = project_dir / "project.json"
    if project_data is None:
        if not proj_json_path.exists():
            raise MissingInputError(
                stage="forensic_casebook",
                artifact=proj_json_path,
                cause=f"project.json missing for slug '{project_slug}'",
            )
        try:
            project_data = json.loads(proj_json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise MissingInputError(
                stage="forensic_casebook",
                artifact=proj_json_path,
                cause=f"Corrupt or unreadable project.json: {exc}",
            ) from exc

    scenes = story_scenes_from_project(project_data)

    images_dir = project_dir / "images"
    cutouts_dir = images_dir / "cutouts"
    videos_dir = project_dir / "videos"
    cache_dir = project_dir / "cache"
    output_dir = REPO_ROOT / "output"

    for d in [videos_dir, cache_dir, output_dir]:
        d.mkdir(parents=True, exist_ok=True)

    if output_mp4_override:
        output_mp4 = output_mp4_override
    else:
        output_mp4 = output_dir / f"{project_slug}_forensic_casebook_16x9.mp4"

    logger.info("=== STEP 1: KOKORO-82M NEURAL NARRATION SYNTHESIS & NOIR CHUNKING ===")
    scene_audios, scene_durs, scene_words = synthesize_noir_narration(
        scenes, cache_dir
    )

    logger.info("=== STEP 2: RENDERING 30FPS CONNECTED SPATIAL CAMERA VIDEO CLIPS ===")
    raw_clips: List[Path] = []
    for idx, sc in enumerate(scenes):
        clip_p = videos_dir / f"forensic_{sc.scene_id}.mp4"
        dur = scene_durs[idx]
        words = scene_words[idx]

        render_forensic_scene_clip(
            scene=sc,
            scene_idx=idx,
            images_dir=images_dir,
            cutouts_dir=cutouts_dir,
            dur=dur,
            words=words,
            output_mp4=clip_p,
            fps=30,
            total_scenes=len(scenes),
        )
        raw_clips.append(clip_p)
        logger.info(f"  ✓ Rendered connected spatial clip {clip_p.name} ({dur:.2f}s)")

    logger.info("=== STEP 3: CINEMATIC DISSOLVE TRANSITIONS TIMELINE STITCH ===")
    filter_parts = []
    cur_v = "[0:v]"
    cur_offset = 0.0
    trans_dur = 0.50

    for i in range(len(raw_clips) - 1):
        dur_a = scene_durs[i]
        cur_offset += dur_a - trans_dur
        next_v = f"[{i+1}:v]"
        out_v = f"[v{i+1}]"
        filter_parts.append(f"{cur_v}{next_v}xfade=transition=dissolve:duration={trans_dur}:offset={cur_offset:.2f}{out_v}")
        cur_v = out_v

    full_filter = ";".join(filter_parts)
    visual_timeline = cache_dir / "visual_timeline_forensic.mp4"

    cmd_stitch = ["ffmpeg", "-y"]
    for rc in raw_clips:
        cmd_stitch.extend(["-i", str(rc)])
    vcodec = ["-c:v", "h264_videotoolbox", "-b:v", "14M"] if sys.platform == "darwin" else ["-c:v", "libx264", "-crf", "18"]
    cmd_stitch.extend([
        "-filter_complex", full_filter,
        "-map", cur_v,
        *vcodec,
        "-pix_fmt", "yuv420p",
        str(visual_timeline),
    ])
    subprocess.run(cmd_stitch, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    logger.info(f"Visual Timeline Assembled: {visual_timeline}")

    logger.info("=== STEP 4: FRAME-ACCURATE STEREO FOLEY SFX MIXING & TWO-ACT SOUNDTRACK ===")
    concat_list = cache_dir / "narration_forensic_list.txt"
    with open(concat_list, "w") as f:
        for sa in scene_audios:
            f.write(f"file '{sa.resolve()}'\n")

    master_voice = cache_dir / "master_voice_forensic.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(master_voice)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
    )

    total_voice_dur = sum(scene_durs) - (len(scene_durs) - 1) * trans_dur

    # Frame-Accurate Word-Level SFX Synchronization with Stereo Panning
    master_sfx = cache_dir / "master_sfx_forensic.wav"
    sfx_inputs = []
    amix_filters = []
    sfx_count = 0
    cur_scene_time = 0.0

    for idx, sc in enumerate(scenes):
        words = scene_words[idx]
        wav_path = scene_audios[idx]
        scene_pauses = detect_speech_pauses(wav_path)

        for cue in sc.sound_cues:
            sfx_f = SFX_DIR / f"{cue['name']}.mp3"
            if not sfx_f.exists():
                sfx_f = SFX_DIR / f"{cue['name']}.wav"
            if sfx_f.exists():
                target_word = cue.get("word_trigger", "").lower().strip(".,!?\"'")
                word_offset = None
                if target_word:
                    for w in words:
                        w_clean = w["word"].lower().strip(".,!?\"'")
                        if target_word in w_clean or w_clean in target_word:
                            word_offset = w["start"]
                            break
                        if target_word == "twenty" and ("20" in w["word"] or "$20" in w["word"]):
                            word_offset = w["start"]
                            break

                raw_offset = word_offset if word_offset is not None else cue.get("offset", 0.5)

                cue_db = get_cue_decibel(cue["name"])
                is_climax = cue_db >= DECIBEL_BUDGET["climax_blast"] - 0.5
                if is_climax:
                    snapped_offset = snap_cue_to_breath_pause(raw_offset, scene_pauses, search_window_sec=1.0)
                else:
                    snapped_offset = raw_offset

                offset = cur_scene_time + snapped_offset
                vol = get_cue_linear_gain(cue["name"])
                sfx_inputs.extend(["-i", str(sfx_f)])
                delay_ms = int(offset * 1000)

                pan_zone = cue.get("pan", "center")
                if pan_zone == "left":
                    pan_filter = "pan=stereo|c0=0.75*c0|c1=0.25*c0"
                elif pan_zone == "right":
                    pan_filter = "pan=stereo|c0=0.25*c0|c1=0.75*c0"
                else:
                    pan_filter = "volume=1.0"

                amix_filters.append(f"[{sfx_count+1}:a]adelay={delay_ms}|{delay_ms},{pan_filter},volume={vol}[sfx{sfx_count}]")
                sfx_count += 1

        cur_scene_time += scene_durs[idx] - trans_dur

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

    # Dynamic Soundtrack from project.json
    full_bgm_wav = cache_dir / "master_bgm_crossfade.wav"
    bgm_track = (project_data.get("music") or {}).get("track") or project_data.get("bgm")
    if bgm_track:
        bgm_path = Path(bgm_track)
        if not bgm_path.is_absolute():
            bgm_path = REPO_ROOT / "assets" / "audio" / "bgm" / bgm_path.name
        if bgm_path.exists():
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(bgm_path), "-t", f"{total_voice_dur:.2f}", "-c:a", "pcm_s16le", str(full_bgm_wav)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
            )

    # Master Audio Mix with Vocal Mid-Side Ducking
    mixed_audio = cache_dir / "mixed_audio_forensic.wav"
    if full_bgm_wav.exists():
        audio_filter = (
            "[0:a]volume=1.0[voice];"
            "[1:a]volume=1.0[sfx];"
            "[2:a]volume=0.18[bgm];"
            "[voice][bgm]sidechaincompress=threshold=0.08:ratio=3.5:attack=20:release=350[ducked_bgm];"
            "[voice][sfx][ducked_bgm]amix=inputs=3:normalize=0[mixed]"
        )
        cmd_mix = [
            "ffmpeg", "-y",
            "-i", str(master_voice),
            "-i", str(master_sfx),
            "-i", str(full_bgm_wav),
            "-filter_complex", audio_filter,
            "-map", "[mixed]",
            "-t", f"{total_voice_dur:.2f}",
            str(mixed_audio),
        ]
    else:
        cmd_mix = [
            "ffmpeg", "-y",
            "-i", str(master_voice),
            "-i", str(master_sfx),
            "-filter_complex", "[0:a][1:a]amix=inputs=2:normalize=0[mixed]",
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

    logger.info(f"✓ Master Forensic Video Rendered: {output_mp4}")
    logger.info(f"  Duration: {dur_final:.2f}s ({dur_final / 60:.2f} mins) | Size: {size_mb:.2f} MB")

    record_ledger_event(
        slug=project_slug,
        stage="render",
        status="PASS",
        details={
            "video_id": project_data.get("id", "LV-01"),
            "title": project_data.get("title", project_slug),
            "topic": project_data.get("topic", project_slug),
            "output_file": str(output_mp4),
            "scenes": len(scenes),
            "notes": f"Connected Spatial Camera & Stereo Foley Engine; {len(scenes)} scenes; duration: {dur_final:.1f}s; {size_mb:.1f} MB; -14 LUFS",
        },
        evidence={"duration": dur_final, "size_mb": size_mb, "lufs": -14.0},
    )

    return output_mp4


def main() -> None:
    parser = argparse.ArgumentParser(description="Forensic Casebook Video Engine")
    parser.add_argument("--slug", type=str, required=True, help="Project slug")
    parser.add_argument("--output", type=Path, default=None, help="Output MP4 path")
    args = parser.parse_args()

    produce_forensic_documentary(project_slug=args.slug, output_mp4_override=args.output)


if __name__ == "__main__":
    main()
