"""tests/test_output_format.py - tools/output_format.py, the terminal report engine.

The rule being tested here is a narrow, important one: a renderer may only ever repeat back what
it was given. It must be deterministic, and it must not print PASS / "online" / "LIVE" for data it
never received. tools/output_format.py is the module every gate message in the pipeline is built
from (pipeline.py, agents.py, orchestrator/*), so a hardcoded green badge here becomes a false
"Ready" claim in a quality report three layers up.
"""

from __future__ import annotations

import re

import pytest

from tools import output_format as fmt
from tools.youtube_skills import hookscore

ANSI_RE = re.compile(r"\033\[[0-9;]*m")


class Report:
    """Minimal stand-in for the agent report objects agent_report_card() reads by getattr."""

    def __init__(self, name="Researcher", status="PASS", duration_s=1.0, summary="", role="Research", emoji="🔬"):
        self.agent_name = name
        self.status = status
        self.duration_s = duration_s
        self.summary = summary
        self.role = role
        self.emoji = emoji


class Agent:
    def __init__(self, name="Researcher", role="Evidence", emoji="🔬", status="PASS"):
        self.name = name
        self.role = role
        self.emoji = emoji
        self.status = status


def plain(text: str) -> str:
    """Strip ANSI codes: output_format decides colour from isatty() at import time."""
    return ANSI_RE.sub("", text)


# --------------------------------------------------------------------------- #
# determinism
# --------------------------------------------------------------------------- #
def test_every_emitter_is_deterministic_for_the_same_input():
    calls = [
        ("table", lambda: fmt.table(["ID", "Status"], [["SH-01", "PASS"], ["SH-02", "WARN"]])),
        ("header", lambda: fmt.header("Quality Gate", "Reference Precision", "🛡️")),
        ("section", lambda: fmt.section("Results")),
        ("progress_bar", lambda: fmt.progress_bar(7, 10, "scenes")),
        ("scene_progress", lambda: fmt.scene_progress(3, 8, "s03", "PASS")),
        ("badge", lambda: fmt.badge("PASS")),
        ("verification_summary", lambda: fmt.verification_summary(4, 2, 1, 7)),
        ("crew_status", lambda: fmt.crew_status([Agent()], ["cinematic_35mm"])),
        ("project_card", lambda: fmt.project_card("SH-01", "Loss Aversion", "35mm", 76, "STRONG", 132, 52.8, 8)),
    ]
    for name, fn in calls:
        first, second = fn(), fn()
        assert first == second, f"{name} is not reproducible - CI logs would diff for no reason"
        assert isinstance(first, str) and first


def test_no_output_embeds_a_timestamp_or_hidden_state():
    # A report line must be a pure function of its arguments: two renders of the same numbers
    # must be byte-identical, with nothing but the values themselves in the text.
    text = plain(fmt.verification_summary(4, 2, 1, 7))
    assert text == plain(fmt.verification_summary(4, 2, 1, 7))
    assert "4 passed" in text and "2 blueprint-ready" in text and "1 warned" in text and "(7 total)" in text


def test_unknown_status_renders_its_own_label_instead_of_defaulting_to_pass():
    assert "[  PASS  ]" in plain(fmt.badge("pass"))
    assert "[ SKIPPED]" in plain(fmt.badge(" skipped "))
    assert "MYSTERY" in plain(fmt.badge("MYSTERY"))
    assert "MYSTERY" in plain(fmt.badge("Mystery"))
    assert "[  PASS  ]" not in plain(fmt.badge("MYSTERY"))


def test_a_table_with_no_rows_says_so_instead_of_fabricating_one():
    assert fmt.table(["ID", "Status"], []) == "  (no data)"
    assert fmt.table([], []) == "  (no data)"


def test_progress_bar_survives_a_zero_total_without_claiming_anything():
    assert fmt.progress_bar(0, 0) == ""
    assert "100%" in fmt.progress_bar(5, 5)
    assert "0%" in fmt.progress_bar(0, 5)


def test_agent_report_card_with_no_reports_claims_no_passes():
    text = plain(fmt.agent_report_card([]))
    assert "0 passed" in text
    assert "[  PASS  ]" not in text, "an empty crew must not print a single green badge"


def test_verification_summary_only_counts_what_it_was_given():
    text = plain(fmt.verification_summary(0, 0, 0, 0))
    assert "0 passed" in text and "0 blueprint-ready" in text and "(0 total)" in text


# --------------------------------------------------------------------------- #
# the voice.md sanitizer never invents copy
# --------------------------------------------------------------------------- #
def test_sanitize_voice_text_strips_blacklisted_buzzwords_only():
    out = fmt.sanitize_voice_text("Let's dive in to the tapestry of the landscape, it is a game-changer")
    for banned in ("dive in", "tapestry", "landscape", "game-changer"):
        assert banned not in out.lower()
    assert "it is a" in out
    assert fmt.sanitize_voice_text("Clean sentence about attention residue.") == "Clean sentence about attention residue."


def test_sanitize_voice_text_never_adds_words():
    src = "delve into an unbelievable realm"
    out = fmt.sanitize_voice_text(src)
    source_tokens = {t.strip(".,;!").lower() for t in src.split()}
    for token in out.split():
        assert token.strip(".,;!).").lower() in source_tokens, "the sanitizer may delete, never invent"


# --------------------------------------------------------------------------- #
# Report status and layout regressions
# --------------------------------------------------------------------------- #
def test_crew_status_only_reports_configuration():
    empty = plain(fmt.crew_status([]))
    assert "No agents configured" in empty
    assert "All agents online" not in empty
    assert "Ready for pipeline execution" not in empty
    failing = plain(fmt.crew_status([Agent(status="FAIL"), Agent(name="Gate", status="WARN")]))
    assert "All agents online" not in failing
    assert "2 agents configured" in failing


def test_a_report_object_with_no_status_should_be_shown_as_unknown():
    class NoStatus:
        agent_name = "Researcher"
        role = "Evidence"
        duration_s = 2.0
        summary = ""
        emoji = "🔬"

    text = plain(fmt.agent_report_card([NoStatus()]))
    assert "[  PASS  ]" not in text
    assert "UNKNOWN" in text.upper()
    assert "1 unknown status" in text
    assert "0 passed" in text


@pytest.mark.parametrize("status", ["PASS", " pass ", "HEALED", "READY"])
def test_a_row_that_fails_the_mp4_check_should_not_be_able_to_say_pass(status):
    line = plain(fmt.verification_project_row("SH-99", status, mp4_valid=False))
    assert "[  PASS  ]" not in line
    assert "FAIL" in line and "✗" in line


@pytest.mark.parametrize("status", ["DRAFT", "BLUEPRINT", "WARN"])
def test_missing_mp4_preserves_non_success_states(status):
    assert plain(fmt.badge(status)) in plain(fmt.verification_project_row("SH-99", status, mp4_valid=False))


HOOK_ICONS = {"🔥": "STRONG", "⚡": "WORKABLE", "⚠️": "WEAK"}


def hook_bar_conflicts():
    """Verdicts where _hook_display's icon disagrees with the band printed beside it.

    output_format hardcodes its own 70/50 cut-points instead of importing hookscore.STRONG_MIN
    and hookscore.WORKABLE_MIN, so the two ladders part company wherever the constants differ.
    """
    conflicts = []
    for v in range(101):
        rendered = plain(fmt._hook_display(v, hookscore.band(v)))
        icon = rendered.split(" ", 1)[0]
        if HOOK_ICONS[icon] != hookscore.band(v):
            conflicts.append((v, icon, HOOK_ICONS[icon], hookscore.band(v)))
    return conflicts


def test_the_hook_bar_colour_follows_the_band_the_scorer_printed():
    # Fixed 2026-10-31. _hook_display() used to re-implement the banding with its own >=70 / >=50
    # literals while hookscore.band() used STRONG_MIN/WORKABLE_MIN, so project_card() printed a
    # flame icon and a [WORKABLE] label for the same verdict. The bar now reads the band it is
    # handed, which retires the old current-behavior pin.
    assert hook_bar_conflicts() == []
    for verdict, expected in [(0, "WEAK"), (47, "WEAK"), (48, "WORKABLE"), (69, "WORKABLE"), (70, "STRONG"), (100, "STRONG")]:
        rendered = plain(fmt._hook_display(verdict, hookscore.band(verdict)))
        assert HOOK_ICONS[rendered.split(" ", 1)[0]] == expected, f"verdict {verdict}"


def test_the_table_frame_should_stay_aligned_with_overlong_cells():
    rendered = plain(fmt.table(["note"], [["x" * 70], ["short"]]))
    assert len({len(line) for line in rendered.splitlines()}) == 1
    assert rendered.count("x") == 70


def test_table_wraps_multiline_colored_cells_and_pads_missing_columns():
    rendered = plain(fmt.table(["one", "two"], [["\033[31m" + "x" * 70 + "\033[0m", "a\nb"], ["short"]], [12, 8]))
    assert len({len(line) for line in rendered.splitlines()}) == 1
    assert rendered.count("x") == 70


def test_an_unrendered_project_is_a_draft_and_not_a_hard_failure(repo_root):
    # verify_all_projects() used to FAIL any project whose MP4 was missing, so one never-built draft
    # held the whole channel at exit 2 - and a gate that is permanently red gets ignored. An unbuilt
    # project is now DRAFT (counted as a warning); only an MP4 that exists and fails is fatal.
    assert "DRAFT" in fmt.STATUS_BADGES and "DRAFT" in fmt.STATUS_BADGES_PLAIN
    assert fmt.badge("DRAFT") == "[ DRAFT  ]"

    src = (repo_root / "tools" / "pipeline.py").read_text(encoding="utf-8")
    assert src.count('if not meta.get("valid") and not mp4_p.exists():') == 2, "both Shorts and Long-Form"
    assert 'status = "FAIL"' in src, "a present-but-broken MP4 must still be fatal"

    # and a channel with no drafts reads exactly as it did before this status existed
    plain = ANSI_RE.sub("", fmt.verification_summary(3, 1, 2, 6))
    assert "never rendered" not in plain
    assert "never rendered" in ANSI_RE.sub("", fmt.verification_summary(3, 1, 2, 6, 1))
