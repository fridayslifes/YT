"""tests/test_title.py - tools/youtube_skills/title.py, the title linter.

Contract (GEMINI.md section 5): report mobile (~40 char) and desktop (~60 char) truncation as two
different failures, catch shouting, catch vague adjectives, and honour the channel's
strictly-lowercase `#shorts` rule.

The thumbnail half of this linter was deleted on 2026-11-01 with the rest of the thumbnail
subsystem: `check(title)` takes a title only, the "duplicate" and "thumb-length" issue kinds no
longer exist, and `youtube_skills.check_packaging(video_title)` takes one argument - because
YouTube picks this channel's feed preview from the video's own frames.
"""

from __future__ import annotations

import pytest

from tools.youtube_skills import title
from tools.youtube_skills.title import check


def kinds(result: dict) -> list[str]:
    return [k for k, _ in result["issues"]]


def messages(result: dict) -> str:
    return " | ".join(m for _, m in result["issues"])


def title_of_length(n: int) -> str:
    """A title whose stripped length is exactly `n`, with a number and no caps words."""
    base = "Why 85% of people walk past "  # 28 characters, contains a concrete figure
    assert n >= len(base)
    return base + "x" * (n - len(base))


# --------------------------------------------------------------------------- #
# length / truncation
# --------------------------------------------------------------------------- #
def test_the_three_documented_limits_are_the_ones_in_force():
    assert (title.DESKTOP, title.MOBILE, title.HARD) == (60, 40, 100)


def test_a_40_character_title_is_not_reported_as_mobile_truncated():
    r = check(title_of_length(40))
    assert r["chars"] == 40
    assert "mobile" not in kinds(r), "the limit is inclusive: 40 characters still fits a feed"


def test_the_boundary_is_41_not_40():
    assert "mobile" not in kinds(check(title_of_length(39)))
    assert "mobile" in kinds(check(title_of_length(41)))


def test_41_characters_is_reported_as_mobile_truncation_only():
    r = check(title_of_length(41))
    assert "mobile" in kinds(r)
    assert "length" not in kinds(r), "41 is well inside the desktop cut"
    assert "characters" not in messages(r)


def test_a_60_character_title_clears_desktop_but_61_does_not():
    assert "length" not in kinds(check(title_of_length(60)))
    r = check(title_of_length(61))
    assert "length" in kinds(r)
    assert "desktop search cuts near 60" in messages(r)
    assert "mobile" in kinds(r), "desktop and mobile truncation are separate failures - both must appear"


def test_100_is_the_hard_limit_and_101_breaks_it():
    assert "hard limit" not in messages(check(title_of_length(100)))
    r = check(title_of_length(101))
    assert "length" in kinds(r)
    assert "hard limit is 100" in messages(r)


def test_the_mobile_preview_shows_the_last_whole_word_that_survives():
    t = "Why You Freeze In The Afternoon 85 Percent Study"
    r = check(t)
    preview = messages(r)
    assert '"Why You Freeze In The Afternoon 85..."' in preview, "the partial 41st word must not be shown as visible"


# --------------------------------------------------------------------------- #
# shouting, vagueness, numbers, front-loading
# --------------------------------------------------------------------------- #
def test_three_all_caps_words_is_shouting_but_two_is_allowed():
    three = check("85% Of People Who SEE THIS PDF TODAY Miss It")
    two = check("85% Of People Who SEE THIS Miss It Today")
    assert "shouting" in kinds(three)
    assert "shouting" not in kinds(two)
    assert "two is the ceiling" in messages(three)


def test_two_letter_acronyms_and_numbers_are_not_counted_as_shouting():
    r = check("Why AI SEO Ranks Differ For 85% Of Channels")
    assert "shouting" not in kinds(r), "len>2 filter means AI/85%/3D are not shouting"


def test_vague_adjectives_are_flagged_by_name():
    r = check("This Is An Amazing Video About Focus")
    assert "vague" in kinds(r)
    assert "amazing" in messages(r)
    for word in ("incredible", "insane", "revolutionary", "ultimate", "mindblowing"):
        assert "vague" in kinds(check(f"Why {word} Focus Habits 85% Fail")), word


def test_the_title_linter_should_share_the_channel_buzzword_blacklist():
    from tools import output_format

    assert title.VOICE_BLACKLIST is output_format.VOICE_BLACKLIST
    for word in output_format.VOICE_BLACKLIST:
        assert "vague" in kinds(check(f"Why {word} Focus Habits 85% Fail")), word


def test_blacklist_matching_respects_word_boundaries():
    assert "vague" not in kinds(check("Why 85% of unlockable doors fail"))


def test_a_title_without_any_figure_is_flagged_as_the_most_reliable_single_fix():
    assert "no-number" in kinds(check("Why Bystanders Walk Past People In Danger"))
    assert "no-number" not in kinds(check("Why 85% Of Bystanders Walk Past People"))
    assert "carries a concrete figure" in " ".join(check("Why 85% Of Bystanders Walk Past People")["good"])


def test_front_three_words_being_all_stop_words_is_flagged():
    assert "front-load" in kinds(check("This Is An Amazing Habit 85% Of People Break"))
    assert "front-load" not in kinds(check("Bystanders Ignore 85% Of Collapses In Public"))


def test_open_question_is_recorded_as_a_strength():
    r = check("Why Do 85% Of Bystanders Walk Past You?")
    assert "open question in the title" in r["good"]


# --------------------------------------------------------------------------- #
# title-only after the 2026-11-01 thumbnail removal
# --------------------------------------------------------------------------- #
def test_check_takes_a_title_and_nothing_else():
    """The thumbnail co-linter is gone: no `thumb` parameter, no thumb-derived issue kinds."""
    import inspect

    params = list(inspect.signature(check).parameters)
    assert params == ["title"], f"title.check() still accepts {params}; check_packaging() is one argument too"

    r = check("Why 85% Of Bystanders Walk Past You")
    assert not any(k.startswith("thumb") or k == "duplicate" for k in kinds(r)), kinds(r)

    from tools.youtube_skills import check_packaging

    assert list(inspect.signature(check_packaging).parameters) == ["video_title"]
    assert check_packaging("Why 85% Of Bystanders Walk Past You")["title"] == "Why 85% Of Bystanders Walk Past You"


# --------------------------------------------------------------------------- #
# determinism and score arithmetic
# --------------------------------------------------------------------------- #
def test_check_is_deterministic_and_score_follows_the_documented_formula():
    title_text = "Why 85% of People Walk Past You"
    first = check(title_text)
    second = check(title_text)
    assert first == second, "the same packaging must always lint the same way"
    assert first["score"] == max(0, min(100, 100 - 14 * len(first["issues"]) + 4 * len(first["good"])))
    assert 0 <= first["score"] <= 100


def test_title_is_stripped_before_measuring_and_reporting():
    bare = "Why 85% of people walk past you"
    padded = f"   {bare}   "
    assert check(padded)["title"] == bare
    assert check(padded)["chars"] == len(bare)
    assert check(padded) == check(bare)


def test_show_renders_every_issue_kind_and_the_score(capsys):
    r = check("This Is An Amazing Video About Focus")
    title.show(r)
    text = capsys.readouterr().out
    assert r["title"] in text
    for kind, _ in r["issues"]:
        assert kind in text
    assert f"score {r['score']}/100" in text


# --------------------------------------------------------------------------- #
# Hashtag casing
# --------------------------------------------------------------------------- #
def test_shorts_hashtag_must_be_lowercase():
    assert "shorts-case" in kinds(check("Loss Aversion Explained #Shorts 1979"))
    assert "shorts-case" in kinds(check("Loss Aversion Explained #SHORTS 1979"))
    assert "shorts-case" not in kinds(check("Loss Aversion Explained #shorts 1979"))


@pytest.mark.parametrize("tag", ["#ShortsFilm", "#Shortstop"])
def test_other_hashtags_do_not_trigger_shorts_case(tag):
    assert "shorts-case" not in kinds(check(f"1979 Experiment {tag}"))
