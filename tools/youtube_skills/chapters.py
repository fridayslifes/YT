#!/usr/bin/env python3
"""chapters.py - YouTube chapters from a timestamped transcript.

    python3 chapters.py transcript.srt            # or .vtt / whisper .json
    python3 chapters.py transcript.srt --target 8 --json

Prints a description block you can paste straight under a video. YouTube's own rules, enforced here
rather than assumed: the list must start at 00:00, needs at least three entries, and each chapter
must be at least 10 seconds long. A block that breaks any of those silently does not become
chapters, which is why this checks instead of trusting.

Boundaries come from the gaps - the pauses you actually took between sections - scored by how long
the pause was and how much the vocabulary changes across it. It is a first draft you retitle, not a
summariser.
"""
from __future__ import annotations

import json
import os
import re
import sys

try:  # imported as tools.youtube_skills.chapters (the pipeline and the tests always do)
    from .deadair import load, validate_timestamps
except ImportError:  # run as a bare script from this directory
    HERE = os.path.dirname(os.path.abspath(__file__))
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    from deadair import load, validate_timestamps

STOP = set(
    "the a an of for to in on and or is are was were be been with this that it as at by from "
    "you your i my we our they them he she but so if then than there here what which who how "
    "when where why not no yes do does did just really very like about into over out up down "
    "can could will would should have has had get got make made go going went one two".split()
)


def keywords(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z']{4,}", text.lower()) if w not in STOP}


def mmss(t: float) -> str:
    secs = int(t)
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def generate(cues: list[tuple[float, float, str]], target: int = 7) -> dict:
    """Generate and validate the actual whole-second timestamps pasted into YouTube."""
    if len(cues) < 6:
        return {"error": "Too few cues to generate chapters (minimum 6 required)"}
    try:
        validate_timestamps(cues)
    except ValueError as exc:
        return {"error": str(exc)}
    dur = max(end for _, end, _ in cues)
    cand = []
    speech_end = cues[0][1]
    for i in range(1, len(cues)):
        gap = cues[i][0] - speech_end
        speech_end = max(speech_end, cues[i][1])
        before = " ".join(c[2] for c in cues[max(0, i - 12):i])
        after = " ".join(c[2] for c in cues[i:i + 12])
        kb, ka = keywords(before), keywords(after)
        shift = 1 - (len(kb & ka) / len(kb | ka)) if (kb | ka) else 0
        cand.append((gap * 1.6 + shift * 3.2, cues[i][0], i))
    cand.sort(reverse=True)
    picked = [0.0]
    min_dist = 10.0
    for _, t, _ in cand:
        if len(picked) >= target:
            break
        t = float(int(t))
        if all(abs(t - p) >= min_dist for p in picked) and dur - t >= min_dist:
            picked.append(t)
    picked.sort()
    chapters = []
    for n, t in enumerate(picked):
        end = picked[n + 1] if n + 1 < len(picked) else dur
        text = " ".join(c[2] for c in cues if c[0] >= t and c[1] <= end)
        kw = list(keywords(text))
        kw.sort(key=lambda w: (-text.lower().count(w), -len(w), w))
        title = " / ".join(w.capitalize() for w in kw[:3]) or ("Intro" if n == 0 else f"Section {n + 1}")
        chapters.append({
            "start": t,
            "timestamp": mmss(t),
            "title": title,
            "seconds": round(end - t, 3),
        })
    lengths = [b - a for a, b in zip(picked, picked[1:] + [dur])]
    ok = len(chapters) >= 3 and picked[0] == 0 and all(seconds >= min_dist for seconds in lengths)
    return {"valid": ok, "duration": round(dur, 3), "chapters": chapters}


def main() -> None:
    a = sys.argv[1:]
    as_json = "--json" in a
    a = [x for x in a if x != "--json"]
    target = int(a[a.index("--target") + 1]) if "--target" in a else 7
    a = [x for x in a if not x.startswith("--") and not x.isdigit()]
    if not a or not os.path.exists(a[0]):
        print(__doc__)
        sys.exit(1)
    result = generate(load(a[0]), target)
    if "error" in result:
        print(result["error"])
        sys.exit(1)
    chapters, ok = result["chapters"], result["valid"]
    if as_json:
        # Keep the standalone command's existing field names as a presentation adapter.
        rows = [
            {"start": c["start"], "label": c["timestamp"], "draft_title": c["title"], "seconds": c["seconds"]}
            for c in chapters
        ]
        print(json.dumps({"valid": ok, "duration": result["duration"], "chapters": rows}, indent=1))
        return
    print()
    for c in chapters:
        print(f"  {c['timestamp']} {c['title']}")
    print(
        f"\n  {len(chapters)} chapters"
        f"{'' if ok else '  -- INVALID: YouTube needs 3+, a 00:00 first entry and 10s minimum each'}"
    )
    print("  Retitle every line before pasting. These are the topic words, not your words.\n")


if __name__ == "__main__":
    main()
