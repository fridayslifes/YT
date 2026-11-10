"""tests/test_chapters.py - tools/youtube_skills/chapters.py + youtube_skills.generate_chapters.

GEMINI.md section 6 and the module docstring both promise YouTube's hard rendering constraints:
the list must start at 00:00, needs at least 3 chapters, and every chapter must be >= 10 seconds.
A block that breaks any of those silently stops being chapters, which is the whole reason the
validator exists.
"""

from __future__ import annotations

import json

import pytest

from tools.youtube_skills import chapters
from tools.youtube_skills import generate_chapters

MIN_CHAPTER_SECONDS = 10.0  # YouTube's floor, hard-coded as min_dist/min_gap in the module

RICH = [
    (0.0, 1.9, "You stare at a screen and your attention drifts away from the task"),
    (4.3, 6.2, "at hand again and again every single working afternoon you spend"),
    (18.7, 20.6, "The doorway effect explains why walking through a door erases"),
    (24.0, 25.9, "what you were about to say entirely in the moment you arrive"),
    (41.8, 43.7, "Sleep pressure builds with adenosine until bedtime procrastination"),
    (46.0, 47.9, "takes over your evening and you never actually start the book"),
    (61.5, 63.4, "The bystander effect means a crowd of witnesses produces nobody"),
    (65.0, 66.9, "who actually helps at all when the emergency is real"),
    (79.0, 80.9, "Decision fatigue degrades every choice you make later"),
    (83.6, 85.5, "in the same working day after a hundred small ones"),
]

SPARSE = [
    (0.0, 1.9, "You stare at a screen and your attention drifts away from the task"),
    (2.2, 4.1, "at hand again and again every single working afternoon you spend"),
    (4.4, 6.3, "The doorway effect explains why walking through a door erases"),
    (6.6, 8.5, "what you were about to say entirely in the moment you arrive"),
    (8.8, 10.7, "Sleep pressure builds with adenosine until bedtime procrastination"),
    (11.0, 12.9, "takes over your evening and you never actually start the book"),
]


def chapter_seconds(result: dict) -> list[float]:
    """Independently recompute each chapter's length from the reported boundaries."""
    starts = [c["start"] for c in result["chapters"]]
    dur = result["duration"]
    return [round(starts[i + 1] - starts[i], 3) if i + 1 < len(starts) else round(dur - starts[i], 3)
            for i in range(len(starts))]


# --------------------------------------------------------------------------- #
# primitives
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "seconds, expected",
    [
        (0, "0:00"),
        (9.4, "0:09"),
        (59.99, "0:59"),
        (60, "1:00"),
        (65, "1:05"),
        (599.6, "9:59"),
        (3600, "1:00:00"),
        (3725, "1:02:05"),
    ],
)
def test_mmss_formats_timestamps_the_way_youtube_accepts(seconds, expected):
    assert chapters.mmss(seconds) == expected


def test_keywords_drops_stop_words_and_short_tokens():
    kw = chapters.keywords("The children were running because the focus drift matters to you")
    assert "children" in kw and "focus" in kw and "drift" in kw
    assert not kw & {"the", "were", "to", "you"}, "stop words must never become chapter titles"
    assert "because" in kw  # not in the shipped stop list
    assert all(len(w) >= 4 for w in kw)
    assert "run" not in kw  # shorter than the 4-char floor


def test_keywords_is_case_insensitive_and_punctuation_free():
    assert chapters.keywords("FOCUS, drift; attention.") == chapters.keywords("focus drift attention")


# --------------------------------------------------------------------------- #
# the hard constraints
# --------------------------------------------------------------------------- #
def test_too_few_cues_returns_an_error_instead_of_inventing_chapters(write_transcript):
    short = write_transcript("short.srt", [(0.0, 1.0, "One cue only.")])
    assert "error" in generate_chapters(short)
    exactly_five = write_transcript("five.srt", [(i * 2.0, i * 2.0 + 1.0, f" cue number {i}") for i in range(5)])
    assert "error" in generate_chapters(exactly_five)


def test_chapters_always_open_at_zero(write_transcript):
    # The generator seeds its candidate list with 0.0, so a block can never fail the 00:00 rule.
    for name, cues in (("rich.srt", RICH), ("sparse.srt", SPARSE)):
        result = generate_chapters(write_transcript(name, cues))
        assert result["chapters"][0]["start"] == 0.0
        assert result["chapters"][0]["timestamp"] == "0:00"


def test_a_block_with_fewer_than_three_chapters_is_reported_invalid(write_transcript):
    result = generate_chapters(write_transcript("sparse.srt", SPARSE))
    assert len(result["chapters"]) == 1
    assert result["valid"] is False, "YouTube silently refuses a 1-entry chapter list"


def test_a_compliant_block_is_reported_valid_and_starts_at_zero(write_transcript):
    result = generate_chapters(write_transcript("rich.srt", RICH))
    assert result["valid"] is True
    assert len(result["chapters"]) >= 3
    assert result["chapters"][0]["start"] == 0.0
    assert result["duration"] == pytest.approx(85.5)


def test_every_generated_chapter_meets_the_ten_second_minimum(write_transcript):
    # The rule chapters.py states in its docstring, verified independently of the valid flag:
    # boundaries must be >= 10s apart AND the final chapter must run >= 10s.
    result = generate_chapters(write_transcript("rich.srt", RICH))
    for c, seconds in zip(result["chapters"], chapter_seconds(result)):
        assert seconds >= MIN_CHAPTER_SECONDS, f"{c} is only {seconds}s"


def test_chapter_starts_are_monotonic_and_inside_the_media_duration(write_transcript):
    result = generate_chapters(write_transcript("rich.srt", RICH))
    starts = [c["start"] for c in result["chapters"]]
    assert starts == sorted(starts)
    assert starts[-1] < result["duration"]
    for c in result["chapters"]:
        assert c["timestamp"] == chapters.mmss(c["start"]), "the pasted label and the numeric start must agree"


def test_chapter_labels_are_topic_words_not_stop_word_noise(write_transcript):
    result = generate_chapters(write_transcript("rich.srt", RICH))
    for c in result["chapters"]:
        assert c["title"]
        assert " / " in c["title"] or c["title"] in {"Intro"}, c["title"]
        assert not {w.lower() for w in c["title"].split()} & {"the", "and", "you"}, "titles must not be filler"


# --------------------------------------------------------------------------- #
# the standalone validator and the API share the same chapter generator
# --------------------------------------------------------------------------- #
def test_cli_validator_accepts_a_compliant_block(write_transcript, monkeypatch, capsys):
    path = write_transcript("rich.srt", RICH)
    monkeypatch.setattr("sys.argv", ["chapters.py", path])
    chapters.main()
    out = capsys.readouterr().out
    assert "INVALID" not in out
    assert "4 chapters" in out
    assert "0:00" in out
    assert "Retitle every line before pasting" in out


def test_cli_validator_rejects_a_block_that_is_too_short(write_transcript, monkeypatch, capsys):
    path = write_transcript("sparse.srt", SPARSE)
    monkeypatch.setattr("sys.argv", ["chapters.py", path])
    chapters.main()
    out = capsys.readouterr().out
    assert "INVALID: YouTube needs 3+, a 00:00 first entry and 10s minimum each" in out


def test_cli_validator_json_carries_the_per_chapter_duration(write_transcript, monkeypatch, capsys):
    path = write_transcript("rich.srt", RICH)
    monkeypatch.setattr("sys.argv", ["chapters.py", path, "--json"])
    chapters.main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is True
    for c in payload["chapters"]:
        assert c["seconds"] >= MIN_CHAPTER_SECONDS
        assert {"start", "label", "draft_title", "seconds"} <= set(c)


def test_cli_refuses_a_missing_file_without_printing_chapters(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["chapters.py", "/no/such/transcript.srt"])
    with pytest.raises(SystemExit) as exc:
        chapters.main()
    assert exc.value.code == 1
    assert "too few cues" not in capsys.readouterr().out


def test_the_api_reports_each_chapter_duration(write_transcript):
    result = generate_chapters(write_transcript("rich.srt", RICH))
    assert [c["seconds"] for c in result["chapters"]] == chapter_seconds(result)
    assert all(c["seconds"] >= MIN_CHAPTER_SECONDS for c in result["chapters"])


def test_cli_and_api_agree_on_chapter_boundaries_labels_and_validation(write_transcript, monkeypatch, capsys):
    path = write_transcript("shared.srt", RICH)
    monkeypatch.setattr("sys.argv", ["chapters.py", path, "--json"])
    chapters.main()
    cli = json.loads(capsys.readouterr().out)
    api = generate_chapters(path)
    assert cli["valid"] == api["valid"]
    assert cli["duration"] == api["duration"]
    assert cli["chapters"] == [
        {"start": c["start"], "label": c["timestamp"], "draft_title": c["title"], "seconds": c["seconds"]}
        for c in api["chapters"]
    ]


def test_chapters_validate_the_whole_second_timestamps_the_user_pastes():
    cues = [(start, start + 0.1, "Focus attention memory research") for start in (0, 2, 10.999, 12, 20.999, 29.998)]
    result = chapters.generate(cues)
    assert all(c["start"] == int(c["start"]) for c in result["chapters"])
    assert all(c["timestamp"] == chapters.mmss(c["start"]) for c in result["chapters"])
    assert result["valid"] is True
    assert all(c["seconds"] >= 10 for c in result["chapters"])


def test_a_video_just_short_of_thirty_seconds_cannot_have_three_valid_chapters():
    cues = [(start, end, "Focus attention memory research") for start, end in
            [(0, 1), (2, 3), (10, 11), (12, 13), (20, 21), (29, 29.999)]]
    assert chapters.generate(cues)["valid"] is False


def test_missing_chapter_transcript_returns_a_read_error(tmp_path):
    missing = tmp_path / "missing.srt"
    assert str(missing) in generate_chapters(missing)["error"]


def test_chapter_duration_includes_longer_overlapping_cues():
    cues = [
        (0, 60, "Continuous speech spans this interval."),
        *[(start, start + 1, "Additional caption content.") for start in (10, 20, 30, 40, 50)],
    ]
    result = chapters.generate(cues)
    assert result["duration"] == 60
    assert result["chapters"][-1]["start"] + result["chapters"][-1]["seconds"] == 60


def test_direct_chapter_generation_rejects_nonfinite_timings():
    cues = [(start, start + 1, "Caption content.") for start in (0, 10, 20, 30, 40, 50)]
    cues[2] = (float("inf"), 21, "Invalid caption timing.")
    assert "error" in chapters.generate(cues)
