"""tests/test_creative_engine.py - tools/creative_engine.py, the blueprint generator.

GEMINI.md section 1 is the rule this file exists to hold: every spoken sentence must trace back to
a real dossier field in channel_assets/scientific_dossiers.json, and a topic with no verified study
must stop the pipeline instead of receiving an invented one.

Unknown topics and missing narration fields must raise MissingDossier before generating
artifacts. Degenerate percentages are excluded from title claims.

Nothing here renders, uploads or touches the network. generate_creative_project() is only ever run
against a monkeypatched YT_ROOT inside pytest's tmp_path, so no test writes into shorts/.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy

import pytest

from conftest import report as honesty_report
from tools import creative_engine as ce
from tools.schemas import PROJECT_SCHEMA_VERSION, validate_project
from tools.youtube_skills import hookscore

# Every field choreograph_scenes() and the upload kit read to build spoken sentences. A dossier
# without one of these is not a dossier; it is a prompt to invent.
GROUNDING_FIELDS = (
    "topic",
    "year",
    "publication",
    "primary_researchers",
    "institution",
    "quantitative_stat",
    "best_hook",
    "broken_assumption",
    "comparison_text",
    "biological_mechanism",
    "real_world_tax",
    "willpower_trap",
    "five_second_override",
    "loop_bridge",
)

VERBATIM_FALLBACK_CLAIMS = (
    "Dopamine and amygdala circuits become locked in conflict.",
    "You stay in dead loops for hours.",
    "Fighting it with willpower doubles cortisol stress.",
    "Pause and take one physical reset action.",
    "Because the moment you let this loop repeat...",
    "a dramatic collapse in objective reasoning",
)

MINIMAL_DOSSIER = {
    "topic": "Test Topic",
    "year": "1999",
    "quantitative_stat": "2.4x Asymmetry",
    "best_hook": "Why does *your* brain do this in 1999 Oxford trials?",
}


# --------------------------------------------------------------------------- #
# topic keys and dossier loading
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Loss Aversion", "loss_aversion"),
        ("  The Paradox of Choice  ", "the_paradox_of_choice"),
        ("Dopamine!! Exhaustion?", "dopamine_exhaustion"),
        ("snake_case_already", "snake_case_already"),
        ("UPPER 123 lower", "upper_123_lower"),
        ("---", ""),
    ],
)
def test_normalize_topic_key_is_the_single_canonical_form(raw, expected):
    assert ce.normalize_topic_key(raw) == expected


def test_every_dossier_is_reachable_by_its_own_topic_string():
    dossiers = ce.load_dossiers()
    for key, dossier in dossiers.items():
        assert ce.synthesize_dossier(dossier["topic"])["topic"] == dossier["topic"], key


def test_dossier_keys_should_be_the_normalized_form_of_their_own_topic():
    # Dossier map keys are the canonical normalized form of their stored topic.
    offenders = []
    for key, dossier in ce.load_dossiers().items():
        expected = ce.normalize_topic_key(str(dossier.get("topic", "")))
        if expected != key:
            offenders.append(f"{key:20} stored under a key that is not normalize({dossier['topic']!r}) = {expected}")
    honesty_report("dossier keys that differ from their normalized topic", offenders)
    assert not offenders, offenders


def test_simulation_argument_narration_fits_the_short_word_band():
    scenes = ce.choreograph_scenes(ce.synthesize_dossier("The Simulation Argument"))
    words = len(re.findall(r"\b\w+\b", " ".join(scene["text"] for scene in scenes)))
    assert 105 <= words <= 155, f"generated simulation narration has {words} words"


def test_load_dossiers_returns_a_dict_even_when_the_file_is_unreadable(monkeypatch, tmp_path):
    monkeypatch.setattr(ce, "DOSSIERS_PATH", tmp_path / "absent.json")
    assert ce.load_dossiers() == {}
    broken = tmp_path / "broken.json"
    broken.write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr(ce, "DOSSIERS_PATH", broken)
    assert ce.load_dossiers() == {}, "a corrupt dossier file must not crash, but must not invent either"
    broken.write_text('[{"topic": "not a keyed dossier map"}]', encoding="utf-8")
    assert ce.load_dossiers() == {}, "a JSON array is not the dossier mapping contract"


def test_shipped_dossiers_carry_every_field_a_spoken_sentence_is_built_from():
    # Every field used by the scene generator must come from the dossier.
    incomplete = []
    for key, dossier in ce.load_dossiers().items():
        missing = [f for f in GROUNDING_FIELDS if not str(dossier.get(f) or "").strip()]
        if missing:
            incomplete.append(f"{key}: missing {', '.join(missing)}")
    honesty_report("dossiers missing a grounding field (generation will stop)", incomplete)
    assert not incomplete, incomplete


@pytest.mark.parametrize("claim", VERBATIM_FALLBACK_CLAIMS)
def test_no_fallback_claim_is_hidden_inside_a_real_dossier(claim):
    """The invented sentences at :379-386 must not also be smuggled into the shipped data.

    If one of these strings ever appears in a dossier, the fallback and the "verified" text become
    indistinguishable and the grounding check stops meaning anything.
    """
    blob = ce.DOSSIERS_PATH.read_text(encoding="utf-8")
    assert claim not in blob


# --------------------------------------------------------------------------- #
# synthesize_dossier: GEMINI.md section 1
# --------------------------------------------------------------------------- #
def test_a_topic_on_file_resolves_to_its_own_verified_dossier():
    # load_dossiers() re-parses the JSON on every call, so compare content, never identity.
    for key, dossier in ce.load_dossiers().items():
        assert ce.synthesize_dossier(dossier["topic"]) == dossier
        assert ce.synthesize_dossier(key) == dossier


def test_a_topic_not_on_file_raises_instead_of_inventing_a_study():
    # GEMINI.md section 1. This is the assertion the user said they would flip once the fabrication
    # was repaired - it is the repaired behaviour, so it is a plain hard assert now.
    # Fixture moved off "Ego Depletion" on 2026-11-03: SH-18 gave that topic a verified dossier, so
    # it is no longer an example of a topic with nothing on file. Von Restorff is real and absent.
    with pytest.raises(ce.MissingDossier) as excinfo:
        ce.synthesize_dossier("The Von Restorff Effect")
    message = str(excinfo.value)
    assert "No verified study on file" in message
    assert "scientific_dossiers.json" in message
    for fabricated in ("Stanford", "Princeton", "1984", "3.1x", "Cognitive Psychology Research Consortium"):
        assert fabricated not in message, f"the refusal itself is still reciting the invented study: {fabricated}"


def test_a_blank_or_punctuation_only_topic_is_refused_rather_than_matched():
    # Fixed 2026-11-01. The fuzzy matcher used to test `norm in k`, and "" is a substring of every
    # dossier key, so a blank topic (also "   ", "!!!", or anything normalize_topic_key() empties)
    # silently returned whichever entry the JSON file lists first - Loss Aversion / Kahneman &
    # Tversky, 1979 - and downstream became a project.json plus an UPLOAD_KIT citing a study nobody
    # asked for. A topic that names nothing is now an error, not a default.
    for blank in ("", "   ", "!!!", "   ...  "):
        with pytest.raises(ce.MissingDossier) as excinfo:
            ce.synthesize_dossier(blank)
        assert "names no topic at all" in str(excinfo.value), blank


@pytest.mark.parametrize("topic", ["choice", "paradox of choice", "The Paradox of Choice (full version)"])
def test_fuzzy_matching_resolves_a_related_topic_to_the_one_study_it_describes(topic):
    assert ce.synthesize_dossier(topic)["topic"] == "The Paradox of Choice"


def test_ambiguous_partial_topic_never_selects_the_first_study(monkeypatch):
    monkeypatch.setattr(ce, "load_dossiers", lambda: {
        "choice_one": {"topic": "Choice One"},
        "choice_two": {"topic": "Choice Two"},
    })

    with pytest.raises(ce.MissingDossier, match="Multiple dossiers match"):
        ce.synthesize_dossier("choice")


def test_a_partially_filled_dossier_is_refused_naming_the_missing_field():
    with pytest.raises(ce.MissingDossier) as excinfo:
        ce._require_field({"topic": "X"}, "year", "X")
    assert "missing 'year'" in str(excinfo.value)
    assert "Fill it in" in str(excinfo.value)
    assert ce._require_field({"year": " 1979 "}, "year", "X") == "1979"
    with pytest.raises(ce.MissingDossier):
        ce._require_field({"year": "   "}, "year", "X")
    with pytest.raises(ce.MissingDossier):
        ce._require_field({"year": None}, "year", "X")


# --------------------------------------------------------------------------- #
# numbers that are safe to say out loud
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "stat, expected",
    [
        ("31% vs 3%", "31%"),
        ("  42 % ", "42%"),
        ("2.4x Asymmetry", ""),
        ("Baseline Reset", ""),
        ("8 million viewers", ""),
        ("3 Horns, 1 Choice", ""),
        ("", ""),
        (None, ""),
    ],
)
def test_percent_stat_only_yields_a_number_that_really_is_a_percentage(stat, expected):
    # creative_engine.py:114-121. A ratio like "2.4x" must not be printed as "Why 2.4% of People...".
    assert ce._percent_stat(stat) == expected


@pytest.mark.parametrize("stat", ["0% of participants froze", "100% of participants froze"])
def test_degenerate_percentages_do_not_become_title_claims(stat):
    assert ce._percent_stat(stat) == ""
    titles = ce.generate_title_suite("Loss Aversion", year="1979", stat=stat)
    assert not any(re.search(r"Why (0|100)% of People", t["title"]) for t in titles)


# --------------------------------------------------------------------------- #
# title suite
# --------------------------------------------------------------------------- #
def test_title_suite_keeps_every_angle_a_real_dossier_supports():
    titles = ce.generate_title_suite("Loss Aversion", year="1979", stat="31% vs 3%")
    assert len(titles) == 5
    for t in titles:
        assert set(t) == {"angle", "title", "notes"}
        assert t["title"].strip() == t["title"]
        assert len(t["title"]) <= 60, f"GEMINI.md desktop truncation: {t['title']}"
        assert "None" not in t["title"] and "{" not in t["title"]
    angles = [t["angle"] for t in titles]
    assert len(set(angles)) == 5


def test_title_suite_drops_the_percentage_angle_when_the_stat_is_a_ratio():
    # The published failure mode: "Why 3.1x of People Freeze". The angle must disappear, not degrade.
    titles = ce.generate_title_suite("Loss Aversion", year="1979", stat="2.4x Asymmetry")
    assert len(titles) == 4
    assert not any("%" in t["title"] for t in titles)
    assert not any("Curiosity Paradox" in t["angle"] for t in titles)


def test_title_suite_drops_the_year_angles_when_the_dossier_has_no_year():
    titles = ce.generate_title_suite("Loss Aversion", year="", stat="31% vs 3%")
    assert len(titles) == 3
    assert not any("1979" in t["title"] or "Study On Why You Freeze" in t["title"] for t in titles)


def test_title_suite_refuses_to_title_a_study_less_topic():
    with pytest.raises(ce.MissingDossier):
        ce.generate_title_suite("Loss Aversion", year="", stat="Baseline Reset")


# --------------------------------------------------------------------------- #
# choreography
# --------------------------------------------------------------------------- #
def test_choreograph_builds_eight_scenes_each_with_its_own_picture_and_movement():
    dossier = ce.synthesize_dossier("Loss Aversion")
    scenes = ce.choreograph_scenes(dossier)
    assert len(scenes) == 8, "GEMINI.md section 4: 8-12 scenes, one beat per sentence"
    seen_paths = set()
    for index, scene in enumerate(scenes, 1):
        text = str(scene.get("text") or "")
        assert text.strip(), f"scene {index} has nothing to say"
        assert text != "None"
        assert scene.get("image") or scene.get("video"), f"scene {index} has no visual reference"
        assert scene.get("motion") or scene.get("preset"), f"scene {index} has no camera move"
        stem = f"s{index:02d}"
        assert stem in str(scene.get("image", "")) + str(scene.get("video", "")), (
            f"scene {index} does not reference its own s{index:02d} asset"
        )
        seen_paths.add(str(scene.get("image")))
    assert len(seen_paths) == 8, "two scenes were pointed at the same still"


def test_scene_one_is_the_dossier_hook_verbatim_and_earns_the_pass_mark():
    for key, dossier in ce.load_dossiers().items():
        scene = ce.choreograph_scenes(dossier)[0]
        assert scene["text"] == dossier["best_hook"]
        score, band_label, weakest = ce.score_hook_candidate(scene["text"])
        assert band_label == hookscore.band(score)
        assert score >= hookscore.STRONG_MIN, f"{key} hook scores {score}, under the repo pass mark"
        assert weakest in {name for name, _ in hookscore.PROPS}


def test_hook_formula_labels_do_not_duplicate_the_live_hook_score():
    """The scorer owns scores; dossier labels should describe the formula only."""
    for key, dossier in ce.load_dossiers().items():
        label = str(dossier.get("hook_formula", ""))
        assert label, f"{key} needs a formula label"
        assert not re.search(r"\bScore\s+\d+\b", label, re.IGNORECASE), f"{key} duplicates a computed score"


def test_choreographed_scripts_land_in_the_short_word_band():
    # GEMINI.md section 2: a short is 105-155 words. The generator's own output is what gets read
    # back to us, so measure it the way generate_creative_project() counts it (:505 regex words).
    offenders = []
    for key, dossier in ce.load_dossiers().items():
        scenes = ce.choreograph_scenes(dossier)
        words = len(re.findall(r"\b\w+\b", " ".join(s["text"] for s in scenes)))
        if not 105 <= words <= 155:
            offenders.append(f"{key:22} {words} words (GEMINI.md wants 105-155)")
    honesty_report("shipped dossiers whose generated script leaves the 105-155 word band", offenders)
    assert len(offenders) < len(ce.load_dossiers()), "every dossier off-band means the generator broke, not the data"


def test_a_short_dossier_should_raise_rather_than_invent_neuroscience():
    with pytest.raises(ce.MissingDossier):
        ce.choreograph_scenes(dict(MINIMAL_DOSSIER))


@pytest.mark.parametrize("field", GROUNDING_FIELDS)
@pytest.mark.parametrize("value", [None, "", "   "])
def test_every_missing_grounding_field_stops_scene_generation(field, value):
    dossier = dict(ce.synthesize_dossier("Loss Aversion"))
    dossier[field] = value
    with pytest.raises(ce.MissingDossier, match=f"missing '{field}'"):
        ce.choreograph_scenes(dossier)


def test_incomplete_dossier_stops_before_creating_project_files(tmp_path):
    with pytest.raises(ce.MissingDossier):
        ce.generate_creative_project(
            "Test Topic", "SH-99", "short_probe", output_root=tmp_path, dossier=dict(MINIMAL_DOSSIER)
        )
    assert not (tmp_path / "short_probe").exists()


# --------------------------------------------------------------------------- #
# upload kit
# --------------------------------------------------------------------------- #
def _kit(**overrides):
    args = dict(
        video_id="SH-99",
        title="Loss Aversion: The 1979 Study On Why You Freeze",
        topic="Loss Aversion",
        citation="Daniel Kahneman & Amos Tversky (1979)",
        year="1979",
        stat="2.4x Asymmetry",
    )
    args.update(overrides)
    return ce.generate_upload_kit_content(**args)


def test_upload_kit_is_deterministic_and_carries_no_unfilled_slots():
    first, second = _kit(), _kit()
    assert first == second
    assert not re.search(r"\{[a-z_]+\}", first), "a raw format slot survived into the kit"
    for token in ("None", "TODO", "TBD", "XXX", "PLACEHOLDER", "<", "lorem"):
        assert token not in first, f"{token} found in a kit meant to be copied into YouTube Studio"


def test_upload_kit_writes_the_shorts_hashtag_in_lowercase_only():
    # GEMINI.md section 5: lowercase #shorts. The kit is copy-pasted into Studio verbatim.
    kit = _kit(title="Loss Aversion #Shorts")
    assert "#shorts" in kit
    assert "#Shorts" not in kit and "#SHORTS" not in kit


def test_upload_kit_tag_block_is_all_lowercase():
    # GEMINI.md section 5: tags lowercase. Take only the fenced block after the section-5 heading.
    kit = _kit()
    section = kit.split("## 5. Defensive Search Tags", 1)[-1]
    match = re.search(r"```(?:text)?\n(.*?)```", section, re.DOTALL)
    assert match, "section 5 must hand Studio a fenced, copy-pasteable tag block"
    tags = [t.strip() for t in match.group(1).strip().split(",")]
    assert len(tags) >= 8
    for tag in tags:
        assert tag, "empty tag entry"
        assert tag == tag.lower(), f"uppercase tag {tag!r} in the lowercase-only block"
        assert not tag.startswith("#"), f"{tag!r} belongs in the description hashtag line, not the tag field"
        assert "\n" not in tag


def test_upload_kit_tag_block_stays_inside_youtubes_own_limits():
    # YouTube splits the tag box on commas and caps one tag at 30 characters, then drops the
    # overflow without telling the uploader. SH-17's kit put the full citation in the block and
    # was about to ship fragments of 39 and 45 characters; the string came out of this generator,
    # so the generator is where it has to be fixed. See tests/test_creative_engine.py::_kit.
    brickman = "Philip Brickman, Dan Coates & Ronnie Janoff-Bulman (1978)"
    expected = {_kit(citation="Daniel Kahneman & Amos Tversky (1979)"): "kahneman tversky 1979",
                _kit(citation=brickman): "brickman coates 1978"}
    for kit, citation_tag in expected.items():
        section = kit.split("## 5. Defensive Search Tags", 1)[-1]
        match = re.search(r"```(?:text)?\n(.*?)```", section, re.DOTALL)
        tags = [t.strip() for t in match.group(1).strip().split(",")]
        assert len(tags) >= 8, "a dropped tag must not quietly shrink the block"
        for tag in tags:
            assert 3 <= len(tag) <= 30, f"{tag!r} is {len(tag)} characters; YouTube drops it"
        assert citation_tag in tags, tags


def test_upload_kit_description_links_a_reachable_video():
    # The description block is pasted into Studio verbatim. Two lines used to ship in it that
    # pointed at nothing: "tap the Related Video button right above the title" (a Studio-only
    # field the API can neither read nor set, so it is empty until someone sets it by hand) and
    # "check the bio link … for our complete Focus Architecture OS" (the channel has no channel
    # links at all — channels.list returns channelLinks: []). Both reach every Short.
    kit = _kit()
    block = kit.split("## 2. Humanized Description", 1)[1].split("## 3.")[0]
    for dead in ("Related Video", "bio link", "Focus Architecture OS"):
        assert dead not in block, f"{dead!r} in a description the viewer cannot act on"
    assert "https://youtu.be/" in block and "https://www.youtube.com/@CognitiveCoreOfficial" in block


def test_upload_kit_related_video_never_invents_a_title():
    kit = _kit(related_target="LV-01", related_target_title="Dopamine Exhaustion")
    assert "LV-01" in kit and "Dopamine Exhaustion" in kit
    # With no explicit target the resolver picks one of the two long-form anchors: it is a hardcoded
    # string, not a lookup, so at minimum it must not say "None".
    fallback = _kit(related_target=None, related_target_title=None)
    assert "None" not in fallback


@pytest.mark.parametrize(
    "topic, expected_target",
    [
        ("Dopamine Exhaustion and scrolling", "LV-01"),
        ("Phone burnout", "LV-01"),
        ("Loss Aversion", "LV-02"),
        ("The Paradox of Choice", "LV-02"),
    ],
)
def test_related_target_resolution_follows_the_documented_clusters(topic, expected_target):
    assert ce.resolve_related_target(topic)[0] == expected_target


# --------------------------------------------------------------------------- #
# end to end blueprint synthesis (tmp only - never writes into shorts/)
# --------------------------------------------------------------------------- #
@pytest.fixture
def repo_shaped_tmp(tmp_path, monkeypatch):
    """Keep generated projects inside a temporary repository."""
    monkeypatch.setattr(ce, "YT_ROOT", tmp_path)
    return tmp_path


def test_generate_creative_project_writes_a_blueprint_built_only_from_the_dossier(repo_shaped_tmp, capsys):
    path = ce.generate_creative_project(
        "Loss Aversion", "SH-99", "short_99_probe", output_root=repo_shaped_tmp / "shorts"
    )
    project = json.loads(path.read_text(encoding="utf-8"))
    scenes = project["scenes"]

    assert validate_project(project, project_path=path) == []
    assert project["schema_version"] == PROJECT_SCHEMA_VERSION == 2
    assert project["id"] == "SH-99" and project["format"] == "short"
    assert project["variant"] == "cinematic_35mm"
    assert project["channel_id"] == "UC6hwVBnsfvfUGxfZi2sFT3A"
    assert project["voice"] == "kokoro"
    assert project["title"] == "Loss Aversion - SH-99"
    assert project["science"] == "Daniel Kahneman & Amos Tversky (1979)"
    assert len(scenes) == 8
    for index, scene in enumerate(scenes, 1):
        assert scene["id"] == f"s{index:02d}"
        assert scene["caption"] == scene["text"]
        assert str(scene.get("image") or "") or str(scene.get("video") or "")
        assert str(scene.get("text") or "").strip() not in ("", "None")
    blob = json.dumps(project)
    assert "None" not in blob and "{" not in blob.replace('{"', "").replace('"}', "")

    # GEMINI.md section 3, the audio recipe, verbatim into project.json.
    assert project["rate"] == "+1%"
    assert project["pitch"] == "-2Hz"
    assert project["gap"] == 0.08
    assert project["music"]["volume"] == 0.18
    assert project["music"]["sfx_volume"] == 0.12

    words = len(re.findall(r"\b\w+\b", " ".join(s["text"] for s in scenes)))
    assert project["metadata"]["word_count"] == words
    assert project["metadata"]["estimated_duration_sec"] == round(words / 150 * 60, 1)

    kit = (path.parent / "UPLOAD_KIT_SH99.md").read_text(encoding="utf-8")
    assert "Daniel Kahneman & Amos Tversky" in kit
    assert "#shorts" in kit and "#Shorts" not in kit
    card = capsys.readouterr().out
    assert "SH-99" in card, "the creation card is the only confirmation the agent prints"


def test_generate_creative_project_preserves_supplied_scenes_and_identity(repo_shaped_tmp, monkeypatch):
    scenes = ce.choreograph_scenes(ce.synthesize_dossier("Loss Aversion"))
    scenes[0].update({
        "id": "opening",
        "caption": "Authored caption, distinct from narration.",
        "pose": {"sprite": "images/aversion_pose.png", "x": 0.4},
        "clue": {"answer": "loss aversion", "reveal_at": 1.5},
        "overlay": {"image": "images/aversion_overlay.png", "text": "Keep this overlay", "until": 2.6},
        "audio": "audio/opening.wav",
        "sound_cues": [{"asset": "audio/aversion.wav", "at": 0.5}],
        "images": ["images/aversion_detail.png"],
    })
    original = deepcopy(scenes)
    monkeypatch.setattr(ce, "choreograph_scenes", lambda *args, **kwargs: pytest.fail("supplied scenes rechoreographed"))

    path = ce.generate_creative_project(
        "Loss Aversion", "SH-99", "short_supplied", scenes=scenes,
        variant="photobook", channel_id="test_channel", voice="af_heart",
    )
    project = json.loads(path.read_text(encoding="utf-8"))

    assert validate_project(project, project_path=path) == []
    assert project["variant"] == "photobook"
    assert project["channel_id"] == "test_channel"
    assert project["voice"] == "af_heart"
    assert scenes == original
    for index, (authored, generated) in enumerate(zip(original, project["scenes"], strict=True), 1):
        expected = {"id": f"s{index:02d}", "caption": authored["text"], **authored}
        assert generated == expected


@pytest.mark.parametrize("scenes", [[], {}, "not a scene list", False, (), [None] * 8, ["not an object"] * 8, [{}]])
def test_invalid_scene_containers_fail_before_artifacts(repo_shaped_tmp, monkeypatch, scenes):
    for name in ("choreograph_scenes", "score_hook_candidate"):
        monkeypatch.setattr(ce, name, lambda *args, **kwargs: pytest.fail("invalid scenes reached choreography or scoring"))

    with pytest.raises(ValueError, match="scenes"):
        ce.generate_creative_project("Loss Aversion", "SH-99", "short_invalid", scenes=scenes)

    assert not (repo_shaped_tmp / "shorts").exists()


@pytest.mark.parametrize(
    "invalid_scene, field",
    [
        ({}, "text"),
        ({"text": None}, "text"),
        ({"text": ""}, "text"),
        ({"text": " \t"}, "text"),
        ({"text": 42}, "text"),
        ({"text": "Hook", "caption": ""}, "caption"),
        ({"text": "Hook", "caption": None}, "caption"),
        ({"text": "Hook", "id": "s02"}, "id"),
        ({"text": "Hook", "id": None}, "id"),
        ({"text": "Hook", "prompt": ""}, "prompt"),
        ({"text": "Hook", "image": "../escape.png"}, "image"),
        ({"text": "Hook", "overlay": {"image": "../escape.png"}}, "overlay"),
    ],
)
def test_invalid_scene_fields_fail_before_artifacts(repo_shaped_tmp, monkeypatch, invalid_scene, field):
    scenes = [{"text": "Loss aversion narration.", "prompt": "Loss aversion visual."} for _ in range(8)]
    scenes[0] = {"prompt": "Loss aversion visual.", **invalid_scene}
    original = deepcopy(scenes)
    for name in ("choreograph_scenes", "score_hook_candidate"):
        monkeypatch.setattr(ce, name, lambda *args, **kwargs: pytest.fail("invalid scenes reached choreography or scoring"))

    with pytest.raises(ValueError, match=rf"\.{field}"):
        ce.generate_creative_project("Loss Aversion", "SH-99", "short_invalid", scenes=scenes)

    assert scenes == original
    assert not (repo_shaped_tmp / "shorts").exists()


@pytest.mark.parametrize(
    "options",
    [
        {"voice": "unknown_voice"},
        {"variant": "3d_cgi"},
        {"channel_id": "invalid/channel"},
        {"voice": "unknown_voice", "variant": "3d_cgi", "channel_id": "invalid/channel"},
    ],
)
def test_invalid_project_identity_fails_before_artifacts(repo_shaped_tmp, monkeypatch, options):
    scenes = [{"text": "Loss aversion narration.", "prompt": "Loss aversion visual."} for _ in range(8)]
    monkeypatch.setattr(ce, "score_hook_candidate", lambda *args, **kwargs: pytest.fail("invalid project reached scoring"))

    with pytest.raises(ValueError) as exc:
        ce.generate_creative_project("Loss Aversion", "SH-99", "short_invalid", scenes=scenes, **options)

    assert len(str(exc.value).splitlines()) == len(options)
    for field in options:
        assert field in str(exc.value)
    assert not (repo_shaped_tmp / "shorts").exists()


def test_generate_creative_project_supplies_a_dossier_it_was_given(repo_shaped_tmp, capsys):
    dossier = dict(ce.synthesize_dossier("The Hedonic Treadmill"))
    path = ce.generate_creative_project(
        "ignored topic", "SH-98", "short_98_probe", output_root=repo_shaped_tmp / "shorts", dossier=dossier
    )
    project = json.loads(path.read_text(encoding="utf-8"))
    assert project["concept"] == "The Hedonic Treadmill"
    assert "Philip Brickman" in project["science"]


def test_an_unknown_topic_stops_before_writing_anything(repo_shaped_tmp, capsys):
    # GEMINI.md section 1 end to end: no project.json, no UPLOAD_KIT, nothing to build.
    with pytest.raises(ce.MissingDossier):
        ce.generate_creative_project("The Von Restorff Effect", "SH-97", "short_97_probe", output_root=repo_shaped_tmp / "shorts")
    assert not (repo_shaped_tmp / "shorts" / "short_97_probe" / "project.json").exists()


def test_an_output_root_outside_the_repo_should_still_produce_a_project(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ce, "YT_ROOT", tmp_path / "repo")
    (tmp_path / "repo").mkdir()
    scratch = tmp_path / "scratch"
    path = ce.generate_creative_project(
        "Loss Aversion", "SH-95", "short_95_probe", output_root=scratch / "shorts"
    )
    assert path.exists()
    assert (path.parent / "UPLOAD_KIT_SH95.md").exists()
    assert str(path.resolve()) in capsys.readouterr().out


def test_score_hook_candidate_reports_the_same_number_as_the_scorer_it_wraps():
    hook = "If you collapse on a *Manhattan* sidewalk, why do *eighty-five* *percent* of strangers stop and watch?"
    parts, verdict, name, _ = hookscore.score(hook)
    score, band_label, weakest = ce.score_hook_candidate(hook)
    assert score == verdict
    assert band_label == hookscore.band(verdict)
    assert weakest == min(parts, key=parts.get)
    assert name != "Unclassified"
    assert isinstance(res := ce.youtube_skills.score_hook(hook), dict) and res["verdict"] == verdict


def test_project_collision_preserves_original_project_and_upload_kit(repo_shaped_tmp):
    path = ce.generate_creative_project("Loss Aversion", "SH-99", "short_collision")
    assert json.loads(path.read_text())["schema_version"] == PROJECT_SCHEMA_VERSION
    original = {item.name: item.read_bytes() for item in path.parent.glob("*") if item.is_file()}

    with pytest.raises(FileExistsError, match=str(path)):
        ce.generate_creative_project("Unknown replacement topic", "SH-98", "short_collision")

    assert {item.name: item.read_bytes() for item in path.parent.glob("*") if item.is_file()} == original


def test_project_collision_allows_explicit_overwrite(repo_shaped_tmp):
    path = ce.generate_creative_project("Loss Aversion", "SH-99", "short_collision")
    replacement = ce.generate_creative_project("Loss Aversion", "SH-98", "short_collision", overwrite=True)
    assert replacement == path
    assert json.loads(path.read_text())["id"] == "SH-98"


def test_project_worker_collision_is_non_retryable_and_names_conflicting_path(repo_shaped_tmp):
    from types import SimpleNamespace

    from tools.orchestrator.contracts import TaskSpec
    from tools.orchestrator.workers import ProjectWorker

    path = ce.generate_creative_project("Loss Aversion", "SH-99", "short_collision")
    original = path.read_bytes()
    dossier = ce.synthesize_dossier("Loss Aversion")
    context = SimpleNamespace(root=repo_shaped_tmp, dep_data=lambda _: {"dossier": dossier})
    spec = TaskSpec("project", "project", "project", params={
        "topic": "Loss Aversion", "video_id": "SH-98", "slug": "short_collision",
    })

    result = ProjectWorker().run(spec, context)

    assert not result.ok
    assert result.retryable is False
    assert str(path) in result.error
    assert path.read_bytes() == original


def test_project_collision_during_generation_preserves_concurrent_writer(repo_shaped_tmp, monkeypatch):
    path = repo_shaped_tmp / "shorts" / "short_collision" / "project.json"
    choreograph = ce.choreograph_scenes

    def concurrent_creation(dossier, **kwargs):
        path.parent.mkdir(parents=True)
        path.write_bytes(b"concurrent reviewed project")
        return choreograph(dossier, **kwargs)

    monkeypatch.setattr(ce, "choreograph_scenes", concurrent_creation)

    with pytest.raises(FileExistsError):
        ce.generate_creative_project("Loss Aversion", "SH-99", "short_collision")

    assert path.read_bytes() == b"concurrent reviewed project"
    assert not list(path.parent.glob("UPLOAD_KIT*"))
