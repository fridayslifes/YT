"""Content-addressed scene render identity, separate from authored projects."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.atomic_files import durable_write_text

# Bump whenever the spatial renderer's defaults, algorithms or encoding contract change.
RENDERER_CONTRACT_VERSION = "3d-spatial-v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


_OVERLAY_FINGERPRINT_KEYS = (
    "caption",
    "clue",
    "stamp",
    "plate_label",
    "pose",
    "mouth",
    "eyebrows",
    "prop",
    "accessory",
    "riddle",
    "inventory",
    "characters",
    "sightlines",
    "countdown_seconds",
    "elimination_banner",
    "cta_banner",
    "highlighter_phrase",
    "exhibit_code",
    "location_text",
    "timestamp_text",
    "overlay",
)


def scene_fingerprint(
    *, scene_index: int, scene: dict, source_image: Path, duration_s: float,
    preset: str, width: int, height: int,
    variant: str | None = None,
    audio_path: Path | None = None,
    audio_sha256: str | None = None,
    timings: list[dict] | None = None,
) -> str:
    """Bind spatial-render, variant, script, audio, timing, and overlay inputs."""
    resolved_variant = variant if variant is not None else (scene.get("variant") or scene.get("engine"))
    resolved_audio_sha = _sha256(audio_path) if audio_path is not None else (audio_sha256 or scene.get("audio_sha256"))
    resolved_timings = list(timings) if timings is not None else scene.get("timings")
    overlay_params = {k: scene[k] for k in _OVERLAY_FINGERPRINT_KEYS if k in scene}

    payload = {
        "scene_index": scene_index,
        "prompt": scene.get("prompt", ""),
        "text": scene.get("text", ""),
        "variant": resolved_variant,
        "audio_sha256": resolved_audio_sha,
        "timings": resolved_timings,
        "overlay_parameters": overlay_params,
        "source_image_sha256": _sha256(source_image),
        # The renderer derives its deterministic particle seed from this stem.
        "source_image_stem": Path(source_image).stem,
        "duration_s": float(duration_s),
        "preset": preset,
        "width": width,
        "height": height,
        "renderer_contract_version": RENDERER_CONTRACT_VERSION,
        "render_parameters": {"fps": 30, "image_steps": scene.get("steps")},
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class RenderManifest:
    """A cache/render_manifest.json sidecar with independently reusable scene entries."""

    def __init__(self, path: Path, scenes: dict | None = None):
        self.path = Path(path)
        self.scenes = scenes or {}

    @classmethod
    def load(cls, path: Path) -> RenderManifest:
        path = Path(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls(path)
        if (
            not isinstance(data, dict)
            or data.get("schema_version") != 1
            or data.get("renderer_contract_version") != RENDERER_CONTRACT_VERSION
            or not isinstance(data.get("scenes"), dict)
        ):
            return cls(path)
        return cls(path, data["scenes"])

    def _output_relative_path(self, output_path: Path) -> str:
        return Path(output_path).resolve().relative_to(self.path.parent.parent.resolve()).as_posix()

    def can_reuse(self, scene_key: str, fingerprint: str, output_path: Path) -> bool:
        entry = self.scenes.get(str(scene_key))
        if not isinstance(entry, dict) or entry.get("fingerprint") != fingerprint:
            return False
        try:
            return (
                entry.get("output_path") == self._output_relative_path(output_path)
                and entry.get("output_sha256") == _sha256(output_path)
            )
        except (OSError, ValueError):
            return False

    def record(self, scene_key: str, fingerprint: str, output_path: Path) -> None:
        self.scenes[str(scene_key)] = {
            "fingerprint": fingerprint,
            "output_path": self._output_relative_path(output_path),
            "output_sha256": _sha256(output_path),
        }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        durable_write_text(self.path, json.dumps({
            "schema_version": 1,
            "renderer_contract_version": RENDERER_CONTRACT_VERSION,
            "scenes": self.scenes,
        }, indent=2, sort_keys=True) + "\n")
