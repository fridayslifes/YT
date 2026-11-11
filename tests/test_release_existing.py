"""Existing-artifact release gates; no generators, renderers, or live APIs."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from tools.orchestrator import cli, verifiers, workflows
from tools.orchestrator.contracts import TaskSpec
from tools.orchestrator.master import MasterAgent
from tools.orchestrator.state import RunContext, RunStore
from tools.orchestrator.tools import ProjectTools
from tools.orchestrator.workers import PublishWorker, ReleaseWorker

NARRATION = [
    "Before you trust your confidence: McArthur Wheeler robbed two banks with lemon juice on his face. What did he miss?",
    "He reportedly thought cameras could not see his face.",
    "Kruger and Dunning opened their 1999 paper with that story.",
    "In their studies, the lowest-scoring quarter averaged the 12th percentile, but estimated the 62nd.",
    "They tested humor, grammar, and logic. Their explanation: limited skill can also make errors harder to recognize.",
    "High scorers sometimes underestimated their relative standing, partly because they overestimated how well their peers performed.",
    "Training improved self-assessment in their experiment. My practical suggestion: predict your performance, then compare it with feedback.",
    "Feeling certain does not prove you are right. Subscribe for the next blind spot.",
]


@pytest.fixture
def imported(tmp_path):
    project = {
        "schema_version": 2,
        "id": "SH-13",
        "format": "short",
        "variant": "cinematic_35mm",
        "channel_id": "test_channel",
        "voice": "kokoro",
        "citation_verified": True,
        "contains_synthetic_media": True,
        "scenes": [
            {"id": f"s{number:02d}", "text": text, "caption": text, "prompt": "Illustrative scene"}
            for number, text in enumerate(NARRATION, 1)
        ],
    }
    evidence = {
        "schema_version": 1,
        "status": "reviewed",
        "video_id": "SH-13",
        "primary_source": {
            "title": "Unskilled and Unaware of It",
            "authors": ["Kruger", "Dunning"],
            "year": 1999,
            "publication": "JPSP",
            "url": "https://example.org/paper",
        },
        "dossier": {
            "topic": "Dunning-Kruger",
            "primary_researchers": "Kruger and Dunning",
            "year": "1999",
            "publication": "JPSP",
            "primary_source": {
                "title": "Unskilled and Unaware of It",
                "authors": ["Justin Kruger", "David Dunning"],
                "year": 1999,
                "publication": "Journal of Personality and Social Psychology 77(6), 1121-1134",
                "url": "https://gwern.net/doc/psychology/1999-kruger.pdf",
            },
            "experiment_design": "Experiments on self assessment in unskilled, median and skilled participants.",
            "quantitative_stat": "12th and 62nd percentile",
            "_verified": True,
        },
        "claims": [
            {
                "id": "C01",
                "paraphrase": "1999 paper: 12th actual and 62nd estimated percentile.",
                "printed_page_locator": "1121, abstract",
                "support_summary": "Supported group average.",
                "used_by": [f"scene_{n}" for n in range(1, 9)],
            },
            {
                "id": "C02",
                "paraphrase": "Wheeler anecdote.",
                "printed_page_locator": "1121",
                "support_summary": "Reported newspaper account.",
                "used_by": ["scene_1"],
            },
        ],
        "editorial_suggestions": [
            {"id": "E01", "text": "Predict, then check.", "status": "Editorial suggestion", "used_by": ["scene_7"]}
        ],
        "script_sha256": hashlib.sha256("\n".join(NARRATION).encode()).hexdigest(),
    }
    folder = tmp_path / "short_fixture"
    (folder / "output").mkdir(parents=True)
    project["evidence_bundle"] = "evidence.json"
    p = folder / "project.json"
    e = tmp_path / "evidence.json"
    p.write_text(json.dumps(project))
    e.write_text(json.dumps(evidence))
    (folder / "UPLOAD_KIT_TEST.md").write_text("* **Primary Title**:\n> Dunning-Kruger: Why 12th Felt Like 62nd\n")
    (folder / "output/short_fixture.mp4").write_bytes(b"existing render")
    spec = TaskSpec(
        "release",
        "release",
        "release",
        params={
            "project_json": str(p),
            "evidence": str(e),
            "video_id": "SH-13",
            "strict_evidence": True,
            "strict_release": True,
        },
        verifiers=list(workflows.STRICT_RELEASE_VERIFIERS),
    )
    store = RunStore(tmp_path)
    state = store.create("release-existing", "test", [spec])
    ctx = RunContext(tmp_path, store.run_dir(state.run_id), state, store, ProjectTools(tmp_path))
    result = ReleaseWorker().run(spec, ctx)
    state.tasks["release"].artifacts = result.artifacts
    return spec, ctx, result, project, evidence


def test_workflow_has_only_release_until_explicit_publish(imported):
    spec, _, _, _, _ = imported
    wf = workflows.release_existing(project_json=spec.params["project_json"], evidence=spec.params["evidence"])
    assert [t.kind for t in wf.tasks] == ["release"]
    assert wf.tasks[0].params["strict_evidence"] is True
    assert wf.tasks[0].params["strict_release"] is True
    assert wf.tasks[0].verifiers == [
        "research",
        "script",
        "project",
        "render",
        "packaging",
        "precompose",
        "consistency",
    ]
    publish = workflows.release_existing(
        project_json=spec.params["project_json"], evidence=spec.params["evidence"], publish=True
    )
    assert publish.tasks[1].requires_approval
    assert publish.tasks[1].depends_on == ["release"]
    assert publish.tasks[1].params["public"] is False


def test_cli_requires_yes_before_publisher(imported, monkeypatch):
    spec, _, _, _, _ = imported
    args = cli.build_parser().parse_args(
        [
            "release-existing",
            "--project",
            spec.params["project_json"],
            "--evidence",
            spec.params["evidence"],
            "--publish",
        ]
    )
    monkeypatch.setattr(MasterAgent, "new_run", lambda *a, **kw: pytest.fail("approval must precede run"))
    assert args.func(args) == 2


def test_produce_publish_cannot_bypass_reviewed_release(monkeypatch):
    with pytest.raises(ValueError, match="release-existing"):
        workflows.produce(topic="Test", video_id="SH-99", slug="short_test", publish=True)
    args = cli.build_parser().parse_args(
        ["produce", "--topic", "Test", "--id", "SH-99", "--slug", "short_test", "--channel", "default", "--publish", "--yes"]
    )
    monkeypatch.setattr(MasterAgent, "new_run", lambda *a, **kw: pytest.fail("produce must not start"))
    assert args.func(args) == 2


def test_publisher_rejects_non_strict_release_before_uploader(imported, monkeypatch):
    from tools import upload_api
    from tools.orchestrator.contracts import Status

    spec, ctx, result, _, _ = imported
    ctx.approve = True
    ctx.state.tasks["release"].status = Status.PASSED
    ctx.state.tasks["release"].data = result.data
    spec.params["strict_release"] = False
    monkeypatch.setattr(
        upload_api, "upload_via_api",
        lambda *a, **kw: pytest.fail("unreviewed release reached uploader"),
    )

    published = PublishWorker().run(
        TaskSpec("publish", "publish", "publish", depends_on=["release"], requires_approval=True), ctx,
    )

    assert not published.ok
    assert "release-existing" in published.error


@pytest.mark.parametrize("broken", ["workflow", "verifiers", "strict_evidence", "dependency", "approval"])
def test_publisher_rejects_incomplete_strict_release_contract(imported, monkeypatch, broken):
    from tools import upload_api
    from tools.orchestrator.contracts import Status

    spec, ctx, result, _, _ = imported
    ctx.approve = True
    ctx.state.tasks["release"].status = Status.PASSED
    ctx.state.tasks["release"].data = result.data
    publish = TaskSpec("publish", "publish", "publish", depends_on=["release"], requires_approval=True)
    if broken == "workflow":
        ctx.state.workflow = "custom"
    elif broken == "verifiers":
        spec.verifiers = []
    elif broken == "strict_evidence":
        spec.params["strict_evidence"] = False
    elif broken == "dependency":
        publish.depends_on = []
    elif broken == "approval":
        publish.requires_approval = False
    monkeypatch.setattr(
        upload_api, "upload_via_api",
        lambda *a, **kw: pytest.fail("incomplete release reached uploader"),
    )

    published = PublishWorker().run(publish, ctx)

    assert not published.ok
    assert "strict verifier" in published.error


def test_import_returns_exact_existing_artifacts_and_evidence(imported):
    spec, ctx, result, project, evidence = imported
    assert result.ok
    assert set(result.artifacts) == {"project_json", "upload_kit", "output_mp4", "evidence"}
    assert ctx.project_json() == Path(spec.params["project_json"])
    assert result.data["scenes"] == project["scenes"]
    assert result.data["evidence"] == evidence
    assert result.data["editorial_suggestions"] == evidence["editorial_suggestions"]
    checks = (
        verifiers.verify_research(spec, result, ctx)
        + verifiers.verify_script(spec, result, ctx)
        + verifiers.verify_project(spec, result, ctx)
    )
    assert not [(c.name, c.message) for c in checks if not c.passed]


@pytest.mark.parametrize("status", [None, "draft"])
def test_strict_release_rejects_unreviewed_evidence(imported, status):
    spec, ctx, result, _, evidence = imported
    if status is None:
        evidence.pop("status")
    else:
        evidence["status"] = status
    Path(spec.params["evidence"]).write_text(json.dumps(evidence))
    failures = [c.message for c in verifiers.verify_research(spec, result, ctx) if not c.passed]
    assert any("unreviewed" in message for message in failures)


def test_strict_release_rejects_a_generated_draft(imported):
    from tools.schemas import prepare_release_draft

    spec, ctx, result, _, _ = imported
    output = ctx.root / "generated-draft.json"
    prepare_release_draft(Path(spec.params["project_json"]), output)
    spec.params["evidence"] = str(output)
    failures = [c.message for c in verifiers.verify_research(spec, result, ctx) if not c.passed]
    assert any("unreviewed" in message for message in failures)


def test_checked_sh13_evidence_has_explicit_reviewed_schema():
    from tools.schemas import validate_evidence

    evidence = json.loads((Path(__file__).resolve().parents[1] / "tests/fixtures/evidence_sh13_sample.json").read_text())
    assert evidence["status"] == "reviewed"
    assert validate_evidence(evidence) == []


@pytest.mark.parametrize(
    "failure",
    [
        "video_id",
        "source",
        "dossier",
        "locator",
        "duplicate",
        "scene",
        "hash",
        "editorial",
        "merged_editorial",
        "citation",
        "bundle",
        "synthetic",
        "numeric",
        "five",
    ],
)
def test_strict_evidence_rejects_unbound_or_unsupported_content(imported, failure):
    spec, ctx, result, project, evidence = imported
    evidence = copy.deepcopy(evidence)
    if failure == "video_id":
        evidence["video_id"] = "SH-99"
    if failure == "source":
        evidence["primary_source"]["url"] = "http://example.org/paper"
    if failure == "dossier":
        evidence["dossier"].pop("publication")
    if failure == "locator":
        evidence["claims"][0]["printed_page_locator"] = ""
    if failure == "duplicate":
        evidence["claims"][1]["id"] = evidence["claims"][0]["id"]
    if failure == "scene":
        evidence["claims"][0]["used_by"] = ["scene_99"]
    if failure == "hash":
        evidence["script_sha256"] = "0" * 64
    if failure == "editorial":
        evidence["editorial_suggestions"] = []
    if failure == "merged_editorial":
        evidence["claims"].append(evidence["editorial_suggestions"][0])
    if failure == "citation":
        project["citation_verified"] = False
    if failure == "bundle":
        project["evidence_bundle"] = "other.json"
    if failure == "synthetic":
        project["contains_synthetic_media"] = False
    if failure == "numeric":
        for claim in evidence["claims"]:
            claim["paraphrase"] = claim["paraphrase"].replace("12th", "twelfth").replace("62nd", "sixty-second")
    if failure == "five":
        project["scenes"][0]["text"] += " 5."
        evidence["script_sha256"] = hashlib.sha256("\n".join(s["text"] for s in project["scenes"]).encode()).hexdigest()
    Path(spec.params["project_json"]).write_text(json.dumps(project))
    Path(spec.params["evidence"]).write_text(json.dumps(evidence))
    result = ReleaseWorker().run(spec, ctx)
    checks = (
        verifiers.verify_research(spec, result, ctx)
        + verifiers.verify_script(spec, result, ctx)
        + verifiers.verify_project(spec, result, ctx)
    )
    assert any(not c.passed and c.severity == "critical" for c in checks), failure


def test_import_rejects_missing_or_multiple_artifacts(imported):
    spec, ctx, _, _, _ = imported
    (Path(spec.params["project_json"]).parent / "UPLOAD_KIT_EXTRA.md").write_text("extra")
    assert not ReleaseWorker().run(spec, ctx).ok


def test_strict_warning_severity(imported, monkeypatch):
    from tools import pipeline, youtube_skills

    spec, ctx, result, _, _ = imported
    kit = Path(result.artifacts["upload_kit"])
    kit.write_text("* **Primary Title**:\n> SH-13 " + "x" * 70 + "\n")
    monkeypatch.setattr(youtube_skills, "check_packaging", lambda _: {"issues": ["weak"]})
    monkeypatch.setattr(pipeline, "pre_compose_validate", lambda _: ["low quality"])
    checks = verifiers.verify_packaging(spec, result, ctx) + verifiers.verify_precompose(spec, result, ctx)
    assert all(c.severity == "critical" for c in checks if not c.passed)
    spec.params.clear()
    checks = verifiers.verify_packaging(spec, result, ctx) + verifiers.verify_precompose(spec, result, ctx)
    assert any(c.severity == "warning" and not c.passed for c in checks)


def test_publish_passes_channel_disclosure_and_external_receipt(imported, monkeypatch):
    from tools import upload_api

    from tools.orchestrator.contracts import Status

    spec, ctx, imported_result, _, _ = imported
    ctx.state.tasks["release"].status = Status.PASSED
    ctx.state.tasks["release"].data = imported_result.data
    ctx.approve = True
    calls = []
    monkeypatch.setattr(upload_api, "upload_via_api", lambda *a, **kw: calls.append((a, kw)) or "abcdefghijk")
    result = PublishWorker().run(
        TaskSpec(
            "publish",
            "publish",
            "publish",
            depends_on=["release"],
            requires_approval=True,
            params={"expected_channel_id": "test_channel"},
        ),
        ctx,
    )
    assert result.ok
    kwargs = calls[0][1]
    assert kwargs["expected_channel_id"] == "test_channel"
    assert kwargs["contains_synthetic_media"] is True
    assert kwargs["receipt_path"] == ctx.root / "channel_assets" / "upload_receipts" / "SH-13.json"
    assert result.artifacts["receipt"] == str(kwargs["receipt_path"])


def test_strict_verifier_reads_dossier_from_evidence_instead_of_worker_claim(imported):
    spec, ctx, result, _, evidence = imported
    evidence["dossier"].pop("publication")
    Path(spec.params["evidence"]).write_text(json.dumps(evidence))
    assert any(not check.passed for check in verifiers.verify_research(spec, result, ctx))


def test_strict_numeric_verifier_reads_real_scenes_instead_of_worker_claim(imported):
    spec, ctx, result, project, evidence = imported
    project["scenes"][0]["text"] += " 5."
    evidence["script_sha256"] = hashlib.sha256("\n".join(s["text"] for s in project["scenes"]).encode()).hexdigest()
    Path(spec.params["project_json"]).write_text(json.dumps(project))
    Path(spec.params["evidence"]).write_text(json.dumps(evidence))
    assert any(
        not check.passed and check.name == "unsourced_numbers" for check in verifiers.verify_script(spec, result, ctx)
    )


def test_null_source_title_does_not_count_as_primary_evidence(imported):
    spec, ctx, result, _, evidence = imported
    evidence["primary_source"]["title"] = None
    Path(spec.params["evidence"]).write_text(json.dumps(evidence))
    assert any(
        not check.passed and check.name == "evidence_primary_source"
        for check in verifiers.verify_research(spec, result, ctx)
    )


def test_null_dossier_field_does_not_count_as_required_evidence(imported):
    spec, ctx, result, _, evidence = imported
    evidence["dossier"]["experiment_design"] = None
    Path(spec.params["evidence"]).write_text(json.dumps(evidence))
    assert any(
        not check.passed and check.name == "dossier_required_fields"
        for check in verifiers.verify_research(spec, result, ctx)
    )


def test_publish_tracker_failure_is_bookkeeping_warning_when_receipt_verified(imported):
    from tools.orchestrator.contracts import WorkerResult

    spec, ctx, _, _, _ = imported
    receipt = ctx.root / "receipt.json"
    receipt.write_text(json.dumps({"state": "verified", "remote_id": "abcdefghijk"}))
    (ctx.root / "CONTENT_TRACKER.md").write_text("tracker unavailable")
    result = WorkerResult(
        ok=True, summary="uploaded", data={"video_id": "abcdefghijk"}, artifacts={"receipt": str(receipt)}
    )
    checks = verifiers.verify_publish(spec, result, ctx)
    assert any(check.name == "publish_receipt" and check.passed for check in checks)
    assert not any(not check.passed and check.severity == "critical" for check in checks)


def test_validation_run_never_authenticates_or_generates(imported, monkeypatch):
    from tools import creative_engine, pipeline, upload_api

    spec, ctx, _, _, _ = imported

    def forbidden(*args, **kwargs):
        pytest.fail("validation-only release invoked an external or generation operation")

    monkeypatch.setattr(upload_api, "get_authenticated_service", forbidden)
    monkeypatch.setattr(pipeline, "build_and_verify", forbidden)
    monkeypatch.setattr(creative_engine, "generate_creative_project", forbidden)
    monkeypatch.setattr(creative_engine, "choreograph_scenes", forbidden)
    monkeypatch.setattr(
        pipeline,
        "verify_rendered_mp4",
        lambda *a, **kw: {
            "valid": True,
            "width": 1080,
            "height": 1920,
            "fps": "30/1",
            "acodec": "aac",
            "sample_rate": "48000",
            "duration_s": 48,
        },
    )
    monkeypatch.setattr(pipeline, "pre_compose_validate", lambda *a: [])
    wf = workflows.release_existing(project_json=spec.params["project_json"], evidence=spec.params["evidence"])
    state = MasterAgent(ctx.root, console=lambda *a: None).new_run(wf)
    assert state.status == "passed"
    assert list(state.tasks) == ["release"]


@pytest.fixture
def approved_publish(imported, monkeypatch):
    """Run real strict release checks, leaving publishing waiting for approval."""
    from tools import pipeline

    spec, ctx, _, _, _ = imported
    monkeypatch.setattr(
        pipeline,
        "verify_rendered_mp4",
        lambda *a, **kw: {
            "valid": True,
            "width": 1080,
            "height": 1920,
            "fps": "30/1",
            "acodec": "aac",
            "sample_rate": "48000",
            "duration_s": 48,
        },
    )
    monkeypatch.setattr(pipeline, "pre_compose_validate", lambda *a: [])
    wf = workflows.release_existing(
        project_json=spec.params["project_json"], evidence=spec.params["evidence"], publish=True
    )
    master = MasterAgent(ctx.root, console=lambda *a: None)
    state = master.new_run(wf, approve=False)
    assert state.tasks["release"].status.value == "passed"
    assert state.tasks["publish"].status.value == "skipped"
    return master, state


def test_release_persists_all_approved_artifact_and_metadata_fingerprints(approved_publish):
    _, state = approved_publish
    binding = state.tasks["release"].data["release_fingerprints"]
    assert set(binding["artifacts"]) == {"project_json", "evidence", "upload_kit", "output_mp4"}
    for name, saved in binding["artifacts"].items():
        path = Path(state.tasks["release"].artifacts[name])
        assert saved == {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    assert len(binding["metadata_sha256"]) == 64


@pytest.mark.parametrize("changed", ["narration", "disclosure", "evidence", "upload_kit", "output_mp4"])
@pytest.mark.parametrize("publisher_state", ["skipped", "failed", "running"])
def test_resume_blocks_stale_release_before_any_upload(approved_publish, monkeypatch, changed, publisher_state):
    from tools import upload_api
    from tools.orchestrator.contracts import Status

    master, state = approved_publish
    release = state.tasks["release"]
    if changed in {"narration", "disclosure"}:
        path = Path(release.artifacts["project_json"])
        project = json.loads(path.read_text())
        if changed == "narration":
            project["scenes"][0]["text"] = "Unreviewed new narration."
        else:
            project["contains_synthetic_media"] = False
        path.write_text(json.dumps(project))
    else:
        path = Path(release.artifacts[changed])
        path.write_bytes(path.read_bytes() + b"changed")
    state.tasks["publish"].status = Status(publisher_state)
    master.store.save(state)
    monkeypatch.setattr(upload_api, "upload_via_api", lambda *a, **kw: pytest.fail("stale release reached upload"))
    resumed = master.resume(state.run_id, approve=True)
    published = resumed.tasks["publish"]
    assert published.status.value == "blocked"
    assert "changed" in published.error.lower()
    assert "release-existing" in published.error
    assert resumed.tasks["release"].status.value == "blocked"
    assert resumed.tasks["release"].data["release_fingerprints"] == release.data["release_fingerprints"]
    # Repeated approval cannot silently bind changed inputs to the old release.
    repeated = master.resume(state.run_id, approve=True)
    assert repeated.tasks["release"].status.value == "blocked"
    assert repeated.tasks["publish"].status.value == "blocked"


def test_resume_requires_binding_for_old_release_records(approved_publish, monkeypatch):
    from tools import upload_api

    master, state = approved_publish
    state.tasks["release"].data.pop("release_fingerprints", None)
    master.store.save(state)
    monkeypatch.setattr(upload_api, "upload_via_api", lambda *a, **kw: pytest.fail("unbound release reached upload"))
    resumed = master.resume(state.run_id, approve=True)
    assert resumed.tasks["publish"].status.value == "failed"
    assert "fingerprint" in resumed.tasks["publish"].error.lower()


def test_unchanged_approved_inputs_can_publish_after_resume(approved_publish, monkeypatch):
    from tools import upload_api

    master, state = approved_publish
    attempts = master.root / "upload-attempts.txt"

    def upload(*args, **kwargs):
        with attempts.open("a", encoding="utf-8") as handle:
            handle.write("attempt\n")
        path = kwargs["receipt_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"state": "verified", "remote_id": "abcdefghijk"}))
        return "abcdefghijk"

    monkeypatch.setattr(upload_api, "upload_via_api", upload)
    resumed = master.resume(state.run_id, approve=True)
    assert resumed.status == "passed"
    assert attempts.read_text(encoding="utf-8").splitlines() == ["attempt"]
    receipt = Path(resumed.tasks["publish"].artifacts["receipt"])
    assert json.loads(receipt.read_text(encoding="utf-8")) == {
        "state": "verified", "remote_id": "abcdefghijk"
    }


def test_resume_blocks_changed_requested_privacy(approved_publish, monkeypatch):
    from tools import upload_api

    master, state = approved_publish
    state.tasks["publish"].spec.params["public"] = True
    master.store.save(state)
    monkeypatch.setattr(upload_api, "upload_via_api", lambda *a, **kw: pytest.fail("changed privacy reached upload"))
    resumed = master.resume(state.run_id, approve=True)
    assert resumed.tasks["publish"].status.value == "failed"
    assert "metadata changed" in resumed.tasks["publish"].error


def test_changed_inputs_after_failed_uploader_are_not_retried(approved_publish, monkeypatch):
    from tools import upload_api

    master, state = approved_publish
    attempts = master.root / "upload-attempts.txt"

    def failed_upload(*args, **kwargs):
        with attempts.open("a", encoding="utf-8") as handle:
            handle.write("attempt\n")
        raise RuntimeError("simulated lost upload response")

    monkeypatch.setattr(upload_api, "upload_via_api", failed_upload)
    failed = master.resume(state.run_id, approve=True)
    assert failed.tasks["publish"].status.value == "failed"
    assert attempts.read_text(encoding="utf-8").splitlines() == ["attempt"]
    path = Path(failed.tasks["release"].artifacts["project_json"])
    project = json.loads(path.read_text())
    project["contains_synthetic_media"] = False
    path.write_text(json.dumps(project))
    monkeypatch.setattr(upload_api, "upload_via_api", lambda *a, **kw: pytest.fail("changed inputs retried upload"))
    resumed = master.resume(state.run_id, approve=True)
    assert resumed.tasks["publish"].status.value == "blocked"
    assert "changed" in resumed.tasks["publish"].error.lower()
    assert attempts.read_text(encoding="utf-8").splitlines() == ["attempt"]
