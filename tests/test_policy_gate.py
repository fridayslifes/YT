"""Unit tests for tools/channel_config.py and tools/policy_gate.py."""

from __future__ import annotations

import pytest

from tools.channel_config import list_channels, load_channel_config
from tools.errors import MissingInputError, PolicyGateError
from tools.policy_gate import evaluate_policy_gate


def _valid_project_data() -> dict:
    return {
        "id": "SH-99",
        "slug": "short_99_policy_test",
        "topic": "Loss Aversion",
        "format": "short",
        "channel": "default",
        "voice": "kokoro",
        "science": "Daniel Kahneman & Amos Tversky (1979)",
        "citation_stat": "losses loom 2x larger than equivalent gains",
        "citation_verified": True,
        "contains_synthetic_media": True,
        "self_declared_made_for_kids": False,
        "scenes": [
            {"id": "s01", "text": "Why does losing ten dollars hurt twice as much as finding the exact same ten dollar bill on the sidewalk?", "prompt": "35mm macro shot of empty wallet on dark mahogany desk, soft chiaroscuro lighting"},
            {"id": "s02", "text": "In nineteen seventy nine, cognitive psychologists Daniel Kahneman and Amos Tversky mapped this universal human pain response in controlled trials.", "prompt": "A vintage 1970s laboratory desk with scattered statistical survey papers and brass desk lamp"},
            {"id": "s03", "text": "They offered volunteers identical financial wagers where the mathematical chance of winning or losing was fifty fifty.", "prompt": "Split screen of two hands holding brass coins under dramatic directional studio lighting"},
            {"id": "s04", "text": "Strict rational economic theory predicted people would weigh equivalent potential outcomes on an even scale with zero emotional distortion.", "prompt": "Cinematic close-up of a balanced antique brass scale resting on an oak ledger"},
            {"id": "s05", "text": "Yet when faced with a five dollar potential loss, participants consistently demanded at least a ten dollar upside to play.", "prompt": "A dramatic low-angle perspective of an executive pushing away a sealed envelope"},
            {"id": "s06", "text": "Neurological brain scans confirmed why: losses trigger the amygdala twice as intensely as gains stimulate the dopamine reward pathways.", "prompt": "Stylized 3D architectural blueprint of neural pathways glowing in warm amber tones"},
            {"id": "s07", "text": "This evolutionary survival adaptation kept our ancient ancestors vigilant against scarce resources when single mistakes proved fatal.", "prompt": "Prehistoric campfire embers drifting into a starry nighttime mountain silhouette"},
            {"id": "s08", "text": "Next time fear stops you from taking action, ask if your brain is exaggerating the downside risk. Subscribe and comment below.", "prompt": "Warm glowing desk with an open leather journal and vintage fountain pen"},
        ],
    }


def test_channel_config_loads_default() -> None:
    cfg = load_channel_config("default")
    assert cfg.channel_name == "FrameForge Studio"
    assert cfg.handle == "@FrameForgeStudio"
    assert "cinematic_35mm" in cfg.supported_variants
    assert cfg.voice == "kokoro"
    assert "default" in list_channels()


def test_channel_config_raises_on_unknown_channel() -> None:
    with pytest.raises(MissingInputError) as exc_info:
        load_channel_config("nonexistent_unknown_channel_xyz")
    assert exc_info.value.stage == "channel_config_load"


def test_policy_gate_passes_on_valid_project() -> None:
    report = evaluate_policy_gate(_valid_project_data())
    assert report.passed is True
    assert report.violations == []


def test_policy_gate_blocks_upload_on_missing_synthetic_disclosure() -> None:
    data = _valid_project_data()
    data["contains_synthetic_media"] = False
    report = evaluate_policy_gate(data)
    assert report.passed is False
    assert any("contains_synthetic_media" in v for v in report.violations)


def test_policy_gate_blocks_upload_on_banned_cloud_voice() -> None:
    data = _valid_project_data()
    data["voice"] = "en-US-AndrewNeural"
    report = evaluate_policy_gate(data)
    assert report.passed is False
    assert any("cloud voice" in v.lower() for v in report.violations)


def test_policy_gate_blocks_upload_on_real_person_likeness() -> None:
    data = _valid_project_data()
    data["scenes"][0]["prompt"] = "Photorealistic portrait of Daniel Kahneman talking to Amos Tversky"
    report = evaluate_policy_gate(data)
    assert report.passed is False
    assert any("likeness" in v.lower() for v in report.violations)


def test_policy_gate_blocks_upload_on_protected_character() -> None:
    data = _valid_project_data()
    data["scenes"][0]["prompt"] = "Spider-Man standing next to Batman on a skyscraper roof"
    report = evaluate_policy_gate(data)
    assert report.passed is False
    assert any("protected copyrighted character" in v.lower() for v in report.violations)


def test_policy_gate_blocks_upload_on_unverified_citation() -> None:
    data = _valid_project_data()
    data["citation_verified"] = False
    report = evaluate_policy_gate(data)
    assert report.passed is False
    assert any("citation_verified" in v for v in report.violations)


def test_policy_gate_blocks_upload_on_missing_closing_ask() -> None:
    data = _valid_project_data()
    data["scenes"][-1]["text"] = "And that is the quiet paradox of human nature that echoes forever."
    report = evaluate_policy_gate(data)
    assert report.passed is False
    assert any("closing" in v.lower() for v in report.violations)


def test_policy_gate_raises_policy_gate_error_when_requested() -> None:
    data = _valid_project_data()
    data["citation_verified"] = False
    with pytest.raises(PolicyGateError) as exc_info:
        evaluate_policy_gate(data, raise_on_failure=True)
    assert exc_info.value.stage == "policy_gate"
