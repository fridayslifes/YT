from __future__ import annotations

import cv2
import numpy as np

from tools import stickman_engine


def test_compute_limb_joints_poses():
    """Verify all pose configurations produce valid joint coordinates."""
    poses = ["idle", "thinking", "pointing", "shocked", "facepalm", "shrugging", "running"]
    for p in poses:
        joints = stickman_engine.compute_limb_joints(100, 100, pose=p, torso_len=80, sway_phase=0.5)
        assert "neck" in joints
        assert "pelvis" in joints
        assert "r_hand" in joints
        assert "l_hand" in joints
        # Pelvis should be below neck
        assert joints["pelvis"][1] > joints["neck"][1]


def test_draw_stickman_face_expressions():
    """Verify face expressions draw distinct pixel patterns."""
    mouths = ["neutral", "smile", "open_gasp", "smirk", "frown"]
    results = []
    for m in mouths:
        canvas = np.zeros((100, 100, 3), dtype=np.uint8)
        stickman_engine.draw_stickman_face(
            canvas, head_center=(50, 50), radius=30, mouth=m, eyebrows="neutral", color=(255, 255, 255)
        )
        assert np.count_nonzero(canvas) > 0
        results.append(canvas)

    # Verify at least two expressions are visually distinct
    assert not np.array_equal(results[0], results[1])


def test_draw_accessory_and_props():
    """Verify accessories and props draw on canvas."""
    canvas = np.zeros((120, 120, 3), dtype=np.uint8)
    stickman_engine.draw_accessory(canvas, (60, 60), 30, accessory="flat_cap", color=(200, 100, 50))
    assert np.count_nonzero(canvas) > 0

    canvas_prop = np.zeros((100, 100, 3), dtype=np.uint8)
    stickman_engine.draw_prop(canvas_prop, (50, 50), prop_name="magnifying_glass")
    assert np.count_nonzero(canvas_prop) > 0


def test_render_stickman_scene_end_to_end(tmp_path):
    """Render a complete stickman scene and verify decoded MP4 stream."""
    out_mp4 = tmp_path / "test_stickman.mp4"
    app = stickman_engine.StickmanAppearance(accessory="flat_cap")
    pose = stickman_engine.StickmanPoseSpec(pose="thinking", mouth="smile", prop="coffee")

    ok = stickman_engine.render_stickman_scene(
        pose_spec=pose,
        app=app,
        output_path=out_mp4,
        caption_text="Test Stickman Caption",
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
