"""Run workers in isolated, deadline-bound POSIX sessions."""

from __future__ import annotations

import json
import os
import select
import signal
import sys
import time
import traceback

from tools import processes

from .contracts import TaskSpec, WorkerResult
from .state import RunContext


def _worker_child(worker, spec, ctx, reader: int, writer: int, group_reader: int, group_writer: int) -> None:
    os.close(reader)
    os.close(group_reader)
    try:
        os.setsid()

        def observe_group(pgid, active):
            # Keep registrations readable even while a large result is being written.
            os.write(group_writer, f"{'+' if active else '-'}{pgid}\n".encode("ascii"))

        processes._group_observer = observe_group

        def stop(signum, frame):
            processes._kill_active_process_groups()
            raise SystemExit(128 + signum)

        signal.signal(signal.SIGTERM, stop)
        if hasattr(signal, "pthread_sigmask"):
            signal.pthread_sigmask(signal.SIG_UNBLOCK, [signal.SIGTERM])
        try:
            result = worker.run(spec, ctx)
        except SystemExit as exc:
            result = WorkerResult(False, "worker exited the process",
                                  error=f"SystemExit({exc.code}) from {spec.kind}", retryable=False)
        except BaseException as exc:
            result = WorkerResult(False, f"worker crashed: {type(exc).__name__}",
                                  error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=6)}")
        try:
            if not isinstance(result, WorkerResult):
                raise TypeError("worker did not return a WorkerResult")
            payload = json.dumps(result.to_dict()).encode("utf-8")
        except Exception as exc:
            payload = json.dumps(WorkerResult(
                False, "worker result serialization failed", error=f"result serialization failed: {exc}",
                retryable=False,
            ).to_dict()).encode("utf-8")
        with os.fdopen(writer, "wb") as pipe:
            pipe.write(payload)
    finally:
        os._exit(0)


def run_worker(worker, spec: TaskSpec, ctx: RunContext) -> WorkerResult:
    """Drain the worker result while waiting, enforce its deadline, and always reap it."""
    if os.name != "posix":
        return WorkerResult(False, "worker supervision unavailable", error="worker deadlines require POSIX", retryable=False)
    if spec.timeout_s <= 0:
        return WorkerResult(False, "invalid worker deadline", error="timeout_s must be positive", retryable=False)
    if sys.platform == "darwin" and getattr(worker, "kind", "") == "publish":
        # macOS crashes a forked child that touches parent's Obj-C/Metal runtime during network SSL.
        # Run publish worker in-process to avoid the fork crash.
        try:
            return worker.run(spec, ctx)
        except Exception as exc:
            return WorkerResult(False, f"publish failed: {exc}", error=str(exc), retryable=False)
    reader, writer = os.pipe()
    group_reader, group_writer = os.pipe()
    deadline = time.monotonic() + spec.timeout_s
    # macOS SIGABRTs a forked child that touches the parent's Obj-C runtime (numpy/Accelerate load it
    # during the release task); this killed the first SH-17 publish before any receipt could be written.
    if sys.platform == "darwin":
        os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
    try:
        pid = os.fork()
    except BaseException:
        os.close(reader)
        os.close(writer)
        os.close(group_reader)
        os.close(group_writer)
        raise
    if pid == 0:
        _worker_child(worker, spec, ctx, reader, writer, group_reader, group_writer)
    os.close(writer)
    os.close(group_writer)
    payload = bytearray()
    group_records = bytearray()
    groups: set[int] = set()
    status = None
    eof = False
    group_eof = False

    def observe_groups(wait_s=0.0):
        nonlocal group_eof
        if group_eof or not select.select([group_reader], [], [], wait_s)[0]:
            return False
        chunk = os.read(group_reader, 65536)
        if not chunk:
            group_eof = True
            return False
        group_records.extend(chunk)
        while b"\n" in group_records:
            record, _, _ = group_records.partition(b"\n")
            pgid = int(record[1:])
            if record.startswith(b"+"):
                groups.add(pgid)
            else:
                groups.discard(pgid)
            del group_records[:len(record) + 1]
        return True

    try:
        while True:
            while observe_groups():
                pass
            if status is None:
                done, code = os.waitpid(pid, os.WNOHANG)
                if done:
                    status = code
            if eof and status is not None:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return WorkerResult(
                    False, f"worker timeout after {spec.timeout_s}s",
                    error=f"worker timeout after {spec.timeout_s}s: {spec.kind}", retryable=False,
                    metrics={"timeout_s": spec.timeout_s, "worker_pid": pid, "process_group": pid},
                )
            ready, _, _ = select.select([] if eof else [reader], [], [], min(remaining, 0.05))
            if ready:
                chunk = os.read(reader, 65536)
                if chunk:
                    payload.extend(chunk)
                else:
                    eof = True
        if not payload or status != 0:
            return WorkerResult(False, "worker exited without a result",
                                error=f"worker result missing; exit status {os.waitstatus_to_exitcode(status)}", retryable=False)
        try:
            return WorkerResult.from_dict(json.loads(payload))
        except Exception as exc:
            return WorkerResult(False, "invalid worker result", error=f"worker result could not be decoded: {exc}", retryable=False)
    finally:
        try:
            signalled: set[int] = set()
            grace_deadline = time.monotonic() + 1.0
            while True:
                while observe_groups():
                    pass
                targets = groups | {pid}
                for pgid in targets - signalled:
                    processes._signal_group(pgid, signal.SIGTERM)
                signalled.update(targets)
                remaining = grace_deadline - time.monotonic()
                if remaining <= 0 or (group_eof and not any(processes._signal_group(pgid, 0) for pgid in targets)):
                    break
                observe_groups(min(remaining, 0.02))
        finally:
            # Stop command creation before the final drain; arrivals during grace remain owned.
            processes._signal_group(pid, signal.SIGKILL)
            if status is None:
                os.waitpid(pid, 0)
            try:
                while observe_groups():
                    pass
            finally:
                for pgid in groups:
                    processes._signal_group(pgid, signal.SIGKILL)
                os.close(reader)
                os.close(group_reader)

