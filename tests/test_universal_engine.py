import hashlib
import json
import tempfile
import wave
from pathlib import Path

import cv2
import numpy as np
import pytest

from demos import archetype_demos
from tools import picture_book_engine, schemas, universal_engine


def _write_test_wav(path: Path, duration_sec: float = 0.25, freq_hz: float = 440.0, sr: int = 24000) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    n_samples = max(int(sr * duration_sec), 240)
    t = np.linspace(0.0, duration_sec, n_samples, endpoint=False)
    samples = (0.25 * np.sin(2.0 * np.pi * freq_hz * t) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(samples.tobytes())
    return path


def _make_schema_v2_project(
    variant: str,
    topic: str = "Signal Detection Theory",
    video_format: str = "short",
    lead_text: str = "You hear a phantom buzz in your pocket when waiting for a vital call.",
) -> dict:
    scenes = []
    for idx in range(1, 9):
        sc_id = f"s{idx:02d}"
        text = f"{lead_text} Beat {idx} on {topic}."
        scenes.append(
            {
                "id": sc_id,
                "duration": 0.25,
                "text": text,
                "caption": f"{topic.upper()} BEAT {idx}",
                "image": f"images/{sc_id}.jpg",
                "prompt": f"{topic} visual plate {idx} on an archival desk",
                "motion": "zoom_in" if idx % 2 == 1 else "pan_right",
                "stamp": f"CASE-{idx:02d}",
                "plate_label": f"EXHIBIT 0{idx} // {topic.upper()[:18]}",
                "pose": {"name": "pointing" if idx % 2 == 1 else "thinking"},
                "mouth": "smile",
                "eyebrows": "normal",
                "prop": "magnifying_glass" if idx == 1 else "coffee",
            }
        )
    return {
        "schema_version": schemas.PROJECT_SCHEMA_VERSION,
        "id": f"SH-{variant[:4].upper()}-01",
        "slug": f"short_{variant}",
        "title": f"{topic} — Studio Study",
        "topic": topic,
        "channel_id": "cognitive_core",
        "variant": variant,
        "format": video_format,
        "voice": "kokoro",
        "fps": 15,
        "gap": 0.04,
        "tail": 0.05,
        "citation_stat": "Green & Swets (1966) Signal Detection Theory and Psychophysics",
        "scenes": scenes,
    }


def test_get_font_fallback():
    font = universal_engine.get_font(Path("/nonexistent/font.ttf"), 24)
    assert font is not None


def test_universal_variants_and_registry_match_schema_v2():
    assert set(universal_engine.UNIVERSAL_VARIANTS.keys()) == set(schemas.SUPPORTED_VARIANTS)
    assert set(universal_engine.ENGINE_REGISTRY.keys()) == set(schemas.SUPPORTED_VARIANTS)
    assert "3d_cgi" not in universal_engine.UNIVERSAL_VARIANTS
    assert "3d_cgi" not in universal_engine.ENGINE_REGISTRY

    for variant in schemas.SUPPORTED_VARIANTS:
        engine = universal_engine.get_engine(variant)
        assert engine.variant == variant

    with pytest.raises(ValueError, match="Unsupported variant"):
        universal_engine.get_engine("3d_cgi")


def test_synthesize_studio_speech_enforces_strict_kokoro_voices(tmp_path):
    out_wav = tmp_path / "forbidden" / "speech.wav"
    with pytest.raises(ValueError, match="Unsupported voice"):
        universal_engine.synthesize_studio_speech(
            "Forbidden cloud voice check.",
            out_wav,
            voice="en-US-AndrewNeural",
        )
    assert not out_wav.exists()

    with pytest.raises(ValueError, match="Unsupported voice"):
        universal_engine.synthesize_studio_speech(
            "Forbidden alias voice check.",
            out_wav,
            voice="default",
        )
    assert not out_wav.exists()


def test_create_project_emits_valid_schema_v2_for_all_variants(tmp_path):
    for idx, variant in enumerate(sorted(schemas.SUPPORTED_VARIANTS)):
        fmt = "short" if idx % 2 == 0 else "long"
        proj_dir = universal_engine.create_project(
            slug=f"proj_{variant}",
            variant=variant,
            format_type=fmt,
            topic=f"Topic {variant}",
            title=f"Title {variant}",
            channel_id="cognitive_core",
            base_dir=tmp_path,
        )
        p_path = proj_dir / "project.json"
        assert p_path.exists()
        data = json.loads(p_path.read_text(encoding="utf-8"))
        errors = schemas.validate_project(data, project_path=p_path)
        assert errors == []
        assert data["schema_version"] == schemas.PROJECT_SCHEMA_VERSION
        assert data["variant"] == variant
        assert data["format"] == fmt
        assert data["voice"] == "kokoro"
        assert len(data["scenes"]) == 8


def test_picture_book_engine_dynamic_project_and_orientation(tmp_path):
    proj_short = _make_schema_v2_project(
        "storybook_picturebook",
        topic="Availability Heuristic",
        video_format="short",
    )
    elements_short = picture_book_engine.story_elements_from_project(proj_short)
    assert len(elements_short) == 8
    assert elements_short[0].render_flight_map is False
    assert "FBI NORJAK" not in elements_short[0].case_header
    assert "AVAILABILITY HEURISTIC" in elements_short[0].case_header

    images_dir = tmp_path / "images"
    cutouts_dir = images_dir / "cutouts"
    images_dir.mkdir(parents=True, exist_ok=True)
    cutouts_dir.mkdir(parents=True, exist_ok=True)

    spread_portrait, _ = picture_book_engine.build_scene_base_spread(
        elements_short[0], images_dir, cutouts_dir, width=1080, height=1920
    )
    assert spread_portrait.shape == (1920, 1080, 3)

    spread_landscape, _ = picture_book_engine.build_scene_base_spread(
        elements_short[0], images_dir, cutouts_dir, width=1920, height=1080
    )
    assert spread_landscape.shape == (1080, 1920, 3)


def test_render_all_archetypes_short_probe():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        p1 = universal_engine.render_photobook_from_scratch(
            tmp_path / "probe_01.mp4", duration=0.2, fps=15, width=540, height=960
        )
        assert p1.exists()
        assert p1.stat().st_size > 500

        p2 = universal_engine.render_riddle_from_scratch(
            tmp_path / "probe_02.mp4", duration=0.2, fps=15, width=540, height=960
        )
        assert p2.exists()
        assert p2.stat().st_size > 500

        p3 = universal_engine.render_stickman_from_scratch(
            tmp_path / "probe_03.mp4", duration=0.2, fps=15, width=540, height=960
        )
        assert p3.exists()
        assert p3.stat().st_size > 500

        p4 = universal_engine.render_hybrid_from_scratch(
            tmp_path / "probe_04.mp4", duration=0.2, fps=15, width=540, height=960
        )
        assert p4.exists()
        assert p4.stat().st_size > 500


def test_demos_extracted_to_demos_module():
    assert hasattr(archetype_demos, "render_30s_photobook_hd_with_audio")
    assert hasattr(archetype_demos, "render_30s_riddle_hd_with_audio")
    assert hasattr(archetype_demos, "render_30s_stickman_hd_with_audio")
    assert hasattr(archetype_demos, "render_30s_hybrid_hd_with_audio")


@pytest.mark.parametrize("variant", sorted(schemas.SUPPORTED_VARIANTS))
def test_all_seven_engines_validate_and_render_distinct_topics(
    variant: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    def _fake_tts_cached(text: str, voice: str, rate: str, pitch: str, cache_dir: Path):
        freq = 320.0 + (sum(ord(ch) for ch in text) % 300)
        dur = 0.25 + (len(text) % 4) * 0.02
        digest = hashlib.sha256(f"{voice}|{text}".encode("utf-8")).hexdigest()[:16]
        out = Path(cache_dir) / f"fake_tts_{digest}.wav"
        if not out.exists():
            _write_test_wav(out, duration_sec=dur, freq_hz=freq)
        words = [
            {"word": "First", "start": 0.0, "end": 0.12},
            {"word": "beat", "start": 0.12, "end": 0.24},
        ]
        return out, words

    def _fast_master_build(proj_path: Path, out_mp4: Path, preview: bool = False, hw_accel: bool = True) -> Path:
        data = json.loads(Path(proj_path).read_text(encoding="utf-8"))
        first_vid = Path(proj_path).parent / data["scenes"][0]["video"]
        assert first_vid.exists() and first_vid.stat().st_size > 500
        out_mp4 = Path(out_mp4)
        out_mp4.parent.mkdir(parents=True, exist_ok=True)
        payload = first_vid.read_bytes() + json.dumps(data, sort_keys=True).encode("utf-8")
        out_mp4.write_bytes(payload)
        return out_mp4

    monkeypatch.setattr("tools.build_video.tts_cached", _fake_tts_cached)
    monkeypatch.setattr("tools.build_video.build", _fast_master_build)

    engine = universal_engine.get_engine(variant)

    dir_a = tmp_path / f"{variant}_topic_a"
    dir_a.mkdir(parents=True, exist_ok=True)
    proj_a = _make_schema_v2_project(
        variant,
        topic=f"Cognitive Anchoring {variant}",
        lead_text="First number on the negotiation table pulls every estimate toward itself.",
    )
    assert engine.validate(proj_a) == []

    proj_a_path = dir_a / "project.json"
    proj_a_path.write_text(json.dumps(proj_a, indent=2), encoding="utf-8")

    src_a = universal_engine._ensure_scene_plate(dir_a, proj_a, proj_a["scenes"][0], 0, 540, 960)
    clip_a = dir_a / "videos" / "s01.mp4"
    clip_a.parent.mkdir(parents=True, exist_ok=True)
    engine.render_scene_clip(
        project_dir=dir_a,
        proj_data=proj_a,
        scene=proj_a["scenes"][0],
        scene_idx=0,
        source_image=src_a,
        target_vid=clip_a,
        duration_s=0.3,
        words=[{"word": "First", "start": 0.0, "end": 0.12}, {"word": "number", "start": 0.12, "end": 0.24}],
        width=540,
        height=960,
        fps=30,
    )
    assert clip_a.exists() and clip_a.stat().st_size > 500

    dir_b = tmp_path / f"{variant}_topic_b"
    dir_b.mkdir(parents=True, exist_ok=True)
    proj_b = _make_schema_v2_project(
        variant,
        topic=f"Sunk Cost Escalation {variant}",
        lead_text="Abandoning a failing ticket feels painful after hours of waiting in rain.",
    )
    src_b = universal_engine._ensure_scene_plate(dir_b, proj_b, proj_b["scenes"][0], 0, 540, 960)
    clip_b = dir_b / "videos" / "s01.mp4"
    clip_b.parent.mkdir(parents=True, exist_ok=True)
    engine.render_scene_clip(
        project_dir=dir_b,
        proj_data=proj_b,
        scene=proj_b["scenes"][0],
        scene_idx=0,
        source_image=src_b,
        target_vid=clip_b,
        duration_s=0.3,
        words=[{"word": "Abandoning", "start": 0.0, "end": 0.12}, {"word": "ticket", "start": 0.12, "end": 0.24}],
        width=540,
        height=960,
        fps=30,
    )
    assert clip_b.exists() and clip_b.stat().st_size > 500
    assert hashlib.sha256(src_a.read_bytes()).hexdigest() != hashlib.sha256(src_b.read_bytes()).hexdigest()
    assert hashlib.sha256(clip_a.read_bytes()).hexdigest() != hashlib.sha256(clip_b.read_bytes()).hexdigest()


def test_build_project_reuses_and_invalidates_render_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    render_calls = []

    def _fake_tts_cached(text: str, voice: str, rate: str, pitch: str, cache_dir: Path):
        digest = hashlib.sha256(f"{voice}|{text}".encode("utf-8")).hexdigest()[:16]
        out = Path(cache_dir) / f"fake_tts_{digest}.wav"
        if not out.exists():
            _write_test_wav(out, duration_sec=0.25, freq_hz=360.0)
        words = [{"word": "Test", "start": 0.0, "end": 0.22}]
        return out, words

    def _fast_render_scene_clip(self, *, target_vid: Path, scene_idx: int, width: int, height: int, **_: object) -> bool:
        render_calls.append(scene_idx)
        target_vid.parent.mkdir(parents=True, exist_ok=True)
        raw = target_vid.with_suffix(".raw.mp4")
        writer = cv2.VideoWriter(str(raw), cv2.VideoWriter_fourcc(*"mp4v"), 15.0, (width, height))
        for _ in range(15):
            writer.write(np.full((height, width, 3), 40 + scene_idx * 10, dtype=np.uint8))
        writer.release()
        universal_engine.reencode_broadcast_mp4(raw, target_vid, fps=15)
        raw.unlink(missing_ok=True)
        return True

    def _fast_master_build(proj_path: Path, out_mp4: Path, preview: bool = False, hw_accel: bool = True) -> Path:
        out_mp4 = Path(out_mp4)
        out_mp4.parent.mkdir(parents=True, exist_ok=True)
        out_mp4.write_bytes(Path(proj_path).read_bytes())
        return out_mp4

    monkeypatch.setattr("tools.build_video.tts_cached", _fake_tts_cached)
    monkeypatch.setattr("tools.build_video.build", _fast_master_build)
    monkeypatch.setattr(universal_engine.RiddleVariantEngine, "render_scene_clip", _fast_render_scene_clip)

    proj_dir = tmp_path / "riddle_manifest_test"
    proj_dir.mkdir(parents=True, exist_ok=True)
    proj = _make_schema_v2_project("riddle", topic="Monty Hall Logic")
    proj_path = proj_dir / "project.json"
    proj_path.write_text(json.dumps(proj, indent=2), encoding="utf-8")

    out_1 = universal_engine.build_project(proj_path)
    assert out_1.exists()
    assert render_calls == list(range(8))

    # Second build with identical inputs reuses all 8 cached scene clips
    render_calls.clear()
    out_2 = universal_engine.build_project(proj_path)
    assert out_2.exists()
    assert render_calls == []

    # Mutating scene 0 overlay parameter (stamp) invalidates only scene 0
    proj_updated = json.loads(proj_path.read_text(encoding="utf-8"))
    proj_updated["scenes"][0]["stamp"] = "UPDATED-STAMP-99"
    proj_path.write_text(json.dumps(proj_updated, indent=2), encoding="utf-8")

    render_calls.clear()
    universal_engine.build_project(proj_path)
    assert render_calls == [0]
