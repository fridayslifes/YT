"""tests/test_cutout_hybrid_suite.py — Unit Tests for Danny Why Hybrid Tooling Suite."""

import math
import numpy as np
import cv2

from tools.sprite_aligner import (
    detect_head_disc,
    detect_feet_anchor,
    trim_alpha_box,
)
from tools.sound_architect import (
    DECIBEL_BUDGET,
    db_to_linear,
    get_cue_decibel,
    get_cue_linear_gain,
    snap_cue_to_breath_pause,
)
from tools.cutout_engine.cutout_director import (
    log_lerp,
    project_world_to_screen,
    compute_screen_shake,
)


def test_distance_transform_head_and_feet_anchor():
    """Verifies that Euclidean distance transform detects head radius and feet anchor accurately."""
    # Synthetic 300x300 cartoon character
    img = np.zeros((300, 300, 4), dtype=np.uint8)
    # Head circle at cx=150, cy=80, radius=50
    cv2.circle(img, (150, 80), 50, (255, 255, 255, 255), -1)
    # Body rect at x=130..170, y=130..270
    cv2.rectangle(img, (130, 130), (170, 270), (255, 255, 255, 255), -1)

    hx, hy, r = detect_head_disc(img)
    fx, fy = detect_feet_anchor(img)

    assert abs(hx - 150) <= 2
    assert abs(hy - 80) <= 2
    assert abs(r - 50.0) <= 2.0
    assert abs(fx - 150) <= 2
    assert fy == 270


def test_trim_alpha_box():
    """Verifies trimming to non-zero alpha bounding box with padding."""
    img = np.zeros((200, 200, 4), dtype=np.uint8)
    img[50:150, 60:140] = (100, 150, 200, 255)

    trimmed, bbox = trim_alpha_box(img, margin=10)
    # 50-10=40, 150+10=160 -> height 120; 60-10=50, 140+10=150 -> width 100
    assert trimmed.shape[0] == 120
    assert trimmed.shape[1] == 100
    assert bbox == (50, 40, 100, 120)


def test_decibel_budget_and_linear_conversion():
    """Verifies Danny Why decibel budget values and db_to_linear conversion."""
    assert DECIBEL_BUDGET["voice"] == 0.0
    assert DECIBEL_BUDGET["climax_blast"] == -8.5
    assert DECIBEL_BUDGET["impact_thud"] == -15.0
    assert DECIBEL_BUDGET["air_whoosh"] == -27.0
    assert DECIBEL_BUDGET["ambient_bed"] == -28.0

    # 0 dB = 1.0 linear
    assert math.isclose(db_to_linear(0.0), 1.0, rel_tol=1e-3)
    # -6 dB ≈ 0.5 linear
    assert math.isclose(db_to_linear(-6.02), 0.5, rel_tol=1e-2)
    # -20 dB = 0.1 linear
    assert math.isclose(db_to_linear(-20.0), 0.1, rel_tol=1e-3)


def test_cue_categories_and_pause_snapping():
    """Verifies decibel category lookup and speech pause snapping."""
    assert get_cue_decibel("sub_bass_drop") == -8.5
    assert get_cue_decibel("desk_thud") == -15.0
    assert get_cue_decibel("typewriter_sfx") == -22.0
    assert get_cue_decibel("paper_swoosh") == -27.0
    assert get_cue_decibel("tension_clock") == -28.0
    # Specific cues must win over generic substrings: "pressure_drop" contains "drop"
    # (impact_thud, -15) but is an air_whoosh (-27); "sub_bass_drop" is a climax_blast (-8.5).
    assert get_cue_decibel("pressure_drop") == -27.0
    assert get_cue_decibel("drop") == -15.0

    # Linear gain check
    assert math.isclose(get_cue_linear_gain("sub_bass_drop"), db_to_linear(-8.5), rel_tol=1e-3)

    # Breath pause snapping
    pauses = [(2.1, 2.5), (6.0, 6.4)]
    # Target 2.2 is within 0.8s of pause center (2.3) -> snaps to 2.3
    snapped = snap_cue_to_breath_pause(2.2, pauses, search_window_sec=0.8)
    assert snapped == 2.3

    # Target 4.0 is far from any pause -> stays 4.0
    far = snap_cue_to_breath_pause(4.0, pauses, search_window_sec=0.8)
    assert far == 4.0


def test_log_space_interpolation():
    """Verifies optical log-space scale interpolation."""
    k0 = 1.0
    k1 = 4.0
    # In log space, midpoint u=0.5 should equal sqrt(k0 * k1) = 2.0
    mid = log_lerp(k0, k1, 0.5)
    assert math.isclose(mid, 2.0, rel_tol=1e-4)


def test_project_world_to_screen():
    """Verifies 2.5D multiplane camera projection at depth Z."""
    # Camera at (540, 960, 0), world point at (540, 960, 1000)
    sx, sy, k = project_world_to_screen(540.0, 960.0, 1000.0, 540.0, 960.0, 0.0, focal_length=1000.0)
    assert sx == 540
    assert sy == 960
    assert math.isclose(k, 1.0, rel_tol=1e-4)

    # Point at Z=2000 should have scale k=0.5
    _, _, k2 = project_world_to_screen(540.0, 960.0, 2000.0, 540.0, 960.0, 0.0, focal_length=1000.0)
    assert math.isclose(k2, 0.5, rel_tol=1e-4)


def test_screen_shake_decay():
    """Verifies screen shake envelope decay."""
    dx0, dy0 = compute_screen_shake(0.02, amplitude=20.0, decay_rate=4.0)
    dx_late, dy_late = compute_screen_shake(1.5, amplitude=20.0, decay_rate=4.0)
    # Early shake should be active
    assert abs(dx0) > 0 or abs(dy0) > 0
    # Late shake should decay to 0
    assert dx_late == 0 and dy_late == 0


def test_cloud_narration_lead_in_matches_beats():
    """The narration WAV must carry the 0.1s lead-in so its duration matches the beat timeline."""
    import json
    import wave
    from pathlib import Path

    import pytest

    cache = Path(__file__).resolve().parent.parent / "shorts" / "short_18_why_clouds_dont_fall" / "cache"
    beats_p = cache / "beats.json"
    wav_p = cache / "narration.wav"
    if not beats_p.exists() or not wav_p.exists():
        pytest.skip("cloud short cache not rendered")
    beats = json.loads(beats_p.read_text(encoding="utf-8"))
    with wave.open(str(wav_p), "rb") as wf:
        wav_dur = wf.getnframes() / float(wf.getframerate())
    beats_end = beats[-1]["segment_end_sec"]
    assert abs(wav_dur - beats_end) < 0.05, f"narration {wav_dur:.3f}s vs beats {beats_end:.3f}s (missing lead-in?)"
