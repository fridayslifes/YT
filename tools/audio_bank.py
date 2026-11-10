#!/usr/bin/env python3
"""FrameForge Studio Foley & Organic Sound Bank (v5.0 — Zero Pitchy Sine Sweeps).

Fixes the "pitchy / whistle" scene transition artifact:
  - Previously, `whoosh.wav` mixed a 90Hz->350Hz sine-wave frequency sweep (`math.sin(ph) * 0.35`)
    and `pop.wav` used a 220Hz->640Hz sine sweep, which sounded like a synthetic laser/whistle on every cut.
  - Now, all transition sounds use 100% non-tonal, multi-stage low-pass filtered velvet brown noise
    paired with a deep, warm 48Hz sub-bass felt thud (zero high-pitched sine sweeps, zero whistle).
"""

from __future__ import annotations

import array
import math
import random
import wave
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
YT_ROOT = TOOLS_DIR.parent
SFX_DIR = YT_ROOT / "assets" / "audio" / "sfx"
BGM_DIR = YT_ROOT / "assets" / "audio" / "bgm"
SR = 44100


def _write_stereo_pcm(path: Path, left: list[float], right: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = min(len(left), len(right))
    buf = array.array("h", [0] * (n * 2))
    for i in range(n):
        l_val = max(-1.0, min(1.0, left[i]))
        r_val = max(-1.0, min(1.0, right[i]))
        buf[2 * i] = int(l_val * 32767.0)
        buf[2 * i + 1] = int(r_val * 32767.0)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(buf.tobytes())


def ensure_studio_sfx_pack(try_remote_cc0: bool = False, force_rebuild: bool = False) -> dict[str, str]:
    """Ensure all warm, non-pitchy studio Foley WAVs exist in assets/audio/sfx/."""
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    status: dict[str, str] = {}
    rng = random.Random(2026)

    # 1. shutter.wav / click.wav (Warm low-mid mechanical film frame thud, no high-frequency beep)
    for cname in ("shutter", "click"):
        p = SFX_DIR / f"{cname}.wav"
        if force_rebuild or not p.exists() or p.stat().st_size < 1024:
            n = int(0.11 * SR)
            left, right = [0.0] * n, [0.0] * n
            lp_l, lp_r = 0.0, 0.0
            for i in range(n):
                t = i / SR
                # Deep mechanical body (85Hz) + soft filtered air transient
                body = math.sin(2 * math.pi * 85.0 * t) * math.exp(-t / 0.018)
                raw_n = rng.gauss(0.0, 0.5) * math.exp(-t / 0.006)
                lp_l = 0.82 * lp_l + 0.18 * raw_n
                lp_r = 0.82 * lp_r + 0.18 * raw_n * 0.95
                left[i] = math.tanh((0.75 * body + 0.45 * lp_l) * 1.4) * 0.70
                right[i] = math.tanh((0.75 * body + 0.45 * lp_r) * 1.4) * 0.70
            _write_stereo_pcm(p, left, right)
            status[cname] = "rebuilt_warm"
        else:
            status[cname] = "cached"

    # 2. pop.wav / bubble.wav (Subtle, warm muted sub-tap at 95Hz — zero high-pitch chirp)
    for pname in ("pop", "bubble"):
        p = SFX_DIR / f"{pname}.wav"
        if force_rebuild or not p.exists() or p.stat().st_size < 1024:
            n = int(0.07 * SR)
            left, right = [0.0] * n, [0.0] * n
            for i in range(n):
                t = i / SR
                env = math.sin(math.pi * min(1.0, t / 0.005)) * math.exp(-t / 0.018)
                # Warm fixed 92Hz chest tap (no upward pitch sweep)
                tap = math.sin(2 * math.pi * 92.0 * t) * env * 0.45
                left[i] = tap
                right[i] = tap
            _write_stereo_pcm(p, left, right)
            status[pname] = "rebuilt_warm"
        else:
            status[pname] = "cached"

    # 3. chime.wav / bell.wav (Warm low cinematic piano/cello fifth — 220Hz A3 + 330Hz E4, no piercing high frequencies)
    for bname in ("chime", "bell"):
        p = SFX_DIR / f"{bname}.wav"
        if force_rebuild or not p.exists() or p.stat().st_size < 1024:
            n = int(0.65 * SR)
            left, right = [0.0] * n, [0.0] * n
            for i in range(n):
                t = i / SR
                att = min(1.0, t / 0.012)
                left[i] = att * 0.55 * (
                    0.65 * math.sin(2 * math.pi * 220.0 * t) * math.exp(-t / 0.24)
                    + 0.35 * math.sin(2 * math.pi * 329.6 * t) * math.exp(-t / 0.18)
                )
                right[i] = att * 0.55 * (
                    0.65 * math.sin(2 * math.pi * 220.4 * t + 0.3) * math.exp(-t / 0.24)
                    + 0.35 * math.sin(2 * math.pi * 330.0 * t + 0.6) * math.exp(-t / 0.18)
                )
            _write_stereo_pcm(p, left, right)
            status[bname] = "rebuilt_warm"
        else:
            status[bname] = "cached"

    # 4. whoosh.wav (100% Non-Tonal Deep Velvet Air Movement + 48Hz Felt Thud — ZERO pitch sweep)
    p_whoosh = SFX_DIR / "whoosh.wav"
    if force_rebuild or not p_whoosh.exists() or p_whoosh.stat().st_size < 1024:
        n = int(0.36 * SR)
        left, right = [0.0] * n, [0.0] * n
        peak_t = 0.18
        # 3-pole cascade low-pass filter state for ultra-smooth dark brown noise (cuts all harshness > 450Hz)
        b1_l = b2_l = b3_l = 0.0
        b1_r = b2_r = b3_r = 0.0
        for i in range(n):
            t = i / SR
            env = math.sin(math.pi * (t / 0.36)) ** 2.2
            # Deep 3-stage low-passed brown noise (pure dark air, zero sine whistle)
            w_l = rng.gauss(0.0, 0.6)
            w_r = rng.gauss(0.0, 0.6)
            b1_l = 0.93 * b1_l + 0.07 * w_l
            b2_l = 0.93 * b2_l + 0.07 * b1_l
            b3_l = 0.93 * b3_l + 0.07 * b2_l

            b1_r = 0.93 * b1_r + 0.07 * w_r
            b2_r = 0.93 * b2_r + 0.07 * b1_r
            b3_r = 0.93 * b3_r + 0.07 * b2_r

            # Subtle 50Hz felt sub-thud at center of cut
            dt = abs(t - peak_t)
            sub_thud = math.sin(2 * math.pi * 50.0 * t) * math.exp(-dt / 0.045) * 0.28

            pan = i / max(1, n - 1)
            left[i] = (b3_l * 1.8 * (0.75 - 0.30 * pan) + sub_thud) * env * 0.55
            right[i] = (b3_r * 1.8 * (0.45 + 0.30 * pan) + sub_thud) * env * 0.55
        _write_stereo_pcm(p_whoosh, left, right)
        status["whoosh"] = "rebuilt_warm"
    else:
        status["whoosh"] = "cached"

    # 5. boom.wav / impact.wav (Warm Cinema Sub-Bass Drop 40Hz-65Hz)
    for iname in ("boom", "impact"):
        p = SFX_DIR / f"{iname}.wav"
        if force_rebuild or not p.exists() or p.stat().st_size < 1024:
            n = int(1.1 * SR)
            left, right = [0.0] * n, [0.0] * n
            ph = 0.0
            for i in range(n):
                t = i / SR
                f_sweep = 38.0 + 32.0 * math.exp(-t / 0.20)
                ph += 2.0 * math.pi * f_sweep / SR
                sub = 0.75 * math.sin(ph) + 0.25 * math.sin(2.0 * ph)
                env = min(1.0, t / 0.010) * math.exp(-t / 0.40)
                sig = math.tanh(sub * env * 1.4) * 0.80
                left[i] = sig
                right[i] = sig
            _write_stereo_pcm(p, left, right)
            status[iname] = "rebuilt_warm"
        else:
            status[iname] = "cached"

    return status


if __name__ == "__main__":
    import json
    print(json.dumps(ensure_studio_sfx_pack(force_rebuild=True), indent=2))
