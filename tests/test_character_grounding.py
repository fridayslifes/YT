#!/usr/bin/env python3
"""tests/test_character_grounding.py — Unit tests for the SOTA character grounding engine."""

import numpy as np
import pytest

from tools.character_grounding_engine import CharacterGroundingEngine


def create_dummy_sprite(width: int = 400, height: int = 1000, top_pad: int = 50, bottom_pad: int = 30) -> np.ndarray:
    """Creates a dummy RGBA sprite with transparent padding at top and bottom."""
    sprite = np.zeros((height, width, 4), dtype=np.uint8)
    # Fill visible character body
    sprite[top_pad : height - bottom_pad, 50 : width - 50, :3] = (180, 120, 80)
    sprite[top_pad : height - bottom_pad, 50 : width - 50, 3] = 255  # opaque
    return sprite


def test_sprite_metrics_alpha_detection():
    engine = CharacterGroundingEngine(canonical_height=1440, ground_y=2700)
    sprite = create_dummy_sprite(width=400, height=1000, top_pad=40, bottom_pad=25)
    metrics = engine.analyze_sprite(sprite, "dummy_1")

    assert metrics.raw_h == 1000
    assert metrics.raw_w == 400
    assert metrics.top_alpha == 40
    assert metrics.bottom_alpha == 1000 - 25 - 1
    assert metrics.visible_h == (1000 - 25 - 1) - 40 + 1
    assert pytest.approx(metrics.sole_y_ratio, 0.001) == (1000 - 25 - 1) / 1000.0


def test_canonical_height_normalization():
    """Different raw crops must result in the exact same canonical visible height."""
    engine = CharacterGroundingEngine(canonical_height=1400, ground_y=2700)

    # Sprite A: 800px visible height
    sprite_a = create_dummy_sprite(width=300, height=900, top_pad=50, bottom_pad=50)  # visible = 800
    # Sprite B: 1200px visible height
    sprite_b = create_dummy_sprite(width=500, height=1300, top_pad=50, bottom_pad=50)  # visible = 1200

    _, _, scale_a, _, _ = engine.compute_placement(sprite_a, "pose_a", target_ground_x=800)
    _, _, scale_b, _, _ = engine.compute_placement(sprite_b, "pose_b", target_ground_x=800)

    met_a = engine.analyze_sprite(sprite_a, "pose_a")
    met_b = engine.analyze_sprite(sprite_b, "pose_b")

    rendered_h_a = met_a.visible_h * scale_a
    rendered_h_b = met_b.visible_h * scale_b

    assert pytest.approx(rendered_h_a, 0.1) == 1400.0
    assert pytest.approx(rendered_h_b, 0.1) == 1400.0


def test_sole_pinned_to_ground():
    """The computed pivot ensures the sole is pinned to ground_y."""
    engine = CharacterGroundingEngine(canonical_height=1440, ground_y=2750)
    sprite = create_dummy_sprite(width=400, height=1000, top_pad=60, bottom_pad=40)

    cx, cy, scale_x, scale_y, (piv_x, piv_y) = engine.compute_placement(
        sprite, "pose_c", target_ground_x=1000, target_ground_y=2750
    )

    metrics = engine.analyze_sprite(sprite, "pose_c")
    assert cy == 2750
    assert pytest.approx(piv_y, 0.001) == metrics.sole_y_ratio


def test_render_contact_shadows():
    engine = CharacterGroundingEngine(canonical_height=1440, ground_y=2700)
    canvas = np.zeros((3840, 2160, 3), dtype=np.uint8)
    canvas[:] = (240, 240, 240)

    shadowed = engine.render_contact_shadows(canvas, target_ground_x=800, target_ground_y=2700, character_visible_width=400)
    # The shadow area around ground_y should be darker than base canvas
    assert np.mean(shadowed[2690:2720, 750:850]) < 235


def test_draw_perspective_ground_plane():
    engine = CharacterGroundingEngine(canonical_height=1440, ground_y=2700)
    canvas = np.zeros((3840, 2160, 3), dtype=np.uint8)
    result = engine.draw_perspective_ground_plane(canvas, ground_y=2700)

    assert result.shape == (3840, 2160, 3)
    # Floor area below 2700 should be filled
    assert np.mean(result[2800:2900, 500:600]) > 0
