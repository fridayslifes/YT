"""Durable filesystem writes and actual overlapping orchestration processes."""

from __future__ import annotations

import json
import multiprocessing
import os
import signal
import stat
from pathlib import Path

import pytest

from tools.orchestrator.contracts import Status, TaskSpec, WorkerResult
from tools.orchestrator.master import MasterAgent
from tools.orchestrator.state import RunStore
from tools.orchestrator.workflows import Workflow

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX filesystem locking")


def _join(process):
    process.join(8)
    assert not process.is_alive(), f"process {process.pid} hung"
    assert process.exitcode == 0


@pytest.mark.parametrize("mode", [None, 0o640])
def test_atomic_write_syncs_complete_file_before_replace_then_directory(tmp_path, monkeypatch, mode):
    # Omitting either fsync or replacing before flushing violates crash durability.
    from tools import atomic_files

    path = tmp_path / "state.json"
    path.write_text("old")
    path.chmod(0o644)
    events = []
    fsync, replace = os.fsync, os.replace

    def sync(fd):
        events.append("directory" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file")
        fsync(fd)

    def publish(source, destination):
        assert events == ["file"]
        assert Path(source).parent == path.parent
        assert Path(source).read_bytes() == 'new café\n'.encode()
        assert path.read_text() == "old"
        events.append("replace")
        replace(source, destination)

    monkeypatch.setattr(os, "fsync", sync)
    monkeypatch.setattr(os, "replace", publish)
    atomic_files.durable_write_text(path, "new café\n", mode=mode)
    assert events == ["file", "replace", "directory"]
    assert path.read_text() == "new café\n"
    assert stat.S_IMODE(path.stat().st_mode) == (0o644 if mode is None else mode)
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("failure", ["fsync", "replace"])
def test_atomic_failure_before_replace_preserves_original_bytes(tmp_path, monkeypatch, failure):
    # A failed staging write must never truncate the old file or leak a temp file.
    from tools.atomic_files import durable_write_text

    path = tmp_path / "state.json"
    original = b'{"status":"approved"}\n'
    path.write_bytes(original)

    def fail(*args):
        raise OSError("injected pre-replace failure")

    monkeypatch.setattr(os, failure, fail)
    with pytest.raises(OSError, match="injected"):
        durable_write_text(path, "replacement")
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]
    print(f"failure={failure}; surviving bytes={path.read_bytes()!r}")


def test_atomic_concurrent_writers_have_distinct_staging_files(tmp_path):
    # A shared .tmp file collides when two independent writers reach replace.
    from tools.atomic_files import durable_write_text

    context = multiprocessing.get_context("fork")
    ready = context.Barrier(2)
    path = tmp_path / "state.json"
    path.write_text("original")

    def write(label):
        replace = os.replace

        def publish(source, destination):
            (tmp_path / f"{label}.source").write_text(str(source))
            ready.wait(timeout=5)
            replace(source, destination)

        os.replace = publish
        durable_write_text(path, label * 10000)

    processes = [context.Process(target=write, args=(label,)) for label in ("A", "B")]
    try:
        for process in processes:
            process.start()
        for process in processes:
            _join(process)
        sources = [(tmp_path / f"{label}.source").read_text() for label in ("A", "B")]
        assert len(set(sources)) == 2
        assert all(Path(source).parent == tmp_path for source in sources)
        assert path.read_text() in {"A" * 10000, "B" * 10000}
        assert not list(tmp_path.glob("*.tmp"))
        print(f"atomic writer pids={[p.pid for p in processes]}; unique staging files={sources}")
    finally:
        for process in processes:
            if process.is_alive():
                process.kill()
                process.join()


def test_state_atomic_save_does_not_touch_another_writers_fixed_temp(tmp_path):
    store = RunStore(tmp_path)
    state = store.create("fixture", "durable", [])
    sentinel = store.run_dir(state.run_id) / "run.json.tmp"
    sentinel.write_bytes(b"another writer owns this")
    state.goal = "updated"
    store.save(state)
    assert sentinel.read_bytes() == b"another writer owns this"
    assert store.load(state.run_id).goal == "updated"


@pytest.mark.parametrize("artifact", ["state", "report"])
def test_state_atomic_failure_preserves_saved_artifact(tmp_path, monkeypatch, artifact):
    store = RunStore(tmp_path)
    state = store.create("fixture", "durable", [])
    store.write_report(state, "original report\n")
    path = store.run_dir(state.run_id) / ("run.json" if artifact == "state" else "REPORT.md")
    original = path.read_bytes()

    def fail(fd):
        raise OSError("disk sync failure")

    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(OSError, match="disk sync"):
        if artifact == "state":
            state.goal = "replacement"
            store.save(state)
        else:
            store.write_report(state, "replacement report")
    assert path.read_bytes() == original
    assert not list(path.parent.glob("*.tmp"))


def test_concurrent_resume_runs_worker_exactly_once(tmp_path):
    # Reading/resetting a RUNNING record before taking the lock dispatches twice.
    context = multiprocessing.get_context("fork")
    entered, release = context.Event(), context.Event()
    calls = tmp_path / "worker-calls.jsonl"

    class Worker:
        kind = "fixture"

        def run(self, spec, ctx):
            with calls.open("a") as handle:
                handle.write(json.dumps({"pid": os.getpid(), "task": spec.id}) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            entered.set()
            assert release.wait(5)
            return WorkerResult(True, "completed once")

    def master():
        return MasterAgent(tmp_path, workers={"fixture": Worker()}, verifiers={}, console=lambda *_: None)

    state = master().store.create("fixture", "exactly once", [TaskSpec("work", "fixture", "work", timeout_s=7)])

    def resume(label):
        try:
            result = master().resume(state.run_id)
            outcome = {"status": result.status}
        except Exception as exc:
            outcome = {"error": type(exc).__name__, "message": str(exc)}
        (tmp_path / f"{label}.json").write_text(json.dumps(outcome))

    first = context.Process(target=resume, args=("first",))
    second = context.Process(target=resume, args=("second",))
    try:
        first.start()
        assert entered.wait(5), "first worker did not start"
        before = (master().store.run_dir(state.run_id) / "run.json").read_bytes()
        second.start()
        second.join(1)
        assert not second.is_alive(), "busy resume waited or dispatched another worker"
        _join(second)
        outcome = json.loads((tmp_path / "second.json").read_text())
        assert outcome["error"] == "LockBusy", outcome
        assert "busy" in outcome["message"].lower()
        assert (master().store.run_dir(state.run_id) / "run.json").read_bytes() == before
        release.set()
        _join(first)
        assert json.loads((tmp_path / "first.json").read_text()) == {"status": "passed"}
        stored = master().store.load(state.run_id)
        assert stored.tasks["work"].status == Status.PASSED
        assert stored.tasks["work"].attempts == 1
        assert master().resume(state.run_id).status == "passed"
        executions = [json.loads(line) for line in calls.read_text().splitlines()]
        assert len(executions) == 1
        print(f"resume pids={[first.pid, second.pid]}; worker executions={executions}; loser={outcome}")
    finally:
        release.set()
        for process in (first, second):
            if process.pid:
                process.join(8)
                if process.is_alive():
                    process.kill()
                    process.join()


def test_exclusive_lock_is_parent_owned_after_fork_and_owner_death(tmp_path):
    # An inherited lock fd otherwise keeps a dead parent's run busy in its child.
    from tools.atomic_files import exclusive_lock

    context = multiprocessing.get_context("fork")
    child_ready = context.Event()
    lock = tmp_path / "execution.lock"
    child_path = tmp_path / "child.pid"

    def owner():
        with exclusive_lock(lock):
            pid = os.fork()
            if pid == 0:
                child_path.write_text(str(os.getpid()))
                child_ready.set()
                signal.pause()
                os._exit(0)
            assert child_ready.wait(5)
            os._exit(0)  # Simulate an owner dying without its context manager cleanup.

    process = context.Process(target=owner)
    try:
        process.start()
        _join(process)
        assert child_ready.is_set()
        with exclusive_lock(lock, blocking=False):
            assert lock.read_bytes() == b""
        print(f"dead owner={process.pid}; surviving child={child_path.read_text()}; lock reclaimed")
    finally:
        if child_path.exists():
            os.kill(int(child_path.read_text()), signal.SIGKILL)
        if process.is_alive():
            process.kill()
            process.join()


def test_new_run_holds_execution_lock_during_worker_dispatch(tmp_path):
    # Locking resume alone leaves ordinary dispatch vulnerable to concurrent resume.
    from tools.atomic_files import LockBusy

    class Worker:
        kind = "fixture"

        def run(self, spec, ctx):
            try:
                with ctx.store.execution_lock(ctx.state.run_id):
                    return WorkerResult(False, "parent did not hold the run lock")
            except LockBusy:
                (tmp_path / "parent-lock-observed").write_text(str(os.getpid()))
                return WorkerResult(True, "parent owns the run lock")

    master = MasterAgent(tmp_path, workers={"fixture": Worker()}, verifiers={}, console=lambda *_: None)
    state = master.new_run(Workflow("fixture", "locked dispatch", [TaskSpec("work", "fixture", "work", timeout_s=2)]))
    assert state.status == "passed"
    assert (tmp_path / "parent-lock-observed").exists()
    with master.store.execution_lock(state.run_id):
        assert master.store.load(state.run_id).tasks["work"].attempts == 1


def test_execute_reloads_state_completed_before_lock_acquisition(tmp_path):
    # A resume can finish after creation but before the creator starts dispatch.
    calls = tmp_path / "calls.log"

    class Worker:
        kind = "fixture"

        def run(self, spec, ctx):
            with calls.open("a") as handle:
                handle.write("executed\n")
            return WorkerResult(True, "done")

    master = MasterAgent(tmp_path, workers={"fixture": Worker()}, verifiers={}, console=lambda *_: None)
    tasks = [TaskSpec("work", "fixture", "work")]
    stale = master.store.create("fixture", "creation race", tasks)
    assert master.resume(stale.run_id).status == "passed"
    assert master.execute(stale, tasks).status == "passed"
    assert calls.read_text() == "executed\n"
