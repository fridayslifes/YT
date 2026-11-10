"""Unit tests for tools/encoder_config.py explicit encoder selection & validation."""

from __future__ import annotations

import sys
import pytest

from tools.encoder_config import (
    load_encoder_config,
    probe_encoder_support,
    resolve_encoder,
    resolve_platform_default_encoder,
)
from tools.errors import RenderingError


def test_load_encoder_config() -> None:
    cfg = load_encoder_config()
    assert isinstance(cfg, dict)
    assert "encoder" in cfg
    assert "h264_bitrate" in cfg


def test_resolve_platform_default_encoder() -> None:
    expected = "h264_videotoolbox" if sys.platform == "darwin" else "libx264"
    assert resolve_platform_default_encoder() == expected


def test_probe_encoder_support() -> None:
    assert probe_encoder_support("libx264") is True
    assert probe_encoder_support("nonexistent_video_encoder_12345") is False


def test_resolve_encoder_default() -> None:
    target, args = resolve_encoder()
    assert target in {"h264_videotoolbox", "libx264"}
    assert "-c:v" in args
    assert target in args


def test_resolve_encoder_explicit_supported() -> None:
    target, args = resolve_encoder("libx264", crf=21)
    assert target == "libx264"
    assert "-c:v" in args
    assert "libx264" in args
    assert "-crf" in args
    assert "21" in args


def test_resolve_encoder_fails_closed_on_unsupported_encoder() -> None:
    with pytest.raises(RenderingError) as exc_info:
        resolve_encoder("invalid_magic_encoder")
    assert exc_info.value.stage == "encoder_selection"


def test_resolve_encoder_fails_closed_on_unavailable_hardware_encoder(monkeypatch: pytest.MonkeyPatch) -> None:
    # If on Darwin, NVENC is not available; force probe to return False
    monkeypatch.setattr("tools.encoder_config.probe_encoder_support", lambda enc: False)
    with pytest.raises(RenderingError) as exc_info:
        resolve_encoder("h264_nvenc")
    assert exc_info.value.stage == "encoder_selection"
    assert "No fallback permitted" in str(exc_info.value)


def test_resolve_encoder_respects_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRAMEFORGE_ENCODER", "libx264")
    target, args = resolve_encoder()
    assert target == "libx264"
