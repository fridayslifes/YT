"""Bound external commands and clean up their POSIX process groups."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Callable
from contextlib import contextmanager


class ProcessDeadlineExceeded(subprocess.TimeoutExpired):
    """A command exceeded its deadline; its group has been terminated and reaped."""


_active_groups: set[int] = set()
_group_observer: Callable[[int, bool], None] | None = None


def _signal_group(pgid: int, sig: int) -> bool:
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        return False
    except PermissionError:
        # macOS reports EPERM for an owned group containing only exited zombies.
        return False
    return True


def terminate_process_group(pgid: int, *, grace_s: float = 1.0) -> None:
    """Allow TERM cleanup, then kill survivors even when the group leader has exited."""
    terminate_process_groups({pgid}, grace_s=grace_s)


def terminate_process_groups(pgids: set[int], *, grace_s: float = 1.0) -> None:
    """Give all owned groups the same grace period, rather than one period per group."""
    survivors = {pgid for pgid in pgids if _signal_group(pgid, signal.SIGTERM)}
    deadline = time.monotonic() + grace_s
    while survivors and time.monotonic() < deadline:
        survivors = {pgid for pgid in survivors if _signal_group(pgid, 0)}
        if not survivors:
            return
        time.sleep(min(0.02, max(0, deadline - time.monotonic())))
    for pgid in survivors:
        _signal_group(pgid, signal.SIGKILL)


def _kill_active_process_groups() -> None:
    """The worker's TERM handler also stops commands that opened their own sessions."""
    for pgid in tuple(_active_groups):
        _signal_group(pgid, signal.SIGKILL)


@contextmanager
def process_group(argv, **kwargs):
    """Own a command's session for streaming callers; always stop survivors and reap."""
    if os.name != "posix":
        raise RuntimeError("process-group deadlines require POSIX")
    proc = None
    try:
        proc = subprocess.Popen(argv, start_new_session=True, **kwargs)
        _active_groups.add(proc.pid)
        if _group_observer is not None:
            _group_observer(proc.pid, True)
        yield proc
    finally:
        if proc is not None:
            try:
                proc.poll()
                terminate_process_group(proc.pid)
            finally:
                proc.wait()
                for pipe in (proc.stdin, proc.stdout, proc.stderr):
                    if pipe is not None:
                        pipe.close()
                _active_groups.discard(proc.pid)
                if _group_observer is not None:
                    _group_observer(proc.pid, False)


def run_process(argv, *, timeout_s, cwd=None, capture_output=True, text=True, check=False):
    """Run one command with a deadline, preserving CompletedProcess/check semantics."""
    if timeout_s <= 0:
        raise ValueError("timeout_s must be positive")
    with process_group(
        argv, cwd=cwd, stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None, text=text,
    ) as proc:
        try:
            stdout, stderr = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired as exc:
            terminate_process_group(proc.pid)
            stdout, stderr = proc.communicate()
            raise ProcessDeadlineExceeded(argv, timeout_s, output=stdout, stderr=stderr) from exc
        result = subprocess.CompletedProcess(argv, proc.returncode, stdout, stderr)
        if check:
            result.check_returncode()
        return result

