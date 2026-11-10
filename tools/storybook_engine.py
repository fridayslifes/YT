#!/usr/bin/env python3
"""FrameForge Tactile Storybook & Archival Casebook Engine (tools/storybook_engine.py).

Transforms raw AI images into authentic, tactile physical book and casebook experiences,
reverse-engineered from top visual essayists (Johnny Harris, Vox, Magnates Media, LEMMiNO,
Bedtime Stories, and classic 3D pop-up books).

Core Architectural Features:
  1. Physical Surface & Spread Compositing:
     - Option 1 (Casebook): Dark mahogany wood desk with aged cream parchment dossier,
       paper fiber noise, center spine crease shadow, and Manila folder tabs.
     - Option 2 (Classic Storybook): Leather-bound book cover with ornate gilded gold foil
       hairlines, warm linen watercolor paper, and center gutter curvature.
  2. 3D Pop-Up Photo Plates with Real Cast Shadows:
     - Polaroid / archival white borders with realistic directional Gaussian drop shadows
       (offset dx, dy, sigma, alpha) making the plate physically hover above the parchment.
  3. Diegetic Fasteners & Mounts:
     - Translucent frosted scotch tape with surface highlights across corners.
     - Photo mounting corners and brass paperclips.
  4. Diegetic Inked Annotations & Rubber Stamps:
     - Red grease-pencil forensic circles and arrows.
     - Semi-transparent yellow highlighter strokes (multiply blend mode).
     - Weathered rubber ink stamps (e.g. 'EXHIBIT A', 'CONFIDENTIAL', 'CASE CLOSED').
  5. Smooth S-Curve Spread Navigation & Transitions:
     - Spread pan (virtual camera glides across the two-page book spread).
     - Photo plate Ken Burns dolly-in with subtle micro-rotation.
     - Page curl / desk slide transitions between story scenes.
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

import cv2
import numpy as np

TOOLS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TOOLS_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from tools.photobook_engine import apply_optical_vignette, generate_film_grain, s_curve_ease  # noqa: E402


# ---------------------------------------------------------------------------
# COLOR PALETTES & TEXTURE CONSTANTS
# ---------------------------------------------------------------------------

STYLE_THEMES: Dict[str, Dict[str, Tuple[int, int, int]]] = {
    "casebook": {
        "desk_base": (12, 18, 27),          # Deep mahogany dark wood (BGR)
        "paper_base": (217, 235, 244),      # Aged cream parchment (#F4EBD9)
        "paper_edge": (180, 205, 220),      # Weathered paper edge tone
        "spine_shadow": (60, 75, 95),       # Center crease shadow
        "tape_tint": (230, 240, 245),       # Frosted scotch tape tint
        "red_ink": (42, 42, 201),           # Crimson ballpoint / forensic ink
        "stamp_ink": (35, 35, 180),         # Weathered red rubber stamp
        "highlight": (59, 235, 255),        # Fluorescent yellow highlighter (BGR)
    },
    "classic": {
        "desk_base": (14, 23, 43),          # Antique dark saddle leather (BGR)
        "paper_base": (235, 249, 255),      # Warm antique linen paper (#FFF9EB)
        "paper_edge": (195, 220, 235),      # Aged linen edge
        "spine_shadow": (70, 85, 105),      # Center spine gutter shadow
        "gold_foil": (55, 175, 212),        # Gilded gold accent (#D4AF37 BGR)
        "tape_tint": (220, 230, 240),       # Parchment mounting tape
        "red_ink": (30, 30, 160),           # Dark crimson bookplate ink
        "stamp_ink": (40, 40, 150),         # Archival library stamp
        "highlight": (70, 215, 255),        # Warm amber highlight
    },
    "scrapbook": {
        "desk_base": (26, 30, 38),          # Dark slate cutting mat / workbench (BGR)
        "paper_base": (230, 238, 246),      # Clean archival off-white sheet
        "paper_edge": (175, 190, 205),      # Weathered paper edge
        "spine_shadow": (55, 65, 80),       # Crease shadow
        "tape_tint": (215, 225, 235),       # Frosted masking tape
        "red_ink": (35, 35, 220),           # Crimson investigation yarn / marker
        "stamp_ink": (30, 30, 195),         # Evidence stamp
        "highlight": (35, 230, 255),        # Neon yellow highlighter (BGR)
        "pin_brass": (45, 175, 225),        # Polished brass thumbtack
    },
}


# ---------------------------------------------------------------------------
# 1. PROCEDURAL PHYSICAL CANVASES (DESK, BOOK SPREAD, GUTTER)
# ---------------------------------------------------------------------------

def generate_storybook_canvas(
    width: int,
    height: int,
    style: str = "casebook",
    is_vertical: bool = False,
) -> np.ndarray:
    """Generates a physical background canvas: wooden desk/leather cover + open paper spread."""
    palette = STYLE_THEMES.get(style, STYLE_THEMES["casebook"])

    # 1. Desk/Cover Base Plate
    canvas = np.full((height, width, 3), palette["desk_base"], dtype=np.uint8)

    # Subtle wood grain / leather surface striations
    noise = np.random.normal(0.0, 4.0, (height, width, 1)).astype(np.float32)
    canvas = np.clip(canvas.astype(np.float32) + noise, 0, 255).astype(np.uint8)

    # 2. Paper Margins (Inset to reveal desk/cover border)
    if is_vertical:
        # Vertical Short (9:16): Single portrait archival page
        margin_x = int(width * 0.05)
        margin_y = int(height * 0.04)
        p_w = width - (2 * margin_x)
        p_h = height - (2 * margin_y)
        paper_rect = (margin_x, margin_y, p_w, p_h)
    else:
        # Widescreen (16:9): Two-page book spread
        margin_x = int(width * 0.04)
        margin_y = int(height * 0.05)
        p_w = width - (2 * margin_x)
        p_h = height - (2 * margin_y)
        paper_rect = (margin_x, margin_y, p_w, p_h)

    px, py, pw, ph = paper_rect

    # 3. Paper Sheet with subtle gradient & fiber noise
    paper = np.full((ph, pw, 3), palette["paper_base"], dtype=np.float32)

    # Organic paper fibers & edge darkening
    y_coords, x_coords = np.ogrid[:ph, :pw]
    cx, cy = pw / 2.0, ph / 2.0
    dist_x = np.abs(x_coords - cx) / cx
    dist_y = np.abs(y_coords - cy) / cy
    edge_falloff = np.clip(1.0 - 0.12 * (dist_x**3 + dist_y**3), 0.70, 1.0)[..., None]
    paper = paper * edge_falloff

    # Micro paper grain
    paper_noise = np.random.normal(0.0, 3.5, (ph, pw, 1)).astype(np.float32)
    paper = np.clip(paper + paper_noise, 0, 255).astype(np.uint8)

    # 4. Center Spine Gutter Crease Shadow (For 16:9 spreads)
    if not is_vertical:
        gutter_cx = pw // 2
        gutter_w = int(pw * 0.08)
        x_indices = np.arange(pw)
        dist_from_gutter = np.abs(x_indices - gutter_cx) / float(gutter_w)
        gutter_mask = np.clip(1.0 - dist_from_gutter, 0.0, 1.0)
        gutter_mask = (gutter_mask ** 2.0) * 0.35  # Max 35% shadow depth
        gutter_mask = gutter_mask[None, :, None]
        paper = (paper.astype(np.float32) * (1.0 - gutter_mask)).astype(np.uint8)

        # Thin dark center fold crease line
        cv2.line(paper, (gutter_cx, 0), (gutter_cx, ph), palette["spine_shadow"], 1, cv2.LINE_AA)

    # 5. Gilded Border / Rule Lines for Classic Style
    if style == "classic":
        gold_color = palette.get("gold_foil", (55, 175, 212))
        inset = 18
        # Outer thin gold hairline
        cv2.rectangle(paper, (inset, inset), (pw - inset, ph - inset), gold_color, 1, cv2.LINE_AA)
        # Inner thin gold hairline
        cv2.rectangle(paper, (inset + 6, inset + 6), (pw - inset - 6, ph - inset - 6), gold_color, 1, cv2.LINE_AA)
        # Corner gold dots
        for cx_pt, cy_pt in [(inset + 3, inset + 3), (pw - inset - 3, inset + 3),
                             (inset + 3, ph - inset - 3), (pw - inset - 3, ph - inset - 3)]:
            cv2.circle(paper, (cx_pt, cy_pt), 3, gold_color, -1, cv2.LINE_AA)

    # 6. Cast Shadow of the entire page onto the desk
    shadow_mask = np.zeros((height, width), dtype=np.float32)
    cv2.rectangle(shadow_mask, (px + 10, py + 12), (px + pw + 10, py + ph + 12), 0.40, -1)
    shadow_mask = cv2.GaussianBlur(shadow_mask, (45, 45), 18.0)[..., None]
    canvas = (canvas.astype(np.float32) * (1.0 - shadow_mask)).astype(np.uint8)

    # Blit paper onto canvas
    canvas[py:py + ph, px:px + pw] = paper
    return canvas


# ---------------------------------------------------------------------------
# 2. 3D POP-UP PHOTO PLATE WITH CAST DROP SHADOW
# ---------------------------------------------------------------------------

def create_photo_plate(
    photo_bgr: np.ndarray,
    target_width: int,
    border_style: str = "polaroid",
    label_text: Optional[str] = None,
) -> np.ndarray:
    """Mounts a raw photo onto a physical paper plate with borders and optional label."""
    h_orig, w_orig = photo_bgr.shape[:2]
    aspect = h_orig / float(w_orig)
    inner_w = target_width
    inner_h = int(round(inner_w * aspect))
    resized_photo = cv2.resize(photo_bgr, (inner_w, inner_h), interpolation=cv2.INTER_LANCZOS4)

    # Border margins (Polaroid vs archival mount)
    border_top = 16
    border_side = 16
    border_bottom = 54 if (border_style == "polaroid" or label_text) else 20

    plate_w = inner_w + (2 * border_side)
    plate_h = inner_h + border_top + border_bottom

    # Archival cardstock base (off-white cream)
    plate = np.full((plate_h, plate_w, 3), (242, 246, 250), dtype=np.uint8)

    # Subtle cardstock noise
    card_noise = np.random.normal(0.0, 2.5, (plate_h, plate_w, 1)).astype(np.float32)
    plate = np.clip(plate.astype(np.float32) + card_noise, 0, 255).astype(np.uint8)

    # Thin inner border inset
    cv2.rectangle(plate, (border_side - 1, border_top - 1),
                  (border_side + inner_w, border_top + inner_h), (190, 200, 210), 1, cv2.LINE_AA)

    # Place resized photo
    plate[border_top:border_top + inner_h, border_side:border_side + inner_w] = resized_photo

    # Optional handwritten label at bottom margin
    if label_text:
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.55
        thickness = 1
        text_size = cv2.getTextSize(label_text, font, scale, thickness)[0]
        tx = (plate_w - text_size[0]) // 2
        ty = inner_h + border_top + ((border_bottom + text_size[1]) // 2) - 4
        # Slightly faded black ink
        cv2.putText(plate, label_text, (tx, ty), font, scale, (45, 42, 38), thickness, cv2.LINE_AA)

    return plate


def composite_plate_with_shadow(
    canvas: np.ndarray,
    plate: np.ndarray,
    center_x: int,
    center_y: int,
    angle_deg: float = 0.0,
    shadow_offset: Tuple[int, int] = (16, 20),
    shadow_blur: int = 25,
    shadow_alpha: float = 0.38,
) -> np.ndarray:
    """Renders a photo plate with a soft directional Gaussian drop shadow onto canvas."""
    c_h, c_w = canvas.shape[:2]
    p_h, p_w = plate.shape[:2]

    # Create enlarged bounding box for rotation
    rad = math.radians(angle_deg)
    cos_a, sin_a = abs(math.cos(rad)), abs(math.sin(rad))
    rot_w = int(p_w * cos_a + p_h * sin_a) + 60
    rot_h = int(p_w * sin_a + p_h * cos_a) + 60

    # 1. Rotate plate image
    M_rot = cv2.getRotationMatrix2D((p_w / 2.0, p_h / 2.0), angle_deg, 1.0)
    M_rot[0, 2] += (rot_w - p_w) / 2.0
    M_rot[1, 2] += (rot_h - p_h) / 2.0

    rot_plate = cv2.warpAffine(plate, M_rot, (rot_w, rot_h), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0))

    # Mask for plate alpha
    plate_alpha = np.ones((p_h, p_w), dtype=np.float32)
    rot_alpha = cv2.warpAffine(plate_alpha, M_rot, (rot_w, rot_h), flags=cv2.INTER_LINEAR, borderValue=0.0)

    # 2. Render Cast Drop Shadow
    full_mask = np.zeros((c_h, c_w), dtype=np.float32)

    top_left_x = int(center_x - (rot_w // 2))
    top_left_y = int(center_y - (rot_h // 2))

    sh_dx, sh_dy = shadow_offset
    sh_x = top_left_x + sh_dx
    sh_y = top_left_y + sh_dy

    # Clamp shadow placement
    sx1 = max(0, sh_x)
    sy1 = max(0, sh_y)
    sx2 = min(c_w, sh_x + rot_w)
    sy2 = min(c_h, sh_y + rot_h)

    rx1 = sx1 - sh_x
    ry1 = sy1 - sh_y
    rx2 = rx1 + (sx2 - sx1)
    ry2 = ry1 + (sy2 - sy1)

    if rx2 > rx1 and ry2 > ry1:
        full_mask[sy1:sy2, sx1:sx2] = rot_alpha[ry1:ry2, rx1:rx2] * shadow_alpha

    # Gaussian blur shadow for realistic penumbra
    blur_k = shadow_blur if (shadow_blur % 2 == 1) else (shadow_blur + 1)
    full_mask = cv2.GaussianBlur(full_mask, (blur_k, blur_k), shadow_blur * 0.60)[..., None]

    # Blend shadow onto canvas
    canvas = (canvas.astype(np.float32) * (1.0 - full_mask)).astype(np.uint8)

    # 3. Composite rotated plate over shadowed canvas
    px1 = max(0, top_left_x)
    py1 = max(0, top_left_y)
    px2 = min(c_w, top_left_x + rot_w)
    py2 = min(c_h, top_left_y + rot_h)

    prx1 = px1 - top_left_x
    pry1 = py1 - top_left_y
    prx2 = prx1 + (px2 - px1)
    pry2 = pry1 + (py2 - py1)

    if prx2 > prx1 and pry2 > pry1:
        overlay_rgb = rot_plate[pry1:pry2, prx1:prx2]
        overlay_a = rot_alpha[pry1:pry2, prx1:prx2][..., None]

        target_roi = canvas[py1:py2, px1:px2]
        canvas[py1:py2, px1:px2] = np.clip(
            target_roi * (1.0 - overlay_a) + overlay_rgb * overlay_a, 0, 255
        ).astype(np.uint8)

    return canvas


# ---------------------------------------------------------------------------
# 3. DIEGETIC FASTENERS, ANNOTATIONS & RUBBER STAMPS
# ---------------------------------------------------------------------------

def draw_frosted_scotch_tape(
    canvas: np.ndarray,
    center_x: int,
    center_y: int,
    width: int = 70,
    height: int = 24,
    angle_deg: float = -25.0,
    style: str = "casebook",
) -> np.ndarray:
    """Renders semi-transparent frosted scotch tape with edge highlights."""
    c_h, c_w = canvas.shape[:2]
    tint = STYLE_THEMES.get(style, STYLE_THEMES["casebook"])["tape_tint"]

    tape = np.full((height, width, 3), tint, dtype=np.uint8)
    # Subtle inner tape surface texture
    tape_noise = np.random.normal(0.0, 3.0, (height, width, 1)).astype(np.float32)
    tape = np.clip(tape.astype(np.float32) + tape_noise, 0, 255).astype(np.uint8)

    # Top/bottom edge reflection highlights
    cv2.line(tape, (0, 0), (width, 0), (255, 255, 255), 1, cv2.LINE_AA)
    cv2.line(tape, (0, height - 1), (width, height - 1), (180, 190, 200), 1, cv2.LINE_AA)

    # Alpha mask (semi-transparent ~55%)
    alpha = np.full((height, width), 0.55, dtype=np.float32)

    # Rotate tape
    M_rot = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), angle_deg, 1.0)
    rad = math.radians(angle_deg)
    rot_w = int(width * abs(math.cos(rad)) + height * abs(math.sin(rad))) + 10
    rot_h = int(width * abs(math.sin(rad)) + height * abs(math.cos(rad))) + 10
    M_rot[0, 2] += (rot_w - width) / 2.0
    M_rot[1, 2] += (rot_h - height) / 2.0

    rot_tape = cv2.warpAffine(tape, M_rot, (rot_w, rot_h), flags=cv2.INTER_LINEAR)
    rot_alpha = cv2.warpAffine(alpha, M_rot, (rot_w, rot_h), flags=cv2.INTER_LINEAR)[..., None]

    tx = int(center_x - (rot_w // 2))
    ty = int(center_y - (rot_h // 2))

    x1, y1 = max(0, tx), max(0, ty)
    x2, y2 = min(c_w, tx + rot_w), min(c_h, ty + rot_h)

    rx1, ry1 = x1 - tx, y1 - ty
    rx2, ry2 = rx1 + (x2 - x1), ry1 + (y2 - y1)

    if rx2 > rx1 and ry2 > ry1:
        roi = canvas[y1:y2, x1:x2]
        canvas[y1:y2, x1:x2] = np.clip(
            roi * (1.0 - rot_alpha[ry1:ry2, rx1:rx2]) + rot_tape[ry1:ry2, rx1:rx2] * rot_alpha[ry1:ry2, rx1:rx2],
            0, 255,
        ).astype(np.uint8)

    return canvas


def draw_rubber_stamp(
    canvas: np.ndarray,
    text: str,
    center_x: int,
    center_y: int,
    angle_deg: float = -12.0,
    style: str = "casebook",
) -> np.ndarray:
    """Renders a weathered rubber ink stamp with bordered frame."""
    stamp_color = STYLE_THEMES.get(style, STYLE_THEMES["casebook"])["stamp_ink"]
    font = cv2.FONT_HERSHEY_DUPLEX
    scale = 1.1
    thickness = 2

    text_size = cv2.getTextSize(text.upper(), font, scale, thickness)[0]
    box_w = text_size[0] + 36
    box_h = text_size[1] + 24

    stamp_layer = np.zeros((box_h, box_w, 3), dtype=np.uint8)
    alpha_layer = np.zeros((box_h, box_w), dtype=np.float32)

    # Stamp border
    cv2.rectangle(stamp_layer, (4, 4), (box_w - 4, box_h - 4), stamp_color, 3, cv2.LINE_AA)
    cv2.rectangle(alpha_layer, (4, 4), (box_w - 4, box_h - 4), 0.85, 3, cv2.LINE_AA)

    # Stamp text
    tx = (box_w - text_size[0]) // 2
    ty = (box_h + text_size[1]) // 2 - 2
    cv2.putText(stamp_layer, text.upper(), (tx, ty), font, scale, stamp_color, thickness, cv2.LINE_AA)
    cv2.putText(alpha_layer, text.upper(), (tx, ty), font, scale, 0.85, thickness, cv2.LINE_AA)

    # Weathered stamp ink erosion
    erosion_noise = np.random.uniform(0.5, 1.0, (box_h, box_w))
    alpha_layer = alpha_layer * erosion_noise

    # Rotate stamp
    rad = math.radians(angle_deg)
    rot_w = int(box_w * abs(math.cos(rad)) + box_h * abs(math.sin(rad))) + 20
    rot_h = int(box_w * abs(math.sin(rad)) + box_h * abs(math.cos(rad))) + 20

    M_rot = cv2.getRotationMatrix2D((box_w / 2.0, box_h / 2.0), angle_deg, 1.0)
    M_rot[0, 2] += (rot_w - box_w) / 2.0
    M_rot[1, 2] += (rot_h - box_h) / 2.0

    rot_stamp = cv2.warpAffine(stamp_layer, M_rot, (rot_w, rot_h), flags=cv2.INTER_LINEAR)
    rot_alpha = cv2.warpAffine(alpha_layer, M_rot, (rot_w, rot_h), flags=cv2.INTER_LINEAR)[..., None]

    c_h, c_w = canvas.shape[:2]
    top_x = int(center_x - (rot_w // 2))
    top_y = int(center_y - (rot_h // 2))

    x1, y1 = max(0, top_x), max(0, top_y)
    x2, y2 = min(c_w, top_x + rot_w), min(c_h, top_y + rot_h)

    rx1, ry1 = x1 - top_x, y1 - top_y
    rx2, ry2 = rx1 + (x2 - x1), ry1 + (y2 - y1)

    if rx2 > rx1 and ry2 > ry1:
        roi = canvas[y1:y2, x1:x2]
        canvas[y1:y2, x1:x2] = np.clip(
            roi * (1.0 - rot_alpha[ry1:ry2, rx1:rx2]) + rot_stamp[ry1:ry2, rx1:rx2] * rot_alpha[ry1:ry2, rx1:rx2],
            0, 255,
        ).astype(np.uint8)

    return canvas


def draw_forensic_circle(
    canvas: np.ndarray,
    center_x: int,
    center_y: int,
    radius: int = 50,
    style: str = "casebook",
) -> np.ndarray:
    """Renders a hand-drawn red ballpoint/marker circle around key visual evidence."""
    ink_color = STYLE_THEMES.get(style, STYLE_THEMES["casebook"])["red_ink"]
    # Hand-drawn jitter with slight elliptical wobble
    axes = (int(radius * 1.08), int(radius * 0.94))
    cv2.ellipse(canvas, (center_x, center_y), axes, 15, 0, 360, ink_color, 2, cv2.LINE_AA)
    # Double stroke imperfection
    cv2.ellipse(canvas, (center_x + 1, center_y - 1), (radius + 2, radius - 1), 18, 10, 340, ink_color, 1, cv2.LINE_AA)
    return canvas


def draw_brass_pushpin(
    canvas: np.ndarray,
    center_x: int,
    center_y: int,
    radius: int = 15,
    color_bgr: Tuple[int, int, int] = (45, 175, 225),  # Polished brass
) -> np.ndarray:
    """Renders a 3D metallic brass pushpin with drop shadow, spherical bevel and specular glare."""
    # 1. Cast directional drop shadow
    sh_x, sh_y = center_x + 7, center_y + 9
    cv2.circle(canvas, (sh_x, sh_y), radius + 2, (15, 18, 24), -1, cv2.LINE_AA)
    # 2. Outer metallic rim
    cv2.circle(canvas, (center_x, center_y), radius, color_bgr, -1, cv2.LINE_AA)
    cv2.circle(canvas, (center_x, center_y), radius, (30, 115, 155), 2, cv2.LINE_AA)
    # 3. Inner spherical dome bevel
    cv2.circle(canvas, (center_x - 2, center_y - 2), int(radius * 0.65), (85, 210, 255), -1, cv2.LINE_AA)
    # 4. Specular glare point
    cv2.circle(canvas, (center_x - 4, center_y - 4), max(2, int(radius * 0.28)), (255, 255, 255), -1, cv2.LINE_AA)
    return canvas


def draw_highlighter_bar(
    canvas: np.ndarray,
    x: int,
    y: int,
    width: int,
    height: int = 26,
    color: Tuple[int, int, int] = (35, 230, 255),  # Vibrant yellow (BGR)
    alpha: float = 0.44,
) -> np.ndarray:
    """Renders a semi-transparent fluorescent yellow highlighter stroke."""
    c_h, c_w = canvas.shape[:2]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(c_w, x + width), min(c_h, y + height)
    if x2 > x1 and y2 > y1:
        roi = canvas[y1:y2, x1:x2].astype(np.float32)
        overlay = np.full_like(roi, color, dtype=np.float32)
        canvas[y1:y2, x1:x2] = np.clip(roi * (1.0 - alpha) + overlay * alpha, 0, 255).astype(np.uint8)
    return canvas


def draw_gold_embossed_seal(
    canvas: np.ndarray,
    center_x: int,
    center_y: int,
    text: str = "ARCHIVE",
    radius: int = 44,
) -> np.ndarray:
    """Renders an ornate circular gilded gold embossed bookplate seal for classic style."""
    gold_primary = (55, 175, 212)    # Gold BGR (#D4AF37)
    gold_shadow = (35, 110, 140)
    gold_light = (110, 215, 250)

    # 1. Drop shadow
    cv2.circle(canvas, (center_x + 6, center_y + 8), radius + 2, (18, 22, 30), -1, cv2.LINE_AA)
    # 2. Concentric gold ridges
    cv2.circle(canvas, (center_x, center_y), radius, gold_primary, -1, cv2.LINE_AA)
    cv2.circle(canvas, (center_x, center_y), radius, gold_shadow, 2, cv2.LINE_AA)
    cv2.circle(canvas, (center_x, center_y), radius - 6, gold_light, 1, cv2.LINE_AA)
    cv2.circle(canvas, (center_x, center_y), radius - 10, gold_shadow, 1, cv2.LINE_AA)

    # 3. Roman embossed typography
    font = cv2.FONT_HERSHEY_DUPLEX
    scale = 0.52
    t_size = cv2.getTextSize(text.upper(), font, scale, 1)[0]
    tx = center_x - (t_size[0] // 2)
    ty = center_y + (t_size[1] // 2) - 1
    cv2.putText(canvas, text.upper(), (tx + 1, ty + 1), font, scale, gold_shadow, 1, cv2.LINE_AA)
    cv2.putText(canvas, text.upper(), (tx, ty), font, scale, (255, 255, 255), 1, cv2.LINE_AA)
    return canvas


# ---------------------------------------------------------------------------
# 4. MASTER SCENE COMPOSITOR (SHORT & LONG-FORM)
# ---------------------------------------------------------------------------

def compose_storybook_scene_plate(
    image_bgr: np.ndarray,
    width: int = 1920,
    height: int = 1080,
    style: str = "casebook",
    stamp_text: Optional[str] = None,
    plate_label: Optional[str] = None,
    add_tape: bool = True,
    add_circle: bool = False,
    circle_pos: Optional[Tuple[int, int]] = None,
) -> np.ndarray:
    """Composites a single master storybook frame with all physical layers."""
    is_vertical = height > width

    # 1. Base Canvas
    canvas = generate_storybook_canvas(width, height, style=style, is_vertical=is_vertical)

    # 2. Compute Plate placement & scale
    if is_vertical:
        # Short (9:16): Plate centered horizontally, sits inside upper safe band
        plate_w = int(width * 0.74)
        center_x = width // 2
        center_y = int(height * 0.44)
        tilt = -1.5
    else:
        # Long (16:9): Plate sits on Left Page of the book spread
        plate_w = int(width * 0.42)
        center_x = int(width * 0.28)
        center_y = height // 2
        tilt = -1.2

    # 3. Build & Composite Photo Plate with real drop shadow
    plate = create_photo_plate(image_bgr, target_width=plate_w, border_style="polaroid", label_text=plate_label)
    canvas = composite_plate_with_shadow(canvas, plate, center_x, center_y, angle_deg=tilt)

    # 4. Fasteners & Mounts based on Style
    p_h, p_w = plate.shape[:2]
    if style == "scrapbook":
        # 3D Brass Pushpin at top center of photo
        pin_x = center_x
        pin_y = center_y - (p_h // 2) + 14
        canvas = draw_brass_pushpin(canvas, pin_x, pin_y, radius=16)

        # Highlight evidence note if label exists
        if plate_label:
            hl_w = int(plate_w * 0.55)
            hl_x = center_x - (hl_w // 2)
            hl_y = center_y + (p_h // 2) - 34
            canvas = draw_highlighter_bar(canvas, hl_x, hl_y, width=hl_w, height=22)

        # Single masking tape piece on corner
        if add_tape:
            br_x = center_x + (p_w // 2) - 16
            br_y = center_y + (p_h // 2) - 12
            canvas = draw_frosted_scotch_tape(canvas, br_x, br_y, width=int(plate_w * 0.20), height=20, angle_deg=-20.0, style=style)
    elif style == "classic":
        # Parchment corner mounting tabs
        if add_tape:
            tape_w = int(plate_w * 0.18)
            tape_h = max(16, int(tape_w * 0.32))
            tl_x = center_x - (p_w // 2) + 10
            tl_y = center_y - (p_h // 2) + 8
            canvas = draw_frosted_scotch_tape(canvas, tl_x, tl_y, width=tape_w, height=tape_h, angle_deg=-35.0, style=style)
            br_x = center_x + (p_w // 2) - 12
            br_y = center_y + (p_h // 2) - 8
            canvas = draw_frosted_scotch_tape(canvas, br_x, br_y, width=tape_w, height=tape_h, angle_deg=-30.0, style=style)
    else:
        # Default Casebook: Diegetic Scotch Tape on corners
        if add_tape:
            tape_w = int(plate_w * 0.22)
            tape_h = max(18, int(tape_w * 0.35))
            tl_x = center_x - (p_w // 2) + 12
            tl_y = center_y - (p_h // 2) + 10
            canvas = draw_frosted_scotch_tape(canvas, tl_x, tl_y, width=tape_w, height=tape_h, angle_deg=-30.0, style=style)
            br_x = center_x + (p_w // 2) - 14
            br_y = center_y + (p_h // 2) - 10
            canvas = draw_frosted_scotch_tape(canvas, br_x, br_y, width=tape_w, height=tape_h, angle_deg=-25.0, style=style)

    # 5. Forensic Circle if requested
    if add_circle:
        cx, cy = circle_pos if circle_pos else (center_x + int(plate_w * 0.15), center_y - 20)
        canvas = draw_forensic_circle(canvas, cx, cy, radius=int(plate_w * 0.18), style=style)

    # 6. Rubber Stamp or Gilded Seal
    if style == "classic":
        seal_x = center_x + int(plate_w * 0.30) if is_vertical else int(width * 0.75)
        seal_y = center_y + int(plate_w * 0.30) if is_vertical else int(height * 0.45)
        canvas = draw_gold_embossed_seal(canvas, seal_x, seal_y, text=(stamp_text or "ARCHIVE"))
    elif stamp_text:
        stamp_x = center_x + int(plate_w * 0.28) if is_vertical else int(width * 0.75)
        stamp_y = center_y + int(plate_w * 0.32) if is_vertical else int(height * 0.45)
        canvas = draw_rubber_stamp(canvas, stamp_text, stamp_x, stamp_y, angle_deg=-14.0, style=style)

    return canvas


# ---------------------------------------------------------------------------
# 5. SMOOTH S-CURVE SPREAD NAVIGATION & VIDEO CLIP GENERATOR
# ---------------------------------------------------------------------------

def render_storybook_clip(
    image_path: Path,
    output_mp4: Path,
    duration_s: float = 3.5,
    fps: int = 30,
    width: int = 1920,
    height: int = 1080,
    style: str = "casebook",
    stamp_text: Optional[str] = None,
    plate_label: Optional[str] = None,
    motion_preset: str = "spread_pan",
) -> bool:
    """Renders a continuous 30 fps storybook camera clip to broadcast MP4."""
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    src_bgr = cv2.imread(str(image_path))
    if src_bgr is None:
        raise ValueError(f"Cannot read image: {image_path}")

    # Generate oversized master canvas (1.06x) for subtle, silky-smooth documentary drift
    oversample = 1.06
    master_w = int(round(width * oversample))
    master_h = int(round(height * oversample))

    master_frame = compose_storybook_scene_plate(
        src_bgr,
        width=master_w,
        height=master_h,
        style=style,
        stamp_text=stamp_text,
        plate_label=plate_label,
    )

    num_frames = int(round(duration_s * fps))
    tmp_raw = output_mp4.with_suffix(".story.raw.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(tmp_raw), fourcc, float(fps), (width, height))

    if not writer.isOpened():
        raise RuntimeError(f"Cannot open video writer: {tmp_raw}")

    is_vertical = height > width
    max_pan_x = master_w - width
    max_pan_y = master_h - height

    try:
        for f_idx in range(num_frames):
            p = f_idx / max(1, num_frames - 1)
            e = s_curve_ease(p)

            if motion_preset == "spread_pan" and not is_vertical:
                # Widescreen: Smooth subtle camera drift across the spread
                crop_x = int(e * max_pan_x * 0.75)
                crop_y = int(max_pan_y * 0.5)
            elif motion_preset == "dolly_in":
                # Subtle push-in onto the plate
                crop_x = int((max_pan_x / 2.0) * (1.0 - (e * 0.15)))
                crop_y = int((max_pan_y / 2.0) * (1.0 - (e * 0.15)))
            else:
                # Default slow lateral drift
                crop_x = int((e * 0.5 + 0.25) * max_pan_x)
                crop_y = int((0.5 + 0.05 * math.sin(e * math.pi)) * max_pan_y)

            crop_x = max(0, min(max_pan_x, crop_x))
            crop_y = max(0, min(max_pan_y, crop_y))

            frame = master_frame[crop_y:crop_y + height, crop_x:crop_x + width].copy()

            # Add subtle 35mm archival grain
            grain = generate_film_grain(height, width, intensity=5.0)
            vignette = apply_optical_vignette(frame, strength=0.35)
            final_frame = np.clip(vignette.astype(np.float32) + grain, 0, 255).astype(np.uint8)

            writer.write(final_frame)
    finally:
        writer.release()

    # Re-encode via broadcast pipeline using explicit encoder config
    from tools.encoder_config import resolve_encoder
    from tools.errors import RenderingError

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise RenderingError(stage="render_storybook_clip", artifact=str(output_mp4), cause="ffmpeg not found on PATH")

    _, enc_args = resolve_encoder(crf=17)
    cmd = [
        ffmpeg_bin, "-y",
        "-i", str(tmp_raw),
        *enc_args,
        "-colorspace", "bt709",
        "-color_trc", "bt709",
        "-color_primaries", "bt709",
        "-r", str(fps),
        str(output_mp4),
    ]
    proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if proc.returncode != 0 or not output_mp4.exists() or output_mp4.stat().st_size == 0:
        raise RenderingError(
            stage="render_storybook_clip",
            artifact=str(output_mp4),
            cause=f"Failed to encode storybook clip (returncode={proc.returncode})",
        )
    if tmp_raw.exists():
        tmp_raw.unlink(missing_ok=True)
    return True


# ---------------------------------------------------------------------------
# CLI FOR TESTING & DEMO GENERATION
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="FrameForge Tactile Storybook Engine")
    ap.add_argument("--image", "-i", type=Path, required=True, help="Input source image")
    ap.add_argument("--output", "-o", type=Path, required=True, help="Output MP4 clip or JPG frame")
    ap.add_argument("--style", "-s", type=str, default="casebook", choices=["casebook", "classic"], help="Aesthetic style")
    ap.add_argument("--stamp", type=str, default=None, help="Rubber stamp text (e.g. 'EXHIBIT A')")
    ap.add_argument("--label", type=str, default=None, help="Handwritten label text at bottom of plate")
    ap.add_argument("--duration", "-d", type=float, default=3.5, help="Clip duration in seconds")
    ap.add_argument("--format", "-f", type=str, default="16:9", choices=["16:9", "9:16"], help="Aspect ratio")
    ap.add_argument("--still-only", action="store_true", help="Output single composited JPG frame instead of MP4")

    args = ap.parse_args()

    w = 1920 if args.format == "16:9" else 1080
    h = 1080 if args.format == "16:9" else 1920

    if args.still_only:
        src = cv2.imread(str(args.image))
        if src is None:
            print(f"Error: Could not load image {args.image}", file=sys.stderr)
            return 1
        frame = compose_storybook_scene_plate(
            src, width=w, height=h, style=args.style,
            stamp_text=args.stamp, plate_label=args.label,
        )
        cv2.imwrite(str(args.output), frame)
        print(f"✅ Rendered storybook still frame ({args.style}): {args.output}")
        return 0

    print(f"🎬 Rendering {args.format} Storybook Clip ({args.style}): {args.output}...")
    ok = render_storybook_clip(
        image_path=args.image,
        output_mp4=args.output,
        duration_s=args.duration,
        width=w,
        height=h,
        style=args.style,
        stamp_text=args.stamp,
        plate_label=args.label,
    )
    if ok:
        print(f"✅ Storybook clip rendered successfully: {args.output}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
