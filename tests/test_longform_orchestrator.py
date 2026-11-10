from __future__ import annotations

import cv2

from tools import longform_orchestrator


def test_calculate_word_budgets():
    """Verify word budgets scale proportionally with duration at 145 wpm."""
    total_10m, budgets_10m = longform_orchestrator.calculate_word_budgets(10.0)
    assert 1400 <= total_10m <= 1500
    assert "Act 1 (Cold Open)" in budgets_10m
    assert "Act 5 (The Turn / Core Thesis)" in budgets_10m

    total_12m, _ = longform_orchestrator.calculate_word_budgets(12.0)
    assert 1700 <= total_12m <= 1800


def test_build_5act_essay_spec():
    """Verify 5-act essay specification structure and mid-roll markers."""
    spec = longform_orchestrator.build_5act_essay_spec(
        topic="Loss Aversion",
        target_minutes=10.0,
        genre="magnates_amber",
        aspect_ratio="16:9",
    )

    assert spec.topic == "Loss Aversion"
    assert len(spec.chapters) == 6
    assert spec.chapters[0].title == "The Anomaly"
    # Word count sanity
    assert spec.total_words > 1000

    # Mid-roll markers for 10-minute video
    assert len(spec.mid_roll_markers) >= 2
    for mr in spec.mid_roll_markers:
        assert ":" in mr.timecode
        assert mr.seconds > 60.0


def test_export_longform_project(tmp_path):
    """Verify project export writes valid project.json and UPLOAD_KIT.md."""
    spec = longform_orchestrator.build_5act_essay_spec(topic="Test Topic", target_minutes=8.0)
    proj_file = longform_orchestrator.export_longform_project(spec, tmp_path)

    assert proj_file.exists()
    kit_file = tmp_path / "UPLOAD_KIT.md"
    assert kit_file.exists()

    content = kit_file.read_text(encoding="utf-8")
    assert "00:00 - Introduction & Cold Open" in content
    assert "Strategic Mid-Roll Monetization Windows" in content


def test_render_chapter_title_card(tmp_path):
    """Render a chapter title card and verify stream decoding."""
    out_mp4 = tmp_path / "chapter_card.mp4"
    ok = longform_orchestrator.render_chapter_title_card(
        title="The Anomaly",
        chapter_num=1,
        output_path=out_mp4,
        width=320,
        height=180,
        duration=0.5,
        fps=10,
        style="magnates_amber",
    )

    assert ok is True
    assert out_mp4.exists()
    assert out_mp4.stat().st_size > 0

    cap = cv2.VideoCapture(str(out_mp4))
    assert cap.isOpened()
    ret, frame = cap.read()
    assert ret is True
    assert frame.shape == (180, 320, 3)
    cap.release()
