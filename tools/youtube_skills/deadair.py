#!/usr/bin/env python3
"""deadair.py - an edit decision list from a timestamped transcript.

    python3 deadair.py transcript.srt            # or .vtt, or whisper .json
    python3 deadair.py transcript.srt --floor 0.35 --json

Finds three things and prints the cuts in transcript order:
  DEAD    gaps between spoken cues longer than the floor
  FILLER  cues that are only filler ("um", "so yeah", "basically")
  REPEAT  a sentence restarted - the second take of the same opening

WHAT IT DOES NOT DO. It does not cut the file. It prints an EDL, the total it would remove, and the
runtime you would land on, and you apply it in whatever editor you use. Nothing here touches media.
Filler attached to a meaningful sentence is retained: cue timestamps cannot locate individual words.
"""
from __future__ import annotations

import json
import math
import os
import re
import sys

FILLER_ONLY = re.compile(
    r"^[\s,.-]*((um+|uh+|er+|ah+|so|okay|ok|right|yeah|like|anyway|basically|"
    r"actually|you know|i mean|let me see|hold on)[\s,.-]*)+$",
    re.I,
)


def parse_ts(s: str) -> float:
    s = s.strip().replace(",", ".")
    p = s.split(":")
    if len(p) == 3:
        return int(p[0]) * 3600 + int(p[1]) * 60 + float(p[2])
    if len(p) == 2:
        return int(p[0]) * 60 + float(p[1])
    raise ValueError(f"Invalid transcript timestamp: {s!r}")


def validate_timestamps(cues: list[tuple[float, float, str]]) -> None:
    """Reject invalid intervals before timing arithmetic or integer conversion."""
    for number, (start, end, _) in enumerate(cues, 1):
        try:
            valid = math.isfinite(start) and math.isfinite(end) and 0 <= start < end
        except (TypeError, ValueError, OverflowError):
            valid = False
        if not valid:
            raise ValueError(f"Transcript cue {number} timestamps must be finite with 0 <= start < end")


def load(path: str) -> list[tuple[float, float, str]]:
    with open(path, encoding="utf-8", errors="replace") as fh:
        raw = fh.read()
    if path.endswith(".json"):
        d = json.loads(raw)
        segs = d if isinstance(d, list) else d.get("segments", []) if isinstance(d, dict) else None
        if not isinstance(segs, list):
            raise ValueError("Transcript JSON must contain a segment list")
        cues = []
        for number, segment in enumerate(segs, 1):
            if not isinstance(segment, dict):
                raise ValueError(f"Transcript segment {number} must be an object")
            text = segment.get("text")
            if text is not None and not isinstance(text, str):
                raise ValueError(f"Transcript segment {number} text must be a string")
            try:
                start, end = float(segment["start"]), float(segment["end"])
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"Transcript segment {number} timestamps must be finite numbers") from exc
            cues.append((start, end, (text or "").strip()))
        validate_timestamps(cues)
        return cues
    cues: list[list] = []
    cur = None
    for line in raw.splitlines():
        m = re.match(r"\s*(\d[\d:.,]+)\s*-->\s*(\d[\d:.,]+)", line)
        if m:
            cur = [parse_ts(m.group(1)), parse_ts(m.group(2)), []]
            cues.append(cur)
        elif not line.strip():
            cur = None
        elif cur is not None:
            cur[2].append(line.strip())
    result = [(a, b, " ".join(t)) for a, b, t in cues if t]
    validate_timestamps(result)
    return result


def norm(t: str) -> list[str]:
    return re.sub(r"[^a-z ]", "", t.lower()).split()


def analyze_cues(cues: list[tuple[float, float, str]], floor: float = 0.45) -> dict:
    """Build one EDL from cue timings; do not infer word timings or change media."""
    if not cues:
        return {"error": "No cues found in transcript"}
    try:
        validate_timestamps(cues)
    except ValueError as exc:
        return {"error": str(exc)}
    dur = max(end for _, end, _ in cues)
    cuts = []
    speech_end = 0.0
    for i, (s, e, t) in enumerate(cues):
        if FILLER_ONLY.match(t):
            cuts.append({"kind": "FILLER", "start": s, "end": e, "why": t.strip()[:48]})
        if i:
            gap = s - speech_end
            if gap > floor:
                keep = floor / 2
                cuts.append({
                    "kind": "DEAD",
                    "start": round(speech_end + keep, 3),
                    "end": round(s - keep, 3),
                    "why": f"{gap:.2f}s gap",
                })
        speech_end = max(speech_end, e)
        if t.strip() and not FILLER_ONLY.match(t):
            j = i - 1
            while j >= 0 and (FILLER_ONLY.match(cues[j][2]) or not cues[j][2].strip()):
                j -= 1
            if j >= 0:
                a1, b1 = norm(cues[j][2])[:5], norm(t)[:5]
                if len(a1) >= 3 and a1 == b1[:len(a1)]:
                    cuts.append({
                        "kind": "REPEAT",
                        "start": cues[j][0],
                        "end": cues[j][1],
                        "why": f'restart of "{" ".join(a1)}"',
                    })
    cuts = [c for c in cuts if c["end"] > c["start"]]
    cuts.sort(key=lambda c: c["start"])
    # Keep the individual reasons, but count overlapping proposed intervals only once.
    removed = 0.0
    covered_until = 0.0
    for cut in cuts:
        removed += max(0.0, cut["end"] - max(cut["start"], covered_until))
        covered_until = max(covered_until, cut["end"])
    return {
        "duration": dur,
        "cuts": cuts,
        "removed": round(removed, 3),
        "out": round(dur - removed, 3),
    }


def main() -> None:
    a = sys.argv[1:]
    as_json = "--json" in a
    a = [x for x in a if x != "--json"]
    floor = float(a[a.index("--floor") + 1]) if "--floor" in a else 0.45
    a = [x for x in a if not x.startswith("--") and not re.match(r"^[\d.]+$", x)]
    if not a or not os.path.exists(a[0]):
        print(__doc__)
        sys.exit(1)
    cues = load(a[0])
    result = analyze_cues(cues, floor)
    if "error" in result:
        print(result["error"])
        sys.exit(1)
    dur, cuts, removed = result["duration"], result["cuts"], result["removed"]
    if as_json:
        print(json.dumps({"source": a[0], **result}, indent=1))
        return
    print(f"\n  {a[0]}   {dur:.2f}s in, {len(cues)} cues, dead-air floor {floor}s\n")
    for c in cuts:
        print(f"    {c['kind']:<7} {c['start']:8.2f} -> {c['end']:8.2f}   {c['end']-c['start']:5.2f}s   {c['why']}")
    print(
        f"\n  {len(cuts)} cuts, {removed:.2f}s removed, {dur - removed:.2f}s out "
        f"({removed / dur * 100 if dur else 0:.1f}% shorter)\n"
    )


if __name__ == "__main__":
    main()
