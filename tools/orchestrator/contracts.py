"""Typed contracts shared by the master, workers and verifiers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Status(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


@dataclass
class CheckResult:
    name: str
    passed: bool
    severity: str = "critical"  # critical | warning
    message: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "severity": self.severity,
            "message": self.message,
            "metrics": self.metrics,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CheckResult":
        return cls(
            name=data.get("name", ""),
            passed=bool(data.get("passed")),
            severity=data.get("severity", "critical"),
            message=data.get("message", ""),
            metrics=data.get("metrics", {}),
        )


@dataclass
class TaskSpec:
    id: str
    kind: str
    title: str
    params: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    verifiers: list[str] = field(default_factory=list)
    max_attempts: int = 1
    timeout_s: int = 1800
    optional: bool = False
    requires_approval: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "params": self.params,
            "depends_on": self.depends_on,
            "verifiers": self.verifiers,
            "max_attempts": self.max_attempts,
            "timeout_s": self.timeout_s,
            "optional": self.optional,
            "requires_approval": self.requires_approval,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TaskSpec":
        return cls(
            id=data["id"],
            kind=data["kind"],
            title=data.get("title", data["id"]),
            params=data.get("params", {}),
            depends_on=list(data.get("depends_on", [])),
            verifiers=list(data.get("verifiers", [])),
            max_attempts=int(data.get("max_attempts", 1)),
            timeout_s=int(data.get("timeout_s", 1800)),
            optional=bool(data.get("optional", False)),
            requires_approval=bool(data.get("requires_approval", False)),
        )


@dataclass
class WorkerResult:
    ok: bool
    summary: str
    artifacts: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    facts: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    retryable: bool = True

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "summary": self.summary,
            "artifacts": self.artifacts,
            "metrics": self.metrics,
            "facts": self.facts,
            "data": self.data,
            "error": self.error,
            "retryable": self.retryable,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorkerResult":
        return cls(
            ok=bool(data.get("ok")),
            summary=data.get("summary", ""),
            artifacts=data.get("artifacts", {}),
            metrics=data.get("metrics", {}),
            facts=data.get("facts", []),
            data=data.get("data", {}),
            error=data.get("error", ""),
            retryable=bool(data.get("retryable", True)),
        )


@dataclass
class TaskRecord:
    spec: TaskSpec
    status: Status = Status.PENDING
    attempts: int = 0
    worker: str = ""
    summary: str = ""
    artifacts: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    facts: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    checks: list[CheckResult] = field(default_factory=list)
    error: str = ""
    started_at: str = ""
    finished_at: str = ""
    duration_s: float = 0.0
    artifact_fingerprints: dict[str, str] = field(default_factory=dict)
    reconciliation_required: bool = False

    def to_dict(self) -> dict:
        return {
            "spec": self.spec.to_dict(),
            "status": self.status.value,
            "attempts": self.attempts,
            "worker": self.worker,
            "summary": self.summary,
            "artifacts": self.artifacts,
            "metrics": self.metrics,
            "facts": self.facts,
            "data": self.data,
            "checks": [c.to_dict() for c in self.checks],
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_s": self.duration_s,
            "artifact_fingerprints": self.artifact_fingerprints,
            "reconciliation_required": self.reconciliation_required,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TaskRecord":
        return cls(
            spec=TaskSpec.from_dict(data["spec"]),
            status=Status(data.get("status", "pending")),
            attempts=int(data.get("attempts", 0)),
            worker=data.get("worker", ""),
            summary=data.get("summary", ""),
            artifacts=data.get("artifacts", {}),
            metrics=data.get("metrics", {}),
            facts=data.get("facts", []),
            data=data.get("data", {}),
            checks=[CheckResult.from_dict(c) for c in data.get("checks", [])],
            error=data.get("error", ""),
            started_at=data.get("started_at", ""),
            finished_at=data.get("finished_at", ""),
            duration_s=float(data.get("duration_s", 0.0)),
            artifact_fingerprints=data.get("artifact_fingerprints", {}),
            reconciliation_required=bool(data.get("reconciliation_required", False)),
        )


@dataclass
class RunState:
    run_id: str
    workflow: str
    goal: str
    created_at: str
    updated_at: str
    status: str = "pending"
    project_root: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    dry_run: bool = False
    tasks: dict[str, TaskRecord] = field(default_factory=dict)
    facts: list[str] = field(default_factory=list)
    progress: list[dict[str, Any]] = field(default_factory=list)
    report_path: str = ""

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "workflow": self.workflow,
            "goal": self.goal,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "project_root": self.project_root,
            "params": self.params,
            "dry_run": self.dry_run,
            "tasks": {k: v.to_dict() for k, v in self.tasks.items()},
            "facts": self.facts,
            "progress": self.progress,
            "report_path": self.report_path,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RunState":
        return cls(
            run_id=data["run_id"],
            workflow=data["workflow"],
            goal=data.get("goal", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            status=data.get("status", "pending"),
            project_root=data.get("project_root", ""),
            params=data.get("params", {}),
            dry_run=bool(data.get("dry_run", False)),
            tasks={k: TaskRecord.from_dict(v) for k, v in data.get("tasks", {}).items()},
            facts=data.get("facts", []),
            progress=data.get("progress", []),
            report_path=data.get("report_path", ""),
        )
