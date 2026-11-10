"""Explicit Hardware & Software Video Encoder Configuration (Rule B Compliant).

Provides explicit encoder selection from configs/encoder.yaml, environment variables,
or explicit project settings. Fails closed with typed RenderingError when an unavailable
encoder is requested, prohibiting silent downgrade loops.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from tools.errors import RenderingError

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "configs" / "encoder.yaml"

SUPPORTED_ENCODERS = frozenset({"auto", "h264_videotoolbox", "libx264", "h264_nvenc"})
_PROBE_CACHE: Dict[str, bool] = {}


def probe_encoder_support(encoder_name: str) -> bool:
    """Probes ffmpeg once to determine if an encoder is usable on the current machine."""
    if encoder_name in _PROBE_CACHE:
        return _PROBE_CACHE[encoder_name]

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        _PROBE_CACHE[encoder_name] = False
        return False

    cmd = [
        ffmpeg_bin,
        "-v", "error",
        "-f", "lavfi",
        "-i", "color=c=black:s=64x64:r=30:d=0.05",
        "-frames:v", "1",
        "-c:v", encoder_name,
        "-f", "null",
        "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=5)
        usable = (proc.returncode == 0)
    except Exception:
        usable = False

    _PROBE_CACHE[encoder_name] = usable
    return usable


def load_encoder_config() -> dict:
    """Loads encoder configuration from configs/encoder.yaml."""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                if isinstance(data, dict):
                    return data
        except Exception as exc:
            raise RenderingError(
                stage="encoder_config_load",
                artifact=str(CONFIG_PATH),
                cause=f"Failed to parse encoder config at {CONFIG_PATH}: {exc}",
            ) from exc
    return {
        "encoder": "auto",
        "h264_bitrate": "14M",
        "libx264_crf": 18,
        "libx264_preset": "fast",
        "fail_on_unavailable": True,
    }


def resolve_platform_default_encoder() -> str:
    """Determines standard default encoder per operating platform."""
    if sys.platform == "darwin":
        return "h264_videotoolbox"
    return "libx264"


def resolve_encoder(
    requested_encoder: Optional[str] = None,
    *,
    bitrate: Optional[str] = None,
    crf: Optional[int] = None,
    preset: Optional[str] = None,
) -> Tuple[str, List[str]]:
    """Resolves an explicit encoder and its CLI arguments.

    Fails closed with RenderingError if the target encoder is unavailable.
    """
    cfg = load_encoder_config()
    target = requested_encoder or os.environ.get("FRAMEFORGE_ENCODER") or cfg.get("encoder") or "auto"
    target = target.strip().lower()

    if target not in SUPPORTED_ENCODERS:
        raise RenderingError(
            stage="encoder_selection",
            artifact=target,
            cause=f"Unsupported encoder '{target}'. Must be one of {sorted(SUPPORTED_ENCODERS)}.",
        )

    if target == "auto":
        target = resolve_platform_default_encoder()

    if not probe_encoder_support(target):
        raise RenderingError(
            stage="encoder_selection",
            artifact=target,
            cause=f"Configured encoder '{target}' is not supported or unavailable in ffmpeg. No fallback permitted per Rule B.",
        )

    eff_bitrate = bitrate or str(cfg.get("h264_bitrate", "14M"))
    eff_crf = crf if crf is not None else int(cfg.get("libx264_crf", 18))
    eff_preset = preset or str(cfg.get("libx264_preset", "fast"))

    if target == "h264_videotoolbox":
        args = [
            "-c:v", "h264_videotoolbox",
            "-b:v", eff_bitrate,
            "-pix_fmt", "yuv420p",
        ]
    elif target == "h264_nvenc":
        args = [
            "-c:v", "h264_nvenc",
            "-b:v", eff_bitrate,
            "-profile:v", "high",
            "-pix_fmt", "yuv420p",
        ]
    else:  # libx264
        args = [
            "-c:v", "libx264",
            "-crf", str(eff_crf),
            "-preset", eff_preset,
            "-pix_fmt", "yuv420p",
        ]

    return target, args
