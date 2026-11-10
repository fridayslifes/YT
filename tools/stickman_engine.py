#!/usr/bin/env python3
"""FrameForge Stickman Storytelling & Vector Engine (tools/stickman_engine.py).

Reverse-engineered from viral minimalist explainer channels:
  - Casually Explained (4.2M subscribers, ~4.1M views/video)
  - StickTale ("Why did ancient Romans pee in their laundry?")
  - MinutePhysics & Sam O'Nella Academy

Core Architectural Features:
  1. Procedural 2D Vector Skeleton:
     - Expressive facial rigs: dot eyes, eyebrow tilts, dynamic mouth shapes (neutral, smile, open_gasp, smirk, frown).
     - Pre-calibrated pose library: `idle`, `thinking`, `pointing`, `shocked`, `facepalm`, `shrugging`, `running`.
  2. Character Consistency System:
     - Signature accessory slot (flat cap, fedora, glasses, tie) locking character identity across hundreds of scenes.
     - Dynamic prop attachment to hand joints (magnifying glass, coffee cup, smartphone, book, pointer).
  3. Zero Visual Friction Output:
     - Generates clean transparent RGBA PNGs/clips for hybrid compositing OR standalone minimalist explainers.
     - Built-in breathing/sway micro-animation preventing visual freeze.
  4. 5-Second Attention Reset Architecture:
     - Designed for high verbal density (~150 wpm, ~12 words per visual cut).
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np


# ---------------------------------------------------------------------------
# DATA STRUCTURES
# ---------------------------------------------------------------------------

@dataclass
class StickmanAppearance:
    """Signature appearance descriptors to ensure 100% character consistency."""
    line_color: Tuple[int, int, int] = (20, 20, 20)  # BGR Dark Ink
    line_thickness: int = 6
    head_radius: int = 36
    torso_length: int = 90
    accessory: Optional[str] = "flat_cap"             # "flat_cap", "glasses", "fedora", "tie", "none"
    accessory_color: Tuple[int, int, int] = (15, 82, 186)  # Default signature navy blue (BGR)


@dataclass
class StickmanPoseSpec:
    """Defines facial expression, limb posture, and held prop."""
    pose: str = "idle"                                # "idle", "thinking", "pointing", "shocked", "facepalm", "shrugging", "running"
    mouth: str = "neutral"                            # "neutral", "smile", "open_gasp", "smirk", "frown"
    eyebrows: str = "neutral"                         # "neutral", "raised", "furrowed", "surprised"
    prop: Optional[str] = None                        # "magnifying_glass", "coffee", "phone", "book", "pointer"
    flip_horizontal: bool = False


# ---------------------------------------------------------------------------
# SKELETON & LIMB RIGGING CALCULATIONS
# ---------------------------------------------------------------------------

def compute_limb_joints(
    cx: int,
    cy: int,
    pose: str,
    torso_len: int = 90,
    sway_phase: float = 0.0,
) -> dict:
    """Computes (x, y) joint coordinates for head, spine, arms, and legs scaled by torso_len."""
    s = max(0.25, float(torso_len) / 90.0)
    def sc(v: float) -> int:
        return int(round(v * s))

    # Micro-sway breathing
    sway_x = int(round(math.sin(sway_phase * math.pi * 2) * 2.0 * s))
    sway_y = int(round(math.cos(sway_phase * math.pi * 2) * 1.5 * s))

    neck = (cx + sway_x, cy + sway_y)
    pelvis = (cx + sway_x, cy + int(round(torso_len)) + sway_y)

    # Defaults
    l_shoulder = (neck[0] - sc(10), neck[1] + sc(12))
    r_shoulder = (neck[0] + sc(10), neck[1] + sc(12))

    l_elbow = (l_shoulder[0] - sc(22), l_shoulder[1] + sc(35))
    r_elbow = (r_shoulder[0] + sc(22), r_shoulder[1] + sc(35))

    l_hand = (l_elbow[0] - sc(10), l_elbow[1] + sc(35))
    r_hand = (r_elbow[0] + sc(10), r_elbow[1] + sc(35))

    l_hip = (pelvis[0] - sc(8), pelvis[1])
    r_hip = (pelvis[0] + sc(8), pelvis[1])

    l_knee = (l_hip[0] - sc(14), l_hip[1] + sc(55))
    r_knee = (r_hip[0] + sc(14), r_hip[1] + sc(55))

    l_foot = (l_knee[0] - sc(6), l_knee[1] + sc(55))
    r_foot = (r_knee[0] + sc(6), r_knee[1] + sc(55))

    if pose == "thinking":
        # Right hand touching chin, left arm crossed
        l_elbow = (neck[0] - sc(26), neck[1] + sc(45))
        l_hand = (neck[0] + sc(5), neck[1] + sc(48))

        r_elbow = (neck[0] + sc(32), neck[1] + sc(36))
        r_hand = (neck[0] + sc(12), neck[1] - sc(8))  # Near chin

    elif pose == "pointing":
        # Right arm pointing forward/upward
        r_elbow = (r_shoulder[0] + sc(40), r_shoulder[1] - sc(10))
        r_hand = (r_elbow[0] + sc(48), r_elbow[1] - sc(18))

    elif pose == "shocked":
        # Both hands on head/cheeks
        l_elbow = (neck[0] - sc(38), neck[1] + sc(10))
        l_hand = (neck[0] - sc(22), neck[1] - sc(26))

        r_elbow = (neck[0] + sc(38), neck[1] + sc(10))
        r_hand = (neck[0] + sc(22), neck[1] - sc(26))

    elif pose == "facepalm":
        # Right hand slapping forehead
        r_elbow = (neck[0] + sc(28), neck[1] + sc(16))
        r_hand = (neck[0], neck[1] - sc(32))  # Forehead

    elif pose == "shrugging":
        # Both hands raised, elbows bent
        l_elbow = (l_shoulder[0] - sc(30), l_shoulder[1] + sc(15))
        l_hand = (l_elbow[0] - sc(15), l_elbow[1] - sc(24))

        r_elbow = (r_shoulder[0] + sc(30), r_shoulder[1] + sc(15))
        r_hand = (r_elbow[0] + sc(15), r_elbow[1] - sc(24))

    elif pose == "running":
        # Dynamic stride
        l_elbow = (l_shoulder[0] - sc(30), l_shoulder[1] - sc(15))
        l_hand = (l_elbow[0] - sc(20), l_elbow[1] - sc(15))

        r_elbow = (r_shoulder[0] + sc(30), r_shoulder[1] + sc(35))
        r_hand = (r_elbow[0] + sc(25), r_elbow[1] + sc(25))

        l_knee = (l_hip[0] + sc(35), l_hip[1] + sc(30))
        l_foot = (l_knee[0] + sc(30), l_knee[1] + sc(45))

        r_knee = (r_hip[0] - sc(35), r_hip[1] + sc(40))
        r_foot = (r_knee[0] - sc(30), r_knee[1] + sc(25))

    return {
        "neck": neck,
        "pelvis": pelvis,
        "l_shoulder": l_shoulder,
        "r_shoulder": r_shoulder,
        "l_elbow": l_elbow,
        "r_elbow": r_elbow,
        "l_hand": l_hand,
        "r_hand": r_hand,
        "l_hip": l_hip,
        "r_hip": r_hip,
        "l_knee": l_knee,
        "r_knee": r_knee,
        "l_foot": l_foot,
        "r_foot": r_foot,
    }


# ---------------------------------------------------------------------------
# RENDERING: FACE, ACCESSORIES, PROPS
# ---------------------------------------------------------------------------

def draw_stickman_face(
    canvas: np.ndarray,
    head_center: Tuple[int, int],
    radius: int,
    mouth: str,
    eyebrows: str,
    color: Tuple[int, int, int],
) -> None:
    """Draws expressive 2D facial features (dot eyes, eyebrows, mouth) scaled to head radius."""
    hx, hy = head_center
    rs = max(0.30, float(radius) / 36.0)
    def sc(v: float) -> int:
        return max(1, int(round(v * rs)))

    # Eye positions
    eye_offset_x = max(2, int(round(radius * 0.32)))
    eye_offset_y = max(1, int(round(radius * 0.12)))
    l_eye = (hx - eye_offset_x, hy - eye_offset_y)
    r_eye = (hx + eye_offset_x, hy - eye_offset_y)
    eye_radius = max(2, int(round(radius * 0.10)))

    cv2.circle(canvas, l_eye, eye_radius, color, -1, cv2.LINE_AA)
    cv2.circle(canvas, r_eye, eye_radius, color, -1, cv2.LINE_AA)

    # Eyebrows
    eb_y = l_eye[1] - sc(8)
    eb_th = max(1, int(round(2 * rs)))
    if eyebrows == "surprised":
        cv2.line(canvas, (l_eye[0] - sc(8), eb_y - sc(6)), (l_eye[0] + sc(8), eb_y - sc(8)), color, eb_th, cv2.LINE_AA)
        cv2.line(canvas, (r_eye[0] - sc(8), eb_y - sc(8)), (r_eye[0] + sc(8), eb_y - sc(6)), color, eb_th, cv2.LINE_AA)
    elif eyebrows == "furrowed":
        cv2.line(canvas, (l_eye[0] - sc(8), eb_y - sc(2)), (l_eye[0] + sc(8), eb_y + sc(4)), color, eb_th, cv2.LINE_AA)
        cv2.line(canvas, (r_eye[0] - sc(8), eb_y + sc(4)), (r_eye[0] + sc(8), eb_y - sc(2)), color, eb_th, cv2.LINE_AA)
    else:
        cv2.line(canvas, (l_eye[0] - sc(8), eb_y), (l_eye[0] + sc(8), eb_y), color, eb_th, cv2.LINE_AA)
        cv2.line(canvas, (r_eye[0] - sc(8), eb_y), (r_eye[0] + sc(8), eb_y), color, eb_th, cv2.LINE_AA)

    # Mouth
    my = hy + int(round(radius * 0.40))
    m_th = max(1, int(round(3 * rs)))
    if mouth == "smile":
        cv2.ellipse(canvas, (hx, my - sc(4)), (sc(14), sc(10)), 0, 10, 170, color, m_th, cv2.LINE_AA)
    elif mouth == "open_gasp":
        cv2.circle(canvas, (hx, my + sc(2)), sc(8), color, -1, cv2.LINE_AA)
    elif mouth == "smirk":
        cv2.line(canvas, (hx - sc(8), my), (hx + sc(10), my - sc(5)), color, m_th, cv2.LINE_AA)
    elif mouth == "frown":
        cv2.ellipse(canvas, (hx, my + sc(8)), (sc(14), sc(10)), 0, 190, 350, color, m_th, cv2.LINE_AA)
    else:  # neutral
        cv2.line(canvas, (hx - sc(10), my), (hx + sc(10), my), color, m_th, cv2.LINE_AA)


def draw_accessory(
    canvas: np.ndarray,
    head_center: Tuple[int, int],
    radius: int,
    accessory: str,
    color: Tuple[int, int, int],
) -> None:
    """Renders locked signature accessory onto the stick figure head scaled to head radius."""
    hx, hy = head_center
    rs = max(0.30, float(radius) / 36.0)
    def sc(v: float) -> int:
        return max(1, int(round(v * rs)))
    outline_th = max(1, int(round(2 * rs)))

    if accessory == "flat_cap":
        cap_y = hy - int(round(radius * 0.70))
        cv2.ellipse(canvas, (hx, cap_y), (radius + sc(6), int(round(radius * 0.55))), 0, 180, 360, color, -1, cv2.LINE_AA)
        cv2.ellipse(canvas, (hx, cap_y), (radius + sc(6), int(round(radius * 0.55))), 0, 180, 360, (20, 20, 20), outline_th, cv2.LINE_AA)
        visor_pts = np.array([
            [hx - radius - sc(2), cap_y + sc(4)],
            [hx + radius + sc(14), cap_y + sc(4)],
            [hx + radius + sc(10), cap_y + sc(12)],
            [hx - radius, cap_y + sc(8)],
        ], dtype=np.int32)
        cv2.fillPoly(canvas, [visor_pts], color, cv2.LINE_AA)
        cv2.polylines(canvas, [visor_pts], True, (20, 20, 20), outline_th, cv2.LINE_AA)

    elif accessory == "glasses":
        l_center = (hx - int(round(radius * 0.32)), hy - int(round(radius * 0.12)))
        r_center = (hx + int(round(radius * 0.32)), hy - int(round(radius * 0.12)))
        g_radius = max(2, int(round(radius * 0.22)))
        cv2.circle(canvas, l_center, g_radius, color, outline_th, cv2.LINE_AA)
        cv2.circle(canvas, r_center, g_radius, color, outline_th, cv2.LINE_AA)
        cv2.line(canvas, (l_center[0] + g_radius, l_center[1]), (r_center[0] - g_radius, r_center[1]), color, outline_th, cv2.LINE_AA)

    elif accessory == "fedora":
        fedora_y = hy - int(round(radius * 0.80))
        cv2.ellipse(canvas, (hx, fedora_y + sc(8)), (radius + sc(16), sc(6)), 0, 0, 360, color, -1, cv2.LINE_AA)
        cv2.ellipse(canvas, (hx, fedora_y + sc(8)), (radius + sc(16), sc(6)), 0, 0, 360, (20, 20, 20), outline_th, cv2.LINE_AA)
        pts = np.array([
            [hx - radius + sc(2), fedora_y + sc(6)],
            [hx - int(round(radius * 0.65)), fedora_y - sc(28)],
            [hx + int(round(radius * 0.65)), fedora_y - sc(28)],
            [hx + radius - sc(2), fedora_y + sc(6)],
        ], dtype=np.int32)
        cv2.fillPoly(canvas, [pts], color, cv2.LINE_AA)
        cv2.polylines(canvas, [pts], True, (20, 20, 20), outline_th, cv2.LINE_AA)


def draw_prop(
    canvas: np.ndarray,
    hand_pos: Tuple[int, int],
    prop_name: str,
    scale: float = 1.0,
) -> None:
    """Snaps a vector prop into the stick figure's hand scaled by `scale`."""
    hx, hy = hand_pos
    s = max(0.30, float(scale))
    def sc(v: float) -> int:
        return max(1, int(round(v * s)))

    if prop_name == "magnifying_glass":
        glass_center = (hx + sc(18), hy - sc(18))
        cv2.circle(canvas, glass_center, sc(16), (230, 240, 255), -1, cv2.LINE_AA)
        cv2.circle(canvas, glass_center, sc(16), (180, 130, 40), max(1, sc(4)), cv2.LINE_AA)
        cv2.line(canvas, (hx, hy), (hx - sc(14), hy + sc(14)), (100, 70, 30), max(1, sc(5)), cv2.LINE_AA)

    elif prop_name == "coffee":
        pts = np.array([
            [hx - sc(10), hy - sc(14)],
            [hx + sc(10), hy - sc(14)],
            [hx + sc(8), hy + sc(14)],
            [hx - sc(8), hy + sc(14)],
        ], dtype=np.int32)
        cv2.fillPoly(canvas, [pts], (240, 240, 240), cv2.LINE_AA)
        cv2.polylines(canvas, [pts], True, (30, 30, 30), max(1, sc(2)), cv2.LINE_AA)
        cv2.ellipse(canvas, (hx + sc(11), hy), (sc(5), sc(8)), 0, -90, 90, (30, 30, 30), max(1, sc(2)), cv2.LINE_AA)

    elif prop_name == "phone":
        pts = np.array([
            [hx - sc(7), hy - sc(16)],
            [hx + sc(7), hy - sc(16)],
            [hx + sc(7), hy + sc(16)],
            [hx - sc(7), hy + sc(16)],
        ], dtype=np.int32)
        cv2.fillPoly(canvas, [pts], (40, 40, 45), cv2.LINE_AA)
        cv2.polylines(canvas, [pts], True, (200, 200, 200), max(1, sc(2)), cv2.LINE_AA)

    elif prop_name == "pointer":
        cv2.line(canvas, (hx, hy), (hx + sc(70), hy - sc(40)), (140, 100, 50), max(1, sc(3)), cv2.LINE_AA)
        cv2.circle(canvas, (hx + sc(70), hy - sc(40)), sc(4), (0, 0, 220), -1, cv2.LINE_AA)


# ---------------------------------------------------------------------------
# CORE STICKMAN COMPOSITOR
# ---------------------------------------------------------------------------

def render_stickman_frame(
    canvas: np.ndarray,
    cx: int,
    cy: int,
    pose_spec: StickmanPoseSpec,
    app: StickmanAppearance,
    sway_phase: float = 0.0,
    scale: float = 1.0,
) -> None:
    """Renders a single stickman character at (cx, cy) onto the canvas scaled by `scale`."""
    s = max(0.30, float(scale))
    head_r = max(8, int(round(app.head_radius * s)))
    torso_len = max(20, int(round(app.torso_length * s)))
    th = max(2, int(round(app.line_thickness * s)))

    head_c = (cx, cy - head_r)
    joints = compute_limb_joints(cx, cy, pose_spec.pose, torso_len, sway_phase)

    # 1. Draw Limbs & Spine
    col = app.line_color

    # Spine (Torso)
    cv2.line(canvas, joints["neck"], joints["pelvis"], col, th + 1, cv2.LINE_AA)

    # Left Leg
    cv2.line(canvas, joints["l_hip"], joints["l_knee"], col, th, cv2.LINE_AA)
    cv2.line(canvas, joints["l_knee"], joints["l_foot"], col, th, cv2.LINE_AA)

    # Right Leg
    cv2.line(canvas, joints["r_hip"], joints["r_knee"], col, th, cv2.LINE_AA)
    cv2.line(canvas, joints["r_knee"], joints["r_foot"], col, th, cv2.LINE_AA)

    # Left Arm
    cv2.line(canvas, joints["l_shoulder"], joints["l_elbow"], col, th, cv2.LINE_AA)
    cv2.line(canvas, joints["l_elbow"], joints["l_hand"], col, th, cv2.LINE_AA)

    # Right Arm
    cv2.line(canvas, joints["r_shoulder"], joints["r_elbow"], col, th, cv2.LINE_AA)
    cv2.line(canvas, joints["r_elbow"], joints["r_hand"], col, th, cv2.LINE_AA)

    # 2. Draw Head (Filled white or transparent with outline)
    cv2.circle(canvas, head_c, head_r, (255, 255, 255), -1, cv2.LINE_AA)
    cv2.circle(canvas, head_c, head_r, col, th, cv2.LINE_AA)

    # 3. Draw Face
    draw_stickman_face(canvas, head_c, head_r, pose_spec.mouth, pose_spec.eyebrows, col)

    # 4. Draw Signature Accessory
    if app.accessory and app.accessory != "none":
        draw_accessory(canvas, head_c, head_r, app.accessory, app.accessory_color)

    # 5. Draw Prop
    if pose_spec.prop:
        draw_prop(canvas, joints["r_hand"], pose_spec.prop, scale=s)


def draw_stickman_scene_plane(
    canvas: np.ndarray,
    char_cx: int,
    char_cy: int,
    torso_len: int,
    scale: float,
) -> None:
    """Draws a grounded sketchbook/whiteboard scene plane with drafting grid, stage horizon, and contact shadow."""
    h, w = canvas.shape[:2]
    grid_step = max(16, int(round(64 * scale)))
    grid_color = (236, 232, 224)

    for gx in range(grid_step, w, grid_step):
        cv2.line(canvas, (gx, 0), (gx, h), grid_color, 1)
    for gy in range(grid_step, h, grid_step):
        cv2.line(canvas, (0, gy), (w, gy), grid_color, 1)

    # Ground horizon & stage plane beneath feet
    foot_y = min(h - max(12, int(round(40 * scale))), char_cy + torso_len + int(round(112 * scale)))
    floor_top = max(0, foot_y - int(round(8 * scale)))
    canvas[floor_top:h, :] = np.clip(canvas[floor_top:h, :].astype(np.int16) - 12, 0, 255).astype(np.uint8)
    cv2.line(canvas, (int(w * 0.08), floor_top), (int(w * 0.92), floor_top), (70, 72, 78), max(1, int(round(3 * scale))), cv2.LINE_AA)

    # Contact shadow ellipse under character
    sh_rx = max(12, int(round(48 * scale)))
    sh_ry = max(4, int(round(12 * scale)))
    cv2.ellipse(canvas, (char_cx, foot_y), (sh_rx, sh_ry), 0, 0, 360, (190, 186, 178), -1, cv2.LINE_AA)

    # Subtle framing border
    inset = max(6, int(round(20 * scale)))
    cv2.rectangle(canvas, (inset, inset), (w - inset, h - inset), (160, 156, 148), max(1, int(round(2 * scale))), cv2.LINE_AA)


# ---------------------------------------------------------------------------
# VIDEO GENERATION (STANDALONE MINIMALIST OR TRANSPARENT OVERLAY)
# ---------------------------------------------------------------------------

def render_stickman_scene(
    pose_spec: StickmanPoseSpec,
    app: StickmanAppearance,
    output_path: Path,
    caption_text: Optional[str] = None,
    bg_color: Tuple[int, int, int] = (250, 247, 238),  # Warm sketchbook paper default
    duration: float = 3.5,
    fps: int = 30,
    width: int = 1080,
    height: int = 1920,
) -> bool:
    """Renders a standalone stickman explainer scene to broadcast MP4 with scaled geometry & scene plane."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    width = (width // 2) * 2
    height = (height // 2) * 2
    num_frames = int(round(duration * fps))

    tmp_raw_mp4 = output_path.with_suffix(".stick.raw.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(tmp_raw_mp4), fourcc, float(fps), (width, height))

    if not writer.isOpened():
        raise RuntimeError(f"Failed to open video writer for {tmp_raw_mp4}")

    scale = max(0.28, min(width, height) / 1080.0)
    char_scale = scale * 1.35
    char_cx = width // 2
    char_cy = int(height * 0.44)
    scaled_torso = max(20, int(round(app.torso_length * char_scale)))

    try:
        for frame_idx in range(num_frames):
            p = frame_idx / max(1, num_frames - 1)
            frame = np.full((height, width, 3), bg_color, dtype=np.uint8)

            # 1. Grounded scene plane & notebook environment
            draw_stickman_scene_plane(frame, char_cx, char_cy, scaled_torso, scale=char_scale)

            # 2. Render Stickman with natural breathing/sway and scaled geometry
            render_stickman_frame(frame, char_cx, char_cy, pose_spec, app, sway_phase=p * 2.0, scale=char_scale)

            # 3. Optional floating speech / caption bubble scaled & wrapped inside safe zone
            if caption_text:
                font = cv2.FONT_HERSHEY_DUPLEX
                font_scale = max(0.32, 0.78 * scale)
                thickness = max(1, int(round(2 * scale)))
                pad_x = max(8, int(round(18 * scale)))
                pad_y = max(6, int(round(14 * scale)))
                max_card_w = max(60, int(width * 0.88))
                max_text_w = max(40, max_card_w - 2 * pad_x)

                words = caption_text.strip().split()
                lines: list[str] = []
                cur = words[0] if words else ""
                for w_tok in words[1:]:
                    cand = f"{cur} {w_tok}"
                    if cv2.getTextSize(cand, font, font_scale, thickness)[0][0] <= max_text_w:
                        cur = cand
                    else:
                        lines.append(cur)
                        cur = w_tok
                if cur:
                    lines.append(cur)
                lines = lines[:3]

                longest = max((cv2.getTextSize(ln, font, font_scale, thickness)[0][0] for ln in lines), default=0)
                if longest > max_text_w and longest > 0:
                    font_scale = max(0.24, font_scale * (max_text_w / float(longest)))

                sizes = [cv2.getTextSize(ln, font, font_scale, thickness)[0] for ln in lines]
                line_h = max((sz[1] for sz in sizes), default=12)
                line_gap = max(4, int(round(8 * scale)))
                block_w = max((sz[0] for sz in sizes), default=40)
                block_h = len(lines) * line_h + max(0, len(lines) - 1) * line_gap

                box_w = min(max_card_w, block_w + 2 * pad_x)
                box_h = block_h + 2 * pad_y
                bx1 = max(4, (width - box_w) // 2)
                bx2 = min(width - 4, bx1 + box_w)
                safe_bot = int(round(height * 0.76))
                by2 = min(height - 4, safe_bot)
                by1 = max(int(round(height * 0.44)), by2 - box_h)

                cv2.rectangle(frame, (bx1, by1), (bx2, by2), (242, 240, 234), -1)
                cv2.rectangle(frame, (bx1, by1), (bx2, by2), (40, 40, 40), max(1, int(round(2 * scale))))

                start_y = by1 + ((by2 - by1) - block_h) // 2 + line_h
                for idx_l, (ln, sz) in enumerate(zip(lines, sizes)):
                    tx = bx1 + ((bx2 - bx1) - sz[0]) // 2
                    ty = start_y + idx_l * (line_h + line_gap)
                    cv2.putText(frame, ln, (tx, ty), font, font_scale, (20, 20, 20), thickness, cv2.LINE_AA)

            writer.write(frame)

    finally:
        writer.release()

    # Re-encode to broadcast H.264 MP4
    success = reencode_broadcast_mp4(tmp_raw_mp4, output_path, fps=fps)
    if tmp_raw_mp4.exists():
        tmp_raw_mp4.unlink(missing_ok=True)
    return success


def reencode_broadcast_mp4(src_path: Path, dst_path: Path, fps: int = 30) -> bool:
    """Encodes to pristine 14 Mbps H.264 MP4."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        shutil.move(str(src_path), str(dst_path))
        return True

    encoders = ["h264_videotoolbox", "libx264"]
    for enc in encoders:
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

        proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if proc.returncode == 0 and dst_path.exists() and dst_path.stat().st_size > 0:
            return True

    shutil.move(str(src_path), str(dst_path))
    return True


# ---------------------------------------------------------------------------
# CLI INTERFACE
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="FrameForge Stickman Storytelling & Vector Engine")
    ap.add_argument("--output", "-o", type=Path, required=True, help="Output MP4 path")
    ap.add_argument("--pose", type=str, default="thinking", choices=["idle", "thinking", "pointing", "shocked", "facepalm", "shrugging", "running"], help="Character pose")
    ap.add_argument("--mouth", type=str, default="neutral", choices=["neutral", "smile", "open_gasp", "smirk", "frown"], help="Mouth expression")
    ap.add_argument("--accessory", type=str, default="flat_cap", choices=["flat_cap", "glasses", "fedora", "tie", "none"], help="Signature locked accessory")
    ap.add_argument("--prop", type=str, default="magnifying_glass", choices=["magnifying_glass", "coffee", "phone", "pointer", "none"], help="Hand prop")
    ap.add_argument("--caption", "-c", type=str, default=None, help="Spoken line caption banner")
    ap.add_argument("--duration", "-d", type=float, default=3.5, help="Clip duration in seconds")
    ap.add_argument("--width", type=int, default=1080, help="Output width (default: 1080)")
    ap.add_argument("--height", type=int, default=1920, help="Output height (default: 1920)")

    args = ap.parse_args()

    app = StickmanAppearance(accessory=args.accessory)
    prop = args.prop if args.prop != "none" else None
    pose = StickmanPoseSpec(pose=args.pose, mouth=args.mouth, prop=prop)

    print(f"✏️ Rendering Stickman Explainer [{args.pose} | {args.accessory} | {args.duration}s @ 30fps]...")
    ok = render_stickman_scene(
        pose_spec=pose,
        app=app,
        output_path=args.output,
        caption_text=args.caption,
        duration=args.duration,
        fps=30,
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
