#!/usr/bin/env python3
"""FrameForge Interactive Riddle & Logic HUD Engine (tools/riddle_director.py).

Reverse-engineered from viral detective and riddle channels (@grandmasterdetective,
7-Second Riddles, Detective Mehul, TED-Ed Riddles).

Core Architectural Features:
  1. Interactive Clue Inventory HUD:
     - Docked top-bar tracking available elements (e.g. "⚪ 3 | ⚫ 2", keys, vials, clues).
     - Visual badge counters with active/eliminated states.
  2. Character Identification Badges & Thought Overlays:
     - Floating numbered pins (①, ②, ③) or suspect labels anchored above character positions.
     - Pulsing thought bubbles with interrogation question marks.
  3. Field-of-View (FOV) Sightline Ray Visualizer:
     - Renders directed sight cones or animated ray lines indicating line-of-sight constraints
       (e.g. Prisoner 3 sees 2 & 1; Prisoner 1 sees nothing).
  4. Epistemic Elimination & Deduction Overlays:
     - Animated cross-outs (✖) and red strike-throughs for eliminated hypotheses.
     - Green validation stamps (✔) for deduced truths.
  5. Urgent Countdown Ticker HUD:
     - Circular radial gauge or digital timer (e.g. 7-second brain teaser clock)
       shifting dynamically from calm cyan to urgent crimson.
  6. Viral Comment Engine CTA:
     - High-retention safe-zone banner ("PART 2 TONIGHT / DROP DEDUCTION IN COMMENTS")
       locking the open loop for algorithmic comment velocity.
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np


# ---------------------------------------------------------------------------
# DATA STRUCTURES
# ---------------------------------------------------------------------------

@dataclass
class InventoryItem:
    """An item displayed in the top clue tracker."""
    label: str               # Text or emoji label (e.g. "White", "Black", "Key")
    count: int               # Current available count
    color: Tuple[int, int, int] = (255, 255, 255)  # BGR color for circle/icon
    symbol: str = "O"        # "O" for circle, "X" for crossed, or custom text


@dataclass
class CharacterAnchor:
    """Position and visual state of a character in the scene."""
    id: str                  # Unique identifier ("1", "2", "3", "A", "B")
    name: str                # Display name (e.g. "Prisoner 1", "Suspect A")
    x: float                 # Normalized X position (0.0 to 1.0)
    y: float                 # Normalized Y position (0.0 to 1.0)
    badge_label: str = "①"   # Badge symbol or number
    is_active: bool = True
    eliminated: bool = False
    thought_text: Optional[str] = None  # e.g. "?" or "Guilty"


@dataclass
class SightlineRay:
    """Directed line of sight between two characters or points."""
    from_id: str             # Source character ID
    to_id: str               # Target character ID
    color: Tuple[int, int, int] = (0, 229, 255)  # Electric Cyan (BGR)
    blocked: bool = False    # True if vision is occluded / blindfolded


@dataclass
class RiddleSceneSpec:
    """Complete specification for an interactive riddle scene."""
    title: str
    inventory: List[InventoryItem] = field(default_factory=list)
    characters: List[CharacterAnchor] = field(default_factory=list)
    sightlines: List[SightlineRay] = field(default_factory=list)
    countdown_seconds: Optional[float] = None
    elimination_banner: Optional[str] = None
    cta_banner: Optional[str] = None


# ---------------------------------------------------------------------------
# DRAWING HELPERS (HUD, BADGES, SIGHTLINES, COUNTDOWN)
# ---------------------------------------------------------------------------

def _ui_scale(w: int, h: int) -> float:
    """Proportional UI scale factor relative to 1080x1920 / 1920x1080 broadcast frame."""
    short_side = min(w, h)
    return max(0.28, short_side / 1080.0)


def _transform_point(x_px: float, y_px: float, camera_matrix: Optional[np.ndarray]) -> Tuple[int, int]:
    """Applies 2x3 affine camera transform matrix to a 2D pixel coordinate when provided."""
    if camera_matrix is not None and camera_matrix.shape == (2, 3):
        tx = float(camera_matrix[0, 0] * x_px + camera_matrix[0, 1] * y_px + camera_matrix[0, 2])
        ty = float(camera_matrix[1, 0] * x_px + camera_matrix[1, 1] * y_px + camera_matrix[1, 2])
        return int(round(tx)), int(round(ty))
    return int(round(x_px)), int(round(y_px))


def _wrap_text_to_width(text: str, font: int, font_scale: float, thickness: int, max_width: int) -> List[str]:
    """Wraps text into lines that fit within max_width pixels."""
    words = text.split()
    if not words:
        return [""]
    lines: List[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        tw = cv2.getTextSize(candidate, font, font_scale, thickness)[0][0]
        if tw <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def draw_glassmorphic_panel(
    canvas: np.ndarray,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    bg_color: Tuple[int, int, int] = (20, 24, 32),
    alpha: float = 0.82,
    border_color: Tuple[int, int, int] = (255, 179, 0),
    radius: int = 16,
) -> None:
    """Draws a rounded frosted glass HUD panel with border accent."""
    h, w = canvas.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    if x2 <= x1 or y2 <= y1:
        return

    sub = canvas[y1:y2, x1:x2]
    blurred = cv2.GaussianBlur(sub, (21, 21), 0)
    colored = np.full_like(sub, bg_color, dtype=np.uint8)
    comp = cv2.addWeighted(blurred, 1.0 - alpha, colored, alpha, 0)
    canvas[y1:y2, x1:x2] = comp

    # Draw refined outline
    cv2.rectangle(canvas, (x1, y1), (x2, y2), border_color, 2, cv2.LINE_AA)


def draw_inventory_hud(
    canvas: np.ndarray,
    items: List[InventoryItem],
    top_margin: Optional[int] = None,
) -> None:
    """Draws the top clue/hat inventory tracker bar scaled to canvas dimensions."""
    if not items:
        return

    h, w = canvas.shape[:2]
    scale = _ui_scale(w, h)
    if top_margin is None:
        top_margin = max(8, int(round(h * 0.04)))

    panel_w = min(int(w * 0.88), int(round(920 * max(1.0, w / 1080.0))))
    panel_h = max(28, int(round(74 * scale)))
    x1 = max(4, (w - panel_w) // 2)
    y1 = max(4, min(h - panel_h - 4, top_margin))
    x2 = min(w - 4, x1 + panel_w)
    y2 = min(h - 4, y1 + panel_h)

    # Glassmorphic background
    draw_glassmorphic_panel(canvas, x1, y1, x2, y2, bg_color=(15, 18, 26), alpha=0.88, border_color=(0, 229, 255))

    # Calculate item slot distribution
    num_items = len(items)
    slot_w = (x2 - x1) / num_items
    icon_r = max(6, int(round(16 * scale)))
    icon_offset = max(14, int(round(40 * scale)))
    font = cv2.FONT_HERSHEY_DUPLEX
    font_scale = max(0.32, 0.72 * scale)
    thickness = max(1, int(round(2 * scale)))

    for idx, item in enumerate(items):
        cx = int(x1 + slot_w * (idx + 0.5))
        cy = y1 + (y2 - y1) // 2

        # Draw item icon indicator (circle)
        icon_x = max(x1 + icon_r + 4, cx - icon_offset)
        cv2.circle(canvas, (icon_x, cy), icon_r, item.color, -1, cv2.LINE_AA)
        cv2.circle(canvas, (icon_x, cy), icon_r + 1, (20, 20, 20), max(1, thickness), cv2.LINE_AA)

        # Draw label & count fit within slot
        text = f"{item.label}: {item.count}"
        max_text_w = max(20, int(slot_w - (icon_x - (x1 + idx * slot_w)) - icon_r - 10))
        cur_scale = font_scale
        t_size = cv2.getTextSize(text, font, cur_scale, thickness)[0]
        if t_size[0] > max_text_w and t_size[0] > 0:
            cur_scale = max(0.25, cur_scale * (max_text_w / float(t_size[0])))
            t_size = cv2.getTextSize(text, font, cur_scale, thickness)[0]

        tx = min(int(x1 + slot_w * (idx + 1)) - t_size[0] - 4, icon_x + icon_r + max(4, int(round(8 * scale))))
        tx = max(icon_x + icon_r + 2, tx)
        ty = cy + t_size[1] // 2
        cv2.putText(canvas, text, (tx, ty), font, cur_scale, (255, 255, 255), thickness, cv2.LINE_AA)

        # Draw divider between items
        if idx < num_items - 1:
            div_x = int(x1 + slot_w * (idx + 1))
            pad_v = max(4, int(round(14 * scale)))
            cv2.line(canvas, (div_x, y1 + pad_v), (div_x, y2 - pad_v), (60, 75, 95), 1, cv2.LINE_AA)


def draw_character_badges(
    canvas: np.ndarray,
    characters: List[CharacterAnchor],
    pulse_phase: float = 0.0,
    camera_matrix: Optional[np.ndarray] = None,
) -> None:
    """Draws floating character badges with pulsing thought bubbles scaled & camera-aligned."""
    h, w = canvas.shape[:2]
    scale = _ui_scale(w, h)

    badge_radius = max(10, int(round(28 * scale)))
    badge_offset_y = max(24, int(round(70 * scale)))
    font = cv2.FONT_HERSHEY_DUPLEX
    lbl_scale = max(0.35, 0.85 * scale)
    tt_scale = max(0.32, 0.75 * scale)
    thickness = max(1, int(round(2 * scale)))

    for char in characters:
        px, py = _transform_point(char.x * w, char.y * h, camera_matrix)
        px = max(badge_radius + 4, min(w - badge_radius - 4, px))
        badge_y = max(badge_radius + 4, min(h - badge_radius - 4, py - badge_offset_y))

        # Pulsing rim
        pulse_r = int(badge_radius + max(2.0, 4.0 * scale) * math.sin(pulse_phase * math.pi * 2))
        cv2.circle(canvas, (px, badge_y), pulse_r, (0, 229, 255), max(1, thickness), cv2.LINE_AA)

        # Badge Fill
        fill_color = (30, 36, 48) if not char.eliminated else (20, 20, 140)
        cv2.circle(canvas, (px, badge_y), badge_radius, fill_color, -1, cv2.LINE_AA)
        border_col = (255, 179, 0) if not char.eliminated else (0, 0, 255)
        cv2.circle(canvas, (px, badge_y), badge_radius, border_col, max(1, thickness), cv2.LINE_AA)

        # Badge Label (e.g. "1", "2", "3")
        lbl = char.badge_label
        t_size = cv2.getTextSize(lbl, font, lbl_scale, thickness)[0]
        cv2.putText(
            canvas, lbl,
            (px - t_size[0] // 2, badge_y + t_size[1] // 2),
            font, lbl_scale, (255, 255, 255), thickness, cv2.LINE_AA
        )

        # Thought Bubble (e.g. "?")
        if char.thought_text:
            tb_r = max(8, int(round(20 * scale)))
            tb_x = min(w - tb_r - 4, px + int(round(45 * scale)))
            tb_y = max(tb_r + 4, badge_y - int(round(35 * scale)))
            # Small tail circles
            cv2.circle(canvas, (px + int(round(22 * scale)), badge_y - int(round(12 * scale))), max(2, int(round(4 * scale))), (255, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(canvas, (px + int(round(32 * scale)), badge_y - int(round(22 * scale))), max(3, int(round(7 * scale))), (255, 255, 255), -1, cv2.LINE_AA)
            # Main thought bubble
            cv2.circle(canvas, (tb_x, tb_y), tb_r, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(canvas, (tb_x, tb_y), tb_r, (0, 0, 0), max(1, thickness), cv2.LINE_AA)
            # Text inside bubble
            tt = char.thought_text
            tt_size = cv2.getTextSize(tt, font, tt_scale, thickness)[0]
            cv2.putText(
                canvas, tt,
                (tb_x - tt_size[0] // 2, tb_y + tt_size[1] // 2),
                font, tt_scale, (0, 0, 0), thickness, cv2.LINE_AA
            )

        # Draw elimination cross if character was eliminated/failed
        if char.eliminated:
            cr = max(8, int(round(22 * scale)))
            cv2.line(canvas, (px - cr, badge_y - cr), (px + cr, badge_y + cr), (0, 0, 255), max(2, int(round(4 * scale))), cv2.LINE_AA)
            cv2.line(canvas, (px + cr, badge_y - cr), (px - cr, badge_y + cr), (0, 0, 255), max(2, int(round(4 * scale))), cv2.LINE_AA)


def draw_sightlines(
    canvas: np.ndarray,
    sightlines: List[SightlineRay],
    characters: Dict[str, CharacterAnchor],
    dash_offset: float = 0.0,
    camera_matrix: Optional[np.ndarray] = None,
) -> None:
    """Draws animated field-of-view sightline rays between characters, aligned to camera transform."""
    h, w = canvas.shape[:2]
    scale = _ui_scale(w, h)

    for ray in sightlines:
        if ray.from_id not in characters or ray.to_id not in characters:
            continue

        c_from = characters[ray.from_id]
        c_to = characters[ray.to_id]

        x1, y1 = _transform_point(c_from.x * w, (c_from.y - 0.04) * h, camera_matrix)
        x2, y2 = _transform_point(c_to.x * w, (c_to.y - 0.04) * h, camera_matrix)

        if ray.blocked:
            # Draw blocked / red occluded sightline
            cv2.line(canvas, (x1, y1), (x2, y2), (0, 0, 180), max(1, int(round(2 * scale))), cv2.LINE_AA)
            mid_x = (x1 + x2) // 2
            mid_y = (y1 + y2) // 2
            b_scale = max(0.55, 1.2 * scale)
            b_th = max(1, int(round(2 * scale)))
            b_size = cv2.getTextSize("[BLOCKED]", cv2.FONT_HERSHEY_PLAIN, b_scale, b_th)[0]
            bx = max(4, min(w - b_size[0] - 4, mid_x - b_size[0] // 2))
            by = max(b_size[1] + 4, min(h - 4, mid_y - max(4, int(round(10 * scale)))))
            cv2.putText(canvas, "[BLOCKED]", (bx, by), cv2.FONT_HERSHEY_PLAIN, b_scale, (0, 0, 255), b_th, cv2.LINE_AA)
        else:
            # Animated dashed ray with glow
            dist = math.hypot(x2 - x1, y2 - y1)
            if dist < 1.0:
                continue

            dash_len = max(12.0, 32.0 * scale)
            num_dashes = max(3, int(dist / dash_len))
            glow_th = max(2, int(round(4 * scale)))
            for i in range(num_dashes):
                t_start = (i / num_dashes + dash_offset) % 1.0
                t_end = ((i + 0.6) / num_dashes + dash_offset) % 1.0
                if t_end > t_start:
                    dx1 = int(x1 + (x2 - x1) * t_start)
                    dy1 = int(y1 + (y2 - y1) * t_start)
                    dx2 = int(x1 + (x2 - x1) * t_end)
                    dy2 = int(y1 + (y2 - y1) * t_end)
                    # Outer glow + core ray
                    cv2.line(canvas, (dx1, dy1), (dx2, dy2), ray.color, glow_th, cv2.LINE_AA)
                    cv2.line(canvas, (dx1, dy1), (dx2, dy2), (255, 255, 255), 1, cv2.LINE_AA)

            # Draw target eye indicator
            cv2.circle(canvas, (x2, y2), max(3, int(round(6 * scale))), ray.color, -1, cv2.LINE_AA)


def draw_countdown_hud(
    canvas: np.ndarray,
    remaining_seconds: float,
    total_seconds: float,
    center_x: int,
    center_y: int,
    radius: Optional[int] = None,
) -> None:
    """Draws a circular radial ticking clock HUD with urgency color shifts scaled to frame."""
    h, w = canvas.shape[:2]
    scale = _ui_scale(w, h)
    if radius is None:
        radius = max(16, int(round(42 * scale)))

    center_x = max(radius + 6, min(w - radius - 6, center_x))
    center_y = max(radius + 6, min(h - radius - 6, center_y))

    progress = max(0.0, min(1.0, remaining_seconds / max(0.001, total_seconds)))

    # Urgency shift: Cyan (calm) -> Amber -> Crimson Red (urgent)
    if progress > 0.5:
        arc_color = (0, 229, 255)  # Cyan
    elif progress > 0.25:
        arc_color = (0, 179, 255)  # Amber
    else:
        arc_color = (0, 0, 255)    # Urgent Red

    ring_th = max(2, int(round(6 * (radius / 42.0))))
    # Background ring
    cv2.circle(canvas, (center_x, center_y), radius, (35, 42, 54), ring_th, cv2.LINE_AA)

    # Progress arc (starts from top -90 deg)
    angle = int(round(progress * 360))
    if angle > 0:
        cv2.ellipse(canvas, (center_x, center_y), (radius, radius), -90, 0, angle, arc_color, ring_th, cv2.LINE_AA)

    # Digital countdown text fitted inside ring
    time_str = f"{remaining_seconds:.1f}s"
    font = cv2.FONT_HERSHEY_DUPLEX
    font_scale = max(0.30, 0.72 * (radius / 42.0))
    thickness = max(1, int(round(2 * (radius / 42.0))))
    t_size = cv2.getTextSize(time_str, font, font_scale, thickness)[0]
    max_inner_w = max(12, int(radius * 1.45))
    if t_size[0] > max_inner_w and t_size[0] > 0:
        font_scale = max(0.25, font_scale * (max_inner_w / float(t_size[0])))
        t_size = cv2.getTextSize(time_str, font, font_scale, thickness)[0]
    cv2.putText(
        canvas, time_str,
        (center_x - t_size[0] // 2, center_y + t_size[1] // 2),
        font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA
    )


def draw_cliffhanger_cta(
    canvas: np.ndarray,
    banner_text: str,
    y_pos: int,
) -> None:
    """Draws a high-impact cliffhanger CTA banner within the 44%-76% safe zone without clipping."""
    h, w = canvas.shape[:2]
    scale = _ui_scale(w, h)
    banner_w = max(80, min(int(w * 0.90), int(round(960 * max(1.0, w / 1080.0)))))
    pad_x = max(8, int(round(20 * scale)))
    max_text_w = max(40, banner_w - 2 * pad_x)

    font = cv2.FONT_HERSHEY_DUPLEX
    font_scale = max(0.32, 0.78 * scale)
    thickness = max(1, int(round(2 * scale)))

    # Wrap text into at most 2 lines and scale down if any line still exceeds max_text_w
    lines = _wrap_text_to_width(banner_text.strip(), font, font_scale, thickness, max_text_w)
    if len(lines) > 2:
        for factor in (0.85, 0.72, 0.60, 0.50, 0.40):
            cand_scale = max(0.26, font_scale * factor)
            cand_lines = _wrap_text_to_width(banner_text.strip(), font, cand_scale, thickness, max_text_w)
            if len(cand_lines) <= 2:
                font_scale = cand_scale
                lines = cand_lines
                break
        else:
            words = banner_text.strip().split()
            mid = max(1, len(words) // 2)
            lines = [" ".join(words[:mid]), " ".join(words[mid:])]

    longest_w = max(cv2.getTextSize(ln, font, font_scale, thickness)[0][0] for ln in lines)
    if longest_w > max_text_w and longest_w > 0:
        font_scale = max(0.24, font_scale * (max_text_w / float(longest_w)))

    line_sizes = [cv2.getTextSize(ln, font, font_scale, thickness)[0] for ln in lines]
    line_h = max(sz[1] for sz in line_sizes) if line_sizes else int(round(20 * scale))
    line_gap = max(4, int(round(10 * scale)))
    total_text_h = len(lines) * line_h + max(0, len(lines) - 1) * line_gap
    pad_y = max(8, int(round(18 * scale)))
    banner_h = max(int(round(64 * scale)), total_text_h + 2 * pad_y)

    x1 = max(4, (w - banner_w) // 2)
    x2 = min(w - 4, x1 + banner_w)

    # Keep CTA inside the 44%..76% vertical safe zone
    safe_top = int(round(h * 0.44))
    safe_bot = int(round(h * 0.76))
    y1 = y_pos - banner_h // 2
    if safe_bot - safe_top >= banner_h:
        y1 = max(safe_top, min(safe_bot - banner_h, y1))
    else:
        y1 = max(4, min(h - banner_h - 4, y1))
    y2 = min(h - 4, y1 + banner_h)

    # Amber gold frosted banner
    draw_glassmorphic_panel(canvas, x1, y1, x2, y2, bg_color=(25, 22, 10), alpha=0.92, border_color=(255, 179, 0))

    # Render each line centered inside [x1, x2] and [y1, y2]
    start_y = y1 + ((y2 - y1) - total_text_h) // 2 + line_h
    for idx, (ln, sz) in enumerate(zip(lines, line_sizes)):
        tx = x1 + ((x2 - x1) - sz[0]) // 2
        ty = start_y + idx * (line_h + line_gap)
        cv2.putText(canvas, ln, (tx, ty), font, font_scale, (255, 235, 180), thickness, cv2.LINE_AA)


# ---------------------------------------------------------------------------
# CORE RIDDLE SCENE RENDERER
# ---------------------------------------------------------------------------

def render_riddle_scene(
    base_image: np.ndarray,
    spec: RiddleSceneSpec,
    output_path: Path,
    duration: float = 3.5,
    fps: int = 30,
    width: int = 1080,
    height: int = 1920,
) -> bool:
    """Renders a fully interactive riddle video clip with dynamic HUD overlays."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    width = (width // 2) * 2
    height = (height // 2) * 2
    num_frames = int(round(duration * fps))

    # Resize base image to canvas dimensions
    resized_base = cv2.resize(base_image, (width, height), interpolation=cv2.INTER_LANCZOS4)

    tmp_raw_mp4 = output_path.with_suffix(".riddle.raw.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(tmp_raw_mp4), fourcc, float(fps), (width, height))

    if not writer.isOpened():
        raise RuntimeError(f"Failed to open video writer for {tmp_raw_mp4}")

    char_dict = {char.id: char for char in spec.characters}

    try:
        for frame_idx in range(num_frames):
            p = frame_idx / max(1, num_frames - 1)
            frame = resized_base.copy()

            # 1. Subtle camera zoom on base plate (1.0 -> 1.04)
            zoom = 1.0 + (p * 0.04)
            M = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), 0.0, zoom)
            frame = cv2.warpAffine(frame, M, (width, height), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)

            # 2. Draw Field-of-View sightline rays (camera-aligned)
            draw_sightlines(frame, spec.sightlines, char_dict, dash_offset=(p * 2.0) % 1.0, camera_matrix=M)

            # 3. Draw Character Badges & Thoughts (camera-aligned)
            draw_character_badges(frame, spec.characters, pulse_phase=p * 2.0, camera_matrix=M)

            # 4. Draw Top Inventory HUD Bar
            draw_inventory_hud(frame, spec.inventory, top_margin=int(height * 0.05))

            # 5. Draw Countdown Timer HUD (if active)
            if spec.countdown_seconds is not None:
                rem_sec = max(0.0, spec.countdown_seconds * (1.0 - p))
                draw_countdown_hud(
                    frame,
                    remaining_seconds=rem_sec,
                    total_seconds=spec.countdown_seconds,
                    center_x=int(width * 0.88),
                    center_y=int(height * 0.17),
                )

            # 6. Draw Elimination Banner or Cliffhanger CTA (inside 44%-76% safe zone)
            if spec.elimination_banner:
                draw_cliffhanger_cta(frame, spec.elimination_banner, y_pos=int(height * 0.50))
            elif spec.cta_banner:
                draw_cliffhanger_cta(frame, spec.cta_banner, y_pos=int(height * 0.68))

            writer.write(frame)

    finally:
        writer.release()

    # Re-encode to broadcast H.264 MP4
    success = reencode_broadcast_mp4(tmp_raw_mp4, output_path, fps=fps)
    if tmp_raw_mp4.exists():
        tmp_raw_mp4.unlink(missing_ok=True)
    return success


def reencode_broadcast_mp4(src_path: Path, dst_path: Path, fps: int = 30) -> bool:
    """Encodes to broadcast H.264 MP4 with BT.709 color tags."""
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
    ap = argparse.ArgumentParser(description="FrameForge Interactive Riddle & Logic HUD Engine")
    ap.add_argument("--image", "-i", type=Path, required=True, help="Base background image")
    ap.add_argument("--output", "-o", type=Path, required=True, help="Output MP4 path")
    ap.add_argument("--title", type=str, required=True, help="Riddle title")
    ap.add_argument("--duration", "-d", type=float, default=3.5, help="Clip duration in seconds")
    ap.add_argument("--countdown", type=float, default=7.0, help="Countdown timer in seconds (optional)")
    ap.add_argument("--cta", type=str, default="WHO DEDUCED IT FIRST? DROP ANSWER IN COMMENTS", help="Cliffhanger CTA text")
    ap.add_argument("--width", type=int, default=1080, help="Output width (default: 1080)")
    ap.add_argument("--height", type=int, default=1920, help="Output height (default: 1920)")

    args = ap.parse_args()

    if not args.image.exists():
        print(f"Error: Base image not found: {args.image}", file=sys.stderr)
        return 1

    img = cv2.imread(str(args.image))
    if img is None:
        print(f"Error: Failed to read image: {args.image}", file=sys.stderr)
        return 1

    # Interactive Riddle Scene Spec
    spec = RiddleSceneSpec(
        title=args.title,
        inventory=[
            InventoryItem(label="White", count=3, color=(255, 255, 255)),
            InventoryItem(label="Black", count=2, color=(40, 40, 40)),
        ],
        characters=[
            CharacterAnchor(id="3", name="Prisoner 3", x=0.22, y=0.55, badge_label="③", thought_text="?"),
            CharacterAnchor(id="2", name="Prisoner 2", x=0.50, y=0.55, badge_label="②", thought_text="?"),
            CharacterAnchor(id="1", name="Prisoner 1", x=0.78, y=0.55, badge_label="①", thought_text="!"),
        ],
        sightlines=[
            SightlineRay(from_id="3", to_id="2"),
            SightlineRay(from_id="3", to_id="1"),
            SightlineRay(from_id="2", to_id="1"),
            SightlineRay(from_id="1", to_id="2", blocked=True),
        ],
        countdown_seconds=args.countdown,
        cta_banner=args.cta,
    )

    print(f"🧩 Rendering Interactive Riddle Scene [{spec.title} | {args.duration}s @ 30fps]...")
    ok = render_riddle_scene(
        base_image=img,
        spec=spec,
        output_path=args.output,
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
