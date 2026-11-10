"""CPU-only acceptance tests against real local FFmpeg output."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from tools import pipeline, visual_engine

pytestmark = pytest.mark.media


def _encode(path, audio_duration="5.2"):
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=1080x1920:r=30:d=5.2",
            "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={audio_duration}",
            "-c:v", "libx264", "-preset", "ultrafast", "-threads", "2", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "48000", "-movflags", "+faststart", str(path),
        ],
        check=True, capture_output=True, text=True, timeout=60,
    )
    return path


@pytest.fixture
def real_mp4(tmp_path):
    return _encode(tmp_path / "valid.mp4")


def test_real_h264_aac_render_is_decodable_and_synchronized(real_mp4):
    # Catches a verifier that trusts container headers without decoding real frames.
    meta = pipeline.verify_rendered_mp4(real_mp4)

    assert meta["valid"] is True, meta
    assert meta["tail_decodable"] is True
    assert meta["video_duration_s"] == pytest.approx(5.2, abs=0.04)
    assert meta["audio_duration_s"] == pytest.approx(5.2, abs=0.04)
    assert meta["av_duration_delta_s"] <= 0.250


def test_truncated_media_cannot_pass_on_readable_headers(real_mp4, tmp_path):
    # Faststart preserves the moov atom while truncation removes the tail packets.
    truncated = tmp_path / "truncated.mp4"
    shutil.copyfile(real_mp4, truncated)
    with truncated.open("r+b") as stream:
        stream.truncate(truncated.stat().st_size // 2)

    meta = pipeline.verify_rendered_mp4(truncated)

    assert meta["valid"] is False, meta
    assert "decode" in meta["error"].lower() or "probe" in meta["error"].lower()
    assert visual_engine.verify_video_decodable(truncated)[0] is False


def test_short_audio_cannot_pass_with_full_length_video(tmp_path):
    # Catches checking only the 5.2-second container duration while audio ends at 1s.
    divergent = _encode(tmp_path / "divergent.mp4", audio_duration="1")

    meta = pipeline.verify_rendered_mp4(divergent)

    assert meta["valid"] is False, meta
    assert meta["av_duration_delta_s"] == pytest.approx(4.2, abs=0.04)
    assert "duration" in meta["error"].lower()
