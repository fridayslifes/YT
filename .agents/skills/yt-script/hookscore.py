#!/usr/bin/env python3
"""hookscore.py - score a YouTube hook before you waste a take on it.

Five properties, 0-100 each. The verdict is 60% the mean and 40% the mean of the two weakest, and
any property below 30 caps the verdict at LEAK_CEILING: a hook with one dead property must not be
able to print STRONG no matter how good the other four are. That ceiling replaced a plain
0.6*mean + 0.4*min, which made one detector misfire a hard cap on every hook - see CALIBRATION.

    python3 hookscore.py hooks.txt            # one hook per line, ranked
    python3 hookscore.py --hook "one line"    # score a single hook
    python3 hookscore.py --calibrate          # re-measure the calibration claim, exits 1 if broken
    python3 hookscore.py --json hooks.txt     # machine-readable

CALIBRATION, and what is NOT claimed. The detectors are keyword and pattern based, so they read
rhetoric imperfectly. --calibrate measures them: every worked example in hooks.json must outscore
every dead hook in hook_controls.txt, and WORKABLE_MIN sits above the control ceiling. That is the
whole basis - internal consistency, no external benchmark, no view-data correlation. This ranks
your hook options against each other. It cannot predict retention or CTR, so treat a low score as
a reason to look again and a high score as nothing at all.
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_formulas(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["hooks"]


FORMULAS = _load_formulas(os.path.join(HERE, "hooks.json"))

FILLER = {
    "basically", "actually", "literally", "just", "really", "very", "so", "kind", "sort", "like",
    "guys", "hey", "welcome", "today", "video", "subscribe", "channel"
}
VAGUE = {
    "amazing", "incredible", "insane", "crazy", "huge", "massive", "game", "changer", "secret",
    "powerful", "ultimate", "best", "revolutionary", "mind", "blowing", "unbelievable"
}
CONCRETE = re.compile(
    r"\b(\d[\d,.]*\s?(%|k|m|x|s|m|h)?|\$\d|\d+\s?(second|minute|hour|day|week|month|year)s?|"
    r"(one|two|three|four|five|six|seven|eight|nine|ten|twelve|fifteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion)"
    r"([\s-](one|two|three|four|five|six|seven|eight|nine|percent|dollars|seconds|minutes|hours|days|weeks|months|years|times))?)\b",
    re.I,
)
YOU = re.compile(r"\b(you|your|you're|youre|yourself)\b", re.I)
STAKE = re.compile(
    r"\b(lose|losing|lost|wasting|waste|quit|fail|failed|failing|broke|cost|costs|risk|before|stop|never|die|dying|dead|"
    r"trap|trapped|hijack|hijacks|destroy|destroying|ruin|ruining|paralyze|paralyzes|freeze|freezes|fake|simulation|blind|mistake|lie|lies|steal|stealing|"
    r"robbed|crime|arrested|entire\s+week|exhausted|forget|forgetting|walk\s+past)\b",
    re.I,
)
WH = re.compile(r"\b(why|how|what|which|who|when)\b", re.I)
CONTRAST = re.compile(
    r"\b(but|nobody|almost|except|yet|despite|secretly|suddenly|instead|however|"
    r"until|before|never|only|actually)\b",
    re.I,
)
# A pointer the viewer cannot resolve from the sentence alone: "this one setting", "the other 3%",
# "one search term". Declaring a gap without asking a question is how the evidence-based formulas
# (The Receipt, The Reveal, The Stack, Before and After) open a loop, and the old detector was blind
# to all of them.
WITHHELD = re.compile(
    r"\b(?:this|these|that|one|two|three|four|five|six|seven|eight|nine|ten|\d+|few|several|the|"
    r"another|both|most)\b[^.?!,]{0,34}\b"
    r"(setting|settings|reason|thing|things|way|ways|prompt|method|trick|habit|rule|rules|step|steps|"
    r"idea|problem|fix|change|changes|file|result|results|difference|answer|explanation|mistake|"
    r"mistakes|numbers?|choice|question|glitch|trap|study|finding|pattern|list|name|word|words)\b",
    re.I,
)
GAP_PHRASE = re.compile(
    r"\b(here'?s|here is|that is (why|what)|what (the other|you|most people)|"
    r"the (real|actual|true) (reason|answer|problem|fix)|do differently|did instead)\b",
    re.I,
)
# The other two ways a declarative hook opens a loop: an act that has no explanation yet
# ("I did not touch the upload button"), and a stated change with the mechanism withheld
# ("This was my thumbnail. This is my thumbnail now.").
UNEXPLAINED = re.compile(
    r"\b(did(?: n'?t| not)|doesn'?t|don'?t|never|stopped|refused|skipped|ignored|walked past|"
    r"without)\b[^.?]{0,40}\b(touch|open|answer|reply|say|help|upload|click|fix|work|matter|use)\w*\b",
    re.I,
)
TRANSFORM = re.compile(
    r"\b(was|were|used to)\b[^!?]{0,44}\b(now|today|anymore|instead)\b|"
    r"\b(no longer|not any more|stops mattering|went from|changed (my|your|the))\b",
    re.I,
)
# A claim that contradicts what everyone else says opens a loop by itself: the viewer has to know
# why the consensus is wrong. Contrarian Flip is this device and nothing else.
CONSENSUS = re.compile(
    r"\b(everyone says|everybody says|they say|they'?ll tell you|conventional wisdom|"
    r"gurus? (say|swear|insist)|the advice is|you'?ve been told|we'?re told)\b",
    re.I,
)
GAIN = re.compile(
    r"\b(get|gets|getting|you'?ll get|have|will have|you'?ll have|build|builds|make|makes|"
    r"save|saves|fix|finally|recover|improve|grows|grew|turn.{0,12}into|unlock)\b",
    re.I,
)
MOVED = re.compile(
    r"\b(went|jumped|drops?\b|dropped|fell|climbed|doubled|tripled|cut|slashed|grew|crashed|rose)\b[^.]{0,20}\b(to|from|by|up|down)\b",
    re.I,
)
DOMAIN = re.compile(
    r"\b(views?|subscribers?|subscriber count|channel|revenue|money|paycheck|clients?|"
    r"hours?|minutes?|evening|morning|week|weekend|sleep|focus|memory|attention|videos?|"
    r"work|job|business|brain)\b",
    re.I,
)
PROXY = re.compile(
    r"^\s*(i|i'?m|we|this|these|that|every|everyone|everybody|most|nobody|almost|no one)\b",
    re.I,
)
SELF_IDENTIFY = re.compile(
    r"\b(everyone|everybody|most (people|creators|of us|who)|people who|anyone who|the average|"
    r"you'?re not|if you)\b",
    re.I,
)
# retrospective advice ("seven things I would do differently") addresses the viewer as the
# person who is about to make the same choices.
ADVICE = re.compile(r"\b(would (do|say|pick|fix|avoid|start|change|handle)|if i (started|were you|had)|shouldn'?t|you should)\b", re.I)
ANNOUNCE = re.compile(
    r"\b(i'?m going to|i am going to|we'?ll (look|talk|cover|discuss)|share (some|my) thoughts|"
    r"in this video|this is a video|today (we|i)|welcome back|let'?s talk about)\b",
    re.I,
)


def _empty_announce(t: str) -> bool:
    """A pure format announcement, which is what hooks.json rule 5 forbids opening with.

    "I let an AI run my channel for 30 days" and "I am going to share some thoughts" are both
    first person, but only the first is a demonstration the viewer has to see the end of. Once the
    sentence names an artifact or a number it stops being empty, so the exemption is on purpose.
    """
    return bool(ANNOUNCE.search(t) and not WITHHELD.search(t) and not CONCRETE.search(t))


def _clean_hook(t: str) -> str:
    return t.replace("*", "").replace("—", " ").replace("–", " ")


def words(t: str) -> list[str]:
    return re.findall(r"[a-z0-9'%$.]+", _clean_hook(t).lower())


def specificity(t: str) -> int:
    w = words(t)
    if not w:
        return 0
    nums = len(CONCRETE.findall(t))
    vague = sum(1 for x in w if x in VAGUE)
    filler = sum(1 for x in w if x in FILLER)
    s = 34 + nums * 22 - vague * 16 - filler * 5
    # proper nouns that are not sentence-initial read as named things
    s += min(18, 6 * sum(1 for x in t.split()[1:] if x[:1].isupper()))
    return max(0, min(100, s))


def _clamp(n: float) -> int:
    return max(0, min(100, round(n)))


def address(t: str) -> int:
    n = len(YOU.findall(t))
    first = 30 if YOU.search(" ".join(t.split()[:6])) else 0
    if n:
        return _clamp(26 + n * 20 + first)
    # No "you" is not the same as no address. A first-person demonstration ("I let an AI run my
    # channel") or a generalisation ("everyone says post daily") makes the viewer self-identify
    # instead of being named, and both are legitimate formulas in hooks.json. The old detector
    # scored them at the bare floor, which is why the library's own examples could not clear it.
    proxy = 34 if (SELF_IDENTIFY.search(t) or ADVICE.search(t)) else 0
    if PROXY.match(t.strip()) or re.match(r"^(why\s+does\s+a|in\s+(nineteen|twenty|\d{4}))\b", t.strip(), re.I):
        proxy = max(proxy, 28)
    if _empty_announce(t):
        proxy = 0
    return _clamp(26 + proxy)


def stakes(t: str) -> int:
    loss = len(STAKE.findall(t))
    gain = len(GAIN.findall(t))
    domain = 10 if DOMAIN.search(t) else 0
    # a stated move in the viewer's own metrics is a stake whether it is up or down
    moved = 12 if (MOVED.search(t) and domain) else 0
    return _clamp(20 + loss * 26 + gain * 10 + domain + moved + (14 if CONCRETE.search(t) else 0))


def curiosity(t: str) -> int:
    s = 22
    if WH.search(t):
        s += 22
    if CONTRAST.search(t):
        s += 12
    if WITHHELD.search(t):
        s += 24
    if GAP_PHRASE.search(t):
        s += 14
    if UNEXPLAINED.search(t) or TRANSFORM.search(t) or CONSENSUS.search(t):
        s += 20
    if t.strip().endswith(("?", "...")):
        s += 12
    # a hook that answers its own question has closed the loop it just opened
    if re.search(r"\b(because|so that|which means|since|which is why)\b", t, re.I):
        s -= 30
    if _empty_announce(t):
        s -= 22
    return _clamp(s)


def brevity(t: str) -> int:
    n = len(words(t))
    if n == 0:
        return 0
    # 9-24 words is the band a spoken hook lands in at ~150wpm inside 10 seconds
    if 9 <= n <= 24:
        return 100
    if n < 9:
        return max(30, 100 - (9 - n) * 11)
    return max(10, 100 - (n - 24) * 7)


PROPS = [
    ("SPECIFICITY", specificity),
    ("ADDRESS", address),
    ("STAKES", stakes),
    ("CURIOSITY", curiosity),
    ("BREVITY", brevity),
]


def classify(t: str) -> tuple[str, int]:
    best, hits = None, 0
    for f in FORMULAS:
        n = sum(1 for p in f["match"] if re.search(p, t, re.I))
        if n > hits:
            best, hits = f, n
    return (best["name"] if best else "Unclassified"), hits


# One pass mark for the whole repo. tools/orchestrator/verifiers.py, tools/output_format.py,
# tools/creative_engine.py and GEMINI.md section 6 all quote hook verdicts; they must import these
# instead of carrying their own literals (they previously disagreed: gate 70, band STRONG 72).
STRONG_MIN = 70
# WORKABLE_MIN is not round. It sits above the highest verdict hook_controls.txt earns and below
# the lowest verdict a worked example in hooks.json earns, so the WEAK band means "worse than the
# worst opener this channel actually ships". Run --calibrate to re-derive both ends from the files.
WORKABLE_MIN = 48
# A property this low is a leak, not a trade-off, and no average can average it away.
LEAK_FLOOR = 30
LEAK_CEILING = 69


def score(t: str) -> tuple[dict[str, int], int, str, int]:
    clean_t = _clean_hook(t)
    parts = {n: fn(clean_t) for n, fn in PROPS}
    vals = sorted(parts.values())
    verdict = round(0.6 * (sum(vals) / len(vals)) + 0.4 * (sum(vals[:2]) / 2))
    if vals[0] < LEAK_FLOOR:
        verdict = min(verdict, LEAK_CEILING)
    name, hits = classify(clean_t)
    return parts, verdict, name, hits


def band(v: int) -> str:
    return "STRONG" if v >= STRONG_MIN else "WORKABLE" if v >= WORKABLE_MIN else "WEAK"


def _read_lines(path: str) -> list[str]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]


def calibrate() -> dict:
    """Re-derive the calibration claim from the two shipped reference files.

    Every number this returns is measured from hooks.json and hook_controls.txt on the current
    detectors, so an edit that quietly breaks the gate shows up here instead of living in a
    docstring as a claim nobody can check.
    """
    examples = [(f["name"], f["example"]) for f in FORMULAS if f.get("example")]
    controls = _read_lines(os.path.join(HERE, "hook_controls.txt"))
    scored = sorted(((score(t)[1], n) for n, t in examples), reverse=True)
    ev = [v for v, _ in scored]
    cv = sorted((score(t)[1] for t in controls), reverse=True)
    if not ev or not cv:
        return {"error": "missing hooks.json examples or hook_controls.txt"}
    pairs = [(e, c) for e in ev for c in cv]
    return {
        "examples": len(ev), "controls": len(cv),
        "example_mean": round(sum(ev) / len(ev), 1), "example_min": ev[-1], "example_max": ev[0],
        "control_mean": round(sum(cv) / len(cv), 1), "control_max": cv[0],
        "separation_pct": round(100 * sum(1 for e, c in pairs if e > c) / len(pairs), 1),
        "median_margin": round(ev[len(ev) // 2] - cv[len(cv) // 2], 1),
        "examples_flagged_weak": [n for v, n in scored if v < WORKABLE_MIN],
        "controls_reaching_workable": [t for t in controls if score(t)[1] >= WORKABLE_MIN],
        "strong_examples": sum(1 for v in ev if v >= STRONG_MIN),
        # the band floor has to sit above every dead control; if it does not, WEAK stops meaning
        # "worse than the worst shipped opener" and the calibration claim is void.
        "floor_above_controls": cv[0] < WORKABLE_MIN,
    }


def report(t: str, parts: dict[str, int], verdict: int, name: str, hits: int) -> None:
    print(f"\n  {t.strip()}")
    print(f"  {'-' * min(72, max(20, len(t.strip())))}")
    for k, v in parts.items():
        print(f"    {k:<12} {v:3d}  {'#' * (v // 5)}")
    print(f"    {'VERDICT':<12} {verdict:3d}  {band(verdict)}")
    print(f"    formula      {name}" + (f"  ({hits} pattern{'s' if hits != 1 else ''} matched)" if hits else "  (no formula matched - that is usually a summary, not a hook)"))
    low = min(parts, key=parts.get)
    print(f"    weakest      {low} - {FIX[low]}")


FIX = {
    "SPECIFICITY": "swap one adjective for a number, a name or a date",
    "ADDRESS": "say 'you' in the first six words, or make it a generalisation the viewer cannot not take personally",
    "STAKES": "name what it costs them to keep doing it the current way",
    "CURIOSITY": "cut the half of the sentence that answers itself, or point at one thing you have not named yet",
    "BREVITY": "9 to 24 words. Read it out loud and stop where you run out of breath",
}


def main() -> None:
    a = sys.argv[1:]
    as_json = "--json" in a
    a = [x for x in a if x != "--json"]
    if "--calibrate" in a:
        c = calibrate()
        print(json.dumps(c, indent=1) if as_json else _calibration_text(c))
        sys.exit(0 if c.get("floor_above_controls") and not c.get("controls_reaching_workable")
                 and c.get("separation_pct", 0) >= 95 else 1)
    if "--hook" in a:
        if a.index("--hook") + 1 >= len(a):
            print("error: --hook needs the hook in quotes after it", file=sys.stderr)
            sys.exit(1)
        lines = [a[a.index("--hook") + 1]]
    elif a and os.path.exists(a[0]):
        with open(a[0], encoding="utf-8") as fh:
            lines = [line for line in fh.read().splitlines() if line.strip()]
    else:
        if a:
            print(f"error: no such file: {a[0]}", file=sys.stderr)
        else:
            print(__doc__)
        sys.exit(1)
    out = []
    for t in lines:
        parts, verdict, name, hits = score(t)
        out.append({
            "hook": t.strip(),
            "properties": parts,
            "verdict": verdict,
            "band": band(verdict),
            "formula": name,
            "matched": hits,
        })
    out.sort(key=lambda r: -r["verdict"])
    if as_json:
        print(json.dumps([{k: v for k, v in r.items() if k != "matched"} for r in out], indent=1))
        return
    for r in out:
        report(r["hook"], r["properties"], r["verdict"], r["formula"], r["matched"])
    if len(out) > 1:
        print(f"\n  winner: {out[0]['hook'].strip()}  ({out[0]['verdict']}, {out[0]['band']})\n")


def _calibration_text(c: dict) -> str:
    if "error" in c:
        return f"  calibration unavailable: {c['error']}"
    weak = ", ".join(c["examples_flagged_weak"]) or "none"
    bad = ", ".join(c["controls_reaching_workable"]) or "none"
    lines = [
        "",
        "  HOOKSCORE CALIBRATION - measured on the current detectors, not asserted",
        "  " + "-" * 66,
        f"    reference set      {c['examples']} worked examples from hooks.json",
        f"    controls           {c['controls']} dead hooks from hook_controls.txt",
        f"    examples           mean {c['example_mean']}  range {c['example_min']}-{c['example_max']}",
        f"    controls           mean {c['control_mean']}  ceiling {c['control_max']}",
        f"    pair separation    {c['separation_pct']}% of example/control pairs ordered correctly",
        f"    median margin      {c['median_margin']:+.1f}",
        f"    bands              WEAK < {WORKABLE_MIN}  WORKABLE < {STRONG_MIN}  STRONG +",
        f"    STRONG examples    {c['strong_examples']} of {c['examples']}",
        f"    flagged weak       {weak}",
        f"    controls in band   {bad}",
        "",
        "    A control reaching WORKABLE, or separation below 95%, means the detectors were edited",
        "    into breaking the gate. That is a fail, not a threshold to move.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
