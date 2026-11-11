"""Unit tests for tools/uniqueness_gate.py (Global Rule C)."""

from __future__ import annotations

import json
from pathlib import Path
from PIL import Image
import pytest

from tools.errors import UniquenessGateError
from tools.uniqueness_gate import (
    audio_envelope_distance,
    compute_image_phash,
    evaluate_uniqueness_gate,
    load_uniqueness_thresholds,
    phash_distance,
    text_token_similarity,
)


def _create_test_image(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (64, 64), color)
    img.save(path)


def test_load_uniqueness_thresholds() -> None:
    cfg = load_uniqueness_thresholds()
    assert cfg["min_phash_distance"] >= 8
    assert cfg["max_sfx_overlap_ratio"] <= 0.60
    assert cfg["disallow_exact_image_reuse"] is True


def test_image_phash_computation_and_distance(tmp_path: Path) -> None:
    img1 = tmp_path / "img1.png"
    img2 = tmp_path / "img2.png"
    img3 = tmp_path / "img3.png"

    _create_test_image(img1, (255, 0, 0))
    _create_test_image(img2, (255, 0, 0))  # identical to img1
    
    # Create img3 with a distinctive pattern
    pattern = Image.new("RGB", (64, 64), (0, 0, 0))
    for x in range(32):
        for y in range(64):
            pattern.putpixel((x, y), (255, 255, 255))
    pattern.save(img3)

    h1 = compute_image_phash(img1)
    h2 = compute_image_phash(img2)
    h3 = compute_image_phash(img3)

    assert phash_distance(h1, h2) == 0
    assert phash_distance(h1, h3) > 0


def test_text_token_similarity() -> None:
    assert text_token_similarity("Why do 85% of people freeze?", "Why do 85% of people freeze?") == 1.0
    assert text_token_similarity("Completely distinct sentence.", "Nothing in common here at all.") == 0.0
    sim = text_token_similarity("Why does fear freeze your brain?", "Why does fear paralyze your focus?")
    assert 0.3 < sim < 0.8


def test_audio_envelope_distance() -> None:
    fp1 = [0.1, 0.2, 0.4, 0.8, 0.5]
    fp2 = [0.1, 0.2, 0.4, 0.8, 0.5]
    assert audio_envelope_distance(fp1, fp2) == 0.0

    fp3 = [0.8, 0.5, 0.2, 0.1, 0.05]
    assert audio_envelope_distance(fp1, fp3) > 0.3


def test_uniqueness_gate_passes_on_distinct_projects(tmp_path: Path) -> None:
    p1 = tmp_path / "shorts" / "short_01" / "project.json"
    p2 = tmp_path / "shorts" / "short_02" / "project.json"

    p1.parent.mkdir(parents=True, exist_ok=True)
    p2.parent.mkdir(parents=True, exist_ok=True)

    _create_test_image(p1.parent / "images" / "s01.jpg", (200, 100, 50))
    _create_test_image(p2.parent / "images" / "s01.jpg", (50, 150, 220))

    p1.write_text(json.dumps({
        "id": "SH-01",
        "music": "ambient_drone_1.mp3",
        "ambience": "library_quiet.wav",
        "scenes": [
            {"id": "s01", "text": "Why do people walk past emergencies on crowded sidewalks?", "prompt": "Crowded city crosswalk in mist", "image": "images/s01.jpg", "sfx": "whoosh_sub.wav"}
        ],
    }))

    p2.write_text(json.dumps({
        "id": "SH-02",
        "music": "piano_minimalist_2.mp3",
        "ambience": "night_wind.wav",
        "scenes": [
            {"id": "s01", "text": "Your brain treats unread notifications like predatory threats.", "prompt": "Glowing vintage smartphone on dark oak table", "image": "images/s01.jpg", "sfx": "tension_riser.wav"}
        ],
    }))

    report = evaluate_uniqueness_gate(p2, root_dir=tmp_path)
    assert report.passed is True
    assert report.violations == []


def test_uniqueness_gate_fails_on_duplicate_opening_text(tmp_path: Path) -> None:
    p1 = tmp_path / "shorts" / "short_01" / "project.json"
    p2 = tmp_path / "shorts" / "short_02" / "project.json"

    p1.parent.mkdir(parents=True, exist_ok=True)
    p2.parent.mkdir(parents=True, exist_ok=True)

    common_hook = "Why does losing money hurt twice as much as finding money?"

    p1.write_text(json.dumps({
        "id": "SH-01",
        "scenes": [{"id": "s01", "text": common_hook, "prompt": "Antique ledger on desk"}],
    }))

    p2.write_text(json.dumps({
        "id": "SH-02",
        "scenes": [{"id": "s01", "text": common_hook, "prompt": "Modern office trading screens"}],
    }))

    report = evaluate_uniqueness_gate(p2, root_dir=tmp_path)
    assert report.passed is False
    assert any("Duplicate opening spoken sentence" in v for v in report.violations)


def test_uniqueness_gate_fails_on_duplicate_opening_prompt(tmp_path: Path) -> None:
    p1 = tmp_path / "shorts" / "short_01" / "project.json"
    p2 = tmp_path / "shorts" / "short_02" / "project.json"

    p1.parent.mkdir(parents=True, exist_ok=True)
    p2.parent.mkdir(parents=True, exist_ok=True)

    common_prompt = "35mm macro shot of empty wallet on dark mahogany desk"

    p1.write_text(json.dumps({
        "id": "SH-01",
        "scenes": [{"id": "s01", "text": "Sentence A about money.", "prompt": common_prompt}],
    }))

    p2.write_text(json.dumps({
        "id": "SH-02",
        "scenes": [{"id": "s01", "text": "Sentence B about finance.", "prompt": common_prompt}],
    }))

    report = evaluate_uniqueness_gate(p2, root_dir=tmp_path)
    assert report.passed is False
    assert any("Duplicate opening scene prompt" in v for v in report.violations)


def test_uniqueness_gate_fails_on_reused_image(tmp_path: Path) -> None:
    p1 = tmp_path / "shorts" / "short_01" / "project.json"
    p2 = tmp_path / "shorts" / "short_02" / "project.json"

    p1.parent.mkdir(parents=True, exist_ok=True)
    p2.parent.mkdir(parents=True, exist_ok=True)

    # Identical image written to both projects
    _create_test_image(p1.parent / "images" / "s01.jpg", (100, 120, 140))
    _create_test_image(p2.parent / "images" / "s01.jpg", (100, 120, 140))

    p1.write_text(json.dumps({
        "id": "SH-01",
        "scenes": [{"id": "s01", "text": "Topic 1", "prompt": "Prompt 1", "image": "images/s01.jpg"}],
    }))

    p2.write_text(json.dumps({
        "id": "SH-02",
        "scenes": [{"id": "s01", "text": "Topic 2", "prompt": "Prompt 2", "image": "images/s01.jpg"}],
    }))

    report = evaluate_uniqueness_gate(p2, root_dir=tmp_path)
    assert report.passed is False
    assert any("Exact image reuse detected" in v for v in report.violations)


def test_uniqueness_gate_fails_on_excessive_sfx_overlap(tmp_path: Path) -> None:
    p1 = tmp_path / "shorts" / "short_01" / "project.json"
    p2 = tmp_path / "shorts" / "short_02" / "project.json"

    p1.parent.mkdir(parents=True, exist_ok=True)
    p2.parent.mkdir(parents=True, exist_ok=True)

    sfx_set = ["whoosh.wav", "boom.wav", "shutter.wav", "chime.wav"]

    p1.write_text(json.dumps({
        "id": "SH-01",
        "scenes": [{"id": f"s0{i}", "text": f"Sentence {i}", "prompt": f"Prompt {i}", "sfx": sfx} for i, sfx in enumerate(sfx_set, 1)],
    }))

    p2.write_text(json.dumps({
        "id": "SH-02",
        "scenes": [{"id": f"s0{i}", "text": f"Alternative {i}", "prompt": f"Unique {i}", "sfx": sfx} for i, sfx in enumerate(sfx_set, 1)],
    }))

    report = evaluate_uniqueness_gate(p2, root_dir=tmp_path)
    assert report.passed is False
    assert any("SFX asset overlap" in v for v in report.violations)


def test_uniqueness_gate_fails_on_duplicate_music_bed(tmp_path: Path) -> None:
    p1 = tmp_path / "shorts" / "short_01" / "project.json"
    p2 = tmp_path / "shorts" / "short_02" / "project.json"

    p1.parent.mkdir(parents=True, exist_ok=True)
    p2.parent.mkdir(parents=True, exist_ok=True)

    p1.write_text(json.dumps({
        "id": "SH-01",
        "music": "cinematic_strings_theme_01.mp3",
        "scenes": [{"id": "s01", "text": "First video line.", "prompt": "Prompt A"}],
    }))

    p2.write_text(json.dumps({
        "id": "SH-02",
        "music": "cinematic_strings_theme_01.mp3",
        "scenes": [{"id": "s01", "text": "Second video line.", "prompt": "Prompt B"}],
    }))

    report = evaluate_uniqueness_gate(p2, root_dir=tmp_path)
    assert report.passed is False
    assert any("Duplicate music bed" in v for v in report.violations)


def test_uniqueness_gate_raises_typed_error(tmp_path: Path) -> None:
    p1 = tmp_path / "shorts" / "short_01" / "project.json"
    p2 = tmp_path / "shorts" / "short_02" / "project.json"

    p1.parent.mkdir(parents=True, exist_ok=True)
    p2.parent.mkdir(parents=True, exist_ok=True)

    p1.write_text(json.dumps({
        "id": "SH-01",
        "scenes": [{"id": "s01", "text": "Same text", "prompt": "Same prompt"}],
    }))

    p2.write_text(json.dumps({
        "id": "SH-02",
        "scenes": [{"id": "s01", "text": "Same text", "prompt": "Same prompt"}],
    }))

    with pytest.raises(UniquenessGateError) as exc_info:
        evaluate_uniqueness_gate(p2, root_dir=tmp_path, raise_on_failure=True)
    assert exc_info.value.stage == "uniqueness_gate"
