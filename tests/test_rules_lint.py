"""Automated Lint Tests for Global Rule A (No Hardcoded Values) and Global Rule B (No Fallbacks).

Enforces repository-wide hygiene:
- Zero bare `except:` across `tools/`.
- Zero `except ...: pass` across `tools/`.
- Zero hardcoded demo phrases in `tools/`.
- Zero imports of `demos` or `tests.fixtures` in production `tools/`.
- No root `demos/` directory (all demos live under `tests/fixtures/`).
- Banned default fallback strings (e.g. `or "Cognitive Science"`).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import List

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"

DEMO_PHRASE_DENYLIST = [
    "wall street 1920",
    "d.b. cooper",
    "db cooper",
    "florence schaffner",
    "tina bar",
    "brian ingram",
    "ralph himmelsbach",
    "3 prisoners hat riddle",
    "quantum vault 7",
    "2 am productive procrastination",
]


def _collect_tools_py_files() -> List[Path]:
    return sorted(p for p in TOOLS_DIR.rglob("*.py") if p.is_file())


def test_no_demos_directory_in_repo_root() -> None:
    """Production code must never import from a root demos directory."""
    demos_dir = REPO_ROOT / "demos"
    assert not demos_dir.exists(), f"Found root demos/ directory at {demos_dir}. Demos must reside exclusively under tests/fixtures/."


def test_no_production_import_of_test_fixtures() -> None:
    """Production files under tools/ must never import tests or fixtures."""
    violations: List[str] = []
    for py_file in _collect_tools_py_files():
        rel_path = py_file.relative_to(REPO_ROOT)
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(("tests", "fixtures", "demos")):
                        violations.append(f"{rel_path}:{node.lineno} imports '{alias.name}'")
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod.startswith(("tests", "fixtures", "demos")):
                    violations.append(f"{rel_path}:{node.lineno} imports from '{mod}'")

    assert not violations, "Found production tools importing tests/fixtures/demos:\n" + "\n".join(violations)


def test_no_bare_except_in_tools() -> None:
    """Rule B: Zero bare `except:` statements permitted in tools/."""
    violations: List[str] = []
    for py_file in _collect_tools_py_files():
        rel_path = py_file.relative_to(REPO_ROOT)
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                violations.append(f"{rel_path}:{node.lineno} has bare except:")

    assert not violations, "Rule B violation: bare except: found in tools/:\n" + "\n".join(violations)


def test_no_except_pass_in_tools() -> None:
    """Rule B: Zero `except ...: pass` statements permitted in tools/."""
    violations: List[str] = []
    for py_file in _collect_tools_py_files():
        rel_path = py_file.relative_to(REPO_ROOT)
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    violations.append(f"{rel_path}:{node.lineno} has except ...: pass")

    assert not violations, "Rule B violation: except ...: pass found in tools/:\n" + "\n".join(violations)


def test_no_hardcoded_demo_phrases_in_tools() -> None:
    """Rule A: Demo script phrases must never exist as string literals in production tools/."""
    violations: List[str] = []
    for py_file in _collect_tools_py_files():
        rel_path = py_file.relative_to(REPO_ROOT)
        content = py_file.read_text(encoding="utf-8").lower()
        for phrase in DEMO_PHRASE_DENYLIST:
            if phrase in content:
                # Find line number
                for line_no, line in enumerate(content.splitlines(), start=1):
                    if phrase in line:
                        violations.append(f"{rel_path}:{line_no} contains banned demo phrase '{phrase}': {line.strip()[:100]}")

    assert not violations, "Rule A violation: hardcoded demo phrases found in tools/:\n" + "\n".join(violations)


def test_no_default_topic_string_fallbacks_in_tools() -> None:
    """Rule A: Production code must not contain silent topic defaults like `or 'Cognitive Science'`."""
    violations: List[str] = []
    banned_tokens = ['or "cognitive science"', "or 'cognitive science'"]
    for py_file in _collect_tools_py_files():
        rel_path = py_file.relative_to(REPO_ROOT)
        content = py_file.read_text(encoding="utf-8").lower()
        for token in banned_tokens:
            if token in content:
                for line_no, line in enumerate(content.splitlines(), start=1):
                    if token in line:
                        violations.append(f"{rel_path}:{line_no} contains banned fallback '{token}'")

    assert not violations, "Rule A violation: default topic fallback found in tools/:\n" + "\n".join(violations)


def test_universal_engine_enforces_rule_b_on_missing_script() -> None:
    """universal_engine.plan_scenes_from_script must fail closed on missing or empty script."""
    from tools.errors import MissingInputError
    from tools.universal_engine import plan_scenes_from_script

    with pytest.raises(MissingInputError) as exc_none:
        plan_scenes_from_script(None, topic="Testing", title="Testing", variant="photobook")  # type: ignore
    assert exc_none.value.stage == "scene_plan"

    with pytest.raises(MissingInputError) as exc_empty:
        plan_scenes_from_script("", topic="Testing", title="Testing", variant="photobook")
    assert exc_empty.value.stage == "scene_plan"
