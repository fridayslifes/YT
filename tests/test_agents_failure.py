"""The compatibility command must report failed stages and stop before upload."""

from __future__ import annotations

import sys
from types import SimpleNamespace

from tools import agents, pipeline


def _report(status: str, name: str = "stage") -> agents.AgentReport:
    return agents.AgentReport(name, name, status, 0.0, name)


def test_legacy_agent_command_exits_nonzero_after_failed_stage(monkeypatch):
    class FakeCrew:
        def run_end_to_end(self, **kwargs):
            return [_report("FAIL")]

    monkeypatch.setattr(agents, "OrchestratorAgent", FakeCrew)
    monkeypatch.setattr(
        sys,
        "argv",
        ["agents.py", "--run", "--topic", "Test", "--id", "SH-99", "--slug", "short_test"],
    )

    assert agents.main() == 2


def test_pipeline_auto_exits_nonzero_after_failed_stage(monkeypatch):
    class FakeCrew:
        def run_end_to_end(self, **kwargs):
            return [_report("FAIL")]

    monkeypatch.setattr(agents, "OrchestratorAgent", FakeCrew)
    monkeypatch.setattr(
        sys,
        "argv",
        ["pipeline.py", "--auto", "--topic", "Test", "--id", "SH-99", "--slug", "short_test"],
    )

    assert pipeline.main() == 2


def test_agents_run_routes_once_through_canonical_adapter(monkeypatch):
    calls = []
    monkeypatch.setattr(
        agents.legacy, "run_production_compat",
        lambda **kwargs: calls.append(kwargs) or SimpleNamespace(status="failed", tasks={}),
    )
    monkeypatch.setattr(
        sys, "argv", ["agents.py", "--run", "--topic", "Test", "--id", "SH-99", "--slug", "short_test"],
    )
    assert agents.main() == 2
    assert len(calls) == 1
    assert calls[0]["topic"] == "Test"


def test_pipeline_auto_routes_once_through_canonical_adapter(monkeypatch):
    calls = []
    monkeypatch.setattr(
        agents.legacy, "run_production_compat",
        lambda **kwargs: calls.append(kwargs) or SimpleNamespace(status="failed", tasks={}),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["pipeline.py", "--auto", "--topic", "Test", "--id", "SH-99", "--slug", "short_test"],
    )
    assert pipeline.main() == 2
    assert len(calls) == 1
    assert calls[0]["blueprint_only"] is False


def test_legacy_crew_does_not_upload_after_failed_quality_gate(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        agents.legacy, "run_production_compat",
        lambda **kwargs: calls.append(kwargs) or SimpleNamespace(status="failed", tasks={}),
    )
    monkeypatch.setattr(
        "tools.orchestrator.cli.run_release_existing",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("strict release reached")),
    )

    reports = agents.OrchestratorAgent().run_end_to_end(
        "Test", "SH-99", "short_test", upload=True,
        evidence=tmp_path / "reviewed-evidence.json", approved=True,
    )

    assert len(calls) == 1
    assert calls[0]["topic"] == "Test"
    assert any(r.status == "FAIL" for r in reports)
    assert any(r.agent_name == "PublishAgent" and r.status == "SKIPPED" for r in reports)


def test_legacy_publisher_requires_reviewed_evidence_and_approval(tmp_path, monkeypatch):
    from tools import upload_api

    monkeypatch.setattr(
        upload_api, "upload_via_api",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("direct upload reached")),
    )

    assert agents.PublishAgent().run(tmp_path, approved=True).status == "FAIL"
    assert agents.PublishAgent().run(tmp_path, evidence=tmp_path / "evidence.json").status == "FAIL"


def test_legacy_publisher_uses_strict_release_and_needs_remote_id(tmp_path, monkeypatch):
    from tools.orchestrator import cli

    calls = []

    def fake_release(project, evidence, **kwargs):
        calls.append((project, evidence, kwargs))
        return SimpleNamespace(
            status="passed", run_id="reviewed-run", report_path=tmp_path / "REPORT.md",
            tasks={"publish": SimpleNamespace(data={})},
        )

    monkeypatch.setattr(cli, "run_release_existing", fake_release)
    evidence = tmp_path / "evidence.json"
    report = agents.PublishAgent().run(tmp_path, evidence=evidence, approved=True, public=True)

    assert report.status == "FAIL"
    assert calls == [(tmp_path / "project.json", evidence, {"publish": True, "public": True, "approve": True})]


def test_legacy_publisher_reports_strict_release_success(tmp_path, monkeypatch):
    from tools.orchestrator import cli

    monkeypatch.setattr(
        cli, "run_release_existing",
        lambda *args, **kwargs: SimpleNamespace(
            status="passed", run_id="reviewed-run", report_path=tmp_path / "REPORT.md",
            tasks={"publish": SimpleNamespace(data={"video_id": "abcdefghijk"})},
        ),
    )

    report = agents.PublishAgent().run(tmp_path, evidence=tmp_path / "evidence.json", approved=True)

    assert report.status == "PASS"
    assert report.metrics["remote_id"] == "abcdefghijk"


def test_research_agent_blocks_copyrighted_fiction():
    agent = agents.ResearchAgent()
    dossier, report = agent.run("Marvel Iron Man Suit Science")
    assert report.status == "FAIL"
    assert "BLOCKED by IP Guard" in report.summary
    assert report.metrics["copyright_cleared"] is False


def test_research_agent_blocks_pseudoscience_falsehoods():
    agent = agents.ResearchAgent()
    dossier, report = agent.run("Flat Earth Horizon Geometry")
    assert report.status == "FAIL"
    assert "BLOCKED by Fact-Check Guard" in report.summary
    assert report.metrics["truth_verified"] is False


def test_research_agent_dynamically_verifies_valid_science():
    agent = agents.ResearchAgent()
    dossier, report = agent.run("Loss Aversion")
    assert report.status == "PASS"
    assert report.metrics["truth_verified"] is True
    assert dossier["topic"] == "Loss Aversion"


def test_research_agent_fails_closed_on_unverified_topic():
    agent = agents.ResearchAgent()
    dossier, report = agent.run("Unverified Random Pseudoscience Trend 999")
    assert report.status == "FAIL"
    assert "FAILED Research Gate" in report.summary
    assert report.metrics["truth_verified"] is False
    assert dossier == {}


