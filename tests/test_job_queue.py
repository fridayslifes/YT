"""Unit tests for tools/job_queue.py (Production Job Queue & Scheduler)."""

from __future__ import annotations

import json
from pathlib import Path

from tools.job_queue import (
    CadenceScheduler,
    EnvironmentSecrets,
    JobSpec,
    JobStatus,
    PersistentJobQueue,
    QueueWorkerDaemon,
)


def test_job_queue_enqueue_and_dequeue(tmp_path: Path) -> None:
    queue = PersistentJobQueue(queue_dir=tmp_path / "queue")

    job = JobSpec(
        job_id="JOB-01",
        workflow="produce",
        channel="default",
        variant="3d_cgi",
        topic="Loss Aversion",
        video_id="SH-01",
        slug="short_01",
    )

    queue.enqueue(job)
    pending = queue.list_jobs(JobStatus.PENDING)
    assert len(pending) == 1
    assert pending[0].job_id == "JOB-01"

    dequeued = queue.dequeue()
    assert dequeued is not None
    assert dequeued.job_id == "JOB-01"
    assert dequeued.status == JobStatus.RUNNING

    running = queue.list_jobs(JobStatus.RUNNING)
    assert len(running) == 1


def test_job_queue_complete_job_creates_receipt(tmp_path: Path) -> None:
    queue = PersistentJobQueue(queue_dir=tmp_path / "queue")

    job = JobSpec(
        job_id="JOB-02",
        workflow="produce",
        channel="default",
        variant="3d_cgi",
        topic="The Bystander Effect",
        video_id="SH-02",
        slug="short_02",
    )

    queue.enqueue(job)
    dequeued = queue.dequeue()
    assert dequeued is not None

    artifacts = {"master_mp4": "/path/to/video.mp4", "upload_kit": "/path/to/kit.md"}
    metrics = {"render_s": 42.5}

    receipt = queue.complete_job(dequeued, artifacts=artifacts, metrics=metrics)
    assert receipt.status == "completed"
    assert receipt.video_id == "SH-02"
    assert receipt.durable_hash != ""

    completed = queue.list_jobs(JobStatus.COMPLETED)
    assert len(completed) == 1
    assert completed[0].job_id == "JOB-02"


def test_job_queue_fail_job(tmp_path: Path) -> None:
    queue = PersistentJobQueue(queue_dir=tmp_path / "queue")

    job = JobSpec(
        job_id="JOB-03",
        workflow="produce",
        channel="default",
        variant="3d_cgi",
        topic="Broken Topic",
        video_id="SH-03",
        slug="short_03",
    )

    queue.enqueue(job)
    dequeued = queue.dequeue()
    assert dequeued is not None

    queue.fail_job(dequeued, "Simulated GPU memory exhaustion")

    failed = queue.list_jobs(JobStatus.FAILED)
    assert len(failed) == 1
    assert "GPU memory exhaustion" in failed[0].error


def test_job_queue_human_approval_gate(tmp_path: Path) -> None:
    queue = PersistentJobQueue(queue_dir=tmp_path / "queue")
    alerts: list[str] = []

    def mock_alert(job: JobSpec, reason: str) -> None:
        alerts.append(f"{job.job_id}:{reason}")

    worker = QueueWorkerDaemon(queue, alert_hook=mock_alert)

    job = JobSpec(
        job_id="JOB-04-PUBLISH",
        workflow="publish",
        channel="default",
        variant="3d_cgi",
        topic="Live Upload Topic",
        video_id="SH-04",
        slug="short_04",
        requires_human_approval=True,
        approved=False,
    )
    queue.enqueue(job)

    # Execution without human_approve must halt and alert
    receipt = worker.execute_next_job(human_approve=False)
    assert receipt is None
    assert len(alerts) == 1
    assert "Human approval required" in alerts[0]

    failed = queue.list_jobs(JobStatus.FAILED)
    assert len(failed) == 1


def test_environment_secrets_provisioning(tmp_path: Path, monkeypatch) -> None:
    secret_json = json.dumps({"installed": {"client_id": "test_client_123"}})
    token_json = json.dumps({"token": "ya29.test_token_abc"})

    monkeypatch.setenv("YOUTUBE_CLIENT_SECRETS", secret_json)
    monkeypatch.setenv("YOUTUBE_TOKEN_JSON", token_json)

    creds = EnvironmentSecrets.provision_youtube_credentials(tmp_path / "credentials")
    assert "client_secrets" in creds
    assert "token" in creds

    assert json.loads(creds["client_secrets"].read_text())["installed"]["client_id"] == "test_client_123"
    assert json.loads(creds["token"].read_text())["token"] == "ya29.test_token_abc"


def test_cadence_scheduler(tmp_path: Path) -> None:
    queue = PersistentJobQueue(queue_dir=tmp_path / "queue")
    scheduler = CadenceScheduler(queue)

    topics = [
        "Loss Aversion",
        "The Bystander Effect",
        "Ego Depletion",
        "Confirmation Bias",
        "Parkinson's Law",
    ]

    jobs = scheduler.schedule_topics_for_channel(
        channel="default",
        topics=topics,
        start_id=10,
        variant="3d_cgi",
    )

    assert len(jobs) == 5
    assert jobs[0].video_id == "SH-10"
    assert jobs[4].video_id == "SH-14"

    pending = queue.list_jobs(JobStatus.PENDING)
    assert len(pending) == 5
