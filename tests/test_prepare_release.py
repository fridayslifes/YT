"""Draft preparation copies only supplied facts and never grants release approval."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from test_schemas import project_data, evidence_data

ROOT = Path(__file__).resolve().parents[1]


def test_draft_keeps_review_fields_empty_and_project_unchanged(tmp_path):
    from tools.schemas import prepare_release_draft, validate_evidence

    project = project_data()
    project["citation_verified"] = False
    path = tmp_path / "project.json"
    path.write_text(json.dumps(project))
    original = path.read_bytes()
    output = tmp_path / "draft.json"
    assert prepare_release_draft(path, output) == output
    draft = json.loads(output.read_text())
    assert draft["schema_version"] == 1
    assert draft["status"] == "draft"
    assert draft["video_id"] == "SH-99"
    assert draft["script_sha256"] == evidence_data()["script_sha256"]
    assert draft["primary_source"] == {"title": "", "authors": [], "year": "", "publication": "", "url": ""}
    assert draft["claims"] == [] and draft["editorial_suggestions"] == []
    assert path.read_bytes() == original
    assert any("status" in error and "unreviewed" in error for error in validate_evidence(draft))


def test_draft_copies_only_present_dossier_and_project_fields(tmp_path):
    from tools.schemas import prepare_release_draft

    project = project_data()
    project["claims"] = [{"id": "C1", "paraphrase": "A supplied claim", "used_by": ["scene_1"]}]
    project["editorial_suggestions"] = [{"id": "E1", "text": "A supplied suggestion"}]
    path = tmp_path / "project.json"
    path.write_text(json.dumps(project))
    dossier = {"topic": "Supplied topic", "publication": "Supplied journal", "year": "1999", "_verified": True}
    output = tmp_path / "draft.json"
    prepare_release_draft(path, output, dossier=dossier)
    draft = json.loads(output.read_text())
    assert draft["dossier"] == dossier
    assert draft["primary_source"]["publication"] == "Supplied journal"
    assert draft["primary_source"]["year"] == "1999"
    assert draft["primary_source"]["authors"] == []
    assert draft["claims"][0] == {"id": "C1", "paraphrase": "A supplied claim", "used_by": ["scene_1"],
                                  "printed_page_locator": "", "support_summary": ""}
    assert draft["editorial_suggestions"][0]["status"] == ""
    assert draft["status"] == "draft"


def test_cli_prepares_default_draft_without_building(tmp_path):
    path = tmp_path / "project.json"
    path.write_text(json.dumps(project_data()))
    command = subprocess.run([sys.executable, str(ROOT / "tools/master.py"), "prepare-release", "--project", str(path)],
                             capture_output=True, text=True, timeout=20)
    assert command.returncode == 0, command.stderr
    draft = tmp_path / "release_evidence.draft.json"
    assert json.loads(draft.read_text())["status"] == "draft"
    assert "draft" in command.stdout and "unreviewed" in command.stdout
    assert sorted(p.name for p in tmp_path.iterdir()) == ["project.json", "release_evidence.draft.json"]


@pytest.mark.parametrize("existing", ["project.json", "reviewed.json"])
def test_preparation_cannot_overwrite_project_or_existing_evidence(tmp_path, existing):
    from tools.schemas import prepare_release_draft

    path = tmp_path / "project.json"
    path.write_text(json.dumps(project_data()))
    output = tmp_path / existing
    if output != path:
        output.write_text('{"status": "reviewed"}')
    before = output.read_bytes()
    with pytest.raises(ValueError, match="exist|overwrite|project"):
        prepare_release_draft(path, output)
    assert output.read_bytes() == before


def test_cli_invalid_project_reports_all_errors_without_output(tmp_path):
    path = tmp_path / "project.json"
    path.write_text('{"id": "../bad", "format": "invalid", "scenes": []}')
    output = tmp_path / "draft.json"
    command = subprocess.run([sys.executable, str(ROOT / "tools/master.py"), "prepare-release", "--project", str(path),
                              "--output", str(output)], capture_output=True, text=True, timeout=20)
    assert command.returncode == 1
    assert "id" in command.stderr and "format" in command.stderr and "scenes" in command.stderr
    assert not output.exists()
