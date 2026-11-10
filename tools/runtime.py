"""Small helpers shared by explicit command-line bootstraps."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _venv_python(script: Path) -> Path:
    return Path(script).resolve().parent.parent / ".venv" / "bin" / "python"


def ensure_venv_cli(script: Path, argv: list[str] | None = None) -> None:
    """Re-exec a command-line script with its repository virtualenv when available."""
    script = Path(script).resolve()
    interpreter = _venv_python(script)
    try:
        if interpreter.exists() and Path(sys.executable).resolve() != interpreter.resolve():
            if os.access(str(interpreter), os.X_OK):
                args = list(sys.argv[1:] if argv is None else argv)
                os.execv(str(interpreter), [str(interpreter), str(script), *args])
    except OSError:
        pass
