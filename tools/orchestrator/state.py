"""Durable run ledger and run context."""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.atomic_files import durable_write_text, exclusive_lock

from .contracts import RunState, TaskRecord, TaskSpec
from .tools import ProjectTools


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(text: str, limit: int = 32) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return value[:limit] or "run"


def new_run_id(workflow: str) -> str:
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{_slug(workflow)}-{uuid.uuid4().hex[:4]}"


def jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    if hasattr(value, "value") and not isinstance(value, (str, int, float, bool)):
        return value.value
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class RunStore:
    def __init__(self, project_root: Path):
        self.root = Path(project_root).resolve()
        override = os.environ.get("ORCHESTRATOR_RUNS_DIR") or os.environ.get("FRAMEFORGE_RUNS_DIR")
        if override:
            self.runs_dir = Path(override).resolve()
            self.runs_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.runs_dir = self.root / ".orchestrator" / "runs"
            try:
                self.runs_dir.mkdir(parents=True, exist_ok=True)
                probe = self.runs_dir / f".probe_{os.getpid()}"
                probe.mkdir(exist_ok=True)
                probe.rmdir()
            except (PermissionError, OSError):
                fallback = Path(tempfile.gettempdir()) / ".orchestrator" / "runs"
                fallback.mkdir(parents=True, exist_ok=True)
                self.runs_dir = fallback

    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    def execution_lock(self, run_id: str, *, blocking: bool = False):
        """Serialize dispatch and resume before reading or changing run state."""
        return exclusive_lock(self.run_dir(run_id) / "execution.lock", blocking=blocking)

    def create(
        self,
        workflow: str,
        goal: str,
        tasks: list[TaskSpec],
        *,
        params: dict | None = None,
        dry_run: bool = False,
    ) -> RunState:
        now = utc_now()
        state = RunState(
            run_id=new_run_id(workflow),
            workflow=workflow,
            goal=goal,
            created_at=now,
            updated_at=now,
            project_root=str(self.root),
            params=params or {},
            dry_run=dry_run,
            tasks={spec.id: TaskRecord(spec=spec) for spec in tasks},
        )
        (self.run_dir(state.run_id)).mkdir(parents=True, exist_ok=True)
        self.save(state)
        self.event(state.run_id, "run_created", workflow=workflow, goal=goal, dry_run=dry_run)
        return state

    def load(self, run_id: str) -> RunState:
        path = self.run_dir(run_id) / "run.json"
        if not path.exists():
            raise FileNotFoundError(f"run not found: {run_id}")
        return RunState.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def latest(self) -> RunState | None:
        runs = sorted([p for p in self.runs_dir.iterdir() if p.is_dir()], reverse=True)
        for run_dir in runs:
            path = run_dir / "run.json"
            if path.exists():
                return RunState.from_dict(json.loads(path.read_text(encoding="utf-8")))
        return None

    def save(self, state: RunState) -> None:
        state.updated_at = utc_now()
        run_dir = self.run_dir(state.run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(jsonable(state.to_dict()), indent=2, ensure_ascii=False)
        durable_write_text(run_dir / "run.json", payload)

    def write_report(self, state: RunState, report: str) -> Path:
        run_dir = self.run_dir(state.run_id)
        path = run_dir / "REPORT.md"
        durable_write_text(path, report)
        state.report_path = str(path)
        self.save(state)
        return path

    def event(self, run_id: str, event: str, **fields: Any) -> None:
        run_dir = self.run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        payload = {"at": utc_now(), "event": event, **jsonable(fields)}
        with (run_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


@dataclass
class RunContext:
    project_root: Path
    run_dir: Path
    state: RunState
    store: RunStore
    tools: ProjectTools
    dry_run: bool = False
    approve: bool = False
    config: dict[str, Any] | None = None

    def dep(self, task_id: str) -> TaskRecord:
        return self.state.tasks[task_id]

    def dep_data(self, task_id: str) -> dict:
        return self.state.tasks[task_id].data

    def artifact(self, task_id: str, name: str, default: str | None = None) -> str | None:
        record = self.state.tasks.get(task_id)
        if not record:
            return default
        return record.artifacts.get(name, default)

    def project_json(self) -> Path | None:
        for task_id in ("release", "project", "script", "research"):
            value = self.artifact(task_id, "project_json")
            if value:
                path = Path(value)
                return path if path.is_absolute() else self.project_root / path
        return None

    @property
    def root(self) -> Path:
        return self.project_root
