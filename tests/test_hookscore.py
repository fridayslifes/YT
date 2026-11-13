"""tests/test_hookscore.py - tools/youtube_skills/hookscore.py + youtube_skills.score_hook.

Contract under test (GEMINI.md section 6 + the module docstring): five properties scored 0-100;
the verdict is 60% the mean of all five plus 40% the mean of the two weakest; any property under
LEAK_FLOOR caps the verdict at LEAK_CEILING so one dead detector can never print STRONG; bands come
from the shared STRONG_MIN / WORKABLE_MIN constants; and classification runs against the 21
formulas in tools/youtube_skills/hooks.json.

The worked-example tests assert that all 21 hooks.json examples score at least WORKABLE; changes
that make an example WEAK fail the suite.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from conftest import report
from tools.youtube_skills import hookscore
from tools.youtube_skills import score_hook

HOOKS_JSON = Path(hookscore.HERE) / "hooks.json"

# The canonical GEMINI.md section 6 example hook, plus a shipped-style variant.
HOOK_STRONG = "If you collapse on a busy sidewalk, why do 85% of people walk past you?"
HOOK_SHIPPED = "If you collapse on a Manhattan sidewalk, why do eighty-five percent of strangers stop and watch you die?"
HOOK_VAGUE = (
    "Today we are going to talk about a really amazing and incredible habit "
    "that will change your life forever guys."
)
PROPERTY_NAMES = ["SPECIFICITY", "ADDRESS", "STAKES", "CURIOSITY", "BREVITY"]


def weakest_link(vals: list[int]) -> int:
    """The documented verdict, reimplemented independently of score()."""
    ordered = sorted(vals)
    verdict = round(0.6 * (sum(ordered) / len(ordered)) + 0.4 * (sum(ordered[:2]) / 2))
    if ordered[0] < hookscore.LEAK_FLOOR:
        verdict = min(verdict, hookscore.LEAK_CEILING)
    return verdict


# --------------------------------------------------------------------------- #
# the five properties
# --------------------------------------------------------------------------- #
def test_score_returns_exactly_the_five_documented_properties():
    parts, verdict, formula, hits = hookscore.score(HOOK_STRONG)
    assert list(parts) == PROPERTY_NAMES
    assert isinstance(verdict, int)
    assert isinstance(formula, str) and formula
    assert isinstance(hits, int)


@pytest.mark.parametrize("hook", [HOOK_STRONG, HOOK_SHIPPED, HOOK_VAGUE, "", "word", "a" * 400])
def test_every_property_stays_in_the_0_100_band_for_any_input(hook):
    parts, verdict, _, _ = hookscore.score(hook)
    for name, value in parts.items():
        assert 0 <= value <= 100, f"{name} out of band for {hook!r}: {value}"
        assert isinstance(value, int)
    assert 0 <= verdict <= 100


def test_specificity_rewards_a_number_and_penalises_vague_and_filler_words():
    plain = hookscore.specificity("Why do people walk past you on a busy sidewalk?")
    with_number = hookscore.specificity("Why do 85% of people walk past you on a sidewalk?")
    assert with_number > plain, "a concrete figure must beat the same sentence without one"
    vague = hookscore.specificity("Why do amazing incredibly crazy people walk past you?")
    assert vague < plain, "vague adjectives must drag Specificity down"
    filler = hookscore.specificity("So basically really just people walk past you today?")
    assert filler < plain, "filler words must drag Specificity down"
    assert hookscore.specificity("") == 0


def test_address_is_awarded_for_second_person_inside_the_first_six_words():
    front = hookscore.address("You collapse on a sidewalk and nobody helps you today")
    late = hookscore.address("A crowd of strangers watches a man fall over, and you feel sick")
    assert front >= 90
    assert late < front, "the 'you' bonus is about position, not just presence"
    assert hookscore.address("He watches the man collapse and says nothing at all today") == 26


def test_a_first_person_or_generalised_opening_is_not_scored_as_no_address():
    # hooks.json ships "I Tried It" and "Contrarian Flip" openings; naming the viewer is not the
    # only way to make someone self-identify, and the floor of 26 used to fail the library's own
    # examples.
    assert hookscore.address("I let an AI run my channel for 30 days and nothing changed at all") > 26
    assert hookscore.address("Everyone says post daily. I posted once a week for a year instead") > 26
    assert hookscore.address("Why does a channel with 50 videos still earn nothing?") > 26


def test_stakes_counts_cost_language_and_recognises_a_gain_frame():
    with_loss = hookscore.stakes("You lose two hours every evening to your phone and never get them back.")
    neutral = hookscore.stakes("Here is a method for planning your evening a little bit better.")
    assert with_loss > neutral
    assert hookscore.stakes("This is the fastest way to turn one long video into thirty Shorts.") > neutral


def test_curiosity_opens_a_loop_and_is_penalised_for_closing_it():
    open_q = hookscore.curiosity("Why do 85% of bystanders walk past you?")
    closed = hookscore.curiosity("Why do 85% of bystanders walk past you, because they think someone else will help?")
    assert open_q > closed, "a hook that answers itself leaves no gap to click into"
    assert hookscore.curiosity("People walk past you on the street.") < open_q
    # a withheld reference is a gap even without a question mark (The Receipt / The Reveal shape)
    assert hookscore.curiosity("Here is the one setting that changed my entire retention curve.") > 22


def test_brevity_plateaus_between_9_and_24_words_and_decays_outside_it():
    assert hookscore.brevity(" ".join(["focus"] * 9)) == 100
    assert hookscore.brevity(" ".join(["focus"] * 24)) == 100
    assert hookscore.brevity(" ".join(["focus"] * 8)) < 100
    assert hookscore.brevity(" ".join(["focus"] * 25)) < 100
    assert hookscore.brevity(" ".join(["focus"] * 40)) < hookscore.brevity(" ".join(["focus"] * 26))
    assert hookscore.brevity("") == 0


# --------------------------------------------------------------------------- #
# the weakest-link verdict
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "hook",
    [
        HOOK_STRONG,
        HOOK_SHIPPED,
        HOOK_VAGUE,
        "You keep losing the first hour of every workday before you even open your laptop.",
        "Why does nobody help you?",
        "Everyone says post daily. I posted once a week for a year and grew more.",
        "",
    ],
)
def test_verdict_is_60_percent_mean_plus_40_percent_of_the_two_weakest(hook):
    parts, verdict, _, _ = hookscore.score(hook)
    assert verdict == weakest_link(list(parts.values()))


def test_the_weakest_properties_pull_the_verdict_below_the_plain_mean():
    parts, verdict, _, _ = hookscore.score(HOOK_STRONG)
    vals = list(parts.values())
    assert verdict < sum(vals) / len(vals), "a plain average would hide the dead property"


def test_a_single_dead_property_caps_the_verdict_below_strong():
    # The leak ceiling is the point of the redesign: four perfect properties cannot rescue
    # a detector reading under LEAK_FLOOR.
    assert hookscore.LEAK_FLOOR == 30
    assert hookscore.LEAK_CEILING == hookscore.STRONG_MIN - 1
    capped = weakest_link([100, 100, 100, 100, 5])
    assert capped <= hookscore.LEAK_CEILING
    assert hookscore.band(capped) != "STRONG"
    # the same hook with a merely weak fifth property is not capped
    assert weakest_link([100, 100, 100, 100, 50]) > capped


def test_leak_capped_verdicts_cannot_be_produced_by_a_real_hook():
    parts, verdict, _, _ = hookscore.score(HOOK_VAGUE)
    assert min(parts.values()) < hookscore.LEAK_FLOOR
    assert verdict <= hookscore.LEAK_CEILING
    assert hookscore.band(verdict) == "WEAK"


# --------------------------------------------------------------------------- #
# bands - one set of constants for the whole repo
# --------------------------------------------------------------------------- #
def test_band_thresholds_are_exactly_two_cuts_and_no_gaps():
    # The band() ladder is the only classifier in the repo, so its two cuts must be the
    # module constants and every verdict must land in one of the three named bands.
    # The absolute numbers are a calibration choice (STRONG_MIN is pinned against the
    # orchestrator gate below); the *shape* below is a correctness requirement.
    assert hookscore.band(hookscore.STRONG_MIN) == "STRONG"
    assert hookscore.band(hookscore.STRONG_MIN - 1) == "WORKABLE"
    assert hookscore.band(hookscore.WORKABLE_MIN) == "WORKABLE"
    assert hookscore.band(hookscore.WORKABLE_MIN - 1) == "WEAK"
    assert hookscore.band(100) == "STRONG"
    assert hookscore.band(0) == "WEAK"
    assert 0 < hookscore.WORKABLE_MIN < hookscore.STRONG_MIN <= 100
    # monotone: a higher verdict can never sit in a lower band
    order = {"WEAK": 0, "WORKABLE": 1, "STRONG": 2}
    bands = [hookscore.band(v) for v in range(101)]
    assert all(order[bands[v]] <= order[bands[v + 1]] for v in range(100))
    assert set(bands) == {"WEAK", "WORKABLE", "STRONG"}


def test_the_strong_band_starts_at_the_pass_mark_gemeni_md_quotes():
    # GEMINI.md section 6 and every gate in the repo treat 70 as the pass mark. That number is
    # load-bearing, unlike WORKABLE_MIN, which the scorer is still calibrating.
    assert hookscore.STRONG_MIN == 70
    assert hookscore.band(70) == "STRONG"


def test_the_pass_mark_is_the_same_constant_everywhere_in_the_repo():
    # GEMINI.md section 6 quotes ">= 70"; the orchestrator gate defaults to hook_min=70.
    # They used to disagree with band() (STRONG at 72); band() must now read STRONG_MIN, and the
    # gate must read it from here rather than carrying a third number.
    from tools.orchestrator import verifiers

    assert hookscore.band(hookscore.STRONG_MIN) == "STRONG"
    assert hookscore.band(hookscore.STRONG_MIN - 1) == "WORKABLE"
    source = Path(verifiers.__file__).read_text(encoding="utf-8")
    defaults = [d.strip() for d in re.findall(r'get\("hook_min",\s*([^)]+)\)', source)]
    assert defaults, "the hook_min default vanished from verifiers.py"
    shared = {str(hookscore.STRONG_MIN), "hookscore.STRONG_MIN", "youtube_skills.hookscore.STRONG_MIN"}
    assert set(defaults) <= shared, f"hook gate {defaults} is not the shared STRONG_MIN={hookscore.STRONG_MIN}"


def test_strong_second_person_numbered_stakes_hook_beats_a_vague_one():
    parts_s, verdict_s, formula_s, _ = hookscore.score(HOOK_SHIPPED)
    parts_v, verdict_v, _, _ = hookscore.score(HOOK_VAGUE)
    assert verdict_s > verdict_v
    assert hookscore.band(verdict_s) == "STRONG"
    assert hookscore.band(verdict_v) == "WEAK"
    assert parts_s["ADDRESS"] >= 90 and parts_s["STAKES"] >= 60
    assert parts_s["SPECIFICITY"] > parts_v["SPECIFICITY"]
    assert formula_s != "Unclassified"


def test_emphasis_asterisks_do_not_change_the_score():
    """project.json wraps spoken words in *asterisks*; scoring must ignore the markup."""
    bare = hookscore.score(HOOK_SHIPPED)
    marked = hookscore.score(
        "If you collapse on a *Manhattan* sidewalk, why do *eighty-five* *percent* of "
        "strangers stop and watch you die?"
    )
    assert bare == marked
    assert hookscore.score("one - two") == hookscore.score("one \u2014 two")


# --------------------------------------------------------------------------- #
# hooks.json formula loading
# --------------------------------------------------------------------------- #
def test_formulas_are_loaded_from_the_paired_json_file_not_hardcoded():
    raw = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    assert {"version", "note", "rules", "hooks"} <= set(raw)
    assert len(raw["rules"]) == 6, "the six authoring rules are part of the shipped file"
    assert hookscore.FORMULAS == raw["hooks"]


def test_hooks_json_ships_the_21_formulas_gemini_md_advertises():
    assert len(hookscore.FORMULAS) == 21
    assert len({f["id"] for f in hookscore.FORMULAS}) == 21
    assert len({f["name"] for f in hookscore.FORMULAS}) == 21


def test_every_formula_is_fully_described_with_compilable_patterns():
    for f in hookscore.FORMULAS:
        assert {"id", "name", "shape", "example", "fails_when", "match"} <= set(f), f["id"]
        assert isinstance(f["match"], list) and f["match"], f["id"]
        for pattern in f["match"]:
            re.compile(pattern)  # raises re.error if the shipped file ever breaks classify()


def test_classify_picks_the_best_matching_formula_and_reports_hit_count():
    name, hits = hookscore.classify("97% of the people who start a channel quit before video 30.")
    assert name == "The Statistic"
    assert hits >= 1
    assert hookscore.classify("hello there") == ("Unclassified", 0)
    assert hookscore.classify("") == ("Unclassified", 0)
    assert name in {f["name"] for f in hookscore.FORMULAS}


def test_fix_advice_exists_for_every_property():
    assert set(hookscore.FIX) == set(PROPERTY_NAMES)


def test_hooks_json_examples_are_not_weaker_than_the_library_advertises():
    """Every shipped formula example clears the library's minimum hook band."""
    weak = []
    for f in hookscore.FORMULAS:
        parts, verdict, _, _ = hookscore.score(f["example"])
        if hookscore.band(verdict) == "WEAK":
            weak.append(f"{f['name']:24} verdict {verdict:3}  weakest={min(parts, key=parts.get)}")
    report("hooks.json worked examples still scored WEAK by the shipped detectors", weak)
    assert not weak, "shipped examples must demonstrate the stakes their formula advertises"


def test_a_worked_example_is_never_flagged_weak():
    offenders = []
    for f in hookscore.FORMULAS:
        _, verdict, _, _ = hookscore.score(f["example"])
        if hookscore.band(verdict) == "WEAK":
            offenders.append(f["name"])
    assert not offenders, f"{len(offenders)} shipped examples are WEAK: {offenders}"


# --------------------------------------------------------------------------- #
# calibration: measure the claim instead of asserting it in prose
# --------------------------------------------------------------------------- #
def test_the_scorer_separates_shipped_examples_from_dead_controls():
    """hookscore.calibrate() is the whole evidence base for the band thresholds.

    The detectors are keyword based and do not rank the 21 formulas uniformly. The load-bearing
    invariants are that every worked example outscores the dead controls and that no control reaches
    the workable band.
    """
    c = hookscore.calibrate()
    assert "error" not in c, c["error"]
    assert c["controls"] >= 8, "hook_controls.txt needs enough dead hooks to mean anything"
    assert c["separation_pct"] == 100.0, f"examples and controls overlap: {c['separation_pct']}%"
    assert c["controls_reaching_workable"] == []
    assert c["control_max"] < hookscore.WORKABLE_MIN, "the WEAK band no longer means 'below shipped quality'"
    assert c["median_margin"] >= 15, f"the two populations are not far apart: {c['median_margin']}"


def test_calibrate_reports_the_examples_it_flags():
    c = hookscore.calibrate()
    flagged = set(c["examples_flagged_weak"])
    measured = {
        f["name"]
        for f in hookscore.FORMULAS
        if hookscore.band(hookscore.score(f["example"])[1]) == "WEAK"
    }
    assert flagged == measured


def test_the_calibrate_command_exits_zero_on_the_shipped_detectors():
    import subprocess
    import sys
    from pathlib import Path

    script = Path(hookscore.__file__)
    r = subprocess.run([sys.executable, str(script), "--calibrate"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "pair separation" in r.stdout


# --------------------------------------------------------------------------- #
# the package-level wrapper the pipeline actually calls
# --------------------------------------------------------------------------- #
def test_score_hook_wrapper_agrees_with_the_module_and_exposes_the_fix():
    res = score_hook(HOOK_STRONG)
    parts, verdict, formula, hits = hookscore.score(HOOK_STRONG)
    assert res["properties"] == parts
    assert res["verdict"] == verdict
    assert res["formula"] == formula
    assert res["matched"] == hits
    assert res["band"] == hookscore.band(verdict)
    assert res["weakest"] == min(parts, key=parts.get)
    assert res["fix"] == hookscore.FIX[res["weakest"]]
    assert res["hook"] == HOOK_STRONG


def test_score_hook_wrapper_survives_blank_and_hostile_input():
    for text in ("", "   ", "*", "\u2014", "?" * 80):
        res = score_hook(text)
        assert res["band"] in {"STRONG", "WORKABLE", "WEAK"}
        assert res["fix"] in hookscore.FIX.values()


def test_score_hook_wrapper_marks_a_summary_as_not_a_hook():
    res = score_hook("Here is some general advice about being more productive at work.")
    assert res["verdict"] < hookscore.WORKABLE_MIN
    assert res["band"] == "WEAK"
