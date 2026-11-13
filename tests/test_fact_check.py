"""Tests for the fact-check layer: live-web verification of factual claims, fiction
exemption, and the offline-safe gates that enforce them. No test touches the network;
the Exa search function is injected or monkeypatched."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from tools import creative_engine as ce
from tools import fact_check as fc
from tools.orchestrator.contracts import TaskSpec, WorkerResult
from tools.orchestrator.verifiers import verify_factcheck, verify_research
from tools.orchestrator.workers import FactCheckWorker, ResearchWorker
from tools.schemas import validate_project


def _project(content_type="factual", scenes=None):
    return {
        "schema_version": 2,
        "id": "SH-1",
        "variant": "cinematic_35mm",
        "format": "short",
        "channel_id": "default",
        "voice": "kokoro",
        "content_type": content_type,
        "scenes": scenes if scenes is not None else [
            {"id": f"s{i:02d}", "text": "t", "caption": "c", "prompt": "p"} for i in range(1, 9)
        ],
    }


# --------------------------------------------------------------------------- #
# claim extraction
# --------------------------------------------------------------------------- #
def test_extract_claims_pulls_numbers_and_study_markers_not_narration():
    scenes = [
        {"text": "A 2019 study found 73% of people freeze."},
        {"text": "You walk into a room and forget why."},
        {"text": "Researchers at Stanford measured 12 subjects."},
    ]
    claims = fc.extract_claims(scenes)
    texts = [c["text"] for c in claims]
    assert "A 2019 study found 73% of people freeze." in texts
    assert "Researchers at Stanford measured 12 subjects." in texts
    assert "You walk into a room and forget why." not in texts
    assert claims[0]["numbers"] == ["2019", "73"]
    assert "Stanford" in claims[1]["entities"]


# --------------------------------------------------------------------------- #
# fiction exemption — must not touch the network
# --------------------------------------------------------------------------- #
def test_fiction_is_exempt_without_any_search():
    def boom(_query):
        raise AssertionError("fiction must not search the web")

    report = fc.check_script(
        [{"text": "In 1999 the dragon burned 3 cities."}], content_type="fiction", search_fn=boom
    )
    assert report["status"] == "exempt" and report["passed"] is True
    assert report["checked"] == 0 and report["claims"] == []


def test_check_project_reads_content_type_from_the_project():
    report = fc.check_project(_project("fiction", [{"text": "A 2019 study found 73%."}]))
    assert report["status"] == "exempt"


# --------------------------------------------------------------------------- #
# no silent fallback: a factual check with no key raises with the fix command
# --------------------------------------------------------------------------- #
def test_factual_without_key_raises_with_fix_command(monkeypatch):
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    with pytest.raises(fc.FactCheckError) as exc:
        fc.check_script([{"text": "A 2019 study found 73% of people freeze."}], content_type="factual")
    assert "EXA_API_KEY" in str(exc.value)


def test_normalize_content_type_rejects_unknown():
    assert fc.normalize_content_type(None) == "factual"
    assert fc.normalize_content_type("FICTION") == "fiction"
    with pytest.raises(fc.FactCheckError):
        fc.normalize_content_type("bogus")


# --------------------------------------------------------------------------- #
# corroboration: a claim passes only when a live source actually contains it
# --------------------------------------------------------------------------- #
def _search_returning(sources):
    return lambda _query: sources


def test_corroborated_when_source_contains_the_numbers_and_entity():
    sources = [{"title": "Paper", "url": "https://example.org/a", "text": "A 2019 Stanford study found 73% freeze."}]
    report = fc.check_script(
        [{"text": "A 2019 Stanford study found 73% of people freeze."}],
        content_type="factual", search_fn=_search_returning(sources),
    )
    assert report["status"] == "passed" and report["passed"] is True
    assert report["claims"][0]["verdict"] == "corroborated"
    assert report["claims"][0]["sources"][0]["url"] == "https://example.org/a"


def test_unverified_when_no_source_matches_and_flagged():
    sources = [{"title": "Cats", "url": "https://example.org/cats", "text": "Cats are nice."}]
    report = fc.check_script(
        [{"text": "Scientists say 99% of cats fly."}],
        content_type="factual", search_fn=_search_returning(sources),
    )
    assert report["status"] == "flagged" and report["passed"] is False
    assert report["claims"][0]["verdict"] == "unverified"
    assert report["flags"] and "99% of cats fly" in report["flags"][0]


def test_no_checkable_claims_passes_without_search():
    def boom(_query):
        raise AssertionError("nothing to check")

    report = fc.check_script([{"text": "You walk into a room."}], content_type="factual", search_fn=boom)
    assert report["status"] == "passed" and report["checked"] == 0


# --------------------------------------------------------------------------- #
# schema contract
# --------------------------------------------------------------------------- #
def test_schema_accepts_factual_and_fiction_and_rejects_unknown():
    assert validate_project(_project("factual")) == []
    assert validate_project(_project("fiction")) == []
    assert any("content_type" in e for e in validate_project(_project("bogus")))
    base = _project()
    base.pop("content_type")
    assert validate_project(base) == []  # absent means factual, back-compat


def test_generate_creative_project_stamps_content_type(tmp_path):
    factual = ce.generate_creative_project(
        "Loss Aversion", "SH-99", "short_99_factual", output_root=tmp_path / "shorts"
    )
    assert json.loads(factual.read_text(encoding="utf-8"))["content_type"] == "factual"
    fiction = ce.generate_creative_project(
        "Loss Aversion", "SH-98", "short_98_fiction", output_root=tmp_path / "shorts", content_type="fiction"
    )
    proj = json.loads(fiction.read_text(encoding="utf-8"))
    assert proj["content_type"] == "fiction"
    assert validate_project(proj, project_path=fiction) == []


# --------------------------------------------------------------------------- #
# research worker / verifier fiction exemption
# --------------------------------------------------------------------------- #
def test_research_worker_exempts_fiction(tmp_path):
    spec = TaskSpec("research", "research", "research", params={"topic": "A Story", "content_type": "fiction"})
    result = ResearchWorker().run(spec, SimpleNamespace(root=tmp_path))
    assert result.ok and result.data["content_type"] == "fiction"
    assert result.data["fact_check"]["status"] == "exempt"
    checks = verify_research(spec, result, None)
    assert any(c.name == "research_fiction_exempt" and c.passed for c in checks)


# --------------------------------------------------------------------------- #
# fact-check worker
# --------------------------------------------------------------------------- #
class _Ctx:
    def __init__(self, root, dossier=None):
        self.root = root
        self._dossier = dossier or {}

    def project_json(self):
        return self.root / "project.json"

    def dep_data(self, _name):
        return {"dossier": self._dossier}


def _write_project(tmp_path, project):
    path = tmp_path / "project.json"
    path.write_text(json.dumps(project), encoding="utf-8")
    return path


def test_factcheck_worker_fiction_writes_exempt_report(tmp_path):
    path = _write_project(tmp_path, _project("fiction"))
    spec = TaskSpec("factcheck", "factcheck", "fc", params={"project_json": str(path), "content_type": "fiction"})
    result = FactCheckWorker().run(spec, _Ctx(tmp_path))
    assert result.ok and result.data["fact_check"]["status"] == "exempt"
    assert (tmp_path / "fact_check.json").exists()


def test_factcheck_worker_factual_with_verified_dossier_is_satisfied(tmp_path):
    path = _write_project(tmp_path, _project("factual"))
    dossier = {"_verified": True, "_synthetic": False, "topic": "Loss Aversion"}
    spec = TaskSpec("factcheck", "factcheck", "fc", params={"project_json": str(path)})
    result = FactCheckWorker().run(spec, _Ctx(tmp_path, dossier))
    assert result.ok and result.data["fact_check"]["status"] == "satisfied_by_dossier"


def test_factcheck_worker_factual_no_dossier_no_key_fails_closed(tmp_path, monkeypatch):
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    scenes = [{"id": "s01", "text": "A 2019 study found 73% freeze.", "caption": "c", "prompt": "p"}]
    path = _write_project(tmp_path, _project("factual", scenes))
    spec = TaskSpec("factcheck", "factcheck", "fc", params={"project_json": str(path)})
    result = FactCheckWorker().run(spec, _Ctx(tmp_path))
    assert not result.ok and not result.retryable
    assert "EXA_API_KEY" in result.error


def test_factcheck_worker_factual_live_web_corroborates(tmp_path, monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    monkeypatch.setattr(
        fc, "_exa_search",
        lambda query, **kw: [{"title": "Paper", "url": "https://example.org/a", "text": "A 2019 study found 73% freeze."}],
    )
    scenes = [{"id": "s01", "text": "A 2019 study found 73% freeze.", "caption": "c", "prompt": "p"}]
    path = _write_project(tmp_path, _project("factual", scenes))
    spec = TaskSpec("factcheck", "factcheck", "fc", params={"project_json": str(path)})
    result = FactCheckWorker().run(spec, _Ctx(tmp_path))
    assert result.ok and result.data["fact_check"]["status"] == "passed"


# --------------------------------------------------------------------------- #
# fact-check verifier (offline, reads the written report)
# --------------------------------------------------------------------------- #
def _report_result(tmp_path, report):
    path = tmp_path / "fact_check.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return WorkerResult(True, "ok", artifacts={"fact_check": str(path)}, data={"fact_check": report})


def test_verify_factcheck_accepts_fiction_exempt(tmp_path):
    result = _report_result(tmp_path, fc.exempt_report("fiction"))
    spec = TaskSpec("factcheck", "factcheck", "fc", params={"content_type": "fiction"})
    checks = verify_factcheck(spec, result, None)
    assert all(c.passed for c in checks), checks


def test_verify_factcheck_accepts_corroborated_factual(tmp_path):
    report = {
        "content_type": "factual", "status": "passed", "passed": True, "checked": 1, "flags": [],
        "claims": [{"scene": 1, "text": "x", "verdict": "corroborated",
                    "sources": [{"title": "P", "url": "https://example.org/a"}]}],
    }
    result = _report_result(tmp_path, report)
    checks = verify_factcheck(TaskSpec("factcheck", "factcheck", "fc"), result, None)
    assert all(c.passed for c in checks), checks


def test_verify_factcheck_rejects_flagged_factual(tmp_path):
    report = {
        "content_type": "factual", "status": "flagged", "passed": False, "checked": 1,
        "flags": ["scene 1: 99% of cats fly"],
        "claims": [{"scene": 1, "text": "99% of cats fly", "verdict": "unverified", "sources": []}],
    }
    result = _report_result(tmp_path, report)
    checks = verify_factcheck(TaskSpec("factcheck", "factcheck", "fc"), result, None)
    assert any(not c.passed for c in checks)


def test_verify_factcheck_rejects_corroborated_claim_without_https_source(tmp_path):
    report = {
        "content_type": "factual", "status": "passed", "passed": True, "checked": 1, "flags": [],
        "claims": [{"scene": 1, "text": "x", "verdict": "corroborated", "sources": [{"url": "http://insecure"}]}],
    }
    result = _report_result(tmp_path, report)
    checks = verify_factcheck(TaskSpec("factcheck", "factcheck", "fc"), result, None)
    assert any(c.name == "factcheck_claim_sources" and not c.passed for c in checks)


def test_verify_factcheck_missing_report_fails(tmp_path):
    result = WorkerResult(True, "ok", artifacts={"fact_check": str(tmp_path / "nope.json")})
    checks = verify_factcheck(TaskSpec("factcheck", "factcheck", "fc"), result, None)
    assert any(not c.passed for c in checks)