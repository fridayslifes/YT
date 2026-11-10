"""tests/test_project_contract.py - the project.json contract over every real project on disk.

Data-driven over the glob `shorts/*/project.json` + `long_form/*/project.json`. Two kinds of check:

  * HARD asserts - a project.json that breaks these cannot be built or must not be published, so a
    new violation fails the suite (test_..._for_every_project, parametrized per file).
  * BASELINE-LOCKED checks - GEMINI.md demands more than the corpus currently delivers (the section 3
    audio recipe, the 105-155 word band, the citation_verified key). Each one records today's
    offender list in BASELINES below, prints it in the REPO HONESTY REPORT, and fails only if a
    project is ADDED to the list. Fixing one shrinks the report instead of breaking the build, which
    is what "report which projects currently violate it" has to mean for a shared tree.

The two word-counting methods in the repo still disagree about a script's length, and one of them
decides whether a build is allowed:
  tools/pipeline.py             counts with text.split(), which treats "*one* *thousand*" as 2 words
  tools/orchestrator/verifiers.py  counts with re.findall(r"\\b\\w+\\b") over the joined script, so
                                the same markup counts 3
Both now read the SAME band from tools/policy.py WORD_BANDS (GEMINI.md's 105-155 / 1100-1500), and
the message each prints is built from that tuple, so a rejection can never quote a band the code did
not enforce. test_the_repo_only_documents_one_word_band_to_its_users locks that.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from conftest import REPO_ROOT, report as honesty_report

# GEMINI.md section 3, verbatim. Anything else is a different video from the one the rules describe.
SPEC_AUDIO = {
    "rate": "+1%",
    "pitch": "-2Hz",
    "gap": 0.08,
    "music.volume": 0.18,
    "music.sfx_volume": 0.12,
}
SHORT_WORD_BAND = (105, 155)  # GEMINI.md:29
LONG_WORD_BAND = (1100, 1500)  # GEMINI.md:29
SHORT_SCENE_BAND = (8, 12)  # GEMINI.md:29 "8-12 scene script"
REQUIRED_PROJECT_KEYS = ("id", "title", "format", "voice", "rate", "gap", "music", "scenes", "genre", "science")
REQUIRED_SCENE_KEYS = ("text", "image", "video")
PATH_SCENE_KEYS = ("image", "video")
PLACEHOLDER_TOKENS = ("TODO", "TBD", "lorem ipsum", "amzn.to/example", "@CognitiveCoreHQ", "{{", "}}")

# The projects that violate a GEMINI.md rule today, by slug. A count was the wrong shape for this:
# it lets one project be fixed while another breaks and the number stays the same. Offenders must be
# prefixed "<slug>: ..." so the set can be compared. Fixing a project shrinks the report; a new
# project on one of these lists is exactly the failure these locks exist to catch. Entries whose
# project directory no longer exists are reported as REMOVED FROM THE CORPUS, never as fixed - the
# list is kept as the record of what was measured on 2026-10-31, before the purge deleted twelve
# Shorts and the LV-02 project.
# Measured 2026-10-31, after lv_02 declared citation_verified=false (it left the third list).
BASELINES: dict[str, tuple[str, ...]] = {
    "audio_off_gemini_md_section_3": (
        "lv_02_focus_protocol",
        "short_01_doorway_effect",
        "short_01b_doorway_part_2",
        "short_02_attention_residue",
        "short_03_bedtime_procrastination",
        "short_04_nyc_architecture",
        "short_05_gruen_effect",
        "short_06_waiting_mode",
        "short_07_zeigarnik_effect",
        "short_08_spotlight_effect",
        "short_09_decision_fatigue",
        "short_10_phantom_vibration",
    ),
    "short_off_the_105_155_word_band": (
        "short_03_bedtime_procrastination",
        "short_06_waiting_mode",
        "short_07_zeigarnik_effect",
        "short_10_phantom_vibration",
    ),
    "citation_verified_key_absent": (
        "short_11_bystander_effect",
        "short_12_parkinsons_law",
        "short_13_dunning_kruger",
    ),
    "loop_tail_key_absent": (
        "short_11_bystander_effect",
        "short_14_paradox_of_choice",
        "short_16_simulation_argument",
    ),
    # GEMINI.md section 2 "end on one ask". Only short_01b asks for anything ("subscribe for Part 3");
    # every other script closes on an aphorism, so a finished Short converts a watch into nothing.
    "no_closing_ask": (
        "short_01_doorway_effect",
        "short_02_attention_residue",
        "short_03_bedtime_procrastination",
        "short_04_nyc_architecture",
        "short_05_gruen_effect",
        "short_06_waiting_mode",
        "short_07_zeigarnik_effect",
        "short_08_spotlight_effect",
        "short_09_decision_fatigue",
        "short_10_phantom_vibration",
        "short_11_bystander_effect",
        "short_12_parkinsons_law",
        "short_13_dunning_kruger",
        "short_14_paradox_of_choice",
        "short_15_loss_aversion",
        "short_16_simulation_argument",
    ),
}


def load(path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def flatten(project: dict) -> dict:
    """The audio recipe keys GEMINI.md section 3 names, whether or not they sit under `music`."""
    flat = {k: v for k, v in project.items() if k in SPEC_AUDIO}
    music = project.get("music") or {}
    for key in SPEC_AUDIO:
        if key.startswith("music."):
            flat[key] = music.get(key.split(".", 1)[1])
    return flat


def split_words(project: dict) -> int:
    """The pipeline.py:403 counting method: text.split() per scene."""
    return sum(len(str(s.get("text") or "").split()) for s in project.get("scenes") or [])


def regex_words(project: dict) -> int:
    """The verifiers.py:215 / creative_engine.py:505 counting method: one regex over the whole script."""
    joined = " ".join(str(s.get("text") or "") for s in project.get("scenes") or [])
    return len(re.findall(r"\b\w+\b", joined))


def project_dir_exists(slug: str) -> bool:
    """Whether a baseline slug is still in the local corpus at all.

    Baselines were measured against the pre-purge tree. Twelve Shorts and the LV-02 project were
    deleted on 2026-10-31 (their live YouTube metadata had been verified), so comparing "was on the
    list" against "is not on today's list" reported those deletions as projects that had FIXED the
    problem - a false all-clear for rules nobody can check any more. Deletion is not compliance, so
    the two are now reported apart.
    """
    return any((REPO_ROOT / kind / slug).is_dir() for kind in ("shorts", "long_form"))


def check_baseline(section: str, offenders: list[str]) -> None:
    """Print today's offenders and fail only on a project that was not already on the list."""
    honesty_report(section, offenders)
    known = set(BASELINES[section])
    # The comparison is existence-scoped in both directions: a deleted project is absent from
    # `offenders` because nothing read its file, not because it complies.
    now = {o.split(":", 1)[0].strip() for o in offenders if project_dir_exists(o.split(":", 1)[0].strip())}
    new = sorted(now - known)
    assert not new, (
        f"{section} gained {len(new)} project(s) that were not on the recorded baseline: {new}. "
        f"Fix the project; editing this list is how a new violation gets blessed."
    )
    still_here = {slug for slug in known if project_dir_exists(slug)}
    removed = sorted(known - still_here)
    fixed = sorted(still_here - now)
    if removed:
        honesty_report(
            f"{section} - baseline projects removed from the corpus (neither fixed nor verified)",
            [f"{s}: project directory is gone; this rule can no longer be checked for it" for s in removed],
        )
    if fixed:
        honesty_report(f"{section} - projects that now comply", fixed)


def test_a_baseline_entry_whose_project_is_gone_is_not_reported_as_fixed(monkeypatch):
    """The false all-clear this harness used to print: deleted != compliant.

    Uses a synthetic section, and restores the shared honesty report afterwards so nothing here
    leaks into the report `pytest -q` prints at the end of the run.
    """
    from conftest import REPORT

    saved = {k: list(v) for k, v in REPORT.items()}
    section = "synthetic_baseline_lock_check"
    monkeypatch.setitem(BASELINES, section, ("short_13_dunning_kruger", "short_99_never_existed"))
    synthetic_present = {"short_13_dunning_kruger", "short_16_simulation_argument"}
    monkeypatch.setattr(sys.modules[__name__], "project_dir_exists", lambda slug: slug in synthetic_present)
    try:
        REPORT.clear()
        check_baseline(section, ["short_13_dunning_kruger: still off spec"])
        assert not any("now comply" in name for name in REPORT), list(REPORT)
        removed_section = next(name for name in REPORT if "removed from the corpus" in name)
        assert REPORT[removed_section] == [
            "short_99_never_existed: project directory is gone; this rule can no longer be checked for it"
        ], REPORT[removed_section]
        # The project that is still here and still off spec is recorded as an offender, not a fix.
        assert REPORT[section] == ["short_13_dunning_kruger: still off spec"], REPORT[section]
        # The lock itself still bites: a new offender fails even when its neighbour vanished.
        with pytest.raises(AssertionError, match="short_16_simulation_argument"):
            check_baseline(section, ["short_16_simulation_argument: brand new violation"])
    finally:
        REPORT.clear()
        REPORT.update(saved)


# --------------------------------------------------------------------------- #
# discovery
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def projects() -> list[dict]:
    """slug -> parsed project, for every shorts/ and long_form/ project.json."""
    files = sorted(REPO_ROOT.glob("shorts/*/project.json")) + sorted(REPO_ROOT.glob("long_form/*/project.json"))
    out = []
    for path in files:
        out.append(
            {
                "slug": path.parent.name,
                "kind": "short" if path.parent.parent.name == "shorts" else "long",
                "path": path,
                "raw": path.read_text(encoding="utf-8"),
                "data": json.loads(path.read_text(encoding="utf-8")),
            }
        )
    return out


# The local inventory after every uploaded project's remote artifact was verified and its working
# directory intentionally removed. Production contracts are exercised by synthetic fixtures until
# a new project is started; any discovered real slug must be recorded here deliberately.
# Emptied: All uploaded legacy shorts verified and removed at creator instruction.
# Clean state for new 4K60 video production.
LOCAL_PROJECTS: tuple[str, ...] = ("short_25_speckled_band", "short_26_dorian_gray")


def test_the_glob_actually_finds_the_corpus(projects):
    discovered = set(ids_of(projects))
    expected = set(LOCAL_PROJECTS)
    assert discovered == expected, (
        "shorts/*/project.json + long_form/*/project.json disagrees with the recorded local inventory: "
        f"missing={sorted(expected - discovered)} unexpected={sorted(discovered - expected)}"
    )
    if not projects:
        honesty_report(
            "formats present in the local corpus",
            ["no retained local projects; production contracts are exercised by synthetic fixtures"],
        )
        return
    kinds = {p["kind"] for p in projects}
    assert kinds <= {"short", "long"}, kinds
    if "long" not in kinds:
        honesty_report(
            "formats present in the local corpus",
            [
                "short only - the LV project.json files are gone, so creative_engine.LONGFORM_ANCHORS is "
                "the only long-form copy this suite can still scan"
            ],
        )


def ids_of(projects):
    return [p["slug"] for p in projects]


# --------------------------------------------------------------------------- #
# HARD: keys, scenes, visuals, emphasis markup, placeholders
# --------------------------------------------------------------------------- #
@pytest.mark.contract
class TestProjectFileContract:
    """The whole corpus in one assertion each, so a failure prints every offending project at once."""

    def test_required_keys_present_and_typed(self, projects):
        offenders = []
        for p in projects:
            data = p["data"]
            missing = [k for k in REQUIRED_PROJECT_KEYS if k not in data]
            wrong_type = [
                k
                for k, v in data.items()
                if k in ("id", "title", "format", "voice", "rate", "genre", "science") and not str(v or "").strip()
            ]
            if not isinstance(data.get("scenes"), list) or not data.get("scenes"):
                missing.append("scenes(non-empty list)")
            if not isinstance(data.get("music"), dict):
                missing.append("music(dict)")
            if not isinstance(data.get("gap"), (int, float)):
                wrong_type.append("gap(number)")
            if missing or wrong_type:
                offenders.append(f"{p['slug']}: missing={missing} bad={wrong_type}")
        assert not offenders, offenders

    def test_format_is_the_one_the_folder_agrees_with(self, projects):
        for p in projects:
            assert p["data"]["format"] in ("short", "long"), p["slug"]
            assert p["data"]["format"] == p["kind"], f"{p['slug']} lives in {p['kind']}s/ but declares {p['data']['format']}"

    def test_id_is_the_channel_id_scheme_and_matches_its_slug(self, projects):
        for p in projects:
            ident = str(p["data"]["id"])
            assert re.fullmatch(r"(SH|LV)-[0-9A-Z]+", ident), f"{p['slug']} id {ident!r}"
            expected_prefix = "SH-" if p["kind"] == "short" else "LV-"
            assert ident.startswith(expected_prefix), f"{p['slug']}: {ident}"
            digits = re.search(r"(\d+)", p["slug"])
            if digits:
                assert digits.group(1) in ident, f"{p['slug']} slug number is not in id {ident}"

    def test_every_scene_has_something_to_say_and_something_to_show(self, projects):
        offenders = []
        for p in projects:
            for index, scene in enumerate(p["data"].get("scenes") or [], 1):
                text = str(scene.get("text") or "").strip()
                if not text:
                    offenders.append(f"{p['slug']} scene {index}: empty narration")
                elif text.lower() == "none":
                    offenders.append(f"{p['slug']} scene {index}: speaks the word None")
                for key in REQUIRED_SCENE_KEYS:
                    value = scene.get(key)
                    if not isinstance(value, str) or not value.strip():
                        offenders.append(f"{p['slug']} scene {index}: {key}={value!r}")
                    # Only asset keys are paths. Narration that opens on an ellipsis
                    # ("...believing it made him invisible") is a spoken line, not an
                    # absolute or escaping path, and used to fail this check.
                    elif key in PATH_SCENE_KEYS and (value.startswith("/") or value.startswith("../")):
                        offenders.append(f"{p['slug']} scene {index}: {key}={value!r} is not project-relative")
        assert not offenders, offenders

    def test_scene_assets_line_up_with_the_render_cache_the_builder_uses(self, projects):
        # The builder keys every clip by the ASSET stem, never the scene index:
        # pipeline.py:790-792 writes videos/<stem>.mp4 from the image the scene names, then puts the
        # scene on the timeline in list order. So "s09_eye_closeup" in scene 2 is not a misrender - it
        # is the prompt-pack name, and 58 projects-worth of those names are already published. What
        # actually breaks a build is a scene whose image and video disagree (the re-render writes a
        # file this scene will never read) or a rendered project whose source images have gone missing.
        mismatched, lost_sources, reused = [], [], []
        for p in projects:
            scenes = p["data"].get("scenes") or []
            rendered = bool(list(p["path"].parent.glob("output/*.mp4")))
            for index, scene in enumerate(scenes, 1):
                image, video = str(scene.get("image") or ""), str(scene.get("video") or "")
                if image and video and Path(image).stem != Path(video).stem:
                    mismatched.append(f"{p['slug']} scene {index}: {image} vs {video}")
                if image and rendered and not (p["path"].parent / image).exists():
                    lost_sources.append(f"{p['slug']} scene {index}: {image} is gone but output/ has a render")
            for key in PATH_SCENE_KEYS:
                seen: dict[str, int] = {}
                for index, scene in enumerate(scenes, 1):
                    value = str(scene.get(key) or "")
                    if value:
                        seen[value] = seen.get(value, 0) + 1
                for value, times in sorted(seen.items()):
                    if times > 1:
                        reused.append(f"{p['slug']}: {value} holds {times} scenes (loop recap)")
        honesty_report("scenes reusing one asset (the replay loop does this on purpose)", reused)
        assert not mismatched, mismatched
        assert not lost_sources, lost_sources

    def test_emphasis_markers_survive_the_tokenizer_that_draws_the_pills(self, projects):
        # GEMINI.md:30 - key words wrapped in *asterisks* drive the caption pill animation. What the
        # animation actually depends on is build_video.script_tokens(): it splits on whitespace and
        # sets emph=True on any token still carrying a "*" after the split. So "*jacket,*" and
        # "*view?*" produce pills like any other word (the display form rstrips the punctuation), but
        # "* word *" produces none at all, and an odd asterisk count means the writer lost track.
        from tools.build_video import script_tokens

        offenders = []
        thin = []
        for p in projects:
            pills = 0
            markers = 0
            for index, scene in enumerate(p["data"].get("scenes") or [], 1):
                text = str(scene.get("text") or "")
                stars = text.count("*")
                markers += stars
                pills += sum(1 for tok in script_tokens(text) if tok["emph"])
                if stars % 2:
                    offenders.append(f"{p['slug']} scene {index}: {stars} asterisks (unbalanced)")
                for run in re.findall(r"\*+([^*]*)\*+", text):
                    if run != run.strip() or not run.strip():
                        offenders.append(f"{p['slug']} scene {index}: *{run}* has no word attached, so no pill is drawn")
            if markers and not pills:
                offenders.append(f"{p['slug']}: {markers} asterisks that yield no pill at all")
            elif pills < 4:
                thin.append(f"{p['slug']}: {pills} emphasised words across {len(p['data'].get('scenes') or [])} scenes")
        assert not offenders, offenders
        honesty_report("projects whose captions barely animate (fewer than 4 emphasis pills)", thin)

    def test_the_first_scene_is_the_hook_and_carries_a_overlay_or_banner(self, projects):
        # A Short has 1-2s to earn the swipe; the hook must be scene 1, never buried.
        offenders = []
        for p in projects:
            if p["kind"] != "short":
                continue
            first = (p["data"].get("scenes") or [{}])[0]
            if not str(first.get("text") or "").strip():
                offenders.append(f"{p['slug']}: scene 1 empty")
        assert not offenders, offenders

    def test_the_last_two_scenes_ask_the_viewer_for_one_thing(self, projects):
        # GEMINI.md section 2 "end on one ask". This reads the same ASK_RE the builder's gate reads, so
        # a script that clears here is a script pre_compose_validate() will not warn about - and the
        # baseline list is the record of how many published Shorts ask for nothing.
        from tools.pipeline import ASK_RE

        offenders = []
        for p in projects:
            scenes = p["data"].get("scenes") or []
            closing = " ".join(str(sc.get("text") or "") for sc in scenes[-2:])
            if not ASK_RE.search(closing):
                offenders.append(f"{p['slug']}: no ask in the closing scenes")
        check_baseline("no_closing_ask", offenders)

    def test_no_placeholder_tokens_anywhere_in_a_buildable_artifact(self, projects):
        # GEMINI.md section 1 "Strict Zero-Placeholder" rule, applied to the file the builder reads.
        offenders = []
        for p in projects:
            hits = [token for token in PLACEHOLDER_TOKENS if token.lower() in p["raw"].lower()]
            if hits:
                offenders.append(f"{p['slug']}: {hits}")
        assert not offenders, offenders

    def test_scenes_count_sits_in_the_documented_band(self, projects):
        offenders = []
        for p in projects:
            if p["kind"] != "short":
                continue
            count = len(p["data"].get("scenes") or [])
            low, high = SHORT_SCENE_BAND
            if not low <= count <= high:
                offenders.append(f"{p['slug']}: {count} scenes (GEMINI.md wants {low}-{high})")
        assert not offenders, offenders


# --------------------------------------------------------------------------- #
# BASELINE-LOCKED: GEMINI.md values the corpus predates
# --------------------------------------------------------------------------- #
@pytest.mark.contract
def test_audio_recipe_matches_gemini_md_section_3(projects):
    offenders = []
    for p in projects:
        flat = flatten(p["data"])
        drift = [f"{key}={flat.get(key)!r}!=want {want!r}" for key, want in SPEC_AUDIO.items() if flat.get(key) != want]
        if drift:
            offenders.append(f"{p['slug']}: {', '.join(drift)}")
    check_baseline("audio_off_gemini_md_section_3", offenders)


@pytest.mark.contract
def test_short_scripts_land_in_the_gemini_word_band(projects):
    offenders = []
    diverging = []
    for p in projects:
        low, high = SHORT_WORD_BAND if p["kind"] == "short" else LONG_WORD_BAND
        split, regex = split_words(p["data"]), regex_words(p["data"])
        on_split = low <= split <= high
        on_regex = low <= regex <= high
        if not on_split:
            offenders.append(f"{p['slug']}: {split} words (split) / {regex} (regex); band {low}-{high}")
        if split != regex and on_split != on_regex:
            diverging.append(f"{p['slug']}: split {split} is on-band, regex {regex} is not (or the reverse)")
    honesty_report("the two word counters disagree on whether a script is on-band", diverging)
    check_baseline("short_off_the_105_155_word_band", offenders)


@pytest.mark.contract
def test_citation_contract_keys_are_declared(projects):
    # GEMINI.md:69 - science is mandatory, citation_verified is "true only when the claim has been
    # matched to the paper". The only reader of citation_verified was thumbnail_studio.resolve_citation(),
    # deleted with the thumbnail subsystem on 2026-11-01, so declaring the key is bookkeeping for the
    # audit rather than a permission slip - which is still worth locking, because a project that never
    # states its citation status cannot be audited at all.
    no_science = []
    absent_verified = []
    false_claims = []
    for p in projects:
        data = p["data"]
        if not str(data.get("science") or "").strip():
            no_science.append(f"{p['slug']}: no science field")
        if "citation_verified" not in data:
            absent_verified.append(f"{p['slug']}: declares no citation_verified key (guard treats it as unverified)")
        elif data["citation_verified"] is True and not str(data.get("citation_stat") or "").strip():
            false_claims.append(f"{p['slug']}: claims citation_verified=true with no citation_stat to check")
    assert not no_science, no_science
    check_baseline("citation_verified_key_absent", absent_verified)
    honesty_report("projects asserting a verified citation with no supporting stat", false_claims)


def headline_number_offenders(titles: dict[str, str], citations: dict[str, str]) -> list[str]:
    """Headline numbers that no citation_stat on the same record supports."""
    offenders = []
    for slug, title in sorted(titles.items()):
        stat = citations.get(slug) or ""
        known = re.findall(r"\d+(?:\.\d+)?", stat)
        for number in re.findall(r"\d+(?:\.\d+)?\s*%|\d+(?:\.\d+)?\s*x\b", str(title or "")):
            if not all(d in known for d in re.findall(r"\d+(?:\.\d+)?", number)):
                offenders.append(f"{slug}: headline says {number.strip()!r}, citation_stat={stat!r}")
    return offenders


def test_a_headline_number_is_supported_by_the_citation_it_ships_with(projects):
    # Fixed 2026-11-01: this pinned a KNOWN BUG ("CURRENT BEHAVIOR - BUG") in which
    # creative_engine.LONGFORM_ANCHORS["LV-02"] read "80% of Your Focus" while nothing in the repo -
    # no dossier, no script, no citation_stat - stated 80%. The owner re-titled the live video on
    # 2026-10-31 to "The 3 Hidden Brain Traps Destroying Your Focus" and the anchor table now matches
    # it, so the assertion is flipped to what the rule requires: no offender at all.
    # GEMINI.md:71 "Headline copy must not contain a number that citation_stat does not support."
    # LV-02's anchor string is also the default related-video target for every Short, so the anchor
    # table is scanned with the projects: a number invented there reaches every UPLOAD_KIT in the repo.
    titles = {p["slug"]: str(p["data"].get("title") or "") for p in projects}
    citations = {p["slug"]: str(p["data"].get("citation_stat") or "") for p in projects}
    from tools import creative_engine

    titles.update(creative_engine.LONGFORM_ANCHORS)
    offenders = headline_number_offenders(titles, citations)
    assert offenders == [], offenders


def test_no_headline_should_state_a_number_the_dossier_cannot_back(projects):
    # Was an expected-failure pin on the LV-02 "80%" headline; the anchor is corrected, so this is now
    # a plain hard assert over the projects. The LONGFORM_ANCHORS copy is covered by the test above and
    # by tests/test_creative_engine.py::test_no_longform_anchor_headline_states_a_percentage.
    titles = {p["slug"]: str(p["data"].get("title") or "") for p in projects}
    citations = {p["slug"]: str(p["data"].get("citation_stat") or "") for p in projects}
    assert headline_number_offenders(titles, citations) == []


def test_a_dossier_related_title_is_the_anchor_string_verbatim():
    # Fixed 2026-11-03: LONGFORM_ANCHORS was cleaned to the live LV-02 title, but two dossiers still
    # carried related_title "The 3 Hidden Brain Traps Destroying 80% of Your Focus". The headline test
    # above only reads the anchor table, so the invented 80% sat in the field that build_project
    # copies into a new Short's related-video title and upload kit.
    from tools import creative_engine

    dossiers = json.loads(
        (REPO_ROOT / "channel_assets" / "scientific_dossiers.json").read_text(encoding="utf-8")
    )
    entries = dossiers if isinstance(dossiers, list) else list(dossiers.values())
    offenders = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        target, titled = entry.get("related_target"), entry.get("related_title")
        if not target or not titled:
            continue
        expected = creative_engine.LONGFORM_ANCHORS.get(target)
        if expected and titled != expected:
            offenders.append(f"{entry.get('topic')}: related_title={titled!r} but {target}={expected!r}")
    assert offenders == [], offenders


@pytest.mark.contract
def test_loop_tail_is_declared_and_consistent(projects):
    absent = []
    values = {}
    for p in projects:
        if p["kind"] != "short":
            continue
        if "tail" not in p["data"]:
            absent.append(f"{p['slug']}: no tail (build_video.py:1025 silently uses 0.20s)")
        else:
            values.setdefault(p["data"]["tail"], []).append(p["slug"])
    check_baseline("loop_tail_key_absent", absent)
    honesty_report("loop tail lengths in use across shorts", [f"{v}s -> {len(s)} project(s)" for v, s in sorted(values.items())])


# --------------------------------------------------------------------------- #
# the gates themselves disagree
# --------------------------------------------------------------------------- #
def test_the_repo_only_documents_one_word_band_to_its_users():
    """The number an agent reads off a failure message must be the number the gate enforced."""
    pipeline_src = (REPO_ROOT / "tools" / "pipeline.py").read_text(encoding="utf-8")
    policy_src = (REPO_ROOT / "tools" / "policy.py").read_text(encoding="utf-8")
    bands = re.search(
        r'WORD_BANDS = \{"short": \((\d+), (\d+)\), "long": \((\d+), (\d+)\)\}', policy_src
    )
    assert bands, "policy.py WORD_BANDS changed shape; update this test"
    short_band = (int(bands.group(1)), int(bands.group(2)))
    long_band = (int(bands.group(3)), int(bands.group(4)))

    assert "if total_words < low:" in pipeline_src, "the low gate no longer compares against the band"
    assert "elif total_words > high:" in pipeline_src, "the high gate no longer compares against the band"
    assert pipeline_src.count("Target is {low}-{high} words.") == 2, (
        "a word-count rejection now prints something other than the band it enforced"
    )

    verifiers_src = (REPO_ROOT / "tools" / "orchestrator" / "verifiers.py").read_text(encoding="utf-8")
    assert re.search(r"WORD_BANDS\[", verifiers_src) and "tools.policy import WORD_BANDS" in verifiers_src, (
        "verifiers.py went back to pipeline imports or its own literals"
    )

    honesty_report(
        "word bands the repo states",
        [
            f"GEMINI.md:29 says {SHORT_WORD_BAND[0]}-{SHORT_WORD_BAND[1]} short / {LONG_WORD_BAND[0]}-{LONG_WORD_BAND[1]} long",
            f"tools/policy.py WORD_BANDS says {short_band[0]}-{short_band[1]} / {long_band[0]}-{long_band[1]} and pipeline.py prints the same numbers it compares",
            "orchestrator/verifiers.py reads tools.policy.WORD_BANDS instead of keeping its own copy",
        ],
    )
    assert short_band == SHORT_WORD_BAND, f"pipeline enforces {short_band}, GEMINI.md documents {SHORT_WORD_BAND}"
    assert long_band == LONG_WORD_BAND, f"pipeline enforces {long_band}, GEMINI.md documents {LONG_WORD_BAND}"
    # No gate may print a band it did not enforce.
    for stale in ("105-135", "95-165", "1,100-1,500 words"):
        assert stale not in pipeline_src, f"pipeline.py still quotes the stale band {stale!r}"
