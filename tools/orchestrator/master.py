"""Supervisor/orchestrator: plan, dispatch, verify, stop, report, resume."""

from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from pathlib import Path

from .contracts import CheckResult, RunState, Status, TaskRecord, TaskSpec
from .execution import run_worker
from .state import RunContext, RunStore, jsonable, utc_now
from .tools import ProjectTools
from .verifiers import VERIFIERS, artifact_integrity
from .workers import Worker, default_workers


class MasterAgent:
    def __init__(
        self,
        project_root: Path,
        *,
        workers: dict[str, Worker] | None = None,
        verifiers=None,
        console=print,
    ):
        self.root = Path(project_root).resolve()
        self.store = RunStore(self.root)
        self.tools = ProjectTools(self.root)
        self.workers = workers or default_workers()
        self.verifiers = verifiers if verifiers is not None else VERIFIERS
        self.console = console

    def validate(self, tasks: list[TaskSpec]) -> None:
        ids = [task.id for task in tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate task ids")
        known = set(ids)
        for task in tasks:
            for dep in task.depends_on:
                if dep not in known:
                    raise ValueError(f"task '{task.id}' depends on unknown task '{dep}'")
            if task.kind not in self.workers:
                raise ValueError(f"task '{task.id}' uses unknown worker '{task.kind}'")
            for name in task.verifiers:
                if name not in self.verifiers:
                    raise ValueError(f"task '{task.id}' uses unknown verifier '{name}'")
        self._order(tasks)

    def _order(self, tasks: list[TaskSpec]) -> list[str]:
        by_id = {task.id: task for task in tasks}
        indegree = {task.id: 0 for task in tasks}
        children = defaultdict(list)
        for task in tasks:
            for dep in task.depends_on:
                indegree[task.id] += 1
                children[dep].append(task.id)
        queue = [task.id for task in tasks if indegree[task.id] == 0]
        order: list[str] = []
        while queue:
            current = queue.pop(0)
            order.append(current)
            for child in children[current]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        if len(order) != len(by_id):
            raise ValueError("task graph contains a cycle")
        return order

    def new_run(
        self,
        workflow,
        *,
        dry_run: bool = False,
        approve: bool = False,
    ) -> RunState:
        self.validate(workflow.tasks)
        state = self.store.create(
            workflow=workflow.name,
            goal=workflow.goal,
            tasks=workflow.tasks,
            params=workflow.params,
            dry_run=dry_run,
        )
        return self.execute(state, workflow.tasks, approve=approve)

    def resume(self, run_id: str, *, approve: bool = False) -> RunState:
        with self.store.execution_lock(run_id):
            return self._resume_locked(run_id, approve=approve)

    def _resume_locked(self, run_id: str, *, approve: bool) -> RunState:
        state = self.store.load(run_id)
        specs = [record.spec for record in state.tasks.values()]
        self.validate(specs)
        invalidated = {
            task_id for task_id, record in state.tasks.items()
            if record.reconciliation_required
            or (record.status == Status.PASSED and not self._artifacts_intact(record))
            or record.status in {Status.FAILED, Status.BLOCKED, Status.RUNNING, Status.SKIPPED}
        }
        for task_id in self._order(specs):
            record = state.tasks[task_id]
            if any(dep in invalidated for dep in record.spec.depends_on):
                invalidated.add(task_id)
            if task_id not in invalidated:
                continue
            if record.reconciliation_required:
                record.status = Status.BLOCKED
            elif record.status == Status.PASSED and (
                record.spec.requires_approval or record.spec.params.get("strict_release")
            ):
                # A completed external action must never run twice. A strict release also
                # retains its original approval binding: resume cannot bless changed inputs.
                record.reconciliation_required = True
                record.status = Status.BLOCKED
                record.error = (
                    "Release inputs changed; start a fresh release-existing validation before publish."
                    if record.spec.params.get("strict_release")
                    else "Completed approval-required task was invalidated; reconcile the external action before continuing."
                )
                record.summary = record.error
            else:
                record.status = Status.PENDING
                record.artifacts = {}
                record.artifact_fingerprints = {}
                record.data = {}
                record.metrics = {}
                record.checks = []
                record.error = ""
                record.summary = "invalidated on resume"
            self._progress(state, record, record.summary)
        state.dry_run = False
        self.store.save(state)
        self.store.event(run_id, "run_resumed")
        return self._execute_locked(state, specs, approve=approve)

    def execute(self, state: RunState, tasks: list[TaskSpec], *, approve: bool = False) -> RunState:
        with self.store.execution_lock(state.run_id):
            # A resume may have completed between creation and lock acquisition.
            state = self.store.load(state.run_id)
            return self._execute_locked(state, tasks, approve=approve)

    def _execute_locked(self, state: RunState, tasks: list[TaskSpec], *, approve: bool) -> RunState:
        state.status = "running"
        self.store.save(state)
        self.log(state, f"run started: {state.run_id} ({len(tasks)} tasks)")
        order = self._order(tasks)
        ctx = RunContext(
            project_root=self.root,
            run_dir=self.store.run_dir(state.run_id),
            state=state,
            store=self.store,
            tools=self.tools,
            dry_run=state.dry_run,
            approve=approve,
            config={},
        )
        if state.dry_run:
            for task_id in order:
                record = state.tasks[task_id]
                record.status = Status.SKIPPED
                record.summary = "dry-run: planned, not executed"
                record.attempts = 0
                record.finished_at = utc_now()
                self._progress(state, record, record.summary)
            state.status = "planned"
            self.store.save(state)
            report = self.build_report(state)
            report_path = self.store.write_report(state, report)
            self.log(state, f"plan written; report: {report_path}")
            return state
        while True:
            self._block_dependents(state)
            pending = [task_id for task_id in order if state.tasks[task_id].status == Status.PENDING]
            if not pending:
                break
            runnable = [task_id for task_id in pending if self._ready(state, task_id)]
            if not runnable:
                for task_id in pending:
                    record = state.tasks[task_id]
                    record.status = Status.BLOCKED
                    record.summary = "no runnable dependency path"
                self.store.save(state)
                break
            task_id = runnable[0]
            self._run_task(state, ctx, state.tasks[task_id].spec, approve=approve)
        state.status = self._final_status(state)
        self.store.save(state)
        report = self.build_report(state)
        report_path = self.store.write_report(state, report)
        self.log(state, f"run {state.status}; report: {report_path}")
        return state

    def _ready(self, state: RunState, task_id: str) -> bool:
        record = state.tasks[task_id]
        for dep_id in record.spec.depends_on:
            dep = state.tasks[dep_id]
            if dep.status == Status.PASSED:
                continue
            if dep.status == Status.SKIPPED and dep.spec.optional:
                continue
            return False
        return True

    def _block_dependents(self, state: RunState) -> None:
        changed = True
        while changed:
            changed = False
            for record in state.tasks.values():
                if record.status != Status.PENDING:
                    continue
                for dep_id in record.spec.depends_on:
                    dep = state.tasks[dep_id]
                    if dep.status in {Status.FAILED, Status.BLOCKED, Status.SKIPPED} and not dep.spec.optional:
                        record.status = Status.BLOCKED
                        record.summary = f"blocked by '{dep_id}' ({dep.status.value})"
                        record.error = dep.error or record.summary
                        record.finished_at = utc_now()
                        state.progress.append(
                            {
                                "at": utc_now(),
                                "task": record.spec.id,
                                "status": "blocked",
                                "note": record.summary,
                            }
                        )
                        self.store.save(state)
                        changed = True
                        break

    def _run_task(self, state: RunState, ctx: RunContext, spec: TaskSpec, *, approve: bool) -> None:
        record = state.tasks[spec.id]
        record.attempts += 1
        record.started_at = utc_now()
        record.finished_at = ""
        record.duration_s = 0.0
        record.checks = []
        record.error = ""
        record.artifacts = {}
        record.artifact_fingerprints = {}

        if state.dry_run:
            record.status = Status.SKIPPED
            record.summary = "dry-run: not executed"
            record.finished_at = utc_now()
            self._progress(state, record, "planned only")
            self.store.save(state)
            return

        if spec.requires_approval and not approve:
            record.status = Status.SKIPPED
            record.summary = "approval required"
            record.error = "requires explicit --yes"
            record.finished_at = utc_now()
            self._progress(state, record, record.summary)
            self.store.save(state)
            return

        worker = self.workers[spec.kind]
        record.status = Status.RUNNING
        record.worker = worker.kind
        self.store.save(state)
        self.log(state, f"→ {spec.id} [{spec.kind}] attempt {record.attempts}/{spec.max_attempts}")

        started = time.monotonic()
        result = run_worker(worker, spec, ctx)
        duration = round(time.monotonic() - started, 1)

        checks: list[CheckResult] = []
        checks.extend(artifact_integrity(result, ctx))
        for name in spec.verifiers:
            try:
                checks.extend(self.verifiers[name](spec, result, ctx))
            except SystemExit as exc:
                checks.append(
                    CheckResult(
                        name=name,
                        passed=False,
                        severity="critical",
                        message=f"verifier exited the process: SystemExit({exc.code})",
                    )
                )
            except Exception as exc:  # noqa: BLE001
                checks.append(
                    CheckResult(
                        name=name,
                        passed=False,
                        severity="critical",
                        message=f"verifier crashed: {type(exc).__name__}: {exc}",
                    )
                )
        record.artifacts = {k: str(v) for k, v in result.artifacts.items() if v}
        try:
            record.artifact_fingerprints = self._fingerprint_artifacts(record.artifacts)
        except OSError as exc:
            checks.append(CheckResult(name="artifact_fingerprints", passed=False, message=str(exc)))
        critical_failed = [check for check in checks if not check.passed and check.severity == "critical"]

        record.metrics = jsonable(result.metrics)
        record.data = jsonable(result.data)
        record.checks = checks
        record.facts = result.facts
        record.summary = result.summary
        record.duration_s = duration
        record.error = result.error
        record.finished_at = utc_now()

        for fact in result.facts:
            if fact and fact not in state.facts:
                state.facts.append(fact)

        if result.ok and not critical_failed:
            record.status = Status.PASSED
            self._refresh_dependency_fingerprints(state, record)
            self.log(state, f"✓ {spec.id} passed in {duration}s | {result.summary}")
        else:
            record.status = Status.FAILED
            if not result.ok and not critical_failed:
                record.checks.append(
                    CheckResult(
                        name="worker_ok",
                        passed=False,
                        severity="critical",
                        message=result.error or result.summary,
                    )
                )
            reasons = "; ".join(c.message for c in critical_failed[:3]) or result.error or result.summary
            record.summary = f"FAILED: {reasons}" if reasons else "FAILED"
            self.log(state, f"✗ {spec.id} failed: {reasons[:240]}")

        self._progress(state, record, record.summary)
        self.store.save(state)

        if record.status == Status.FAILED and record.attempts < spec.max_attempts and result.retryable:
            record.status = Status.PENDING
            record.summary = f"retrying: {record.summary}"
            self.store.save(state)
            time.sleep(0.5)

    def _progress(self, state: RunState, record: TaskRecord, note: str) -> None:
        state.progress.append(
            {
                "at": utc_now(),
                "task": record.spec.id,
                "status": record.status.value,
                "attempt": record.attempts,
                "note": note[:500],
                "artifacts": sorted(record.artifacts.keys()),
            }
        )

    def _artifacts_intact(self, record: TaskRecord) -> bool:
        has_local_artifact = False
        for value in record.artifacts.values():
            if not value or str(value).startswith(("http://", "https://")):
                continue
            has_local_artifact = True
            path = Path(value)
            if not path.is_absolute():
                path = self.root / path
            if not path.exists():
                return False
        if has_local_artifact and not record.artifact_fingerprints:
            # Older run records have only an existence check. Revalidate them on resume
            # instead of treating unverified bytes as an unchanged pass.
            return False
        if record.artifact_fingerprints:
            try:
                return self._fingerprint_artifacts(record.artifacts) == record.artifact_fingerprints
            except OSError:
                return False
        return True

    def _fingerprint_artifacts(self, artifacts: dict[str, str]) -> dict[str, str]:
        fingerprints = {}
        for name, value in artifacts.items():
            if not value or str(value).startswith(("http://", "https://")):
                continue
            path = Path(value)
            if not path.is_absolute():
                path = self.root / path
            if path.is_dir():
                # Project directories grow during later tasks; their declared files carry
                # content hashes while the directory artifact records its type/existence.
                fingerprints[name] = "directory"
                continue
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            fingerprints[name] = digest.hexdigest()
        return fingerprints

    def _refresh_dependency_fingerprints(self, state: RunState, record: TaskRecord) -> None:
        """Transfer the build's declared project output after a checked mutation.

        A build writes resolved assets back into its input project.json. Declaring that file
        as a build output updates its ancestors' content baseline. Other tasks cannot
        rebind ancestor hashes just by declaring the same path as their own output.
        """
        if record.spec.kind != "build":
            return
        digest = record.artifact_fingerprints.get("project_json")
        if not digest or digest == "directory":
            return
        path = Path(record.artifacts["project_json"])
        outputs = {(path if path.is_absolute() else self.root / path).resolve(): digest}
        pending = list(record.spec.depends_on)
        visited = set()
        while pending:
            task_id = pending.pop()
            if task_id in visited:
                continue
            visited.add(task_id)
            dependency = state.tasks[task_id]
            pending.extend(dependency.spec.depends_on)
            if (
                dependency.status != Status.PASSED
                or dependency.spec.requires_approval
                or dependency.spec.params.get("strict_release")
            ):
                continue
            refreshed = []
            for name, old_digest in dependency.artifact_fingerprints.items():
                path = Path(dependency.artifacts[name])
                digest = outputs.get((path if path.is_absolute() else self.root / path).resolve())
                if digest and digest != old_digest:
                    dependency.artifact_fingerprints[name] = digest
                    refreshed.append(name)
            if refreshed:
                self._progress(
                    state, dependency,
                    f"artifact ownership updated after {record.spec.id}: {', '.join(refreshed)}",
                )

    def _final_status(self, state: RunState) -> str:
        required = [rec for rec in state.tasks.values() if not rec.spec.optional]
        if all(rec.status == Status.PASSED for rec in required):
            return "passed"
        if any(rec.status == Status.FAILED for rec in required):
            return "failed"
        return "blocked"

    def log(self, state: RunState, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.console(f"[master {stamp}] {message}")
        self.store.event(state.run_id, "log", message=message)

    def build_report(self, state: RunState) -> str:
        lines: list[str] = []
        lines.append(f"# Master Run Report — {state.run_id}")
        lines.append("")
        lines.append(f"- **Workflow:** `{state.workflow}`")
        lines.append(f"- **Goal:** {state.goal}")
        lines.append(f"- **Status:** **{state.status.upper()}**")
        lines.append(f"- **Created:** {state.created_at}")
        lines.append(f"- **Dry run:** {state.dry_run}")
        lines.append("")
        lines.append("## Task ledger")
        lines.append("")
        lines.append("| Task | Kind | Status | Attempts | Critical fails | Warnings | Summary |")
        lines.append("|---|---|---|---:|---:|---:|---|")
        for record in state.tasks.values():
            critical = sum(1 for c in record.checks if not c.passed and c.severity == "critical")
            warnings = sum(1 for c in record.checks if not c.passed and c.severity == "warning")
            summary = record.summary.replace("|", "\\|")[:140]
            lines.append(
                f"| `{record.spec.id}` | {record.spec.kind} | {record.status.value} | "
                f"{record.attempts} | {critical} | {warnings} | {summary} |"
            )
        failures = [
            (record, check)
            for record in state.tasks.values()
            for check in record.checks
            if not check.passed and check.severity == "critical"
        ]
        warnings = [
            (record, check)
            for record in state.tasks.values()
            for check in record.checks
            if not check.passed and check.severity == "warning"
        ]
        lines.append("")
        if failures:
            lines.append("## Blocking failures")
            lines.append("")
            for record, check in failures:
                lines.append(f"- **{record.spec.id} / {check.name}:** {check.message}")
        if warnings:
            lines.append("")
            lines.append("## Warnings")
            lines.append("")
            for record, check in warnings[:30]:
                lines.append(f"- {record.spec.id} / {check.name}: {check.message}")
            if len(warnings) > 30:
                lines.append(f"- … {len(warnings) - 30} more")
        lines.append("")
        lines.append("## Artifacts")
        lines.append("")
        for record in state.tasks.values():
            if not record.artifacts:
                continue
            lines.append(f"### {record.spec.id}")
            for name, value in record.artifacts.items():
                lines.append(f"- `{name}`: `{value}`")
        lines.append("")
        lines.append("## Evidence")
        lines.append("")
        for record in state.tasks.values():
            if not record.checks:
                continue
            passed = [c.name for c in record.checks if c.passed]
            failed = [c.name for c in record.checks if not c.passed]
            if passed or failed:
                lines.append(
                    f"- **{record.spec.id}:** passed={passed or 'none'} failed={failed or 'none'}"
                )
        if state.facts:
            lines.append("")
            lines.append("## Facts")
            lines.append("")
            for fact in state.facts[:25]:
                lines.append(f"- {fact}")
        audit = state.tasks.get("audit")
        if audit and audit.data.get("findings"):
            lines.append("")
            lines.append("## Audit findings")
            lines.append("")
            for finding in audit.data["findings"][:40]:
                lines.append(
                    f"- **{finding.get('level')}** {finding.get('project')} / "
                    f"{finding.get('kind')}: {finding.get('detail')}"
                )
            for note in audit.data.get("tracker_findings", [])[:10]:
                lines.append(f"- tracker: {note}")
        lines.append("")
        lines.append("## Progress ledger")
        lines.append("")
        for entry in state.progress[-40:]:
            lines.append(
                f"- {entry.get('at')} `{entry.get('task')}` {entry.get('status')}: "
                f"{str(entry.get('note', ''))[:180]}"
            )
        lines.append("")
        lines.append(
            "Gate policy: critical check failure blocks the task and its dependents; "
            "warnings are surfaced but do not auto-publish. Publication requires a strict `release-existing --publish --yes` run."
        )
        lines.append("")
        return "\n".join(lines)
