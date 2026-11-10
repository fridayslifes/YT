"""Real processes protect the deadline, durable failure, and process cleanup contracts."""

from __future__ import annotations

import json
import os
import signal
import shlex
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from tools.orchestrator.contracts import Status, TaskSpec, WorkerResult
from tools.orchestrator.master import MasterAgent
from tools.orchestrator.workflows import Workflow

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX process-group supervision")


def _assert_gone(pid):
    until = time.monotonic() + 1.0
    while time.monotonic() < until:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.01)
    pytest.fail(f"process {pid} survived cleanup")


def _assert_group_gone(pgid):
    with pytest.raises(ProcessLookupError):
        os.killpg(pgid, 0)


@pytest.mark.parametrize("spawn_child", [False, True])
def test_master_deadline_is_durable_blocks_dependents_and_cleans_group(tmp_path, spawn_child):
    # Removing supervision must break the wall-clock bound and let the dependent execute.
    class HangingWorker:
        kind = "hang"

        def run(self, spec, ctx):
            if spec.id == "dependent":
                (tmp_path / "dependent-ran").touch()
                return WorkerResult(True, "dependent ran")
            (tmp_path / "worker.pid").write_text(str(os.getpid()))
            if spawn_child:
                child = subprocess.Popen([
                    sys.executable, "-c",
                    "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)",
                ])
                (tmp_path / "child.pid").write_text(str(child.pid))
            time.sleep(3.2)
            return WorkerResult(True, "deadline was ignored")

    master = MasterAgent(tmp_path, workers={"hang": HangingWorker()}, verifiers={}, console=lambda *_: None)
    tasks = [TaskSpec("hang", "hang", "hang", timeout_s=1, max_attempts=3),
             TaskSpec("dependent", "hang", "dependent", depends_on=["hang"])]
    started = time.monotonic()
    try:
        state = master.new_run(Workflow("timeout", "deadline", tasks))
        elapsed = time.monotonic() - started
        assert elapsed < 3.0
        stored = master.store.load(state.run_id)
        assert stored.status == "failed"
        assert stored.tasks["hang"].status == Status.FAILED
        assert stored.tasks["hang"].attempts == 1
        assert "timeout" in stored.tasks["hang"].error.lower()
        assert stored.tasks["hang"].metrics["timeout_s"] == 1
        assert stored.tasks["dependent"].status == Status.BLOCKED
        assert not (tmp_path / "dependent-ran").exists()
        worker_pid = int((tmp_path / "worker.pid").read_text())
        _assert_gone(worker_pid)
        with pytest.raises(ChildProcessError):
            os.waitpid(worker_pid, os.WNOHANG)
        if spawn_child:
            _assert_gone(int((tmp_path / "child.pid").read_text()))
        _assert_group_gone(worker_pid)
        print(f"master timeout: {elapsed:.3f}s; worker/group={worker_pid}; child={spawn_child}; durable={stored.status}")
    finally:
        child_path = tmp_path / "child.pid"
        if child_path.exists():
            try:
                os.kill(int(child_path.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_run_process_timeout_kills_ignoring_descendant_and_reaps(tmp_path):
    # Killing only the immediate process leaves its SIGTERM-ignoring child alive.
    from tools.processes import ProcessDeadlineExceeded, run_process

    script = (
        "import os,pathlib,signal,subprocess,sys,time; "
        "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        f"pathlib.Path({str(tmp_path / 'parent.pid')!r}).write_text(str(os.getpid())); "
        "p=subprocess.Popen([sys.executable,'-c',"
        "'import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)']); "
        f"pathlib.Path({str(tmp_path / 'child.pid')!r}).write_text(str(p.pid)); "
        "print('started',flush=True); time.sleep(60)"
    )
    started = time.monotonic()
    with pytest.raises(ProcessDeadlineExceeded) as caught:
        run_process([sys.executable, "-c", script], timeout_s=0.5)
    elapsed = time.monotonic() - started
    assert elapsed < 3.0
    assert "started" in caught.value.stdout
    parent_pid = int((tmp_path / "parent.pid").read_text())
    child_pid = int((tmp_path / "child.pid").read_text())
    _assert_gone(parent_pid)
    _assert_gone(child_pid)
    with pytest.raises(ChildProcessError):
        os.waitpid(parent_pid, os.WNOHANG)
    _assert_group_gone(parent_pid)
    print(f"process timeout: {elapsed:.3f}s; group={parent_pid}; child={child_pid}; all gone/reaped")


@pytest.mark.parametrize("behavior, diagnostic", [
    ("exception", "ValueError"), ("exit", "SystemExit"),
    ("serialization", "serializ"), ("abrupt", "result"),
])
def test_worker_failures_return_explicit_results(behavior, diagnostic):
    # Uncaught exits or unencodable results must never masquerade as a success or hang the parent.
    from tools.orchestrator.execution import run_worker

    class BrokenWorker:
        def run(self, spec, ctx):
            if behavior == "exception":
                raise ValueError("broken")
            if behavior == "exit":
                raise SystemExit(7)
            if behavior == "abrupt":
                os._exit(9)
            return WorkerResult(True, "bad payload", data={"bad": object()})

    result = run_worker(BrokenWorker(), TaskSpec("broken", "broken", "broken", timeout_s=1), SimpleNamespace())
    assert not result.ok
    assert diagnostic.lower() in result.error.lower()
    if behavior in {"exit", "serialization", "abrupt"}:
        assert not result.retryable


def test_worker_large_result_is_drained_before_waiting_for_exit():
    # Waiting for the child before draining a full pipe deadlocks a valid large result.
    from tools.orchestrator.execution import run_worker

    class LargeWorker:
        def run(self, spec, ctx):
            return WorkerResult(True, "large", data={"payload": "x" * 1_000_000, "pid": os.getpid()})

    result = run_worker(LargeWorker(), TaskSpec("large", "large", "large", timeout_s=2), SimpleNamespace())
    assert result.ok
    assert len(result.data["payload"]) == 1_000_000
    assert json.loads(json.dumps(result.to_dict()))["summary"] == "large"
    with pytest.raises(ChildProcessError):
        os.waitpid(result.data["pid"], os.WNOHANG)


@pytest.mark.parametrize("ignore_term", [False, True])
def test_worker_deadline_cleans_nested_process_runner_group(tmp_path, ignore_term):
    # A new session created by run_process must not escape the outer worker deadline.
    from tools.orchestrator.execution import run_worker
    from tools.processes import run_process

    class NestedWorker:
        def run(self, spec, ctx):
            if ignore_term:
                signal.signal(signal.SIGTERM, signal.SIG_IGN)
            run_process([
                sys.executable, "-c",
                "import os,pathlib,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                f"pathlib.Path({str(tmp_path / 'nested.pid')!r}).write_text(str(os.getpid())); time.sleep(60)",
            ], timeout_s=30)
            return WorkerResult(True, "escaped deadline")

    started = time.monotonic()
    try:
        result = run_worker(NestedWorker(), TaskSpec("nested", "nested", "nested", timeout_s=1), SimpleNamespace())
        assert time.monotonic() - started < 3.0
        assert not result.ok and not result.retryable
        nested_pid = int((tmp_path / "nested.pid").read_text())
        _assert_gone(nested_pid)
        _assert_group_gone(nested_pid)
    finally:
        if (tmp_path / "nested.pid").exists():
            try:
                os.killpg(int((tmp_path / "nested.pid").read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_worker_shutdown_observes_nested_command_started_during_term_grace(tmp_path):
    # Closing the observation pipe at timeout strands commands launched during TERM cleanup.
    from tools.orchestrator.execution import run_worker
    from tools.processes import run_process

    pid_file = tmp_path / "late.pid"
    launch_file = tmp_path / "launch.json"

    class LateCommandWorker:
        def run(self, spec, ctx):
            started = time.monotonic()

            def during_shutdown(signum, frame):
                # The child inherits ignored TERM, making the later hard kill observable.
                signal.signal(signal.SIGTERM, signal.SIG_IGN)
                time.sleep(0.3)
                launch_file.write_text(json.dumps({"elapsed": time.monotonic() - started}))
                run_process(["/bin/sh", "-c", f"echo $$ > {shlex.quote(str(pid_file))}; exec /bin/sleep 60"],
                            timeout_s=30)

            signal.signal(signal.SIGTERM, during_shutdown)
            time.sleep(60)
            return WorkerResult(True, "escaped shutdown")

    started = time.monotonic()
    try:
        result = run_worker(LateCommandWorker(), TaskSpec("late", "late", "late", timeout_s=1), SimpleNamespace())
        elapsed = time.monotonic() - started
        assert elapsed < 3.0
        assert not result.ok and not result.retryable
        assert json.loads(launch_file.read_text())["elapsed"] >= 1.2
        nested_pid = int(pid_file.read_text())
        _assert_gone(nested_pid)
        _assert_group_gone(nested_pid)
        with pytest.raises(ChildProcessError):
            os.waitpid(result.metrics["worker_pid"], os.WNOHANG)
        print(f"shutdown arrival: {elapsed:.3f}s; nested/group={nested_pid}; worker reaped; group gone")
    finally:
        if pid_file.exists():
            try:
                os.killpg(int(pid_file.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_run_process_preserves_output_and_check_semantics(tmp_path):
    from tools.processes import run_process

    result = run_process([sys.executable, "-c", "import os; print(os.getcwd())"], timeout_s=2, cwd=tmp_path)
    assert result.stdout.strip() == str(tmp_path)
    result = run_process([sys.executable, "-c", "print('bytes')"], timeout_s=2, text=False)
    assert result.stdout == b"bytes\n"
    with pytest.raises(subprocess.CalledProcessError) as caught:
        run_process([sys.executable, "-c", "import sys; print('error',file=sys.stderr); sys.exit(4)"],
                    timeout_s=2, check=True)
    assert caught.value.returncode == 4
    assert caught.value.stderr == "error\n"


@pytest.fixture
def hanging_media_commands(tmp_path, monkeypatch):
    # Local executable fixtures exercise callers, not a mocked subprocess API.
    from tools import processes

    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    pid_file = tmp_path / "media.pid"
    for name in ("ffprobe", "ffmpeg", "blender"):
        command = binary_dir / name
        command.write_text(
            f"#!/bin/sh\necho $$ > {shlex.quote(str(pid_file))}\nexec /bin/sleep 3.2\n"
        )
        command.chmod(0o755)
    original_popen = subprocess.Popen

    def record_pid(*args, **kwargs):
        proc = original_popen(*args, **kwargs)
        # Record the real PID in the parent: deadline enforcement may precede script startup.
        pid_file.write_text(str(proc.pid))
        return proc

    monkeypatch.setattr(processes.subprocess, "Popen", record_pid)
    monkeypatch.setenv("PATH", str(binary_dir) + os.pathsep + os.environ["PATH"])
    return binary_dir, pid_file


@pytest.mark.parametrize("operation", ["identity", "duration", "measure", "shape", "motion"])
def test_media_command_deadlines_stop_hanging_commands(tmp_path, monkeypatch, hanging_media_commands, operation):
    # Reverting one media call to an unbounded subprocess must miss the deadline and fail this test.
    from tools import branding_engine, build_video, visual_engine
    from tools.processes import ProcessDeadlineExceeded

    _, pid_file = hanging_media_commands
    source = tmp_path / "source.mp4"
    source.touch()
    for module in (branding_engine, build_video, visual_engine):
        monkeypatch.setattr(module, "PROBE_TIMEOUT_S", 0.3, raising=False)
        monkeypatch.setattr(module, "MEDIA_TIMEOUT_S", 0.3, raising=False)
    operations = {
        "identity": lambda: build_video._video_identity(source),
        "duration": lambda: build_video._media_duration(source),
        "measure": lambda: branding_engine.measure_master(str(source)),
        "shape": lambda: visual_engine._probe_video_shape(source),
        "motion": lambda: visual_engine._decode_gray_frames(source, 2, 2, [0], None),
    }
    started = time.monotonic()
    with pytest.raises(ProcessDeadlineExceeded):
        operations[operation]()
    assert time.monotonic() - started < 2.0
    _assert_gone(int(pid_file.read_text()))


def test_branding_concat_deadline_preserves_film_and_cleans_temporary_files(tmp_path, monkeypatch, hanging_media_commands):
    from tools import build_video
    from tools.processes import ProcessDeadlineExceeded

    _, pid_file = hanging_media_commands
    film = tmp_path / "film.mp4"
    film.write_bytes(b"original film")
    for name in build_video.BRANDING_MASTERS.values():
        (tmp_path / name).touch()
    monkeypatch.setattr(build_video, "BRANDING_DIR", tmp_path)
    monkeypatch.setattr(build_video, "MEDIA_TIMEOUT_S", 0.3, raising=False)
    monkeypatch.setattr(build_video, "_media_duration", lambda path: 3.0)
    monkeypatch.setattr(build_video, "_video_identity", lambda path: ("h264", "1080", "1920", "30/1"))
    started = time.monotonic()
    with pytest.raises(ProcessDeadlineExceeded):
        build_video.attach_branding(film, {"format": "long", "branding": {"outro": True}})
    assert time.monotonic() - started < 2.0
    assert film.read_bytes() == b"original film"
    assert not film.with_suffix(".branding.txt").exists()
    assert not film.with_suffix(".branding.tmp.mp4").exists()
    _assert_gone(int(pid_file.read_text()))


def test_blender_deadline_reaches_native_fallback_and_removes_script(tmp_path, monkeypatch, hanging_media_commands):
    from tools import visual_engine

    _, pid_file = hanging_media_commands
    monkeypatch.setattr(visual_engine, "BLENDER_TIMEOUT_S", 0.3, raising=False)
    output = tmp_path / "output.mp4"

    def native(obj_path, output_mp4, *args, **kwargs):
        output_mp4.write_bytes(b"native fallback output")
        return True

    # Native rendering invokes model/encoder work; keep the CLI and fallback decision real.
    monkeypatch.setattr(visual_engine, "render_obj_mesh_native", native)
    started = time.monotonic()
    assert visual_engine.BlenderBridge.render_mesh(tmp_path / "input.obj", output)
    assert time.monotonic() - started < 2.0
    assert output.read_bytes() == b"native fallback output"
    assert not (tmp_path / "_blender_tmp_render.py").exists()
    _assert_gone(int(pid_file.read_text()))


def test_darwin_worker_fork_inherits_objc_fork_safety(monkeypatch):
    """The child must survive long enough to write its result; macOS aborts it otherwise."""
    from tools.orchestrator import execution

    seen = {}

    def fake_fork():
        seen["value"] = os.environ.get("OBJC_DISABLE_INITIALIZE_FORK_SAFETY")
        raise RuntimeError("stop before forking")

    monkeypatch.delenv("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", raising=False)
    monkeypatch.setattr(execution.sys, "platform", "darwin")
    monkeypatch.setattr(os, "fork", fake_fork)
    with pytest.raises(RuntimeError, match="stop before forking"):
        execution.run_worker(SimpleNamespace(), TaskSpec("w", "build", "worker"), SimpleNamespace())
    assert seen["value"] == "YES"
