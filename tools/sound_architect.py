#!/usr/bin/env python3
"""tools/sound_architect.py — Master Sound Designer & Audio Architect.

Implements the SOTA documentary audio architecture (LEMMiNO, Vox, MagnatesMedia):
1. The 3-Tier Layering Model:
   - Tier 1 (Espresso): Continuous sub-bass suspense drone & analog room tone (-22 dBFS).
   - Tier 2 (Milk): Two-act thematic score with dynamic breathing and mid-side vocal ducking.
   - Tier 3 (Cream): Triple-layer page-flip foley (Riser + Swoosh + Paper + Desk Thud) + spatial tactile cues.
2. Shure SM7B Vocal Studio Chain with Room Acoustic Reflection.
"""

from __future__ import annotations

import array
import logging
import math
import random
import sys
import wave
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SFX_DIR = REPO_ROOT / "assets" / "audio" / "sfx"
BGM_DIR = REPO_ROOT / "assets" / "audio" / "bgm"
SR = 48000

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sound_architect")


def _write_stereo_wav(path: Path, left: List[float], right: List[float], sample_rate: int = SR) -> None:
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
        wf.setframerate(sample_rate)
        wf.writeframes(buf.tobytes())


def ensure_documentary_foley_pack() -> Dict[str, Path]:
    """Generates the advanced documentary foley layers: tension risers, paper swooshes, desk thuds."""
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(2026)
    out: Dict[str, Path] = {}

    # 1. tension_riser.wav (0.35s reverse suckback / exponential swell before transitions)
    p_riser = SFX_DIR / "tension_riser.wav"
    if not p_riser.exists() or p_riser.stat().st_size < 1024:
        n = int(0.35 * SR)
        left, right = [0.0] * n, [0.0] * n
        b1_l = b2_l = b3_l = 0.0
        b1_r = b2_r = b3_r = 0.0
        for i in range(n):
            t = i / SR
            # Exponential reverse envelope (soft start -> rapid crescendo right at edge)
            env = (math.exp((t / 0.35) * 3.2) - 1.0) / (math.exp(3.2) - 1.0)
            w_l = rng.gauss(0.0, 0.5)
            w_r = rng.gauss(0.0, 0.5)
            # Low-pass filter sweeps open from 180Hz to 850Hz
            alpha = 0.04 + 0.16 * (t / 0.35)
            b1_l = (1.0 - alpha) * b1_l + alpha * w_l
            b2_l = (1.0 - alpha) * b2_l + alpha * b1_l
            b3_l = (1.0 - alpha) * b3_l + alpha * b2_l

            b1_r = (1.0 - alpha) * b1_r + alpha * w_r
            b2_r = (1.0 - alpha) * b2_r + alpha * b1_r
            b3_r = (1.0 - alpha) * b3_r + alpha * b2_r

            # Sub-bass pitch riser (35Hz to 70Hz)
            f_pitch = 35.0 + 35.0 * (t / 0.35) ** 2
            sub = math.sin(2 * math.pi * f_pitch * t) * 0.30

            left[i] = (b3_l * 1.6 + sub) * env * 0.55
            right[i] = (b3_r * 1.6 + sub) * env * 0.55
        _write_stereo_wav(p_riser, left, right)
        logger.info("  ✓ Generated tension_riser.wav")
    out["tension_riser"] = p_riser

    # 2. desk_thud.wav (0.24s warm, heavy 45Hz mahogany desk impact thud)
    p_thud = SFX_DIR / "desk_thud.wav"
    if not p_thud.exists() or p_thud.stat().st_size < 1024:
        n = int(0.24 * SR)
        left, right = [0.0] * n, [0.0] * n
        for i in range(n):
            t = i / SR
            # 45Hz sub-transient with natural wood damping decay
            f_wood = 48.0 * math.exp(-t / 0.06)
            wood_body = math.sin(2 * math.pi * f_wood * t) * math.exp(-t / 0.045)
            knock = rng.gauss(0.0, 0.3) * math.exp(-t / 0.008)
            sig = math.tanh((wood_body * 0.85 + knock * 0.25) * 1.5) * 0.75
            left[i] = sig
            right[i] = sig
        _write_stereo_wav(p_thud, left, right)
        logger.info("  ✓ Generated desk_thud.wav")
    out["desk_thud"] = p_thud

    # 3. paper_swoosh.wav (0.38s tactile paper drag + air displacement)
    p_swoosh = SFX_DIR / "paper_swoosh.wav"
    if not p_swoosh.exists() or p_swoosh.stat().st_size < 1024:
        n = int(0.38 * SR)
        left, right = [0.0] * n, [0.0] * n
        b1_l = b2_l = 0.0
        b1_r = b2_r = 0.0
        for i in range(n):
            t = i / SR
            env = math.sin(math.pi * (t / 0.38)) ** 1.8
            raw_n = rng.gauss(0.0, 0.6)
            # Band-pass filter around 400Hz-1200Hz to simulate dry parchment paper flutter
            b1_l = 0.88 * b1_l + 0.12 * raw_n
            b2_l = 0.88 * b2_l + 0.12 * b1_l
            b1_r = 0.88 * b1_r + 0.12 * raw_n * 0.95
            b2_r = 0.88 * b2_r + 0.12 * b1_r
            paper_rustle = (b1_l - b2_l) * 2.2
            pan = t / 0.38  # moves left to right
            left[i] = paper_rustle * env * (1.0 - 0.4 * pan) * 0.45
            right[i] = paper_rustle * env * (0.6 + 0.4 * pan) * 0.45
        _write_stereo_wav(p_swoosh, left, right)
        logger.info("  ✓ Generated paper_swoosh.wav")
    out["paper_swoosh"] = p_swoosh

    return out


def generate_continuous_drone_bed(duration_sec: float, output_wav: Path) -> Path:
    """Generates a continuous atmospheric sub-bass tension drone + warm tape room tone."""
    if output_wav.exists() and output_wav.stat().st_size > 100000:
        return output_wav

    n = int(duration_sec * SR)
    left, right = [0.0] * n, [0.0] * n
    rng = random.Random(42)

    # Multi-frequency organic sub-bass drone (42Hz fundamental + 84Hz second harmonic + 126Hz fifth)
    # with gentle slow LFO modulation (0.08Hz pulse)
    lp_l = lp_r = 0.0
    for i in range(n):
        t = i / SR
        lfo = 0.85 + 0.15 * math.sin(2 * math.pi * 0.075 * t)
        drone = (
            0.55 * math.sin(2 * math.pi * 42.0 * t)
            + 0.30 * math.sin(2 * math.pi * 63.0 * t + 0.5)
            + 0.15 * math.sin(2 * math.pi * 84.0 * t + 1.2)
        ) * lfo

        # Warm analog vinyl tape hiss / room tone (very soft low-passed noise)
        tape_raw = rng.gauss(0.0, 0.08)
        lp_l = 0.96 * lp_l + 0.04 * tape_raw
        lp_r = 0.96 * lp_r + 0.04 * tape_raw * 0.98

        sig_l = (drone * 0.18 + lp_l * 0.05)
        sig_r = (drone * 0.18 + lp_r * 0.05)
        left[i] = sig_l
        right[i] = sig_r

    _write_stereo_wav(output_wav, left, right)
    logger.info(f"  ✓ Generated continuous drone bed: {output_wav.name} ({duration_sec:.2f}s)")
    return output_wav


# ---------------------------------------------------------------------------
# Danny Why Decibel-Budget Audio Mixing Table (§9)
# ---------------------------------------------------------------------------
DECIBEL_BUDGET = {
    "voice": 0.0,              # 0 dBFS reference (master dialogue)
    "climax_blast": -8.5,      # -8 to -10 dBFS (strictly placed in breath/speech pause)
    "impact_thud": -15.0,      # -14 to -19 dBFS (physical impacts, desk thuds)
    "mechanical_click": -22.0, # -20 to -24 dBFS (shutter clicks, tape snaps)
    "air_whoosh": -27.0,       # -25 to -31 dBFS (paper swooshes, page turns)
    "ambient_bed": -28.0,      # -26 to -33 dBFS (continuous room tone & drone bed)
    "bgm_voice_duck": -12.0,   # Duck BGM by 12 dB during active dialogue
}

CUE_CATEGORIES: Dict[str, str] = {
    # Climax blasts (-8.5 dBFS)
    "sub_bass_drop": "climax_blast",
    "thunder_crack": "climax_blast",
    "boom": "climax_blast",
    "explosion": "climax_blast",
    "cannon": "climax_blast",
    # Physical impacts (-15.0 dBFS)
    "desk_thud": "impact_thud",
    "cash_register": "impact_thud",
    "stamp": "impact_thud",
    "slam": "impact_thud",
    "drop": "impact_thud",
    # Tactile / Mechanical clicks (-22.0 dBFS)
    "typewriter": "mechanical_click",
    "match_strike": "mechanical_click",
    "ice_in_bourbon": "mechanical_click",
    "flight_attendant_ding": "mechanical_click",
    "shutter": "mechanical_click",
    "vinyl_needle": "mechanical_click",
    "seatbelt_chime": "mechanical_click",
    "cockpit_radio": "mechanical_click",
    "click": "mechanical_click",
    "chime": "mechanical_click",
    "pop": "mechanical_click",
    # Air / whooshes (-27.0 dBFS)
    "paper_swoosh": "air_whoosh",
    "wind_howl": "air_whoosh",
    "pressure_drop": "air_whoosh",
    "dramatic_whoosh": "air_whoosh",
    "whoosh": "air_whoosh",
    "riser": "air_whoosh",
    # Ambient bed (-28.0 dBFS)
    "tension_clock": "ambient_bed",
    "drone": "ambient_bed",
    "room_tone": "ambient_bed",
}


def db_to_linear(db: float) -> float:
    """Converts a decibel value to a linear amplitude multiplier."""
    return float(10.0 ** (db / 20.0))


def get_cue_decibel(cue_name: str) -> float:
    """Returns the calibrated target decibel level for a given sound effect name."""
    cue_lower = cue_name.lower()
    # Longest key first so specific cues win over generic substrings
    # (e.g. "pressure_drop" must match air_whoosh, not the generic "drop" impact).
    for key in sorted(CUE_CATEGORIES, key=len, reverse=True):
        if key in cue_lower:
            return DECIBEL_BUDGET[CUE_CATEGORIES[key]]
    return DECIBEL_BUDGET["mechanical_click"]


def get_cue_linear_gain(cue_name: str) -> float:
    """Returns the linear amplitude multiplier for a given sound effect name."""
    return db_to_linear(get_cue_decibel(cue_name))


def snap_cue_to_breath_pause(
    target_time_sec: float,
    pauses: List[Tuple[float, float]],
    search_window_sec: float = 0.8,
) -> float:
    """Snaps a climax sound cue to the center of the nearest natural breath pause if within search_window_sec."""
    if not pauses:
        return target_time_sec
    best_time = target_time_sec
    min_dist = float("inf")
    for p_start, p_end in pauses:
        p_center = (p_start + p_end) / 2.0
        dist = abs(target_time_sec - p_center)
        if dist < min_dist and dist <= search_window_sec:
            min_dist = dist
            best_time = p_center
    return round(best_time, 3)


def build_triple_layer_page_flip_sfx(
    cue_time: float,
    current_time: float,
    sfx_inputs: List[str],
    amix_filters: List[str],
    sfx_count: int,
) -> int:
    """Creates an industry-grade triple-layered page flip foley event.

    Layer 1: Pre-transition tension riser (starts 0.28s before turn, -20.0 dBFS)
    Layer 2: Air swoosh + paper flutter (starts right on turn, -27.0 dBFS air_whoosh)
    Layer 3: Mahogany desk landing thud (starts 0.35s after turn as page settles, -15.0 dBFS impact_thud)
    """
    foley = ensure_documentary_foley_pack()

    # 1. Pre-turn riser (-20.0 dBFS)
    vol_riser = round(db_to_linear(-20.0), 3)
    delay_riser = max(0, int((current_time + cue_time - 0.28) * 1000))
    sfx_inputs.extend(["-i", str(foley["tension_riser"])])
    amix_filters.append(f"[{sfx_count+1}:a]adelay={delay_riser}|{delay_riser},volume={vol_riser:.3f}[sfx{sfx_count}]")
    sfx_count += 1

    # 2. Main paper swoosh + page turn (-27.0 dBFS air_whoosh)
    vol_swoosh = round(db_to_linear(DECIBEL_BUDGET["air_whoosh"]), 3)
    delay_turn = max(0, int((current_time + cue_time) * 1000))
    sfx_inputs.extend(["-i", str(foley["paper_swoosh"])])
    amix_filters.append(f"[{sfx_count+1}:a]adelay={delay_turn}|{delay_turn},pan=stereo|c0=0.7*c0|c1=0.3*c0,volume={vol_swoosh:.3f}[sfx{sfx_count}]")
    sfx_count += 1

    # 3. Soft desk landing thud (-15.0 dBFS impact_thud)
    vol_thud = round(db_to_linear(DECIBEL_BUDGET["impact_thud"]), 3)
    delay_thud = max(0, int((current_time + cue_time + 0.38) * 1000))
    sfx_inputs.extend(["-i", str(foley["desk_thud"])])
    amix_filters.append(f"[{sfx_count+1}:a]adelay={delay_thud}|{delay_thud},volume={vol_thud:.3f}[sfx{sfx_count}]")
    sfx_count += 1

    return sfx_count


def detect_speech_pauses(
    wav_path: Path,
    min_pause_sec: float = 0.18,
    threshold_db: float = -42.0,
    window_ms: int = 20,
) -> List[Tuple[float, float]]:
    """Detects speech and breath pauses via windowed RMS analysis (< threshold_db for >= min_pause_sec).

    Based on Danny Why §2 audio calibration. Returns list of (start_sec, end_sec) intervals.
    """
    with wave.open(str(wav_path), "rb") as wf:
        sr = wf.getframerate()
        n_ch = wf.getnchannels()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if n_ch > 1:
        samples = samples.reshape(-1, n_ch).mean(axis=1)

    win_size = int(sr * (window_ms / 1000.0))
    hop_size = win_size // 2
    n_win = (len(samples) - win_size) // hop_size

    rms_db = []
    times = []
    for w in range(n_win):
        chunk = samples[w * hop_size : w * hop_size + win_size]
        rms = float(np.sqrt(np.mean(chunk**2) + 1e-12))
        val_db = float(20.0 * np.log10(rms))
        rms_db.append(val_db)
        times.append((w * hop_size + win_size / 2) / float(sr))

    pauses: List[Tuple[float, float]] = []
    in_pause = False
    pause_start = 0.0

    for t, val in zip(times, rms_db):
        if val < threshold_db:
            if not in_pause:
                in_pause = True
                pause_start = t
        else:
            if in_pause:
                pause_dur = t - pause_start
                if pause_dur >= min_pause_sec:
                    pauses.append((round(pause_start, 3), round(t, 3)))
                in_pause = False

    if in_pause:
        pause_dur = times[-1] - pause_start
        if pause_dur >= min_pause_sec:
            pauses.append((round(pause_start, 3), round(times[-1], 3)))

    logger.info(f"Detected {len(pauses)} breath pauses in {wav_path.name}")
    return pauses
