"""Dynamic Channel Configuration Manager.

Loads and validates channel-specific configurations from configs/channels/<name>.yaml.
Provides strict governance on supported variants, voice synthesis, color palettes,
topic rules, and platform disclosures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import yaml

from tools.errors import MissingInputError

REPO_ROOT = Path(__file__).resolve().parent.parent
CHANNELS_DIR = REPO_ROOT / "configs" / "channels"


@dataclass
class ChannelConfig:
    channel_name: str
    channel_id: str
    handle: str
    niche: str
    default_variant: str
    supported_variants: List[str]
    voice: str = "kokoro"
    rate: str = "+1%"
    pitch: str = "-2Hz"
    color_palette: Dict[str, str] = field(default_factory=dict)
    cadence: Dict[str, Any] = field(default_factory=dict)
    topic_rules: Dict[str, Any] = field(default_factory=dict)
    bans: List[str] = field(default_factory=list)
    disclosures: Dict[str, Any] = field(default_factory=dict)


_CHANNEL_CACHE: Dict[str, ChannelConfig] = {}


def list_channels() -> List[str]:
    """Returns all available channel names configured in configs/channels/."""
    if not CHANNELS_DIR.exists():
        return []
    return sorted(p.stem for p in CHANNELS_DIR.glob("*.yaml") if p.is_file())


def load_channel_config(channel_identifier: str) -> ChannelConfig:
    """Loads and validates a channel configuration by filename, handle, or channel_id."""
    clean_id = channel_identifier.strip().lower().replace("@", "")
    if clean_id in _CHANNEL_CACHE:
        return _CHANNEL_CACHE[clean_id]

    target_file = CHANNELS_DIR / f"{clean_id}.yaml"
    if not target_file.exists():
        # Search all yaml files in configs/channels/ for matching name, handle, or id
        found_file = None
        for p in CHANNELS_DIR.glob("*.yaml"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                if (
                    p.stem.lower() == clean_id
                    or str(data.get("channel_id", "")).lower() == clean_id
                    or str(data.get("channel_name", "")).lower().replace(" ", "_") == clean_id
                    or str(data.get("handle", "")).lower().replace("@", "") == clean_id
                ):
                    found_file = p
                    break
            except Exception:
                continue

        if not found_file:
            available = list_channels()
            raise MissingInputError(
                stage="channel_config_load",
                artifact=channel_identifier,
                cause=f"Channel '{channel_identifier}' not found in {CHANNELS_DIR}. Available channels: {available}",
            )
        target_file = found_file

    with open(target_file, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    config = ChannelConfig(
        channel_name=str(raw.get("channel_name", target_file.stem)),
        channel_id=str(raw.get("channel_id", "")),
        handle=str(raw.get("handle", "")),
        niche=str(raw.get("niche", "")),
        default_variant=str(raw.get("default_variant", "cinematic_35mm")),
        supported_variants=list(raw.get("supported_variants", ["cinematic_35mm"])),
        voice=str(raw.get("voice", "kokoro")),
        rate=str(raw.get("rate", "+1%")),
        pitch=str(raw.get("pitch", "-2Hz")),
        color_palette=dict(raw.get("color_palette", {})),
        cadence=dict(raw.get("cadence", {})),
        topic_rules=dict(raw.get("topic_rules", {})),
        bans=list(raw.get("bans", [])),
        disclosures=dict(raw.get("disclosures", {})),
    )

    _CHANNEL_CACHE[clean_id] = config
    _CHANNEL_CACHE[target_file.stem] = config
    return config
