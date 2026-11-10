"""Branding attachment - the step that finally puts the channel's stinger and end-screen slate
onto a finished render.

Nothing in this file runs ffmpeg: the two probes attach_branding uses (`_media_duration`,
`_video_identity`) are monkeypatched, which keeps the suite inside the constraint stated in
conftest.py while still covering every branch that decides whether a splice happens. The concat
itself was verified out-of-band against a synthetic 1920x1080/30fps/bt709 film (23.5s out, 30/1
preserved, captions shifted once).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import build_video
from tools.build_video import BRANDING_MASTERS, _shift_srt, attach_branding

IDENT = ("h264", "1920", "1080", "yuv420p", "tv", "bt709", "30/1")


def make_film(tmp_path: Path, branded: bool = False) -> Path:
    out = tmp_path / "output"
    out.mkdir(exist_ok=True)
    film = out / "lv_xx.mp4"
    film.write_bytes(b"\x00" * 64)
    (out / "lv_xx.srt").write_text(
        "1\n00:00:00,000 --> 00:00:03,000\nfirst cue\n\n"
        "2\n00:00:03,000 --> 00:00:06,000\nsecond cue\n",
        encoding="utf-8",
    )
    if branded:
        (out / "lv_xx.branding.json").write_text(json.dumps({
            "parts": ["intro_16x9.mp4", "lv_xx.mp4", "outro_16x9_endscreen.mp4"],
            "raw_dur": 6.0, "branded_dur": 23.5, "intro_shift": 2.5,
        }))
    return film


def stub_probes(monkeypatch, durations: dict[str, float], identity: tuple[str, ...] = IDENT) -> None:
    monkeypatch.setattr(build_video, "_media_duration", lambda p: durations[Path(p).name])
    monkeypatch.setattr(build_video, "_video_identity", lambda p: identity)


def test_no_branding_block_leaves_the_render_alone(tmp_path, monkeypatch):
    film = make_film(tmp_path)
    monkeypatch.setattr(build_video, "_media_duration",
                        lambda p: (_ for _ in ()).throw(AssertionError("probed a film that needs nothing")))
    assert attach_branding(film, {"format": "long"}) == film
    assert not (film.parent / "lv_xx.branding.json").exists()


def test_a_short_that_asks_for_branding_is_refused_with_the_reason(tmp_path):
    film = make_film(tmp_path)
    with pytest.raises(SystemExit) as exc:
        attach_branding(film, {"format": "short", "branding": {"intro": True}}),
    assert "Shorts loop" in str(exc.value)


def test_a_missing_master_names_the_command_that_makes_it(tmp_path, monkeypatch):
    film = make_film(tmp_path)
    monkeypatch.setattr(build_video, "BRANDING_DIR", tmp_path / "empty_assets")
    stub_probes(monkeypatch, {"lv_xx.mp4": 6.0})
    with pytest.raises(SystemExit) as exc:
        attach_branding(film, {"format": "long", "branding": {"outro": True}})
    assert "branding_engine.py" in str(exc.value)


def test_an_apostrophe_in_the_path_cannot_break_the_concat_list(tmp_path, monkeypatch):
    # The concat demuxer reads file '...' lines; an unescaped quote in a path would let the rest of
    # the line be parsed as options, so the guard refuses before writing the list at all.
    root = tmp_path / "it's a studio" / "channel_assets"
    root.mkdir(parents=True)
    for name in BRANDING_MASTERS.values():
        (root / name).write_bytes(b"\x00" * 32)
    film = make_film(root)
    monkeypatch.setattr(build_video, "BRANDING_DIR", root)
    stub_probes(monkeypatch, {"lv_xx.mp4": 6.0})
    with pytest.raises(SystemExit) as exc:
        attach_branding(film, {"format": "long", "branding": {"outro": True}})
    assert "concat list" in str(exc.value)


def test_a_mismatched_master_fails_instead_of_copying_a_second_codec_into_the_stream(
    tmp_path, monkeypatch
):
    film = make_film(tmp_path)
    for name in BRANDING_MASTERS.values():
        (tmp_path / name).write_bytes(b"\x00" * 32)
    monkeypatch.setattr(build_video, "BRANDING_DIR", tmp_path)
    stub_probes(monkeypatch, {"lv_xx.mp4": 6.0, **{n: 2.5 for n in BRANDING_MASTERS.values()}})
    monkeypatch.setattr(
        build_video, "_video_identity",
        lambda p: ("hevc", "1920", "1080", "yuv420p", "tv", "bt709", "30/1")
        if Path(p).name.startswith("intro") else IDENT,
    )
    with pytest.raises(SystemExit) as exc:
        attach_branding(film, {"format": "long", "branding": {"intro": True}})
    assert "changes codec mid-stream" in str(exc.value)


def test_a_second_attach_does_not_stack_a_second_slate(tmp_path, monkeypatch):
    film = make_film(tmp_path, branded=True)
    # The film already measures the branded duration in the marker, so attach must return before it
    # probes a master or runs ffmpeg.
    monkeypatch.setattr(build_video, "_media_duration", lambda p: 23.5)
    assert attach_branding(film, {"format": "long", "branding": {"intro": True, "outro": True}}) == film
    assert film.read_bytes() == b"\x00" * 64, "the branded file must be untouched, not concatenated again"


def test_a_freshly_rerendered_film_brands_even_though_the_marker_is_stale(tmp_path, monkeypatch):
    film = make_film(tmp_path, branded=True)
    for name in BRANDING_MASTERS.values():
        (tmp_path / name).write_bytes(b"\x00" * 32)
    monkeypatch.setattr(build_video, "BRANDING_DIR", tmp_path)
    # raw 6.0s no longer matches the marker's 23.5s, so the marker must not veto the splice; the run
    # then dies at the concat because these are not real MP4s, which is the point: it tried.
    stub_probes(monkeypatch, {"lv_xx.mp4": 6.0, **{n: 2.5 for n in BRANDING_MASTERS.values()}})
    with pytest.raises(SystemExit) as exc:
        attach_branding(film, {"format": "long", "branding": {"outro": True}})
    assert "concat" in str(exc.value).lower()


def test_the_srt_moves_by_exactly_the_intro_and_keeps_its_words(tmp_path):
    cues = [
        "1\n00:00:00,000 --> 00:00:03,000\nfirst cue",
        "2\n00:01:59,500 --> 00:02:02,250\nsecond cue",
    ]
    p = tmp_path / "lv_xx.srt"
    p.write_text("\n\n".join(cues) + "\n", encoding="utf-8")
    _shift_srt(p, 2.5)
    text = p.read_text(encoding="utf-8")
    assert "00:00:02,500 --> 00:00:05,500" in text, text
    assert "00:02:02,000 --> 00:02:04,750" in text, text
    assert "first cue" in text and "second cue" in text


def test_the_srt_shift_is_a_noop_without_an_intro_or_a_sidecar(tmp_path):
    srt = tmp_path / "lv_xx.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:03,000\nfirst cue\n", encoding="utf-8")
    _shift_srt(srt, 0.0)
    assert srt.read_text(encoding="utf-8").startswith("1\n00:00:00,000")
    _shift_srt(tmp_path / "missing.srt", 2.5)


def test_every_long_form_ships_an_end_screen(repo_root, project_files):
    """A long-form with no slate is a video that never asks for the subscription.

    YouTube only lets the subscribe and next-video elements sit in the last 20 seconds, and the
    channel renders a 15s canvas for exactly that. Shorts are excluded by rule - see the refusal in
    attach_branding().
    """
    long_form = [p for p in project_files if p.parts[-3] == "long_form"]
    offenders = []
    for p in long_form:
        proj = json.loads(p.read_text(encoding="utf-8"))
        if not (proj.get("branding") or {}).get("outro"):
            offenders.append(p.parent.name)
    assert not offenders, f"long-form renders with no end screen: {offenders}"
