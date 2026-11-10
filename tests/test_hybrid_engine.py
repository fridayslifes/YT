from __future__ import annotations

import cv2
import numpy as np

from tools import hybrid_engine, riddle_director, stickman_engine


def test_render_hybrid_scene_end_to_end(tmp_path):
    """Render a mixed-media hybrid scene and verify MP4 stream validity."""
    out_mp4 = tmp_path / "test_hybrid.mp4"
    bg_img = np.full((320, 180, 3), (45, 55, 75), dtype=np.uint8)

    pose = stickman_engine.StickmanPoseSpec(pose="thinking", prop="magnifying_glass")
    app = stickman_engine.StickmanAppearance(accessory="flat_cap")

    riddle_spec = riddle_director.RiddleSceneSpec(
        title="Test Hybrid Riddle",
        inventory=[
            riddle_director.InventoryItem(label="⚪", count=3),
            riddle_director.InventoryItem(label="⚫", count=2),
        ],
        characters=[
            riddle_director.CharacterAnchor(id="1", name="Detective", x=0.5, y=0.55, badge_label="①"),
        ],
        sightlines=[],
        countdown_seconds=3.0,
        cta_banner="WHO IS GUILTY? COMMENT BELOW",
    )

    ok = hybrid_engine.render_hybrid_scene(
        bg_image=bg_img,
        pose_spec=pose,
        appearance=app,
        riddle_spec=riddle_spec,
        output_path=out_mp4,
        style="magnates_amber",
        trajectory="magnates_drift",
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
