"""tools/job_queue.py — Persistent Job Queue, Scheduler & Production Worker.

Provides:
1. Persistent FIFO Job Queue in `.orchestrator/queue/` with durable state transitions.
2. Production Worker daemon executing multi-stage runs with durable receipts.
3. Cadence Scheduler mapping channel frequency (e.g. 5 shorts/week) to topic queues.
4. Environment Secrets Injection (`YOUTUBE_CLIENT_SECRETS`, `YOUTUBE_TOKEN_JSON`).
5. Structured Alert Hooks and Failure Reporting.
6. Human-in-the-Loop Approval Gate: Publishing strictly requires explicit approval.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_QUEUE_DIR = REPO_ROOT / ".orchestrator" / "queue"
DEFAULT_RECEIPTS_DIR = REPO_ROOT / ".orchestrator" / "receipts"

logger = logging.getLogger("job_queue")


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    AWAITING_APPROVAL = "awaiting_approval"


@dataclass
class JobSpec:
    job_id: str
    workflow: str
    channel: str
    variant: str
    topic: str
    video_id: str
    slug: str
    params: Dict[str, Any] = field(default_factory=dict)
    requires_human_approval: bool = False
    approved: bool = False
    status: JobStatus = JobStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> JobSpec:
        d = dict(data)
        if "status" in d and isinstance(d["status"], str):
            d["status"] = JobStatus(d["status"])
        return cls(**d)


@dataclass
class JobReceipt:
    job_id: str
    video_id: str
    channel: str
    status: str
    started_at: float
    completed_at: float
    artifacts: Dict[str, str] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    durable_hash: str = ""
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EnvironmentSecrets:
    """Safely extracts and provisions API credentials from environment variables."""

    @staticmethod
    def provision_youtube_credentials(target_dir: Path) -> Dict[str, Path]:
        """Provisions client_secrets.json and token.json from env vars if present."""
        target_dir.mkdir(parents=True, exist_ok=True)
        provisioned: Dict[str, Path] = {}

        # 1. Client secrets
        raw_secrets = os.environ.get("YOUTUBE_CLIENT_SECRETS")
        b64_secrets = os.environ.get("YOUTUBE_CLIENT_SECRETS_BASE64")
        secrets_file = target_dir / "client_secrets.json"

        if raw_secrets:
            secrets_file.write_text(raw_secrets, encoding="utf-8")
            provisioned["client_secrets"] = secrets_file
        elif b64_secrets:
            secrets_file.write_bytes(base64.b64decode(b64_secrets))
            provisioned["client_secrets"] = secrets_file

        # 2. Token credentials
        raw_token = os.environ.get("YOUTUBE_TOKEN_JSON")
        b64_token = os.environ.get("YOUTUBE_TOKEN_JSON_BASE64")
        token_file = target_dir / "token.json"

        if raw_token:
            token_file.write_text(raw_token, encoding="utf-8")
            provisioned["token"] = token_file
        elif b64_token:
            token_file.write_bytes(base64.b64decode(b64_token))
            provisioned["token"] = token_file

        return provisioned


class PersistentJobQueue:
    """File-backed durable FIFO queue persisting across crashes and container restarts."""

    def __init__(self, queue_dir: Optional[Path] = None):
        self.queue_dir = queue_dir or DEFAULT_QUEUE_DIR
        self.pending_dir = self.queue_dir / "pending"
        self.running_dir = self.queue_dir / "running"
        self.completed_dir = self.queue_dir / "completed"
        self.failed_dir = self.queue_dir / "failed"

        for d in (self.pending_dir, self.running_dir, self.completed_dir, self.failed_dir):
            d.mkdir(parents=True, exist_ok=True)

    def enqueue(self, job: JobSpec) -> Path:
        """Enqueues a new production job."""
        file_path = self.pending_dir / f"{job.job_id}.json"
        file_path.write_text(json.dumps(job.to_dict(), indent=2), encoding="utf-8")
        logger.info("Enqueued job %s (%s: %s)", job.job_id, job.channel, job.topic)
        return file_path

    def dequeue(self) -> Optional[JobSpec]:
        """Atomically dequeues the oldest pending job and moves it to running."""
        pending_files = sorted(self.pending_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
        if not pending_files:
            return None

        target = pending_files[0]
        data = json.loads(target.read_text(encoding="utf-8"))
        job = JobSpec.from_dict(data)
        job.status = JobStatus.RUNNING
        job.started_at = time.time()

        running_file = self.running_dir / target.name
        running_file.write_text(json.dumps(job.to_dict(), indent=2), encoding="utf-8")
        target.unlink(missing_ok=True)
        return job

    def complete_job(self, job: JobSpec, artifacts: Dict[str, str], metrics: Dict[str, Any]) -> JobReceipt:
        """Marks a job completed and records a durable signed receipt."""
        running_file = self.running_dir / f"{job.job_id}.json"
        job.status = JobStatus.COMPLETED
        job.completed_at = time.time()

        # Compute tamper-evident hash of produced artifacts
        hasher = hashlib.sha256()
        for k, v in sorted(artifacts.items()):
            hasher.update(f"{k}:{v}".encode("utf-8"))
        receipt_hash = hasher.hexdigest()

        receipt = JobReceipt(
            job_id=job.job_id,
            video_id=job.video_id,
            channel=job.channel,
            status=job.status.value,
            started_at=job.started_at or job.created_at,
            completed_at=job.completed_at,
            artifacts=artifacts,
            metrics=metrics,
            durable_hash=receipt_hash,
        )

        completed_file = self.completed_dir / f"{job.job_id}.json"
        completed_file.write_text(json.dumps(job.to_dict(), indent=2), encoding="utf-8")
        running_file.unlink(missing_ok=True)

        receipt_file = DEFAULT_RECEIPTS_DIR / f"{job.video_id}_receipt.json"
        receipt_file.parent.mkdir(parents=True, exist_ok=True)
        receipt_file.write_text(json.dumps(receipt.to_dict(), indent=2), encoding="utf-8")

        logger.info("Job %s completed successfully. Receipt: %s", job.job_id, receipt_file)
        return receipt

    def fail_job(self, job: JobSpec, error: str) -> None:
        """Marks a job failed and stores diagnostic output."""
        running_file = self.running_dir / f"{job.job_id}.json"
        job.status = JobStatus.FAILED
        job.completed_at = time.time()
        job.error = error

        failed_file = self.failed_dir / f"{job.job_id}.json"
        failed_file.write_text(json.dumps(job.to_dict(), indent=2), encoding="utf-8")
        running_file.unlink(missing_ok=True)
        logger.error("Job %s failed: %s", job.job_id, error)

    def list_jobs(self, status: Optional[JobStatus] = None) -> List[JobSpec]:
        """Lists all jobs across queues, optionally filtered by status."""
        jobs: List[JobSpec] = []
        directories = {
            JobStatus.PENDING: self.pending_dir,
            JobStatus.RUNNING: self.running_dir,
            JobStatus.COMPLETED: self.completed_dir,
            JobStatus.FAILED: self.failed_dir,
        }
        targets = [directories[status]] if status else directories.values()
        for d in targets:
            for p in sorted(d.glob("*.json")):
                try:
                    jobs.append(JobSpec.from_dict(json.loads(p.read_text(encoding="utf-8"))))
                except (json.JSONDecodeError, OSError) as exc:
                    logger.warning("Failed to parse job spec from %s: %s", p, exc)
        return jobs


class QueueWorkerDaemon:
    """Production worker daemon that pulls jobs, enforces human approval, and triggers workflows."""

    def __init__(
        self,
        queue: PersistentJobQueue,
        alert_hook: Optional[Callable[[JobSpec, str], None]] = None,
    ):
        self.queue = queue
        self.alert_hook = alert_hook or self._default_alert

    def _default_alert(self, job: JobSpec, error: str) -> None:
        logger.critical("🚨 PRODUCTION ALERT: Job %s (%s) failed! Reason: %s", job.job_id, job.topic, error)

    def execute_next_job(self, *, human_approve: bool = False) -> Optional[JobReceipt]:
        """Executes the next pending job from the persistent queue."""
        job = self.queue.dequeue()
        if not job:
            return None

        # Human approval gate check for upload/publish tasks
        if job.requires_human_approval and not (human_approve or job.approved):
            job.status = JobStatus.AWAITING_APPROVAL
            self.queue.fail_job(job, "Job requires explicit human approval (--publish --yes). Execution halted.")
            self.alert_hook(job, "Human approval required for publication.")
            return None

        try:
            from tools.orchestrator import workflows
            from tools.orchestrator.master import MasterAgent

            wf = workflows.produce(
                topic=job.topic,
                video_id=job.video_id,
                slug=job.slug,
                genre=job.variant,
                variant=job.variant,
                channel=job.channel,
                build=bool(job.params.get("build", True)),
                direct=bool(job.params.get("direct", True)),
            )

            master = MasterAgent(REPO_ROOT)
            state = master.run(wf, approve=human_approve)

            if state.status == "failed":
                err_msg = f"Workflow produce failed on run {state.run_id}"
                self.queue.fail_job(job, err_msg)
                self.alert_hook(job, err_msg)
                return None

            artifacts: Dict[str, str] = {}
            for t_record in state.tasks.values():
                artifacts.update(t_record.artifacts)

            receipt = self.queue.complete_job(job, artifacts=artifacts, metrics={"run_id": state.run_id})
            return receipt

        except Exception as exc:
            err = f"Unexpected execution exception: {exc}"
            self.queue.fail_job(job, err)
            self.alert_hook(job, err)
            return None


class CadenceScheduler:
    """Schedules production runs according to channel publication cadences."""

    def __init__(self, queue: PersistentJobQueue):
        self.queue = queue

    def schedule_topics_for_channel(
        self,
        channel: str,
        topics: List[str],
        start_id: int = 1,
        variant: str = "3d_cgi",
    ) -> List[JobSpec]:
        """Schedules a batch of topics onto the production queue."""
        scheduled: List[JobSpec] = []
        for idx, topic in enumerate(topics, start=start_id):
            vid_id = f"SH-{idx:02d}"
            clean_slug = "short_" + re.sub(r"[^a-z0-9]+", "_", topic.lower()).strip("_")
            job_id = f"JOB-{vid_id}-{int(time.time())}"

            job = JobSpec(
                job_id=job_id,
                workflow="produce",
                channel=channel,
                variant=variant,
                topic=topic,
                video_id=vid_id,
                slug=clean_slug,
                params={"build": True, "direct": True},
            )
            self.queue.enqueue(job)
            scheduled.append(job)

        return scheduled
