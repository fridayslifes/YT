"""A later task cannot silently replace a passed ancestor's artifact baseline."""

from __future__ import annotations

import hashlib

from tools.orchestrator.contracts import TaskSpec, WorkerResult
from tools.orchestrator.master import MasterAgent
from tools.orchestrator.workflows import Workflow


def test_generic_descendant_cannot_rebind_ancestor_artifact_hash(tmp_path):
    artifact = tmp_path / "project.json"

    class Writer:
        kind = "fake"

        def run(self, spec, ctx):
            artifact.write_text("original" if spec.id == "source" else "changed")
            return WorkerResult(True, "written", artifacts={"project_json": str(artifact)})

    master = MasterAgent(tmp_path, workers={"fake": Writer()}, verifiers={}, console=lambda *_: None)
    workflow = Workflow("test", "test", [
        TaskSpec("source", "fake", "source"),
        TaskSpec("later", "fake", "later", depends_on=["source"]),
    ])

    state = master.new_run(workflow)

    assert state.status == "passed"
    assert state.tasks["source"].artifact_fingerprints["project_json"] == hashlib.sha256(b"original").hexdigest()
    assert state.tasks["later"].artifact_fingerprints["project_json"] == hashlib.sha256(b"changed").hexdigest()


def test_hashless_legacy_local_artifact_is_revalidated_on_resume(tmp_path):
    artifact = tmp_path / "project.json"
    calls = tmp_path / "calls.log"

    class Writer:
        kind = "fake"
        def run(self, spec, ctx):
            with calls.open("a") as handle:
                handle.write(spec.id + "\n")
            artifact.write_text(f"version {len(calls.read_text().splitlines())}")
            return WorkerResult(True, "written", artifacts={"project_json": str(artifact)})

    worker = Writer()
    master = MasterAgent(tmp_path, workers={"fake": worker}, verifiers={}, console=lambda *_: None)
    state = master.new_run(Workflow("test", "test", [TaskSpec("source", "fake", "source")]))
    state.tasks["source"].artifact_fingerprints = {}
    master.store.save(state)

    resumed = master.resume(state.run_id)

    assert resumed.status == "passed"
    assert calls.read_text().splitlines() == ["source", "source"]
    assert resumed.tasks["source"].artifact_fingerprints["project_json"] == hashlib.sha256(b"version 2").hexdigest()
