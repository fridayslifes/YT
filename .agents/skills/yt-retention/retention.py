#!/usr/bin/env python3
"""retention.py - read a YouTube Studio audience-retention export and find the leaks.

    python3 retention.py retention.csv
    python3 retention.py retention.csv --transcript transcript.srt   # names what was said at each drop
    python3 retention.py retention.csv --json

Get the file from Studio: Analytics -> a video -> Engagement -> the audience-retention chart ->
the download icon -> "Audience retention". Two columns, a position (percent or seconds) and a
percentage still watching.

It reports three things, because they are three different problems with three different fixes:
  HOOK LEAK    what you lost in the first 30 seconds
  CLIFFS       single steep drops - a specific moment people left at
  SLIDE        the steady bleed rate across the flat middle

With --transcript it prints what you were saying at each cliff, which is the only version of this
report you can act on without scrubbing the video yourself.
"""
from __future__ import annotations

import csv
import json
import os
import sys


def load_csv(path: str) -> list[tuple[float, float]]:
    rows = []
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as fh:
        for r in csv.reader(fh):
            nums = []
            for c in r:
                c = c.strip().replace("%", "").replace(",", "")
                try:
                    nums.append(float(c))
                except ValueError:
                    nums.append(None)
            vals = [n for n in nums if n is not None]
            if len(vals) >= 2:
                rows.append((vals[0], vals[1]))
    return rows


HOOK_WINDOW_S = 30.0


def hook_cutoff(xs: list[float], duration: float | None = None) -> tuple[float, float, bool]:
    """Resolve (video length in seconds, hook cutoff in x-axis units, percent-axis?).

    The headline metric is "percent lost in the first 30 seconds", so the 30-second window has to be
    placed on whatever axis this CSV actually uses. A seconds axis gives the length away (max(x));
    a percent axis does not, and guessing one (an invented 10% of the video) would print a
    seconds-labelled number that never measured 30 seconds of anything. So a percent axis without a
    real duration is an error, not a default.
    """
    axis_max = max(xs)
    pct_axis = axis_max <= 100.5
    if not pct_axis:
        return (float(duration) if duration else axis_max), HOOK_WINDOW_S, False
    if not duration:
        raise ValueError(
            "this CSV's x-axis is percent-of-video, so the opening window cannot be labelled in "
            f"seconds without the video length - pass --duration <seconds> "
            f"(or use the seconds-axis Studio export) to measure the first {int(HOOK_WINDOW_S)}s"
        )
    duration = float(duration)
    return duration, min(HOOK_WINDOW_S / duration * 100, 100.0), True


def main() -> None:
    a = sys.argv[1:]
    as_json = "--json" in a
    a = [x for x in a if x != "--json"]
    tr = a[a.index("--transcript") + 1] if "--transcript" in a else None
    files = [x for x in a if not x.startswith("--") and x != tr]
    if not files or not os.path.exists(files[0]):
        print(__doc__)
        sys.exit(1)
    rows = load_csv(files[0])
    if len(rows) < 8:
        print("could not read at least 8 data points from that csv")
        sys.exit(1)
    xs = [r[0] for r in rows]
    ys = [r[1] for r in rows]
    dur_arg = float(a[a.index("--duration") + 1]) if "--duration" in a else None

    try:
        dur, cutoff, pct_axis = hook_cutoff(xs, dur_arg)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)

    def at(x: float) -> float:
        return (x / 100.0 * dur) if pct_axis else x

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
    if tr and os.path.exists(tr):
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        from deadair import load as load_cues
        cues = load_cues(tr)
        for c in cliffs:
            t = c["at_seconds"]
            near = [q[2] for q in cues if q[0] <= t + 4 and q[1] >= t - 4]
            said[str(c["from"])] = " ".join(near)[:140]
    window_s = min(HOOK_WINDOW_S, dur)
    out = {
        "points": len(rows),
        "duration_s": round(dur, 1),
        "hook_window_s": round(window_s, 1),
        "start": start,
        "hook_leak": round(hook_leak, 2),
        "end": ys[-1],
        "cliffs": cliffs,
        "slide_per_unit": round(slide, 3),
        "said": said,
    }
    if as_json:
        print(json.dumps(out, indent=1))
        return
    print(f"\n  {files[0]}   {len(rows)} points   {ys[0]:.1f}% -> {ys[-1]:.1f}%   video ~{dur:.0f}s\n")
    verdict = "healthy" if hook_leak < 25 else "leaking" if hook_leak < 40 else "severe"
    print(f"  HOOK LEAK   {hook_leak:.1f}% lost in the opening {window_s:.0f} seconds   [{verdict}]")
    print("              under 25 is healthy for this length. Fix the first line before anything else.\n")
    print("  CLIFFS      the moments people actually left")
    for c in cliffs:
        print(f"    -{c['lost']:5.1f}%  at {c['at_seconds']:>7.0f}s" + (f"   \"{said.get(str(c['from']),'')}\"" if said else ""))
    if not cliffs:
        print("    none steeper than 0.8% - the loss is all slide, not moments")
    print(f"\n  SLIDE       {slide:.3f}% per {'percent of the video' if pct_axis else 'second'} across the middle")
    print("              a flat slide is pacing, not content. Cut the middle, do not rewrite it.\n")


if __name__ == "__main__":
    main()
