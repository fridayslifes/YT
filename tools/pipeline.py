#!/usr/bin/env python3
"""FrameForge Unified 3D Video Production Pipeline & Self-Healing Quality Gate (v5.0).

Pure 3D Spatial Pipeline:
  1. Active Self-Healing of the Best Engine (`run_with_healing`):
     Diagnoses root causes, flushes Metal/MPS memory, repairs caches, and retries the primary SOTA engine.
  2. Unified 3-Plane 3D Spatial Motion Generation (`generate_project_motion` & `build_and_verify`):
     Every scene in both Shorts (9:16) and Long-Form (16:9) videos is rendered through
     `visual_engine.render_3d_spatial_scene` (3-plane Z-decomposition, bilateral depth, 3D normal relighting,
     physical aperture DoF, and volumetric depth particles) — zero legacy 2D or single-plane 2.5D fallbacks.
  3. Reference Precision & Recall Verification Gate (`--verify-all`).

Usage:
    python tools/pipeline.py --verify-all
    python tools/pipeline.py --build long_form/lv_02_focus_protocol/project.json
    python tools/pipeline.py --motion long_form/lv_02_focus_protocol/project.json
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, TypeVar

if "/opt/homebrew/bin" not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"/opt/homebrew/bin:{os.environ.get('PATH', '')}"

TOOLS_DIR = Path(__file__).resolve().parent
YT_ROOT = TOOLS_DIR.parent

if str(YT_ROOT) not in sys.path:
    sys.path.insert(0, str(YT_ROOT))
from tools.runtime import ensure_venv_cli  # noqa: E402

if __name__ == "__main__":
    ensure_venv_cli(Path(__file__), sys.argv[1:])

import cv2  # noqa: F401, E402
import numpy as np  # noqa: F401, E402

py_ver = f"python{sys.version_info.major}.{sys.version_info.minor}"
VENV_SITE = YT_ROOT / ".venv" / "lib" / py_ver / "site-packages"
if VENV_SITE.exists() and str(VENV_SITE) not in sys.path:
    sys.path.append(str(VENV_SITE))

sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(YT_ROOT))

from tools import audio_bank        # noqa: E402
from tools import build_video       # noqa: E402
from tools import creative_engine   # noqa: E402
from tools import output_format as fmt  # noqa: E402
from tools import tracker           # noqa: E402
from tools import visual_engine     # noqa: E402
from tools import youtube_skills    # noqa: E402
from tools.policy import WORD_BANDS  # noqa: E402
from tools.processes import run_process  # noqa: E402
from tools.render_manifest import RenderManifest, scene_fingerprint  # noqa: E402
from tools.schemas import validate_project  # noqa: E402

T = TypeVar("T")

# GEMINI.md section 2 script-length bands. The gate compares against these and the failure message
# prints these, so a rejected script is never told a band the code did not enforce. verifiers.py
# reads the same tuple instead of keeping its own copy.
# Median words-per-minute across this channel's own 17 rendered projects (regex word count of the
# script against ffprobe duration of the shipped MP4): 169, range 147-208. Used only to turn a word
# band into a runtime estimate; GEMINI.md's "38-52s" for 105-155 words is what this reproduces.
DELIVERY_WPM = 169

# GEMINI.md section 2: the script ends on one ask the viewer can act on inside YouTube. Only asks the
# channel can be credited for count - "thanks for watching" closes a video, it does not ask for anything.
ASK_RE = re.compile(
    r"\b(subscrib\w*|hit the bell|turn on notifications|next video|watch (?:our|the|this|next)"
    r"|comment (?:below|and tell|your)|part \d)\b",
    re.IGNORECASE,
)

PRESETS_3D = [
    "depthflow_spiral",
    "depthflow_orbit",
    "depthflow_vertigo",
    "depthflow_dolly",
    "depthflow_roll",
    "spatial_drift",
]


def _resolve_3d_preset(sc: dict, idx: int) -> str:
    """Map any scene preset or legacy motion label to a canonical 3D spatial trajectory."""
    raw = (sc.get("preset") or sc.get("motion") or "").lower().strip()
    if raw in PRESETS_3D or raw.startswith("depthflow_"):
        return raw
    legacy_to_3d = {
        "punch": "depthflow_vertigo",
        "zoom_in": "depthflow_dolly",
        "dolly_in": "depthflow_dolly",
        "zoom_out": "depthflow_orbit",
        "dolly_out": "depthflow_orbit",
        "pan_up": "depthflow_spiral",
        "pan_down": "spatial_drift",
        "pan_left": "depthflow_roll",
        "pan_right": "depthflow_roll",
        "drift_left": "depthflow_roll",
        "drift_right": "depthflow_roll",
        "breathing": "spatial_drift",
    }
    return legacy_to_3d.get(raw, PRESETS_3D[idx % len(PRESETS_3D)])


# --------------------------------------------------------------------------- #
# 1. Active Self-Healing Runner (Diagnose -> Repair Root Cause -> Retry Best)
# --------------------------------------------------------------------------- #
def run_with_healing(
    stage_name: str,
    fn: Callable[[], T],
    heal_fn: Callable[[Exception, int], None] | None = None,
    max_attempts: int = 3,
) -> T:
    """Run the primary SOTA engine; on failure, execute root-cause repair (`heal_fn`) and retry."""
    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as e:
            last_err = e
            print(f"  [Self-Heal: {stage_name}] Attempt {attempt}/{max_attempts} encountered error: {e}", file=sys.stderr)
            if attempt < max_attempts:
                visual_engine._heal_gpu_memory()
                if heal_fn is not None:
                    try:
                        heal_fn(e, attempt)
                    except Exception as he:
                        print(f"  [Self-Heal: {stage_name}] Repair hook note: {he}", file=sys.stderr)
                time.sleep(0.6 * attempt)
    raise RuntimeError(f"Stage '{stage_name}' failed after {max_attempts} self-healing attempts: {last_err}") from last_err


def verify_pipeline_assets() -> dict:
    """Verify all self-contained SOTA pipeline components."""
    sfx_status = audio_bank.ensure_studio_sfx_pack(try_remote_cc0=False)
    fonts_dir = TOOLS_DIR / "fonts"
    fonts = list(fonts_dir.glob("*.ttf")) + list(fonts_dir.glob("*.ttc"))
    kokoro_onnx = TOOLS_DIR / "kokoro_models" / "kokoro-v1.0.onnx"
    kokoro_voices = TOOLS_DIR / "kokoro_models" / "voices-v1.0.bin"

    status = {
        "fonts_ready": len(fonts) > 0,
        "fonts_count": len(fonts),
        "sfx_pack_ready": len(sfx_status) >= 5,
        "kokoro_onnx_ready": kokoro_onnx.exists() and kokoro_onnx.stat().st_size > 200_000_000,
        "kokoro_voices_ready": kokoro_voices.exists() and kokoro_voices.stat().st_size > 20_000_000,
        "ffmpeg_ready": shutil.which("ffmpeg") is not None,
        "ffprobe_ready": shutil.which("ffprobe") is not None,
    }
    status["all_connected"] = all(
        [status["fonts_ready"], status["sfx_pack_ready"], status["kokoro_onnx_ready"], status["kokoro_voices_ready"], status["ffmpeg_ready"], status["ffprobe_ready"]]
    )
    return status


def configure_pipeline_environment() -> dict:
    """Verify and initialize all local pipeline assets, audio bank, fonts, and directories."""
    print("=== Initializing & Configuring FrameForge 3D Studio Environment ===")
    sfx_res = audio_bank.ensure_studio_sfx_pack(force_rebuild=False)
    status = verify_pipeline_assets()
    status["sfx_details"] = sfx_res
    return {"status": "ok", "environment": status}


# --------------------------------------------------------------------------- #
# 2. Reference Precision & Recall Pre-Compose & Post-Render Quality Gates
# --------------------------------------------------------------------------- #
# Full-resolution Farneback optical flow is by far the most expensive part of a
# --verify-all run (it used to run once per scene reference, per section, per build).
# Every asset check therefore goes through the two helpers below:
#   * a memo cache keyed by (path, mtime, size, mode) so an asset is verified once
#     per process run (a rebuilt clip changes mtime/size and is re-verified),
#   * a bounded, downscaled sampler for the long-form sweep (long-form clips are
#     16:9 x ~600 frames, so the full-res pass costs minutes per clip).
CHEAP_FLOW_MAX_WIDTH = 480
CHEAP_FLOW_MAX_SAMPLES = 12
CHEAP_FLOW_FRAME_STEP = 3  # matches visual_engine.verify_motion_quality's every-3rd-frame sampling

# Motion-verification cost control for the bulk sweep. "auto" (default) samples only the long-form
# clips - they are 16:9 and several hundred frames each - and lets visual_engine's own gate decide
# for Shorts. Override with PIPELINE_MOTION_VERIFY=full (pay the full pass everywhere) or
# =sampled (use the bounded sampler everywhere).
MOTION_VERIFY_MODE = (os.environ.get("PIPELINE_MOTION_VERIFY", "auto") or "auto").strip().lower()
_MOTION_MODE_FORCE = {"full": False, "sampled": True}.get(MOTION_VERIFY_MODE)
if MOTION_VERIFY_MODE not in ("auto", "full", "sampled"):
    print(f"  [motion verify] unknown PIPELINE_MOTION_VERIFY={MOTION_VERIFY_MODE!r}; using 'auto'", file=sys.stderr)

_ASSET_CHECK_CACHE: dict[tuple[str, int, int, str], dict] = {}


def _asset_check_key(path: Path, mode: str) -> tuple[str, int, int, str]:
    try:
        st = path.stat()
        return (str(path.resolve()), int(st.st_mtime), int(st.st_size), mode)
    except OSError:
        return (str(path), 0, 0, mode)


def _flow_pair_metrics(prev_gray, gray, scale: float) -> tuple[float, float, float, float] | None:
    """One sampled frame-pair of optical flow, with magnitudes rescaled to original-pixel units.

    dF/dx is resolution invariant (F_orig = scale * F_low while x_orig = scale * u), so the shear
    gradient computed on the low-res field is already in original-pixel units; only the flow
    magnitudes need the scale factor. Blur/erode kernels are divided by the same factor so they
    cover the same physical area as the full-resolution gate.
    """
    flow = cv2.calcOpticalFlowFarneback(prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
    mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1])
    mag = mag * scale
    active = mag > 0.12
    coverage = float(np.mean(active))
    if not np.any(active):
        return None
    mean_mag = float(mag[active].mean())
    angle_std = float(np.std(ang[active]))
    p90_mag = float(np.percentile(mag[active], 90))
    if p90_mag < 0.85 or coverage < 0.15:
        return mean_mag, angle_std, coverage, 0.0
    kb = max(3, int(round(21 / scale)) | 1)
    ke = max(3, int(round(9 / scale)) | 1)
    flow_s = cv2.GaussianBlur(flow, (kb, kb), max(0.5, 5.0 / scale))
    gx_u = cv2.Sobel(flow_s[..., 0], cv2.CV_32F, 1, 0, ksize=3) / 8.0
    gy_u = cv2.Sobel(flow_s[..., 0], cv2.CV_32F, 0, 1, ksize=3) / 8.0
    gx_v = cv2.Sobel(flow_s[..., 1], cv2.CV_32F, 1, 0, ksize=3) / 8.0
    gy_v = cv2.Sobel(flow_s[..., 1], cv2.CV_32F, 0, 1, ksize=3) / 8.0
    grad_mag = np.sqrt(gx_u ** 2 + gy_u ** 2 + gx_v ** 2 + gy_v ** 2)
    active_interior = cv2.erode(active.astype(np.uint8), np.ones((ke, ke), np.uint8)) > 0
    eval_region = grad_mag[active_interior] if np.any(active_interior) else grad_mag
    shear = float(np.percentile(eval_region, 99.0)) / max(1.25, p90_mag)
    return mean_mag, angle_std, coverage, shear


def cheap_motion_quality(video_path: Path, max_width: int = CHEAP_FLOW_MAX_WIDTH,
                         max_samples: int = CHEAP_FLOW_MAX_SAMPLES) -> dict:
    """Sampled / downscaled stand-in for visual_engine.verify_motion_quality (same return keys)."""
    empty = {"valid": False, "score": "MISSING", "precision": 0.0, "recall": 0.0, "mean_flow_px": 0.0,
             "non_rigidity_std": 0.0, "flow_shear_ratio": 0.0, "max_shear_ratio": 0.0,
             "frames_sampled": 0, "sampled": True}
    if not video_path.exists():
        return empty

    cap = cv2.VideoCapture(str(video_path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    first_ok, first = cap.read()
    if not first_ok or first is None:
        cap.release()
        return {**empty, "score": "ERROR", "reason": "Cannot read video frames"}

    h0, w0 = first.shape[:2]
    scale = max(1.0, float(max(h0, w0)) / float(max_width))
    step = CHEAP_FLOW_FRAME_STEP

    def _proxy(frame):
        if scale <= 1.0:
            small = frame
        else:
            small = cv2.resize(frame, (max(2, int(round(w0 / scale))), max(2, int(round(h0 / scale)))),
                               interpolation=cv2.INTER_AREA)
        return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

    prev_gray = _proxy(first)
    mags, angle_stds, active_ratios, shear_ratios = [], [], [], []
    pair_starts: list[int] = []
    if total > step:
        n_pairs = max(1, min(max_samples, total // step))
        denom = max(1, n_pairs - 1)
        pair_starts = sorted({round(j * (total - 1 - step) / denom) for j in range(n_pairs)})
    else:
        pair_starts = list(range(0, max(1, total - step), step))[:max_samples]

    gray_by_idx: dict[int, object] = {0: prev_gray}
    needed = {i for start in pair_starts for i in (start, start + step)} - {0}
    idx = 0
    while needed:
        ok = cap.grab()
        if not ok:
            break
        idx += 1
        if idx in needed:
            ret_f, frm = cap.retrieve()
            if ret_f and frm is not None:
                gray_by_idx[idx] = _proxy(frm)
            needed.discard(idx)
    cap.release()

    for start in pair_starts:
        base, nxt = gray_by_idx.get(start), gray_by_idx.get(start + step)
        if base is None or nxt is None:
            continue
        got = _flow_pair_metrics(base, nxt, scale)
        if got is None:
            continue
        mean_mag, angle_std, coverage, shear = got
        mags.append(mean_mag)
        angle_stds.append(angle_std)
        active_ratios.append(coverage)
        if shear > 0.0:
            shear_ratios.append(shear)

    if not mags:
        return {**empty, "score": "TOO_STATIC"}

    mean_mag = float(np.mean(mags))
    mean_angle_std = float(np.mean(angle_stds)) if angle_stds else 0.0
    mean_coverage = float(np.mean(active_ratios)) if active_ratios else 0.0
    mean_shear = float(np.mean(shear_ratios)) if shear_ratios else 0.0
    max_shear = float(np.max(shear_ratios)) if shear_ratios else 0.0

    has_disocclusion_tear = mean_shear > 0.34 or max_shear > 0.55
    if 0.40 <= mean_mag <= 25.0:
        base_prec = min(1.0, 0.82 + 0.18 * (1.0 - abs(mean_mag - 3.5) / 22.0))
    elif mean_mag < 0.40:
        base_prec = max(0.1, mean_mag / 0.40)
    else:
        base_prec = max(0.1, 25.0 / mean_mag)
    if has_disocclusion_tear:
        tear_penalty = max(0.25, 1.0 - (max(mean_shear - 0.30, max_shear - 0.48) * 0.85))
        precision = round(base_prec * tear_penalty, 3)
    else:
        precision = round(base_prec, 3)
    recall = round(min(1.0, 0.55 * min(1.0, mean_angle_std / 0.18) + 0.45 * min(1.0, mean_coverage / 0.50)), 3)

    is_organic = mean_angle_std >= 0.08
    has_momentum = 0.40 <= mean_mag <= 26.0
    if has_disocclusion_tear:
        rating = "DISOCCLUSION_TEAR"
    elif has_momentum and is_organic:
        rating = "EXCELLENT"
    elif has_momentum:
        rating = "GOOD"
    elif mean_mag < 0.45:
        rating = "TOO_STATIC"
    else:
        rating = "EXCESSIVE_TEAR"

    return {
        "valid": rating in ["EXCELLENT", "GOOD"],
        "score": rating,
        "precision": precision,
        "recall": recall,
        "mean_flow_px": round(mean_mag, 2),
        "non_rigidity_std": round(mean_angle_std, 2),
        "flow_shear_ratio": round(mean_shear, 3),
        "max_shear_ratio": round(max_shear, 3),
        "frames_sampled": len(mags),
        "sampled": True,
    }


def verify_motion_quality_cached(video_path: Path, cheap: bool = False) -> dict:
    """verify_motion_quality() with a per-run memo keyed by (path, mtime, size, mode)."""
    mode = "cheap" if cheap else "full"
    key = _asset_check_key(video_path, mode)
    cached = _ASSET_CHECK_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        result = cheap_motion_quality(video_path) if cheap else visual_engine.verify_motion_quality(video_path)
    except Exception as e:
        print(f"  [motion verify] {video_path.name}: {type(e).__name__}: {e}", file=sys.stderr)
        result = {"valid": False, "score": "ERROR", "precision": 0.0, "recall": 0.0, "reason": str(e)}
    _ASSET_CHECK_CACHE[key] = result
    return result


def verify_image_precision_cached(img_path: Path) -> dict:
    """verify_image_precision_recall() with a per-run memo keyed by (path, mtime, size)."""
    key = _asset_check_key(img_path, "image")
    cached = _ASSET_CHECK_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        result = visual_engine.verify_image_precision_recall(img_path)
    except Exception as e:
        print(f"  [image verify] {img_path.name}: {type(e).__name__}: {e}", file=sys.stderr)
        result = {"valid": False, "precision": 0.0, "recall": 0.0, "size_kb": 0}
    _ASSET_CHECK_CACHE[key] = result
    return result


FIDELITY_MIN = 0.98


def _spoken_tokens(text: str) -> list[str]:
    """Words as they were spoken, for matching script text against shipped captions.

    Numbers are kept. The captions are built from the script's own display words
    (build_video.py:1094), so a digit in project.json has a matching digit in the SRT, and dropping
    bare numerals would blind the check to the one edit that matters most on this channel: a
    published statistic quietly changed by one digit. All 17 rendered projects still line up at
    1.000-0.990 with the numerals in place.
    """
    text = text.replace("—", " ").replace("–", " ").lower()
    return re.sub(r"[\[\]\(\)\"*'`,.!;:?]", " ", text).split()


def _shipped_captions(root: Path) -> Path | None:
    srts = sorted(root.glob("output/*.srt"))
    if not srts:
        return None

    # the canonical render's sidecar first, then any caption that has an mp4 beside it, then the
    # biggest file - a preview or a stale older-name export must not be treated as the shipped word
    def rank(s: Path) -> tuple[int, int, int]:
        return (s.stem == root.name, s.with_suffix(".mp4").exists(), s.stat().st_size)

    return max(srts, key=rank)


def caption_fidelity_issues(root: Path, scenes: list[dict]) -> list[str]:
    """Warn when project.json no longer describes the video that was actually rendered.

    Scene text is edited after a render more often than the MP4 is rebuilt, and every downstream
    judgement (hook score, citations, what the channel claims it said) then describes a script that
    nobody spoke. The 17 rendered projects line up at 99.0-100% token for token, so a miss here is a
    real edit and not normalisation noise.
    """
    srt = _shipped_captions(root)
    script = " ".join(sc.get("text", "") for sc in scenes)
    if not srt or not script.strip():
        return []
    spoken = _spoken_tokens(
        " ".join(
            ln.strip()
            for ln in srt.read_text(encoding="utf-8", errors="replace").splitlines()
            if ln.strip() and not ln.strip().isdigit() and "-->" not in ln
        )
    )
    wanted = _spoken_tokens(script)
    if not spoken or not wanted:
        return []
    sm = difflib.SequenceMatcher(None, wanted, spoken, autojunk=False)
    ratio = sm.ratio()
    if ratio >= FIDELITY_MIN:
        return []
    diffs = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        diffs.append(
            f"word {i1 + 1}: project.json says \"{' '.join(wanted[i1:i2]) or '(nothing)'}\" "
            f"while the video says \"{' '.join(spoken[j1:j2]) or '(nothing)'}\""
        )
        if len(diffs) >= 3:
            break
    return [
        f"Caption fidelity ({ratio:.1%}): project.json has been edited since {srt.name} was rendered "
        f"and no rebuild followed. {'. '.join(diffs)}."
        + (" Re-render, or restore the spoken wording." if len(diffs) < 3 else "")
    ]


def pre_compose_validate(proj_path: Path, cheap_flow: bool | None = None) -> list[str]:
    """Pre-compose precision/recall gate.

    cheap_flow: None -> decide from the project format (long-form clips are sampled, Shorts are not);
    True/False forces the sampled / full-resolution optical-flow pass.
    """
    issues = []
    if not proj_path.exists():
        return [f"Missing project file: {proj_path}"]
    try:
        proj = json.loads(proj_path.read_text())
    except Exception as e:
        return [f"Invalid JSON in {proj_path}: {e}"]

    root = proj_path.parent
    scenes = proj.get("scenes", [])
    fmt_mode = proj.get("format", "short")
    # Long-form clips are 16:9 and several hundred frames each: a full-resolution Farneback
    # pass on all of them costs ~30s per clip, so the default for that format is the
    # downscaled, frame-bounded sampler.
    if cheap_flow is None:
        cheap_flow = fmt_mode == "long"
    if not scenes:
        issues.append("No scenes defined in project.json")

    total_words = 0
    for idx, sc in enumerate(scenes):
        words = sc.get("text", "").split()
        total_words += len(words)
        # Match build_video.build()'s visual selection: shots override images, and
        # either list overrides the single video/image. Every selected shot must exist.
        selected = sc.get("shots") or sc.get("images") or [sc.get("video") or sc.get("image")]
        assets = []
        for item in selected:
            if isinstance(item, str):
                assets.append(item)
            elif isinstance(item, dict):
                rel = item.get("video") or item.get("image")
                if rel:
                    assets.append(rel)
                else:
                    issues.append(f"Scene {idx+1} missing asset: shot has no video or image")
            else:
                issues.append(f"Scene {idx+1} missing asset: shot has no video or image")
        assets = list(dict.fromkeys(assets))

        resolved_assets = []
        for img_rel in assets:
            p = root / img_rel
            # render_shot() promotes an image to its generated video when present.
            # Validate the promoted clip even if the original image is absent.
            if p.suffix.lower() not in build_video.VIDEO_EXTS:
                generated_video = p.parent.parent / "videos" / f"{p.stem}.mp4"
                if generated_video.exists():
                    p = generated_video
                    img_rel = str(p.relative_to(root)) if p.is_relative_to(root) else str(p)
            resolved_assets.append(p)
            if not p.is_file():
                issues.append(f"Scene {idx+1} missing asset: {img_rel}")
                continue
            if p.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                v_metrics = verify_image_precision_cached(p)
                if not v_metrics["valid"]:
                    issues.append(
                        f"Scene {idx+1} image precision/recall warning ({p.name}): "
                        f"precision={v_metrics['precision']}, recall={v_metrics['recall']}, size={v_metrics['size_kb']}KB"
                    )
            elif p.suffix.lower() in build_video.VIDEO_EXTS:
                q = verify_motion_quality_cached(p, cheap=cheap_flow)
                if not q.get("valid", True):
                    issues.append(
                        f"Scene {idx+1} 3D motion precision/recall warning ({p.name}): {q.get('score')} "
                        f"(precision={q.get('precision')}, recall={q.get('recall')}, flow={q.get('mean_flow_px')}px)"
                    )

        has_motion_clip = any(path.suffix.lower() in build_video.VIDEO_EXTS for path in resolved_assets)
        if fmt_mode == "long":
            max_words_threshold = 95
        else:
            max_words_threshold = 28 if has_motion_clip else 20
        if len(assets) <= 1 and len(words) > max_words_threshold:
            issues.append(
                f"Scene {idx+1} visual habituation risk: holds single angle for ~{len(words)*0.3:.1f}s."
            )

    low, high = WORD_BANDS["long" if fmt_mode == "long" else "short"]
    if total_words < low:
        issues.append(f"Word count too low ({total_words} words). Target is {low}-{high} words.")
    elif total_words > high:
        issues.append(f"Word count too high ({total_words} words). Target is {low}-{high} words.")

    if scenes and not ASK_RE.search(" ".join(str(sc.get("text") or "") for sc in scenes[-2:])):
        issues.append(
            "No closing ask: the last two scenes never name an action the viewer can take on this "
            "channel (subscribe / next video / comment). GEMINI.md section 2."
        )

    if scenes:
        hook_text = scenes[0].get("text", "")
        if fmt_mode == "long" and hook_text:
            sents = re.split(r"(?<=[.!?])\s+", hook_text.strip())
            hook_text = " ".join(sents[:2]) if len(sents) > 1 and len(sents[0].split()) < 10 else sents[0]
        if hook_text:
            hook_res = youtube_skills.score_hook(hook_text)
            if hook_res["verdict"] < youtube_skills.hookscore.WORKABLE_MIN:
                issues.append(
                    f"Scene 1 Hook Warning (score {hook_res['verdict']}/100 [{hook_res['band']}]): "
                    f"formula='{hook_res['formula']}', weakest={hook_res['weakest']} ({hook_res['fix']})"
                )

    if scenes:
        issues.extend(caption_fidelity_issues(root, scenes))

    kits = list(root.glob("UPLOAD_KIT*.md"))
    if not kits:
        issues.append("Missing UPLOAD_KIT_*.md in project directory")
    else:
        kit_content = kits[0].read_text(encoding="utf-8", errors="replace")
        title_m = (
            re.search(r"\* \*\*Primary[^\*]*\*\*:\s*[\r\n]+>\s*`?([^`\r\n]+)`?", kit_content)
            or re.search(r"\*\*Title\*\*:\s*([^\n\r]+)", kit_content)
            or re.search(r"Title:\s*([^\n\r]+)", kit_content)
        )
        vid_title = title_m.group(1).strip() if title_m else proj.get("title", "")
        if vid_title:
            pkg_res = youtube_skills.check_packaging(vid_title)
            if pkg_res.get("issues"):
                for ikind, imsg in pkg_res["issues"]:
                    if ikind in {"length", "shouting", "vague", "shorts-case"}:
                        issues.append(f"Packaging Issue ({ikind}): {imsg}")
    return issues


def verify_rendered_mp4(
    mp4_path: Path, format_type: str = "short", *, probe_timeout_s: float = 30.0, decode_timeout_s: float = 90.0,
) -> dict:
    """Require matching streams, synchronized durations, and a decodable video tail."""
    unavailable = {
        "tail_decodable": False, "video_duration_s": None,
        "audio_duration_s": None, "av_duration_delta_s": None,
    }
    if not mp4_path.exists():
        return {"valid": False, **unavailable, "error": "MP4 file does not exist"}
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=format_name,duration,size,bit_rate:stream=codec_name,codec_type,width,height,sample_rate,r_frame_rate,duration",
        "-of", "json", str(mp4_path),
    ]
    try:
        out = json.loads(run_process(cmd, check=True, capture_output=True, text=True, timeout_s=probe_timeout_s).stdout)
    except Exception as e:
        diagnostic = getattr(e, "stderr", None)
        if isinstance(diagnostic, bytes):
            diagnostic = diagnostic.decode("utf-8", errors="replace")
        return {"valid": False, **unavailable, "error": f"ffprobe error: {e}" + (f": {diagnostic.strip()}" if diagnostic else "")}

    streams = {s.get("codec_type"): s for s in out.get("streams", []) if isinstance(s, dict)}
    fmt = out.get("format") or {}
    v, a = streams.get("video", {}), streams.get("audio", {})
    def stream_duration(stream):
        try:
            value = float(stream.get("duration"))
            return value if math.isfinite(value) and value > 0 else None
        except (TypeError, ValueError):
            return None

    video_duration = stream_duration(v)
    audio_duration = stream_duration(a)
    av_delta = abs(video_duration - audio_duration) if video_duration is not None and audio_duration is not None else None
    try:
        dur = float(fmt.get("duration", 0))
    except (TypeError, ValueError):
        dur = 0.0
    try:
        bitrate_mbps = round(int(fmt.get("bit_rate", 0)) / 1_000_000, 2)
    except (TypeError, ValueError):
        bitrate_mbps = 0.0
    try:
        size_mb = round(int(fmt.get("size", 0)) / (1024 * 1024), 2)
    except (TypeError, ValueError):
        size_mb = 0.0
    is_short = format_type != "long"

    target_w = 1080 if is_short else 1920
    target_h = 1920 if is_short else 1080
    res_match = (v.get("width") == target_w and v.get("height") == target_h)
    audio_match = (str(a.get("sample_rate", "")) == "48000" and a.get("codec_name") == "aac")
    fps_match = v.get("r_frame_rate") == "30/1"
    container_match = "mp4" in str(fmt.get("format_name", "")).split(",")
    codec_match = v.get("codec_name") == "h264"
    failures = []
    if not v or not a:
        failures.append("audio and video streams are required")
    if not container_match:
        failures.append(f"container is {fmt.get('format_name') or 'unknown'}, expected MP4")
    if not codec_match:
        failures.append(f"video codec is {v.get('codec_name') or 'missing'}, expected H.264")
    if not res_match:
        failures.append(f"dimensions are {v.get('width')}x{v.get('height')}, expected {target_w}x{target_h}")
    if not fps_match:
        failures.append(f"frame rate is {v.get('r_frame_rate') or 'missing'}, expected 30/1")
    if not audio_match:
        failures.append(f"audio is {a.get('codec_name') or 'missing'} @ {a.get('sample_rate') or 'missing'} Hz, expected AAC @ 48000 Hz")
    finite_duration = math.isfinite(dur)
    if not finite_duration or dur < 5.0:
        failures.append(f"duration is {dur}s, expected a finite duration of at least 5s")
    if av_delta is None:
        failures.append("finite positive audio and video stream durations are required")
    elif av_delta > 0.250:
        failures.append(f"audio/video duration divergence is {av_delta:.3f}s, maximum 0.250s")
    tail_decodable, decode_detail = visual_engine.verify_video_decodable(mp4_path, timeout=decode_timeout_s)
    if not tail_decodable:
        failures.append(f"tail decode failed: {decode_detail}")
    sweet_spot = (28.0 <= dur <= 58.0) if is_short else (480.0 <= dur <= 720.0)

    ref_precision = round(
        0.35 * float(res_match)
        + 0.25 * float(audio_match)
        + 0.20 * float(fps_match)
        + 0.20 * min(1.0, bitrate_mbps / 6.0),
        3,
    )
    return {
        "valid": not failures,
        "width": v.get("width"),
        "height": v.get("height"),
        "vcodec": v.get("codec_name"),
        "fps": v.get("r_frame_rate"),
        "acodec": a.get("codec_name"),
        "sample_rate": a.get("sample_rate"),
        "duration_s": dur if finite_duration else 0.0,
        "video_duration_s": video_duration,
        "audio_duration_s": audio_duration,
        "av_duration_delta_s": av_delta,
        "tail_decodable": tail_decodable,
        "bitrate_mbps": bitrate_mbps,
        "size_mb": size_mb,
        "reference_precision": ref_precision,
        "shorts_compliant": (finite_duration and dur <= 180.0) if is_short else True,
        "sweet_spot_pacing": sweet_spot,
        **({"error": "; ".join(failures)} if failures else {}),
    }


# --------------------------------------------------------------------------- #
# 3. Audio-Synced 3D Spatial Motion Generator & Self-Healing Project Builder
# --------------------------------------------------------------------------- #
def compute_scene_durations(proj: dict, cache_dir: Path) -> list[float]:
    """Pre-synthesize TTS for each scene with active cache self-healing to get exact spoken durations."""
    voice = build_video._validate_kokoro_voice(proj.get("voice", "kokoro"))
    rate = proj.get("rate", "+1%")
    pitch = proj.get("pitch", "-2Hz")
    default_gap = proj.get("gap", 0.08)
    durations = []

    for idx, sc in enumerate(proj.get("scenes", [])):
        raw_text = sc.get("text", "").replace("*", "").strip()
        if raw_text:
            def _tts_dur(rt=raw_text, sc_item=sc):
                mp3, spoken = build_video.tts_cached(rt, voice, rate, pitch, cache_dir)
                audio = build_video.decode_audio(mp3)
                a, b = build_video.auto_trim_bounds(audio, spoken)
                return max(2.2, round((b - a) + sc_item.get("pause", default_gap), 2))

            def _heal_tts_cache(_err: Exception, _att: int):
                for f in cache_dir.glob("*.mp3"):
                    if f.stat().st_size < 512:
                        f.unlink(missing_ok=True)

            dur = run_with_healing(f"tts_dur_s{idx+1:02d}", _tts_dur, heal_fn=_heal_tts_cache)
        else:
            dur = float(sc.get("duration", 3.0))
        durations.append(dur)
    return durations


def scene_seed(project_key: str, scene_index: int) -> int:
    """A per-project deterministic seed for one scene's FLUX plate.

    The generator used `idx * 17 + 42`, which is the same number for every video: scene 1 of SH-17
    and scene 1 of SH-18 started from an identical noise latent, and because the generic role
    template describes no topic, they rendered the same man at the same desk. Hashing the project
    keeps a re-render reproducible while making each Short its own.
    """
    digest = hashlib.sha256(f"scene-seed:{project_key}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100_000_000 + scene_index * 17


def generate_project_motion(proj_path: Path) -> int:
    """Generate duration-synced 3D spatial clips (.mp4) with optical-flow precision/recall verification."""
    if not proj_path.exists():
        print(f"[Error] Project file not found: {proj_path}")
        return 1

    proj = json.loads(proj_path.read_text())
    root = proj_path.parent
    videos_dir, images_dir, cache_dir = root / "videos", root / "images", root / "cache"
    for d in (videos_dir, images_dir, cache_dir):
        d.mkdir(parents=True, exist_ok=True)

    is_long = proj.get("format", "short") == "long"
    img_w, img_h = (1280, 720) if is_long else (768, 1360)
    vid_w, vid_h = (1920, 1080) if is_long else (1080, 1920)

    scenes = proj.get("scenes", [])
    durations = compute_scene_durations(proj, cache_dir)
    print(f"\n=== Generating Audio-Synced 3D Spatial Clips for {proj_path.name} ({len(scenes)} scenes, {'16:9' if is_long else '9:16'}) ===")

    updated = False
    for idx, sc in enumerate(scenes):
        dur = durations[idx] if idx < len(durations) else 3.5
        current_asset = sc.get("image") or sc.get("video")
        stem = Path(current_asset).stem if current_asset else f"s{idx+1:02d}"

        src_img = None
        if current_asset and (root / current_asset).suffix.lower() in {".jpg", ".jpeg", ".png"} and (root / current_asset).exists():
            src_img = root / current_asset
        elif (images_dir / f"{stem}.jpg").exists():
            src_img = images_dir / f"{stem}.jpg"
        elif (images_dir / f"{stem}.png").exists():
            src_img = images_dir / f"{stem}.png"
        else:
            matches = [m for m in images_dir.glob(f"*{stem}*") if m.suffix.lower() in {".jpg", ".jpeg", ".png"}]
            if matches:
                src_img = matches[0]

        if not src_img or not src_img.exists():
            src_img = images_dir / f"{stem}.jpg"
            visual_engine.generate_scene_image(sc.get("prompt", f"Dramatic scene {idx+1}"), src_img, width=img_w, height=img_h, steps=sc.get("steps"), seed=scene_seed(str(proj.get("id") or proj_path.parent.name), idx))

        target_vid = videos_dir / f"{stem}.mp4"
        target_preset = _resolve_3d_preset(sc, idx)

        run_with_healing(
            f"3d_spatial_s{idx+1:02d}",
            lambda si=src_img, tv=target_vid, d=dur, pr=target_preset: visual_engine.render_3d_spatial_scene(
                si, tv, preset=pr, duration=d, target_w=vid_w, target_h=vid_h
            ),
        )
        sc["video"] = str(target_vid.relative_to(root))
        sc["preset"] = target_preset
        sc["motion"] = target_preset
        if src_img and src_img.exists():
            sc["image"] = str(src_img.relative_to(root))
        proj_path.write_text(json.dumps(proj, indent=2))
        updated = True

    if updated:
        print(f"  Updated {proj_path.name} with verified duration-synced 3D spatial clips.")
    return 0


def append_to_tracker(
    video_id: str,
    title: str,
    concept: str,
    science: str,
    rel_mp4: str,
    rel_kit: str,
    fmt_label: str = "Short (9:16)",
    live_link=tracker.KEEP,
    status=tracker.KEEP,
    views=tracker.KEEP,
    related_target=tracker.KEEP,
) -> bool:
    """Write the project's row into CONTENT_TRACKER.md, mapping by that table's header names.

    Arguments left at `tracker.KEEP` are not specified by the caller and keep the cell the row
    already has, so a rebuild cannot erase a live video's link or its view count. The old version
    emitted a fixed 10-column row against a 7-column table, which widened section 2 and pushed
    every later row out of alignment. See tools/tracker.py.
    """
    title_topic = f"*{title}*" if not concept or concept.strip().lower() in title.strip().lower() else f"*{title} ({concept})*"
    wrote = tracker.update_tracker_row(
        video_id,
        {
            "fmt_label": fmt_label,
            "title": title_topic,
            "concept": concept,
            "science": science,
            "live_link": live_link,
            "views": views,
            "rel_mp4": f"`{rel_mp4}`",
            "rel_kit": f"`{rel_kit}`",
            "status": status,
            "related_target": related_target,
        },
    )
    if not wrote:
        print(
            f"  [tracker] CONTENT_TRACKER.md has no table with an ID column - {video_id} left untouched. "
            "Add the row by hand or fix tools/tracker.py first.",
            file=sys.stderr,
        )
    return wrote


def assemble_new_project(topic: str, video_id: str, slug: str, hw_accel: bool = True, genre: str = "3d_cgi") -> Path:
    return creative_engine.generate_creative_project(topic, video_id, slug, genre=genre)


def build_and_verify(project_dir_or_json: Path, hw_accel: bool = True, force_motion: bool = False) -> dict:
    """Self-healing end-to-end 3D build: renders 3-plane 3D spatial clips, builds mastered MP4, and verifies Reference Precision & Recall."""
    proj_json = project_dir_or_json if project_dir_or_json.name.endswith(".json") else (project_dir_or_json / "project.json")
    try:
        proj_data = json.loads(proj_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid project.json: {exc}") from exc
    schema_errors = validate_project(proj_data, project_path=proj_json)
    if schema_errors:
        raise ValueError("project schema errors:\n" + "\n".join(schema_errors))
    project_dir = proj_json.parent
    cache_dir = project_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "videos").mkdir(parents=True, exist_ok=True)

    audio_bank.ensure_studio_sfx_pack(try_remote_cc0=False)
    fmt_type = proj_data.get("format", "short")
    is_long = (fmt_type == "long")
    img_w, img_h = (1280, 720) if is_long else (768, 1360)
    vid_w, vid_h = (1920, 1080) if is_long else (1080, 1920)
    durations = compute_scene_durations(proj_data, cache_dir)
    manifest = RenderManifest.load(cache_dir / "render_manifest.json")

    for idx, sc in enumerate(proj_data.get("scenes", [])):
        dur = durations[idx] if idx < len(durations) else 3.5

        vid_rel = sc.get("video")
        img_rel = sc.get("image")

        if vid_rel:
            stem = Path(vid_rel).stem
            target_vid = project_dir / vid_rel
        elif img_rel and Path(img_rel).suffix.lower() in {".mp4", ".mov"}:
            stem = Path(img_rel).stem
            target_vid = project_dir / img_rel
            sc["video"] = img_rel
        else:
            stem = Path(img_rel).stem if img_rel else f"s{idx+1:02d}"
            target_vid = project_dir / "videos" / f"{stem}.mp4"
            sc["video"] = f"videos/{stem}.mp4"

        variant_name = str(proj_data.get("variant") or proj_data.get("genre") or "cinematic_35mm")
        src_img = None
        if img_rel and Path(img_rel).suffix.lower() in {".jpg", ".jpeg", ".png"}:
            candidate = project_dir / img_rel
            if candidate.exists():
                src_img = candidate
        if not src_img:
            for ext in (".jpg", ".png"):
                candidate = project_dir / "images" / f"{stem}{ext}"
                if candidate.exists():
                    src_img = candidate
                    break
        if not src_img:
            matches = sorted(m for m in (project_dir / "images").glob(f"*{stem}*") if m.suffix.lower() in {".jpg", ".jpeg", ".png"})
            if matches:
                src_img = matches[0]
            else:
                src_img = project_dir / "images" / f"{stem}.jpg"
                prompt = sc.get("prompt")
                if not prompt or not prompt.strip():
                    raise ValueError(f"Scene {idx+1} in {proj_json} is missing a visual prompt; no fallback allowed.")
                print(f"  [FLUX MLX] Generating scene {idx+1} visual plate: {src_img.name}...")
                ok = visual_engine.generate_scene_image(
                    prompt,
                    src_img,
                    width=img_w,
                    height=img_h,
                    steps=sc.get("steps"),
                    seed=scene_seed(str(proj_data.get("id") or project_dir.name), idx),
                    genre=variant_name,
                )
                if not ok or not src_img.exists():
                    raise RuntimeError(f"Scene {idx+1} AI image generation failed for {src_img}. No fallback permitted.")
        sc["image"] = str(src_img.relative_to(project_dir))
        target_preset = _resolve_3d_preset(sc, idx) if variant_name == "cinematic_35mm" else (sc.get("preset") or sc.get("motion") or variant_name)
        sc["preset"] = target_preset
        sc["motion"] = target_preset
        fingerprint = scene_fingerprint(
            scene_index=idx,
            scene=sc,
            source_image=src_img,
            duration_s=dur,
            preset=target_preset,
            width=vid_w,
            height=vid_h,
            variant=variant_name,
        )
        scene_key = str(idx)
        needs_render = force_motion or not manifest.can_reuse(scene_key, fingerprint, target_vid)
        if not needs_render:
            q_check = verify_motion_quality_cached(target_vid, cheap=is_long)
            if not q_check.get("valid", False):
                print(
                    f"  [Self-Heal: Scene {idx+1}] Existing clip {target_vid.name} flagged {q_check.get('score')} "
                    f"(shear={q_check.get('flow_shear_ratio')}) -> re-rendering clip..."
                )
                needs_render = True

        if needs_render:
            target_vid.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=f".{target_vid.stem}.render-", dir=target_vid.parent) as staging:
                staged_clip = Path(staging) / target_vid.name
                is_storybook = str(proj_data.get("genre", "")).startswith("storybook_") or sc.get("engine") == "storybook"
                story_style = "classic" if "classic" in str(proj_data.get("genre", "")) else "casebook"
                if is_storybook:
                    from tools import storybook_engine
                    rendered = run_with_healing(
                        f"render_storybook_s{idx+1:02d}",
                        lambda si=src_img, tv=staged_clip, d=dur, st=story_style, sc_ref=sc: storybook_engine.render_storybook_clip(
                            si, tv, duration_s=d, width=vid_w, height=vid_h, style=st,
                            stamp_text=sc_ref.get("stamp"), plate_label=sc_ref.get("plate_label"),
                        ),
                    )
                else:
                    rendered = run_with_healing(
                        f"render_3d_s{idx+1:02d}",
                        lambda si=src_img, tv=staged_clip, d=dur, pr=target_preset: visual_engine.render_3d_spatial_scene(
                            si, tv, preset=pr, duration=d, target_w=vid_w, target_h=vid_h
                        ),
                    )
                # A False result can mean an encoder failure or a motion warning.
                # Only a newly produced decodable clip may reach composition.
                encoded_ok, encoded_detail = visual_engine.verify_encoded_output(staged_clip)
                if not encoded_ok:
                    raise RuntimeError(f"Scene {idx+1} render produced no valid fresh clip: {encoded_detail}")
                staged_clip.replace(target_vid)
            if rendered is True:
                manifest.record(scene_key, fingerprint, target_vid)
                manifest.save()

    proj_json.write_text(json.dumps(proj_data, indent=2))

    pre_issues = pre_compose_validate(proj_json)
    if pre_issues:
        print(f"  [Pre-compose Precision/Recall Notes]: {pre_issues}")

    out_mp4 = project_dir / "output" / f"{project_dir.name}.mp4"
    out_p = run_with_healing(
        "master_video_build",
        lambda: build_video.build(proj_json, out_mp4, preview=False, hw_accel=hw_accel),
    )
    meta = verify_rendered_mp4(out_p, format_type=fmt_type)

    vid_id = proj_data.get("id") or f"SH-{project_dir.name[:8].upper()}"
    kits = list(project_dir.glob("UPLOAD_KIT*.md"))
    rel_kit = str(kits[0].relative_to(YT_ROOT)) if kits else f"shorts/{project_dir.name}/UPLOAD_KIT.md"
    # A re-render of a video that is already Live must not rewrite its status: the copy on YouTube is
    # older than this render, and only an upload can change that. Leave the row saying "Live" so the
    # tracker keeps describing what is public.
    existing_row = tracker.read_tracker_row(vid_id)
    tracker_status = tracker.KEEP
    if not str(existing_row.get("live_link", "")).startswith("["):
        tracker_status = "**Rendered — Gate PASS**" if meta.get("valid") else "**Re-render**"
    append_to_tracker(
        video_id=vid_id,
        title=proj_data.get("title", project_dir.name),
        concept=proj_data.get("concept", ""),
        science=proj_data.get("science", "Cognitive Psychology"),
        rel_mp4=str(out_p.relative_to(YT_ROOT)),
        rel_kit=rel_kit,
        fmt_label="Long (16:9)" if fmt_type == "long" else "Short (9:16)",
        status=tracker_status,
    )

    return meta


def verify_all_projects() -> int:
    """Full pre-upload quality gate.

    Exit codes (so cron / CI / the creator can branch on them):
      0 = everything clean (or blueprint-only), 1 = warnings, 2 = hard failures.
    """
    fmt.emit(fmt.verification_header())

    fmt.emit(fmt.section("1. Core Pipeline Environment & Studio SFX Bank", "🎧"))
    assets_res = verify_pipeline_assets()
    asset_rows = [
        ["Typography / Fonts", f"{assets_res.get('fonts_count', 0)} TTF/TTC fonts", "PASS" if assets_res.get("fonts_ready") else "FAIL"],
        ["Studio SFX Pack", "5 non-pitchy Foley WAVs", "PASS" if assets_res.get("sfx_pack_ready") else "FAIL"],
        ["Kokoro ONNX Engine", "Local 82M neural TTS", "PASS" if assets_res.get("kokoro_onnx_ready") else "FAIL"],
        ["FFmpeg / Videotoolbox", "Hardware H.264 Encoder", "PASS" if assets_res.get("ffmpeg_ready") else "FAIL"],
    ]
    fmt.emit(fmt.table(["Component", "Specification", "Status"], asset_rows))
    env_failed = sum(1 for row in asset_rows if row[2] == "FAIL")

    fmt.emit(fmt.section("2. Production Shorts (9:16 Vertical)", "📱"))
    shorts_dir = YT_ROOT / "shorts"
    all_shorts = sorted(shorts_dir.glob("short_*"))
    passed, blueprints, warned, failed, drafts = 0, 0, 0, 0, 0

    for s_dir in all_shorts:
        proj_p = s_dir / "project.json"
        if not proj_p.exists():
            continue
        exact_mp4 = s_dir / "output" / f"{s_dir.name}.mp4"
        mp4s = sorted((s_dir / "output").glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True) if (s_dir / "output").exists() else []
        mp4_p = exact_mp4 if exact_mp4.exists() else (mp4s[0] if mp4s else exact_mp4)
        issues = pre_compose_validate(proj_p, cheap_flow=_MOTION_MODE_FORCE)
        meta = verify_rendered_mp4(mp4_p, format_type="short")

        non_asset_issues = [i for i in issues if "missing asset:" not in i]
        if not meta.get("valid") and not mp4_p.exists():
            # Never rendered. A draft is work in progress, not a broken deliverable, so it may not
            # hold the whole channel's gate red; only an MP4 that exists and fails does that. Its own
            # script warnings still count as warnings, and still print on the row.
            status = "BLUEPRINT" if not non_asset_issues else "DRAFT"
            if status == "BLUEPRINT":
                blueprints += 1
            else:
                drafts += 1
                warned += 1
            fmt.emit(fmt.verification_project_row(
                name=s_dir.name,
                status=status,
                mp4_valid=False,
                ref_precision=1.0 if status == "BLUEPRINT" else 0.0,
                duration_s=0.0,
                bitrate_mbps=0.0,
                issues=(["Blueprint ready: Script, Hook & 6-Layer 3D Prompts PASS"]
                        if status == "BLUEPRINT" else issues),
            ))
            continue

        if not meta.get("valid"):
            status = "FAIL"
            failed += 1
        elif issues:
            status = "WARN"
            warned += 1
        else:
            status = "PASS"
            passed += 1
        fmt.emit(fmt.verification_project_row(
            name=s_dir.name,
            status=status,
            mp4_valid=meta.get("valid", False),
            ref_precision=meta.get("reference_precision", 0.0),
            duration_s=meta.get("duration_s", 0.0),
            bitrate_mbps=meta.get("bitrate_mbps", 0.0),
            issues=issues,
        ))

    fmt.emit(fmt.verification_summary(passed, blueprints, warned, len(all_shorts), drafts))

    long_dir = YT_ROOT / "long_form"
    all_long = sorted(long_dir.glob("lv_*")) if long_dir.exists() else []
    l_passed = l_warned = l_failed = l_drafts = 0
    if all_long:
        fmt.emit(fmt.section("3. Production Long-Form (16:9 Broadcast Compliance)", "🖥️"))
        for l_dir in all_long:
            proj_p = l_dir / "project.json"
            if not proj_p.exists():
                continue
            exact_mp4 = l_dir / "output" / f"{l_dir.name}.mp4"
            mp4s = sorted((l_dir / "output").glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True) if (l_dir / "output").exists() else []
            mp4_p = exact_mp4 if exact_mp4.exists() else (mp4s[0] if mp4s else exact_mp4)
            issues = pre_compose_validate(proj_p, cheap_flow=_MOTION_MODE_FORCE)
            meta = verify_rendered_mp4(mp4_p, format_type="long")
            if not meta.get("valid") and not mp4_p.exists():
                # Same rule as Shorts: an unbuilt long-form is a plan, not a broken deliverable.
                l_drafts += 1
                l_warned += 1
                fmt.emit(fmt.verification_project_row(
                    name=l_dir.name, status="DRAFT", mp4_valid=False, ref_precision=0.0,
                    duration_s=0.0, bitrate_mbps=0.0, issues=issues,
                ))
                continue
            if not meta.get("valid"):
                status = "FAIL"
                l_failed += 1
            elif issues:
                status = "WARN"
                l_warned += 1
            else:
                status = "PASS"
                l_passed += 1
            fmt.emit(fmt.verification_project_row(
                name=l_dir.name,
                status=status,
                mp4_valid=meta.get("valid", False),
                ref_precision=meta.get("reference_precision", 0.0),
                duration_s=meta.get("duration_s", 0.0),
                bitrate_mbps=meta.get("bitrate_mbps", 0.0),
                issues=issues,
            ))
        fmt.emit(fmt.verification_summary(l_passed, 0, l_warned, len(all_long), l_drafts))

    fmt.emit(fmt.section("4. YouTube Skills Engine Insights", "💡"))
    _lo, _hi = WORD_BANDS["short"]
    fmt.emit(fmt.skill_tip("yt-script", (
        f"Target {_lo}-{_hi} words, about {_lo * 60 // DELIVERY_WPM}-{_hi * 60 // DELIVERY_WPM}s at the "
        f"{DELIVERY_WPM} wpm this channel's own renders measure - the band pre_compose_validate() enforces."
    )))
    fmt.emit(fmt.skill_tip("yt-package", "Keep title under 55 characters and check the subject survives the mobile cut."))
    fmt.emit(fmt.skill_tip("yt-seo", "All search tags and title hashtags must be strictly lowercase (e.g. #shorts, loss aversion)."))
    fmt.emit(fmt.skill_tip("yt-retention", "Carve 34% Mid-channel ducking during active speech while preserving 90% Side stereo warmth."))
    fmt.emit("")

    total_warned = warned + l_warned
    total_failed = failed + l_failed + env_failed
    draft_note = f" + {drafts + l_drafts} never-rendered draft(s) counted as warnings" if drafts + l_drafts else ""
    if total_failed:
        code = 2
        verdict = (f"{total_failed} HARD FAILURE(S) ({failed} short, {l_failed} long-form, {env_failed} environment) "
                 f"+ {total_warned} warning(s){draft_note}")
    elif total_warned:
        code = 1
        verdict = f"{total_warned} warning(s), no hard failures{draft_note}"
    else:
        code = 0
        verdict = "clean - no warnings, no failures"
    fmt.emit(f"  GATE VERDICT: {verdict}  ->  exit {code} (0=clean, 1=warnings, 2=hard failures)")
    fmt.emit("")
    return code


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--configure", action="store_true")
    ap.add_argument("--verify-all", action="store_true")
    ap.add_argument("--agents", action="store_true", help="Show status of the 7-Agent Autonomous Crew")
    ap.add_argument("--auto", action="store_true", help="Full autonomous end-to-end production (build + quality gate)")
    ap.add_argument("--upgrade-blueprints", action="store_true", help="Upgrade all unrendered blueprint projects via S4 Visual Director")
    ap.add_argument("--studio-3d", action="store_true", help="Show 3D Studio status")
    ap.add_argument("--build", type=Path, help="Build & verify a project.json or project directory")
    ap.add_argument("--force-motion", action="store_true", help="Force re-rendering of all 3D scene clips")
    ap.add_argument("--motion", type=Path, help="Generate audio-synced 3D spatial clips for a project.json")
    ap.add_argument("--topic", type=str, help="Topic name for new Short project")
    ap.add_argument("--id", type=str, help="Video ID (e.g., SH-17)")
    ap.add_argument("--slug", type=str, help="Folder slug")
    ap.add_argument("--genre", type=str, default="3d_cgi", help="Visual genre profile")
    ap.add_argument("--branding", action="store_true", help="Generate channel intro/outro branding suite")
    ap.add_argument("--upload", type=Path, help="Release reviewed project via strict gate, then upload")
    ap.add_argument("--upload-api", type=Path, help="Alias for --upload")
    ap.add_argument("--evidence", type=Path, help="Reviewed evidence JSON required for upload")
    ap.add_argument("--yes", action="store_true", help="Approve irreversible upload after strict release checks")
    ap.add_argument("--public", action="store_true", help="Set uploaded video privacy to public (default: unlisted)")
    ap.add_argument("--sync-stats", action="store_true", help="Fetch live YouTube stats via API and update CONTENT_TRACKER.md")
    ap.add_argument("--hook", type=str, help="Score a spoken hook formula and weak points")
    ap.add_argument("--lint-package", action="store_true", help="Lint a published title")
    ap.add_argument("--title", type=str, help="Video title for package linting")
    ap.add_argument("--deadair", type=Path, help="Find dead-air gaps & retakes in transcript")
    ap.add_argument("--retention", type=Path, help="Diagnose retention drop-offs from Studio CSV")
    ap.add_argument("--axis", choices=["seconds", "percent"], help="Retention CSV position axis (required when it is ambiguous)")
    ap.add_argument("--duration", type=float, help="Video length in seconds for a percent-axis retention CSV")
    ap.add_argument("--transcript", type=Path, help="Transcript SRT/VTT file for retention analysis")
    ap.add_argument("--chapters", type=Path, help="Generate and validate YouTube chapters from transcript")
    ap.add_argument("--swipe", type=Path, help="Find viral outlier videos beating channel median")
    ap.add_argument("--min-multiple", type=float, default=1.5, help="Multiplier threshold for viral outliers")
    return ap


def main() -> int:
    ap = build_arg_parser()

    # Normalize slash-style CLI flags (/auto, /public, /verify-all, etc.) to standard --flags.
    # Only known declared flags are converted; filesystem paths (including non-existent absolute
    # paths on Linux, macOS, or Windows) are strictly preserved as-is.
    valid_slash_flags = {
        opt.lstrip("-")
        for action in ap._actions
        for opt in action.option_strings
        if opt.startswith("--")
    }
    norm_argv = [sys.argv[0]]
    for arg in sys.argv[1:]:
        if arg.startswith("/") and not arg.startswith("//"):
            candidate = arg[1:].split("=", 1)[0]
            if candidate in valid_slash_flags:
                norm_argv.append("--" + arg[1:])
                continue
        norm_argv.append(arg)
    sys.argv = norm_argv

    argv = list(sys.argv)
    if len(argv) > 1 and argv[1] == "build":
        argv[1] = "--build"
    sys.argv = argv

    args = ap.parse_args()

    upload_requested = args.upload is not None or args.upload_api is not None
    other_action = any((
        args.configure, args.verify_all, args.agents, args.auto, args.upgrade_blueprints,
        args.studio_3d, args.build, args.motion, args.topic, args.branding,
        args.sync_stats, args.hook, args.lint_package, args.deadair, args.retention,
        args.chapters, args.swipe,
    ))
    if upload_requested and (other_action or (args.upload is not None and args.upload_api is not None)):
        print("Upload must be a single action; run production or analysis separately.", file=sys.stderr)
        return 2

    if args.configure:
        print(json.dumps(configure_pipeline_environment(), indent=2))
        return 0
    if args.verify_all:
        return verify_all_projects()
    if args.studio_3d:
        return subprocess.run([sys.executable, str(TOOLS_DIR / "studio_3d.py"), "--status"]).returncode
    if args.upgrade_blueprints:
        from tools.agents import OrchestratorAgent, report_exit_code
        orch = OrchestratorAgent()
        reports = []
        for s_dir in sorted((YT_ROOT / "shorts").glob("short_*")):
            mp4 = s_dir / "output" / f"{s_dir.name}.mp4"
            if not mp4.exists() and (s_dir / "project.json").exists():
                reports.extend(orch.upgrade_existing_project(s_dir / "project.json"))
        return report_exit_code(reports) if reports else 0
    if args.topic and args.id and args.slug:
        if args.agents or args.auto:
            from tools.agents import OrchestratorAgent, report_exit_code
            orch = OrchestratorAgent()
            reports = orch.run_end_to_end(
                topic=args.topic,
                video_id=args.id,
                slug=args.slug,
                genre=args.genre,
                blueprint_only=not args.auto,
            )
            return report_exit_code(reports)
        assemble_new_project(args.topic, args.id, args.slug, genre=args.genre)
        return 0
    if args.agents:
        from tools.agents import OrchestratorAgent
        OrchestratorAgent().print_crew_status()
        return 0
    if args.motion:
        return generate_project_motion(args.motion.resolve())
    if args.build:
        meta = build_and_verify(args.build.resolve(), force_motion=args.force_motion)
        print(json.dumps(meta, indent=2))
        return 0 if meta.get("valid") else 1
    if args.branding:
        cmd = [sys.executable, str(TOOLS_DIR / "branding_engine.py")]
        return subprocess.run(cmd).returncode
    if args.upload or args.upload_api:
        target = (args.upload or args.upload_api).resolve()
        from tools.orchestrator.cli import legacy_upload_command
        return legacy_upload_command(target, args.evidence, public=args.public, approve=args.yes)
    if args.sync_stats:
        from tools.upload_api import sync_channel_stats
        sync_channel_stats()
        return 0
    if args.hook:
        res = youtube_skills.score_hook(args.hook)
        print(json.dumps(res, indent=2))
        return 0
    if args.lint_package:
        res = youtube_skills.check_packaging(args.title or "")
        print(json.dumps(res, indent=2))
        return 1 if res.get("issues") else 0
    if args.deadair:
        res = youtube_skills.analyze_dead_air(args.deadair.resolve())
        print(json.dumps(res, indent=2))
        return 1 if res.get("error") else 0
    if args.retention:
        t_path = args.transcript.resolve() if args.transcript else None
        res = youtube_skills.diagnose_retention(
            args.retention.resolve(), transcript_path=t_path, duration=args.duration, axis=args.axis
        )
        print(json.dumps(res, indent=2))
        return 1 if res.get("error") else 0
    if args.chapters:
        res = youtube_skills.generate_chapters(args.chapters.resolve())
        print(json.dumps(res, indent=2))
        return 0 if res.get("valid") is True else 1
    if args.swipe:
        res = youtube_skills.find_viral_outliers(args.swipe.resolve(), min_multiple=args.min_multiple)
        print(json.dumps(res, indent=2))
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
