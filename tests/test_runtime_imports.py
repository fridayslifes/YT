from __future__ import annotations

import importlib
import os


def test_render_module_imports_never_reexec(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("import attempted to replace the host process")

    monkeypatch.setattr(os, "execv", forbidden)
    import sys

    # Reproduce running under an interpreter outside the repository venv. The
    # creative engine is imported transitively by pipeline, so both imports
    # must remain safe even when its CLI bootstrap would otherwise re-exec.
    monkeypatch.setattr(sys, "executable", "/usr/bin/python3")
    for module_name in (
        "tools.creative_engine",
        "tools.pipeline",
        "tools.build_video",
        "tools.visual_engine",
    ):
        module = importlib.import_module(module_name)
        importlib.reload(module)


def test_runtime_bootstrap_reexecs_only_when_requested(monkeypatch, tmp_path):
    from tools import runtime

    target = tmp_path / ".venv" / "bin" / "python"
    target.parent.mkdir(parents=True)
    target.write_text("", encoding="utf-8")
    target.chmod(0o755)
    script = tmp_path / "tools" / "render.py"
    script.parent.mkdir()
    script.write_text("", encoding="utf-8")
    calls = []
    monkeypatch.setattr(runtime, "_venv_python", lambda _script: target)
    monkeypatch.setattr(runtime.sys, "executable", "/usr/bin/python3")
    monkeypatch.setattr(runtime.os, "execv", lambda executable, argv: calls.append((executable, argv)))

    runtime.ensure_venv_cli(script, ["--example"])

    assert calls == [(str(target), [str(target), str(script.resolve()), "--example"])]

