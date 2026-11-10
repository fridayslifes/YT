#!/usr/bin/env python3
"""FrameForge Hybrid Canvas Compositor (tools/hybrid_engine.py).

Unifies:
  1. Archetype 1: 35mm Cinematic Photobook Background (Depth drift, warm amber/noir grade, film grain).
  2. Archetype 3: Stickman / 2D Character Plane (Procedural poses, accessories, hand props, breathing sway).
  3. Archetype 2: Interactive Riddle HUD Overlay (Clue inventory, character badges, FOV rays, countdown timer).

Produces mixed-media video essays and interactive detective shorts (Vox / Kurzgesagt / Ted-Ed style).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

TOOLS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TOOLS_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from tools.photobook_engine import (  # noqa: E402
    apply_color_grade,
    apply_optical_vignette,
    compute_camera_transform,
    generate_film_grain,
)
from tools.riddle_director import (  # noqa: E402
    CharacterAnchor,
    InventoryItem,
    RiddleSceneSpec,
    draw_character_badges,
    draw_cliffhanger_cta,
    draw_countdown_hud,
    draw_inventory_hud,
    draw_sightlines,
)
from tools.stickman_engine import (  # noqa: E402
    StickmanAppearance,
    StickmanPoseSpec,
    render_stickman_frame,
)


def render_hybrid_scene(
    bg_image: np.ndarray,
    pose_spec: StickmanPoseSpec,
    appearance: StickmanAppearance,
    riddle_spec: Optional[RiddleSceneSpec],
    output_path: Path,
    style: str = "magnates_amber",
    trajectory: str = "magnates_drift",
    duration: float = 3.5,
    fps: int = 30,
    width: int = 1080,
    height: int = 1920,
    char_pos: Tuple[float, float] = (0.50, 0.52),
) -> bool:
    """Renders a complete hybrid video scene compositing 3D photobook, stickman, and riddle HUD."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    width = (width // 2) * 2
    height = (height // 2) * 2
    num_frames = int(round(duration * fps))

    # Extended background plate to avoid edge-clip during camera drift
    bg_resized = cv2.resize(bg_image, (int(width * 1.25), int(height * 1.25)), interpolation=cv2.INTER_LANCZOS4)

    tmp_raw_mp4 = output_path.with_suffix(".hybrid.raw.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(tmp_raw_mp4), fourcc, float(fps), (width, height))

    if not writer.isOpened():
        raise RuntimeError(f"Failed to open video writer for {tmp_raw_mp4}")

    char_cx = int(round(char_pos[0] * width))
    char_cy = int(round(char_pos[1] * height))

    try:
        for frame_idx in range(num_frames):
            p = frame_idx / max(1, num_frames - 1)

            # ---------------------------------------------------------------
            # 1. LAYER 1: 35mm Background Camera Parallax Drift
            # ---------------------------------------------------------------
            pan_x, pan_y, zoom, rot = compute_camera_transform(trajectory, p, z_depth=3000.0)
            bh, bw = bg_resized.shape[:2]
            bcx, bcy = bw / 2.0, bh / 2.0
            M_bg = cv2.getRotationMatrix2D((bcx, bcy), rot, zoom)
            M_bg[0, 2] += (width / 2.0 - bcx) + pan_x
            M_bg[1, 2] += (height / 2.0 - bcy) + pan_y

            frame = cv2.warpAffine(bg_resized, M_bg, (width, height), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT)

            # Apply Cinematic Color Grade to background plate
            frame = apply_color_grade(frame, style)

            # ---------------------------------------------------------------
            # 2. LAYER 2: Character Plane with Contact Shadow
            # ---------------------------------------------------------------
            # Subtle parallax drift on character (Z-Mid ~ 1000px)
            c_pan_x, c_pan_y, c_zoom, c_rot = compute_camera_transform(trajectory, p, z_depth=1000.0)
            cur_cx = int(char_cx + c_pan_x)
            cur_cy = int(char_cy + c_pan_y)

            # Ambient contact shadow beneath feet
            shadow_y = cur_cy + appearance.torso_length + 115
            cv2.ellipse(frame, (cur_cx, shadow_y), (48, 14), 0, 0, 360, (15, 18, 22), -1, cv2.LINE_AA)

            # Render Stickman Character
            render_stickman_frame(frame, cur_cx, cur_cy, pose_spec, appearance, sway_phase=p * 2.0)

            # ---------------------------------------------------------------
            # 3. LAYER 3: Interactive Riddle HUD (if specified)
            # ---------------------------------------------------------------
            if riddle_spec:
                char_dict = {c.id: c for c in riddle_spec.characters}
                # Sightlines
                draw_sightlines(frame, riddle_spec.sightlines, char_dict, dash_offset=(p * 2.0) % 1.0)
                # Badges
                draw_character_badges(frame, riddle_spec.characters, pulse_phase=p * 2.0)
                # Top Inventory Bar
                draw_inventory_hud(frame, riddle_spec.inventory, top_margin=int(height * 0.05))
                # Countdown Ticker
                if riddle_spec.countdown_seconds is not None:
                    rem_sec = max(0.0, riddle_spec.countdown_seconds * (1.0 - p))
                    draw_countdown_hud(
                        frame,
                        remaining_seconds=rem_sec,
                        total_seconds=riddle_spec.countdown_seconds,
                        center_x=int(width * 0.88),
                        center_y=int(height * 0.17),
                    )
                # Cliffhanger CTA
                if riddle_spec.cta_banner:
                    draw_cliffhanger_cta(frame, riddle_spec.cta_banner, y_pos=int(height * 0.72))

            # ---------------------------------------------------------------
            # 4. LAYER 4: Unifying Film Chemistry (Vignette + 35mm Grain)
            # ---------------------------------------------------------------
            frame_vignette = apply_optical_vignette(frame, strength=0.35)
            grain = generate_film_grain(height, width, intensity=9.0)
            frame_final = np.clip(frame_vignette.astype(np.float32) + grain, 0, 255).astype(np.uint8)

            writer.write(frame_final)

    finally:
        writer.release()

    success = reencode_broadcast_mp4(tmp_raw_mp4, output_path, fps=fps)
    if tmp_raw_mp4.exists():
        tmp_raw_mp4.unlink(missing_ok=True)
    return success


def reencode_broadcast_mp4(src_path: Path, dst_path: Path, fps: int = 30) -> bool:
    """Encodes to broadcast H.264 MP4."""
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


def main() -> int:
    ap = argparse.ArgumentParser(description="FrameForge Hybrid Canvas Compositor")
    ap.add_argument("--bg", type=Path, required=True, help="35mm background image plate")
    ap.add_argument("--output", "-o", type=Path, required=True, help="Output MP4 path")
    ap.add_argument("--pose", type=str, default="thinking", choices=["idle", "thinking", "pointing", "shocked", "facepalm", "shrugging", "running"], help="Character pose")
    ap.add_argument("--prop", type=str, default="magnifying_glass", help="Held prop")
    ap.add_argument("--style", type=str, default="magnates_amber", help="Cinematic color grade")
    ap.add_argument("--trajectory", type=str, default="magnates_drift", help="Camera move preset")
    ap.add_argument("--riddle", action="store_true", help="Overlay interactive riddle HUD")
    ap.add_argument("--duration", "-d", type=float, default=3.5, help="Duration in seconds")
    ap.add_argument("--width", type=int, default=1080, help="Width (default: 1080)")
    ap.add_argument("--height", type=int, default=1920, help="Height (default: 1920)")

    args = ap.parse_args()

    if not args.bg.exists():
        print(f"Error: Background image not found: {args.bg}", file=sys.stderr)
        return 1

    bg_img = cv2.imread(str(args.bg))
    if bg_img is None:
        print(f"Error: Failed to read background image: {args.bg}", file=sys.stderr)
        return 1

    app = StickmanAppearance(accessory="flat_cap")
    pose = StickmanPoseSpec(pose=args.pose, mouth="neutral", prop=args.prop if args.prop != "none" else None)

    riddle_spec = None
    if args.riddle:
        riddle_spec = RiddleSceneSpec(
            title="Hybrid Riddle",
            inventory=[
                InventoryItem(label="White", count=3),
                InventoryItem(label="Black", count=2),
            ],
            characters=[
                CharacterAnchor(id="1", name="Detective", x=0.50, y=0.52, badge_label="①", thought_text="?"),
            ],
            sightlines=[],
            countdown_seconds=7.0,
            cta_banner="SOLVE THE PUZZLE IN COMMENTS",
        )

    print(f"🎨 Rendering Hybrid Canvas Scene [{args.style} | {args.pose} | {args.duration}s @ 30fps]...")
    ok = render_hybrid_scene(
        bg_image=bg_img,
        pose_spec=pose,
        appearance=app,
        riddle_spec=riddle_spec,
        output_path=args.output,
        style=args.style,
        trajectory=args.trajectory,
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
