from __future__ import annotations

import hashlib
import json
import multiprocessing
from types import SimpleNamespace

import pytest

from tools.orchestrator.contracts import CheckResult, Status, TaskRecord, TaskSpec, WorkerResult
from tools.orchestrator.master import MasterAgent
from tools.orchestrator.state import RunStore
from tools.orchestrator.tools import ProjectTools
from tools.orchestrator.verifiers import VERIFIERS, verify_research, verify_script
from tools.orchestrator.workers import AuditWorker, BuildWorker, ResearchWorker
from tools.orchestrator.workflows import Workflow, produce
from tools.output_format import VOICE_BLACKLIST


class FakeWorker:
    kind = "fake"

    def __init__(self, *, artifact: str | None = None):
        self.artifact = artifact

    def run(self, spec, ctx):
        _record_call(ctx.root / "fake-calls.log", spec.id)
        artifacts = {"out": self.artifact} if self.artifact else {}
        return WorkerResult(ok=True, summary="fake done", artifacts=artifacts)


def _task(task_id: str, deps: list[str] | None = None, verifiers: list[str] | None = None) -> TaskSpec:
    return TaskSpec(
        id=task_id,
        kind="fake",
        title=task_id,
        depends_on=deps or [],
        verifiers=verifiers or [],
    )


def _passing_verifier(spec, result, ctx):
    return [CheckResult(name="ok", passed=True)]


def _workflow(*tasks: TaskSpec) -> Workflow:
    return Workflow(name="test", goal="test", tasks=list(tasks))


def _record_call(path, task_id):
    with path.open("a") as handle:
        handle.write(task_id + "\n")


def test_dag_runs_in_dependency_order(tmp_path):
    calls = tmp_path / "calls.log"

    class RecordingWorker(FakeWorker):
        def run(self, spec, ctx):
            _record_call(calls, spec.id)
            return WorkerResult(ok=True, summary="ok")

    master = MasterAgent(
        tmp_path,
        workers={"fake": RecordingWorker()},
        verifiers={"ok": _passing_verifier},
        console=lambda *_: None,
    )
    state = master.new_run(_workflow(_task("b", ["a"], ["ok"]), _task("a", [], ["ok"])))
    assert state.status == "passed"
    assert calls.read_text().splitlines() == ["a", "b"]


def test_legacy_production_runner_builds_and_dispatches_one_canonical_workflow(monkeypatch):
    from tools.orchestrator import cli, workflows
    from tools.orchestrator import master as master_module

    workflow = object()
    state = object()
    produced = []
    dispatched = []

    def fake_produce(**kwargs):
        produced.append(kwargs)
        return workflow

    class FakeMaster:
        def __init__(self, root):
            self.root = root

        def new_run(self, received, **kwargs):
            dispatched.append((received, kwargs))
            return state

    monkeypatch.setattr(workflows, "produce", fake_produce)
    monkeypatch.setattr(master_module, "MasterAgent", FakeMaster)

    result = cli.run_production_workflow(
        topic="Test", video_id="SH-99", slug="short_test", build=False,
    )

    assert result is state
    assert len(produced) == len(dispatched) == 1
    assert produced[0]["build"] is False
    assert produced[0]["publish"] is False
    assert dispatched[0][0] is workflow


def test_failed_task_blocks_dependents(tmp_path):
    def failing(spec, result, ctx):
        return [CheckResult(name="bad", passed=False, message="nope")]

    master = MasterAgent(
        tmp_path,
        workers={"fake": FakeWorker()},
        verifiers={"bad": failing, "ok": _passing_verifier},
        console=lambda *_: None,
    )
    state = master.new_run(_workflow(_task("a", [], ["bad"]), _task("b", ["a"], ["ok"])))
    assert state.tasks["a"].status == Status.FAILED
    assert state.tasks["b"].status == Status.BLOCKED
    assert state.status == "failed"


def test_missing_artifact_fails_task(tmp_path):
    master = MasterAgent(
        tmp_path,
        workers={"fake": FakeWorker(artifact=str(tmp_path / "missing.jpg"))},
        verifiers={"ok": _passing_verifier},
        console=lambda *_: None,
    )
    state = master.new_run(_workflow(_task("a", [], ["ok"])))
    assert state.tasks["a"].status == Status.FAILED
    assert any(c.name == "artifact:out" for c in state.tasks["a"].checks)


def test_worker_systemexit_is_a_failure_not_a_crash(tmp_path):
    class ExitWorker:
        kind = "fake"

        def run(self, spec, ctx):
            raise SystemExit(1)

    master = MasterAgent(
        tmp_path,
        workers={"fake": ExitWorker()},
        verifiers={"ok": _passing_verifier},
        console=lambda *_: None,
    )
    state = master.new_run(_workflow(_task("a", [], ["ok"])))
    assert state.tasks["a"].status == Status.FAILED
    assert "SystemExit" in state.tasks["a"].error


def test_dry_run_writes_plan_only(tmp_path):
    worker = FakeWorker()
    master = MasterAgent(
        tmp_path,
        workers={"fake": worker},
        verifiers={"ok": _passing_verifier},
        console=lambda *_: None,
    )
    state = master.new_run(_workflow(_task("a", [], ["ok"])), dry_run=True)
    assert state.status == "planned"
    assert state.tasks["a"].status == Status.SKIPPED
    assert not (tmp_path / "fake-calls.log").exists()


def test_resume_retries_failed_and_unblocks(tmp_path):
    class Gate:
        fail = True

        def __call__(self, spec, result, ctx):
            return [CheckResult(name="gate", passed=not self.fail, message="gate")]

    gate = Gate()
    worker = FakeWorker()
    master = MasterAgent(
        tmp_path,
        workers={"fake": worker},
        verifiers={"gate": gate},
        console=lambda *_: None,
    )
    state = master.new_run(_workflow(_task("a", [], ["gate"]), _task("b", ["a"], ["gate"])))
    assert state.tasks["a"].status == Status.FAILED
    assert state.tasks["b"].status == Status.BLOCKED
    gate.fail = False
    resumed = master.resume(state.run_id)
    assert resumed.tasks["a"].status == Status.PASSED
    assert resumed.tasks["b"].status == Status.PASSED
    assert resumed.status == "passed"


def test_state_roundtrip(tmp_path):
    store = RunStore(tmp_path)
    state = store.create("wf", "goal", [_task("a")])
    store.save(state)
    loaded = store.load(state.run_id)
    assert loaded.run_id == state.run_id
    assert loaded.tasks["a"].spec.kind == "fake"


def test_busy_resume_cli_returns_nonzero_without_traceback(tmp_path, monkeypatch, capsys):
    from tools.orchestrator import cli

    store = RunStore(tmp_path)
    state = store.create("busy", "busy", [TaskSpec("search", "search", "search")])
    context = multiprocessing.get_context("fork")
    held, release = context.Event(), context.Event()

    def hold():
        with store.execution_lock(state.run_id):
            held.set()
            assert release.wait(5)

    holder = context.Process(target=hold)
    try:
        holder.start()
        assert held.wait(2)
        before = (store.run_dir(state.run_id) / "run.json").read_bytes()
        monkeypatch.setattr(cli, "ROOT", tmp_path)
        assert cli.main(["resume", state.run_id]) != 0
        output = capsys.readouterr()
        assert "busy" in output.err.lower()
        assert state.run_id in output.err
        assert "Traceback" not in output.err
        assert (store.run_dir(state.run_id) / "run.json").read_bytes() == before
    finally:
        release.set()
        holder.join(5)
        if holder.is_alive():
            holder.kill()
            holder.join()


def test_research_verifier_rejects_synthetic():
    dossier = {
        "topic": "Ego Depletion",
        "primary_researchers": "Cognitive Psychology Research Consortium",
        "year": "1984",
        "publication": "Behavioral Decision Research",
        "experiment_design": "Controlled trials",
        "quantitative_stat": "3.1x",
        "_verified": False,
        "_synthetic": True,
    }
    result = WorkerResult(ok=True, summary="x", data={"dossier": dossier})
    checks = verify_research(TaskSpec(id="r", kind="research", title="r"), result, None)
    provenance = next(c for c in checks if c.name == "dossier_provenance")
    assert provenance.passed is False
    assert "synthetic" in provenance.message.lower()


def _scene_text(words: int) -> str:
    return " ".join(["word"] * words)


@pytest.mark.parametrize("primary_source, passes", [
    (None, False),
    ({"title": "Paper", "authors": ["A"], "year": 1999, "url": "https://example.org/a.pdf"}, True),
    ({"title": "Paper", "authors": ["A"], "year": 1999, "url": "http://example.org/a.pdf"}, False),
    ({"title": "", "authors": ["A"], "year": 1999, "url": "https://example.org/a.pdf"}, False),
    ({"title": "Paper", "authors": [], "year": 1999, "url": "https://example.org/a.pdf"}, False),
    ({"title": "Paper", "authors": ["A"], "year": "199", "url": "https://example.org/a.pdf"}, False),
])
def test_dossier_needs_a_checkable_primary_source_before_scripting(primary_source, passes):
    """method_claims compares script to dossier; this compares the dossier to a paper someone can open."""
    dossier = {
        "topic": "Example", "primary_researchers": "A and B", "year": "1999",
        "publication": "JPSP", "experiment_design": "Experiments on self assessment",
        "quantitative_stat": "12 subjects",
    }
    if primary_source is not None:
        dossier["primary_source"] = primary_source
    checks = verify_research(
        TaskSpec("research", "research", "research"), WorkerResult(True, "x", data={"dossier": dossier}), None
    )
    check = next(c for c in checks if c.name == "dossier_primary_source")
    assert check.passed is passes


def test_script_verifier_rejects_weak_hook():
    scenes = [
        {"text": "The Doorway Effect", "prompt": "a room"},
        *[{"text": _scene_text(14), "prompt": "a room"} for _ in range(7)],
    ]
    result = WorkerResult(
        ok=True,
        summary="x",
        data={"scenes": scenes, "dossier": {"year": "1979"}, "claims": [{"field": "year", "value": "1979"}]},
    )
    checks = verify_script(TaskSpec(id="s", kind="script", title="s", params={"hook_min": 70}), result, None)
    hook = next(c for c in checks if c.name == "hook_score")
    assert hook.passed is False


def test_code_search(tmp_path):
    (tmp_path / "sample.py").write_text("def build_and_verify():\n    pass\n", encoding="utf-8")
    tools = ProjectTools(tmp_path)
    result = tools.search_code("build_and_verify")
    assert result["matches"]
    assert result["matches"][0]["path"].endswith("sample.py")


# --------------------------------------------------------------------------- #
# the release DAG after the 2026-11-01 thumbnail removal
# --------------------------------------------------------------------------- #
def test_the_release_gate_verifies_render_packaging_precompose_and_consistency():
    """The thumbnail task is gone from the release DAG, and `consistency` replaced its role.

    The channel takes its feed preview from the video's own frames, so `tools/thumbnail_studio.py`,
    `tools/thumbball.py`, the orchestrator ThumbnailWorker, verify_thumbnail, the pixel blob gate and
    the `thumbnails` subcommand were deleted on purpose. What replaced the pixel gate is a gate on the
    repo itself: a change that leaves a dangling reference behind must not reach an upload.
    """
    wf = produce(topic="Loss Aversion", video_id="SH-99", slug="short_99_loss_aversion", build=True)
    assert [t.id for t in wf.tasks] == ["research", "script", "project", "build", "release"]

    release = next(t for t in wf.tasks if t.id == "release")
    assert release.verifiers == ["render", "packaging", "precompose", "consistency"], (
        f"the release gate reads {release.verifiers}; the thumbnail half was removed on 2026-11-01"
    )
    assert release.depends_on == ["build"]

    dag_text = " ".join(
        f"{t.id} {t.kind} {t.title} {' '.join(t.verifiers)} {' '.join(sorted(t.params))}" for t in wf.tasks
    ).lower()
    assert "thumb" not in dag_text, f"the DAG still wires a thumbnail: {dag_text}"
    assert "thumbnail" not in {t.kind for t in wf.tasks}


def test_no_task_in_the_dag_asks_for_a_verifier_that_does_not_exist():
    """A deleted verifier leaves a name behind in workflows.py, and the master only fails at runtime."""
    for build in (False, True):
        wf = produce(topic="Loss Aversion", video_id="SH-99", slug="short_99_loss_aversion", build=build)
        referenced = {name for task in wf.tasks for name in task.verifiers}
        dangling = sorted(referenced - set(VERIFIERS))
        assert not dangling, f"build={build} asks for unregistered verifier(s) {dangling}"
    assert "thumbnail" not in VERIFIERS, "verify_thumbnail came back without its task"


@pytest.mark.parametrize("change", ["missing", "modified"])
def test_resume_reruns_all_descendants_of_changed_artifact(tmp_path, change):
    calls = tmp_path / "calls.log"

    class ArtifactWorker:
        kind = "fake"

        def run(self, spec, ctx):
            _record_call(calls, spec.id)
            path = tmp_path / f"{spec.id}.txt"
            path.write_text(f"{spec.id}:{calls.read_text().splitlines().count(spec.id)}")
            return WorkerResult(ok=True, summary="written", artifacts={"out": str(path)})

    master = MasterAgent(tmp_path, workers={"fake": ArtifactWorker()}, verifiers={}, console=lambda *_: None)
    state = master.new_run(_workflow(
        _task("source"), _task("middle", ["source"]), _task("leaf", ["middle"]), _task("independent")
    ))
    original = state.tasks["source"].artifact_fingerprints["out"]
    assert original == hashlib.sha256((tmp_path / "source.txt").read_bytes()).hexdigest()
    if change == "missing":
        (tmp_path / "source.txt").unlink()
    else:
        # Same length as the original content: existence and size are insufficient.
        (tmp_path / "source.txt").write_text("tampered")
    resumed = master.resume(state.run_id)
    assert resumed.status == "passed"
    assert calls.read_text().splitlines()[-3:] == ["source", "middle", "leaf"]
    assert resumed.tasks["independent"].attempts == 1
    assert all(resumed.tasks[name].attempts == 2 for name in ("source", "middle", "leaf"))


def test_resume_reuses_unchanged_fingerprinted_files(tmp_path):
    path = tmp_path / "artifact.txt"
    path.write_text("unchanged")
    worker = FakeWorker(artifact=str(path))
    master = MasterAgent(tmp_path, workers={"fake": worker}, verifiers={}, console=lambda *_: None)
    state = master.new_run(_workflow(_task("a")))
    resumed = master.resume(state.run_id)
    assert resumed.status == "passed"
    assert (tmp_path / "fake-calls.log").read_text().splitlines() == ["a"]
    assert resumed.tasks["a"].artifact_fingerprints["out"] == hashlib.sha256(b"unchanged").hexdigest()


@pytest.mark.parametrize("change", ["upstream", "receipt"])
def test_completed_external_task_never_replays_after_invalidation(tmp_path, change):
    calls = tmp_path / "calls.log"

    class ArtifactWorker:
        kind = "fake"

        def run(self, spec, ctx):
            _record_call(calls, spec.id)
            path = tmp_path / f"{spec.id}.txt"
            path.write_text(spec.id)
            return WorkerResult(ok=True, summary="done", artifacts={"out": str(path)}, data={"receipt": "kept"})

    publish = _task("publish", ["source"])
    publish.requires_approval = True
    master = MasterAgent(tmp_path, workers={"fake": ArtifactWorker()}, verifiers={}, console=lambda *_: None)
    state = master.new_run(_workflow(_task("source"), publish), approve=True)
    original_artifacts = dict(state.tasks["publish"].artifacts)
    if change == "upstream":
        (tmp_path / "source.txt").write_text("changed")
    else:
        (tmp_path / "publish.txt").unlink()
    for _ in range(2):
        resumed = master.resume(state.run_id, approve=True)
        assert resumed.status == "blocked"
        assert resumed.tasks["publish"].status == Status.BLOCKED
        assert resumed.tasks["publish"].reconciliation_required
        assert resumed.tasks["publish"].artifacts == original_artifacts
        assert resumed.tasks["publish"].data == {"receipt": "kept"}
    assert calls.read_text().splitlines().count("publish") == 1


def test_old_task_record_deserializes_without_fingerprint_fields():
    record = TaskRecord.from_dict({"spec": _task("old").to_dict(), "status": "passed"})
    assert record.artifact_fingerprints == {}
    assert record.reconciliation_required is False


def test_audit_critical_findings_fail_without_retry(tmp_path, monkeypatch):
    from tools import creative_engine
    from tools.orchestrator import impact

    finding = SimpleNamespace(
        detail="missing module", sites=[SimpleNamespace(file="example.py", line=1)]
    )
    monkeypatch.setattr(creative_engine, "load_dossiers", lambda: {})
    monkeypatch.setattr(impact, "Index", lambda root: None)
    monkeypatch.setattr(impact, "find_stale", lambda index: [finding])
    monkeypatch.setattr(impact, "severity", lambda item: "critical")
    master = MasterAgent(tmp_path, workers={"audit": AuditWorker()}, verifiers={}, console=lambda *_: None)
    state = master.new_run(_workflow(TaskSpec("audit", "audit", "audit", max_attempts=3)))
    assert state.status == "failed"
    assert state.tasks["audit"].metrics["critical"] == 1
    assert state.tasks["audit"].attempts == 1
    assert "critical" in state.tasks["audit"].error


def test_empty_audit_corpus_reports_media_assessed_zero(tmp_path, monkeypatch):
    from tools.orchestrator import impact
    from tools import creative_engine

    monkeypatch.setattr(creative_engine, "load_dossiers", lambda: {})
    monkeypatch.setattr(impact, "Index", lambda root: None)
    monkeypatch.setattr(impact, "find_stale", lambda index: [])
    monkeypatch.setattr(impact, "severity", lambda item: "warning")
    result = AuditWorker().run(_task("audit"), SimpleNamespace(root=tmp_path))

    assert result.metrics["media_assessed"] == 0
    assert "no retained media assessed" in result.summary.lower()
    assert result.metrics["scanned"] == 0
    assert result.metrics["skipped"] == 0


def test_audit_isolates_malformed_project_json_and_counts_it_as_skipped(tmp_path, monkeypatch):
    from tools.orchestrator import impact
    from tools import creative_engine

    bad = tmp_path / "shorts" / "short_bad"
    bad.mkdir(parents=True)
    (bad / "project.json").write_text("{ broken", encoding="utf-8")
    monkeypatch.setattr(creative_engine, "load_dossiers", lambda: {})
    monkeypatch.setattr(impact, "Index", lambda root: None)
    monkeypatch.setattr(impact, "find_stale", lambda index: [])
    monkeypatch.setattr(impact, "severity", lambda item: "warning")
    result = AuditWorker().run(_task("audit"), SimpleNamespace(root=tmp_path))

    assert result.metrics["scanned"] == 1
    assert result.metrics["skipped"] == 1
    assert any("malformed project JSON" in item["detail"] for item in result.data["findings"])


def _verified_dossier():
    return {
        "topic": "Example", "primary_researchers": "Example Author", "year": "1979",
        "publication": "Example Journal", "experiment_design": "Controlled trials",
        "quantitative_stat": "10%", "_verified": True, "_synthetic": False,
    }


@pytest.mark.parametrize("source", ["custom", "shipped"])
@pytest.mark.parametrize("markers", [
    {"_verified": False, "_synthetic": True},
    {"_verified": False, "_synthetic": False},
    {"_verified": "true", "_synthetic": False},
    {"_verified": 1, "_synthetic": False},
    {"_verified": True, "_synthetic": "false"},
    {"_verified": True, "_synthetic": 0},
])
def test_research_preserves_rejected_provenance(tmp_path, monkeypatch, source, markers):
    from tools import creative_engine

    dossier = {**_verified_dossier(), **markers}
    params = {"topic": "Example"}
    if source == "custom":
        path = tmp_path / "dossier.json"
        path.write_text(json.dumps(dossier))
        params["dossier"] = str(path)
    else:
        monkeypatch.setattr(creative_engine, "load_dossiers", lambda: {"example": dossier})
    spec = TaskSpec("research", "research", "research", params=params)
    result = ResearchWorker().run(spec, SimpleNamespace(root=tmp_path))
    for name, value in markers.items():
        assert result.data["dossier"][name] == value
        assert type(result.data["dossier"][name]) is type(value)
    provenance = next(check for check in verify_research(spec, result, None) if check.name == "dossier_provenance")
    assert not provenance.passed


@pytest.mark.parametrize("source, expected", [("custom", False), ("shipped", True)])
def test_only_checked_in_dossiers_get_legacy_verification_default(tmp_path, monkeypatch, source, expected):
    from tools import creative_engine

    dossier = _verified_dossier()
    dossier.pop("_verified")
    dossier.pop("_synthetic")
    params = {"topic": "Example"}
    if source == "custom":
        path = tmp_path / "dossier.json"
        path.write_text(json.dumps(dossier))
        params["dossier"] = str(path)
    else:
        monkeypatch.setattr(creative_engine, "load_dossiers", lambda: {"example": dossier})
    spec = TaskSpec("research", "research", "research", params=params)
    result = ResearchWorker().run(spec, SimpleNamespace(root=tmp_path))
    provenance = next(check for check in verify_research(spec, result, None) if check.name == "dossier_provenance")
    assert provenance.passed is expected


def test_custom_dossier_requires_an_object(tmp_path):
    path = tmp_path / "dossier.json"
    path.write_text("[]")
    result = ResearchWorker().run(
        TaskSpec("research", "research", "research", params={"topic": "Example", "dossier": str(path)}),
        SimpleNamespace(root=tmp_path),
    )
    assert not result.ok and not result.retryable
    assert "object" in result.error


def test_research_empty_stored_topic_cannot_match_unrelated_request(tmp_path, monkeypatch):
    from tools import creative_engine

    monkeypatch.setattr(creative_engine, "load_dossiers", lambda: {"unrelated": {**_verified_dossier(), "topic": ""}})
    result = ResearchWorker().run(
        TaskSpec("research", "research", "research", params={"topic": "Example"}), SimpleNamespace(root=tmp_path)
    )
    assert not result.ok


def test_research_exact_match_beats_earlier_partial_match(tmp_path, monkeypatch):
    from tools import creative_engine

    monkeypatch.setattr(creative_engine, "load_dossiers", lambda: {
        "exam": {**_verified_dossier(), "topic": "Exam", "year": "1980"},
        "example": _verified_dossier(),
    })
    result = ResearchWorker().run(
        TaskSpec("research", "research", "research", params={"topic": "Example"}), SimpleNamespace(root=tmp_path)
    )
    assert result.data["dossier"]["year"] == "1979"


@pytest.mark.parametrize("field", ["topic", "primary_researchers", "year", "publication", "experiment_design", "quantitative_stat"])
def test_null_research_field_is_missing(field):
    result = WorkerResult(True, "x", data={"dossier": {**_verified_dossier(), field: None}})
    checks = verify_research(TaskSpec("research", "research", "research"), result, None)
    required = next(check for check in checks if check.name == "dossier_required_fields")
    assert not required.passed
    assert field in required.metrics["missing"]


@pytest.mark.parametrize("text, supported", [
    ("5 trials", False), ("19 trials", False), ("79 trials", False), ("13th rank", False),
    ("3 trials", False), ("31 trials", False), ("1.2 trials", False),
    ("1979", True), ("3.1 times", True), ("1,200 participants", True), ("1200 participants", True),
    ("12th rank", True),
])
def test_numeric_claims_require_exact_dossier_tokens(text, supported):
    result = WorkerResult(True, "x", data={
        "scenes": [{"text": text, "prompt": "room"}],
        "dossier": {"year": "1979", "quantitative_stat": "3.1x, 1,200 participants, 12th rank"},
        "claims": [{"field": "year", "value": "1979"}],
    })
    checks = verify_script(TaskSpec("script", "script", "script"), result, None)
    numeric = next(check for check in checks if check.name == "unsourced_numbers")
    assert numeric.passed is supported


@pytest.mark.parametrize("text, dossier_design, supported", [
    (
        "In controlled laboratory testing, winners matched controls",
        "Study 1 was short field interviews with three groups.",
        False,
    ),
    (
        "The experiment found no difference",
        "Study 1 was short field interviews with three groups.",
        False,
    ),
    (
        "Dopamine receptors drive the loop",
        "Adaptation level raises the baseline through contrast and habituation.",
        False,
    ),
    (
        "Brain scans show the amygdala firing",
        "Brain scans show the amygdala responding to losses.",
        True,
    ),
    (
        "Brain scans show the amygdala firing",
        "Neuroimaging shows the amygdala responding to losses.",
        False,
    ),
    ("The team interviewed 22 winners", "Study 1 was short field interviews.", True),
])
def test_method_and_mechanism_claims_require_dossier_support(text, dossier_design, supported):
    """A spoken method or neural mechanism must be stated by the dossier, like a spoken number."""
    result = WorkerResult(True, "x", data={
        "scenes": [{"text": text, "prompt": "room"}],
        "dossier": {"topic": "Example", "year": "1978", "experiment_design": dossier_design},
        "claims": [{"field": "topic", "value": "Example"}],
    })
    checks = verify_script(TaskSpec("script", "script", "script"), result, None)
    method = next(check for check in checks if check.name == "method_claims")
    assert method.passed is supported
    assert method.severity == "critical"


@pytest.mark.parametrize("prompt,dossier_design,supported", [
    # SH-17 shipped this exact frame: the narration said "interviewed" while scene 4's prompt
    # asked FLUX for cortex and amygdala pathways the 1978 paper never measured.
    (
        "beside a glass display illuminating active prefrontal cortex and amygdala pathways",
        "Study 1 was short field interviews with three groups.",
        False,
    ),
    (
        "a 1978 laboratory testing table receding into shallow depth of field",
        "Study 1 was short field interviews with three groups.",
        False,
    ),
    (
        "beside a glass display illuminating active amygdala pathways",
        "Neuroimaging shows the amygdala responding to losses.",
        True,
    ),
    (
        "reviewing handwritten study records and annotated data sheets",
        "Study 1 was short field interviews with three groups.",
        True,
    ),
])
def test_image_prompts_answer_to_the_same_method_rule_as_the_narration(
    prompt, dossier_design, supported
):
    """A depicted method or mechanism needs dossier support even when the spoken text is clean."""
    result = WorkerResult(True, "x", data={
        "scenes": [{"text": "The team interviewed 22 winners", "prompt": prompt}],
        "dossier": {"topic": "Example", "year": "1978", "experiment_design": dossier_design},
        "claims": [{"field": "topic", "value": "Example"}],
    })
    checks = verify_script(TaskSpec("script", "script", "script"), result, None)
    visual = next(check for check in checks if check.name == "visual_method_claims")
    assert visual.passed is supported
    assert visual.severity == "critical"


@pytest.mark.parametrize("prompt,named", [
    ("researchers (Philip Brickman) in period-accurate academic attire", True),
    ("two research investigators in period-accurate academic attire", False),
])
def test_image_prompts_must_not_request_a_real_persons_likeness(prompt, named):
    """FLUX Kommunity License s4.a(v) bars output that violates publicity or digital-replica rights."""
    result = WorkerResult(True, "x", data={
        "scenes": [{"text": "The team interviewed 22 winners", "prompt": prompt}],
        "dossier": {
            "topic": "Example",
            "year": "1978",
            "experiment_design": "Study 1 was short field interviews with three groups.",
            "primary_researchers": "Philip Brickman, Dan Coates & Ronnie Janoff-Bulman",
        },
        "claims": [{"field": "topic", "value": "Example"}],
    })
    checks = verify_script(TaskSpec("script", "script", "script"), result, None)
    subject = next(check for check in checks if check.name == "named_subject")
    assert subject.passed is not named
    assert subject.severity == "critical"


def test_voice_blacklist_blocks_normal_script():
    result = WorkerResult(True, "x", data={
        "scenes": [{"text": "unlock your potential", "prompt": "room"}],
        "dossier": {}, "claims": [{"field": "topic", "value": "Example"}],
    })
    checks = verify_script(TaskSpec("script", "script", "script"), result, None)
    blacklist = next(check for check in checks if check.name == "voice_blacklist")
    assert not blacklist.passed
    assert blacklist.severity == "critical"


@pytest.mark.parametrize("word", VOICE_BLACKLIST)
def test_script_and_title_use_the_same_blacklist_and_case_matching(word):
    from tools.orchestrator import verifiers
    from tools.youtube_skills import title

    assert verifiers.VOICE_BLACKLIST is title.VOICE_BLACKLIST
    text = f"Observe {word.upper()} in 3 trials"
    result = WorkerResult(True, "x", data={
        "scenes": [{"text": text, "prompt": "room"}], "dossier": {}, "claims": [],
    })
    checks = verify_script(TaskSpec("script", "script", "script"), result, None)
    blacklist = next(check for check in checks if check.name == "voice_blacklist")
    assert not blacklist.passed
    assert word in blacklist.metrics["words"]
    assert "vague" in {kind for kind, _ in title.check(text)["issues"]}


@pytest.mark.parametrize("text", [
    "There are 3 unlockable doors", "Study 3 testamentary records", "Researchers delved into 3 archives",
])
def test_script_and_title_blacklist_use_whole_words(text):
    from tools.youtube_skills import title

    result = WorkerResult(True, "x", data={
        "scenes": [{"text": text, "prompt": "room"}], "dossier": {}, "claims": [],
    })
    checks = verify_script(TaskSpec("script", "script", "script"), result, None)
    blacklist = next(check for check in checks if check.name == "voice_blacklist")
    assert blacklist.passed
    assert blacklist.metrics["words"] == []
    assert "vague" not in {kind for kind, _ in title.check(text)["issues"]}


@pytest.mark.parametrize("text, paraphrase, uses, supported", [
    ("5 trials", "Measured 5.2 units", ["scene_1"], False),
    ("12 participants", "Measured group performance", ["scene_1"], False),
    ("12 participants", "Measured 12 participants", ["scene_1"], True),
    ("12 participants", "Measured 12 participants", ["scene_2"], False),
])
def test_strict_numbers_require_claim_content_and_scene_binding(monkeypatch, text, paraphrase, uses, supported):
    from tools.orchestrator import verifiers

    evidence = {
        "dossier": _verified_dossier(),
        "claims": [{
            "id": "C01", "paraphrase": paraphrase, "printed_page_locator": "page 12",
            "support_summary": "The reported observation.", "used_by": uses,
        }],
    }
    project = {"scenes": [{"text": text, "prompt": "room"}]}
    monkeypatch.setattr(verifiers, "_read_strict_inputs", lambda spec, ctx: (evidence, project))
    checks = verify_script(
        TaskSpec("script", "script", "script", params={"strict_evidence": True}), WorkerResult(True, "x"), None
    )
    numeric = next(check for check in checks if check.name == "unsourced_numbers")
    assert numeric.passed is supported


def test_verified_build_mutation_is_reused_but_later_external_edit_invalidates(tmp_path, monkeypatch):
    from tools import pipeline

    calls = tmp_path / "calls.log"
    project_dir = tmp_path / "short_fixture"
    project_dir.mkdir()
    project_json = project_dir / "project.json"

    class ProductionWorker:
        kind = "fake"

        def run(self, spec, ctx):
            _record_call(calls, spec.id)
            if spec.id == "project":
                project_json.write_text(json.dumps({"id": "SH-TEST", "scenes": []}))
                return WorkerResult(True, "blueprint", artifacts={"project_json": str(project_json)})
            if spec.id == "release":
                return WorkerResult(True, "reviewed", artifacts=dict(ctx.state.tasks["build"].artifacts))
            return WorkerResult(True, "published", artifacts={"url": "https://example.org/published"})

    def fake_build(path, **kwargs):
        _record_call(calls, "build")
        project = json.loads(path.read_text())
        project["resolved_assets"] = True
        path.write_text(json.dumps(project))
        output = path.parent / "output" / f"{path.parent.name}.mp4"
        output.parent.mkdir(exist_ok=True)
        output.write_bytes(b"verified rendered content")
        return {"valid": True}

    def verify_build(spec, result, ctx):
        return [CheckResult("resolved_assets", json.loads(project_json.read_text()).get("resolved_assets") is True)]

    monkeypatch.setattr(pipeline, "build_and_verify", fake_build)
    publisher = _task("publish", ["release"])
    publisher.requires_approval = True
    master = MasterAgent(
        tmp_path, workers={"fake": ProductionWorker(), "build": BuildWorker()},
        verifiers={"render": verify_build}, console=lambda *_: None,
    )
    state = master.new_run(_workflow(
        _task("project"),
        TaskSpec("build", "build", "build", depends_on=["project"], verifiers=["render"]),
        _task("release", ["build"]), publisher,
    ), approve=True)
    assert state.status == "passed"
    assert state.tasks["build"].artifacts["project_json"] == str(project_json)
    assert state.tasks["project"].artifact_fingerprints["project_json"] == hashlib.sha256(project_json.read_bytes()).hexdigest()
    resumed = master.resume(state.run_id, approve=True)
    assert resumed.status == "passed"
    assert calls.read_text().splitlines() == ["project", "build", "release", "publish"]

    project_json.write_text(json.dumps({"id": "SH-TEST", "external_change": True}))
    resumed = master.resume(state.run_id, approve=True)
    assert calls.read_text().splitlines() == ["project", "build", "release", "publish", "project", "build", "release"]
    assert resumed.tasks["publish"].status == Status.BLOCKED
    assert resumed.tasks["publish"].reconciliation_required
    repeated = master.resume(state.run_id, approve=True)
    assert repeated.tasks["publish"].status == Status.BLOCKED
    assert calls.read_text().splitlines().count("publish") == 1
    assert calls.read_text().splitlines().count("build") == 2


@pytest.mark.parametrize("worker_ok, check_ok, declared", [
    (False, True, True), (True, False, True), (True, True, False),
])
def test_failed_or_undeclared_mutation_does_not_refresh_upstream_hash(tmp_path, worker_ok, check_ok, declared):
    path = tmp_path / "project.json"

    class MutatingWorker:
        kind = "build"

        def run(self, spec, ctx):
            if spec.id == "source":
                path.write_text("original")
                return WorkerResult(True, "original", artifacts={"project_json": str(path)})
            path.write_text("changed")
            return WorkerResult(worker_ok, "mutated", artifacts={"project_json": str(path)} if declared else {})

    master = MasterAgent(
        tmp_path, workers={"build": MutatingWorker()},
        verifiers={"check": lambda *args: [CheckResult("check", check_ok)]}, console=lambda *_: None,
    )
    source = _task("source")
    source.kind = "build"
    mutation = _task("build", ["source"], ["check"])
    mutation.kind = "build"
    state = master.new_run(_workflow(source, mutation))
    assert state.tasks["source"].artifact_fingerprints["project_json"] == hashlib.sha256(b"original").hexdigest()


@pytest.mark.parametrize("protection", ["strict_release", "approval"])
def test_declared_mutation_never_rebinds_immutable_record(tmp_path, protection):
    path = tmp_path / "artifact.json"

    class MutatingWorker:
        kind = "build"

        def run(self, spec, ctx):
            path.write_text("original" if spec.id == "protected" else "changed")
            return WorkerResult(True, "written", artifacts={"project_json": str(path)})

    protected = _task("protected")
    protected.kind = "build"
    protected.params["strict_release"] = protection == "strict_release"
    protected.requires_approval = protection == "approval"
    mutation = _task("mutation", ["protected"])
    mutation.kind = "build"
    master = MasterAgent(tmp_path, workers={"build": MutatingWorker()}, verifiers={}, console=lambda *_: None)
    state = master.new_run(_workflow(protected, mutation), approve=True)
    assert state.tasks["protected"].artifact_fingerprints["project_json"] == hashlib.sha256(b"original").hexdigest()
    resumed = master.resume(state.run_id, approve=True)
    assert resumed.tasks["protected"].status == Status.BLOCKED
    assert resumed.tasks["protected"].reconciliation_required


@pytest.mark.parametrize("metadata", [
    {"url": "https://example.org/study/53"},
    {"source_url": "https://example.org/study/53"},
    {"doi": "10.53/example"},
    {"metadata": {"version": 53}},
    {"references": [{"page": 53}]},
    {"experiment_design": "See https://example.org/study/53 for the experimental method."},
])
def test_dossier_metadata_cannot_support_numeric_claim(metadata):
    result = WorkerResult(True, "x", data={
        "scenes": [{"text": "53 participants", "prompt": "room"}],
        "dossier": {"year": "1979", "quantitative_stat": "10%", **metadata},
        "claims": [{"field": "year", "value": "1979"}],
    })
    checks = verify_script(TaskSpec("script", "script", "script"), result, None)
    numeric = next(check for check in checks if check.name == "unsourced_numbers")
    assert not numeric.passed
