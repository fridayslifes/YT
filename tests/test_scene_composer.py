"""Locks the shared scene-composition invariants every Short relies on.

Rules live in .agents/personas/scene_composer.md and tools/scene_composer.py.
"""

from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from tools import scene_composer as sc

FONT_PATH = Path(__file__).resolve().parent.parent / "tools" / "fonts" / "BeVietnamPro-Bold.ttf"
FONT = ImageFont.truetype(str(FONT_PATH), 64)


def test_band_pixels_is_the_documented_44_to_76_band():
    assert sc.band_pixels(3840) == (1689, 2918)
    assert sc.band_pixels(1920) == (844, 1459)


def test_text_layer_errors_flags_anything_leaving_the_band():
    assert sc.text_layer_errors([("caption", 1700, 2900)], 3840) == []
    bad = sc.text_layer_errors([("hook", 600, 760), ("caption", 2500, 3000)], 3840)
    assert len(bad) == 2 and "hook" in bad[0] and "caption" in bad[1]


def test_caption_wrap_never_leaves_a_single_word_orphan():
    draw = ImageDraw.Draw(Image.new("RGB", (2160, 3840)))
    text = ("The bubbles rise and pop, fizzing bits of the ground into the air. "
            "They even dyed the soil and watched the color fly.")
    lines = sc.wrap_balanced(draw, text, FONT, 1750)
    assert len(lines) >= 2
    assert all(len(line.split()) >= 2 for line in lines), lines


def test_ground_texture_is_never_blank():
    g = sc.make_ground_texture(2160, 2600, 3840, 7, (62, 78, 98))
    assert g.shape == (1240, 2160, 3)
    # a blank band would be a pure vertical gradient: rows are identical per channel
    row_variance = g[:, :, 0].std(axis=1).mean()
    assert row_variance > 3.0, row_variance
