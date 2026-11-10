# UPGRADE_STATE.md — FrameForge Production Architecture Upgrade

**Status:** PHASE 1 IN PROGRESS (Extra Instruction 1 Fixed; Phase 3 Thumbnail Policy Locked; Executing Rule B & Rule A cleanup).  
**Last Updated:** 2026-11-11 02:56:00 UTC  
**Master Protocol:** AGENTS.md + GEMINI.md  
**Environment:** Mac Darwin 27.2.0 ARM64 (Local host) & Linux Debian Bookworm 3.11.18 ARM64 (Docker verification container)

---

## 1. Goal & Acceptance Criteria

### Restated Goal
Refactor FrameForge into an uncompromising, production-grade video engine strictly governed by:
- **Global Rule A (No Hardcoded Content):** Zero script/narration strings, HUD copy, titles, BGM/SFX paths, durations, voice names, palettes, or default topics in code. Everything derives from `project.json`, scene plans, or `configs/`. Demos exist only under `tests/fixtures/`.
- **Global Rule B (No Fallbacks / Silent Degenerations):** Zero `except: pass`, zero fallback fonts, silent audio omission, auto-fallbacks, or default topic fallbacks. Failures must raise typed errors specifying stage, artifact, and cause.
- **Global Rule C (Per-Video Uniqueness):** Independent SFX sets, audio designs, and images tailored to each script. Automated uniqueness gate enforcing distance thresholds across SFX timing/assets, image perceptual hashes, audio fingerprints, and opening hooks.
- **Unified 0-to-1 Explicit Chain (14 Stages):**  
  `1. topic -> 2. research/dossier -> 3. script -> 4. scene plan -> 5. narration (Kokoro) -> 6. word timings -> 7. SFX plan -> 8. audio design + mix -> 9. per-scene images -> 10. per-variant render -> 11. frame/audio QA -> 12. uniqueness gate -> 13. policy gate -> 14. upload kit.`

### Final Acceptance Test
Execute `master.py produce --channel <channel> --variant <variant> --topic <topic>` on two distinct topics across each style variant. Each run must print stage-by-stage PASS/FAIL status through all 14 stages, generate independent verifiable artifacts, pass the uniqueness comparison between runs, and `./check.sh` must remain 100% green.

---

## 2. Targeted Verification of Seed Claims (Step 0 Audit)

### A. Verified Claims Marked [DONE]
All 5 items claimed as DONE were tested using targeted commands and confirmed passing:

1. **Variant registry in `tools/universal_engine.py`**
   - **Command:** `.venv/bin/python -c "import tools.universal_engine as ue; print(list(ue.ENGINE_REGISTRY.keys())); print(ue.SUPPORTED_VARIANTS)"`
   - **Output:** `['cinematic_35mm', 'photobook', 'storybook_picturebook', 'stickman_skeleton', 'riddle', 'hybrid_mixed_media', 'cutout_cartoon']` | `frozenset({'riddle', 'stickman_skeleton', 'hybrid_mixed_media', 'cutout_cartoon', 'photobook', 'storybook_picturebook', 'cinematic_35mm'})`
   - **Test Suite:** `.venv/bin/python -m pytest tests/test_universal_engine.py -q` -> `15 passed in 9.27s`
   - **Verdict:** **VERIFIED DONE**

2. **`--variant` / `--channel` in orchestrator CLI (`master.py produce`)**
   - **Verification:** Inspected `tools/master.py produce` CLI argument parser definitions.
   - **Output:** Both options present (`--variant VARIANT` canonical style variant; `--channel CHANNEL` target channel profile identifier).
   - **Test Suite:** `.venv/bin/python -m pytest tests/test_orchestrator*.py -q` -> `116 passed in 3.72s`
   - **Verdict:** **VERIFIED DONE**

3. **No `edge_tts` imports in codebase**
   - **Command:** `git grep -i "import edge_tts" && git grep -n "edge_tts" tools/`
   - **Output:** `NONE` (Zero occurrences in python imports or `tools/`).
   - **Verdict:** **VERIFIED DONE**

4. **`colab_server` endpoints and imports**
   - **Command:** `.venv/bin/python -c "import tools.cloud_worker.colab_server as cs; print([x for x in dir(cs) if not x.startswith('_')])"`
   - **Output:** Clean import exposing FastAPI app and endpoints: `get_health`, `render_hybrid_api`, `render_photobook_api`, `render_stickman_api`, `sync_model`.
   - **Test Suite:** `.venv/bin/python -m pytest tests/test_cloud_worker.py -q` -> `3 passed in 0.82s`
   - **Verdict:** **VERIFIED DONE**

5. **Analytics API v2 in `analyze_channel_monetization`**
   - **Command:** `git grep -n "v2" tools/analyze_channel_monetization.py`
   - **Output:** Line 64: `yta = build("youtubeAnalytics", "v2", credentials=creds)`. Line 6 doc references `yt-analytics.readonly` v2 scope. Read-only dry run executes successfully without raising.
   - **Verdict:** **VERIFIED DONE**

---

### B. Verified Claims Marked [PARTIAL]
1. **D1 — Hardcoded DB Cooper / Wall Street text:**
   - `tools/multimedia_director.py:1` contains hardcoded Wall Street 1920 demo text.
   - `tools/picture_book_engine.py:1268`: `elif project_slug == "long_01_db_cooper_1971": elements = DB_COOPER_PICTURE_BOOK`. Line 1561: `default="long_01_db_cooper_1971"`.
   - `tools/visual_director.py:53, 58, 67` contain hardcoded Wall Street 1920 prompt anchors.
   - `tools/universal_engine.py:375, 380, 385, 390, 395` import from `demos.archetype_demos`.
2. **D5 — Stale Edge-TTS text:**
   - `GEMINI.md:106`: `Primary voice: en-US-AndrewNeural (or local Kokoro-82M neural blend am_adam + bm_george fallback)`.
   - `tools/guard.py:66`: `"default_voice": "en-US-AndrewNeural (Edge-TTS consumer endpoint)"` in baseline dictionary comparison.
3. **D6 — Hardcoded OS paths & VideoToolbox usage:**
   - `/opt/homebrew/bin` hardcoded in `tools/build_video.py:30-31`, `tools/pipeline.py:36-37`, `tools/visual_engine.py:38-39` (and lines 211, 231, 271, 317, 432, 895, 964).
   - `tools/pipeline.py:1199`: Hardcoded OS path check `not (arg.startswith("/Users") or arg.startswith("/private") or Path(arg).exists())`.
   - `videotoolbox` explicitly referenced in 37 places across 14 files (`branding_engine`, `build_video`, `cutout_director`, `forensic_casebook_engine`, `humanizer_director`, `hybrid_engine`, `longform_orchestrator`, `photobook_engine`, `picture_book_engine`, `riddle_director`, `stickman_engine`, `storybook_engine`, `universal_engine`, `visual_engine`).
4. **D13 — Channel configs:**
   - Only `configs/channels/cognitive_core.yaml` exists.
   - `tools/orchestrator/cli.py:317` sets `produce.add_argument("--channel", default="cognitive_core")`.
5. **D14 — Policy gate:**
   - `tools/policy.py` contains only `WORD_BANDS = {"short": (105, 155), "long": (1100, 1500)}` (3 lines). No policy verification gate checking AI disclosures, asset licenses, likeness rights, or study grounding.
6. **D15 — Thumbnail contradiction:**
   - `tools/branding_engine.py:636` implements `def render_longform_thumbnail()`.
   - `tests/test_impact.py:322-334` asserts no thumbnail verifiers or worker kinds exist, and repo docs state thumbnails were deleted 2026-11-01. Requires architectural decision before modifying.

---

### C. Verified Claims Marked [NOT DONE]
1. **Rule A (Hardcoded video content):**
   - `tools/universal_engine.py:1191` `_default_scenes_for_topic()` hardcodes 8 fixed beats, `or "Cognitive Science"`, and fixed duration `4.2s`.
   - Fixed BGM file paths in 4 engines (`tools/universal_engine.py`, `tools/branding_engine.py`, `tools/hybrid_engine.py`, `tools/photobook_engine.py`).
   - Fixed SFX literals in `audio_bank.py`, `sound_architect.py`, `humanizer_director.py`.
2. **Rule B (Fallbacks & Silent Failure):**
   - Measured AST count: **27 `except: pass`** handlers across `tools/`.
   - Measured count: **39 `fallback`** occurrences in `tools/` (including default font fallback in `universal_engine.py:65-71`, `cmd_fallback` in `universal_engine.py:1115`, Blender auto-fallback in `visual_engine.py:1919`, and SFX fallback list in `humanizer_director.py:103`).
3. **Rule C (Uniqueness Gate):**
   - Not implemented. No perceptual-hash check, audio fingerprint check, SFX pattern comparison, or opening 3-second duplication validator.
4. **D16 (Deployment):**
   - Dockerfile(s), queue workers, and cloud production infrastructure not yet built.

---

### D. Verified Claims Marked [NOT VERIFIED]
- **D8:** Render stream spec across all variants.
- **D9:** Upload-kit and `verify_packaging` consistency across formats.
- **D10:** Riddle and stickman auto-scaling under varying resolutions.
- **D11:** Frame QA (caption-face collisions, UI occlusion, safe-zone conformance).
- **End-to-End Render per Variant:** Full render validation per variant has not been executed in this session.

---

## 3. Baseline Test Execution Results

### 1. Mac Baseline (Darwin 27.2.0 ARM64, `.venv` Python 3.11.14)
Execution of `./check.sh all`:
- **ruff:** `PASS` (All checks passed)
- **compileall:** `PASS`
- **pytest:** `PASS` (`973 passed, 1 skipped, 1 warning in 55.72s`)
- **impact (`tools/master.py impact --all`):** `PASS` (`0 dangling reference(s)`)
- **guard (`tools/guard.py`):** `PASS` (`OVERALL GUARD VERDICT: PASSED`)
- **Overall Mac check.sh:** **PASS**

### 2. Linux Baseline (Debian Bookworm ARM64 Docker Container, Python 3.11.18)
Execution inside clean container with `PYTHONPYCACHEPREFIX` and `RUFF_CACHE_DIR`:
- **ruff:** `PASS` (`All checks passed!`)
- **compileall:** `PASS` (`tools` and `tests` compiled cleanly)
- **impact:** `PASS` (`0 dangling reference(s)`)
- **guard:** `PASS` (`OVERALL GUARD VERDICT: PASSED`)
- **pytest:** `963 passed, 1 skipped, 1 warning, 8 failed, 2 errors in 98.03s`

#### Classification of Linux Failing Tests:
1. **Environment Deficiencies (Missing system binary or optional heavy package):**
   - `tests/test_media_acceptance.py::test_real_h264_aac_render_is_decodable_and_synchronized` (ERROR): `FileNotFoundError: 'ffmpeg'` (System binary missing in slim container).
   - `tests/test_media_acceptance.py::test_truncated_media_cannot_pass_on_readable_headers` (ERROR): `FileNotFoundError: 'ffmpeg'`.
   - `tests/test_branding.py::test_a_freshly_rerendered_film_brands_even_though_the_marker_is_stale` (FAILED): `FileNotFoundError: 'ffmpeg'`.
   - `tests/test_media_acceptance.py::test_short_audio_cannot_pass_with_full_length_video` (FAILED): `FileNotFoundError: 'ffmpeg'`.
   - `tests/test_universal_engine.py::test_all_seven_engines_validate_and_render_distinct_topics[cutout_cartoon]` (FAILED): `FileNotFoundError: 'ffmpeg'`.
   - `tests/test_universal_engine.py::test_all_seven_engines_validate_and_render_distinct_topics[storybook_picturebook]` (FAILED): `FileNotFoundError: 'ffmpeg'`.
   - `tests/test_universal_engine.py::test_build_project_reuses_and_invalidates_render_manifest` (FAILED): `FileNotFoundError: 'ffmpeg'`.
   - `tests/test_pipeline_validation.py::test_synthesize_kokoro_uses_exact_voice_styles_and_only_blends_explicit_kokoro` (FAILED): `ModuleNotFoundError: No module named 'kokoro_onnx'` (Optional neural TTS package not installed).
   - *Note on `tests/test_guard.py`:* Succeeded in container because `tools/kokoro_models/` weights were mounted from host. If weights are missing, it fails closed as expected.

2. **Real Codebase Bugs (Cross-Platform / Path Normalization Defect) [RESOLVED]:**
   - `tests/test_legacy_upload_routes.py::test_pipeline_upload_forwards_release_inputs`
   - `tests/test_legacy_upload_routes.py::test_pipeline_rejects_upload_mixed_with_production`
   - `tests/test_legacy_upload_routes.py::test_pipeline_cli_preserves_nonexistent_absolute_linux_paths`  
     **Diagnosis & Resolution:** Replaced heuristic slash normalization at `tools/pipeline.py:1199` with exact validation against declared `ap._actions` `--flags`. Added regression test `test_pipeline_cli_preserves_nonexistent_absolute_linux_paths` asserting nonexistent absolute Linux paths (`/tmp/...`, `/var/...`) are strictly preserved. Verified on both Darwin and Linux Debian Bookworm container (`9 passed in 0.17s`).

---

## 4. User Decisions & Architectural Alignment

### Phase 3 Thumbnail Policy (Decided by User 2026-11-11):
- **Shorts:** Strictly zero thumbnails. Feed previews are selected from video frames by YouTube.
- **Long-Form (16:9):** Custom thumbnails are explicitly permitted and supported via `render_longform_thumbnail()`. Must pass through policy gate (no misleading imagery, zero real-person likeness).
- **Documentation & Impact Alignment:** Update `tests/test_impact.py`, `AGENTS.md`, `GEMINI.md`, and `VIDEO_GUIDE_SHORTS_AND_LONG.md` to forbid Shorts thumbnail pipelines while allowing long-form thumbnails. Run `master.py impact --all` after updating.

---

## 5. Work Execution Log

### Task 0: Audit & Baseline Verification [COMPLETED]
- Seeded `UPGRADE_STATE.md`.
- Verified 5 claims marked DONE via targeted CLI/test runs: variant registry (7 variants), `--variant`/`--channel` CLI flags (116 orchestrator tests passed), zero `edge_tts` imports, `colab_server` endpoints (3 tests passed), and Analytics API v2 in `analyze_channel_monetization`.
- Committed as `f200d64` and pushed to remote `origin/main` (`2ca982d`).

### Extra Instruction 1: Normalize only declared CLI flags & preserve absolute Linux paths [COMPLETED]
- Fixed flag heuristic in `tools/pipeline.py` which was rewriting nonexistent Linux paths like `/tmp/evidence.json` to `--tmp/evidence.json`. Replaced with strict membership check against declared `--flags`.
- Added regression test `test_pipeline_cli_preserves_nonexistent_absolute_linux_paths` in `tests/test_legacy_upload_routes.py`.
- Verified `./check.sh all` on Mac (974 tests passed) and Linux Docker container (9/9 legacy upload tests passed).
- Committed locally as `93b6c79`.

### Task 1.0: Universal Engine Decoupling, Typed Errors, and Demo Migration [COMPLETED]
- Created `tools/errors.py` with typed exceptions: `FrameForgeError`, `StageError`, `MissingInputError`, `RenderingError`, `AudioDesignError`, `PolicyGateError`, `UniquenessGateError`.
- Moved showcase demo scripts from `demos/` to `tests/fixtures/archetype_demos.py` and deleted the `demos/` directory so demos are never imported by production code.
- Removed hardcoded `_default_scenes_for_topic` in `tools/universal_engine.py` and replaced with `plan_scenes_from_script(script, topic=topic, title=title, variant=variant)` which raises `MissingInputError` if `script` is missing or empty.
- Removed legacy demo CLI flags (`--all-30s`, `--demo`, `--photobook-30s`, etc.) from `tools/universal_engine.py`.
- Updated `tools/orchestrator/impact.py` to index both `tools/` and `tests/` into `index.modules` so test fixture imports resolve cleanly.
- Verified: `./check.sh all` passed with 0 ruff errors, 974 passing tests, 0 dangling references, and all guard gates passing.

---

## 5. Master Task DAG & Implementation Order

```
[Phase 1: Rule B & Rule A Elimination]
  ├── Task 1.1: Eliminate all 27 `except: pass` and silent fallbacks; implement typed exceptions (StageError)
  ├── Task 1.2: Remove font/Blender/SFX/encoder fallbacks; fail fast on missing dependencies
  ├── Task 1.3: Eliminate hardcoded demo scenes (_default_scenes_for_topic) and replace with dynamic script scene planner
  └── Task 1.4: Add AST lint checks to prevent regression of hardcoded values and silent fallbacks

[Phase 2: Variant Isolation & Clean Blueprint Generation]
  ├── Task 2.1: Enforce project.json contract across all 7 variants
  ├── Task 2.2: Remove `demos/` imports from production code; relocate demo assets to `tests/fixtures/`
  └── Task 2.3: Remove DB Cooper and Wall Street hardcoded defaults from picture_book, forensic, and humanizer engines

[Phase 3: Thumbnail Contradiction Decision]
  └── Task 3.1: Present long-form 16:9 thumbnail vs. Shorts feed-frame contradiction to user; implement agreed design

[Phase 4: Environment & CLI Hardening]
  ├── Task 4.1: Eliminate stale Edge-TTS references in GEMINI.md and tools/guard.py
  ├── Task 4.2: Replace hardcoded `/opt/homebrew` and `/Users` paths with environment-safe resolution
  ├── Task 4.3: Make hardware encoder selection explicit and fail closed if unavailable
  └── Task 4.4: Remove `--channel` default ("cognitive_core"); make `--channel` required

[Phase 5: Channel Governance & Policy Gate]
  ├── Task 5.1: Support dynamic channel configs in `configs/channels/`
  └── Task 5.2: Build comprehensive `policy_gate` (licensing, AI disclosure, study grounding, likeness checks)

[Phase 6: Audio/Visual QA & Rule C Uniqueness Gate]
  ├── Task 6.1: Frame & audio QA gate (-14 LUFS, caption safe-zone 0.44–0.76, face avoidance, pacing)
  └── Task 6.2: Rule C uniqueness gate (SFX overlap, image pHash distance, audio fingerprint, 3s opening)

[Phase 7: Cloud / Container Architecture]
  ├── Task 7.1: Dockerfile with system ffmpeg/ffprobe and complete dependencies
  └── Task 7.2: Execution queue, secrets handling, receipt durability, and human-in-the-loop publish gate
```

---

## 5. Handoff

- **Done:** Step 0 complete. State seeded, all claims verified, baseline tests executed on Mac and Linux with exact failures categorized.
- **In Progress:** Awaiting user review of `UPGRADE_STATE.md` and explicit "proceed" confirmation.
- **Exact Next Command:** Await user input. Upon "proceed", begin **Task 1.1: Rule B & Rule A cleanup**.
