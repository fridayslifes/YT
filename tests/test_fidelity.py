"""tests/test_fidelity.py - does project.json still describe the video that was actually rendered?

tools/pipeline.py:395-462 compares the scene text against the shipped SRT with difflib and warns below
FIDELITY_MIN. Two failure modes are worth tests, because they pull in opposite directions:

  * a silent pass after someone edits a script and never rebuilds, so the channel goes on quoting a
    line nobody spoke (hook scores, citations and UPLOAD_KITs all read that file);
  * a warning that fires on every project because normalisation is too weak - a gate that cries wolf
    gets ignored, and the real edits get ignored with it.

Everything here runs out of tmp_path: no ffmpeg, no MP4, no model, no network.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import REPO_ROOT, report as honesty_report
from tools.pipeline import (
    FIDELITY_MIN,
    _shipped_captions,
    _spoken_tokens,
    caption_fidelity_issues,
)

SCRIPT = "You open forty tabs, and your brain pays for every one of them. That is the attention tax."
SCENES = [{"text": "You open forty tabs, and your brain pays for every one of them."},
          {"text": "That is the attention tax."}]


def make_project(tmp_path: Path, slug: str, captions: list[str], extra_srts: dict[str, str] | None = None) -> Path:
    """A project directory holding scenes and the captions its render actually spoke."""
    root = tmp_path / slug
    (root / "output").mkdir(parents=True)
    body = "\n".join(f"{i}\n00:00:0{i},000 --> 00:00:1{i},000\n{line}\n" for i, line in enumerate(captions, 1))
    (root / "output" / f"{slug}.srt").write_text(body, encoding="utf-8")
    for name, text in (extra_srts or {}).items():
        (root / "output" / name).write_text(text, encoding="utf-8")
    return root


def test_a_script_that_matches_its_own_captions_raises_nothing(tmp_path):
    root = make_project(tmp_path, "short_x", ["You open forty tabs, and your brain pays for every one of them.",
                                                   "That is the attention tax."])
    assert caption_fidelity_issues(root, SCENES) == []


def test_an_edit_made_after_the_render_is_caught_and_names_the_words(tmp_path):
    root = make_project(tmp_path, "short_x", ["You open forty tabs, and your brain pays for every one of them.",
                                                   "That is the attention tax."])
    edited = [{"text": "You open fifty tabs, and your brain pays for every one of them."},
              {"text": "That is the attention tax."}]
    issues = caption_fidelity_issues(root, edited)
    assert len(issues) == 1, issues
    assert "Caption fidelity" in issues[0] and "Re-render" in issues[0]
    # the message has to point at the words, not just accuse the file
    assert "fifty" in issues[0] and "forty" in issues[0]


def test_a_statistic_changed_after_the_render_is_caught_not_blinded(tmp_path):
    """Numbers are compared, not skipped: a one-digit change to a published stat is the edit that
    matters most on this channel, and dropping bare numerals would have hidden it."""
    root = make_project(tmp_path, "short_x", ["You open 50 tabs, and your brain pays for every one of them.",
                                                   "That is the attention tax."])
    issues = caption_fidelity_issues(root, SCENES)
    assert len(issues) == 1, issues
    assert "forty" in issues[0] and "50" in issues[0]


def test_emphasis_markers_and_case_do_not_break_fidelity(tmp_path):
    root = make_project(tmp_path, "short_x", ["YOU OPEN FORTY TABS, AND YOUR BRAIN PAYS FOR EVERY ONE OF THEM.",
                                                   "THAT IS THE ATTENTION TAX."])
    marked = [{"text": "You open *forty* tabs, and your brain pays for *every* one of them."},
              {"text": "That is the *attention* tax."}]
    assert caption_fidelity_issues(root, marked) == []
    assert _spoken_tokens("You open *forty* tabs") == ["you", "open", "forty", "tabs"]


def test_a_project_that_has_never_been_rendered_is_not_declared_faithful(tmp_path):
    """No captions means no evidence. Silence here is a pass, so the wording of the result matters
    to whoever reads the gate - it must not be able to claim the script was checked."""
    root = tmp_path / "short_unbuilt"
    (root / "output").mkdir(parents=True)
    assert _shipped_captions(root) is None
    assert caption_fidelity_issues(root, SCENES) == []


def test_the_canonical_caption_wins_over_a_stale_duplicate(tmp_path):
    # The channel keeps old exports beside the current one (short_8/short_9 each have a duplicate
    # MP4 under a different name). Picking the wrong sidecar would either bury a real divergence or
    # invent one, so the ranking is: the stem that matches the folder, then a caption with an MP4
    # beside it, then the biggest file.
    root = make_project(tmp_path, "short_x", ["You open forty tabs, and your brain pays for every one of them.",
                                                   "That is the attention tax."])
    (root / "output" / "preview_old.srt").write_text(
        "1\n00:00:00,000 --> 00:00:05,000\nYou open ninety tabs and your brain pays for every one of them that is tax\n",
        encoding="utf-8",
    )
    assert _shipped_captions(root).name == "short_x.srt"
    assert caption_fidelity_issues(root, SCENES) == []

    # with no canonical caption on disk, a caption that has a video beside it outranks an orphan,
    # even a bigger one - an orphan .srt is not evidence of what the shipped MP4 said
    (root / "output" / "short_x.srt").unlink()
    (root / "output" / "preview_old.mp4").write_bytes(b"\x00" * 2048)
    (root / "output" / "tiny_matching.srt").write_text(
        "1\n00:00:00,000 --> 00:00:05,000\nYou open forty tabs and your brain pays for every one of them\n",
        encoding="utf-8",
    )
    assert _shipped_captions(root).name == "preview_old.srt"
    assert caption_fidelity_issues(root, SCENES), "the check must disagree when it reads the stale caption"


def test_the_threshold_sits_where_the_constant_says_it_does(tmp_path):
    words = [f"word{i}" for i in range(120)]
    script = " ".join(words)
    scenes = [{"text": script}]

    # three substitutions out of 120 words lands under FIDELITY_MIN and has to warn
    spoken = list(words)
    wanted = int((1 - FIDELITY_MIN) * len(words)) + 1
    for i in range(wanted):
        spoken[i] = f"changed{i}"
    root = make_project(tmp_path, "short_x", [" ".join(spoken)])
    assert caption_fidelity_issues(root, scenes), "a divergence this large should not pass"

    # one substitution out of 120 is normalisation noise and must not
    near_match = list(words)
    near_match[0] = "changed0"
    root2 = make_project(tmp_path, "short_y", [" ".join(near_match)])
    assert caption_fidelity_issues(root2, scenes) == []


# --------------------------------------------------------------------------- #
# the live corpus
# --------------------------------------------------------------------------- #
@pytest.mark.contract
def test_the_rebuild_queue_is_exactly_the_scripts_that_were_edited():
    """Every project.json on disk must either match its shipped captions or be on this list.

    The channel's scripts were rewritten on 2026-10-31 - six hooks cleared the WORKABLE gate and
    sixteen Shorts gained the closing ask GEMINI.md section 2 requires. The MP4s beside them still
    speak the old words, so project.json no longer describes the video that was rendered, which is
    precisely what this check exists to make loud. Each row leaves the queue when that project is
    re-rendered; a project joining it without a rebuild behind it fails the suite.

    Editing this list is how a desync gets blessed, so it names slugs, not counts.
    """
    import json

    REBUILD_QUEUE = {
        "short_01_doorway_effect", "short_02_attention_residue", "short_03_bedtime_procrastination",
        "short_04_nyc_architecture", "short_05_gruen_effect", "short_06_waiting_mode",
        "short_07_zeigarnik_effect", "short_08_spotlight_effect", "short_09_decision_fatigue",
        "short_10_phantom_vibration", "short_11_bystander_effect", "short_12_parkinsons_law",
        "short_14_paradox_of_choice", "short_15_loss_aversion",
    }

    offenders, unjudged = [], []
    for path in sorted(REPO_ROOT.glob("shorts/*/project.json")) + sorted(REPO_ROOT.glob("long_form/*/project.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        issues = caption_fidelity_issues(path.parent, data.get("scenes") or [])
        if issues:
            offenders.append(f"{path.parent.name}: {issues[0]}")
        elif _shipped_captions(path.parent) is None:
            unjudged.append(f"{path.parent.name}: no captions on disk (never rendered)")
    names = {o.split(":", 1)[0].strip() for o in offenders}
    honesty_report("scripts awaiting a rebuild (project.json now speaks words the MP4 never said)",
                   sorted(names))
    honesty_report("projects the fidelity check cannot judge because they were never rendered", unjudged)
    new = sorted(names - REBUILD_QUEUE)
    assert not new, f"{new} diverged from its render without being on the rebuild queue: re-render it."
    assert not unjudged or len(unjudged) <= 3, f"more projects lost their captions than the 3 recorded: {unjudged}"
