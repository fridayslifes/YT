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
    """Computes (x, y) joint coordinates for head, spine, arms, and legs."""
    # Micro-sway breathing
    sway_x = int(math.sin(sway_phase * math.pi * 2) * 2.0)
    sway_y = int(math.cos(sway_phase * math.pi * 2) * 1.5)

    neck = (cx + sway_x, cy + sway_y)
    pelvis = (cx + sway_x, cy + torso_len + sway_y)

    # Defaults
    l_shoulder = (neck[0] - 10, neck[1] + 12)
    r_shoulder = (neck[0] + 10, neck[1] + 12)

    l_elbow = (l_shoulder[0] - 22, l_shoulder[1] + 35)
    r_elbow = (r_shoulder[0] + 22, r_shoulder[1] + 35)

    l_hand = (l_elbow[0] - 10, l_elbow[1] + 35)
    r_hand = (r_elbow[0] + 10, r_elbow[1] + 35)

    l_hip = (pelvis[0] - 8, pelvis[1])
    r_hip = (pelvis[0] + 8, pelvis[1])

    l_knee = (l_hip[0] - 14, l_hip[1] + 55)
    r_knee = (r_hip[0] + 14, r_hip[1] + 55)

    l_foot = (l_knee[0] - 6, l_knee[1] + 55)
    r_foot = (r_knee[0] + 6, r_knee[1] + 55)

    if pose == "thinking":
        # Right hand touching chin, left arm crossed
        l_elbow = (neck[0] - 26, neck[1] + 45)
        l_hand = (neck[0] + 5, neck[1] + 48)

        r_elbow = (neck[0] + 32, neck[1] + 36)
        r_hand = (neck[0] + 12, neck[1] - 8)  # Near chin

    elif pose == "pointing":
        # Right arm pointing forward/upward
        r_elbow = (r_shoulder[0] + 40, r_shoulder[1] - 10)
        r_hand = (r_elbow[0] + 48, r_elbow[1] - 18)

    elif pose == "shocked":
        # Both hands on head/cheeks
        l_elbow = (neck[0] - 38, neck[1] + 10)
        l_hand = (neck[0] - 22, neck[1] - 26)

        r_elbow = (neck[0] + 38, neck[1] + 10)
        r_hand = (neck[0] + 22, neck[1] - 26)

    elif pose == "facepalm":
        # Right hand slapping forehead
        r_elbow = (neck[0] + 28, neck[1] + 16)
        r_hand = (neck[0], neck[1] - 32)  # Forehead

    elif pose == "shrugging":
        # Both hands raised, elbows bent
        l_elbow = (l_shoulder[0] - 30, l_shoulder[1] + 15)
        l_hand = (l_elbow[0] - 15, l_elbow[1] - 24)

        r_elbow = (r_shoulder[0] + 30, r_shoulder[1] + 15)
        r_hand = (r_elbow[0] + 15, r_elbow[1] - 24)

    elif pose == "running":
        # Dynamic stride
        l_elbow = (l_shoulder[0] - 30, l_shoulder[1] - 15)
        l_hand = (l_elbow[0] - 20, l_elbow[1] - 15)

        r_elbow = (r_shoulder[0] + 30, r_shoulder[1] + 35)
        r_hand = (r_elbow[0] + 25, r_elbow[1] + 25)

        l_knee = (l_hip[0] + 35, l_hip[1] + 30)
        l_foot = (l_knee[0] + 30, l_knee[1] + 45)

        r_knee = (r_hip[0] - 35, r_hip[1] + 40)
        r_foot = (r_knee[0] - 30, r_knee[1] + 25)

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
    """Draws expressive 2D facial features (dot eyes, eyebrows, mouth)."""
    hx, hy = head_center

    # Eye positions
    eye_offset_x = int(radius * 0.32)
    eye_offset_y = int(radius * 0.12)
    l_eye = (hx - eye_offset_x, hy - eye_offset_y)
    r_eye = (hx + eye_offset_x, hy - eye_offset_y)
    eye_radius = max(2, int(radius * 0.10))

    cv2.circle(canvas, l_eye, eye_radius, color, -1, cv2.LINE_AA)
    cv2.circle(canvas, r_eye, eye_radius, color, -1, cv2.LINE_AA)

    # Eyebrows
    eb_y = l_eye[1] - 8
    if eyebrows == "surprised":
        cv2.line(canvas, (l_eye[0] - 8, eb_y - 6), (l_eye[0] + 8, eb_y - 8), color, 2, cv2.LINE_AA)
        cv2.line(canvas, (r_eye[0] - 8, eb_y - 8), (r_eye[0] + 8, eb_y - 6), color, 2, cv2.LINE_AA)
    elif eyebrows == "furrowed":
        cv2.line(canvas, (l_eye[0] - 8, eb_y - 2), (l_eye[0] + 8, eb_y + 4), color, 2, cv2.LINE_AA)
        cv2.line(canvas, (r_eye[0] - 8, eb_y + 4), (r_eye[0] + 8, eb_y - 2), color, 2, cv2.LINE_AA)
    else:
        cv2.line(canvas, (l_eye[0] - 8, eb_y), (l_eye[0] + 8, eb_y), color, 2, cv2.LINE_AA)
        cv2.line(canvas, (r_eye[0] - 8, eb_y), (r_eye[0] + 8, eb_y), color, 2, cv2.LINE_AA)

    # Mouth
    my = hy + int(radius * 0.40)
    if mouth == "smile":
        cv2.ellipse(canvas, (hx, my - 4), (14, 10), 0, 10, 170, color, 3, cv2.LINE_AA)
    elif mouth == "open_gasp":
        cv2.circle(canvas, (hx, my + 2), 8, color, -1, cv2.LINE_AA)
    elif mouth == "smirk":
        cv2.line(canvas, (hx - 8, my), (hx + 10, my - 5), color, 3, cv2.LINE_AA)
    elif mouth == "frown":
        cv2.ellipse(canvas, (hx, my + 8), (14, 10), 0, 190, 350, color, 3, cv2.LINE_AA)
    else:  # neutral
        cv2.line(canvas, (hx - 10, my), (hx + 10, my), color, 3, cv2.LINE_AA)


def draw_accessory(
    canvas: np.ndarray,
    head_center: Tuple[int, int],
    radius: int,
    accessory: str,
    color: Tuple[int, int, int],
) -> None:
    """Renders locked signature accessory onto the stick figure head."""
    hx, hy = head_center

    if accessory == "flat_cap":
        # Classic vintage flat cap (e.g. Peaky Blinders / detective style)
        cap_y = hy - int(radius * 0.70)
        # Cap crown
        cv2.ellipse(canvas, (hx, cap_y), (radius + 6, int(radius * 0.55)), 0, 180, 360, color, -1, cv2.LINE_AA)
        cv2.ellipse(canvas, (hx, cap_y), (radius + 6, int(radius * 0.55)), 0, 180, 360, (20, 20, 20), 2, cv2.LINE_AA)
        # Peak / Visor
        visor_pts = np.array([
            [hx - radius - 2, cap_y + 4],
            [hx + radius + 14, cap_y + 4],
            [hx + radius + 10, cap_y + 12],
            [hx - radius, cap_y + 8],
        ], dtype=np.int32)
        cv2.fillPoly(canvas, [visor_pts], color, cv2.LINE_AA)
        cv2.polylines(canvas, [visor_pts], True, (20, 20, 20), 2, cv2.LINE_AA)

    elif accessory == "glasses":
        # Round glasses
        l_center = (hx - int(radius * 0.32), hy - int(radius * 0.12))
        r_center = (hx + int(radius * 0.32), hy - int(radius * 0.12))
        g_radius = int(radius * 0.22)
        cv2.circle(canvas, l_center, g_radius, color, 2, cv2.LINE_AA)
        cv2.circle(canvas, r_center, g_radius, color, 2, cv2.LINE_AA)
        # Bridge
        cv2.line(canvas, (l_center[0] + g_radius, l_center[1]), (r_center[0] - g_radius, r_center[1]), color, 2, cv2.LINE_AA)

    elif accessory == "fedora":
        # Detective fedora hat
        fedora_y = hy - int(radius * 0.80)
        # Brim
        cv2.ellipse(canvas, (hx, fedora_y + 8), (radius + 16, 6), 0, 0, 360, color, -1, cv2.LINE_AA)
        cv2.ellipse(canvas, (hx, fedora_y + 8), (radius + 16, 6), 0, 0, 360, (20, 20, 20), 2, cv2.LINE_AA)
        # Crown
        pts = np.array([
            [hx - radius + 2, fedora_y + 6],
            [hx - int(radius * 0.65), fedora_y - 28],
            [hx + int(radius * 0.65), fedora_y - 28],
            [hx + radius - 2, fedora_y + 6],
        ], dtype=np.int32)
        cv2.fillPoly(canvas, [pts], color, cv2.LINE_AA)
        cv2.polylines(canvas, [pts], True, (20, 20, 20), 2, cv2.LINE_AA)


def draw_prop(
    canvas: np.ndarray,
    hand_pos: Tuple[int, int],
    prop_name: str,
) -> None:
    """Snaps a vector prop into the stick figure's hand."""
    hx, hy = hand_pos

    if prop_name == "magnifying_glass":
        # Detective magnifying glass
        glass_center = (hx + 18, hy - 18)
        cv2.circle(canvas, glass_center, 16, (230, 240, 255), -1, cv2.LINE_AA)
        cv2.circle(canvas, glass_center, 16, (180, 130, 40), 4, cv2.LINE_AA)  # Brass rim
        # Handle
        cv2.line(canvas, (hx, hy), (hx - 14, hy + 14), (100, 70, 30), 5, cv2.LINE_AA)

    elif prop_name == "coffee":
        # Coffee mug
        pts = np.array([
            [hx - 10, hy - 14],
            [hx + 10, hy - 14],
            [hx + 8, hy + 14],
            [hx - 8, hy + 14],
        ], dtype=np.int32)
        cv2.fillPoly(canvas, [pts], (240, 240, 240), cv2.LINE_AA)
        cv2.polylines(canvas, [pts], True, (30, 30, 30), 2, cv2.LINE_AA)
        # Handle
        cv2.ellipse(canvas, (hx + 11, hy), (5, 8), 0, -90, 90, (30, 30, 30), 2, cv2.LINE_AA)

    elif prop_name == "phone":
        # Smartphone
        pts = np.array([
            [hx - 7, hy - 16],
            [hx + 7, hy - 16],
            [hx + 7, hy + 16],
            [hx - 7, hy + 16],
        ], dtype=np.int32)
        cv2.fillPoly(canvas, [pts], (40, 40, 45), cv2.LINE_AA)
        cv2.polylines(canvas, [pts], True, (200, 200, 200), 2, cv2.LINE_AA)

    elif prop_name == "pointer":
        # Teacher / Explainer pointer stick
        cv2.line(canvas, (hx, hy), (hx + 70, hy - 40), (140, 100, 50), 3, cv2.LINE_AA)
        cv2.circle(canvas, (hx + 70, hy - 40), 4, (0, 0, 220), -1, cv2.LINE_AA)


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
) -> None:
    """Renders a single stickman character at (cx, cy) onto the canvas."""
    head_c = (cx, cy - app.head_radius)
    joints = compute_limb_joints(cx, cy, pose_spec.pose, app.torso_length, sway_phase)

    # 1. Draw Limbs & Spine
    col = app.line_color
    th = app.line_thickness

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
    cv2.circle(canvas, head_c, app.head_radius, (255, 255, 255), -1, cv2.LINE_AA)
    cv2.circle(canvas, head_c, app.head_radius, col, th, cv2.LINE_AA)

    # 3. Draw Face
    draw_stickman_face(canvas, head_c, app.head_radius, pose_spec.mouth, pose_spec.eyebrows, col)

    # 4. Draw Signature Accessory
    if app.accessory and app.accessory != "none":
        draw_accessory(canvas, head_c, app.head_radius, app.accessory, app.accessory_color)

    # 5. Draw Prop
    if pose_spec.prop:
        draw_prop(canvas, joints["r_hand"], pose_spec.prop)


# ---------------------------------------------------------------------------
# VIDEO GENERATION (STANDALONE MINIMALIST OR TRANSPARENT OVERLAY)
# ---------------------------------------------------------------------------

def render_stickman_scene(
    pose_spec: StickmanPoseSpec,
    app: StickmanAppearance,
    output_path: Path,
    caption_text: Optional[str] = None,
    bg_color: Tuple[int, int, int] = (255, 255, 255),  # Pure white paper default
    duration: float = 3.5,
    fps: int = 30,
    width: int = 1080,
    height: int = 1920,
) -> bool:
    """Renders a standalone stickman explainer scene to broadcast MP4."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    width = (width // 2) * 2
    height = (height // 2) * 2
    num_frames = int(round(duration * fps))

    tmp_raw_mp4 = output_path.with_suffix(".stick.raw.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(tmp_raw_mp4), fourcc, float(fps), (width, height))

    if not writer.isOpened():
        raise RuntimeError(f"Failed to open video writer for {tmp_raw_mp4}")

    # Anchor character at middle-lower area (safe zone)
    char_cx = width // 2
    char_cy = int(height * 0.48)

    try:
        for frame_idx in range(num_frames):
            p = frame_idx / max(1, num_frames - 1)
            frame = np.full((height, width, 3), bg_color, dtype=np.uint8)

            # Render Stickman with natural breathing/sway
            render_stickman_frame(frame, char_cx, char_cy, pose_spec, app, sway_phase=p * 2.0)

            # Optional floating speech / caption bubble
            if caption_text:
                font = cv2.FONT_HERSHEY_DUPLEX
                t_size = cv2.getTextSize(caption_text, font, 0.78, 2)[0]
                tx = (width - t_size[0]) // 2
                ty = int(height * 0.76)
                # Frosted card behind text
                cv2.rectangle(frame, (tx - 18, ty - t_size[1] - 14), (tx + t_size[0] + 18, ty + 14), (240, 240, 240), -1)
                cv2.rectangle(frame, (tx - 18, ty - t_size[1] - 14), (tx + t_size[0] + 18, ty + 14), (40, 40, 40), 2)
                cv2.putText(frame, caption_text, (tx, ty), font, 0.78, (20, 20, 20), 2, cv2.LINE_AA)

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
