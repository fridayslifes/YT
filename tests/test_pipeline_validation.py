"""Offline regressions for the media and asset checks shared by both release paths."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import pipeline, visual_engine


def test_stat_card_wraps_a_long_title_instead_of_clipping_it():
    """A citation stat is the one number the video exists to show; it must not run off the card.

    SH-18's first render drew "23 Labs, 2,141 Participants" on a single unwrapped line inside a box
    clamped to 928 px, so the centred title hung off both edges and shipped as
    "3 Labs, 2,141 Participan".
    """
    from PIL import ImageFont

    from tools.build_video import FONT_DIR, stat_card_box

    title_font = ImageFont.truetype(str(FONT_DIR / "BeVietnamPro-Bold.ttf"), 78)
    sub_font = ImageFont.truetype(str(FONT_DIR / "BeVietnamPro-Medium.ttf"), 50)
    subtitle = "Pooled Ego-Depletion Effect (Hagger et al. 2016, p. 546)"

    wrapped = stat_card_box("23 Labs, 2,141 Participants", subtitle, title_font, sub_font, 928)
    single = stat_card_box("23 Labs", subtitle, title_font, sub_font, 928)
    assert wrapped.width <= 928, "the card itself must stay inside the frame"
    assert wrapped.height > single.height, "the long title took a second line instead of overflowing"
    assert title_font.getlength("23 Labs, 2,141 Participants") > 928 - 2 * 26 - 24, (
        "the fixture no longer exercises the overflow path"
    )

    with pytest.raises(ValueError, match="cannot fit"):
        stat_card_box("P" * 120, subtitle, title_font, sub_font, 928)


def test_stat_card_budget_uses_the_measured_caption_height():
    """The card must leave the room the caption actually needs, after the transform enlarges it.

    SH-19's stat scene failed with "no room for the caption at 18.73s ... 303px of caption against
    1 active text layer(s)". Two arithmetic errors caused it: the budget clamped the card before
    _apply_3d_card_perspective added its 28 px pad to top and bottom, and it reserved 3x the caption
    font (276 px) for a group that wraps to two lines and measures 303 px.
    """
    from PIL import ImageFont

    from tools import build_video as bv

    fmt = bv.FORMATS["short"]
    H = fmt["H"]
    band = int(H * (bv.SHORT_TEXT_BAND[1] - bv.SHORT_TEXT_BAND[0]))

    renderer = bv.CaptionRenderer(fmt, bv.FONT_DIR / "BeVietnamPro-Bold.ttf")
    # A real group is at most fmt["max_words"] words and fmt["max_chars"] characters; this pair is
    # inside both caps and still wraps, which is what made the caption taller than the estimate.
    group = [{"disp": w, "start": 0.0, "end": 0.4} for w in ("goals", "clustered")]
    assert len(group) <= fmt["max_words"] and sum(len(w["disp"]) for w in group) <= fmt["max_chars"] + 2
    measured = max(renderer.layer(0, group, a).height for a in range(len(group)))
    assert measured > int(fmt["font"] * 3), (
        "the fixture no longer exercises a wrapping caption; the estimate would pass by accident"
    )

    card_max_h = band - measured - 32 - 2 * bv.CARD_PERSPECTIVE_PAD
    title_font = ImageFont.truetype(str(bv.FONT_DIR / "BeVietnamPro-Bold.ttf"), int(fmt["font"] * 0.85))
    sub_font = ImageFont.truetype(str(bv.FONT_DIR / "BeVietnamPro-Medium.ttf"), int(fmt["note_font"] * 1.15))
    card = bv.stat_card_box(
        "3 Studies, 66,062 Goals",
        "Archival field data (Dai, Milkman & Riis 2014, p. 11)",
        title_font,
        sub_font,
        int(fmt["W"] * 0.86),
        max_h=card_max_h,
    )
    grown = bv._apply_3d_card_perspective(card)
    assert grown.height - card.height == 2 * bv.CARD_PERSPECTIVE_PAD, (
        "the transform's growth changed; the budget constant has to follow it"
    )

    card_top = int(H * fmt["stat_y"])
    free_below = int(H * bv.SHORT_TEXT_BAND[1]) - (card_top + grown.height + 16)
    assert free_below >= measured, (
        f"a {measured}px caption needs room inside the band: only {free_below}px left under the card"
    )


def test_precompose_reports_each_active_missing_shot(tmp_path, monkeypatch):
    project_dir = tmp_path / "short_test"
    (project_dir / "images").mkdir(parents=True)
    (project_dir / "images" / "present.jpg").write_bytes(b"image")
    project = {
        "format": "short",
        "scenes": [
            {
                "text": "A scene with two distinct visual shots.",
                "image": "images/unused-primary.jpg",
                "shots": [
                    {"image": "images/present.jpg"},
                    {"image": "images/missing.jpg"},
                ],
            }
        ],
    }
    project_path = project_dir / "project.json"
    project_path.write_text(json.dumps(project), encoding="utf-8")
    monkeypatch.setattr(
        pipeline,
        "verify_image_precision_cached",
        lambda _: {"valid": True, "precision": 1.0, "recall": 1.0, "size_kb": 1},
    )

    issues = pipeline.pre_compose_validate(project_path)

    assert any("Scene 1 missing asset: images/missing.jpg" in issue for issue in issues)
    assert not any("unused-primary.jpg" in issue for issue in issues)


def test_precompose_reports_missing_selected_video_even_when_an_image_exists(tmp_path, monkeypatch):
    project_dir = tmp_path / "short_test"
    (project_dir / "images").mkdir(parents=True)
    (project_dir / "images" / "fallback.jpg").write_bytes(b"image")
    project_path = project_dir / "project.json"
    project_path.write_text(
        json.dumps({"format": "short", "scenes": [{"text": "A scene.", "video": "videos/missing.mp4", "image": "images/fallback.jpg"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        pipeline,
        "verify_image_precision_cached",
        lambda _: {"valid": True, "precision": 1.0, "recall": 1.0, "size_kb": 1},
    )

    assert any(
        "Scene 1 missing asset: videos/missing.mp4" in issue
        for issue in pipeline.pre_compose_validate(project_path)
    )


def test_precompose_rejects_a_scene_with_no_visual_source(tmp_path):
    project_path = tmp_path / "project.json"
    project_path.write_text(json.dumps({"format": "short", "scenes": [{"text": "No visual source."}]}), encoding="utf-8")

    assert any("Scene 1 missing asset" in issue for issue in pipeline.pre_compose_validate(project_path))


@pytest.mark.parametrize("image_exists", [False, True])
def test_precompose_validates_promoted_video_instead_of_image(tmp_path, monkeypatch, image_exists):
    (tmp_path / "images").mkdir()
    (tmp_path / "videos").mkdir()
    if image_exists:
        (tmp_path / "images" / "s01.jpg").write_bytes(b"unused image")
    clip = tmp_path / "videos" / "s01.mp4"
    clip.write_bytes(b"selected video")
    project_path = tmp_path / "project.json"
    project_path.write_text(json.dumps({"scenes": [{"text": "Subscribe for the next video.", "image": "images/s01.jpg"}]}))
    checked = []

    def check_motion(path, **kwargs):
        checked.append(path)
        return {"valid": False, "score": "invalid promoted clip"}

    monkeypatch.setattr(pipeline, "verify_motion_quality_cached", check_motion)
    monkeypatch.setattr(
        pipeline, "verify_image_precision_cached",
        lambda path: pytest.fail("renderer replaces this image with its matching video"),
    )

    issues = pipeline.pre_compose_validate(project_path)

    assert checked == [clip]
    assert not any("missing asset" in issue for issue in issues)
    assert any("invalid promoted clip" in issue for issue in issues)


@pytest.mark.parametrize(
    "field,value,diagnostic",
    [
        ("width", 720, "dimensions are 720x1920, expected 1080x1920"),
        ("r_frame_rate", "24/1", "frame rate is 24/1, expected 30/1"),
        ("sample_rate", "44100", "audio is aac @ 44100 Hz, expected AAC @ 48000 Hz"),
        ("codec_name", "mp3", "audio is mp3 @ 48000 Hz, expected AAC @ 48000 Hz"),
        ("duration", "4.9", "duration is 4.9s, expected a finite duration of at least 5s"),
        ("duration", "4.999", "duration is 4.999s, expected a finite duration of at least 5s"),
        ("duration", "inf", "duration is infs, expected a finite duration of at least 5s"),
        ("duration", "-inf", "duration is -infs, expected a finite duration of at least 5s"),
        ("duration", "NaN", "duration is nans, expected a finite duration of at least 5s"),
        ("format_name", "matroska", "container is matroska, expected MP4"),
    ],
)
def test_media_probe_rejects_wrong_stream_or_container(tmp_path, monkeypatch, field, value, diagnostic):
    mp4 = tmp_path / "render.mp4"
    mp4.write_bytes(b"synthetic fixture")
    probe = {
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920, "r_frame_rate": "30/1", "duration": "38.0"},
            {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "duration": "38.0"},
        ],
        "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "38.0", "size": "10000", "bit_rate": "2000000"},
    }
    target = probe["format"] if field in {"duration", "format_name"} else probe["streams"][1 if field in {"sample_rate", "codec_name"} else 0]
    target[field] = value
    monkeypatch.setattr(pipeline, "run_process", lambda *a, **kw: SimpleNamespace(stdout=json.dumps(probe)))
    monkeypatch.setattr(visual_engine, "verify_video_decodable", lambda *a, **kw: (True, "decoded"))

    meta = pipeline.verify_rendered_mp4(mp4)

    assert meta["valid"] is False
    assert diagnostic in meta["error"]


@pytest.mark.parametrize("duration", ["5.0", "38.0"])
def test_media_probe_accepts_matching_stream_and_container(tmp_path, monkeypatch, duration):
    mp4 = tmp_path / "render.mp4"
    mp4.write_bytes(b"synthetic fixture")
    probe = {
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920, "r_frame_rate": "30/1", "duration": duration},
            {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "duration": duration},
        ],
        "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": duration, "size": "10000", "bit_rate": "2000000"},
    }
    monkeypatch.setattr(pipeline, "run_process", lambda *a, **kw: SimpleNamespace(stdout=json.dumps(probe)))
    monkeypatch.setattr(visual_engine, "verify_video_decodable", lambda *a, **kw: (True, "decoded"))

    assert pipeline.verify_rendered_mp4(mp4)["valid"] is True


def test_media_probe_preserves_stderr_diagnostics(tmp_path, monkeypatch):
    mp4 = tmp_path / "broken.mp4"
    mp4.write_bytes(b"bad headers")

    def broken_probe(*args, **kwargs):
        raise pipeline.subprocess.CalledProcessError(1, args[0], stderr="moov atom not found")

    monkeypatch.setattr(pipeline, "run_process", broken_probe)

    meta = pipeline.verify_rendered_mp4(mp4)

    assert meta["valid"] is False
    assert "moov atom not found" in meta["error"]


def test_media_probe_honors_explicit_timeout(tmp_path, monkeypatch):
    mp4 = tmp_path / "slow.mp4"
    mp4.write_bytes(b"slow probe")

    def timed_out(*args, **kwargs):
        if kwargs.get("timeout_s") != 0.01:
            pytest.fail("media probe must receive the caller's timeout")
        raise pipeline.subprocess.TimeoutExpired(args[0], kwargs["timeout_s"])

    monkeypatch.setattr(pipeline, "run_process", timed_out)

    meta = pipeline.verify_rendered_mp4(mp4, probe_timeout_s=0.01)

    assert meta["valid"] is False
    assert "ffprobe" in meta["error"]


def test_chapters_command_exits_nonzero_for_invalid_chapters(monkeypatch, tmp_path):
    transcript = tmp_path / "transcript.srt"
    transcript.write_text("", encoding="utf-8")
    monkeypatch.setattr(pipeline.youtube_skills, "generate_chapters", lambda _: {"valid": False, "chapters": []})
    monkeypatch.setattr(sys, "argv", ["pipeline.py", "--chapters", str(transcript)])

    assert pipeline.main() == 1


def test_studio_command_preserves_child_failure_code(monkeypatch):
    monkeypatch.setattr(pipeline.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=7))
    monkeypatch.setattr(sys, "argv", ["pipeline.py", "--studio-3d"])

    assert pipeline.main() == 7


def test_package_lint_command_reports_issues(monkeypatch):
    monkeypatch.setattr(pipeline.youtube_skills, "check_packaging", lambda _: {"issues": [("shorts-case", "lowercase") ]})
    monkeypatch.setattr(sys, "argv", ["pipeline.py", "--lint-package", "--title", "Example #Shorts"])

    assert pipeline.main() == 1


@pytest.fixture
def scene_build(tmp_path, monkeypatch):
    """Keep the coordinator and cache real; replace only expensive/external operations."""
    monkeypatch.setattr(pipeline, "YT_ROOT", tmp_path)
    project_dir = tmp_path / "short_manifest"
    for name in ("images", "videos"):
        (project_dir / name).mkdir(parents=True)
    scenes = []
    for number in range(1, 9):
        stem = f"s{number:02d}"
        (project_dir / "images" / f"{stem}.jpg").write_bytes(stem.encode())
        (project_dir / "videos" / f"{stem}.mp4").write_bytes(b"untracked clip")
        scenes.append({"id": stem, "text": f"Schema-valid narration for scene {number}.",
                       "caption": f"Schema-valid narration for scene {number}.",
                       "image": f"images/{stem}.jpg", "video": f"videos/{stem}.mp4",
                       "prompt": f"Image {stem}", "duration": 3.5, "preset": "depthflow_orbit"})
    path = project_dir / "project.json"
    path.write_text(json.dumps({"schema_version": 2, "id": "SH-99", "format": "short",
                                "variant": "cinematic_35mm", "channel_id": "test_channel",
                                "voice": "kokoro", "scenes": scenes}))
    rendered = []
    bad_motion = set()

    def render(source, output, *, preset, duration, target_w, target_h):
        rendered.append(output.name)
        output.write_bytes(f"rendered-{len(rendered)}-{source.read_bytes()!r}-{preset}-{duration}-{target_w}-{target_h}".encode())
        return True

    def compose(project, output, **kwargs):
        output.parent.mkdir(exist_ok=True)
        output.write_bytes(b"master fixture")
        return output

    monkeypatch.setattr(pipeline.audio_bank, "ensure_studio_sfx_pack", lambda **kwargs: {})
    # Keep this render-identity fixture offline: production derives duration from
    # narration, while this fixture varies the explicit duration input directly.
    monkeypatch.setattr(
        pipeline,
        "compute_scene_durations",
        lambda project, cache: [scene["duration"] for scene in project["scenes"]],
    )
    monkeypatch.setattr(visual_engine, "generate_scene_image", lambda *a, **kw: pytest.fail("no model generation"))
    monkeypatch.setattr(visual_engine, "render_3d_spatial_scene", render)
    monkeypatch.setattr(
        visual_engine, "verify_encoded_output",
        lambda p: (p.is_file() and p.read_bytes().startswith(b"rendered-"), "invalid scene fixture"),
    )
    monkeypatch.setattr(pipeline, "verify_motion_quality_cached", lambda p, **kw: {"valid": p.name not in bad_motion})
    monkeypatch.setattr(pipeline, "pre_compose_validate", lambda p: [])
    monkeypatch.setattr(pipeline.build_video, "build", compose)
    monkeypatch.setattr(pipeline, "verify_rendered_mp4", lambda *a, **kw: {"valid": True})
    monkeypatch.setattr(pipeline.tracker, "read_tracker_row", lambda _: {})
    monkeypatch.setattr(pipeline, "append_to_tracker", lambda **kw: True)
    return SimpleNamespace(path=path, rendered=rendered, bad_motion=bad_motion)


def test_build_manifest_requires_records_then_reuses_identical_inputs(scene_build):
    pipeline.build_and_verify(scene_build.path)
    assert scene_build.rendered == [f"s{number:02d}.mp4" for number in range(1, 9)]
    scene_build.rendered.clear()

    pipeline.build_and_verify(scene_build.path)

    assert scene_build.rendered == []
    authored = json.loads(scene_build.path.read_text())
    assert "render_manifest" not in authored
    assert "fingerprint" not in json.dumps(authored)
    manifest = json.loads((scene_build.path.parent / "cache" / "render_manifest.json").read_text())
    assert set(manifest["scenes"]) == {str(number) for number in range(8)}


@pytest.mark.parametrize("changed", ["prompt", "source", "source_stem", "duration", "preset", "steps", "output", "missing_record", "motion"])
def test_build_manifest_rerenders_only_the_affected_scene(scene_build, changed):
    pipeline.build_and_verify(scene_build.path)
    scene_build.rendered.clear()
    project = json.loads(scene_build.path.read_text())
    if changed in {"prompt", "duration", "preset", "steps"}:
        project["scenes"][0][changed] = {
            "prompt": "A replacement prompt", "duration": 4.5,
            "preset": "depthflow_dolly", "steps": 8,
        }[changed]
        scene_build.path.write_text(json.dumps(project))
    elif changed == "source":
        (scene_build.path.parent / "images" / "s01.jpg").write_bytes(b"updated image")
    elif changed == "source_stem":
        source = scene_build.path.parent / "images" / "s01.jpg"
        renamed = source.with_name("renamed.jpg")
        source.rename(renamed)
        project["scenes"][0]["image"] = "images/renamed.jpg"
        scene_build.path.write_text(json.dumps(project))
    elif changed == "output":
        (scene_build.path.parent / "videos" / "s01.mp4").write_bytes(b"tampered clip")
    elif changed == "missing_record":
        path = scene_build.path.parent / "cache" / "render_manifest.json"
        manifest = json.loads(path.read_text())
        del manifest["scenes"]["0"]
        path.write_text(json.dumps(manifest))
    else:
        scene_build.bad_motion.add("s01.mp4")

    pipeline.build_and_verify(scene_build.path)

    assert scene_build.rendered == ["s01.mp4"]


@pytest.mark.parametrize("changed", ["dimensions", "renderer", "force"])
def test_build_manifest_invalidates_all_scenes_when_shared_render_inputs_change(scene_build, monkeypatch, changed):
    from tools import render_manifest

    pipeline.build_and_verify(scene_build.path)
    scene_build.rendered.clear()
    if changed == "dimensions":
        project = json.loads(scene_build.path.read_text())
        project["format"] = "long"
        scene_build.path.write_text(json.dumps(project))
    elif changed == "renderer":
        monkeypatch.setattr(render_manifest, "RENDERER_CONTRACT_VERSION", "test-new-contract")

    pipeline.build_and_verify(scene_build.path, force_motion=changed == "force")

    assert scene_build.rendered == [f"s{number:02d}.mp4" for number in range(1, 9)]


@pytest.mark.parametrize("render_result", [False, True])
def test_build_manifest_rejects_stale_output_before_composition_after_failed_render(scene_build, monkeypatch, render_result):
    pipeline.build_and_verify(scene_build.path)
    manifest_path = scene_build.path.parent / "cache" / "render_manifest.json"
    original = manifest_path.read_bytes()
    project = json.loads(scene_build.path.read_text())
    project["scenes"][0]["prompt"] = "Changed prompt requiring a new render"
    scene_build.path.write_text(json.dumps(project))
    output = scene_build.path.parent / "videos" / "s01.mp4"
    old_clip = output.read_bytes()
    monkeypatch.setattr(visual_engine, "render_3d_spatial_scene", lambda *a, **kw: render_result)
    monkeypatch.setattr(pipeline.build_video, "build", lambda *a, **kw: pytest.fail("stale scene reached composition"))

    with pytest.raises(RuntimeError, match="Scene 1"):
        pipeline.build_and_verify(scene_build.path)

    assert output.read_bytes() == old_clip
    assert manifest_path.read_bytes() == original


def test_build_manifest_allows_fresh_valid_clip_with_motion_warning_without_recording_it(scene_build, monkeypatch):
    pipeline.build_and_verify(scene_build.path)
    manifest_path = scene_build.path.parent / "cache" / "render_manifest.json"
    original = manifest_path.read_bytes()
    project = json.loads(scene_build.path.read_text())
    project["scenes"][0]["prompt"] = "Changed prompt requiring a new render"
    scene_build.path.write_text(json.dumps(project))

    def motion_warning(source, output, **kwargs):
        output.write_bytes(b"rendered-motion-warning")
        return False

    monkeypatch.setattr(visual_engine, "render_3d_spatial_scene", motion_warning)

    assert pipeline.build_and_verify(scene_build.path)["valid"] is True
    assert (scene_build.path.parent / "videos" / "s01.mp4").read_bytes() == b"rendered-motion-warning"
    assert manifest_path.read_bytes() == original


def test_build_manifest_rejects_fresh_corrupt_clip_and_preserves_canonical_output(scene_build, monkeypatch):
    pipeline.build_and_verify(scene_build.path)
    output = scene_build.path.parent / "videos" / "s01.mp4"
    original = output.read_bytes()

    def corrupt_render(source, destination, **kwargs):
        destination.write_bytes(b"corrupt fresh clip")
        return False

    monkeypatch.setattr(visual_engine, "render_3d_spatial_scene", corrupt_render)
    monkeypatch.setattr(pipeline.build_video, "build", lambda *a, **kw: pytest.fail("corrupt scene reached composition"))

    with pytest.raises(RuntimeError, match="Scene 1"):
        pipeline.build_and_verify(scene_build.path, force_motion=True)

    assert output.read_bytes() == original


# --------------------------------------------------------------------------- #
# Local-only Kokoro speech routing & cache isolation
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("voice", ["am_adam", "af_heart", "bm_george", "bf_emma", "kokoro"])
def test_tts_cached_routes_supported_voices_to_local_kokoro(tmp_path, monkeypatch, voice):
    from tools import build_video as bv
    from tools.schemas import KOKORO_VOICES

    assert voice in KOKORO_VOICES
    assert not hasattr(bv, "_synthesize_edge"), "_synthesize_edge must be removed from build_video"
    assert "edge_tts" not in bv.__dict__, "edge_tts import must be removed from build_video"

    calls = []

    def fake_kokoro(text, mp3, voice_spec="am_adam"):
        calls.append((text, mp3, voice_spec))
        mp3.write_bytes(b"kokoro-mp3-" * 40)
        return [{"text": "Narration", "start": 0.05, "end": 0.45}]

    monkeypatch.setattr(bv, "_synthesize_kokoro", fake_kokoro)
    cache_dir = tmp_path / "cache"

    mp3_path, words = bv.tts_cached("Narration line.", voice, "+1%", "-2Hz", cache_dir)

    assert calls == [("Narration line.", mp3_path, voice)]
    assert mp3_path.parent == cache_dir
    assert mp3_path.is_file()
    assert words == [{"text": "Narration", "start": 0.05, "end": 0.45}]


@pytest.mark.parametrize(
    "invalid_voice",
    [
        "en-US-AndrewNeural",
        "en-US-JennyNeural",
        "af_unknown",
        "kokoro_blend",
        "KOKORO",
        "",
        "   ",
        None,
        123,
        True,
        False,
        [],
        {},
    ],
)
def test_tts_cached_rejects_unknown_or_malformed_voice_before_side_effects(tmp_path, monkeypatch, invalid_voice):
    from tools import build_video as bv

    monkeypatch.setattr(
        bv,
        "_synthesize_kokoro",
        lambda *a, **kw: pytest.fail("invalid voice must fail before synthesis"),
    )
    cache_dir = tmp_path / "cache_must_not_be_created"

    with pytest.raises(ValueError, match="voice"):
        bv.tts_cached("Test narration.", invalid_voice, "+1%", "-2Hz", cache_dir)

    assert not cache_dir.exists()


@pytest.mark.parametrize("bad_voice", ["en-US-AndrewNeural", "af_unknown", "kokoro_custom"])
def test_tts_cached_existing_cache_cannot_bypass_voice_validation(tmp_path, monkeypatch, bad_voice):
    import hashlib
    from tools import build_video as bv

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)
    namespace = getattr(bv, "TTS_CACHE_NAMESPACE", "kokoro-v1.0-local")
    for raw_key in (
        f"{bad_voice}|+1%|-2Hz|Cached text",
        f"{namespace}|{bad_voice}|+1%|-2Hz|Cached text",
    ):
        digest = hashlib.sha1(raw_key.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
        (cache_dir / f"{digest}.mp3").write_bytes(b"cached-audio-" * 40)
        (cache_dir / f"{digest}.json").write_text(json.dumps([{"text": "Cached", "start": 0.0, "end": 0.3}]))

    monkeypatch.setattr(
        bv,
        "_synthesize_kokoro",
        lambda *a, **kw: pytest.fail("invalid voice must fail before synthesis"),
    )

    with pytest.raises(ValueError, match="voice"):
        bv.tts_cached("Cached text", bad_voice, "+1%", "-2Hz", cache_dir)


def test_tts_cached_reuses_valid_cache_and_invalidates_on_text_or_voice_change(tmp_path, monkeypatch):
    from tools import build_video as bv

    calls = []

    def fake_kokoro(text, mp3, voice_spec="am_adam"):
        calls.append((text, voice_spec, mp3.name))
        mp3.write_bytes(f"audio-{len(calls)}-{voice_spec}-{text}".encode("utf-8") * 20)
        return [{"text": text.split()[0], "start": 0.0, "end": 0.4, "call": len(calls)}]

    monkeypatch.setattr(bv, "_synthesize_kokoro", fake_kokoro)
    cache_dir = tmp_path / "cache"

    mp3_a1, words_a1 = bv.tts_cached("Alpha script.", "am_adam", "+1%", "-2Hz", cache_dir)
    mp3_a2, words_a2 = bv.tts_cached("Alpha script.", "am_adam", "+1%", "-2Hz", cache_dir)

    assert len(calls) == 1
    assert mp3_a1 == mp3_a2
    assert words_a1 == words_a2

    mp3_b, words_b = bv.tts_cached("Beta script.", "am_adam", "+1%", "-2Hz", cache_dir)
    assert len(calls) == 2
    assert mp3_b != mp3_a1
    assert words_b[0]["call"] == 2

    mp3_c, words_c = bv.tts_cached("Alpha script.", "af_heart", "+1%", "-2Hz", cache_dir)
    assert len(calls) == 3
    assert mp3_c not in {mp3_a1, mp3_b}
    assert words_c[0]["call"] == 3


def test_tts_cached_isolates_old_unversioned_backend_cache(tmp_path, monkeypatch):
    import hashlib
    from tools import build_video as bv

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)
    legacy_key = hashlib.sha1("am_adam|+1%|-2Hz|Legacy line.".encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
    legacy_mp3 = cache_dir / f"{legacy_key}.mp3"
    legacy_meta = cache_dir / f"{legacy_key}.json"
    legacy_mp3.write_bytes(b"legacy-unverified-backend-" * 30)
    legacy_meta.write_text(json.dumps([{"text": "legacy", "start": 0.0, "end": 0.2}]))

    calls = []

    def fake_kokoro(text, mp3, voice_spec="am_adam"):
        calls.append((text, voice_spec, mp3))
        mp3.write_bytes(b"fresh-local-kokoro-" * 30)
        return [{"text": "Legacy", "start": 0.05, "end": 0.55}]

    monkeypatch.setattr(bv, "_synthesize_kokoro", fake_kokoro)

    mp3_path, words = bv.tts_cached("Legacy line.", "am_adam", "+1%", "-2Hz", cache_dir)

    assert len(calls) == 1
    assert mp3_path != legacy_mp3
    assert mp3_path.read_bytes() == b"fresh-local-kokoro-" * 30
    assert words == [{"text": "Legacy", "start": 0.05, "end": 0.55}]


@pytest.mark.parametrize("bad_voice", ["en-US-AndrewNeural", "af_unknown", "KOKORO", "", None, True, 99])
def test_synthesize_kokoro_rejects_unknown_voice_directly_before_model_load(tmp_path, monkeypatch, bad_voice):
    from tools import build_video as bv

    monkeypatch.setattr(bv, "KOKORO_DIR", tmp_path / "missing_models")
    out_mp3 = tmp_path / "out.mp3"

    with pytest.raises(ValueError, match="voice"):
        bv._synthesize_kokoro("Direct synthesis test.", out_mp3, voice_spec=bad_voice)

    assert not out_mp3.exists()


def test_synthesize_kokoro_uses_exact_voice_styles_and_only_blends_explicit_kokoro(tmp_path, monkeypatch):
    import numpy as np
    from tools import build_video as bv

    model_dir = tmp_path / "kokoro_models"
    model_dir.mkdir()
    (model_dir / "kokoro-v1.0.onnx").write_bytes(b"onnx")
    (model_dir / "voices-v1.0.bin").write_bytes(b"voices")
    monkeypatch.setattr(bv, "KOKORO_DIR", model_dir)
    monkeypatch.setattr(bv, "_KOKORO_INSTANCE", None)

    style_vectors = {
        "am_adam": np.array([1.0, 0.0], dtype=np.float32),
        "bm_george": np.array([0.0, 1.0], dtype=np.float32),
        "af_heart": np.array([0.2, 0.8], dtype=np.float32),
    }
    create_calls = []

    class FakeKokoro:
        def __init__(self, onnx_path, voices_path):
            self.onnx_path = onnx_path
            self.voices_path = voices_path

        def get_voices(self):
            return list(style_vectors)

        def get_voice_style(self, name):
            return style_vectors[name]

        def create(self, text, voice, speed, lang):
            create_calls.append((text, np.array(voice, dtype=np.float32), speed, lang))
            return np.zeros(2400, dtype=np.float32), 24000

    import kokoro_onnx
    import soundfile as sf

    monkeypatch.setattr(kokoro_onnx, "Kokoro", FakeKokoro)
    monkeypatch.setattr(sf, "write", lambda path, samples, sr: Path(path).write_bytes(b"wav"))
    monkeypatch.setattr(
        bv.subprocess,
        "run",
        lambda cmd, **kw: Path(cmd[-1]).write_bytes(b"mp3" * 120),
    )
    monkeypatch.setattr(bv, "decode_audio", lambda path, af=None: np.zeros(bv.SR, dtype=np.float32))
    monkeypatch.setattr(
        bv,
        "_align_with_faster_whisper",
        lambda mp3, txt, aud: [{"text": "Hello", "start": 0.0, "end": 0.4}],
    )

    bv._synthesize_kokoro("Hello world", tmp_path / "adam.mp3", voice_spec="am_adam")
    assert np.allclose(create_calls[-1][1], style_vectors["am_adam"])

    bv._synthesize_kokoro("Hello world", tmp_path / "heart.mp3", voice_spec="af_heart")
    assert np.allclose(create_calls[-1][1], style_vectors["af_heart"])

    bv._synthesize_kokoro("Hello world", tmp_path / "house.mp3", voice_spec="kokoro")
    expected_blend = (0.68 * style_vectors["am_adam"] + 0.32 * style_vectors["bm_george"]).astype(np.float32)
    assert np.allclose(create_calls[-1][1], expected_blend)

    # A schema-listed voice absent from the loaded model bin must fail directly, not blend.
    with pytest.raises(ValueError, match="voice"):
        bv._synthesize_kokoro("Hello world", tmp_path / "missing_in_bin.mp3", voice_spec="af_bella")

