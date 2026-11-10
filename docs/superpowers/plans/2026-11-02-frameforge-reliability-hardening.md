# FrameForge Reliability Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement audit improvements 1–7 so FrameForge validates real media, bounds execution, reuses renders by identity, prepares versioned release evidence, has one canonical coordinator, persists concurrent state durably, and carries no acknowledged XFAIL/data/documentation debt.

**Architecture:** Preserve the current master/worker/verifier design. Add narrow shared modules for process supervision, render manifests, schema validation, and durable file operations, then integrate them at existing boundaries. Keep all network/model/upload behavior out of tests and retain legacy CLIs as adapters rather than independent coordinators.

**Tech Stack:** Python 3.11, dataclasses, multiprocessing/fcntl/os/subprocess, pytest, FFmpeg/FFprobe, JSON and Markdown.

**Spec:** `docs/superpowers/specs/2026-11-02-frameforge-reliability-hardening-design.md`

## Global Constraints

- Implement only selected audit items 1–7; do not initialize Git, add CI, migrate Python, or implement channel profiles.
- Use strict test-first red/green cycles for every behavior change; record the failing and passing command in each task report.
- Never invoke network services, model generation, upload, publication, or YouTube APIs.
- Preserve strict-release approval, fingerprints, receipt locking, synthetic-media declaration, and channel identity checks.
- Real media tests must be offline and CPU-only, create artifacts only under pytest `tmp_path`, and use H.264 video plus AAC 48 kHz audio at 30 fps.
- A strict release must reject unreviewed evidence drafts.
- Legacy commands remain available but must dispatch the canonical master workflow.
- No implementation task runs in parallel with another implementation task.
- Because this workspace is not a Git checkout and audit item 8 is excluded, use a read-only baseline snapshot plus `diff -ruN` review packages instead of commits. Do not initialize Git.

## File structure

- `tools/processes.py`: bounded subprocess execution and process-group termination.
- `tools/orchestrator/execution.py`: isolated worker execution with `TaskSpec.timeout_s`.
- `tools/render_manifest.py`: scene-input fingerprints and atomic render-cache manifest records.
- `tools/schemas.py`: runtime project/evidence validation and release-draft creation.
- `tools/atomic_files.py`: durable atomic text/JSON writes and file locks.
- `tools/policy.py`: lightweight shared production constants such as word bands.
- Existing pipeline/orchestrator/legacy modules integrate those focused services.
- Tests remain grouped by behavior: actual media, execution deadlines, render identity, schemas/release preparation, legacy routing/import safety, durable concurrency, and content honesty.

## Blast-radius trace

Before planning, the master ran `tools/master.py impact --path` for every existing module below and `impact --name` for affected keys/commands. Reported production/test/doc sites are part of the tasks that follow; historical `.superpowers/sdd/2026-11-02-short-13-safe-release/` scratch sites are read-only evidence and are not edited.

- `tools/pipeline.py` — 109 sites across `CONTENT_TRACKER.md`, `GEMINI.md`, `channel_assets/YOUTUBE_API_GUIDE.md`, requirements, Shorts docs, 10 test modules, `tools/agents.py`, and orchestrator workers/verifiers.
- `tools/visual_engine.py` — 22 sites across `GEMINI.md`, requirements, `build_video.py`, `pipeline.py`, `studio_3d.py`, and release verification.
- `tools/build_video.py` — 21 sites across production guides, audio docs, branding/project tests, and `pipeline.py`.
- `tools/creative_engine.py` — 22 sites across production docs, creative/orchestrator/project/release tests, agents, workers, and pipeline.
- `tools/agents.py` — 26 sites across production docs, legacy-route/failure tests, orchestrator docs, and pipeline.
- `tools/orchestrator/master.py` — 113 sites across `AGENTS.md`, `README.md`, production/API guides, reports/specs/plans, impact tests, and orchestrator docs.
- `tools/orchestrator/state.py` — 6 sites in orchestrator docs/specs/plans and historical scratch.
- `tools/tracker.py` — 6 sites in tracker/upload tests and pipeline/upload integrations.
- `tools/orchestrator/workflows.py` — 15 sites in release tests, impact tests, orchestrator docs, specs/plans/reports, and historical scratch.
- `tools/orchestrator/cli.py` — 12 sites in legacy/release/impact tests and docs/specs/plans/reports.
- `tools/orchestrator/workers.py` — 22 sites in CLI, impact tests, orchestrator docs, specs/plans/reports, and historical scratch.
- `tools/orchestrator/verifiers.py` — 23 sites in requirements, hook/project/orchestrator/release/impact tests, orchestrator docs, specs/plans/reports, and `GEMINI.md`.
- `project.json` reported four workflow-construction sites. `scientific_dossiers.json` reported `AGENTS.md`, `GEMINI.md`, and the prior release plan. The existing index reported no current sites for new `prepare-release`, render-manifest names, or schema-version names.

---

### Task 1: Real media acceptance and decode-aware release validation

**Files:**
- Modify: `tools/pipeline.py:602-679`
- Modify: `tools/visual_engine.py:230-283`
- Modify: `tools/orchestrator/verifiers.py:543-620`
- Modify: `pyproject.toml:12-34`
- Create: `tests/test_media_acceptance.py`
- Modify: `tests/test_pipeline_validation.py`

**Interfaces:**
- Produces: `pipeline.verify_rendered_mp4(mp4_path: Path, format_type: str = "short", *, probe_timeout_s: float = 30.0, decode_timeout_s: float = 90.0) -> dict`.
- Consumes: a real local FFmpeg/FFprobe installation; no network or model dependency.
- Result adds `tail_decodable`, `video_duration_s`, `audio_duration_s`, and `av_duration_delta_s`; `valid` is false if tail decode fails or duration delta exceeds `0.250` seconds.

- [ ] **Step 1: Write actual-media failing tests**

  Add a fixture that runs FFmpeg against `lavfi` color and sine sources for `5.2` seconds, emitting `1080x1920`, 30 fps, H.264, AAC 48 kHz to `tmp_path`. Assert the real verifier returns `valid=True`, `tail_decodable=True`, and duration delta `<= 0.250`. Copy and truncate the file and assert `valid=False` with a decode/probe error. Generate a 5.2-second video with 1-second audio and assert it is rejected for A/V divergence.

- [ ] **Step 2: Verify RED**

  Run: `.venv/bin/python -m pytest -q tests/test_media_acceptance.py`

  Expected: failures because the verifier does not decode the tail, expose per-stream durations, or reject duration divergence.

- [ ] **Step 3: Implement minimal decode-aware verification**

  Extend ffprobe entries to include per-stream duration, apply explicit probe timeout, reuse a public `visual_engine.verify_video_decodable(path, timeout=...)` wrapper around the existing tail-frame decoder, and aggregate failures without hiding probe diagnostics. Do not accept header-only media.

- [ ] **Step 4: Verify GREEN and regression scope**

  Run: `.venv/bin/python -m pytest -q tests/test_media_acceptance.py tests/test_pipeline_validation.py tests/test_release_existing.py`

  Expected: all tests pass; real media creation/decoding runs, no mocks assert FFmpeg behavior.

- [ ] **Step 5: Record evidence**

  Write the red/green commands, measured media metadata, files changed, and concerns to the task report. Preserve generated files only under pytest temporary directories.

### Task 2: Worker deadlines and bounded subprocesses

**Files:**
- Create: `tools/processes.py`
- Create: `tools/orchestrator/execution.py`
- Modify: `tools/orchestrator/master.py:250-274`
- Modify: `tools/pipeline.py:602-614`
- Modify: `tools/build_video.py:984-999,1080-1100`
- Modify: `tools/branding_engine.py:565-583`
- Modify: `tools/visual_engine.py:827-929,1917-1926`
- Create: `tests/test_execution_timeouts.py`
- Modify: `tests/test_orchestrator.py`

**Interfaces:**
- Produces: `processes.run_process(argv, *, timeout_s, cwd=None, capture_output=True, text=True, check=False) -> subprocess.CompletedProcess` with `ProcessDeadlineExceeded` on timeout and process-group cleanup.
- Produces: `execution.run_worker(worker, spec: TaskSpec, ctx: RunContext) -> WorkerResult`; deadline comes from `spec.timeout_s`.
- Master consumes `run_worker` instead of calling `worker.run` directly.

- [ ] **Step 1: Write deadline failures first**

  Add one fake worker that sleeps past a one-second timeout and another that spawns a long-lived child. Assert the master returns within three seconds, records a failed non-retryable timeout result, does not run dependents, and leaves no spawned child alive. Add a direct `run_process` test with a sleeping process and the same cleanup expectation.

- [ ] **Step 2: Verify RED**

  Run: `.venv/bin/python -m pytest -q tests/test_execution_timeouts.py`

  Expected: the master hangs past the asserted bound or lacks the execution API.

- [ ] **Step 3: Implement supervised workers**

  On POSIX, fork a child, call `os.setsid()`, execute the worker, send a serializable `WorkerResult` through a pipe, and close descriptors. The parent waits only for `timeout_s`; on expiry send `SIGTERM` to the process group, wait `1.0` second, then send `SIGKILL`. Convert child exceptions/SystemExit/serialization failure into explicit worker results. Always reap the child.

- [ ] **Step 4: Apply the subprocess policy**

  Replace the identified unbounded ffprobe, branding, concat, Blender, and motion-decode processes with explicit deadlines and group cleanup. Preserve existing encoder-specific timeouts and stderr sidecars.

- [ ] **Step 5: Verify GREEN and regression scope**

  Run: `.venv/bin/python -m pytest -q tests/test_execution_timeouts.py tests/test_orchestrator.py tests/test_media_acceptance.py tests/test_branding.py`

  Expected: deadline/cleanup assertions and all affected regression tests pass.

- [ ] **Step 6: Record evidence**

  Include wall-clock bounds, killed PIDs/process groups, durable task state, commands, and changed files in the task report.

### Task 3: Collision-safe projects and content-addressed render manifests

**Files:**
- Create: `tools/render_manifest.py`
- Modify: `tools/creative_engine.py:523-605`
- Modify: `tools/orchestrator/workers.py:238-305`
- Modify: `tools/pipeline.py:831-914`
- Create: `tests/test_render_manifest.py`
- Modify: `tests/test_creative_engine.py`
- Modify: `tests/test_pipeline_validation.py`

**Interfaces:**
- Produces: `render_manifest.scene_fingerprint(*, scene_index, scene, source_image, duration_s, preset, width, height) -> str`.
- Produces: `RenderManifest.load(path)`, `can_reuse(scene_key, fingerprint, output_path)`, `record(...)`, and `save()`.
- Changes: `generate_creative_project(..., overwrite: bool = False) -> Path`; an existing `project.json` raises `FileExistsError` unless overwrite is explicit.

- [ ] **Step 1: Write collision and identity tests**

  Assert a second generation into the same slug refuses replacement and leaves the original bytes unchanged. Assert identical scene inputs plus unchanged output hash reuse one scene, while changing prompt, source-image bytes, duration, preset, dimensions, or renderer contract version invalidates exactly that scene. Assert an output-byte change invalidates reuse even with matching inputs.

- [ ] **Step 2: Verify RED**

  Run: `.venv/bin/python -m pytest -q tests/test_render_manifest.py tests/test_creative_engine.py -k 'collision or manifest or fingerprint'`

  Expected: missing manifest API and silent overwrite/reuse behavior fail.

- [ ] **Step 3: Implement manifest primitives and collision preflight**

  Use SHA-256 over canonical sorted JSON plus the source image hash. Store `schema_version=1`, renderer contract version, per-scene fingerprint, output relative path, and output SHA-256 in `cache/render_manifest.json`. Save atomically. Do not place manifest keys into authored `project.json`.

- [ ] **Step 4: Integrate selective rendering**

  Pipeline reuse requires manifest match, output hash match, and motion-quality pass. Missing/mismatched data rerenders only that scene, then records the new output. ProjectWorker reports collision as a deterministic non-retryable failure with the conflicting path.

- [ ] **Step 5: Verify GREEN and regression scope**

  Run: `.venv/bin/python -m pytest -q tests/test_render_manifest.py tests/test_creative_engine.py tests/test_pipeline_validation.py tests/test_orchestrator.py`

  Expected: selective invalidation and collision behavior pass without invoking model generation.

- [ ] **Step 6: Record evidence**

  Include the literal fingerprints used by tests, invalidation matrix, commands, files changed, and any compatibility ruling.

### Task 4: Runtime schemas and `prepare-release`

**Files:**
- Create: `tools/schemas.py`
- Modify: `tools/pipeline.py:831-845`
- Modify: `tools/orchestrator/verifiers.py:145-239,457-491`
- Modify: `tools/orchestrator/cli.py`
- Modify: `tools/orchestrator/workflows.py`
- Modify: `tools/orchestrator/impact.py` registries if required for the new subcommand
- Create: `tests/test_schemas.py`
- Create: `tests/test_prepare_release.py`
- Modify: `tests/test_release_existing.py`
- Modify: `tests/test_impact.py`
- Modify: `tools/orchestrator/README.md`

**Interfaces:**
- Produces: `schemas.validate_project(data: dict, *, project_path: Path | None = None) -> list[str]`.
- Produces: `schemas.validate_evidence(data: dict, *, project: dict | None = None, evidence_path: Path | None = None) -> list[str]`.
- Produces: `schemas.prepare_release_draft(project_path: Path, output_path: Path, dossier: dict | None = None) -> Path`.
- Adds CLI: `.venv/bin/python tools/master.py prepare-release --project PATH [--output PATH]`.

- [ ] **Step 1: Write schema failures**

  Hand-build literal valid and invalid project/evidence dictionaries. Assert the validator returns every actionable error together for malformed identity, unsupported format, unsafe paths, scene count/type errors, duplicate scene IDs, invalid audio options, wrong script hash, missing page locators, unreviewed status, and mismatched video ID.

- [ ] **Step 2: Write draft-command failures**

  Assert `prepare-release` writes `schema_version: 1`, `status: draft`, matching video ID and script SHA-256, empty human-review fields where source data is absent, and no `citation_verified` mutation. Assert strict release rejects that draft specifically as unreviewed.

- [ ] **Step 3: Verify RED**

  Run: `.venv/bin/python -m pytest -q tests/test_schemas.py tests/test_prepare_release.py`

  Expected: missing schema/draft APIs and subcommand failures.

- [ ] **Step 4: Implement validators and command**

  Use no external schema dependency. Validate before `build_and_verify` creates cache/output directories or ensures SFX. The project verifier consumes the same errors. `prepare-release` may copy only fields already present in project/dossier and must never mark a draft reviewed or citations verified.

- [ ] **Step 5: Integrate strict release**

  Require `schema_version=1` and `status=reviewed` for new evidence. Maintain explicitly tested compatibility for the existing reviewed SH-13 evidence only if its full strict contract passes; otherwise migrate that checked-in evidence by adding version/status without changing claims.

- [ ] **Step 6: Verify GREEN and impact**

  Run: `.venv/bin/python -m pytest -q tests/test_schemas.py tests/test_prepare_release.py tests/test_release_existing.py tests/test_project_contract.py tests/test_impact.py`

  Run: `.venv/bin/python tools/master.py impact --name prepare-release`

  Expected: tests pass and every command/document reference resolves.

- [ ] **Step 7: Record evidence**

  Include sample draft path/content summary, rejection reason, commands, changed files, and compatibility decision.

### Task 5: Pure imports and one canonical production coordinator

**Files:**
- Create: `tools/runtime.py`
- Create: `tools/policy.py`
- Create: `tools/orchestrator/legacy.py`
- Modify: `tools/pipeline.py:34-74,1150-1205`
- Modify: `tools/build_video.py:32-64`
- Modify: `tools/visual_engine.py:111-125`
- Modify: `tools/orchestrator/verifiers.py:300-365`
- Modify: `tools/agents.py:530-603,640-685`
- Modify: `tools/orchestrator/cli.py` to expose an internal canonical production runner
- Create: `tests/test_runtime_imports.py`
- Modify: `tests/test_agents_failure.py`
- Modify: `tests/test_legacy_upload_routes.py`
- Modify: `tests/test_orchestrator.py`
- Modify: `GEMINI.md` legacy-command descriptions where behavior changes

**Interfaces:**
- Produces: `runtime.ensure_venv_cli(script: Path, argv: list[str] | None = None) -> None`, called only when a file is executed as `__main__`.
- Produces: `policy.WORD_BANDS` as the single shared band mapping.
- Produces: `legacy.run_production_compat(...) -> RunState`; both legacy CLIs consume it.

- [ ] **Step 1: Write import-safety and routing tests**

  Patch `os.execv` to raise and reload/import the three render modules; imports must succeed without invoking it. Assert explicit CLI bootstrap invokes the runtime helper when appropriate. Replace legacy production dependencies with a recording canonical runner and assert `pipeline --agents/--auto`, `agents.py --run`, and `OrchestratorAgent.run_end_to_end` all dispatch the master workflow once and do not call legacy research/script/render agents.

- [ ] **Step 2: Verify RED**

  Run: `.venv/bin/python -m pytest -q tests/test_runtime_imports.py tests/test_agents_failure.py tests/test_legacy_upload_routes.py`

  Expected: module-level bootstrap or independent legacy DAG assertions fail.

- [ ] **Step 3: Move runtime and policy boundaries**

  Guard re-exec behind `__name__ == "__main__"` before heavy imports. Replace verifier imports of pipeline used only for word bands with `tools.policy`. Preserve direct CLI behavior and exit codes.

- [ ] **Step 4: Implement canonical compatibility adapter**

  Build the canonical `produce` workflow and run it through `MasterAgent`. Convert task records to legacy `AgentReport` objects only for display compatibility. Upload requests remain rejected unless routed through a separately validated `release-existing` call with reviewed evidence and explicit approval.

- [ ] **Step 5: Verify GREEN and regression scope**

  Run: `.venv/bin/python -m pytest -q tests/test_runtime_imports.py tests/test_agents_failure.py tests/test_legacy_upload_routes.py tests/test_orchestrator.py tests/test_release_existing.py`

  Expected: imports are side-effect-safe, all production routes use the master, upload safety remains intact.

- [ ] **Step 6: Record evidence**

  Include dispatch call counts, import subprocess results, commands, changed files, and preserved legacy behavior.

### Task 6: Durable run and tracker concurrency

**Files:**
- Create: `tools/atomic_files.py`
- Modify: `tools/orchestrator/state.py:46-118`
- Modify: `tools/orchestrator/master.py:71-132`
- Modify: `tools/tracker.py:190-254`
- Modify: `tools/orchestrator/cli.py` error reporting for a busy run
- Create: `tests/test_durable_state.py`
- Modify: `tests/test_tracker_schema.py`
- Modify: `tests/test_orchestrator.py`
- Modify: `tests/test_upload_safety.py`

**Interfaces:**
- Produces: `atomic_files.durable_write_text(path: Path, text: str, *, mode: int | None = None) -> None`.
- Produces: `atomic_files.exclusive_lock(path: Path, *, blocking: bool = True)` context manager and `LockBusy`.
- Produces: `RunStore.execution_lock(run_id: str, *, blocking: bool = False)`.

- [ ] **Step 1: Write durable/concurrent failures**

  Run two processes that update distinct tracker rows concurrently and assert both updates survive. Inject a failure before replace and assert original bytes remain. Run two resumes against one pending run and assert exactly one worker execution while the other receives a clear busy result. Assert no shared fixed `.tmp` filename is used.

- [ ] **Step 2: Verify RED**

  Run: `.venv/bin/python -m pytest -q tests/test_durable_state.py tests/test_tracker_schema.py -k 'concurrent or atomic or resume or failure'`

  Expected: lost-update, duplicate-execution, or missing API failures.

- [ ] **Step 3: Implement durable primitives**

  Create a unique temporary file beside the destination, write/flush/fsync, preserve requested mode, replace, fsync the directory, and clean up on error. File locks use `fcntl.flock`; lock files contain no secrets.

- [ ] **Step 4: Integrate locks**

  Hold the run execution lock around dispatch/resume state transitions. Hold one tracker lock across the complete read/modify/write transaction. Convert busy-run errors into an operator-facing nonzero CLI result without a traceback.

- [ ] **Step 5: Verify GREEN and regression scope**

  Run: `.venv/bin/python -m pytest -q tests/test_durable_state.py tests/test_tracker_schema.py tests/test_orchestrator.py tests/test_upload_safety.py`

  Expected: concurrent updates serialize, original data survives injected failure, and duplicate resume execution is impossible.

- [ ] **Step 6: Record evidence**

  Include process counts, final tracker rows, surviving bytes after injected failure, commands, and changed files.

### Task 7: Eliminate XFAIL, data drift, audit ambiguity, and contradictory docs

**Files:**
- Modify: `tools/creative_engine.py:151-190`
- Modify: `tools/youtube_skills/hooks.json`
- Modify: `channel_assets/scientific_dossiers.json`
- Modify: `tests/test_creative_engine.py:192-230`
- Modify: `tests/test_hookscore.py:269-295`
- Modify: `tests/test_fidelity.py`
- Modify: `tests/test_project_contract.py`
- Modify: `tools/orchestrator/workers.py:466-545`
- Modify: `pyproject.toml:12-34`
- Modify: `shorts/README.md:25-32`
- Modify: `long_form/README.md:24-35`
- Modify: `tools/orchestrator/README.md:35-77`
- Modify: `README.md` only if needed to keep corpus wording consistent

**Interfaces:**
- `_percent_stat` returns an empty string for percentages `<=0` or `>=100`.
- Audit results expose an explicit `media_assessed` count and say `no retained media assessed` when zero.
- Pytest uses `xfail_strict = true`; the suite contains zero intentional XFAIL tests after this task.

- [ ] **Step 1: Convert acknowledged debt into failing assertions**

  Remove the current-behavior assertion for 0%, unmark the two spec-gap tests, and assert both 0% and 100% produce no percentage-led title. Make the hook worked-example test ordinary. Add literal assertions that dossier keys equal normalized stored topics, generated simulation-argument narration is within 105–155 words, and empty audit output reports zero media assessed.

- [ ] **Step 2: Verify RED**

  Run: `.venv/bin/python -m pytest -q tests/test_creative_engine.py tests/test_hookscore.py tests/test_fidelity.py tests/test_project_contract.py tests/test_orchestrator.py`

  Expected: failures list degenerate title claims, four weak hook examples, three dossier-key mismatches, the 165-word script, and missing empty-audit wording.

- [ ] **Step 3: Apply minimal content/data fixes**

  Reject degenerate percentages. Rewrite only the four failing hook examples so each states an observable stake while preserving its named formula. Rename the three dossier keys to their normalized topic forms. Shorten only the simulation-argument narration source fields needed to reach 105–155 words without changing numeric claims or inventing evidence.

- [ ] **Step 4: Clarify audit and documentation**

  Audit discovers the same immediate project directories as contract tests, isolates malformed JSON per project, reports scanned/media-assessed/skipped counts, and explicitly labels an empty corpus. Shorts docs state the five-second technical floor and no retained renders; long-form docs require 30 fps; orchestrator docs state ordinary warnings may pass production but block strict release where configured.

- [ ] **Step 5: Enable strict expected-failure policy**

  Set `xfail_strict = true`, remove obsolete XFAIL/current-behavior markers, and keep marker declarations only if still used by passing tests.

- [ ] **Step 6: Verify GREEN and honesty report**

  Run: `.venv/bin/python -m pytest -q tests/test_creative_engine.py tests/test_hookscore.py tests/test_fidelity.py tests/test_project_contract.py tests/test_orchestrator.py`

  Run: `./check.sh`

  Expected: zero XFAILs; no dossier-key, simulation-word-band, or weak-hook findings; documentation/impact gate passes.

- [ ] **Step 7: Record evidence**

  Include before/after hook scores, final simulation word count, normalized keys, audit empty-corpus message, commands, and changed files.

## Final integration gate

- [ ] Generate one whole-change review package from the pre-task baseline snapshot and dispatch an independent architecture/correctness reviewer.
- [ ] Resolve every Critical/Important review finding through the recorded fix loop and re-review.
- [ ] Run `./check.sh` and confirm Ruff, compileall, pytest, and `impact --all` all pass with zero XFAILs and zero dangling references.
- [ ] Run `.venv/bin/python tools/master.py audit`; confirm the report passes and explicitly identifies the number of retained media projects assessed.
- [ ] Run `.venv/bin/python tools/master.py workers`; confirm the canonical worker/verifier registry remains intact.
- [ ] Inspect the generated real-media pytest output and the task ledger; do not infer media validity from unit mocks.

## Self-review

- Spec coverage: Tasks 1–7 map one-to-one to the seven selected audit items; audit item 8 is explicitly excluded.
- Placeholder scan: no implementation step contains TBD/TODO/fill-later language; human-review blanks are deliberate draft data required to fail strict release.
- Type consistency: task interfaces name their producers and consumers; later tasks consume the exact signatures introduced earlier.
- Safety: no task authorizes network, upload, publication, Git initialization, CI, Python migration, or channel-profile work.

