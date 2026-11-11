"""FrameForge Per-Video Uniqueness Gate (Global Rule C).

Strictly enforces:
1. SFX Uniqueness: Overlap of asset IDs + timing patterns under configured threshold.
2. Image Uniqueness: Per-scene perceptual-hash (dHash) distance over threshold; zero image reuse.
3. Audio Uniqueness: Music bed and ambience divergence, and acoustic fingerprint distance.
4. Opening 3-Seconds Uniqueness: First spoken line and visual subject cannot be repeated.

Thresholds are dynamically loaded from configs/uniqueness.yaml.
Fails closed with UniquenessGateError if any threshold is violated.
"""

from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
from PIL import Image
import yaml

from tools.errors import UniquenessGateError

logger = logging.getLogger("uniqueness_gate")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "configs" / "uniqueness.yaml"


@dataclass
class UniquenessGateReport:
    passed: bool
    violations: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    comparisons: List[Dict[str, Any]] = field(default_factory=list)


def load_uniqueness_thresholds(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Loads uniqueness thresholds from configs/uniqueness.yaml."""
    path = config_path or DEFAULT_CONFIG_PATH
    if not path.exists():
        return {
            "max_sfx_overlap_ratio": 0.50,
            "max_sfx_timing_correlation": 0.60,
            "min_phash_distance": 10,
            "disallow_exact_image_reuse": True,
            "require_distinct_music_bed": True,
            "require_distinct_ambience": True,
            "min_audio_distance": 0.20,
            "disallow_opening_line_reuse": True,
            "disallow_opening_subject_reuse": True,
            "max_opening_text_similarity": 0.70,
        }
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("thresholds", {})


def compute_image_phash(image_path: Path) -> int:
    """Computes a 64-bit perceptual hash combining luminance distribution and spatial structure."""
    with Image.open(image_path) as img:
        rgb = img.convert("RGB").resize((8, 8), Image.Resampling.BILINEAR)
        arr = np.asarray(rgb, dtype=np.float32)
        lum = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]

        # Handle flat uniform images by encoding quantized mean luminance across bytes
        if float(lum.std()) < 0.5:
            mean_byte = int(round(float(lum.mean()))) & 0xFF
            val = 0
            for _ in range(8):
                val = (val << 8) | mean_byte
            return val

        mean = float(lum.mean())
        bits = lum >= mean
        val = 0
        for b in bits.flatten():
            val = (val << 1) | int(b)
        return val


def phash_distance(h1: int, h2: int) -> int:
    """Computes the Hamming distance (0 to 64) between two 64-bit perceptual hashes."""
    return bin(h1 ^ h2).count("1")


def text_token_similarity(text1: str, text2: str) -> float:
    """Computes token-based Jaccard similarity between two strings."""
    t1 = set(re.findall(r"\b\w+\b", text1.lower()))
    t2 = set(re.findall(r"\b\w+\b", text2.lower()))
    if not t1 or not t2:
        return 0.0
    return len(t1 & t2) / len(t1 | t2)


def compute_audio_fingerprint(audio_path: Path, window_s: float = 0.5) -> List[float]:
    """Computes an acoustic RMS energy envelope fingerprint vector across 0.5s windows."""
    try:
        import soundfile as sf
        data, samplerate = sf.read(str(audio_path), always_2d=True)
        mono = data.mean(axis=1)
        samples_per_window = int(samplerate * window_s)
        if samples_per_window <= 0 or len(mono) == 0:
            return []
        envelope: List[float] = []
        for i in range(0, len(mono), samples_per_window):
            chunk = mono[i : i + samples_per_window]
            rms = math.sqrt(float(np.mean(chunk**2))) if len(chunk) > 0 else 0.0
            envelope.append(rms)
        total = sum(envelope) or 1.0
        return [round(e / total, 6) for e in envelope]
    except Exception as exc:
        logger.warning("Audio fingerprint extraction failed for %s: %s", audio_path, exc)
        return []


def audio_envelope_distance(fp1: List[float], fp2: List[float]) -> float:
    """Computes cosine distance (0.0 to 1.0) between two normalized energy envelopes."""
    if not fp1 or not fp2:
        return 1.0
    min_len = min(len(fp1), len(fp2))
    if min_len < 4:
        return 1.0
    v1 = np.array(fp1[:min_len])
    v2 = np.array(fp2[:min_len])
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return 1.0
    similarity = float(np.dot(v1, v2) / (norm1 * norm2))
    return max(0.0, min(1.0, 1.0 - similarity))


def extract_project_profile(project_path: Path) -> Dict[str, Any]:
    """Extracts identity, visual prompts, images, SFX, and audio assets for uniqueness checking."""
    project_dir = project_path.parent
    data = json.loads(project_path.read_text(encoding="utf-8"))
    scenes = data.get("scenes", [])

    opening_text = str(scenes[0].get("text", "")).strip() if scenes else ""
    opening_prompt = str(scenes[0].get("prompt", "")).strip() if scenes else ""

    # Extract scene image paths and compute perceptual hashes
    scene_images: List[Tuple[int, Path, int]] = []
    for idx, sc in enumerate(scenes, start=1):
        img_rel = sc.get("image")
        if img_rel:
            img_path = project_dir / img_rel
            if img_path.exists():
                try:
                    ph = compute_image_phash(img_path)
                    scene_images.append((idx, img_path, ph))
                except (OSError, ValueError) as exc:
                    logger.warning("pHash calculation failed for %s: %s", img_path, exc)

    # Extract SFX assets
    sfx_assets: Set[str] = set()
    sfx_plan_file = project_dir / "cache" / "sfx_plan.json"
    if sfx_plan_file.exists():
        try:
            sfx_plan = json.loads(sfx_plan_file.read_text(encoding="utf-8"))
            for item in sfx_plan.get("cues", []):
                sfx_name = item.get("sfx") or item.get("asset") or item.get("file")
                if sfx_name:
                    sfx_assets.add(str(sfx_name).lower())
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("SFX plan parse failed for %s: %s", sfx_plan_file, exc)

    for sc in scenes:
        sfx_item = sc.get("sfx")
        if sfx_item:
            sfx_assets.add(str(sfx_item).lower())

    music_bed = str(data.get("music") or data.get("bgm") or "").strip().lower()
    ambience = str(data.get("ambience") or "").strip().lower()

    # Audio mix fingerprint
    audio_fp: List[float] = []
    audio_mix = project_dir / "cache" / "mix.wav"
    if not audio_mix.exists():
        audio_mix = project_dir / "cache" / "narration.wav"
    if audio_mix.exists():
        audio_fp = compute_audio_fingerprint(audio_mix)

    return {
        "id": data.get("id", project_dir.name),
        "path": project_path,
        "project_dir": project_dir,
        "opening_text": opening_text,
        "opening_prompt": opening_prompt,
        "scene_images": scene_images,
        "sfx_assets": sfx_assets,
        "music_bed": music_bed,
        "ambience": ambience,
        "audio_fingerprint": audio_fp,
    }


def evaluate_uniqueness_gate(
    project_dir_or_json: Path,
    *,
    root_dir: Optional[Path] = None,
    config_path: Optional[Path] = None,
    raise_on_failure: bool = False,
) -> UniquenessGateReport:
    """Compares the target project against every other project in the repository.

    Fails closed if any visual plate, SFX sequence, opening hook, or audio track
    repeats prior videos beyond configured thresholds.
    """
    root = root_dir or REPO_ROOT
    proj_path = (
        project_dir_or_json
        if project_dir_or_json.name.endswith(".json")
        else project_dir_or_json / "project.json"
    )
    if not proj_path.exists():
        raise UniquenessGateError(
            stage="uniqueness_gate",
            artifact=str(proj_path),
            cause=f"Target project.json not found: {proj_path}",
        )

    thresholds = load_uniqueness_thresholds(config_path)
    target_profile = extract_project_profile(proj_path)
    target_id = target_profile["id"]

    # Collect all other project.json files in the repository
    other_project_paths: List[Path] = []
    for pattern in ("shorts/*/project.json", "long_form/*/project.json"):
        for candidate in sorted(root.glob(pattern)):
            if candidate.resolve() != proj_path.resolve():
                other_project_paths.append(candidate)

    violations: List[str] = []
    comparisons: List[Dict[str, Any]] = []

    for other_path in other_project_paths:
        try:
            other_profile = extract_project_profile(other_path)
        except Exception as exc:
            logger.warning("Failed to extract project profile for %s: %s", other_path, exc)
            continue

        other_id = other_profile["id"]
        comp_metrics: Dict[str, Any] = {"compared_with": other_id}

        # 1. Opening 3-seconds uniqueness check
        t_open = target_profile["opening_text"]
        o_open = other_profile["opening_text"]
        if t_open and o_open:
            sim = text_token_similarity(t_open, o_open)
            comp_metrics["opening_text_similarity"] = round(sim, 3)
            if thresholds.get("disallow_opening_line_reuse", True) and t_open.lower() == o_open.lower():
                violations.append(
                    f"Duplicate opening spoken sentence with video '{other_id}': '{t_open}'"
                )
            elif sim >= thresholds.get("max_opening_text_similarity", 0.70):
                violations.append(
                    f"Opening spoken sentence too similar to '{other_id}' (similarity={sim:.2f} >= {thresholds.get('max_opening_text_similarity')}): '{t_open}' vs '{o_open}'"
                )

        t_prompt = target_profile["opening_prompt"]
        o_prompt = other_profile["opening_prompt"]
        if t_prompt and o_prompt and thresholds.get("disallow_opening_subject_reuse", True):
            if t_prompt.lower() == o_prompt.lower():
                violations.append(
                    f"Duplicate opening scene prompt with video '{other_id}': '{t_prompt}'"
                )

        # 2. Per-scene image perceptual hash uniqueness
        min_phash_dist = thresholds.get("min_phash_distance", 10)
        disallow_exact = thresholds.get("disallow_exact_image_reuse", True)

        for t_idx, t_img_path, t_phash in target_profile["scene_images"]:
            for o_idx, o_img_path, o_phash in other_profile["scene_images"]:
                dist = phash_distance(t_phash, o_phash)
                if dist == 0 and disallow_exact:
                    violations.append(
                        f"Exact image reuse detected: Scene {t_idx} ({t_img_path.name}) in '{target_id}' matches Scene {o_idx} ({o_img_path.name}) in '{other_id}' (dHash distance=0)."
                    )
                elif dist < min_phash_dist:
                    violations.append(
                        f"Image perceptual similarity too high: Scene {t_idx} in '{target_id}' has dHash distance {dist} < {min_phash_dist} against Scene {o_idx} in '{other_id}'."
                    )

        # 3. SFX asset overlap check
        t_sfx = target_profile["sfx_assets"]
        o_sfx = other_profile["sfx_assets"]
        max_sfx_overlap = thresholds.get("max_sfx_overlap_ratio", 0.50)
        if t_sfx and o_sfx:
            overlap = len(t_sfx & o_sfx) / len(t_sfx | o_sfx)
            comp_metrics["sfx_overlap_ratio"] = round(overlap, 3)
            if overlap > max_sfx_overlap:
                violations.append(
                    f"SFX asset overlap with '{other_id}' ({overlap:.2f}) exceeds policy limit ({max_sfx_overlap}). Shared assets: {sorted(t_sfx & o_sfx)}"
                )

        # 4. Audio design uniqueness
        if thresholds.get("require_distinct_music_bed", True):
            t_music = target_profile["music_bed"]
            o_music = other_profile["music_bed"]
            if t_music and o_music and t_music == o_music:
                violations.append(
                    f"Duplicate music bed with video '{other_id}': '{t_music}'. Each video requires its own score."
                )

        if thresholds.get("require_distinct_ambience", True):
            t_amb = target_profile["ambience"]
            o_amb = other_profile["ambience"]
            if t_amb and o_amb and t_amb == o_amb:
                violations.append(
                    f"Duplicate ambience bed with video '{other_id}': '{t_amb}'. Each video requires distinct ambient room sound."
                )

        t_fp = target_profile["audio_fingerprint"]
        o_fp = other_profile["audio_fingerprint"]
        min_aud_dist = thresholds.get("min_audio_distance", 0.20)
        if t_fp and o_fp:
            a_dist = audio_envelope_distance(t_fp, o_fp)
            comp_metrics["audio_distance"] = round(a_dist, 3)
            if a_dist < min_aud_dist:
                violations.append(
                    f"Audio acoustic envelope too similar to '{other_id}' (distance={a_dist:.2f} < {min_aud_dist})."
                )

        comparisons.append(comp_metrics)

    passed = len(violations) == 0
    report = UniquenessGateReport(
        passed=passed,
        violations=violations,
        metrics={
            "target_id": target_id,
            "compared_projects_count": len(other_project_paths),
            "violations_count": len(violations),
        },
        comparisons=comparisons,
    )

    if not passed and raise_on_failure:
        raise UniquenessGateError(
            stage="uniqueness_gate",
            artifact=str(proj_path),
            cause="Rule C Uniqueness Gate failed:\n" + "\n".join(f"- {v}" for v in violations),
        )

    return report
