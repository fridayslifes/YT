"""Atomic durable text replacement and process-owned POSIX file locks."""

from __future__ import annotations

import fcntl
import os
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path


def durable_write_text(path: Path, text: str, *, mode: int | None = None) -> None:
    """Publish complete UTF-8 text only after syncing it, then sync the directory.

    Existing permission bits are preserved unless ``mode`` is supplied. New files
    default to private permissions. Failure before replacement leaves the old file
    intact; a directory-sync failure after replacement is still reported to callers.
    """
    path = Path(path)
    if mode is None:
        try:
            mode = stat.S_IMODE(path.stat().st_mode)
        except FileNotFoundError:
            mode = 0o600
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fchmod(handle.fileno(), mode)
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


class LockBusy(RuntimeError):
    """Another process owns the requested exclusive lock."""


_lock_fds: set[int] = set()


def _close_inherited_locks() -> None:
    # flock ownership follows the open file description across fork. Closing the
    # child's duplicate (without LOCK_UN) keeps the parent as the only owner.
    for fd in _lock_fds:
        os.close(fd)
    _lock_fds.clear()


os.register_at_fork(after_in_child=_close_inherited_locks)


@contextmanager
def exclusive_lock(path: Path, *, blocking: bool = True):
    """Hold a stable, empty lock file; never unlink it while waiters may exist."""
    path = Path(path)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    owner = os.getpid()
    _lock_fds.add(fd)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError as exc:
            raise LockBusy(f"busy: another process holds {path}") from exc
        yield
    finally:
        if os.getpid() == owner:
            _lock_fds.discard(fd)
            # Closing the sole owner descriptor releases flock even on exceptions.
            os.close(fd)
