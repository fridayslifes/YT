#!/usr/bin/env python3
"""branding_engine.py - SOTA Intro Stinger & Outro End-Screen Suite for FrameForge Studio.

Generates broadcast-grade branding assets:
1. channel_assets/intro_16x9.mp4 (2.5s Long-Form Intro Stinger @ 1080p, 14 Mbps)
2. channel_assets/intro_9x16.mp4 (2.0s Shorts Intro Stinger @ 1080x1920, 14 Mbps)
3. channel_assets/outro_16x9_endscreen.mp4 (15.0s YouTube End Screen Master with Video & Subscribe Targets)
4. channel_assets/outro_9x16_loop.mp4 (2.5s Shorts Infinite Loop Bridge)

Audio:
- Intro: 45Hz sub-bass hit + mechanical 35mm shutter click + decaying analog tape tail
- Outro: 15s warm atmospheric cinematic drone + vinyl crackle with exponential fade-out

Loudness, as run_branding_check() measures it after every render: the 15s end screen lands at
-14.5 LUFS, but the three sub-3s stingers stay near -18 (-18.1/-18.1/-17.4). That is not the filter
failing - their true peak is already at the -1.5 dBTP ceiling, so the +4 dB of linear gain loudnorm
would need is refused, and dynamic mode cannot ramp inside 3 seconds. Raising them means crushing the
transient, which is the part of the stinger you hear. Treat the stingers as -18 LUFS assets and dip
the film under them if they ever sound hot; the check prints the measured numbers so the log cannot
claim -14.
"""
import array
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
from tools.processes import run_process  # noqa: E402


def _channel_labels() -> tuple[str, str]:
    """Return (UPPER_NAME, handle) from configs/channels/default.yaml."""
    from tools.channel_config import load_channel_config

    try:
        cfg = load_channel_config("default")
        name = (cfg.channel_name or "MY CHANNEL").upper()
        handle = cfg.handle or "@MyChannel"
    except Exception:
        name = "MY CHANNEL"
        handle = "@MyChannel"
    return name, handle

ASSETS_DIR = os.path.join(ROOT_DIR, "channel_assets")
FONTS_DIR = os.path.join(ROOT_DIR, "tools", "fonts")
SFX_DIR = os.path.join(ROOT_DIR, "assets", "audio", "sfx")

FPS = 30
SAMPLE_RATE = 44100
PROBE_TIMEOUT_S = 30.0
MEDIA_TIMEOUT_S = 120.0

# Every finished file on this channel is BT.709 limited-range (build_video.py:1138). These masters
# used to be encoded from a JPEG frame sequence with no colour flags at all, so they carried
# yuvj420p/smpte170m and splicing an outro onto a graded video flipped its colour space mid-stream.
# PNG frames plus the explicit flags below make the masters match the deliverable.
# The main builder normalises every finished video with this exact filter (build_video.py:1151), so
# the masters carry it too. It reaches the -14 LUFS target on the 15s end screen and no-ops on the
# sub-3s stingers, whose true peak is already at the ceiling - see the module docstring for the
# measured numbers. What it can do unconditionally is keep audio off the file's own clipping edge.
AUDIO_FLAGS = ["-af", "loudnorm=I=-14:TP=-1.5:LRA=11"]

COLOR_FLAGS = [
    "-pix_fmt", "yuv420p",
    "-color_range", "tv",
    "-color_primaries", "bt709",
    "-color_trc", "bt709",
    "-colorspace", "bt709",
]

def get_font(size: int, bold: bool = True):
    font_name = "BeVietnamPro-Bold.ttf" if bold else "BeVietnamPro-Medium.ttf"
    font_path = os.path.join(FONTS_DIR, font_name)
    try:
        return ImageFont.truetype(font_path, size)
    except Exception:
        return ImageFont.load_default()

def synthesize_intro_audio(output_wav: str, duration: float = 2.5):
    """Synthesizes high-impact 2.5s sonic stinger audio."""
    n_samples = int(SAMPLE_RATE * duration)
    left, right = [0.0] * n_samples, [0.0] * n_samples

    # 1. Sub-bass felt drop (t = 0.25s)
    sub_start = int(0.25 * SAMPLE_RATE)
    sub_len = int(0.60 * SAMPLE_RATE)
    for i in range(sub_len):
        idx = sub_start + i
        if idx >= n_samples:
            break
        t = i / SAMPLE_RATE
        freq = 55.0 - (18.0 * (t / 0.60))
        env = math.sin(math.pi * min(1.0, t / 0.06)) * math.exp(-t / 0.18)
        val = 0.60 * env * math.sin(2 * math.pi * freq * t)
        left[idx] += val
        right[idx] += val

    # 2. Shutter click transient
    shutter_path = os.path.join(SFX_DIR, "shutter.wav")
    if os.path.exists(shutter_path):
        try:
            with wave.open(shutter_path, "rb") as wf:
                sw, nc, nf = wf.getsampwidth(), wf.getnchannels(), wf.getnframes()
                raw = wf.readframes(nf)
                if sw == 2:
                    samples = array.array("h")
                    samples.frombytes(raw)
                    shutter_start = int(0.28 * SAMPLE_RATE)
                    for k in range(0, min(len(samples), (n_samples - shutter_start) * nc), nc):
                        target = shutter_start + (k // nc)
                        if target < n_samples:
                            l_val = (samples[k] / 32768.0) * 0.45
                            r_val = (samples[k + 1] / 32768.0) * 0.45 if nc > 1 else l_val
                            left[target] += l_val
                            right[target] += r_val
        except Exception as e:
            print(f"Shutter note: {e}")

    # 3. Metallic / Glass Resonant Chime Glint (t = 0.35s)
    glint_start = int(0.35 * SAMPLE_RATE)
    glint_len = int(0.70 * SAMPLE_RATE)
    for i in range(glint_len):
        idx = glint_start + i
        if idx >= n_samples:
            break
        t = i / SAMPLE_RATE
        env = math.exp(-t / 0.12)
        val = 0.08 * env * (math.sin(2 * math.pi * 1174.66 * t) + 0.5 * math.sin(2 * math.pi * 2349.32 * t))
        left[idx] += val
        right[idx] += val

    # 4. Soft tape hiss tail
    rng = np.random.RandomState(42)
    hiss = rng.normal(0, 0.015, n_samples)
    lp = 0.0
    for i in range(n_samples):
        t = i / SAMPLE_RATE
        lp += 0.07 * (hiss[i] - lp)
        fade_in = min(1.0, max(0.0, (t - 0.15) / 0.25))
        fade_out = min(1.0, max(0.0, (duration - t) / 0.70))
        amp = 0.04 * fade_in * fade_out
        left[i] += lp * amp
        right[i] += lp * amp

    # Normalize to -1.5 dB peak
    peak = max(max(abs(x) for x in left), max(abs(x) for x in right), 0.001)
    scale = (10.0 ** (-1.5 / 20.0)) / peak
    buf = array.array("h", [0] * (n_samples * 2))
    for i in range(n_samples):
        buf[2 * i] = int(max(-1.0, min(1.0, left[i] * scale)) * 32767.0)
        buf[2 * i + 1] = int(max(-1.0, min(1.0, right[i] * scale)) * 32767.0)

    with wave.open(output_wav, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(buf.tobytes())

def synthesize_outro_audio(output_wav: str, duration: float = 15.0):
    """Synthesizes smooth 15s cinematic atmospheric drone with vinyl warmth."""
    n_samples = int(SAMPLE_RATE * duration)
    left, right = [0.0] * n_samples, [0.0] * n_samples
    rng = np.random.RandomState(1234)

    # 1. Warm chord drone (D minor / A resonant frequencies: 73.4Hz, 110Hz, 146.8Hz, 220Hz)
    chord = [73.42, 110.00, 146.83, 220.00, 329.63]
    for i in range(n_samples):
        t = i / SAMPLE_RATE
        # Envelope: 1s fade-in, steady, 3s exponential fade-out
        fade_in = min(1.0, t / 1.0)
        fade_out = min(1.0, max(0.0, (duration - t) / 3.0))
        env = fade_in * fade_out

        val_l, val_r = 0.0, 0.0
        for idx, freq in enumerate(chord):
            detune = 1.0 + 0.003 * math.sin(2 * math.pi * 0.2 * t + idx)
            amp = 0.10 / (idx + 1)
            sig_l = math.sin(2 * math.pi * freq * detune * t)
            sig_r = math.sin(2 * math.pi * freq * detune * t + (math.pi / 4))
            val_l += amp * sig_l
            val_r += amp * sig_r

        left[i] = val_l * env
        right[i] = val_r * env

    # 2. Vinyl crackle / tape texture
    crackle = rng.normal(0, 0.008, n_samples)
    for i in range(n_samples):
        t = i / SAMPLE_RATE
        env = min(1.0, max(0.0, (duration - t) / 2.5))
        # Periodic random dust pops
        pop = 0.18 if (rng.rand() < 0.00015 and t > 0.5 and t < duration - 1.0) else 0.0
        left[i] += (crackle[i] + pop) * env
        right[i] += (crackle[i] + pop) * env

    # Normalize to -16 LUFS (-2.0 dB peak)
    peak = max(max(abs(x) for x in left), max(abs(x) for x in right), 0.001)
    scale = (10.0 ** (-2.0 / 20.0)) / peak
    buf = array.array("h", [0] * (n_samples * 2))
    for i in range(n_samples):
        buf[2 * i] = int(max(-1.0, min(1.0, left[i] * scale)) * 32767.0)
        buf[2 * i + 1] = int(max(-1.0, min(1.0, right[i] * scale)) * 32767.0)

    with wave.open(output_wav, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(buf.tobytes())

def render_intro_video(width: int, height: int, output_mp4: str, duration: float = 2.5):
    """Renders SOTA 2.5s Intro Stinger with volumetric bloom and chromatic edge dispersion."""
    temp_dir = tempfile.mkdtemp(prefix="intro_render_")
    total_frames = int(FPS * duration)

    avatar_3d_path = os.path.join(ASSETS_DIR, "avatar_3d_labyrinth_800x800.png")
    avatar_2d_path = os.path.join(ASSETS_DIR, "avatar_labyrinth_800x800.png")
    chosen_avatar_path = avatar_3d_path if os.path.exists(avatar_3d_path) else avatar_2d_path
    avatar = Image.open(chosen_avatar_path).convert("RGBA") if os.path.exists(chosen_avatar_path) else None

    title_size = 52 if width >= 1920 else 58
    sub_size = 22 if width >= 1920 else 26
    font_title = get_font(title_size, bold=True)
    font_sub = get_font(sub_size, bold=False)

    emblem_size = int(min(width, height) * 0.34)
    cx, cy = width // 2, (height // 2) - 35

    audio_wav = os.path.join(temp_dir, "intro_audio.wav")
    synthesize_intro_audio(audio_wav, duration)

    rng = np.random.RandomState(42)

    for f in range(total_frames):
        img = Image.new("RGBA", (width, height), (7, 8, 11, 255))
        draw = ImageDraw.Draw(img)

        # Global Alpha Envelope (Fade in 0..10 frames, fade out last 12 frames)
        if f < 10:
            alpha = f / 10.0
        elif f > (total_frames - 12):
            alpha = max(0.0, (total_frames - f) / 12.0)
        else:
            alpha = 1.0

        # Snappy exponential zoom
        zoom_prog = min(1.0, f / 14.0)
        zoom_scale = 0.60 + 0.40 * (1.0 - math.pow(2.0, -10.0 * zoom_prog))
        cur_emblem_w = int(emblem_size * zoom_scale)

        if avatar and cur_emblem_w > 10:
            emblem_scaled = avatar.resize((cur_emblem_w, cur_emblem_w), Image.Resampling.LANCZOS)
            ex = cx - cur_emblem_w // 2
            ey = cy - cur_emblem_w // 2

            # Optical chromatic aberration at snap impact (frame 9 to 18)
            if 8 <= f <= 18:
                chroma_shift = int(6 * math.sin(math.pi * ((f - 8) / 10.0)))
                r, g, b, a = emblem_scaled.split()
                # Offset red and cyan channels
                r_img = Image.new("RGBA", (cur_emblem_w, cur_emblem_w), (0, 0, 0, 0))
                r_img.paste(r, (chroma_shift, 0))
                b_img = Image.new("RGBA", (cur_emblem_w, cur_emblem_w), (0, 0, 0, 0))
                b_img.paste(b, (-chroma_shift, 0))
                chroma_comp = Image.merge("RGBA", (r_img.split()[0], g, b_img.split()[0], a))
                img.paste(chroma_comp, (ex, ey), mask=a)
            else:
                img.paste(emblem_scaled, (ex, ey), mask=emblem_scaled)

        # Optical Cyan Flash / Volumetric Bloom
        if 8 <= f <= 22:
            flash_p = math.sin(math.pi * ((f - 8) / 14.0))
            bloom_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            bl_draw = ImageDraw.Draw(bloom_layer)
            radius = int(cur_emblem_w * (0.8 + 0.5 * flash_p))
            bl_draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                            fill=(0, 229, 255, int(75 * flash_p)))
            bloom_layer = bloom_layer.filter(ImageFilter.GaussianBlur(radius=28))
            img = Image.alpha_composite(img, bloom_layer)
            draw = ImageDraw.Draw(img)

        # Anamorphic Specular Gleam Sweep (frames 11 to 24)
        if 11 <= f <= 24:
            sweep_p = (f - 11) / 13.0
            beam_x = int(cx - cur_emblem_w * 0.7 + (cur_emblem_w * 1.4 * sweep_p))
            gleam_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            gl_draw = ImageDraw.Draw(gleam_layer)
            # Diagonal beam at 45 degrees
            gl_draw.line(
                (beam_x - 120, cy + cur_emblem_w // 2, beam_x + 120, cy - cur_emblem_w // 2),
                fill=(255, 230, 180, int(90 * math.sin(math.pi * sweep_p))),
                width=16,
            )
            gleam_layer = gleam_layer.filter(ImageFilter.GaussianBlur(radius=12))
            img = Image.alpha_composite(img, gleam_layer)
            draw = ImageDraw.Draw(img)

        # Kinetic Tracked Typography
        if f >= 12:
            text_p = min(1.0, (f - 12) / 12.0)
            text_alpha = int(255 * alpha * text_p)
            title_text, _ = _channel_labels()
            bbox = draw.textbbox((0, 0), title_text, font=font_title)
            tw = bbox[2] - bbox[0]
            tx = cx - tw // 2
            ty = cy + (cur_emblem_w // 2) + 40
            draw.text((tx, ty), title_text, fill=(245, 245, 250, text_alpha), font=font_title)

            sub_text = "THE MIND PROTOCOL"
            sub_bbox = draw.textbbox((0, 0), sub_text, font=font_sub)
            sw = sub_bbox[2] - sub_bbox[0]
            sx = cx - sw // 2
            sy = ty + 68
            draw.text((sx, sy), sub_text, fill=(255, 185, 35, int(180 * alpha * text_p)), font=font_sub)

        # 35mm grain overlay
        grain = rng.randint(-8, 8, (height, width, 1), dtype=np.int16)
        arr = np.array(img, dtype=np.int16)
        arr[:, :, :3] = np.clip(arr[:, :, :3] + grain, 0, 255)
        final_frame = Image.fromarray(arr.astype(np.uint8), mode="RGBA").convert("RGB")

        frame_path = os.path.join(temp_dir, f"frame_{f:04d}.png")
        final_frame.save(frame_path, "PNG")

    # Encode with FFmpeg
    vcodec = ["-c:v", "h264_videotoolbox", "-b:v", "14M"] if sys.platform == "darwin" else ["-c:v", "libx264", "-crf", "16"]
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", os.path.join(temp_dir, "frame_%04d.png"),
        "-i", audio_wav,
        *vcodec,
        *COLOR_FLAGS,
        *AUDIO_FLAGS,
        "-c:a", "aac",
        "-b:a", "320k",
        "-ar", "48000",
        "-shortest",
        output_mp4
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    shutil.rmtree(temp_dir, ignore_errors=True)
    print(f"Generated SOTA Intro: {output_mp4}")

def render_outro_endscreen(width: int, height: int, output_mp4: str, duration: float = 15.0):
    """Renders 15.0s YouTube End Screen Master with official safe-zone target slots."""
    temp_dir = tempfile.mkdtemp(prefix="outro_render_")
    total_frames = int(FPS * duration)

    avatar_3d_path = os.path.join(ASSETS_DIR, "avatar_3d_labyrinth_800x800.png")
    avatar_2d_path = os.path.join(ASSETS_DIR, "avatar_labyrinth_800x800.png")
    chosen_avatar_path = avatar_3d_path if os.path.exists(avatar_3d_path) else avatar_2d_path
    avatar = Image.open(chosen_avatar_path).convert("RGBA") if os.path.exists(chosen_avatar_path) else None

    audio_wav = os.path.join(temp_dir, "outro_audio.wav")
    synthesize_outro_audio(audio_wav, duration)

    font_title = get_font(34, bold=True)
    font_body = get_font(20, bold=False)
    font_btn = get_font(22, bold=True)

    rng = np.random.RandomState(99)

    print(f"Rendering {total_frames} frames for 15s YouTube End Screen ({width}x{height})...")

    # Target Slots (Official YouTube End Screen Safe Bounds)
    # Left slot: Next Recommended Video (16:9 ratio, width 640 x height 360)
    # Right slot: Subscribe Avatar (circle radius 110px)
    vid_box = [width - 760, 260, width - 120, 620] # (x1, y1, x2, y2)
    sub_center = (420, 440)
    sub_radius = 110

    for f in range(total_frames):
        t = f / FPS
        img = Image.new("RGBA", (width, height), (8, 9, 12, 255))
        draw = ImageDraw.Draw(img)

        # Global Opacity Envelope (Fade in 0..15 frames, Fade out last 30 frames)
        if f < 15:
            alpha = f / 15.0
        elif f > (total_frames - 30):
            alpha = max(0.0, (total_frames - f) / 30.0)
        else:
            alpha = 1.0

        # Background subtle moving cyan/amber gradient aura
        aura_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        a_draw = ImageDraw.Draw(aura_layer)
        aura_x = int(width * 0.45 + 50 * math.sin(t * 0.4))
        aura_y = int(height * 0.50 + 30 * math.cos(t * 0.3))
        a_draw.ellipse((aura_x - 450, aura_y - 300, aura_x + 450, aura_y + 300),
                       fill=(0, 229, 255, int(18 * alpha)))
        a_draw.ellipse((sub_center[0] - 220, sub_center[1] - 220, sub_center[0] + 220, sub_center[1] + 220),
                       fill=(255, 185, 35, int(14 * alpha)))
        aura_layer = aura_layer.filter(ImageFilter.GaussianBlur(radius=55))
        img = Image.alpha_composite(img, aura_layer)
        draw = ImageDraw.Draw(img)

        # Top Header Brand
        header_text = "UPGRADE YOUR MENTAL OPERATING SYSTEM"
        h_bbox = draw.textbbox((0, 0), header_text, font=font_title)
        hw = h_bbox[2] - h_bbox[0]
        hx = (width - hw) // 2
        hy = 110
        draw.text((hx, hy), header_text, fill=(245, 245, 250, int(240 * alpha)), font=font_title)

        sub_head = "SCIENCE-GROUNDED BEHAVIORAL PROTOCOLS"
        sh_bbox = draw.textbbox((0, 0), sub_head, font=font_body)
        shw = sh_bbox[2] - sh_bbox[0]
        draw.text(((width - shw) // 2, hy + 50), sub_head, fill=(0, 229, 255, int(200 * alpha)), font=font_body)

        # 1. Video Element Placeholder Box (YouTube End Screen Slot)
        x1, y1, x2, y2 = vid_box
        draw.rectangle([x1, y1, x2, y2], fill=(14, 16, 22, int(200 * alpha)),
                       outline=(0, 229, 255, int(160 * alpha)), width=3)
        v_title = "RECOMMENDED NEXT DEEP DIVE"
        v_bbox = draw.textbbox((0, 0), v_title, font=font_btn)
        draw.text((x1 + (x2 - x1 - (v_bbox[2] - v_bbox[0])) // 2, y1 + 160),
                  v_title, fill=(240, 240, 245, int(190 * alpha)), font=font_btn)
        draw.text((x1 + 30, y1 + 30), "NEXT PROTOCOL ➔", font=font_body, fill=(255, 185, 35, int(220 * alpha)))

        # 2. Subscribe Avatar Slot
        scx, scy = sub_center
        # Animated pulsing golden ring
        pulse_r = sub_radius + 12 + 6 * math.sin(t * 3.0)
        draw.ellipse((scx - pulse_r, scy - pulse_r, scx + pulse_r, scy + pulse_r),
                     outline=(255, 185, 35, int(130 * alpha)), width=2)
        
        if avatar:
            sub_av = avatar.resize((sub_radius * 2, sub_radius * 2), Image.Resampling.LANCZOS)
            img.paste(sub_av, (scx - sub_radius, scy - sub_radius), mask=sub_av)

        _, s_name = _channel_labels()
        sn_bbox = draw.textbbox((0, 0), s_name, font=font_body)
        draw.text((scx - (sn_bbox[2] - sn_bbox[0]) // 2, scy + sub_radius + 28),
                  s_name, fill=(245, 245, 250, int(230 * alpha)), font=font_body)

        # Subscribe Pill Button
        btn_w, btn_h = 180, 46
        bx1 = scx - btn_w // 2
        by1 = scy + sub_radius + 68
        draw.rounded_rectangle([bx1, by1, bx1 + btn_w, by1 + btn_h], radius=23,
                               fill=(255, 23, 68, int(230 * alpha)))
        btn_txt = "SUBSCRIBE"
        bt_bbox = draw.textbbox((0, 0), btn_txt, font=font_btn)
        draw.text((bx1 + (btn_w - (bt_bbox[2] - bt_bbox[0])) // 2, by1 + 10),
                  btn_txt, fill=(255, 255, 255, int(255 * alpha)), font=font_btn)

        # 35mm grain
        grain = rng.randint(-7, 7, (height, width, 1), dtype=np.int16)
        arr = np.array(img, dtype=np.int16)
        arr[:, :, :3] = np.clip(arr[:, :, :3] + grain, 0, 255)
        final_frame = Image.fromarray(arr.astype(np.uint8), mode="RGBA").convert("RGB")

        frame_path = os.path.join(temp_dir, f"frame_{f:04d}.png")
        final_frame.save(frame_path, "PNG")

    # Encode with FFmpeg
    vcodec = ["-c:v", "h264_videotoolbox", "-b:v", "14M"] if sys.platform == "darwin" else ["-c:v", "libx264", "-crf", "16"]
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", os.path.join(temp_dir, "frame_%04d.png"),
        "-i", audio_wav,
        *vcodec,
        *COLOR_FLAGS,
        *AUDIO_FLAGS,
        "-c:a", "aac",
        "-b:a", "320k",
        "-ar", "48000",
        "-shortest",
        output_mp4
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    shutil.rmtree(temp_dir, ignore_errors=True)
    print(f"Generated SOTA End Screen Outro: {output_mp4}")

def render_shorts_outro_loop(width: int, height: int, output_mp4: str, duration: float = 2.5):
    """Renders 2.5s Shorts Infinite Loop Bridge formatted for 9:16 safe zones."""
    temp_dir = tempfile.mkdtemp(prefix="shorts_outro_")
    total_frames = int(FPS * duration)

    avatar_3d_path = os.path.join(ASSETS_DIR, "avatar_3d_labyrinth_800x800.png")
    avatar_2d_path = os.path.join(ASSETS_DIR, "avatar_labyrinth_800x800.png")
    chosen_avatar_path = avatar_3d_path if os.path.exists(avatar_3d_path) else avatar_2d_path
    avatar = Image.open(chosen_avatar_path).convert("RGBA") if os.path.exists(chosen_avatar_path) else None

    audio_wav = os.path.join(temp_dir, "shorts_loop_audio.wav")
    synthesize_outro_audio(audio_wav, duration)

    font_title = get_font(42, bold=True)
    font_sub = get_font(24, bold=False)

    cx = width // 2
    # Center safe zone (38% to 54% frame height)
    cy = int(height * 0.44)
    emblem_size = 280

    rng = np.random.RandomState(77)

    for f in range(total_frames):
        t = f / FPS
        img = Image.new("RGBA", (width, height), (8, 9, 12, 255))
        draw = ImageDraw.Draw(img)

        # Pulse scale
        scale = 1.0 + 0.03 * math.sin(t * 3.5)
        cur_size = int(emblem_size * scale)

        # Draw central avatar
        if avatar:
            av_scaled = avatar.resize((cur_size, cur_size), Image.Resampling.LANCZOS)
            img.paste(av_scaled, (cx - cur_size // 2, cy - cur_size // 2), mask=av_scaled)

        # Animated cyan pulse ring around avatar
        pulse_r = (cur_size // 2) + 16 + int(8 * math.sin(t * 4.0))
        draw.ellipse((cx - pulse_r, cy - pulse_r, cx + pulse_r, cy + pulse_r),
                     outline=(0, 229, 255, 140), width=2)

        # Tagline in safe zone
        t_text, s_text = _channel_labels()
        tb = draw.textbbox((0, 0), t_text, font=font_title)
        draw.text((cx - (tb[2] - tb[0]) // 2, cy + cur_size // 2 + 35),
                  t_text, fill=(245, 245, 250, 240), font=font_title)

        sb = draw.textbbox((0, 0), s_text, font=font_sub)
        draw.text((cx - (sb[2] - sb[0]) // 2, cy + cur_size // 2 + 88),
                  s_text, fill=(255, 185, 35, 210), font=font_sub)

        # 35mm grain
        grain = rng.randint(-8, 8, (height, width, 1), dtype=np.int16)
        arr = np.array(img, dtype=np.int16)
        arr[:, :, :3] = np.clip(arr[:, :, :3] + grain, 0, 255)
        final_frame = Image.fromarray(arr.astype(np.uint8), mode="RGBA").convert("RGB")

        frame_path = os.path.join(temp_dir, f"frame_{f:04d}.png")
        final_frame.save(frame_path, "PNG")

    vcodec = ["-c:v", "h264_videotoolbox", "-b:v", "14M"] if sys.platform == "darwin" else ["-c:v", "libx264", "-crf", "16"]
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", os.path.join(temp_dir, "frame_%04d.png"),
        "-i", audio_wav,
        *vcodec,
        *COLOR_FLAGS,
        *AUDIO_FLAGS,
        "-c:a", "aac",
        "-b:a", "320k",
        "-ar", "48000",
        "-shortest",
        output_mp4
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    shutil.rmtree(temp_dir, ignore_errors=True)
    print(f"Generated SOTA Shorts Outro Loop: {output_mp4}")

def measure_master(path: str) -> str:
    """Print the colour metadata and loudness a master actually carries.

    The module docstring used to assert -14 LUFS for files that measured -18. Measuring after the
    render means the log reports the file rather than the intention, and a regressional encoder edit
    shows up as a number instead of a silent claim.
    """
    if not os.path.exists(path):
        return "MISSING"
    probe = run_process(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=pix_fmt,color_range,color_space", "-of", "csv=p=0", path],
        capture_output=True, text=True, timeout_s=PROBE_TIMEOUT_S,
    ).stdout.strip()
    loud = run_process(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af",
         "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True, timeout_s=MEDIA_TIMEOUT_S,
    ).stderr
    found = re.findall(r'"input_(i|tp)"\s*:\s*"(-?[\d.]+)"', loud)
    lufs = tp = "?"
    for key, val in found:
        if key == "i":
            lufs = val
        elif key == "tp":
            tp = val
    return f"{probe or 'no colour tags'} | {lufs} LUFS | {tp} dBTP"


def render_longform_thumbnail(
    title: str,
    subtitle: str,
    output_png: str,
    width: int = 1280,
    height: int = 720,
) -> str:
    """Render a 16:9 long-form thumbnail template (Shorts remain frame-based by design)."""
    img = Image.new("RGBA", (width, height), (8, 9, 12, 255))
    aura = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ad = ImageDraw.Draw(aura)
    ad.ellipse((int(width * 0.52), int(height * 0.12), int(width * 0.96), int(height * 0.88)), fill=(0, 229, 255, 42))
    ad.ellipse((int(width * 0.06), int(height * 0.18), int(width * 0.48), int(height * 0.84)), fill=(255, 200, 61, 34))
    aura = aura.filter(ImageFilter.GaussianBlur(radius=48))
    img = Image.alpha_composite(img, aura)
    draw = ImageDraw.Draw(img)

    safe_margin_x, safe_margin_y = int(width * 0.06), int(height * 0.08)
    font_badge = get_font(24, bold=True)
    font_title = get_font(68, bold=True)
    font_sub = get_font(32, bold=False)

    ch_upper, _ = _channel_labels()
    badge_txt = f"{ch_upper} // DEEP DIVE"
    draw.rounded_rectangle(
        (safe_margin_x, safe_margin_y, safe_margin_x + 420, safe_margin_y + 48),
        radius=12,
        fill=(18, 24, 36, 235),
        outline=(0, 229, 255, 220),
        width=2,
    )
    draw.text((safe_margin_x + 20, safe_margin_y + 10), badge_txt, fill=(0, 229, 255, 255), font=font_badge)

    max_text_w = int(width * 0.82)
    words = title.upper().split()
    lines, cur = [], []
    for w in words:
        trial = " ".join(cur + [w])
        bbox = draw.textbbox((0, 0), trial, font=font_title)
        if (bbox[2] - bbox[0]) > max_text_w and cur:
            lines.append(" ".join(cur))
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(" ".join(cur))

    y_cursor = safe_margin_y + 92
    for idx, ln in enumerate(lines[:3]):
        col = (255, 200, 61, 255) if idx == 0 else (245, 247, 252, 255)
        draw.text((safe_margin_x, y_cursor), ln, fill=col, font=font_title)
        y_cursor += 84

    draw.text((safe_margin_x, min(height - safe_margin_y - 52, y_cursor + 24)), subtitle, fill=(108, 232, 222, 240), font=font_sub)

    os.makedirs(os.path.dirname(os.path.abspath(output_png)), exist_ok=True)
    img.convert("RGB").save(output_png, "PNG")
    return output_png


def run_branding_check():
    print("\n[Branding masters - measured, not assumed]")
    for name in ("intro_16x9", "intro_9x16", "outro_16x9_endscreen", "outro_9x16_loop"):
        path = os.path.join(ASSETS_DIR, f"{name}.mp4")
        print(f"  {name:<24} {measure_master(path)}")


def main():
    os.makedirs(ASSETS_DIR, exist_ok=True)
    # 1. Long-form 16:9 Intro (2.5s)
    intro_16x9 = os.path.join(ASSETS_DIR, "intro_16x9.mp4")
    render_intro_video(1920, 1080, intro_16x9, duration=2.5)

    # 2. Shorts 9:16 Intro (2.0s)
    intro_9x16 = os.path.join(ASSETS_DIR, "intro_9x16.mp4")
    render_intro_video(1080, 1920, intro_9x16, duration=2.0)

    # 3. Long-form 16:9 Outro End Screen (15.0s)
    outro_16x9 = os.path.join(ASSETS_DIR, "outro_16x9_endscreen.mp4")
    render_outro_endscreen(1920, 1080, outro_16x9, duration=15.0)

    # 4. Shorts 9:16 Outro Loop Bridge (2.5s)
    outro_9x16 = os.path.join(ASSETS_DIR, "outro_9x16_loop.mp4")
    render_shorts_outro_loop(1080, 1920, outro_9x16, duration=2.5)

    print("\nAll Master Intro & Outro assets rendered successfully.")
    run_branding_check()

if __name__ == "__main__":
    main()
