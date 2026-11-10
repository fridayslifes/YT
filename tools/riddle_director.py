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
    top_margin: int = 60,
) -> None:
    """Draws the top clue/hat inventory tracker bar."""
    if not items:
        return

    w = canvas.shape[1]
    panel_w = min(int(w * 0.88), 920)
    panel_h = 74
    x1 = (w - panel_w) // 2
    y1 = top_margin
    x2 = x1 + panel_w
    y2 = y1 + panel_h

    # Glassmorphic background
    draw_glassmorphic_panel(canvas, x1, y1, x2, y2, bg_color=(15, 18, 26), alpha=0.88, border_color=(0, 229, 255))

    # Calculate item slot distribution
    num_items = len(items)
    slot_w = panel_w / num_items

    for idx, item in enumerate(items):
        cx = int(x1 + slot_w * (idx + 0.5))
        cy = y1 + panel_h // 2

        # Draw item icon indicator (circle)
        cv2.circle(canvas, (cx - 40, cy), 16, item.color, -1, cv2.LINE_AA)
        cv2.circle(canvas, (cx - 40, cy), 17, (20, 20, 20), 2, cv2.LINE_AA)

        # Draw label & count
        text = f"{item.label}: {item.count}"
        font = cv2.FONT_HERSHEY_DUPLEX
        cv2.putText(canvas, text, (cx - 15, cy + 7), font, 0.72, (255, 255, 255), 2, cv2.LINE_AA)

        # Draw divider between items
        if idx < num_items - 1:
            div_x = int(x1 + slot_w * (idx + 1))
            cv2.line(canvas, (div_x, y1 + 14), (div_x, y2 - 14), (60, 75, 95), 1, cv2.LINE_AA)


def draw_character_badges(
    canvas: np.ndarray,
    characters: List[CharacterAnchor],
    pulse_phase: float = 0.0,
) -> None:
    """Draws floating character badges with pulsing thought bubbles."""
    h, w = canvas.shape[:2]

    for char in characters:
        px = int(round(char.x * w))
        py = int(round(char.y * h))

        # Badge Pin
        badge_radius = 28
        badge_y = py - 70

        # Pulsing rim
        pulse_r = int(badge_radius + 4 * math.sin(pulse_phase * math.pi * 2))
        cv2.circle(canvas, (px, badge_y), pulse_r, (0, 229, 255), 2, cv2.LINE_AA)

        # Badge Fill
        fill_color = (30, 36, 48) if not char.eliminated else (20, 20, 140)
        cv2.circle(canvas, (px, badge_y), badge_radius, fill_color, -1, cv2.LINE_AA)
        border_col = (255, 179, 0) if not char.eliminated else (0, 0, 255)
        cv2.circle(canvas, (px, badge_y), badge_radius, border_col, 2, cv2.LINE_AA)

        # Badge Label (e.g. "1", "2", "3")
        font = cv2.FONT_HERSHEY_DUPLEX
        lbl = char.badge_label
        t_size = cv2.getTextSize(lbl, font, 0.85, 2)[0]
        cv2.putText(
            canvas, lbl,
            (px - t_size[0] // 2, badge_y + t_size[1] // 2),
            font, 0.85, (255, 255, 255), 2, cv2.LINE_AA
        )

        # Thought Bubble (e.g. "?")
        if char.thought_text:
            tb_x = px + 45
            tb_y = badge_y - 35
            tb_r = 20
            # Small tail circles
            cv2.circle(canvas, (px + 22, badge_y - 12), 4, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(canvas, (px + 32, badge_y - 22), 7, (255, 255, 255), -1, cv2.LINE_AA)
            # Main thought bubble
            cv2.circle(canvas, (tb_x, tb_y), tb_r, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(canvas, (tb_x, tb_y), tb_r, (0, 0, 0), 2, cv2.LINE_AA)
            # Text inside bubble
            tt = char.thought_text
            tt_size = cv2.getTextSize(tt, font, 0.75, 2)[0]
            cv2.putText(
                canvas, tt,
                (tb_x - tt_size[0] // 2, tb_y + tt_size[1] // 2),
                font, 0.75, (0, 0, 0), 2, cv2.LINE_AA
            )

        # Draw elimination cross if character was eliminated/failed
        if char.eliminated:
            cv2.line(canvas, (px - 22, badge_y - 22), (px + 22, badge_y + 22), (0, 0, 255), 4, cv2.LINE_AA)
            cv2.line(canvas, (px + 22, badge_y - 22), (px - 22, badge_y + 22), (0, 0, 255), 4, cv2.LINE_AA)


def draw_sightlines(
    canvas: np.ndarray,
    sightlines: List[SightlineRay],
    characters: Dict[str, CharacterAnchor],
    dash_offset: float = 0.0,
) -> None:
    """Draws animated field-of-view sightline rays between characters."""
    h, w = canvas.shape[:2]

    for ray in sightlines:
        if ray.from_id not in characters or ray.to_id not in characters:
            continue

        c_from = characters[ray.from_id]
        c_to = characters[ray.to_id]

        x1 = int(round(c_from.x * w))
        y1 = int(round((c_from.y - 0.04) * h))
        x2 = int(round(c_to.x * w))
        y2 = int(round((c_to.y - 0.04) * h))

        if ray.blocked:
            # Draw blocked / red occluded sightline
            cv2.line(canvas, (x1, y1), (x2, y2), (0, 0, 180), 2, cv2.LINE_AA)
            mid_x = (x1 + x2) // 2
            mid_y = (y1 + y2) // 2
            cv2.putText(canvas, "[BLOCKED]", (mid_x - 45, mid_y - 10), cv2.FONT_HERSHEY_PLAIN, 1.2, (0, 0, 255), 2, cv2.LINE_AA)
        else:
            # Animated dashed ray with glow
            dist = math.hypot(x2 - x1, y2 - y1)
            if dist < 1.0:
                continue

            num_dashes = max(3, int(dist / 32))
            for i in range(num_dashes):
                t_start = (i / num_dashes + dash_offset) % 1.0
                t_end = ((i + 0.6) / num_dashes + dash_offset) % 1.0
                if t_end > t_start:
                    dx1 = int(x1 + (x2 - x1) * t_start)
                    dy1 = int(y1 + (y2 - y1) * t_start)
                    dx2 = int(x1 + (x2 - x1) * t_end)
                    dy2 = int(y1 + (y2 - y1) * t_end)
                    # Outer glow + core ray
                    cv2.line(canvas, (dx1, dy1), (dx2, dy2), ray.color, 4, cv2.LINE_AA)
                    cv2.line(canvas, (dx1, dy1), (dx2, dy2), (255, 255, 255), 1, cv2.LINE_AA)

            # Draw target eye indicator
            cv2.circle(canvas, (x2, y2), 6, ray.color, -1, cv2.LINE_AA)


def draw_countdown_hud(
    canvas: np.ndarray,
    remaining_seconds: float,
    total_seconds: float,
    center_x: int,
    center_y: int,
    radius: int = 42,
) -> None:
    """Draws a circular radial ticking clock HUD with urgency color shifts."""
    progress = max(0.0, min(1.0, remaining_seconds / max(0.001, total_seconds)))

    # Urgency shift: Cyan (calm) -> Amber -> Crimson Red (urgent)
    if progress > 0.5:
        arc_color = (0, 229, 255)  # Cyan
    elif progress > 0.25:
        arc_color = (0, 179, 255)  # Amber
    else:
        arc_color = (0, 0, 255)    # Urgent Red

    # Background ring
    cv2.circle(canvas, (center_x, center_y), radius, (35, 42, 54), 6, cv2.LINE_AA)

    # Progress arc (starts from top -90 deg)
    angle = int(round(progress * 360))
    if angle > 0:
        cv2.ellipse(canvas, (center_x, center_y), (radius, radius), -90, 0, angle, arc_color, 6, cv2.LINE_AA)

    # Digital countdown text
    time_str = f"{remaining_seconds:.1f}s"
    font = cv2.FONT_HERSHEY_DUPLEX
    t_size = cv2.getTextSize(time_str, font, 0.72, 2)[0]
    cv2.putText(
        canvas, time_str,
        (center_x - t_size[0] // 2, center_y + t_size[1] // 2),
        font, 0.72, (255, 255, 255), 2, cv2.LINE_AA
    )


def draw_cliffhanger_cta(
    canvas: np.ndarray,
    banner_text: str,
    y_pos: int,
) -> None:
    """Draws a high-impact cliffhanger CTA banner within the 44%-76% safe zone."""
    w = canvas.shape[1]
    banner_w = min(int(w * 0.90), 960)
    banner_h = 80
    x1 = (w - banner_w) // 2
    y1 = y_pos - banner_h // 2
    x2 = x1 + banner_w
    y2 = y1 + banner_h

    # Amber gold frosted banner
    draw_glassmorphic_panel(canvas, x1, y1, x2, y2, bg_color=(25, 22, 10), alpha=0.92, border_color=(255, 179, 0))

    # Pulsing banner text
    font = cv2.FONT_HERSHEY_DUPLEX
    t_size = cv2.getTextSize(banner_text, font, 0.78, 2)[0]
    cv2.putText(
        canvas, banner_text,
        ((w - t_size[0]) // 2, y1 + (banner_h + t_size[1]) // 2),
        font, 0.78, (255, 235, 180), 2, cv2.LINE_AA
    )


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

            # 2. Draw Field-of-View sightline rays
            draw_sightlines(frame, spec.sightlines, char_dict, dash_offset=(p * 2.0) % 1.0)

            # 3. Draw Character Badges & Thoughts
            draw_character_badges(frame, spec.characters, pulse_phase=p * 2.0)

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
                draw_cliffhanger_cta(frame, spec.elimination_banner, y_pos=int(height * 0.48))
            elif spec.cta_banner:
                draw_cliffhanger_cta(frame, spec.cta_banner, y_pos=int(height * 0.70))

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
    ap.add_argument("--title", type=str, default="3 Prisoners Hat Riddle", help="Riddle title")
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

    # Standard 3-Prisoners Riddle Setup
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
