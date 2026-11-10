# FrameForge Reliability Hardening Design

## Intent

Implement the first seven improvements from the 2026-11-02 repository audit while preserving FrameForge's master/worker/verifier release model. The goal is for a green gate to prove that a real deterministic media artifact is decodable, production tasks cannot hang indefinitely, render reuse is traceable, release evidence has a supported preparation path, legacy production entry points share the canonical master, concurrent state updates are durable, and the remaining acknowledged content/documentation defects are cleared.

The user explicitly selected improvements 1–7 and excluded improvement 8. This design therefore does not initialize Git, add CI, migrate Python, or extract Cognitive Core into a channel-neutral profile.

## Goals

1. Exercise actual local FFmpeg/FFprobe media generation and decoding in the repository gate without network, GPU, or model downloads.
2. Enforce `TaskSpec.timeout_s` and bound the identified unbounded external processes, terminating child process groups on timeout.
3. Refuse accidental project replacement and reuse scene renders only when a content fingerprint proves their inputs and output are unchanged.
4. Validate project and release-evidence structures at runtime and add a `prepare-release` command that creates an explicitly unverified review draft.
5. Route legacy production commands through the canonical master and make `tools.pipeline`, `tools.build_video`, and `tools.visual_engine` safe to import without replacing the host process.
6. Serialize orchestration-run execution and tracker updates; persist state and tracker changes with atomic, durable replacement.
7. Remove the two expected failures and the repository-honesty drift identified by `./check.sh`, and correct contradictory operator documentation.

## Non-goals and anti-goals

- Do not upload, publish, deploy, contact YouTube, or perform any network operation.
- Do not initialize a Git repository, add CI configuration, migrate Python, or implement the channel-profile proposal (audit item 8).
- Do not weaken strict release verification or synthesize verified scientific evidence.
- Do not retain generated MP4/WAV artifacts in production project directories; media-smoke artifacts live in pytest temporary directories.
- Do not replace the master orchestrator or package the repository as an installable Python distribution.
- Do not make broad visual/rendering changes unrelated to cache identity or process supervision.

## Selected approach

### Approach A — Incremental hardening of the existing architecture (selected)

Add small focused modules for process supervision, schema validation, durable writes, and render manifests, then integrate them at existing boundaries. Preserve current CLIs through adapters and add focused regression tests plus one actual CPU-only media smoke test. This minimizes migration risk and keeps the release safety model intact.

### Approach B — Replace the pipeline with a new job system

A queue-backed worker system could supply cancellation, locks, caching, and schemas in one abstraction, but it would be a rewrite, would invalidate extensive release-safety tests, and would exceed the selected scope.

### Approach C — Patch each call site independently

Adding isolated timeouts, hashes, and temporary-file writes would be faster initially, but would duplicate policy across already-large modules and make later failures inconsistent. It is rejected in favor of narrow shared primitives.

## Design

### 1. Real media acceptance

`pipeline.verify_rendered_mp4` will require both valid stream metadata and a successful tail-frame decode. It will also reject material audio/video duration divergence. A pytest media-smoke test will generate a small H.264/AAC MP4 from FFmpeg lavfi inputs in `tmp_path`, validate it through the real verifier, decode it through FFmpeg, and prove that a truncated/corrupt artifact is rejected. The test is offline, CPU-only, and runs in the normal `./check.sh` suite when FFmpeg and FFprobe are available; their absence is a hard environment failure because the production gate already requires them.

### 2. Supervised execution and subprocess policy

The master will execute workers in an isolated POSIX child process, receive a serializable `WorkerResult`, and enforce `timeout_s`. The child establishes its own process group. On timeout, the parent terminates the group, escalates to kill after a short grace period, records a non-retryable timeout result, and persists the failed ledger state. Focused tests use a deliberately hanging fake worker and a spawned grandchild to prove bounded completion and cleanup.

Identified standalone probes and Blender/branding calls will use explicit deadlines and diagnostic stderr tails. Existing encoder-specific cleanup remains intact.

### 3. Collision-safe projects and content-addressed render reuse

Project generation refuses to replace an existing `project.json` unless the caller explicitly requests overwrite. The canonical project worker never silently overwrites a reviewed project.

Each scene render has a manifest record under the project's cache directory. The fingerprint binds scene index, prompt, source-image content hash, narration-derived duration, selected preset, output dimensions, renderer contract version, and relevant render parameters. Existing video reuse requires a matching fingerprint, matching output hash, and a passing motion check. Missing or mismatched records rerender only the affected scene. The authored project remains compatible; manifest data is operational cache metadata.

### 4. Runtime schemas and release preparation

A lightweight in-repository validator will report all project errors together without introducing a new dependency. It covers version, identity, format, required scene fields, scene count, path safety, and audio/render option types. It runs before expensive build side effects and from the project verifier.

Evidence validation covers schema version, video identity, primary source, claims, editorial suggestions, script hash, synthetic-media declaration, and project binding. `master.py prepare-release --project PATH [--output PATH]` creates a versioned `draft` evidence bundle populated only with facts already present in the project/dossier. Fields requiring human page-level review remain empty and the draft is deliberately rejected by strict release until reviewed. The command never marks citations verified and never publishes.

### 5. One canonical coordinator and pure imports

Runtime re-exec moves to explicit CLI bootstrap paths. Importing `tools.pipeline`, `tools.build_video`, or `tools.visual_engine` performs no `os.execv`. Shared word-band policy moves to a lightweight module so verifiers do not import the rendering pipeline just to read constants.

Legacy `pipeline.py --agents/--auto` and `agents.py --run` production entry points become compatibility adapters over the canonical master workflow. They preserve safe exit status and human summaries but do not maintain a second production DAG. Upload remains available only through strict `release-existing --publish --yes` and is not exercised in this work.

### 6. Durable concurrent state

Each run has an exclusive execution lock covering run/resume dispatch. A concurrent resume fails clearly before executing a worker. State saves and tracker updates use unique temporary files in the destination directory, flush and `fsync` file contents, `os.replace`, then `fsync` the directory. Tracker read/modify/write occurs under one shared lock so two video updates cannot lose each other.

### 7. Honesty debt and documentation

- Degenerate 0% and 100% values cannot produce percentage-led title claims.
- All shipped hook worked examples meet their advertised scoring band; the related XFAIL becomes a passing test.
- The simulation-argument generated Short falls inside 105–155 spoken words.
- Dossier keys equal normalized stored topics.
- XFAILs are eliminated; pytest strict-xfail mode is enabled.
- Shorts and long-form documentation agrees with the actual minimum-duration and 30-fps release gates and with the empty retained-project corpus.
- The orchestrator guide distinguishes ordinary production warnings from strict-release blockers.

## Safety and compatibility

- Existing strict release fingerprints, approval requirements, receipt locking, synthetic-media declaration, and channel identity checks remain unchanged.
- No test invokes network services, model generation, upload, or publication.
- Compatibility adapters remain until a future separately approved removal.
- New schemas accept explicitly identified legacy inputs only where doing so cannot weaken strict release; new generated artifacts carry version fields.

## Acceptance

The change is complete only when:

1. Each task has a test-first red/green record and an independent reviewer approval.
2. The real media smoke test creates and validates an actual decodable H.264/AAC MP4 and rejects corruption.
3. A hanging worker is terminated within its declared deadline and its durable run state records failure without executing dependents.
4. Changing one scene input invalidates only that scene's manifest; unchanged inputs reuse the verified output.
5. `prepare-release` creates a versioned draft that strict release rejects until human-required fields are supplied.
6. Legacy production entry points reach the canonical master; importing render modules cannot re-exec the interpreter.
7. Concurrent run/tracker tests demonstrate serialization and durable atomic replacement.
8. `./check.sh` passes with zero XFAILs and a clean honesty report for the items in scope.
9. `.venv/bin/python tools/master.py audit` passes and explicitly reports that no retained media projects were assessed when the corpus is empty.

