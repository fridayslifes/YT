#!/usr/bin/env python3
"""title.py - lint a YouTube title before you publish it.

    python3 title.py --title "..."
    python3 title.py titles.txt            # one per line, ranked
    python3 title.py --title "..." --json

Length: YouTube truncates around 60 characters on desktop search and around 40 on a mobile home
feed. Both limits are reported because they are different failures - a desktop truncation loses the
tail, a mobile one can lose the subject.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.output_format import VOICE_BLACKLIST  # noqa: E402

DESKTOP, MOBILE, HARD = 60, 40, 100
VAGUE = {
    "amazing", "incredible", "huge", "massive", "ultimate", "best", "powerful",
    "secret", "mindblowing", "epic", "perfect", "complete", "everything"
}
STOP = {
    "the", "a", "an", "of", "for", "to", "in", "on", "and", "or", "is", "are", "with", "your", "you",
    "my", "i", "this", "that", "it", "how", "what", "why"
}


def words(t: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", t.lower())


def check(title: str) -> dict:
    t = title.strip()
    n = len(t)
    issues, good = [], []
    if n > HARD:
        issues.append(("length", f"{n} characters - YouTube's hard limit is {HARD}"))
    elif n > DESKTOP:
        issues.append(("length", f"{n} characters - desktop search cuts near {DESKTOP}"))
    else:
        good.append(f"{n} characters, inside the {DESKTOP}-character desktop cut")
    if n > MOBILE:
        head = t[:MOBILE].rsplit(" ", 1)[0]
        issues.append(("mobile", f'a mobile feed shows about "{head}..." - check the subject survives'))
    caps = [w for w in t.split() if len(w) > 2 and w.isupper()]
    if len(caps) > 2:
        issues.append(("shouting", f"{len(caps)} all-caps words - two is the ceiling before it reads as spam"))
    elif caps:
        good.append(f"{len(caps)} all-caps word for emphasis")
    v = [w for w in words(t) if w in VAGUE]
    v.extend(word for word in VOICE_BLACKLIST if re.search(r"\b" + re.escape(word) + r"\b", t, re.IGNORECASE))
    if v:
        issues.append(("vague", f"{', '.join(sorted(set(v)))} - swap for a number, a name or a date"))
    if any(tag != "#shorts" for tag in re.findall(r"(?<!\w)#shorts\b", t, re.IGNORECASE)):
        issues.append(("shorts-case", "use #shorts in lowercase"))
    nums = re.findall(r"\d[\d,.]*%?", t)
    if nums:
        good.append(f"carries a concrete figure ({', '.join(nums[:3])})")
    else:
        issues.append(("no-number", "no number, date or name - the most reliable single fix"))
    if t.endswith("?"):
        good.append("open question in the title")
    front = [w for w in words(t)[:3] if w not in STOP]
    if not front:
        issues.append(("front-load", "the first three words are all filler - move the subject forward"))
    score = max(0, min(100, 100 - 14 * len(issues) + 4 * len(good)))
    return {"title": t, "chars": n, "score": score, "issues": issues, "good": good}


def show(r: dict) -> None:
    print(f'\n  "{r["title"]}"')
    print(f"  {r['chars']} chars   score {r['score']}/100")
    for k, m in r["issues"]:
        print(f"    x  {k:<12} {m}")
    for m in r["good"]:
        print(f"    ok              {m}")


def main() -> None:
    a = sys.argv[1:]
    as_json = "--json" in a
    a = [x for x in a if x != "--json"]
    if "--title" in a:
        rows = [check(a[a.index("--title") + 1])]
    elif a and os.path.exists(a[0]):
        with open(a[0], encoding="utf-8") as fh:
            rows = [check(line) for line in fh.read().splitlines() if line.strip()]
    else:
        if a:
            print(f"error: no such file: {a[0]}", file=sys.stderr)
        print(__doc__)
        sys.exit(1)
    rows.sort(key=lambda r: -r["score"])
    if as_json:
        print(json.dumps(rows, indent=1))
        return
    for r in rows:
        show(r)
    print()


if __name__ == "__main__":
    main()
