"""Runtime contracts reject malformed authored data before build side effects."""

import copy
import hashlib
import json

import pytest


def project_data():
    return {
        "schema_version": 1, "id": "SH-99", "format": "short",
        "citation_verified": True, "contains_synthetic_media": True,
        "evidence_bundle": "evidence.json",
        "scenes": [
            {"id": "s1", "text": "First thought.", "prompt": "A room", "image": "images/one.jpg"},
            {"id": "s2", "text": "Second thought.", "prompt": "A room"},
            {"id": "s3", "text": "Third thought.", "prompt": "A room"},
            {"id": "s4", "text": "Fourth thought.", "prompt": "A room"},
            {"id": "s5", "text": "Fifth thought.", "prompt": "A room"},
            {"id": "s6", "text": "Sixth thought.", "prompt": "A room"},
            {"id": "s7", "text": "Seventh thought.", "prompt": "A room"},
            {"id": "s8", "text": "Last thought.", "prompt": "A room"},
        ],
        "music": {"volume": 0.18, "sfx_volume": 0.12, "bpm": 74, "seed": 42},
        "rate": "+1%", "pitch": "-2Hz", "gap": 0.08,
    }


def evidence_data():
    return {
        "schema_version": 1, "status": "reviewed", "video_id": "SH-99",
        "primary_source": {"title": "A paper", "authors": ["A. Researcher"], "year": 1999,
                           "publication": "A journal", "url": "https://example.org/paper"},
        "claims": [{"id": "C1", "paraphrase": "First thought.", "printed_page_locator": "12",
                    "support_summary": "A statement on page 12", "used_by": ["scene_1"]}],
        "editorial_suggestions": [{"id": "E1", "text": "Last thought.",
                                   "status": "Editorial", "used_by": ["scene_8"]}],
        "script_sha256": hashlib.sha256(
            b"First thought.\nSecond thought.\nThird thought.\nFourth thought.\nFifth thought.\nSixth thought.\nSeventh thought.\nLast thought."
        ).hexdigest(),
    }


def test_valid_project_and_explicit_legacy_defaults(tmp_path):
    from tools.schemas import validate_project

    project = project_data()
    assert validate_project(project, project_path=tmp_path / "project.json") == []
    del project["schema_version"]
    del project["format"]
    assert validate_project(project) == []


def test_project_collects_all_independent_errors():
    from tools.schemas import validate_project

    project = project_data()
    project.update(schema_version=2, id="../escape", format="square", music={"volume": "loud"}, rate=12)
    project["scenes"][0].update(text=None, prompt=3, image="../secret.jpg")
    project["scenes"][1]["id"] = "s1"
    project["scenes"][2] = "not a scene"
    project["scenes"].pop()
    errors = "\n".join(validate_project(project))
    for field in ("schema_version", "id", "format", "music.volume", "rate", "scenes", "scenes[0].text",
                  "scenes[0].prompt", "scenes[0].image", "scenes[1].id", "scenes[2]"):
        assert field in errors, (field, errors)


@pytest.mark.parametrize("payload", [None, [], 3, "project"])
def test_nonobject_project_returns_actionable_error(payload):
    from tools.schemas import validate_project

    assert "object" in " ".join(validate_project(payload))


@pytest.mark.parametrize("path", ["/tmp/out.mp4", "../out.mp4", "..\\out.mp4", "https://example.org/a", "bad\x00.mp4"])
def test_scene_paths_cannot_escape_project(path):
    from tools.schemas import validate_project

    project = project_data()
    project["scenes"][0]["video"] = path
    assert any("scenes[0].video" in error for error in validate_project(project))


def test_scene_symlink_escape_is_rejected(tmp_path):
    from tools.schemas import validate_project

    folder = tmp_path / "project"
    folder.mkdir()
    (folder / "images").symlink_to(tmp_path, target_is_directory=True)
    assert any("scenes[0].image" in error for error in validate_project(project_data(), project_path=folder / "project.json"))


@pytest.mark.parametrize("field,media", [
    ("shots", "../../outside.mp4"),
    ("shots", {"image": "../../outside.jpg"}),
    ("shots", {"video": "../../outside.mp4"}),
    ("images", "../../outside.jpg"),
    ("images", {"image": "../../outside.jpg"}),
    ("images", {"video": "../../outside.mp4"}),
])
def test_nested_scene_media_paths_cannot_escape_project(field, media):
    from tools.schemas import validate_project

    project = project_data()
    project["scenes"][0][field] = [media]
    errors = validate_project(project)
    assert any(f"scenes[0].{field}[0]" in error for error in errors), errors


@pytest.mark.parametrize("field,value", [("shots", "images/one.jpg"), ("images", [3]), ("shots", [None])])
def test_nested_scene_media_containers_and_entries_must_be_supported_types(field, value):
    from tools.schemas import validate_project

    project = project_data()
    project["scenes"][0][field] = value
    errors = validate_project(project)
    assert any(f"scenes[0].{field}" in error for error in errors), errors


def test_valid_nested_scene_media_forms_remain_supported():
    from tools.schemas import validate_project

    project = project_data()
    project["scenes"][0]["shots"] = ["images/one.jpg", {"video": "videos/two.mp4", "motion": "pan_left"}]
    assert validate_project(project) == []


@pytest.mark.parametrize("field,value", [("gap", True), ("tail", -1), ("pitch", 2),
                                         ("progress_bar", "yes"), ("music", []), ("scenes", {})])
def test_invalid_audio_render_and_scene_types_are_reported(field, value):
    from tools.schemas import validate_project

    project = project_data()
    project[field] = value
    assert any(field in error for error in validate_project(project))


def test_evidence_validates_source_claims_hash_and_project_binding(tmp_path):
    from tools.schemas import validate_evidence

    assert validate_evidence(evidence_data(), project=project_data(), evidence_path=tmp_path / "evidence.json") == []


def test_evidence_collects_all_review_errors(tmp_path):
    from tools.schemas import validate_evidence

    evidence = evidence_data()
    evidence.update(schema_version=2, status="draft", video_id="SH-01", script_sha256="0" * 64)
    evidence["primary_source"]["url"] = "http://example.org/paper"
    evidence["claims"][0].update(printed_page_locator="", support_summary="", used_by=["scene_99"])
    evidence["editorial_suggestions"][0]["paraphrase"] = "Claims must stay separate"
    project = project_data()
    project.update(citation_verified=False, contains_synthetic_media=False, evidence_bundle="other.json")
    errors = "\n".join(validate_evidence(evidence, project=project, evidence_path=tmp_path / "evidence.json"))
    for field in ("schema_version", "status", "video_id", "script_sha256", "primary_source.url",
                  "printed_page_locator", "support_summary", "used_by", "editorial_suggestions",
                  "citation_verified", "contains_synthetic_media", "evidence_bundle"):
        assert field in errors, (field, errors)


def test_no_implicit_legacy_evidence_bypass():
    from tools.schemas import validate_evidence

    evidence = evidence_data()
    evidence["video_id"] = "SH-13"
    del evidence["schema_version"]
    del evidence["status"]
    errors = "\n".join(validate_evidence(evidence))
    assert "schema_version" in errors and "status" in errors


def test_duplicate_claims_and_bad_containers_are_all_reported():
    from tools.schemas import validate_evidence

    evidence = evidence_data()
    evidence["claims"].append(copy.deepcopy(evidence["claims"][0]))
    evidence["claims"].append(None)
    evidence["editorial_suggestions"] = {}
    errors = "\n".join(validate_evidence(evidence))
    assert "claims[1].id" in errors and "claims[2]" in errors and "editorial_suggestions" in errors


def test_invalid_project_build_has_no_filesystem_side_effects(tmp_path, monkeypatch):
    from tools import pipeline

    project = project_data()
    project.update(format="invalid", scenes=[])
    path = tmp_path / "project.json"
    path.write_text(json.dumps(project))
    monkeypatch.setattr(pipeline.audio_bank, "ensure_studio_sfx_pack", lambda **kw: pytest.fail("invalid input reached SFX"))
    with pytest.raises(ValueError, match="format"):
        pipeline.build_and_verify(path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["project.json"]


def test_unsafe_nested_media_is_rejected_before_build_side_effects(tmp_path, monkeypatch):
    from tools import pipeline

    project = project_data()
    project["scenes"][0]["shots"] = [{"video": "../../outside.mp4"}]
    path = tmp_path / "project.json"
    path.write_text(json.dumps(project))
    monkeypatch.setattr(pipeline.audio_bank, "ensure_studio_sfx_pack", lambda **kw: pytest.fail("invalid input reached SFX"))
    with pytest.raises(ValueError, match=r"scenes\[0\]\.shots\[0\]\.video"):
        pipeline.build_and_verify(path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["project.json"]


def test_project_verifier_reports_schema_errors(tmp_path):
    from tools.orchestrator.contracts import TaskSpec, WorkerResult
    from tools.orchestrator.verifiers import verify_project
    from types import SimpleNamespace

    path = tmp_path / "project.json"
    path.write_text(json.dumps({"id": "../bad", "scenes": "bad"}))
    result = WorkerResult(ok=True, summary="fixture", artifacts={"project_json": str(path)})
    checks = verify_project(TaskSpec("project", "project", "project"), result, SimpleNamespace(project_root=tmp_path))
    failures = "\n".join(check.message for check in checks if not check.passed)
    assert "id" in failures and "scenes" in failures


@pytest.mark.parametrize("payload", [3, None, [], {"scenes": 3}, {"scenes": None}])
def test_project_verifier_returns_failures_for_malformed_roots_and_scenes(tmp_path, payload):
    from tools.orchestrator.contracts import TaskSpec, WorkerResult
    from tools.orchestrator.verifiers import verify_project
    from types import SimpleNamespace

    path = tmp_path / "project.json"
    path.write_text(json.dumps(payload))
    result = WorkerResult(ok=True, summary="fixture", artifacts={"project_json": str(path)})
    checks = verify_project(TaskSpec("project", "project", "project"), result, SimpleNamespace(project_root=tmp_path))
    assert any(check.name == "project_schema" and not check.passed for check in checks)


@pytest.mark.parametrize("cap_y,ok", [(0.34, False), (0.16, False), (0.78, False), (0.66, True), (0.44, True)])
def test_burned_in_text_stays_in_the_shorts_safe_band(tmp_path, cap_y, ok):
    """A caption over the subject's face, or under the Shorts UI block, is not shippable."""
    from tools.orchestrator.contracts import TaskSpec, WorkerResult
    from tools.orchestrator.verifiers import verify_project
    from types import SimpleNamespace

    scenes = [{"text": f"scene {i}", "cap_y": cap_y, "image": f"images/s{i}.jpg", "video": f"videos/s{i}.mp4",
               "shots": [{"start": 0.0, "end": 2.0, "video": f"videos/s{i}.mp4"}]} for i in range(1, 9)]
    path = tmp_path / "project.json"
    path.write_text(json.dumps({"id": "SH-99", "format": "short", "title": "T", "voice": "v", "rate": "+1%",
                                "gap": 0.08, "music": {}, "genre": "3d_cgi", "science": "s", "scenes": scenes}))
    result = WorkerResult(ok=True, summary="fixture", artifacts={"project_json": str(path)})
    checks = verify_project(TaskSpec("project", "project", "project"), result, SimpleNamespace(project_root=tmp_path))
    band = next(check for check in checks if check.name == "caption_safe_band")
    assert band.passed is ok
    assert band.severity == "critical"
