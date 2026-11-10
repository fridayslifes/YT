"""tests/test_deadair.py - tools/youtube_skills/deadair.py + youtube_skills.analyze_dead_air.

GEMINI.md section 6: the EDL must flag pauses longer than 0.45s, filler-word cues and
false starts / repeated takes. Pure text + arithmetic, no media, no ffmpeg.
"""

from __future__ import annotations

import json

import pytest

from tools.youtube_skills import deadair
from tools.youtube_skills import analyze_dead_air, generate_chapters

# A five-cue transcript with one obvious 1.6s pause, one filler-only cue and one retake.
CUES = [
    (0.0, 1.2, "You keep checking your phone in bed."),
    (1.2, 1.9, "Um."),
    (3.5, 4.7, "You keep checking your phone in bed and lose an hour."),
    (4.7, 5.0, "yeah"),
    (5.05, 6.0, "That is the revenge sleep delay thing."),
]


def cuts_of(result: dict, kind: str) -> list[dict]:
    return [c for c in result["cuts"] if c["kind"] == kind]


# --------------------------------------------------------------------------- #
# timestamp parsing and loading
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("00:00:00,000", 0.0),
        ("00:00:02,500", 2.5),
        ("00:01:02,500", 62.5),
        ("01:02:03,000", 3723.0),
        ("00:01:02.500", 62.5),
        ("01:30,000", 90.0),
        ("  00:00:10,000  ", 10.0),
    ],
)
def test_parse_ts_handles_srt_and_vtt_style_timestamps(raw, expected):
    assert deadair.parse_ts(raw) == pytest.approx(expected)


@pytest.mark.parametrize("raw", ["12", "00:01:02:03"])
def test_parse_ts_rejects_malformed_timestamp_shape(raw):
    with pytest.raises(ValueError, match="timestamp"):
        deadair.parse_ts(raw)


@pytest.mark.parametrize("operation", [analyze_dead_air, generate_chapters])
def test_malformed_srt_timestamp_returns_error_in_public_api(tmp_path, operation):
    path = tmp_path / "bad.srt"
    path.write_text("1\n00:00:00,000 --> 12\nA line with malformed timing\n", encoding="utf-8")

    assert "timestamp" in operation(path)["error"].lower()


def test_load_reads_srt_cues_and_joins_multi_line_text(write_transcript):
    body = (
        "1\n00:00:00,000 --> 00:00:01,000\nFirst line\nsecond line of the same cue\n\n"
        "2\n00:00:01,000 --> 00:00:02,000\nOnly line\n"
    )
    cues = deadair.load(write_transcript("multi.srt", body))
    assert cues == [(0.0, 1.0, "First line second line of the same cue"), (1.0, 2.0, "Only line")]


def test_load_reads_whisper_json_segments(write_transcript):
    seg = write_transcript(
        "seg.json",
        json.dumps({"segments": [{"start": 0.0, "end": 1.0, "text": " Hello there "}, {"start": 1.0, "end": 2.0, "text": "You"}]}),
    )
    assert deadair.load(seg) == [(0.0, 1.0, "Hello there"), (1.0, 2.0, "You")]


def test_a_bare_segment_list_loads_like_any_other_transcript(write_transcript):
    bare = write_transcript("bare.json", json.dumps([{"start": 2.0, "end": 3.5, "text": "Bare list"}]))
    assert deadair.load(bare) == [(2.0, 3.5, "Bare list")]


def test_load_of_a_non_transcript_returns_nothing_rather_than_garbage(write_transcript):
    assert deadair.load(write_transcript("notes.srt", "just prose, no timestamps at all")) == []


def test_numeric_caption_text_survives_loading_without_adding_cue_indices(write_transcript):
    body = (
        "1\n00:00:00,000 --> 00:00:01,000\n1968\n\n"
        "2\n00:00:01,000 --> 00:00:02,000\nDarley and Latane published the study\n"
    )
    cues = deadair.load(write_transcript("year.srt", body))
    assert [c[2] for c in cues] == ["1968", "Darley and Latane published the study"]


def test_vtt_identifiers_are_not_added_to_caption_text(write_transcript):
    body = (
        "WEBVTT\n\nfirst\n00:00.000 --> 00:01.000\n1968\n\n"
        "second\n00:01.000 --> 00:02.000\nThe study\n"
    )
    assert deadair.load(write_transcript("year.vtt", body)) == [(0.0, 1.0, "1968"), (1.0, 2.0, "The study")]


# --------------------------------------------------------------------------- #
# pauses
# --------------------------------------------------------------------------- #
def test_a_pause_longer_than_the_floor_becomes_a_dead_air_cut(write_transcript):
    result = analyze_dead_air(write_transcript("a.srt", CUES))
    dead = cuts_of(result, "DEAD")
    assert len(dead) == 1
    assert dead[0]["why"] == "1.60s gap"
    # keep = floor / 2 on each side of the gap, measured from the *preceding cue's* end
    # (here the "Um." cue at 1.9s) to the next cue's start (3.5s)
    assert dead[0]["start"] == pytest.approx(1.9 + 0.225)
    assert dead[0]["end"] == pytest.approx(3.5 - 0.225)
    assert result["duration"] == 6.0


def test_the_floor_is_strictly_greater_than(write_transcript):
    cues = [(0.0, 1.0, "First spoken sentence here."), (1.45, 2.5, "Second spoken sentence here.")]
    result = analyze_dead_air(write_transcript("a.srt", cues))
    assert cuts_of(result, "DEAD") == [], "exactly 0.45s is not longer than 0.45s"
    assert analyze_dead_air(write_transcript("b.srt", cues), floor=0.4)["cuts"], "0.5s > a 0.4s floor"


def test_overlapping_cues_produce_no_negative_dead_air_cut(write_transcript):
    cues = [(0.0, 2.0, "One sentence that runs on."), (1.5, 3.0, "Another cue overlapping it.")]
    result = analyze_dead_air(write_transcript("a.srt", cues))
    assert cuts_of(result, "DEAD") == []
    assert result["removed"] == 0


def test_nested_overlapping_cues_do_not_create_dead_air_inside_speech():
    cues = [
        (0, 10, "Continuous speech throughout this whole interval."),
        (1, 2, "Another shorter overlapping cue."),
        (5, 6, "Later overlapping speech remains."),
        (12, 13, "A real pause precedes this cue."),
    ]
    dead = cuts_of(deadair.analyze_cues(cues), "DEAD")
    assert len(dead) == 1
    assert dead[0]["start"] == pytest.approx(10.225)
    assert dead[0]["end"] == pytest.approx(11.775)


@pytest.mark.parametrize("operation", [analyze_dead_air, generate_chapters])
@pytest.mark.parametrize("start,end", [("inf", 21), (20, "inf"), ("NaN", 21), (-1, 21), (21, 20), (20, 20)])
def test_invalid_transcript_timings_return_validation_errors(tmp_path, operation, start, end):
    cues = [{"start": t, "end": t + 1, "text": "Distinct transcript content."} for t in (0, 10, 20, 30, 40, 50)]
    cues[2].update(start=start, end=end)
    path = tmp_path / "timings.json"
    path.write_text(json.dumps(cues))
    result = operation(path)
    assert "error" in result
    assert "timestamp" in result["error"].lower()


# --------------------------------------------------------------------------- #
# filler words
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text", ["Um.", "uh", "so yeah, basically", "I mean...", "actually", "you know"])
def test_a_cue_that_is_only_filler_is_flagged(write_transcript, text):
    cues = [(0.0, 1.0, "A real sentence with content."), (1.05, 1.6, text)]
    result = analyze_dead_air(write_transcript("a.srt", cues))
    assert cuts_of(result, "FILLER"), f"{text!r} should be a filler cut"


def test_filler_recogniser_keeps_real_sentences(write_transcript):
    cues = [(0.0, 1.0, "You basically have to try this method."), (1.05, 1.6, "Really, the data supports it.")]
    result = analyze_dead_air(write_transcript("a.srt", cues))
    assert cuts_of(result, "FILLER") == []


def test_inline_filler_preserves_meaningful_speech_without_word_timings(write_transcript):
    # A cue timestamp cannot locate "Um" within the spoken audio. Cutting the cue would
    # remove the substantive sentence as well, so inline filler requires manual review.
    cues = [(0.0, 1.0, "Um, the first thing you should notice about this is the pause.")]
    result = analyze_dead_air(write_transcript("a.srt", cues))
    assert result["cuts"] == []
    assert result["removed"] == 0


# --------------------------------------------------------------------------- #
# false starts
# --------------------------------------------------------------------------- #
def test_a_restarted_take_is_flagged_as_repeat(write_transcript):
    cues = [
        (0.0, 1.2, "You keep checking your phone in bed."),
        (1.3, 2.6, "You keep checking your phone in bed and lose an hour."),
    ]
    result = analyze_dead_air(write_transcript("a.srt", cues))
    rep = cuts_of(result, "REPEAT")
    assert len(rep) == 1
    assert rep[0]["start"] == 0.0 and rep[0]["end"] == 1.2
    assert 'restart of "you keep checking your phone"' == rep[0]["why"]


def test_punctuation_and_case_are_ignored_when_comparing_takes(write_transcript):
    cues = [
        (0.0, 1.2, "YOU KEEP, CHECKING YOUR PHONE!"),
        (1.3, 2.6, "you keep checking your phone in bed and lose an hour."),
    ]
    assert cuts_of(analyze_dead_air(write_transcript("a.srt", cues)), "REPEAT")


def test_a_filler_cue_between_two_takes_does_not_hide_the_restart(write_transcript):
    result = analyze_dead_air(write_transcript("a.srt", CUES))
    assert len(cuts_of(result, "REPEAT")) == 1


def test_a_restarted_take_is_caught_when_the_first_take_is_short(write_transcript):
    cues = [
        (0.0, 0.8, "You keep checking"),
        (0.9, 2.6, "You keep checking your phone in bed and lose an hour."),
    ]
    assert cuts_of(analyze_dead_air(write_transcript("a.srt", cues)), "REPEAT")


def test_a_short_first_take_does_not_match_a_different_opening(write_transcript):
    cues = [(0.0, 0.8, "You keep checking"), (0.9, 2.6, "You keep changing the task.")]
    assert cuts_of(analyze_dead_air(write_transcript("different.srt", cues)), "REPEAT") == []


# --------------------------------------------------------------------------- #
# the EDL as a whole: honesty and arithmetic
# --------------------------------------------------------------------------- #
def test_the_edl_is_sorted_never_degenerate_and_the_totals_add_up(write_transcript):
    result = analyze_dead_air(write_transcript("a.srt", CUES))
    starts = [c["start"] for c in result["cuts"]]
    assert starts == sorted(starts)
    assert all(c["end"] > c["start"] for c in result["cuts"]), "zero/negative-length cuts are filtered"
    removed = sum(c["end"] - c["start"] for c in result["cuts"])
    assert result["removed"] == pytest.approx(round(removed, 3))
    assert result["out"] == pytest.approx(round(result["duration"] - removed, 3))
    assert 0 < result["removed"] < result["duration"]
    assert result["source"].endswith("a.srt")


@pytest.mark.parametrize("cues, duration, removed", [
    ([(0, 2, "um"), (1, 3, "uh"), (2, 3, "okay")], 3, 3),
    ([(0, 5, "um"), (1, 3, "uh"), (2, 3, "okay")], 5, 5),
    ([(0, 2, "um"), (1, 3, "uh"), (3, 5, "Meaningful speech remains.")], 5, 3),
])
def test_overlapping_cuts_count_each_removed_second_once(cues, duration, removed):
    result = deadair.analyze_cues(cues)
    assert result["duration"] == duration
    assert result["removed"] == removed
    assert result["out"] == duration - removed
    assert len(result["cuts"]) >= 2, "each diagnostic reason remains available"


def test_an_empty_transcript_yields_an_error_instead_of_a_fabricated_edl(write_transcript):
    assert analyze_dead_air(write_transcript("empty.srt", "")) == {"error": "No cues found in transcript"}
    assert analyze_dead_air(write_transcript("prose.srt", "no timestamps here at all")) == {
        "error": "No cues found in transcript"
    }


def test_a_missing_transcript_returns_an_error_with_the_path(tmp_path):
    missing = tmp_path / "does-not-exist.srt"
    result = analyze_dead_air(missing)
    assert set(result) == {"error"}
    assert str(missing) in result["error"]


@pytest.mark.parametrize("body", ["{bad json", '{"segments": null}', '[{"text": "missing timestamps"}]'])
def test_malformed_transcript_json_returns_an_error(write_transcript, body):
    assert "error" in analyze_dead_air(write_transcript("bad.json", body))


@pytest.mark.parametrize("operation", [analyze_dead_air, generate_chapters])
@pytest.mark.parametrize("text", [1968, True, ["caption"], {"text": "caption"}])
def test_non_string_segment_text_returns_a_validation_error(write_transcript, operation, text):
    path = write_transcript("bad.json", json.dumps({"segments": [{"start": 0, "end": 1, "text": text}]}))
    result = operation(path)
    assert "text must be a string" in result["error"]


@pytest.mark.parametrize("operation", [analyze_dead_air, generate_chapters])
def test_non_object_segments_return_a_validation_error(write_transcript, operation):
    result = operation(write_transcript("bad.json", '["caption"]'))
    assert "must be an object" in result["error"]


def test_cli_json_output_matches_the_programmatic_edl(write_transcript, monkeypatch, capsys):
    path = write_transcript("cli.srt", CUES)
    monkeypatch.setattr("sys.argv", ["deadair.py", path, "--json"])
    deadair.main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["duration"] == 6.0
    assert [c["kind"] for c in payload["cuts"]] == ["REPEAT", "FILLER", "DEAD", "FILLER"]
    assert payload == analyze_dead_air(path)


def test_cli_and_api_agree_on_short_retakes_and_numeric_captions(write_transcript, monkeypatch, capsys):
    cues = [(0.0, 0.8, "You keep checking"), (0.9, 2.0, "You keep checking your phone"), (2.1, 3.0, "1968")]
    path = write_transcript("short.srt", cues)
    monkeypatch.setattr("sys.argv", ["deadair.py", path, "--json"])
    deadair.main()
    payload = json.loads(capsys.readouterr().out)
    assert payload == analyze_dead_air(path)
    assert cuts_of(payload, "REPEAT")
    assert payload["duration"] == 3.0


def test_cli_reports_the_documented_floor_and_percentage_when_not_json(write_transcript, monkeypatch, capsys):
    path = write_transcript("cli.srt", CUES)
    monkeypatch.setattr("sys.argv", ["deadair.py", path, "--floor", "0.35"])
    deadair.main()
    out = capsys.readouterr().out
    assert "dead-air floor 0.35s" in out
    assert "cuts," in out and "% shorter" in out
