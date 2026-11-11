"""Tests for tools/guard.py — verifies post-change guard and storyline continuity."""

from __future__ import annotations

from tools import guard


def test_guard_all_gates_pass():
    report = guard.run_guard()
    assert report["passed"] is True, report["gates"]
    for gate in report["gates"]:
        assert gate["passed"] is True, f"{gate['gate']} failed: {gate['failures']}"


def test_guard_cli_exits_zero(capsys):
    rc = guard.main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "OVERALL GUARD VERDICT: PASSED" in out
    assert "BEFORE vs. AFTER EFFECT COMPARISON:" in out


def test_guard_passes_on_sample_dossiers():
    from pathlib import Path

    sample = Path(__file__).resolve().parent / "fixtures" / "sample_dossiers.json"
    report = guard.run_guard(dossiers_path=sample)
    assert report["passed"] is True, report["gates"]
    for gate in report["gates"]:
        assert gate["passed"] is True, f"{gate['gate']} failed: {gate['failures']}"
