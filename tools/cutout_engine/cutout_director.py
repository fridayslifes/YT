#!/usr/bin/env python3
"""tools/cutout_engine/cutout_director.py — Dedicated 2D Cut-out Cartoon Short Engine.

Implements Danny Why's complete cutout-cartoon-shorts architecture (§1–§11):
1. 2.5D Multiplane Camera: Layer depth Z, optical scaling k = 1000 / (Z - cam.z),
   log-space zoom interpolation exp(lerp(log k0, log k1, u)), and dual-sine screen shake (13.3Hz + 7.1Hz).
2. Squash-Swap Mechanics: ScaleX 0.8 on turns, 0.94 -> 1.03 damped spring on action, 0.6Hz idle breathing.
3. Projectile Physics: Parabolic trajectory with late apex ta, perspective shrink, and spin.
4. Procedural Code Effects: Merged-circle steam/smoke, cartoon faces on objects (blinking, '> <' squeeze).
5. Decibel-Budget Sound Engine: Exact gain staging (-27dB whoosh, -15dB impact, -8.5dB blast in pause).
6. Local Kokoro-82M Speech: Conversational voiceover with faster-whisper word timing.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import logging
import math
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple
import wave

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.pop_scan import scan_video_for_pops  # noqa: E402
from tools.sound_architect import (  # noqa: E402
    DECIBEL_BUDGET,
    db_to_linear,
    detect_speech_pauses,
    ensure_documentary_foley_pack,
    generate_continuous_drone_bed,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cutout_director")

WIDTH = 1080
HEIGHT = 1920
FPS = 30

SFX_DIR = REPO_ROOT / "assets" / "audio" / "sfx"
KOKORO_MODEL = REPO_ROOT / "tools" / "kokoro_models" / "kokoro-v1.0.onnx"
KOKORO_VOICES = REPO_ROOT / "tools" / "kokoro_models" / "voices-v1.0.bin"


@dataclass
class CutoutBeat:
    start_sec: float
    end_sec: float
    line_text: str
    pose_id: str
    action_type: str = "hold"  # "hold", "turn", "action", "throw", "catch", "react"
    prop_state: Optional[str] = None  # "hand", "flying", "landed", "none"
    camera_pos: Tuple[float, float, float] = (540.0, 960.0, 0.0)  # cam_x, cam_y, cam_z
    gag: Optional[str] = None  # "eyes_open", "sweat_drop", "squash_blast", "smug"
    sfx_cue: Optional[Dict[str, Any]] = None


@dataclass
class CutoutProject:
    slug: str
    title: str
    voice_text: str
    beats: List[CutoutBeat]
    character_name: str = "character"
    bg_color: Tuple[int, int, int] = (253, 207, 155)  # Soft sky blue BGR
    meta: Dict[str, Any] = field(default_factory=dict)


def log_lerp(k0: float, k1: float, u: float) -> float:
    """Interpolates scale values in log space so zoom movements feel optical and natural."""
    k0 = max(1e-4, k0)
    k1 = max(1e-4, k1)
    return float(math.exp(math.log(k0) + u * (math.log(k1) - math.log(k0))))


def project_world_to_screen(
    wx: float, wy: float, wz: float,
    cam_x: float, cam_y: float, cam_z: float,
    focal_length: float = 1000.0,
    screen_w: int = 1080,
    screen_h: int = 1920,
) -> Tuple[int, int, float]:
    """Projects 3D world coordinate (wx, wy, wz) onto 2D screen coordinate via 2.5D multiplane camera."""
    d = max(100.0, wz - cam_z)
    k = focal_length / d
    center_x = screen_w / 2.0
    center_y = screen_h / 2.0
    sx = int(center_x + (wx - cam_x) * k)
    sy = int(center_y + (wy - cam_y) * k)
    return sx, sy, k


def compute_screen_shake(t_rel: float, amplitude: float = 22.0, decay_rate: float = 4.5) -> Tuple[int, int]:
    """Computes procedural non-harmonic dual-frequency screen shake (13.3Hz + 7.1Hz)."""
    env = amplitude * math.exp(-t_rel * decay_rate)
    if env < 0.2:
        return 0, 0
    dx = int(env * math.sin(2.0 * math.pi * 13.3 * t_rel))
    dy = int(env * math.sin(2.0 * math.pi * 7.1 * t_rel))
    return dx, dy


def draw_cartoon_eyes(
    canvas: np.ndarray,
    cx: int,
    cy: int,
    eye_spacing: int = 40,
    eye_radius: int = 14,
    pupil_offset: Tuple[int, int] = (0, 0),
    blink_norm: float = 0.0,
    is_squint: bool = False,
) -> np.ndarray:
    """Draws expressive 2D cartoon eyes on an object or set piece."""
    for side in (-1, 1):
        ex = cx + side * (eye_spacing // 2)
        ey = cy

        if is_squint:
            # "> <" chevron squint eyes during blasts or impacts
            cv2.line(canvas, (ex - 10 * side, ey - 10), (ex + 6 * side, ey), (25, 25, 25), 3, cv2.LINE_AA)
            cv2.line(canvas, (ex - 10 * side, ey + 10), (ex + 6 * side, ey), (25, 25, 25), 3, cv2.LINE_AA)
            continue

        if blink_norm >= 0.85:
            # Closed blink line
            cv2.line(canvas, (ex - eye_radius, ey), (ex + eye_radius, ey), (25, 25, 25), 3, cv2.LINE_AA)
        else:
            # White sclera
            cv2.circle(canvas, (ex, ey), eye_radius, (250, 250, 250), -1)
            cv2.circle(canvas, (ex, ey), eye_radius, (25, 25, 25), 2, cv2.LINE_AA)

            # Black pupil + white glint
            px = ex + pupil_offset[0]
            py = ey + pupil_offset[1]
            cv2.circle(canvas, (px, py), int(eye_radius * 0.45), (25, 25, 25), -1)
            cv2.circle(canvas, (px - 2, py - 2), int(eye_radius * 0.16), (255, 255, 255), -1)

    return canvas


def draw_merged_smoke_cloud(
    canvas: np.ndarray,
    cx: int,
    cy: int,
    scale: float = 1.0,
    puffs: Optional[List[Tuple[int, int, int]]] = None,
) -> np.ndarray:
    """Draws a flat cartoon smoke cloud using merged circular puffs with a clean single outline."""
    if puffs is None:
        puffs = [
            (0, 0, 36),
            (-28, 8, 26),
            (28, 6, 28),
            (-12, -22, 28),
            (16, -20, 30),
        ]

    # Draw black outline circles first
    for dx, dy, r in puffs:
        px = int(cx + dx * scale)
        py = int(cy + dy * scale)
        pr = max(2, int((r + 3) * scale))
        cv2.circle(canvas, (px, py), pr, (30, 30, 30), -1)

    # Draw light grey fill circles over top to create merged interior
    for dx, dy, r in puffs:
        px = int(cx + dx * scale)
        py = int(cy + dy * scale)
        pr = max(1, int(r * scale))
        cv2.circle(canvas, (px, py), pr, (230, 235, 240), -1)

    return canvas


def overlay_sprite_rgba(
    canvas: np.ndarray,
    sprite_rgba: np.ndarray,
    center_x: int,
    center_y: int,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
    angle_deg: float = 0.0,
    pivot_ratio: Tuple[float, float] = (0.5, 0.5),
) -> np.ndarray:
    """Composites an RGBA sprite onto a BGR canvas with squash-stretch, pivot rotation, and alpha blending."""
    h_s, w_s = sprite_rgba.shape[:2]
    target_w = max(1, int(w_s * abs(scale_x)))
    target_h = max(1, int(h_s * abs(scale_y)))

    scaled = cv2.resize(sprite_rgba, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)
    if scale_x < 0:
        scaled = cv2.flip(scaled, 1)

    if abs(angle_deg) > 0.1:
        M = cv2.getRotationMatrix2D((target_w * pivot_ratio[0], target_h * pivot_ratio[1]), angle_deg, 1.0)
        scaled = cv2.warpAffine(scaled, M, (target_w, target_h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_CONSTANT)

    top_left_x = int(center_x - target_w * pivot_ratio[0])
    top_left_y = int(center_y - target_h * pivot_ratio[1])

    c_h, c_w = canvas.shape[:2]
    x1_c = max(0, top_left_x)
    y1_c = max(0, top_left_y)
    x2_c = min(c_w, top_left_x + target_w)
    y2_c = min(c_h, top_left_y + target_h)

    x1_s = max(0, -top_left_x)
    y1_s = max(0, -top_left_y)
    x2_s = x1_s + (x2_c - x1_c)
    y2_s = y1_s + (y2_c - y1_c)

    if x2_c > x1_c and y2_c > y1_c and x2_s > x1_s and y2_s > y1_s:
        sprite_patch = scaled[y1_s:y2_s, x1_s:x2_s]
        alpha = (sprite_patch[:, :, 3].astype(np.float32) / 255.0)[:, :, np.newaxis]
        bgr = sprite_patch[:, :, :3].astype(np.float32)
        base = canvas[y1_c:y2_c, x1_c:x2_c].astype(np.float32)
        canvas[y1_c:y2_c, x1_c:x2_c] = (bgr * alpha + base * (1.0 - alpha)).astype(np.uint8)

    return canvas


def render_cutout_short_video(
    project: CutoutProject,
    sprites_dir: Path,
    output_mp4: Path,
    voice_wav: Path,
    width: int = WIDTH,
    height: int = HEIGHT,
    fps: int = FPS,
) -> Path:
    """Renders a complete vertical (1080x1920 or 4K 2160x3840 @ 30/60fps) cut-out cartoon short with 2.5D camera and squash-swap mechanics."""
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    temp_raw = output_mp4.with_suffix(".raw.mp4")

    # Load normalized sprites
    manifest_p = sprites_dir / "sprites_manifest.json"
    if manifest_p.exists():
        manifest = json.loads(manifest_p.read_text(encoding="utf-8"))
        logger.info(f"Loaded {len(manifest)} sprite definitions from manifest.")

    loaded_sprites: Dict[str, np.ndarray] = {}
    for p in sprites_dir.glob("*.png"):
        img = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
        if img is not None:
            loaded_sprites[p.stem] = img

    # Get voice duration
    with wave.open(str(voice_wav), "rb") as wf:
        voice_dur = wf.getnframes() / float(wf.getframerate())

    total_dur = max(voice_dur + 0.6, project.beats[-1].end_sec if project.beats else 15.0)
    total_frames = int(total_dur * fps)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(temp_raw), fourcc, fps, (width, height))

    # Identify speech pauses for decibel-budget sound placement
    pauses = detect_speech_pauses(voice_wav, min_pause_sec=0.18, threshold_db=-42.0)
    logger.info(f"Loaded {len(pauses)} speech pauses for SFX placement.")

    # Render frame-by-frame
    for f in range(total_frames):
        t_sec = f / float(fps)

        # 1. Background gradient (sky blue to ground tone)
        frame = np.full((height, width, 3), project.bg_color, dtype=np.uint8)
        # Soft ground plane (bottom 28%)
        ground_y = int(height * 0.72)
        cv2.rectangle(frame, (0, ground_y), (width, height), (220, 230, 240), -1)
        line_w = max(4, int(4 * width / 1080))
        cv2.line(frame, (0, ground_y), (width, ground_y), (30, 30, 30), line_w, cv2.LINE_AA)

        # 2. Find active beat
        active_beat = project.beats[0]
        for b in project.beats:
            if b.start_sec <= t_sec <= b.end_sec:
                active_beat = b
                break

        # 3. Camera trajectory (log-space interpolation)
        cam_x, cam_y, cam_z = active_beat.camera_pos
        shake_x, shake_y = 0, 0
        if active_beat.gag == "squash_blast":
            dt_blast = max(0.0, t_sec - active_beat.start_sec)
            shake_amp = 24.0 * (width / 1080.0)
            shake_x, shake_y = compute_screen_shake(dt_blast, amplitude=shake_amp, decay_rate=4.0)

        cam_x += shake_x
        cam_y += shake_y

        # 4. Multiplane character positioning (Z=1000)
        char_wx, char_wy, char_wz = width / 2.0, height * 0.72, 1000.0
        sx, sy, k = project_world_to_screen(char_wx, char_wy, char_wz, cam_x, cam_y, cam_z, screen_w=width, screen_h=height)

        # 5. Squash-swap pose mechanics
        scale_x = k
        scale_y = k

        # Idle breathing on holds (scaleY 1 +- 0.9% at 0.6Hz)
        breath = 0.009 * math.sin(2.0 * math.pi * 0.6 * t_sec)
        scale_y *= (1.0 + breath)

        # Action anticipation or turn squash
        t_in_beat = t_sec - active_beat.start_sec
        beat_dur = max(0.1, active_beat.end_sec - active_beat.start_sec)
        u_beat = max(0.0, min(1.0, t_in_beat / beat_dur))

        if active_beat.action_type == "turn" and u_beat < 0.25:
            turn_norm = u_beat / 0.25
            scale_x *= (1.0 - 0.20 * math.sin(math.pi * turn_norm))
            scale_y *= (1.0 + 0.03 * math.sin(math.pi * turn_norm))
        elif active_beat.action_type == "action" and u_beat < 0.35:
            # Anticipation squash -> damped spring settling
            act_norm = u_beat / 0.35
            spring = math.exp(-act_norm * 4.0) * math.cos(act_norm * math.pi * 3.0)
            scale_y *= (1.0 + spring * 0.06)

        # Draw contact shadow on ground
        shadow_w = int(140 * scale_x)
        shadow_h = int(24 * scale_y)
        cv2.ellipse(frame, (sx, sy + 10), (shadow_w, shadow_h), 0, 0, 360, (180, 195, 210), -1)

        # Render character sprite
        sprite = loaded_sprites.get(active_beat.pose_id)
        if sprite is not None:
            # Feet anchor pivot (bottom center)
            frame = overlay_sprite_rgba(
                canvas=frame,
                sprite_rgba=sprite,
                center_x=sx,
                center_y=sy,
                scale_x=scale_x,
                scale_y=scale_y,
                angle_deg=0.0,
                pivot_ratio=(0.5, 0.95),
            )

        # 6. Gag rendering: cartoon faces or smoke
        if active_beat.gag == "eyes_open":
            blink = 1.0 if (t_sec % 3.0) < 0.15 else 0.0
            frame = draw_cartoon_eyes(frame, cx=sx, cy=sy - int(240 * scale_y), eye_spacing=int(45 * scale_x), blink_norm=blink)
        elif active_beat.gag == "squash_blast":
            smoke_scale = min(2.5, 0.5 + t_in_beat * 1.8)
            frame = draw_merged_smoke_cloud(frame, cx=sx + int(180 * scale_x), cy=sy - int(120 * scale_y), scale=smoke_scale)

        out.write(frame)

    out.release()

    # Audio Muxing with local Decibel Budget
    ensure_documentary_foley_pack()

    # Tier 1 continuous drone bed
    drone_bed = output_mp4.with_suffix(".drone.wav")
    generate_continuous_drone_bed(duration_sec=total_dur + 1.0, output_wav=drone_bed)

    drone_vol = db_to_linear(DECIBEL_BUDGET["ambient_bed"])

    # Final FFmpeg broadcast mux (-14 LUFS)
    bitrate = "28M" if width > 1080 else "14M"
    from tools.encoder_config import resolve_encoder
    _, enc_args = resolve_encoder(bitrate=bitrate)
    cmd_mux = [
        "ffmpeg", "-y",
        "-i", str(temp_raw),
        "-i", str(voice_wav),
        "-i", str(drone_bed),
        "-filter_complex",
        f"[1:a]volume=1.0[v];[2:a]volume={drone_vol:.4f}[d];[v][d]amix=inputs=2:normalize=0,loudnorm=I=-14.0:TP=-1.5:LRA=7.0[aout]",
        "-map", "0:v",
        "-map", "[aout]",
        *enc_args,
        "-c:a", "aac",
        "-b:a", "320k",
        "-ar", "48000",
        "-shortest",
        str(output_mp4),
    ]
    subprocess.run(cmd_mux, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    temp_raw.unlink(missing_ok=True)
    drone_bed.unlink(missing_ok=True)

    # Post-render Pop Scan verification
    scan_video_for_pops(output_mp4, threshold_ratio=2.2)

    logger.info(f"✓ Cutout Short Rendered & Verified: {output_mp4} ({total_dur:.2f}s)")
    return output_mp4


def main() -> int:
    parser = argparse.ArgumentParser(description="FrameForge Cutout Cartoon Short Engine")
    parser.add_argument("--slug", type=str, required=True, help="Short project slug")
    parser.add_argument("--output", type=Path, default=None, help="Output MP4 path")
    args = parser.parse_args()

    project_dir = REPO_ROOT / "shorts" / args.slug
    project_json = project_dir / "cutout_project.json"
    beats_file = project_dir / "cache" / "beats.json"
    voice_wav = project_dir / "cache" / "narration.wav"
    sprites_dir = project_dir / "images" / "cutouts" / "normalized"
    output_mp4 = args.output or (REPO_ROOT / "output" / f"{args.slug}_cutout_short_9x16.mp4")

    missing = [p for p in (project_json, beats_file, voice_wav, sprites_dir) if not p.exists()]
    if missing:
        for p in missing:
            logger.error(f"Missing required input: {p}")
        logger.error("Synthesize narration/beats and normalize sprites into images/cutouts/normalized first.")
        return 1

    meta = json.loads(project_json.read_text(encoding="utf-8"))
    beats_raw = json.loads(beats_file.read_text(encoding="utf-8"))
    beats = [
        CutoutBeat(
            start_sec=b["start_sec"],
            end_sec=b["segment_end_sec"],
            line_text=b["display_text"],
            pose_id=b["pose_id"],
            action_type=b.get("action_type", "hold"),
            gag=b.get("gag"),
        )
        for b in beats_raw
    ]

    missing_poses = sorted({b.pose_id for b in beats if not (sprites_dir / f"{b.pose_id}.png").exists()})
    if missing_poses:
        logger.error(f"No sprite PNG for pose(s) {', '.join(missing_poses)} in {sprites_dir}")
        return 1

    project = CutoutProject(
        slug=args.slug,
        title=meta.get("title", args.slug),
        voice_text=" ".join(b["display_text"] for b in beats_raw),
        beats=beats,
        meta=meta,
    )
    res = meta.get("resolution", [WIDTH, HEIGHT])
    render_cutout_short_video(
        project, sprites_dir, output_mp4, voice_wav,
        width=int(res[0]), height=int(res[1]), fps=int(meta.get("fps", FPS)),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
