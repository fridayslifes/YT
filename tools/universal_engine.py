#!/usr/bin/env python3
"""FrameForge Universal Multi-Variant Engine & 7-Style Registry (tools/universal_engine.py).

Dispatches data-driven project builds across all 7 canonical production variants:
  1. `cinematic_35mm`: Portra 400 / 35mm documentary plate motion + depth parallax + grain/vignette
  2. `photobook`: Tactile archival plate drift + vintage color grading + optical vignette
  3. `storybook_picturebook`: Physical leather book spread + drop-cap text + memo card + living motion plates
  4. `stickman_skeleton`: Expressive 2D vector stickman rig + grounded drafting scene plane
  5. `riddle`: Interactive logic puzzle HUD + sightlines + character badges + countdown + safe-zone CTA
  6. `hybrid_mixed_media`: 35mm atmospheric background plate + 2D stickman plane + interactive riddle HUD
  7. `cutout_cartoon`: 2.5D multiplane camera + squash-swap pose sprites + cartoon gags

Every variant engine implements:
  - `validate(project) -> List[str]`
  - `build(project, out_dir=None, *, preview=False) -> Path`
  - `preview(project, out_dir=None) -> Path`

All narration is synthesized exclusively through local Kokoro-82M ONNX (`tools.build_video.tts_cached`),
and every rendered scene clip is fingerprinted in `cache/render_manifest.json` across `variant`, `text`,
`prompt`, `audio_sha256`, `timings`, and `overlay_parameters`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import wave

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools import build_video  # noqa: E402
from tools.audio_bank import SFX_DIR, ensure_studio_sfx_pack  # noqa: E402
from tools.build_video import _synthesize_kokoro, _validate_kokoro_voice  # noqa: E402
from tools.render_manifest import RenderManifest, scene_fingerprint  # noqa: E402
from tools.schemas import (  # noqa: E402
    PROJECT_SCHEMA_VERSION,
    SUPPORTED_VARIANTS,
    validate_project,
)
from tools.visual_engine import remotion_spring, verify_encoded_output  # noqa: E402

FONT_DIR = PROJECT_ROOT / "tools" / "fonts"
BE_VIETNAM_BOLD = FONT_DIR / "BeVietnamPro-Bold.ttf"
BE_VIETNAM_MED = FONT_DIR / "BeVietnamPro-Medium.ttf"
BEBAS_NEUE = FONT_DIR / "BebasNeue-Regular.ttf"
ANTON = FONT_DIR / "Anton-Regular.ttf"


def get_font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    """Safely loads FreeType font with fallback to default PIL font."""
    if path.exists():
        try:
            return ImageFont.truetype(str(path), size)
        except Exception:
            pass
    return ImageFont.load_default()


def reencode_broadcast_mp4(src_path: Path, dst_path: Path, fps: int = 30, bitrate: str = "8M") -> bool:
    """Encodes raw video to crisp, web-optimized broadcast H.264 MP4."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        shutil.move(str(src_path), str(dst_path))
        return True

    for enc in ("h264_videotoolbox", "libx264"):
        cmd = [ffmpeg_bin, "-y", "-i", str(src_path), "-c:v", enc]
        if enc == "h264_videotoolbox":
            cmd.extend(["-b:v", bitrate, "-profile:v", "high", "-pix_fmt", "yuv420p"])
        else:
            cmd.extend(["-crf", "20", "-preset", "fast", "-pix_fmt", "yuv420p"])

        cmd.extend([
            "-colorspace", "bt709",
            "-color_primaries", "bt709",
            "-color_trc", "bt709",
            "-movflags", "+faststart",
            str(dst_path),
        ])
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0 and dst_path.exists() and dst_path.stat().st_size > 1000:
            return True

    shutil.move(str(src_path), str(dst_path))
    return dst_path.exists()


def reencode_broadcast_mp4_with_audio(
    video_path: Path,
    audio_path: Path,
    dst_path: Path,
    fps: int = 30,
    bitrate: str = "12M",
) -> bool:
    """Multiplexes raw video and master audio into pristine broadcast Full HD H.264 MP4."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        return False

    for enc in ("h264_videotoolbox", "libx264"):
        cmd = [
            ffmpeg_bin, "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-c:v", enc,
        ]
        if enc == "h264_videotoolbox":
            cmd.extend(["-b:v", bitrate, "-profile:v", "high", "-pix_fmt", "yuv420p"])
        else:
            cmd.extend(["-crf", "17", "-preset", "fast", "-pix_fmt", "yuv420p"])

        cmd.extend([
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "48000",
            "-ac", "2",
            "-colorspace", "bt709",
            "-color_primaries", "bt709",
            "-color_trc", "bt709",
            "-movflags", "+faststart",
            "-shortest",
            str(dst_path),
        ])
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0 and dst_path.exists() and dst_path.stat().st_size > 1000:
            return True

    return False


def synthesize_studio_speech(
    text: str,
    output_wav: Path,
    voice: str = "kokoro",
    rate: str = "+7%",
    pitch: str = "-1Hz",
) -> Tuple[Path, List[dict]]:
    """Synthesizes human neural speech strictly via local Kokoro-82M ONNX and masters it through Shure SM7B EQ chain."""
    kokoro_spec = _validate_kokoro_voice(voice)
    output_wav = Path(output_wav)
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    raw_mp3 = output_wav.with_suffix(".raw.mp3")

    words = _synthesize_kokoro(text, raw_mp3, voice_spec=kokoro_spec)

    voice_af = (
        "highpass=f=65,"
        "equalizer=f=135:t=q:w=1.1:g=+2.4,"
        "equalizer=f=2400:t=q:w=1.4:g=+0.8,"
        "equalizer=f=3400:t=q:w=1.6:g=-1.6,"
        "lowpass=f=13500,"
        "deesser=i=0.6:m=0.4:f=0.5:s=o,"
        "acompressor=threshold=-16dB:ratio=2.0:attack=15:release=160,"
        "alimiter=limit=-1.2dB"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(raw_mp3), "-af", voice_af, "-ar", "44100", "-ac", "2", str(output_wav)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
    )
    raw_mp3.unlink(missing_ok=True)
    return output_wav, words


def render_caption_pill(
    draw: ImageDraw.ImageDraw,
    words: List[dict],
    t: float,
    w_canvas: int,
    h_canvas: int,
    font: ImageFont.FreeTypeFont,
    lead_in: float = 0.8,
) -> None:
    """Renders Remotion spring-animated word-by-word highlighted subtitle pills in the safe band."""
    active_word = ""
    active_start = 0.0
    for w in words:
        s = float(w.get("start", 0.0)) + lead_in
        e = float(w.get("end", 0.0)) + lead_in
        if s <= t <= e + 0.16:
            active_word = w.get("text") or w.get("word", "")
            active_start = s
            break
        elif t < s:
            break

    if active_word:
        w_pop = remotion_spring(min(0.3, max(0.0, t - active_start)), damping=14.0, stiffness=220.0)
        clean_w = active_word.strip("\"'()").upper()
        scale = h_canvas / 3840.0
        char_w = max(18, int(62 * scale))
        pad = max(40, int(140 * scale))
        cap_box_w = min(int(w_canvas * 0.88), max(int(360 * scale), int((len(clean_w) * char_w + pad) * min(1.08, w_pop))))
        cap_x0 = (w_canvas - cap_box_w) // 2
        cap_y0 = int(h_canvas * 0.58)
        cap_box_h = int(140 * scale * min(1.05, w_pop))
        r_rad = max(16, int(32 * scale))
        border_w = max(3, int(6 * scale))
        draw.rounded_rectangle(
            [cap_x0, cap_y0, cap_x0 + cap_box_w, cap_y0 + cap_box_h],
            radius=r_rad,
            fill=(14, 18, 28, 235),
            outline=(255, 215, 65, 255),
            width=border_w,
        )
        draw.text(
            (w_canvas // 2, cap_y0 + cap_box_h // 2),
            clean_w,
            fill=(255, 255, 255, 255),
            font=font,
            anchor="mm",
        )


def build_master_audio_track(
    voice_wav: Path,
    output_wav: Path,
    total_duration: float = 30.0,
    lead_in: float = 0.8,
    sfx_events: Optional[List[Tuple[str, float, float]]] = None,
    drone_freqs: Tuple[float, float] = (50.0, 75.0),
    drone_vol: float = 0.10,
) -> Path:
    """Mixes mastered voiceover, ambient drone pad, and synchronized Foley SFX."""
    ensure_studio_sfx_pack()
    sr = 44100
    total_samples = int(total_duration * sr)
    master = np.zeros((total_samples, 2), dtype=np.float32)

    with wave.open(str(voice_wav), "rb") as wf:
        v_bytes = wf.readframes(wf.getnframes())
    v_arr = np.frombuffer(v_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    v_samples = v_arr.reshape(-1, 2)

    s_idx = int(lead_in * sr)
    copy_len = min(len(v_samples), total_samples - s_idx)
    master[s_idx:s_idx + copy_len] += v_samples[:copy_len] * 0.95

    t_axis = np.arange(total_samples) / sr
    lfo = 0.5 + 0.5 * np.sin(2 * np.pi * 0.12 * t_axis)
    f1, f2 = drone_freqs
    pad_l = (0.65 * np.sin(2 * np.pi * f1 * t_axis) + 0.35 * np.sin(2 * np.pi * f2 * t_axis)) * lfo
    pad_r = (0.65 * np.sin(2 * np.pi * (f1 * 1.005) * t_axis) + 0.35 * np.sin(2 * np.pi * (f2 * 0.995) * t_axis)) * lfo
    master[:, 0] += pad_l * drone_vol
    master[:, 1] += pad_r * drone_vol

    for sfx_name, at_sec, vol in (sfx_events or []):
        sfx_path = SFX_DIR / sfx_name
        if not sfx_path.exists():
            continue
        try:
            with wave.open(str(sfx_path), "rb") as wf:
                raw = wf.readframes(wf.getnframes())
            channels = wf.getnchannels()
            arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            if channels == 1:
                arr = np.column_stack([arr, arr])
            else:
                arr = arr.reshape(-1, 2)
            i0 = int(at_sec * sr)
            i1 = min(total_samples, i0 + len(arr))
            master[i0:i1] += arr[:i1 - i0] * vol
        except Exception:
            pass

    peak = np.max(np.abs(master))
    if peak > 0.95:
        master = master / peak * 0.95

    int_pcm = (master * 32767.0).astype(np.int16)
    with wave.open(str(output_wav), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(int_pcm.tobytes())

    return output_wav


# ===========================================================================
# LEGACY 3.5-SECOND QUICK PROBES & EXTRACTED DEMO RE-EXPORTS
# ===========================================================================

def render_photobook_from_scratch(output_path: Path, duration: float = 3.5, fps: int = 30, width: int = 1080, height: int = 1920) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total_frames = int(duration * fps)
    base_bg = Image.new("RGBA", (width, height), (18, 16, 14, 255))
    tmp_raw = output_path.with_suffix(".raw.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(tmp_raw), fourcc, float(fps), (width, height))
    try:
        for _ in range(total_frames):
            arr = cv2.cvtColor(np.array(base_bg), cv2.COLOR_RGBA2BGR)
            writer.write(arr)
    finally:
        writer.release()
    reencode_broadcast_mp4(tmp_raw, output_path, fps=fps)
    tmp_raw.unlink(missing_ok=True)
    return output_path


def render_riddle_from_scratch(output_path: Path, duration: float = 3.5, fps: int = 30, width: int = 1080, height: int = 1920) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total_frames = int(duration * fps)
    base_bg = Image.new("RGBA", (width, height), (32, 18, 54, 255))
    tmp_raw = output_path.with_suffix(".raw.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(tmp_raw), fourcc, float(fps), (width, height))
    try:
        for _ in range(total_frames):
            arr = cv2.cvtColor(np.array(base_bg), cv2.COLOR_RGBA2BGR)
            writer.write(arr)
    finally:
        writer.release()
    reencode_broadcast_mp4(tmp_raw, output_path, fps=fps)
    tmp_raw.unlink(missing_ok=True)
    return output_path


def render_stickman_from_scratch(output_path: Path, duration: float = 3.5, fps: int = 30, width: int = 1080, height: int = 1920) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total_frames = int(duration * fps)
    base_bg = Image.new("RGBA", (width, height), (250, 247, 238, 255))
    tmp_raw = output_path.with_suffix(".raw.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(tmp_raw), fourcc, float(fps), (width, height))
    try:
        for _ in range(total_frames):
            arr = cv2.cvtColor(np.array(base_bg), cv2.COLOR_RGBA2BGR)
            writer.write(arr)
    finally:
        writer.release()
    reencode_broadcast_mp4(tmp_raw, output_path, fps=fps)
    tmp_raw.unlink(missing_ok=True)
    return output_path


def render_hybrid_from_scratch(output_path: Path, duration: float = 3.5, fps: int = 30, width: int = 1080, height: int = 1920) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total_frames = int(duration * fps)
    base_bg = Image.new("RGBA", (width, height), (10, 14, 22, 255))
    tmp_raw = output_path.with_suffix(".raw.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(tmp_raw), fourcc, float(fps), (width, height))
    try:
        for _ in range(total_frames):
            arr = cv2.cvtColor(np.array(base_bg), cv2.COLOR_RGBA2BGR)
            writer.write(arr)
    finally:
        writer.release()
    reencode_broadcast_mp4(tmp_raw, output_path, fps=fps)
    tmp_raw.unlink(missing_ok=True)
    return output_path


def render_30s_photobook_hd_with_audio(output_path: Path, fps: int = 30) -> Path:
    from demos.archetype_demos import render_30s_photobook_hd_with_audio as _demo
    return _demo(output_path, fps=fps)


def render_30s_riddle_hd_with_audio(output_path: Path, fps: int = 30) -> Path:
    from demos.archetype_demos import render_30s_riddle_hd_with_audio as _demo
    return _demo(output_path, fps=fps)


def render_30s_stickman_hd_with_audio(output_path: Path, fps: int = 30) -> Path:
    from demos.archetype_demos import render_30s_stickman_hd_with_audio as _demo
    return _demo(output_path, fps=fps)


def render_30s_hybrid_hd_with_audio(output_path: Path, fps: int = 30) -> Path:
    from demos.archetype_demos import render_30s_hybrid_hd_with_audio as _demo
    return _demo(output_path, fps=fps)


def generate_all_4_archetype_demos(demo_dir: Path) -> Dict[str, Path]:
    from demos.archetype_demos import generate_all_4_archetype_demos as _demos
    return _demos(demo_dir)


# ===========================================================================
# CANONICAL 7-VARIANT PRODUCTION ARCHITECTURE & ENGINE REGISTRY
# ===========================================================================

UNIVERSAL_VARIANTS: Dict[str, Dict[str, str]] = {
    "cinematic_35mm": {
        "name": "Cinematic 35mm Documentary",
        "description": "Portra 400 photorealism, Leica Summilux depth of field, 35mm film grain, and dynamic camera drift.",
        "target_format": "Both (Short & Long)",
        "pacing": "2.5s–3.8s visual cut cycle",
        "audio": "Kokoro Shure SM7B voiceover + Mid/Side vocal pocket ducking + cinema sub-bass",
    },
    "photobook": {
        "name": "Archival Photobook & Visual Essay",
        "description": "Mounted archival plates, warm amber/sepia documentary color grading, optical vignette, and S-curve camera drift.",
        "target_format": "Both (Short & Long)",
        "pacing": "3.0s–4.5s tactile plate glide",
        "audio": "Kokoro Shure SM7B voiceover + archival foley + ambient drone",
    },
    "storybook_picturebook": {
        "name": "Tactile Physical Picture-Book",
        "description": "Full-bleed physical open book on mahogany desk with page flips, multi-image collage, memo cards, and word-locked highlighter sweeps.",
        "target_format": "Both (Short & Long)",
        "pacing": "Spread navigation with dynamic evidence card drops and stamps",
        "audio": "Narrative Foley timed to spoken words + tactile page-turn transients",
    },
    "stickman_skeleton": {
        "name": "Expressive 2D Vector Stickman / Skeleton",
        "description": "Minimalist high-contrast vector characters with procedural joint animation, grounded drafting scene plane, and signature accessories.",
        "target_format": "Both (Short & Long)",
        "pacing": "Fast snappy dialogue-driven gestures and vector cuts",
        "audio": "High-energy comedic foley + vocal pops + Kokoro local narration",
    },
    "riddle": {
        "name": "Interactive 2D Logic Riddle & HUD",
        "description": "Interactive clue inventory bar, character badges, animated FOV sightline rays, radial countdown timer, and safe-zone CTA.",
        "target_format": "Both (Short & Long)",
        "pacing": "Suspenseful deduction pacing with visual clue reveals",
        "audio": "Ticking countdown transients + Kokoro local narration + mystery drone",
    },
    "hybrid_mixed_media": {
        "name": "Hybrid Mixed-Media & Clue HUD",
        "description": "Photorealistic 35mm atmospheric plate + 2D expressive stickman plane + interactive clue inventory HUD.",
        "target_format": "Both (Short & Long)",
        "pacing": "Investigative pacing with interactive evidence collection",
        "audio": "Atmospheric Foley + UI tick transients + mystery synth pad",
    },
    "cutout_cartoon": {
        "name": "2D Cut-Out Cartoon Short Engine",
        "description": "2.5D multiplane camera, squash-swap character pose mechanics, procedural cartoon smoke/eye gags, and decibel-budget foley.",
        "target_format": "Both (Short & Long)",
        "pacing": "Snappy beat-synced pose swaps and log-space camera zooms",
        "audio": "Kokoro local narration + decibel-budget foley in speech pauses",
    },
}

assert frozenset(UNIVERSAL_VARIANTS.keys()) == SUPPORTED_VARIANTS, (
    f"UNIVERSAL_VARIANTS keys {tuple(UNIVERSAL_VARIANTS.keys())} must match schemas.SUPPORTED_VARIANTS {SUPPORTED_VARIANTS}"
)


def _load_project_input(project: Union[Dict[str, Any], Path, str]) -> Tuple[Dict[str, Any], Optional[Path], Path]:
    """Resolves a project dict, project.json Path, directory Path, or slug into (data, json_path, project_dir)."""
    if isinstance(project, dict):
        slug = str(project.get("slug") or project.get("id") or "inline_project").lower().replace(" ", "_")
        fmt = str(project.get("format") or "short").lower()
        base = PROJECT_ROOT / ("shorts" if fmt == "short" else "projects") / slug
        return dict(project), None, base

    if isinstance(project, str) and not Path(project).exists():
        found = find_project_dir(project)
        if not found:
            raise FileNotFoundError(f"Project directory not found for slug '{project}'")
        project = found

    p = Path(project)
    if p.is_dir():
        proj_json = p / "project.json"
        if not proj_json.exists():
            raise FileNotFoundError(f"Missing project.json in {p}")
        data = json.loads(proj_json.read_text(encoding="utf-8"))
        return data, proj_json, p

    if not p.exists():
        raise FileNotFoundError(f"Project file not found: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    return data, p, p.parent


def _ensure_scene_plate(
    project_dir: Path,
    proj_data: Dict[str, Any],
    scene: Dict[str, Any],
    scene_idx: int,
    width: int,
    height: int,
) -> Path:
    """Ensures a topic- and scene-specific visual plate exists on disk for the scene."""
    img_rel = str(scene.get("image") or f"images/s{scene_idx + 1:02d}.jpg")
    if Path(img_rel).suffix.lower() not in {".jpg", ".jpeg", ".png"}:
        img_rel = f"images/s{scene_idx + 1:02d}.jpg"
        scene["image"] = img_rel

    img_path = project_dir / img_rel
    if img_path.exists() and img_path.stat().st_size > 256:
        return img_path

    img_path.parent.mkdir(parents=True, exist_ok=True)
    seed_str = "|".join([
        str(proj_data.get("id", "")),
        str(proj_data.get("title", "")),
        str(proj_data.get("topic", "")),
        str(proj_data.get("variant", "")),
        str(scene.get("id", f"s{scene_idx + 1:02d}")),
        str(scene.get("text", "")),
        str(scene.get("prompt", "")),
    ])
    digest = hashlib.sha256(seed_str.encode("utf-8")).digest()

    r0, g0, b0 = 24 + (digest[0] % 70), 28 + (digest[1] % 70), 36 + (digest[2] % 80)
    r1, g1, b1 = 60 + (digest[3] % 110), 55 + (digest[4] % 110), 70 + (digest[5] % 110)
    accent = (80 + (digest[6] % 160), 110 + (digest[7] % 130), 140 + (digest[8] % 110))

    y_lin = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    x_lin = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
    bg_b = (b0 * (1.0 - y_lin) + b1 * y_lin + 18.0 * np.sin(x_lin * math.pi * (2 + (digest[9] % 3)))).clip(0, 255)
    bg_g = (g0 * (1.0 - y_lin) + g1 * y_lin + 18.0 * np.cos(y_lin * math.pi * (2 + (digest[10] % 3))) + 0.0 * x_lin).clip(0, 255)
    bg_r = (r0 * (1.0 - y_lin) + r1 * y_lin + 18.0 * np.sin((x_lin + y_lin) * math.pi * 2.0)).clip(0, 255)
    canvas = np.stack([bg_b, bg_g, bg_r], axis=-1).astype(np.uint8)

    pil_img = Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)
    scale = min(width, height) / 1080.0

    for k in range(5):
        off = k * 3
        cx = int((0.18 + (digest[(11 + off) % 32] / 255.0) * 0.64) * width)
        cy = int((0.18 + (digest[(12 + off) % 32] / 255.0) * 0.54) * height)
        rad = int((45 + (digest[(13 + off) % 32] % 130)) * scale)
        col = (
            (accent[0] + k * 23) % 255,
            (accent[1] + k * 37) % 255,
            (accent[2] + k * 51) % 255,
        )
        draw.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=col, width=max(2, int(4 * scale)))

    font_title = get_font(BE_VIETNAM_BOLD, max(16, int(34 * scale)))
    font_sub = get_font(BE_VIETNAM_MED, max(12, int(22 * scale)))

    title_str = str(proj_data.get("title") or proj_data.get("topic") or "FrameForge").upper()[:42]
    prompt_str = str(scene.get("prompt") or scene.get("text") or f"Scene {scene_idx + 1}")[:90]
    card_x0, card_y0 = int(width * 0.08), int(height * 0.14)
    card_x1, card_y1 = int(width * 0.92), int(height * 0.36)
    draw.rounded_rectangle([card_x0, card_y0, card_x1, card_y1], radius=max(8, int(20 * scale)), fill=(16, 20, 28), outline=accent, width=max(2, int(3 * scale)))
    draw.text((width // 2, card_y0 + int(38 * scale)), f"{title_str} • S{scene_idx + 1:02d}", fill=accent, font=font_title, anchor="mm")

    wrapped = textwrap.wrap(prompt_str, width=36)[:2]
    for l_idx, line in enumerate(wrapped):
        draw.text((width // 2, card_y0 + int((88 + l_idx * 32) * scale)), line, fill=(235, 240, 248), font=font_sub, anchor="mm")

    out_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    cv2.imwrite(str(img_path), out_bgr)
    return img_path


def _ensure_cutout_sprites(sprites_dir: Path, proj_data: Dict[str, Any]) -> Path:
    """Ensures normalized RGBA cutout character pose sprites exist for cutout_cartoon builds."""
    sprites_dir.mkdir(parents=True, exist_ok=True)
    poses = ("idle", "pointing", "thinking", "shocked", "facepalm", "shrugging", "running")
    from tools import stickman_engine

    seed_bytes = hashlib.sha256(str(proj_data.get("id") or proj_data.get("title") or "cutout").encode("utf-8")).digest()
    acc_choices = ("flat_cap", "glasses", "fedora")
    acc = acc_choices[seed_bytes[0] % len(acc_choices)]
    acc_col = (int(40 + seed_bytes[1] % 180), int(50 + seed_bytes[2] % 160), int(60 + seed_bytes[3] % 160))

    manifest = {}
    for idx, pose_name in enumerate(poses):
        sp_path = sprites_dir / f"{pose_name}.png"
        if not sp_path.exists():
            canvas_bgr = np.full((420, 320, 3), (255, 0, 255), dtype=np.uint8)
            app = stickman_engine.StickmanAppearance(accessory=acc, accessory_color=acc_col)
            mouth = ("neutral", "smile", "open_gasp", "smirk")[idx % 4]
            prop = "magnifying_glass" if pose_name == "pointing" else ("coffee" if pose_name == "thinking" else None)
            spec = stickman_engine.StickmanPoseSpec(pose=pose_name, mouth=mouth, prop=prop)
            stickman_engine.render_stickman_frame(canvas_bgr, 160, 175, spec, app, sway_phase=0.1 * idx, scale=1.0)
            is_bg = (
                (canvas_bgr[:, :, 0] > 240)
                & (canvas_bgr[:, :, 1] < 20)
                & (canvas_bgr[:, :, 2] > 240)
            )
            rgba = np.zeros((420, 320, 4), dtype=np.uint8)
            rgba[:, :, :3] = canvas_bgr
            rgba[:, :, 3] = np.where(is_bg, 0, 255).astype(np.uint8)
            cv2.imwrite(str(sp_path), rgba)
        manifest[pose_name] = {"file": f"{pose_name}.png", "pivot": [0.5, 0.95]}

    manifest_path = sprites_dir / "sprites_manifest.json"
    if not manifest_path.exists():
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return sprites_dir


def _build_riddle_spec_for_scene(proj_data: Dict[str, Any], sc: Dict[str, Any], idx: int):
    """Builds a RiddleSceneSpec from scene metadata or deterministic scene attributes."""
    from tools import riddle_director

    raw_riddle = sc.get("riddle") if isinstance(sc.get("riddle"), dict) else sc
    title = str(raw_riddle.get("title") or proj_data.get("title") or f"Riddle Scene {idx + 1}")

    inv_raw = raw_riddle.get("inventory")
    if isinstance(inv_raw, list) and inv_raw:
        inventory = [
            riddle_director.InventoryItem(
                label=str(it.get("label", f"Clue {i + 1}")),
                count=int(it.get("count", 1)),
                color=tuple(it.get("color", (255, 255, 255))),
            )
            for i, it in enumerate(inv_raw)
            if isinstance(it, dict)
        ]
    else:
        words = [w.strip(".,!?\"'():;") for w in str(sc.get("text", "")).split() if len(w.strip(".,!?\"'():;")) >= 4]
        lbl_a = (words[0].title()[:10] if words else "Clues")
        lbl_b = (words[-1].title()[:10] if len(words) > 1 else "Suspects")
        inventory = [
            riddle_director.InventoryItem(label=lbl_a, count=idx + 1, color=(255, 255, 255)),
            riddle_director.InventoryItem(label=lbl_b, count=max(1, 3 - (idx % 3)), color=(40, 180, 255)),
        ]

    chars_raw = raw_riddle.get("characters")
    if isinstance(chars_raw, list) and chars_raw:
        characters = [
            riddle_director.CharacterAnchor(
                id=str(c.get("id", str(i + 1))),
                name=str(c.get("name", f"P{i + 1}")),
                x=float(c.get("x", 0.25 + 0.25 * i)),
                y=float(c.get("y", 0.56)),
                badge_label=str(c.get("badge_label", str(i + 1))),
                eliminated=bool(c.get("eliminated", False)),
                thought_text=c.get("thought_text"),
            )
            for i, c in enumerate(chars_raw)
            if isinstance(c, dict)
        ]
    else:
        characters = [
            riddle_director.CharacterAnchor(id="1", name="Suspect 1", x=0.26, y=0.56, badge_label="1", thought_text="?" if idx % 2 == 0 else None),
            riddle_director.CharacterAnchor(id="2", name="Suspect 2", x=0.52, y=0.56, badge_label="2", eliminated=(idx > 4), thought_text="!" if idx % 2 == 1 else None),
            riddle_director.CharacterAnchor(id="3", name="Suspect 3", x=0.76, y=0.56, badge_label="3", thought_text="?"),
        ]

    rays_raw = raw_riddle.get("sightlines")
    if isinstance(rays_raw, list) and rays_raw:
        sightlines = [
            riddle_director.SightlineRay(
                from_id=str(r.get("from_id", "1")),
                to_id=str(r.get("to_id", "2")),
                blocked=bool(r.get("blocked", False)),
            )
            for r in rays_raw
            if isinstance(r, dict)
        ]
    else:
        sightlines = [
            riddle_director.SightlineRay(from_id="3", to_id="2", blocked=(idx % 3 == 2)),
            riddle_director.SightlineRay(from_id="2", to_id="1", blocked=False),
        ]

    countdown = raw_riddle.get("countdown_seconds")
    if countdown is None and idx >= max(0, len(proj_data.get("scenes", [])) - 3):
        countdown = 7.0

    cta_banner = raw_riddle.get("cta_banner")
    elimination_banner = raw_riddle.get("elimination_banner")

    return riddle_director.RiddleSceneSpec(
        title=title,
        inventory=inventory,
        characters=characters,
        sightlines=sightlines,
        countdown_seconds=float(countdown) if countdown is not None else None,
        elimination_banner=str(elimination_banner) if elimination_banner else None,
        cta_banner=str(cta_banner) if cta_banner else None,
    )


class VariantEngine:
    """Base contract for all 7 production style engines."""

    variant: str = ""

    def validate(self, project: Union[Dict[str, Any], Path, str]) -> List[str]:
        try:
            proj_data, proj_json, _ = _load_project_input(project)
        except Exception as exc:
            return [str(exc)]

        errors = list(validate_project(proj_data, project_path=proj_json))
        actual_variant = proj_data.get("variant")
        if actual_variant != self.variant:
            errors.append(f"project.variant: expected {self.variant!r} for {self.__class__.__name__}, got {actual_variant!r}")
        return errors

    def render_scene_clip(
        self,
        *,
        project_dir: Path,
        proj_data: Dict[str, Any],
        scene: Dict[str, Any],
        scene_idx: int,
        source_image: Path,
        target_vid: Path,
        duration_s: float,
        words: List[Dict[str, Any]],
        width: int,
        height: int,
        fps: int = 30,
    ) -> bool:
        raise NotImplementedError

    def build(
        self,
        project: Union[Dict[str, Any], Path, str],
        out_dir: Optional[Path] = None,
        *,
        preview: bool = False,
        force_motion: bool = False,
    ) -> Path:
        errors = self.validate(project)
        if errors:
            raise ValueError("Invalid project for engine build:\n" + "\n".join(errors))

        proj_data, proj_json, project_dir = _load_project_input(project)
        for sub in ("images", "videos", "cache", "output"):
            (project_dir / sub).mkdir(parents=True, exist_ok=True)

        if proj_json is None:
            proj_json = project_dir / "project.json"

        cache_dir = project_dir / "cache"
        is_long = proj_data.get("format", "short") == "long"
        if preview:
            vid_w, vid_h = (960, 540) if is_long else (540, 960)
        else:
            vid_w, vid_h = (1920, 1080) if is_long else (1080, 1920)

        voice = _validate_kokoro_voice(proj_data.get("voice", "kokoro"))
        rate = str(proj_data.get("rate", "+1%"))
        pitch = str(proj_data.get("pitch", "-2Hz"))
        default_gap = float(proj_data.get("gap", 0.08))

        manifest = RenderManifest.load(cache_dir / "render_manifest.json")
        scenes = proj_data.get("scenes", [])

        for idx, sc in enumerate(scenes):
            raw_text = str(sc.get("text", "")).replace("*", "").strip()
            mp3_path, spoken_words = build_video.tts_cached(raw_text, voice, rate, pitch, cache_dir)
            audio_arr = build_video.decode_audio(mp3_path)
            a_trim, b_trim = build_video.auto_trim_bounds(audio_arr, spoken_words)
            dur = max(2.2, round((b_trim - a_trim) + float(sc.get("pause", default_gap)), 2))

            stem = Path(str(sc.get("video") or sc.get("image") or f"s{idx + 1:02d}")).stem
            src_img = _ensure_scene_plate(project_dir, proj_data, sc, idx, vid_w, vid_h)
            sc["image"] = str(src_img.relative_to(project_dir))

            target_vid = project_dir / "videos" / f"{stem}.mp4"
            sc["video"] = f"videos/{stem}.mp4"
            preset = str(sc.get("preset") or sc.get("motion") or self.variant)

            fingerprint = scene_fingerprint(
                scene_index=idx,
                scene=sc,
                source_image=src_img,
                duration_s=dur,
                preset=preset,
                width=vid_w,
                height=vid_h,
                variant=self.variant,
                audio_path=mp3_path,
                timings=spoken_words,
            )

            scene_key = str(idx)
            needs_render = force_motion or preview or not manifest.can_reuse(scene_key, fingerprint, target_vid)
            if needs_render:
                target_vid.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(prefix=f".{target_vid.stem}.render-", dir=target_vid.parent) as staging:
                    staged_clip = Path(staging) / target_vid.name
                    self.render_scene_clip(
                        project_dir=project_dir,
                        proj_data=proj_data,
                        scene=sc,
                        scene_idx=idx,
                        source_image=src_img,
                        target_vid=staged_clip,
                        duration_s=dur,
                        words=spoken_words,
                        width=vid_w,
                        height=vid_h,
                        fps=30,
                    )
                    encoded_ok, encoded_detail = verify_encoded_output(staged_clip)
                    if not encoded_ok:
                        raise RuntimeError(f"Scene {idx + 1} ({self.variant}) produced invalid clip: {encoded_detail}")
                    staged_clip.replace(target_vid)
                if not preview:
                    manifest.record(scene_key, fingerprint, target_vid)
                    manifest.save()

        proj_json.write_text(json.dumps(proj_data, indent=2), encoding="utf-8")

        target_out_dir = Path(out_dir) if out_dir is not None else (project_dir / "output")
        target_out_dir.mkdir(parents=True, exist_ok=True)
        slug_name = str(proj_data.get("slug") or project_dir.name)
        suffix = "_preview.mp4" if preview else ".mp4"
        out_mp4 = target_out_dir / f"{slug_name}{suffix}"

        return build_video.build(proj_json, out_mp4, preview=preview, hw_accel=True)

    def preview(self, project: Union[Dict[str, Any], Path, str], out_dir: Optional[Path] = None) -> Path:
        return self.build(project, out_dir=out_dir, preview=True)


class Cinematic35mmEngine(VariantEngine):
    variant = "cinematic_35mm"

    def render_scene_clip(self, *, source_image: Path, target_vid: Path, duration_s: float, scene: Dict[str, Any], scene_idx: int, width: int, height: int, fps: int = 30, **_: Any) -> bool:
        from tools import photobook_engine

        src_bgr = cv2.imread(str(source_image))
        if src_bgr is None:
            src_bgr = np.full((height, width, 3), (24, 30, 42), dtype=np.uint8)
        layers = photobook_engine.decompose_single_image(src_bgr, width, height)
        trajectories = ("lemmino_reveal", "magnates_drift", "archival_zoom", "vertigo_reveal")
        traj = str(scene.get("trajectory") or trajectories[scene_idx % len(trajectories)])
        style = str(scene.get("style") or "portra_35mm")
        return photobook_engine.render_photobook_scene(
            layers=layers,
            output_path=target_vid,
            style=style,
            trajectory=traj,
            duration=duration_s,
            fps=fps,
            width=width,
            height=height,
        )


class PhotobookVariantEngine(VariantEngine):
    variant = "photobook"

    def render_scene_clip(self, *, source_image: Path, target_vid: Path, duration_s: float, scene: Dict[str, Any], scene_idx: int, width: int, height: int, fps: int = 30, **_: Any) -> bool:
        from tools import photobook_engine

        src_bgr = cv2.imread(str(source_image))
        if src_bgr is None:
            src_bgr = np.full((height, width, 3), (28, 24, 20), dtype=np.uint8)
        layers = photobook_engine.decompose_single_image(src_bgr, width, height)
        trajectories = ("magnates_drift", "archival_zoom", "lemmino_reveal", "vertigo_reveal")
        traj = str(scene.get("trajectory") or trajectories[scene_idx % len(trajectories)])
        style = str(scene.get("style") or "magnates_amber")
        return photobook_engine.render_photobook_scene(
            layers=layers,
            output_path=target_vid,
            style=style,
            trajectory=traj,
            duration=duration_s,
            fps=fps,
            width=width,
            height=height,
        )


class StorybookPicturebookEngine(VariantEngine):
    variant = "storybook_picturebook"

    def render_scene_clip(
        self,
        *,
        project_dir: Path,
        proj_data: Dict[str, Any],
        scene: Dict[str, Any],
        scene_idx: int,
        target_vid: Path,
        duration_s: float,
        words: List[Dict[str, Any]],
        width: int,
        height: int,
        fps: int = 30,
        **_: Any,
    ) -> bool:
        from tools import picture_book_engine

        elements = picture_book_engine.story_elements_from_project(proj_data)
        element = elements[scene_idx]
        images_dir = project_dir / "images"
        cutouts_dir = images_dir / "cutouts"
        normalized_words = [
            {"word": str(w.get("word") or w.get("text") or ""), "start": float(w.get("start", 0.0)), "end": float(w.get("end", 0.0))}
            for w in words
        ]
        picture_book_engine.render_dynamic_scene_clip(
            element=element,
            images_dir=images_dir,
            cutouts_dir=cutouts_dir,
            dur=duration_s,
            words=normalized_words,
            output_mp4=target_vid,
            is_first_scene=(scene_idx == 0),
            is_last_scene=(scene_idx == len(elements) - 1),
            fps=fps,
            width=width,
            height=height,
        )
        return target_vid.exists()


class StickmanSkeletonEngine(VariantEngine):
    variant = "stickman_skeleton"

    def render_scene_clip(self, *, proj_data: Dict[str, Any], scene: Dict[str, Any], scene_idx: int, target_vid: Path, duration_s: float, width: int, height: int, fps: int = 30, **_: Any) -> bool:
        from tools import stickman_engine

        poses = ("thinking", "pointing", "idle", "shocked", "shrugging", "facepalm", "running")
        mouths = ("neutral", "smile", "open_gasp", "smirk", "frown")
        props = ("magnifying_glass", "coffee", "pointer", "phone", None)
        accessories = ("flat_cap", "glasses", "fedora")

        seed_input = "|".join([
            str(proj_data.get("id", "")),
            str(proj_data.get("title", "")),
            str(proj_data.get("topic", "")),
            str(scene.get("id", "")),
            str(scene.get("text", "")),
            str(scene.get("prompt", "")),
        ])
        seed_h = hashlib.sha256(seed_input.encode("utf-8")).digest()
        raw_pose = scene.get("pose")
        if isinstance(raw_pose, dict):
            pose_name = str(raw_pose.get("name") or raw_pose.get("pose") or poses[(scene_idx + seed_h[0]) % len(poses)])
            mouth_name = str(raw_pose.get("mouth") or scene.get("mouth") or mouths[(scene_idx + seed_h[1]) % len(mouths)])
            prop_name = raw_pose.get("prop", scene.get("prop", props[(scene_idx + seed_h[2]) % len(props)]))
            acc_name = str(raw_pose.get("accessory") or scene.get("accessory") or accessories[seed_h[3] % len(accessories)])
        else:
            pose_name = str(raw_pose or poses[(scene_idx + seed_h[0]) % len(poses)])
            mouth_name = str(scene.get("mouth") or mouths[(scene_idx + seed_h[1]) % len(mouths)])
            prop_name = scene.get("prop", props[(scene_idx + seed_h[2]) % len(props)])
            acc_name = str(scene.get("accessory") or accessories[seed_h[3] % len(accessories)])

        acc_color = (int(40 + seed_h[4] % 160), int(45 + seed_h[5] % 150), int(55 + seed_h[6] % 160))
        app = stickman_engine.StickmanAppearance(accessory=acc_name, accessory_color=acc_color)
        pose_spec = stickman_engine.StickmanPoseSpec(pose=pose_name, mouth=mouth_name, prop=prop_name)
        caption_str = str(scene.get("plate_label") or scene.get("caption") or scene.get("text") or "").strip()[:64]
        return stickman_engine.render_stickman_scene(
            pose_spec=pose_spec,
            app=app,
            output_path=target_vid,
            caption_text=caption_str or None,
            duration=duration_s,
            fps=fps,
            width=width,
            height=height,
        )


class RiddleVariantEngine(VariantEngine):
    variant = "riddle"

    def render_scene_clip(self, *, proj_data: Dict[str, Any], scene: Dict[str, Any], scene_idx: int, source_image: Path, target_vid: Path, duration_s: float, width: int, height: int, fps: int = 30, **_: Any) -> bool:
        from tools import riddle_director

        base_img = cv2.imread(str(source_image))
        if base_img is None:
            base_img = np.full((height, width, 3), (30, 38, 52), dtype=np.uint8)
        spec = _build_riddle_spec_for_scene(proj_data, scene, scene_idx)
        return riddle_director.render_riddle_scene(
            base_image=base_img,
            spec=spec,
            output_path=target_vid,
            duration=duration_s,
            fps=fps,
            width=width,
            height=height,
        )


class HybridMixedMediaEngine(VariantEngine):
    variant = "hybrid_mixed_media"

    def render_scene_clip(self, *, proj_data: Dict[str, Any], scene: Dict[str, Any], scene_idx: int, source_image: Path, target_vid: Path, duration_s: float, width: int, height: int, fps: int = 30, **_: Any) -> bool:
        from tools import hybrid_engine, stickman_engine

        bg_img = cv2.imread(str(source_image))
        if bg_img is None:
            bg_img = np.full((height, width, 3), (24, 30, 42), dtype=np.uint8)

        poses = ("pointing", "thinking", "shocked", "shrugging", "idle")
        props = ("magnifying_glass", "pointer", "coffee", "phone")
        raw_pose = scene.get("pose")
        if isinstance(raw_pose, dict):
            pose_name = str(raw_pose.get("name") or raw_pose.get("pose") or poses[scene_idx % len(poses)])
            prop_name = raw_pose.get("prop", scene.get("prop", props[scene_idx % len(props)]))
        else:
            pose_name = str(raw_pose or poses[scene_idx % len(poses)])
            prop_name = scene.get("prop", props[scene_idx % len(props)])

        pose_spec = stickman_engine.StickmanPoseSpec(pose=pose_name, mouth="neutral", prop=prop_name)
        app = stickman_engine.StickmanAppearance(accessory=str(scene.get("accessory") or "flat_cap"))
        riddle_spec = _build_riddle_spec_for_scene(proj_data, scene, scene_idx)
        riddle_spec.cta_banner = None

        return hybrid_engine.render_hybrid_scene(
            bg_image=bg_img,
            pose_spec=pose_spec,
            appearance=app,
            riddle_spec=riddle_spec,
            output_path=target_vid,
            style=str(scene.get("style") or "magnates_amber"),
            trajectory=str(scene.get("trajectory") or "magnates_drift"),
            duration=duration_s,
            fps=fps,
            width=width,
            height=height,
        )


class CutoutCartoonEngine(VariantEngine):
    variant = "cutout_cartoon"

    def render_scene_clip(
        self,
        *,
        project_dir: Path,
        proj_data: Dict[str, Any],
        scene: Dict[str, Any],
        scene_idx: int,
        target_vid: Path,
        duration_s: float,
        words: List[Dict[str, Any]],
        width: int,
        height: int,
        fps: int = 30,
        **_: Any,
    ) -> bool:
        from tools.cutout_engine import cutout_director
        from tools.sound_architect import DECIBEL_BUDGET, db_to_linear

        sprites_dir = _ensure_cutout_sprites(project_dir / "images" / "cutouts" / "normalized", proj_data)
        poses = ("idle", "pointing", "thinking", "shocked", "shrugging", "running")
        actions = ("hold", "turn", "action")
        gags = (None, "eyes_open", "squash_blast")

        raw_pose = scene.get("pose")
        if isinstance(raw_pose, dict):
            pose_id = str(raw_pose.get("name") or raw_pose.get("pose") or poses[scene_idx % len(poses)])
        else:
            pose_id = str(raw_pose or poses[scene_idx % len(poses)])
        action_type = str(scene.get("action_type") or actions[scene_idx % len(actions)])
        gag = scene.get("gag", gags[scene_idx % len(gags)])
        cam_z = float(scene.get("cam_z", 120.0 if scene_idx % 2 == 1 else 0.0))

        beat = cutout_director.CutoutBeat(
            start_sec=0.0,
            end_sec=duration_s,
            line_text=str(scene.get("text", "")),
            pose_id=pose_id,
            action_type=action_type,
            camera_pos=(width / 2.0, height * 0.50, cam_z),
            gag=gag,
        )
        seed_input = "|".join([
            str(proj_data.get("id", "")),
            str(proj_data.get("title", "")),
            str(proj_data.get("topic", "")),
            str(scene.get("id", "")),
            str(scene.get("text", "")),
        ])
        seed_d = hashlib.sha256(seed_input.encode("utf-8")).digest()
        bg_color = (int(205 + seed_d[0] % 45), int(180 + seed_d[1] % 55), int(140 + seed_d[2] % 55))
        c_proj = cutout_director.CutoutProject(
            slug=f"{project_dir.name}_s{scene_idx + 1:02d}",
            title=str(proj_data.get("title") or project_dir.name),
            voice_text=str(scene.get("text", "")),
            beats=[beat],
            bg_color=bg_color,
        )

        tmp_wav = target_vid.with_suffix(".scene_voice.wav")
        sr = 48000
        n_samples = max(1, int(round(duration_s * sr)))
        t_arr = np.linspace(0.0, max(0.05, duration_s), n_samples, endpoint=False, dtype=np.float32)
        tone = (0.04 * np.sin(2.0 * math.pi * 220.0 * t_arr) * 32767.0).astype(np.int16)
        stereo = np.column_stack([tone, tone]).ravel()
        with wave.open(str(tmp_wav), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(stereo.tobytes())

        temp_raw = target_vid.with_suffix(".raw.mp4")
        drone_bed = target_vid.with_suffix(".drone.wav")
        try:
            cutout_director.render_cutout_short_video(
                project=c_proj,
                sprites_dir=sprites_dir,
                output_mp4=target_vid,
                voice_wav=tmp_wav,
                width=width,
                height=height,
                fps=fps,
            )
        except subprocess.CalledProcessError:
            if not temp_raw.exists():
                raise
            drone_vol = db_to_linear(DECIBEL_BUDGET["ambient_bed"])
            cmd_fallback = [
                "ffmpeg", "-y",
                "-i", str(temp_raw),
                "-i", str(tmp_wav),
                "-i", str(drone_bed),
                "-filter_complex",
                f"[1:a]volume=1.0[v];[2:a]volume={drone_vol:.4f}[d];[v][d]amix=inputs=2:normalize=0,loudnorm=I=-14.0:TP=-1.5:LRA=7.0[aout]",
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "libx264",
                "-crf", "18",
                "-preset", "fast",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "320k",
                "-ar", "48000",
                "-shortest",
                str(target_vid),
            ]
            subprocess.run(cmd_fallback, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        finally:
            tmp_wav.unlink(missing_ok=True)
            temp_raw.unlink(missing_ok=True)
            drone_bed.unlink(missing_ok=True)
        return target_vid.exists()


ENGINE_REGISTRY: Dict[str, VariantEngine] = {
    "cinematic_35mm": Cinematic35mmEngine(),
    "photobook": PhotobookVariantEngine(),
    "storybook_picturebook": StorybookPicturebookEngine(),
    "stickman_skeleton": StickmanSkeletonEngine(),
    "riddle": RiddleVariantEngine(),
    "hybrid_mixed_media": HybridMixedMediaEngine(),
    "cutout_cartoon": CutoutCartoonEngine(),
}


def get_engine(variant: str) -> VariantEngine:
    """Returns the registered VariantEngine for `variant` or raises ValueError."""
    if not isinstance(variant, str) or variant not in ENGINE_REGISTRY:
        valid = ", ".join(SUPPORTED_VARIANTS)
        raise ValueError(f"Unsupported variant {variant!r}; expected one of: {valid}")
    return ENGINE_REGISTRY[variant]


def list_variants() -> None:
    """Displays a clean, structured overview of all 7 canonical video production variants."""
    print("\n" + "=" * 80)
    print(" FrameForge Universal Multi-Variant Production Architecture (7 Canonical Variants)")
    print("=" * 80)
    for key, info in UNIVERSAL_VARIANTS.items():
        print(f"\n[{key.upper()}] - {info['name']}")
        print(f"  * Description:   {info['description']}")
        print(f"  * Target Format: {info['target_format']}")
        print(f"  * Pacing:        {info['pacing']}")
        print(f"  * Audio Profile: {info['audio']}")
    print("\n" + "=" * 80 + "\n")


def find_project_dir(slug: str) -> Optional[Path]:
    """Finds a project directory in projects/, shorts/, or long_form/."""
    candidates = [
        PROJECT_ROOT / "projects" / slug,
        PROJECT_ROOT / "shorts" / slug,
        PROJECT_ROOT / "long_form" / slug,
    ]
    for c in candidates:
        if c.exists() and (c / "project.json").exists():
            return c
    for c in candidates:
        if c.exists():
            return c
    return None


def _default_scenes_for_topic(topic: str, title: str, variant: str, count: int = 8) -> List[Dict[str, Any]]:
    """Builds 8 schema-valid, topic-specific default scenes when scaffolding a new project."""
    clean_topic = topic.strip() or "Cognitive Science"
    clean_title = title.strip() or clean_topic.title()
    beats = [
        f"When you encounter {clean_topic} in everyday life, why does your first instinct feel so certain yet miss the hidden pattern?",
        f"Behavioral researchers studying {clean_topic} noticed that people consistently misread the earliest signal under time pressure.",
        f"In controlled experiments on {clean_topic}, participants focused on the loudest cue while ignoring the baseline rate right in front of them.",
        f"That single shift in attention explains how {clean_topic} quietly reshapes decisions before conscious reasoning even starts.",
        f"Notice what happens when you slow the sequence down and compare each assumption in {clean_topic} against measurable evidence.",
        f"Once the underlying mechanism of {clean_topic} becomes visible, the original paradox stops looking mysterious and starts looking predictable.",
        f"You can test {clean_topic} yourself today by writing down your first prediction before checking the outcome.",
        f"Where have you noticed {clean_topic} in your own decisions? Drop your example in the comments and subscribe for the next breakdown.",
    ]
    scenes: List[Dict[str, Any]] = []
    for i in range(max(8, count)):
        sc_id = f"s{i + 1:02d}"
        text = beats[i % len(beats)]
        scenes.append({
            "id": sc_id,
            "text": text,
            "caption": text,
            "prompt": f"{clean_title} ({variant}) visual plate {i + 1}: {clean_topic} documentary evidence scene {i + 1}",
            "image": f"images/{sc_id}.jpg",
            "duration": 4.2,
        })
    return scenes


def create_project(
    slug: str,
    variant: str = "storybook_picturebook",
    format_type: str = "long",
    topic: str = "Untitled Project",
    title: str = "",
    *,
    video_id: Optional[str] = None,
    channel_id: str = "cognitive_core",
    voice: str = "kokoro",
    scenes: Optional[List[Dict[str, Any]]] = None,
    base_dir: Optional[Path] = None,
) -> Path:
    """Scaffolds a standardized Schema v2 project structure and validates it before writing."""
    if variant not in UNIVERSAL_VARIANTS:
        valid_keys = ", ".join(UNIVERSAL_VARIANTS.keys())
        raise ValueError(f"Unknown variant '{variant}'. Must be one of: {valid_keys}")

    fmt_norm = "short" if format_type.lower() in {"short", "shorts"} else "long"
    validated_voice = _validate_kokoro_voice(voice)

    if not title:
        title = topic.title()

    if video_id is None:
        prefix = "SH" if fmt_norm == "short" else "LV"
        digest_num = int(hashlib.sha256(slug.encode("utf-8")).hexdigest()[:4], 16) % 90 + 10
        video_id = f"{prefix}-{digest_num}"

    scene_list = [dict(s) for s in scenes] if scenes is not None else _default_scenes_for_topic(topic, title, variant)

    project_data: Dict[str, Any] = {
        "schema_version": PROJECT_SCHEMA_VERSION,
        "id": video_id,
        "slug": slug,
        "channel_id": channel_id,
        "variant": variant,
        "genre": variant,
        "format": fmt_norm,
        "topic": topic,
        "title": title,
        "voice": validated_voice,
        "fps": 30,
        "scenes": scene_list,
    }

    errors = validate_project(project_data)
    if errors:
        raise ValueError("Invalid project schema in create_project:\n" + "\n".join(errors))

    if base_dir is not None:
        proj_dir = Path(base_dir) / slug
    elif fmt_norm == "short":
        proj_dir = PROJECT_ROOT / "shorts" / slug
    else:
        proj_dir = PROJECT_ROOT / "projects" / slug

    for sub in ("images", "videos", "cache", "output"):
        (proj_dir / sub).mkdir(parents=True, exist_ok=True)

    proj_json_path = proj_dir / "project.json"
    proj_json_path.write_text(json.dumps(project_data, indent=2), encoding="utf-8")

    aspect_ratio = "9:16" if fmt_norm == "short" else "16:9"
    kit_path = proj_dir / f"UPLOAD_KIT_{slug.upper()}.md"
    kit_content = f"""# UPLOAD KIT: {title} ({slug})
> **Variant**: {UNIVERSAL_VARIANTS[variant]['name']}
> **Format**: {aspect_ratio} ({fmt_norm.upper()})
> **Channel**: {channel_id}

## 1. Title Options
* **Primary (Curiosity + Mechanism)**:
> `{title}`

## 2. Description Block
{topic} — explored through {UNIVERSAL_VARIANTS[variant]['name']}.
"""
    kit_path.write_text(kit_content, encoding="utf-8")
    return proj_dir


def clean_project(slug: str, dry_run: bool = False) -> Dict[str, Any]:
    """Cleans up temporary intermediate render caches, wav gaps, and raw videos while preserving masters."""
    proj_dir = find_project_dir(slug)
    if not proj_dir:
        raise FileNotFoundError(f"Project directory not found for slug '{slug}'")

    cache_dir = proj_dir / "cache"
    patterns_to_remove = [
        "*.raw.mp4",
        "*.raw.wav",
        "gap_*.wav",
        "tmp_*.wav",
        "tmp_*.mp4",
        "raw_*.wav",
        "*.tmp",
    ]

    files_found: List[Path] = []
    total_bytes = 0

    if cache_dir.exists():
        for pat in patterns_to_remove:
            for p in cache_dir.glob(pat):
                files_found.append(p)
                total_bytes += p.stat().st_size

    videos_dir = proj_dir / "videos"
    if videos_dir.exists():
        for p in videos_dir.glob("*.raw.mp4"):
            files_found.append(p)
            total_bytes += p.stat().st_size

    freed_mb = total_bytes / (1024 * 1024)

    if not dry_run:
        for f in files_found:
            f.unlink(missing_ok=True)

    return {"cleaned_files": len(files_found), "freed_mb": freed_mb}


def build_project(
    slug_or_path: Union[str, Path, Dict[str, Any]],
    out_dir: Optional[Path] = None,
    *,
    preview: bool = False,
    force_motion: bool = False,
) -> Path:
    """Builds a project by validating its schema v2 contract and dispatching to its registered VariantEngine."""
    proj_data, proj_json, project_dir = _load_project_input(slug_or_path)
    variant = proj_data.get("variant")
    engine = get_engine(variant)
    target = proj_json if proj_json is not None else proj_data
    return engine.build(target, out_dir=out_dir, preview=preview, force_motion=force_motion)


def preview_project(
    slug_or_path: Union[str, Path, Dict[str, Any]],
    out_dir: Optional[Path] = None,
) -> Path:
    """Renders a fast preview MP4 for a project via its registered VariantEngine."""
    proj_data, proj_json, _ = _load_project_input(slug_or_path)
    engine = get_engine(proj_data.get("variant"))
    target = proj_json if proj_json is not None else proj_data
    return engine.preview(target, out_dir=out_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description="FrameForge Universal Multi-Variant Production Engine")
    parser.add_argument("--list-variants", action="store_true", help="List all 7 canonical video production variants")
    parser.add_argument("--create-project", action="store_true", help="Scaffold a new project directory and configuration")
    parser.add_argument("--build-project", action="store_true", help="Build a project using its configured variant engine")
    parser.add_argument("--clean-project", action="store_true", help="Clean temporary cache and raw files for a project")
    parser.add_argument("--slug", type=str, help="Project slug (e.g. video_01, long_01_db_cooper_1971)")
    parser.add_argument("--variant", choices=list(UNIVERSAL_VARIANTS.keys()), default="storybook_picturebook", help="Variant choice")
    parser.add_argument("--format", choices=["short", "long"], default="long", help="Video format (short: 9:16, long: 16:9)")
    parser.add_argument("--topic", type=str, default="Untitled Topic", help="Topic or subject of the video")
    parser.add_argument("--title", type=str, default="", help="Display title of the video")
    parser.add_argument("--dry-run", action="store_true", help="Perform a dry-run check without deleting or rendering files")

    # Legacy showcase demo flags (routed to demos/archetype_demos.py)
    parser.add_argument("--all-30s", action="store_true", help="Generate all archetypes as 30s broadcast Full HD demo videos")
    parser.add_argument("--demo", action="store_true", help="Generate quick probe demos")
    parser.add_argument("--photobook-30s", action="store_true", help="Render 30s broadcast Full HD photobook demo")
    parser.add_argument("--riddle-30s", action="store_true", help="Render 30s broadcast Full HD riddle demo")
    parser.add_argument("--stickman-30s", action="store_true", help="Render 30s broadcast Full HD stickman demo")
    parser.add_argument("--hybrid-30s", action="store_true", help="Render 30s broadcast Full HD hybrid demo")
    parser.add_argument("--archetype", choices=["photobook", "riddle", "stickman", "hybrid"], help="Generate a specific archetype probe")
    parser.add_argument("-o", "--output", type=str, help="Output MP4 file path")
    parser.add_argument("-d", "--duration", type=float, default=3.5, help="Duration in seconds (default 3.5)")
    args = parser.parse_args()

    demo_dir = PROJECT_ROOT / "demos"

    if args.list_variants:
        list_variants()
        return 0

    if args.create_project:
        if not args.slug:
            print("Error: --slug is required to create a project (e.g. --slug video_01)")
            return 1
        create_project(
            slug=args.slug,
            variant=args.variant,
            format_type=args.format,
            topic=args.topic,
            title=args.title,
        )
        return 0

    if args.build_project:
        if not args.slug:
            print("Error: --slug is required to build a project")
            return 1
        res_mp4 = build_project(args.slug, out_dir=Path(args.output).parent if args.output else None)
        print(f"\n[Project Build Succeeded] {res_mp4} ({res_mp4.stat().st_size / 1e6:.2f} MB)")
        return 0

    if args.clean_project:
        if not args.slug:
            print("Error: --slug is required to clean a project")
            return 1
        clean_project(args.slug, dry_run=args.dry_run)
        return 0

    if args.all_30s:
        results = generate_all_4_archetype_demos(demo_dir)
        for name, path in results.items():
            print(f"  * {name.upper()}: {path} ({path.stat().st_size / 1e6:.2f} MB)")
        return 0

    if args.photobook_30s:
        out = Path(args.output) if args.output else demo_dir / "demo_01_photobook_30s_hd.mp4"
        render_30s_photobook_hd_with_audio(out)
        return 0

    if args.riddle_30s:
        out = Path(args.output) if args.output else demo_dir / "demo_02_riddle_30s_hd.mp4"
        render_30s_riddle_hd_with_audio(out)
        return 0

    if args.stickman_30s:
        out = Path(args.output) if args.output else demo_dir / "demo_03_stickman_30s_hd.mp4"
        render_30s_stickman_hd_with_audio(out)
        return 0

    if args.hybrid_30s:
        out = Path(args.output) if args.output else demo_dir / "demo_04_hybrid_30s_hd.mp4"
        render_30s_hybrid_hd_with_audio(out)
        return 0

    if args.demo:
        render_photobook_from_scratch(demo_dir / "demo_01_photobook.mp4")
        render_riddle_from_scratch(demo_dir / "demo_02_riddle.mp4")
        render_stickman_from_scratch(demo_dir / "demo_03_stickman.mp4")
        render_hybrid_from_scratch(demo_dir / "demo_04_hybrid.mp4")
        return 0

    if args.archetype:
        out = Path(args.output) if args.output else demo_dir / f"demo_{args.archetype}.mp4"
        if args.archetype == "photobook":
            render_photobook_from_scratch(out, duration=args.duration)
        elif args.archetype == "riddle":
            render_riddle_from_scratch(out, duration=args.duration)
        elif args.archetype == "stickman":
            render_stickman_from_scratch(out, duration=args.duration)
        elif args.archetype == "hybrid":
            render_hybrid_from_scratch(out, duration=args.duration)
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
