"""Older upload commands must enter the reviewed release workflow."""

from __future__ import annotations

import sys
from types import SimpleNamespace

from tools import agents, pipeline, upload_api
from tools.orchestrator import cli


def test_shared_legacy_route_requires_evidence_and_approval(tmp_path, monkeypatch):
    monkeypatch.setattr(
        cli, "run_release_existing",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("release was started")),
    )

    assert cli.legacy_upload_command(tmp_path, None, public=False, approve=True) == 2
    assert cli.legacy_upload_command(tmp_path, tmp_path / "evidence.json", public=False, approve=False) == 2


def test_shared_legacy_route_passes_project_and_evidence_to_strict_release(tmp_path, monkeypatch):
    calls = []
    evidence = tmp_path / "evidence.json"

    def fake_release(project, evidence_path, **kwargs):
        calls.append((project, evidence_path, kwargs))
        return SimpleNamespace(status="passed")

    monkeypatch.setattr(cli, "run_release_existing", fake_release)
    monkeypatch.setattr(cli, "_print_state", lambda *args, **kwargs: None)

    assert cli.legacy_upload_command(tmp_path, evidence, public=True, approve=True) == 0
    assert calls == [(tmp_path / "project.json", evidence, {"publish": True, "public": True, "approve": True})]


def test_pipeline_upload_without_release_inputs_never_calls_uploader(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["pipeline.py", "--upload", str(tmp_path)])
    monkeypatch.setattr(
        upload_api, "upload_via_api",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("direct upload reached")),
    )

    assert pipeline.main() == 2


def test_pipeline_upload_forwards_release_inputs(tmp_path, monkeypatch):
    evidence = tmp_path / "evidence.json"
    calls = []
    monkeypatch.setattr(
        cli, "legacy_upload_command",
        lambda project, evidence_path, **kwargs: calls.append((project, evidence_path, kwargs)) or 1,
    )
    monkeypatch.setattr(
        sys, "argv", ["pipeline.py", "--upload-api", str(tmp_path), "--evidence", str(evidence), "--yes", "--public"],
    )

    assert pipeline.main() == 1
    assert calls == [(tmp_path.resolve(), evidence, {"public": True, "approve": True})]


def test_pipeline_rejects_upload_mixed_with_production(tmp_path, monkeypatch):
    monkeypatch.setattr(
        cli, "legacy_upload_command",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("upload route reached")),
    )
    monkeypatch.setattr(
        sys, "argv", [
            "pipeline.py", "--auto", "--topic", "Test", "--id", "SH-99", "--slug", "short_test",
            "--upload", str(tmp_path), "--evidence", str(tmp_path / "evidence.json"), "--yes",
        ],
    )

    assert pipeline.main() == 2


def test_upload_api_cli_without_reviewed_inputs_never_calls_uploader(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["upload_api.py", str(tmp_path)])
    monkeypatch.setattr(
        upload_api, "upload_via_api",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("direct upload reached")),
    )

    assert upload_api.main() == 2


def test_legacy_agent_cli_rejects_upload_without_reviewed_inputs(monkeypatch):
    class FakeCrew:
        def run_end_to_end(self, **kwargs):
            raise AssertionError("production started")

    monkeypatch.setattr(agents, "OrchestratorAgent", FakeCrew)
    monkeypatch.setattr(
        sys, "argv", ["agents.py", "--run", "--topic", "Test", "--id", "SH-99", "--slug", "short_test", "--upload"],
    )

    assert agents.main() == 2


def test_legacy_agent_cli_rejects_upload_outside_run(monkeypatch):
    class FakeCrew:
        def __init__(self):
            raise AssertionError("crew was started")

    monkeypatch.setattr(agents, "OrchestratorAgent", FakeCrew)
    monkeypatch.setattr(sys, "argv", ["agents.py", "--status", "--upload"])

    assert agents.main() == 2
