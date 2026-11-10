from __future__ import annotations

import cv2
import numpy as np
import pytest

from tools import riddle_director


def test_glassmorphic_panel_boundaries():
    """Verify glassmorphic panel respects bounds and modifies image."""
    canvas = np.zeros((100, 100, 3), dtype=np.uint8)
    riddle_director.draw_glassmorphic_panel(canvas, 10, 10, 90, 90)
    # Inside panel should no longer be pitch black
    assert np.mean(canvas[20:80, 20:80]) > 0


def test_inventory_hud_drawing():
    """Verify top inventory HUD draws item badges and counts."""
    canvas = np.zeros((200, 400, 3), dtype=np.uint8)
    items = [
        riddle_director.InventoryItem(label="White", count=3, color=(255, 255, 255)),
        riddle_director.InventoryItem(label="Black", count=2, color=(0, 0, 0)),
    ]
    riddle_director.draw_inventory_hud(canvas, items, top_margin=20)
    # Top region should have non-zero pixels
    assert np.count_nonzero(canvas[20:100, :]) > 0


def test_character_badges_and_thoughts():
    """Verify character anchor badges and thought bubbles render."""
    canvas = np.zeros((400, 400, 3), dtype=np.uint8)
    chars = [
        riddle_director.CharacterAnchor(id="1", name="P1", x=0.3, y=0.5, badge_label="①", thought_text="?"),
        riddle_director.CharacterAnchor(id="2", name="P2", x=0.7, y=0.5, badge_label="②", eliminated=True),
    ]
    riddle_director.draw_character_badges(canvas, chars, pulse_phase=0.5)
    # Check pixels around character 1 and 2 positions
    assert np.count_nonzero(canvas[100:250, 80:160]) > 0
    assert np.count_nonzero(canvas[100:250, 240:320]) > 0


def test_character_badges_and_sightlines_transform_with_camera_matrix():
    """Verify camera matrix shifts badge and sightline coordinates accordingly."""
    canvas_base = np.zeros((400, 400, 3), dtype=np.uint8)
    canvas_shifted = np.zeros((400, 400, 3), dtype=np.uint8)
    c1 = riddle_director.CharacterAnchor(id="1", name="P1", x=0.25, y=0.5, badge_label="1")
    c2 = riddle_director.CharacterAnchor(id="2", name="P2", x=0.75, y=0.5, badge_label="2")
    chars = [c1, c2]
    rays = [riddle_director.SightlineRay(from_id="1", to_id="2")]
    char_dict = {"1": c1, "2": c2}

    M = np.array([[1.0, 0.0, 30.0], [0.0, 1.0, -20.0]], dtype=np.float32)
    riddle_director.draw_character_badges(canvas_base, chars, pulse_phase=0.0)
    riddle_director.draw_sightlines(canvas_base, rays, char_dict, dash_offset=0.1)

    riddle_director.draw_character_badges(canvas_shifted, chars, pulse_phase=0.0, camera_matrix=M)
    riddle_director.draw_sightlines(canvas_shifted, rays, char_dict, dash_offset=0.1, camera_matrix=M)

    assert not np.array_equal(canvas_base, canvas_shifted)
    base_xs = np.where(canvas_base.sum(axis=2) > 0)[1]
    shift_xs = np.where(canvas_shifted.sum(axis=2) > 0)[1]
    assert shift_xs.mean() > base_xs.mean() + 15.0


@pytest.mark.parametrize("w,h", [(540, 960), (1080, 1920), (1920, 1080)])
def test_cliffhanger_cta_and_hud_never_clip_or_touch_frame_border(w, h):
    """Ensure CTA banner and HUD stay within safe bounds at 540x960, 1080x1920, and 1920x1080."""
    canvas = np.zeros((h, w, 3), dtype=np.uint8)
    items = [
        riddle_director.InventoryItem(label="White", count=3, color=(255, 255, 255)),
        riddle_director.InventoryItem(label="Black", count=2, color=(40, 40, 40)),
    ]
    riddle_director.draw_inventory_hud(canvas, items, top_margin=int(h * 0.05))
    riddle_director.draw_countdown_hud(
        canvas, remaining_seconds=5.0, total_seconds=7.0, center_x=int(w * 0.88), center_y=int(h * 0.17)
    )
    riddle_director.draw_cliffhanger_cta(
        canvas, "WHO DEDUCED IT FIRST? DROP YOUR FULL LOGICAL ANSWER IN THE COMMENTS BELOW!", y_pos=int(h * 0.70)
    )

    # Outer 4px border must stay completely untouched (zero clipping)
    assert np.count_nonzero(canvas[:, :4]) == 0
    assert np.count_nonzero(canvas[:, w - 4 :]) == 0
    assert np.count_nonzero(canvas[:4, :]) == 0
    assert np.count_nonzero(canvas[h - 4 :, :]) == 0

    # CTA must lie strictly inside the 44%..76% vertical safe zone
    cta_only = np.zeros((h, w, 3), dtype=np.uint8)
    riddle_director.draw_cliffhanger_cta(
        cta_only, "WHO DEDUCED IT FIRST? DROP YOUR FULL LOGICAL ANSWER IN THE COMMENTS BELOW!", y_pos=int(h * 0.70)
    )
    ys = np.where(cta_only.sum(axis=2) > 0)[0]
    assert ys.min() >= int(round(h * 0.44))
    assert ys.max() <= int(round(h * 0.76))


def test_sightlines_active_and_blocked():
    """Verify field-of-view sightline rays render for both active and blocked lines."""
    canvas = np.zeros((300, 300, 3), dtype=np.uint8)
    c1 = riddle_director.CharacterAnchor(id="A", name="A", x=0.2, y=0.5)
    c2 = riddle_director.CharacterAnchor(id="B", name="B", x=0.8, y=0.5)
    char_dict = {"A": c1, "B": c2}

    rays = [
        riddle_director.SightlineRay(from_id="A", to_id="B", blocked=False),
        riddle_director.SightlineRay(from_id="B", to_id="A", blocked=True),
    ]
    riddle_director.draw_sightlines(canvas, rays, char_dict, dash_offset=0.2)
    assert np.count_nonzero(canvas) > 0


def test_countdown_hud_color_shift():
    """Verify countdown radial HUD draws with time transitions."""
    canvas1 = np.zeros((150, 150, 3), dtype=np.uint8)
    canvas2 = np.zeros((150, 150, 3), dtype=np.uint8)

    # Calm state (progress > 0.5)
    riddle_director.draw_countdown_hud(canvas1, remaining_seconds=6.0, total_seconds=7.0, center_x=75, center_y=75)
    # Urgent state (progress < 0.25)
    riddle_director.draw_countdown_hud(canvas2, remaining_seconds=1.0, total_seconds=7.0, center_x=75, center_y=75)

    assert np.count_nonzero(canvas1) > 0
    assert np.count_nonzero(canvas2) > 0
    # Both states should have drawn different color distributions
    assert not np.array_equal(canvas1, canvas2)


def test_render_riddle_scene_end_to_end(tmp_path):
    """Render a complete riddle scene and verify decoded MP4 stream."""
    out_mp4 = tmp_path / "test_riddle.mp4"
    base_img = np.full((320, 180, 3), (35, 45, 60), dtype=np.uint8)

    spec = riddle_director.RiddleSceneSpec(
        title="Test Riddle",
        inventory=[
            riddle_director.InventoryItem(label="⚪", count=3),
            riddle_director.InventoryItem(label="⚫", count=2),
        ],
        characters=[
            riddle_director.CharacterAnchor(id="1", name="P1", x=0.25, y=0.6, badge_label="①"),
            riddle_director.CharacterAnchor(id="2", name="P2", x=0.75, y=0.6, badge_label="②", thought_text="?"),
        ],
        sightlines=[
            riddle_director.SightlineRay(from_id="1", to_id="2"),
        ],
        countdown_seconds=3.0,
        cta_banner="WHO KNOWS? COMMENT BELOW",
    )

    ok = riddle_director.render_riddle_scene(
        base_image=base_img,
        spec=spec,
        output_path=out_mp4,
        duration=0.5,
        fps=10,
        width=180,
        height=320,
    )

    assert ok is True
    assert out_mp4.exists()
    assert out_mp4.stat().st_size > 0

    cap = cv2.VideoCapture(str(out_mp4))
    assert cap.isOpened()
    ret, frame = cap.read()
    assert ret is True
    assert frame.shape == (320, 180, 3)
    cap.release()
