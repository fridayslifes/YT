"""YouTube Skills & Heuristics Core Module (Integrated from youtube-agent-skill).

Exposes programmatic Python APIs for:
- Hook scoring & classification (hookscore)
- Title linting (title)
- Transcript dead-air & retake detection (deadair)
- Studio retention drop-off diagnosis (retention)
- YouTube chapter validation (chapters)
- Outlier virality scoring against channel median (swipe)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import hookscore
from . import title
from . import deadair
from . import retention
from . import chapters
from . import swipe

__all__ = [
    "score_hook",
    "check_packaging",
    "analyze_dead_air",
    "diagnose_retention",
    "generate_chapters",
    "find_viral_outliers",
    "hookscore",
    "title",
    "deadair",
    "retention",
    "chapters",
    "swipe",
]


def score_hook(text: str) -> dict[str, Any]:
    """Score a hook string across Specificity, Address, Stakes, Curiosity, Brevity."""
    parts, verdict, formula, hits = hookscore.score(text)
    b = hookscore.band(verdict)
    low = min(parts, key=parts.get)
    fix_msg = hookscore.FIX.get(low, "")
    return {
        "hook": text.strip(),
        "properties": parts,
        "verdict": verdict,
        "band": b,
        "formula": formula,
        "matched": hits,
        "weakest": low,
        "fix": fix_msg,
    }


def check_packaging(video_title: str) -> dict[str, Any]:
    """Lint a title for truncation, shouting, vagueness, and a missing concrete figure."""
    return title.check(video_title)


def analyze_dead_air(transcript_path: str | Path, floor: float = 0.45) -> dict[str, Any]:
    """Generate an EDL for gaps, whole filler cues and retakes, or an error dictionary."""
    try:
        cues = deadair.load(str(transcript_path))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return {"error": f"Could not read transcript: {exc}"}
    result = deadair.analyze_cues(cues, floor)
    return result if "error" in result else {"source": str(transcript_path), **result}


def diagnose_retention(
    csv_path: str | Path,
    transcript_path: str | Path | None = None,
    duration: float | None = None,
    axis: str | None = None,
) -> dict[str, Any]:
    """Read a YouTube Studio retention CSV and compute hook leak, cliffs, and slide.

    duration is the video length in seconds. It is required when the CSV exports a percent-of-video
    x-axis (the 30-second hook window cannot be placed on that axis without it); a seconds-axis CSV
    has the length in its own time column. axis is "seconds" or "percent" and is required whenever
    the position column cannot prove which one it is - see retention.hook_cutoff.
    """
    rows = retention.load_csv(str(csv_path))
    if len(rows) < 8:
        return {"error": "Could not read at least 8 data points from CSV"}
    xs = [r[0] for r in rows]
    ys = [r[1] for r in rows]

    try:
        duration_s, cutoff, pct_axis = retention.hook_cutoff(xs, duration, axis)
    except ValueError as e:
        return {"error": str(e)}

    def at(x):
        return (x / 100.0 * duration_s) if pct_axis else x

    start = ys[0] or 100.0
    hook_end = min((y for x, y in rows if x <= cutoff), default=start)
    hook_leak = start - hook_end

    drops = []
    for i in range(1, len(rows)):
        d = ys[i - 1] - ys[i]
        span = xs[i] - xs[i - 1] or 1
        drops.append((d / span, xs[i - 1], xs[i], d))
    drops.sort(reverse=True)
    cliffs = [
        {
            "from": round(a1, 2),
            "to": round(b1, 2),
            "lost": round(d, 2),
            "at_seconds": round(at(a1), 1),
        }
        for _, a1, b1, d in drops[:5]
        if d > 0.8
    ]
    mid = [d for d, x0, _, _ in [(r[0], r[1], r[2], r[3]) for r in drops] if x0 > cutoff]
    slide = sum(mid) / len(mid) if mid else 0

    said = {}
    if transcript_path and Path(transcript_path).exists():
        cues = deadair.load(str(transcript_path))
        for c in cliffs:
            t = c["at_seconds"]
            near = [q[2] for q in cues if q[0] <= t + 4 and q[1] >= t - 4]
            said[str(c["from"])] = " ".join(near)[:140]

    return {
        "points": len(rows),
        "duration_s": round(duration_s, 1),
        "hook_window_s": round(min(retention.HOOK_WINDOW_S, duration_s), 1),
        "start": start,
        "hook_leak": round(hook_leak, 2),
        "end": ys[-1],
        "cliffs": cliffs,
        "slide_per_unit": round(slide, 3),
        "said": said,
    }


def generate_chapters(transcript_path: str | Path, target: int = 7) -> dict[str, Any]:
    """Generate and validate YouTube chapters from an SRT/VTT/Whisper transcript."""
    try:
        cues = deadair.load(str(transcript_path))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return {"error": f"Could not read transcript: {exc}"}
    return chapters.generate(cues, target)


def find_viral_outliers(json_path: str | Path, min_multiple: float = 1.5) -> dict[str, Any]:
    """Rank collected competitor videos by multiple of their own channel's median views."""
    import json as _json

    raw_data = _json.loads(Path(json_path).read_text(encoding="utf-8"))
    rows = raw_data.get("videos", []) if isinstance(raw_data, dict) else raw_data
    return swipe.rank_outliers(rows, min_multiple)

