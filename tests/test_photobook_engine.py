from __future__ import annotations

import cv2
import numpy as np

from tools import photobook_engine


def test_s_curve_ease_boundaries():
    """Verify smoothstep easing strictly respects 0.0 and 1.0 boundaries."""
    assert photobook_engine.s_curve_ease(0.0) == 0.0
    assert photobook_engine.s_curve_ease(1.0) == 1.0
    assert 0.0 < photobook_engine.s_curve_ease(0.5) < 1.0
    # Clamping behavior
    assert photobook_engine.s_curve_ease(-0.5) == 0.0
    assert photobook_engine.s_curve_ease(1.5) == 1.0


def test_compute_camera_transform_presets():
    """Verify camera transforms across all presets produce realistic motion values."""
    presets = ["magnates_drift", "lemmino_reveal", "archival_zoom", "vertigo_reveal"]
    for preset in presets:
        # Near layer (Z=200) moves faster than Far layer (Z=3000)
        near_pan_x, near_pan_y, near_zoom, _ = photobook_engine.compute_camera_transform(
            preset, progress=0.8, z_depth=200.0, reference_z=1000.0
        )
        far_pan_x, far_pan_y, far_zoom, _ = photobook_engine.compute_camera_transform(
            preset, progress=0.8, z_depth=3000.0, reference_z=1000.0
        )
        # Parallax check: near layer should have greater displacement magnitude
        assert abs(near_pan_x) >= abs(far_pan_x)
        assert near_zoom > 0.95


def test_color_grading_presets():
    """Verify 3-way color grading transforms image arrays properly."""
    test_img = np.full((100, 100, 3), 128, dtype=np.uint8)
    for style in ["magnates_amber", "lemmino_noir", "archival_sepia", "portra_35mm"]:
        graded = photobook_engine.apply_color_grade(test_img, style)
        assert graded.shape == (100, 100, 3)
        assert graded.dtype == np.uint8
        # Graded output should differ from flat gray input
        assert not np.array_equal(graded, test_img)


def test_vignette_and_grain():
    """Verify optical vignette and procedural film grain generation."""
    test_img = np.full((120, 120, 3), 200, dtype=np.uint8)
    vignetted = photobook_engine.apply_optical_vignette(test_img, strength=0.5)
    # Corners should be darker than center
    center_val = vignetted[60, 60, 0]
    corner_val = vignetted[5, 5, 0]
    assert corner_val < center_val

    grain = photobook_engine.generate_film_grain(120, 120, intensity=10.0)
    assert grain.shape == (120, 120, 1)
    assert -40.0 < np.mean(grain) < 40.0


def test_decompose_single_image():
    """Verify automatic decomposition creates 3 planes with expected Z-depth order."""
    test_img = np.random.randint(0, 255, (200, 200, 3), dtype=np.uint8)
    layers = photobook_engine.decompose_single_image(test_img, target_w=108, target_h=192)
    assert len(layers) == 3
    # Check Z-depth ordering
    z_depths = [layer.z_depth for layer in layers]
    assert z_depths == [3000.0, 1000.0, 200.0]
    # Check foreground and background flags
    assert layers[0].is_background is True
    assert layers[2].is_foreground is True


def test_render_photobook_scene_end_to_end(tmp_path):
    """Render a short test clip and verify output stream validity."""
    out_mp4 = tmp_path / "test_photobook.mp4"
    bg = np.full((240, 140, 3), (40, 50, 70), dtype=np.uint8)
    subj = np.full((240, 140, 4), (200, 180, 160, 220), dtype=np.uint8)
    fg = np.full((240, 140, 4), (10, 10, 20, 100), dtype=np.uint8)

    layers = [
        photobook_engine.PhotobookLayer(image=bg, z_depth=3000.0, is_background=True),
        photobook_engine.PhotobookLayer(image=subj, z_depth=1000.0),
        photobook_engine.PhotobookLayer(image=fg, z_depth=200.0, is_foreground=True),
    ]

    ok = photobook_engine.render_photobook_scene(
        layers=layers,
        output_path=out_mp4,
        style="magnates_amber",
        trajectory="magnates_drift",
        duration=0.5,
        fps=10,
        width=140,
        height=240,
    )
    assert ok is True
    assert out_mp4.exists()
    assert out_mp4.stat().st_size > 0

    # Verify video decodes
    cap = cv2.VideoCapture(str(out_mp4))
    assert cap.isOpened()
    ret, frame = cap.read()
    assert ret is True
    assert frame.shape == (240, 140, 3)
    cap.release()
