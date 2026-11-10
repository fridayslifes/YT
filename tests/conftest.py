"""Shared pytest fixtures for the FrameForge pipeline test suite.

Design constraints:
  - The suite covers pure logic, artifact contracts, orchestration and mocked upload safety.
    Media, network and model operations are mocked or exercised with local fixtures.
  - `tools` has NO __init__.py - it is a PEP 420 implicit namespace package imported from
    the repo root, exactly the way tools/pipeline.py does it at runtime. The
    [tool.pytest.ini_options] pythonpath entry plus the sys.path bootstrap below make that
    work whether you run `pytest -q`, `pytest tests/test_title.py` or `./check.sh`.
  - The suite uses no expected-failure markers; behavior required by GEMINI.md is asserted directly.
"""

from __future__ import annotations

import fcntl
import multiprocessing.context
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterable, Sequence

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _install_sandbox_fork_sync_fallback() -> None:
    """Provide filesystem-backed Event/Barrier on ForkContext when POSIX sem_open is sandbox-blocked."""
    try:
        multiprocessing.get_context("fork").Lock()
        return
    except PermissionError:
        pass

    sync_dir = Path(tempfile.mkdtemp(prefix="ff_mp_sync_"))

    class _FileEvent:
        def __init__(self) -> None:
            fd, raw = tempfile.mkstemp(dir=sync_dir, prefix="ev_")
            os.close(fd)
            self._path = Path(raw)

        def is_set(self) -> bool:
            return self._path.exists() and self._path.stat().st_size > 0

        def set(self) -> None:
            self._path.write_bytes(b"1")

        def clear(self) -> None:
            if self._path.exists():
                self._path.write_bytes(b"")

        def wait(self, timeout: float | None = None) -> bool:
            deadline = None if timeout is None else (time.monotonic() + float(timeout))
            while True:
                if self.is_set():
                    return True
                if deadline is not None and time.monotonic() >= deadline:
                    return False
                time.sleep(0.005)

    class _FileBarrier:
        def __init__(self, parties: int) -> None:
            self.parties = int(parties)
            fd, raw = tempfile.mkstemp(dir=sync_dir, prefix="bar_")
            os.close(fd)
            self._path = Path(raw)

        def wait(self, timeout: float | None = None) -> int:
            with self._path.open("a+b") as fh:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
                fh.seek(0)
                idx = len(fh.read())
                fh.write(b"1")
                fh.flush()
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            deadline = None if timeout is None else (time.monotonic() + float(timeout))
            while True:
                if self._path.stat().st_size >= self.parties:
                    return idx
                if deadline is not None and time.monotonic() >= deadline:
                    raise TimeoutError("Barrier wait timed out")
                time.sleep(0.005)

    multiprocessing.context.ForkContext.Event = lambda self: _FileEvent()  # type: ignore[method-assign]
    multiprocessing.context.ForkContext.Barrier = (  # type: ignore[method-assign]
        lambda self, parties, action=None, timeout=None: _FileBarrier(parties)
    )


_install_sandbox_fork_sync_fallback()

ANSI_RE = re.compile(r"\033\[[0-9;]*m")

# --------------------------------------------------------------------------- #
# Honesty report: findings that are true about the repo today but are NOT suite
# failures (a data drift or a calibration gap). Printed after every pytest run so
# `pytest -q` can never look silently green about them. See test_project_contract.py
# and test_hookscore.py.
# --------------------------------------------------------------------------- #
REPORT: dict[str, list[str]] = {}


def report(section_name: str, lines: list[str]) -> None:
    """Record a finding that is true today but is not a suite failure.

    Merging (not overwriting) lets several tests contribute to one section; duplicates are
    dropped so a parametrized test does not print the same line twenty times.
    """
    bucket = REPORT.setdefault(section_name, [])
    for line in lines:
        if line not in bucket:
            bucket.append(line)


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    sections = {name: lines for name, lines in REPORT.items() if lines}
    if not sections:
        return
    terminalreporter.write_sep("=", "REPO HONESTY REPORT (true today, not a test failure)")
    for section_name, lines in sections.items():
        terminalreporter.write_line(f"{section_name}:")
        for line in sorted(lines):
            terminalreporter.write_line(f"  {line}")
    terminalreporter.write_line(
        "Baseline-locked: NEW violations fail the tests; fixed ones only shrink this report."
    )


def strip_ansi(text: str) -> str:
    """Remove ANSI colour codes so assertions hold in a TTY run and in a captured run.

    tools/output_format.py decides USE_COLOR at import time from isatty()/NO_COLOR, so the
    raw string differs between `pytest -q` and `pytest -s` in a terminal. Never assert on it.
    """
    return ANSI_RE.sub("", text)


def srt_timestamp(seconds: float) -> str:
    """Seconds -> SRT `HH:MM:SS,mmm`."""
    ms = int(round(seconds * 1000))
    h, rest = divmod(ms, 3_600_000)
    m, rest = divmod(rest, 60_000)
    s, milli = divmod(rest, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"


def make_srt(cues: Sequence[tuple[float, float, str]]) -> str:
    """Build an SRT body from (start, end, text) tuples. Multi-line text kept as-is."""
    blocks = []
    for i, (start, end, text) in enumerate(cues, 1):
        blocks.append(f"{i}\n{srt_timestamp(start)} --> {srt_timestamp(end)}\n{text}\n")
    return "\n".join(blocks)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def project_files(repo_root: Path) -> list[Path]:
    """Every shorts/*/project.json and long_form/*/project.json in the repo."""
    return sorted(repo_root.glob("shorts/*/project.json")) + sorted(repo_root.glob("long_form/*/project.json"))


@pytest.fixture
def write_transcript(tmp_path):
    """Write an SRT (or any transcript shape) to disk and return its path string."""

    def _write(name: str, cues: Iterable[tuple[float, float, str]] | str) -> str:
        path = tmp_path / name
        body = make_srt(list(cues)) if isinstance(cues, (list, tuple)) else cues
        path.write_text(body, encoding="utf-8")
        return str(path)

    return _write
