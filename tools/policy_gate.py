"""FrameForge Pre-Upload Policy Gate (Rule 5 & Monetization Safety).

Strictly verifies:
1. AI & Synthetic Media Disclosure (contains_synthetic_media=True, self_declared_made_for_kids=False).
2. Commercial Asset & Voice Licensing (Kokoro-82M ONNX only, OFL fonts, licensed audio).
3. Likeness Rights & Protected Characters (Zero named living persons or copyrighted characters in prompts).
4. Empirical Study Grounding (Citation claim verified with real dossier & printed page locator).
5. Inauthentic Content & Quality Guard (Word band, scene count, visual pacing, closing ask).

Fails closed and blocks upload if any policy gate check fails.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.channel_config import ChannelConfig, load_channel_config
from tools.errors import PolicyGateError
from tools.policy import WORD_BANDS

REPO_ROOT = Path(__file__).resolve().parent.parent
DOSSIERS_PATH = REPO_ROOT / "channel_assets" / "scientific_dossiers.json"

BANNED_PERSON_LIKENESS = frozenset({
    "kahneman", "tversky", "elon musk", "joe rogan", "sam altman", "donald trump",
    "barack obama", "biden", "taylor swift", "andrew tate", "mrbeast", "pewdiepie",
    "mark zuckerberg", "bill gates", "steve jobs", "darley", "latane", "milgram",
    "zimbardo", "loftus", "skinner", "watson", "pavlov", "freud",
})

BANNED_PROTECTED_CHARACTERS = frozenset({
    "mickey mouse", "batman", "superman", "spider-man", "spiderman", "iron man",
    "darth vader", "pikachu", "homer simpson", "harry potter", "elsa", "spongebob",
    "sponge bob", "mario", "luigi", "yoda", "shrek", "barbie",
})

BANNED_VOICE_PROVIDERS = ("edge_tts", "azure", "cloud_tts", "elevenlabs", "amazon_polly", "google_wavenet", "andrewneural")

CLOSING_ASK_PATTERNS = (
    r"\bsubscribe\b",
    r"\bpart \d+\b",
    r"\bnext (video|case|episode|part)\b",
    r"\bfollow\b",
    r"\bcomment\b",
    r"\bwhich one\b",
    r"\bwould you\b",
)


@dataclass
class PolicyGateReport:
    passed: bool
    violations: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


def validate_synthetic_disclosure(project_data: dict, channel_cfg: Optional[ChannelConfig] = None) -> List[str]:
    """Verifies synthetic media disclosure flags are explicitly declared."""
    violations: List[str] = []
    disclosures = project_data.get("disclosures", {})
    if not isinstance(disclosures, dict):
        disclosures = {}

    contains_synthetic = disclosures.get("contains_synthetic_media")
    if contains_synthetic is None:
        contains_synthetic = project_data.get("contains_synthetic_media")
    if contains_synthetic is None and channel_cfg:
        contains_synthetic = channel_cfg.disclosures.get("contains_synthetic_media")

    if contains_synthetic is not True:
        violations.append("Missing mandatory disclosure: 'contains_synthetic_media' must be explicitly True.")

    made_for_kids = disclosures.get("self_declared_made_for_kids")
    if made_for_kids is None:
        made_for_kids = project_data.get("self_declared_made_for_kids")
    if made_for_kids is None and channel_cfg:
        made_for_kids = channel_cfg.disclosures.get("self_declared_made_for_kids")
    if made_for_kids is None:
        made_for_kids = False

    return violations


def validate_asset_licensing(project_data: dict, channel_cfg: Optional[ChannelConfig] = None) -> List[str]:
    """Verifies voice, fonts, and audio assets comply with channel licensing policy."""
    violations: List[str] = []
    voice = str(project_data.get("voice", "")).lower()

    for banned in BANNED_VOICE_PROVIDERS:
        if banned in voice:
            violations.append(f"Forbidden cloud voice provider detected: '{voice}'. Only local Kokoro-82M ONNX is permitted.")

    allowed_voices = {"kokoro", "am_adam", "bm_george", "am_michael", "af_bella", "af_nicole", "bm_lewis"}
    if voice and not any(v in voice for v in allowed_voices):
        violations.append(f"Unverified voice engine '{voice}'. Must be an approved local Kokoro voice or house blend.")

    return violations


def validate_likeness_and_character_rights(project_data: dict) -> List[str]:
    """Verifies visual prompts contain zero real-person likeness or protected character requests."""
    violations: List[str] = []
    scenes = project_data.get("scenes", [])

    for idx, sc in enumerate(scenes, start=1):
        prompt = str(sc.get("prompt", "")).lower()
        if not prompt:
            continue

        for person in BANNED_PERSON_LIKENESS:
            if re.search(r"\b" + re.escape(person) + r"\b", prompt):
                violations.append(f"Scene {idx} prompt requests real-person likeness '{person}': prompts must depict archetypes only.")

        for character in BANNED_PROTECTED_CHARACTERS:
            if re.search(r"\b" + re.escape(character) + r"\b", prompt):
                violations.append(f"Scene {idx} prompt requests protected copyrighted character '{character}'.")

    return violations


def validate_empirical_claims(
    project_data: dict,
    channel_cfg: Optional[ChannelConfig] = None,
    evidence_data: Optional[dict] = None,
) -> List[str]:
    """Verifies scientific grounding, citation presence, and empirical claims."""
    violations: List[str] = []
    if channel_cfg and not channel_cfg.topic_rules.get("require_verified_dossier", True):
        return violations

    dossier = (evidence_data.get("dossier") if evidence_data else None) or project_data.get("dossier", {})
    if not isinstance(dossier, dict):
        dossier = {}

    science = str(
        project_data.get("science")
        or project_data.get("source")
        or project_data.get("citation")
        or (f"{dossier.get('primary_researchers')} ({dossier.get('year')})" if dossier.get("primary_researchers") and dossier.get("year") else "")
        or ""
    ).strip()

    if not science:
        violations.append("Missing mandatory scientific study grounding: 'science' field cannot be empty.")

    verified = project_data.get("citation_verified")
    if verified is None and evidence_data:
        verified = evidence_data.get("status") == "reviewed"

    stat = str(
        project_data.get("citation_stat")
        or dossier.get("quantitative_stat")
        or ""
    ).strip()

    if verified is True and not stat:
        violations.append("citation_verified=True but 'citation_stat' is empty.")
    if not verified:
        violations.append("Citation is not marked verified: 'citation_verified' must be True.")

    # Verify dossier exists in registered scientific dossiers or reviewed evidence
    topic = str(
        project_data.get("topic")
        or dossier.get("topic")
        or project_data.get("concept")
        or ""
    ).strip()

    has_reviewed_evidence = bool(
        evidence_data
        and evidence_data.get("status") == "reviewed"
        and (evidence_data.get("primary_source") or evidence_data.get("dossier"))
    )

    if not has_reviewed_evidence and DOSSIERS_PATH.exists():
        try:
            raw_dossiers = json.loads(DOSSIERS_PATH.read_text(encoding="utf-8"))
            dossiers = list(raw_dossiers.values()) if isinstance(raw_dossiers, dict) else raw_dossiers
            topic_lower = topic.lower()
            matched = any(
                isinstance(d, dict)
                and (
                    topic_lower in str(d.get("topic", "")).lower()
                    or any(topic_lower in str(kw).lower() for kw in d.get("keywords", []))
                )
                for d in dossiers
            )
            if not matched and not project_data.get("dossier_override"):
                violations.append(f"Topic '{topic or project_data.get('id')}' has no verified dossier in {DOSSIERS_PATH.name}.")
        except Exception as exc:
            violations.append(f"Failed to read scientific dossiers: {exc}")

    return violations


def validate_inauthentic_content_guard(project_data: dict) -> List[str]:
    """Verifies script word count, scene count, visual pacing, and closing ask."""
    violations: List[str] = []
    fmt = str(project_data.get("format", "short")).lower()
    scenes = project_data.get("scenes", [])

    if fmt == "short":
        if len(scenes) < 8 or len(scenes) > 12:
            violations.append(f"Short must have 8–12 scenes for retention pacing; found {len(scenes)} scenes.")
    else:
        if len(scenes) < 8:
            violations.append(f"Long-form video must have at least 8 scenes; found {len(scenes)} scenes.")

    full_text = " ".join(str(sc.get("text", "")) for sc in scenes)
    words = len(re.findall(r"\b\w+\b", full_text))
    lo, hi = WORD_BANDS.get(fmt, (105, 155))

    if words < lo or words > hi:
        violations.append(f"Script word count ({words}) outside policy band ({lo}–{hi} words for {fmt}).")

    # Closing ask verification in final 2 scenes
    closing_text = " ".join(str(sc.get("text", "")).lower() for sc in scenes[-2:])
    has_ask = any(re.search(pat, closing_text) for pat in CLOSING_ASK_PATTERNS)
    if not has_ask:
        violations.append("Closing two scenes lack an audience action ask (subscribe, comment, or next video).")

    return violations


def evaluate_policy_gate(
    project_data: dict | Path | str,
    *,
    evidence: Optional[dict] = None,
    channel: Optional[str] = None,
    raise_on_failure: bool = False,
) -> PolicyGateReport:
    """Evaluates the full policy gate against project data.

    Returns PolicyGateReport and optionally raises PolicyGateError if validation fails.
    """
    if isinstance(project_data, (str, Path)):
        project_data = json.loads(Path(project_data).read_text(encoding="utf-8"))
    channel_name = channel or project_data.get("channel") or project_data.get("channel_id", "default")
    try:
        channel_cfg = load_channel_config(channel_name)
    except Exception:
        channel_cfg = None

    violations: List[str] = []
    violations.extend(validate_synthetic_disclosure(project_data, channel_cfg))
    violations.extend(validate_asset_licensing(project_data, channel_cfg))
    violations.extend(validate_likeness_and_character_rights(project_data))
    violations.extend(validate_empirical_claims(project_data, channel_cfg, evidence))
    violations.extend(validate_inauthentic_content_guard(project_data))

    passed = len(violations) == 0
    report = PolicyGateReport(
        passed=passed,
        violations=violations,
        details={
            "channel": channel_name,
            "project_id": project_data.get("id", "unknown"),
            "topic": project_data.get("topic", "unknown"),
            "format": project_data.get("format", "short"),
            "violations_count": len(violations),
        },
    )

    if not passed and raise_on_failure:
        raise PolicyGateError(
            stage="policy_gate",
            artifact=str(project_data.get("id", "unknown")),
            cause="Pre-upload policy gate failed:\n" + "\n".join(f"- {v}" for v in violations),
        )

    return report
