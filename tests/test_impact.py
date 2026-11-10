"""tests/test_impact.py - the change-propagation index the release gate now depends on.

`tools/orchestrator/impact.py` exists because the 2026-11-01 thumbnail deletion left references in
six source files, three tests and six documents, and no existing gate noticed: ruff only sees code,
the contract tests only read project.json, and audit only walked projects. So this file checks both
halves - that the index finds a dangling reference, and that the live repo currently has none of the
critical kind.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.orchestrator import impact  # noqa: E402


def build_repo(tmp_path: Path) -> Path:
    """A two-file repo plus one document, arranged so every rule has one violation."""
    tools = tmp_path / "tools"
    (tools / "orchestrator").mkdir(parents=True)
    (tmp_path / "channel_assets").mkdir()

    (tools / "pipeline.py").write_text(
        "from tools import kept  # noqa\n"
        "from tools import gone  # noqa\n"
        'def main():\n    ap.add_argument("--build", help="x")\n',
        encoding="utf-8",
    )
    (tools / "kept.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tools / "worker.py").write_text(
        'TOOLS_DIR = Path(".")\nsubprocess.run([str(TOOLS_DIR / "gone_worker.py")])\n', encoding="utf-8"
    )
    (tools / "orchestrator" / "verifiers.py").write_text(
        'def verifier(name):\n    return lambda fn: fn\n\n@verifier("render")\ndef verify_render():\n    return []\n',
        encoding="utf-8",
    )
    (tools / "orchestrator" / "workflows.py").write_text(
        'verifiers=["render", "thumbnail"]\ndepends_on=["build"]\nkind="release"\n',
        encoding="utf-8",
    )
    (tmp_path / "GUIDE.md").write_text(
        "# Guide\n"
        "```\n"
        "python tools/pipeline.py --gone\n"
        "python tools/master.py thumbnails --all\n"
        "```\n"
        "See tools/gone_module.py for the engine.\n"
        # Built in two pieces so this file does not itself contain a dangling line citation -
        # the index scans test sources too, and correctly flagged these strings the first time.
        "Cite " + "tools/pipeline" + ".py:9999 for the gate.\n"
        "Cite " + "tools/deleted" + ".py:3 for the old gate.\n"
        "Plate: channel_assets/absent.png\n",
        encoding="utf-8",
    )
    return tmp_path


def rules(findings: list[impact.Finding]) -> set[str]:
    return {f.rule for f in findings}


def test_the_index_finds_every_class_of_dangling_reference(tmp_path):
    index = impact.Index(build_repo(tmp_path))
    found = rules(impact.find_stale(index))
    assert "broken-import" in found, "an import of a module that is gone must be reported"
    assert "missing-script" in found, "a document naming a deleted script must be reported"
    assert "doc-unknown-flag" in found, "a document showing a flag the script never had must be reported"
    assert "citation-missing-file" in found, "a citation to a deleted file must be reported"
    assert "citation-past-end-of-file" in found, "a line citation past the end must be reported"
    assert "unregistered-verifier" in found, "a DAG task asking for a deleted verifier must be reported"
    assert "missing-asset" in found, "a checked-in asset path that is not on disk must be reported"


def test_a_clean_repo_reports_nothing(tmp_path):
    repo = build_repo(tmp_path)
    (repo / "tools" / "pipeline.py").write_text(
        'from tools import kept  # noqa\nVALUE = 1\n\n\ndef main():\n    ap.add_argument("--build", help="x")\n',
        encoding="utf-8",
    )
    (repo / "tools" / "orchestrator" / "workflows.py").write_text(
        'verifiers=["render"]\nkind="release"\n', encoding="utf-8"
    )
    (repo / "tools" / "worker.py").write_text(
        'TOOLS_DIR = Path(".")\nsubprocess.run([str(TOOLS_DIR / "kept.py")])\n', encoding="utf-8"
    )
    (repo / "GUIDE.md").write_text(
        "python tools/pipeline.py --build\nSee tools/kept.py.\nCite tools/pipeline.py:5 for the gate.\n",
        encoding="utf-8",
    )
    findings = impact.find_stale(impact.Index(repo))
    assert [f.detail for f in findings] == [], [str(f) for f in findings]


def test_critical_and_drift_are_separated(tmp_path):
    """A dangling import fails a release; a stale line number in a guide is only worth reporting."""
    findings = impact.find_stale(impact.Index(build_repo(tmp_path)))
    critical, warnings = impact.split_findings(findings)
    assert {"broken-import", "unregistered-verifier"} <= {f.rule for f in critical}

    # The same rule splits by where the reference lives: code that shells out to a deleted script
    # crashes, a document naming one has merely drifted.
    code_scripts = [f for f in critical if f.rule == "missing-script"]
    doc_scripts = [f for f in warnings if f.rule == "missing-script"]
    assert any("gone_worker.py" in f.detail for f in code_scripts), [f.detail for f in code_scripts]
    assert any("gone_module.py" in f.detail for f in doc_scripts), [f.detail for f in doc_scripts]
    assert {"citation-past-end-of-file", "doc-unknown-flag", "missing-asset"} <= {f.rule for f in warnings}
    assert not any(
        f.rule in impact.CRITICAL_RULES and impact.severity(f) == "critical" for f in warnings
    )


def test_unknown_subcommand_is_reported_against_the_cli_that_owns_it(tmp_path):
    repo = build_repo(tmp_path)
    (repo / "tools" / "master.py").write_text("raise SystemExit()\n", encoding="utf-8")
    (repo / "tools" / "orchestrator" / "cli.py").write_text(
        'sub.add_parser("produce")\nsub.add_parser("audit")\n'
        'ap.add_argument("--json")\n',
        encoding="utf-8",
    )
    details = [f.detail for f in impact.find_stale(impact.Index(repo))]
    assert any("thumbnails" in d for d in details), details


def test_impact_lists_the_sites_that_still_name_a_deleted_module(tmp_path):
    index = impact.Index(build_repo(tmp_path))
    sites = impact.impact(index, name="gone_module")
    assert any(s.file == "GUIDE.md" and s.kind == "doc-script" for s in sites), [str(s) for s in sites]
    assert impact.impact(index, path="tools/pipeline.py"), "a path query must resolve to its basename"


def test_impact_on_a_name_nothing_references_returns_nothing(tmp_path):
    index = impact.Index(build_repo(tmp_path))
    assert impact.impact(index, name="never_existed") == []
    with pytest.raises(ValueError):
        impact.impact(index)


def test_prepare_release_cli_and_documented_flags_resolve():
    index = impact.Index(ROOT)
    sites = impact.impact(index, name="prepare-release")
    assert any(site.kind == "subcommand-declared" and site.file == "tools/orchestrator/cli.py" for site in sites)
    findings = impact.check_documented_flags(index)
    assert not [finding for finding in findings if "prepare-release" in finding.detail]


def test_a_file_that_does_not_parse_is_raised_not_skipped(tmp_path):
    repo = build_repo(tmp_path)
    (repo / "tools" / "broken.py").write_text("def main(:\n", encoding="utf-8")
    with pytest.raises(SyntaxError):
        impact.Index(repo)


def workflow_dependency_findings(tmp_path, source):
    directory = tmp_path / "tools" / "orchestrator"
    directory.mkdir(parents=True)
    (directory / "workflows.py").write_text(source, encoding="utf-8")
    # A registered worker kind is deliberately not a declaration of a task with that id.
    (directory / "workers.py").write_text('class BuildWorker:\n    kind = "build"\n', encoding="utf-8")
    index = impact.Index(tmp_path)
    return index, [finding for finding in impact.check_registries(index)
                   if finding.rule == "unknown-task-dependency"]


def test_dependency_references_and_worker_kinds_do_not_declare_tasks(tmp_path):
    index, findings = workflow_dependency_findings(tmp_path, '''
def produce():
    return [TaskSpec(id="release", kind="build", depends_on=["build"])]
''')
    assert len(findings) == 1
    assert 'task id "build"' in findings[0].detail
    assert impact.severity(findings[0]) == "critical"
    assert findings[0].sites[0].kind == "dag-dependency"
    assert all("build" not in ids for ids in index.workflow_task_ids.values())


def test_a_task_in_another_workflow_cannot_satisfy_a_missing_dependency(tmp_path):
    _, findings = workflow_dependency_findings(tmp_path, '''
def unrelated():
    return [TaskSpec(id="build", kind="build")]

def produce():
    return [TaskSpec(id="release", kind="build", depends_on=["build"])]
''')
    assert len(findings) == 1
    assert "produce" in findings[0].detail


def test_real_declarations_satisfy_forward_and_positional_task_dependencies(tmp_path):
    index, findings = workflow_dependency_findings(tmp_path, '''
def produce():
    return [
        TaskSpec(id="release", kind="build", depends_on=["prepare"]),
        TaskSpec("prepare", "build", "Prepare source"),
    ]
''')
    assert findings == []
    sites = impact.impact(index, name="prepare")
    assert {site.kind for site in sites} == {"dag-task", "dag-dependency"}


def test_nested_workflow_does_not_borrow_its_parent_task_declarations(tmp_path):
    _, findings = workflow_dependency_findings(tmp_path, '''
def outer():
    parent = TaskSpec(id="build", kind="build")
    def inner():
        return [TaskSpec(id="release", kind="build", depends_on=["build"])]
    return parent
''')
    assert len(findings) == 1
    assert "inner" in findings[0].detail


def test_module_level_task_declarations_are_indexed(tmp_path):
    _, findings = workflow_dependency_findings(tmp_path, '''
tasks = [
    TaskSpec(id="build", kind="build"),
    TaskSpec(id="release", kind="build", depends_on=["build"]),
]
''')
    assert findings == []


def test_dynamic_task_declarations_defer_unresolved_dependencies_to_runtime(tmp_path):
    index, findings = workflow_dependency_findings(tmp_path, '''
def produce():
    tasks = [TaskSpec(task_id, "build", task_id) for task_id in ["prepare"]]
    tasks.append(TaskSpec("release", "build", "Release", depends_on=["prepare"]))
    return tasks
''')
    assert findings == []
    assert index.dynamic_task_scopes
    assert any(site.kind == "dag-dependency" for site in impact.impact(index, name="prepare"))


def test_dynamic_task_scope_does_not_hide_another_workflows_missing_dependency(tmp_path):
    _, findings = workflow_dependency_findings(tmp_path, '''
def dynamic():
    return [TaskSpec(task_id, "build", task_id) for task_id in ["prepare"]]

def static():
    return [TaskSpec("release", "build", "Release", depends_on=["prepare"])]
''')
    assert len(findings) == 1
    assert "static" in findings[0].detail


def test_runtime_validation_rejects_missing_dynamically_constructed_tasks(tmp_path):
    from tools.orchestrator.contracts import TaskSpec
    from tools.orchestrator.master import MasterAgent

    tasks = [TaskSpec(task_id, "build", task_id) for task_id in ["different"]]
    tasks.append(TaskSpec("release", "build", "Release", depends_on=["prepare"]))
    master = MasterAgent(tmp_path, workers={"build": object()}, verifiers={})
    with pytest.raises(ValueError, match="unknown task 'prepare'"):
        master.validate(tasks)


def test_called_task_factories_supply_ids_in_the_calling_workflow(tmp_path):
    _, findings = workflow_dependency_findings(tmp_path, '''
def prepare():
    return TaskSpec("prepare", "build", "Prepare")
def source_tasks():
    return [prepare()]
def produce():
    return [*source_tasks(), TaskSpec("release", "build", "Release", depends_on=["prepare"])]
''')
    assert findings == []


def test_task_from_dict_defers_dynamic_dependencies_to_runtime(tmp_path):
    index, findings = workflow_dependency_findings(tmp_path, '''
def produce(data):
    tasks = [TaskSpec.from_dict(item) for item in data]
    tasks.append(TaskSpec("release", "build", "Release", depends_on=["prepare"]))
    return tasks
''')
    assert findings == []
    assert index.dynamic_task_scopes


def test_factory_dependencies_are_checked_in_each_calling_workflow(tmp_path):
    _, findings = workflow_dependency_findings(tmp_path, '''
def release_task():
    return TaskSpec("release", "build", "Release", depends_on=["prepare"])
def complete():
    return [TaskSpec("prepare", "build", "Prepare"), release_task()]
def incomplete():
    return [release_task()]
''')
    assert len(findings) == 1
    assert "incomplete" in findings[0].detail


def test_nested_task_factory_resolves_without_borrowing_unrelated_scope(tmp_path):
    _, findings = workflow_dependency_findings(tmp_path, '''
def produce():
    def prepare():
        return TaskSpec("prepare", "build", "Prepare")
    return [prepare(), TaskSpec("release", "build", "Release", depends_on=["prepare"])]
def unrelated():
    return [TaskSpec("release", "build", "Release", depends_on=["prepare"])]
''')
    assert len(findings) == 1
    assert "unrelated" in findings[0].detail


# --------------------------------------------------------------------------- #
# the live repo
# --------------------------------------------------------------------------- #
def test_the_live_repo_has_no_critical_dangling_reference():
    """The gate's own guarantee: nothing in `tools/` names a module, script or verifier that is gone."""
    index = impact.Index(ROOT)
    critical, _ = impact.split_findings(impact.find_stale(index))
    assert [f.detail for f in critical] == [], "\n".join(str(f) for f in critical)
    assert "thumbnail" not in index.verifier_names
    assert index.worker_kinds and "thumbnail" not in index.worker_kinds
    assert index.modules and impact.summary(index)["modules"] >= 30, "the index must cover the real tree"


def test_the_live_repo_leaves_no_shorts_thumbnail_pipeline_reference():
    """Shorts thumbnail pipeline is forbidden, while long-form 16:9 thumbnail generator exists in tools.branding_engine."""
    from tools import branding_engine

    index = impact.Index(ROOT)
    findings = impact.find_stale(index)
    assert [str(f) for f in findings] == [], "still dangling:\n" + "\n".join(str(f) for f in findings)
    assert "thumbnail" not in index.verifier_names
    assert index.worker_kinds and "thumbnail" not in index.worker_kinds
    assert hasattr(branding_engine, "render_longform_thumbnail"), "Long-form thumbnail generator must exist in branding_engine"
