# Short 13 Safe Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct Short 13 against the primary study, rebuild it, release it through an idempotent master workflow, upload it unlisted to the verified Cognitive Core channel, and remove only the local Short 13 and Short 16 project directories after remote verification.

**Architecture:** An immutable evidence bundle outside the disposable project directories binds the approved script to page-level primary-source support. A new `release-existing` master workflow imports the corrected project and existing render without regenerating content, runs every release gate, and calls a receipt-backed uploader that verifies the channel, discloses synthetic media, never adds engagement actions, and refuses ambiguous retries. Upload receipts stay under `channel_assets/upload_receipts/` so cleanup cannot remove them.

**Tech Stack:** Python 3.11, pytest, YouTube Data API v3, ffmpeg/ffprobe, existing FrameForge orchestrator and renderer.

**Spec:** `docs/reports/2026-11-02-sh13-release-proposal.md`

## Global Constraints

- Final narration is the approved eight-scene, 116-word script, with the lemon-juice wording made precise as “with lemon juice on his face.”
- The 12th and 62nd values are percentile ranks for the lowest-scoring quarter, never percentages or a universal individual result.
- The prediction/feedback exercise is labeled as an editorial suggestion; it is not represented as an experimental treatment.
- Use the original 1999 Kruger and Dunning paper as primary evidence; every factual claim has a printed-page locator and support summary.
- Public title is `Dunning-Kruger: Why 12th Felt Like 62nd`; lowercase `#shorts` belongs in the description.
- Reuse existing compatible images and motion clips; rebuild narration, captions, timing, overlays, and the final MP4.
- Upload privacy is `unlisted`. A later public transition is outside this plan until the user answers the visibility question.
- Expected channel ID is `UC6hwVBnsfvfUGxfZi2sFT3A`; mismatch blocks before any insert call.
- `status.containsSyntheticMedia` is `true`; made-for-kids is `false`.
- No automatic creator comment, like, reply, pin, playlist, related-video, or visibility change.
- An ambiguous upload state never triggers a new insert. Tracker failure retries bookkeeping only.
- Never delete a YouTube video. Delete local Short 13 and Short 16 directories only after the Short 13 receipt and an independent remote check both confirm the upload.
- Preserve the evidence bundle, upload receipt, master ledger, and remote video ID outside both deleted project directories.
- Builders do not verify their own work. Each task requires a separate read-only reviewer or verifier.
- This workspace is not a Git repository. Do not initialize Git. Use scoped before/after manifests and unified diffs in the plan workspace instead of commits.

---

### Task 1: Primary evidence and corrected Short 13 package

**Files:**
- Create: `channel_assets/evidence/SH-13-dunning-kruger.json`
- Modify: `shorts/short_13_dunning_kruger/project.json`
- Modify: `shorts/short_13_dunning_kruger/UPLOAD_KIT_SHORT_13.md`

**Interfaces:**
- Produces: evidence bundle schema version 1 with `video_id`, `topic`, `primary_source`, `dossier`, `claims`, `editorial_suggestions`, and `script_sha256`.
- Produces: a project whose ordered `scenes[*].text` hashes to `script_sha256`, and whose `evidence_bundle` points to the repository-relative evidence file.
- Consumed by: Task 2 strict evidence verifier and Task 3 renderer.

- [ ] **Step 1: Trace the blast radius and capture originals**

Run:

```bash
.venv/bin/python tools/master.py impact --path shorts/short_13_dunning_kruger/project.json --json
.venv/bin/python tools/master.py impact --path shorts/short_13_dunning_kruger/UPLOAD_KIT_SHORT_13.md --json
.venv/bin/python tools/master.py impact --path channel_assets/scientific_dossiers.json --json
```

Record outputs and SHA-256 hashes in the plan workspace. Do not edit `scientific_dossiers.json`; the new evidence record is video-specific and survives cleanup.

- [ ] **Step 2: Write the evidence bundle**

Use this shape and fill every claim with a concise paraphrase, printed-page locator, and support summary from the paper:

```json
{
  "schema_version": 1,
  "video_id": "SH-13",
  "topic": "Dunning-Kruger effect",
  "primary_source": {
    "title": "Unskilled and Unaware of It",
    "authors": ["Justin Kruger", "David Dunning"],
    "year": 1999,
    "publication": "Journal of Personality and Social Psychology",
    "url": "https://gwern.net/doc/psychology/1999-kruger.pdf"
  },
  "dossier": {
    "topic": "Dunning-Kruger effect",
    "primary_researchers": "Justin Kruger and David Dunning",
    "year": "1999",
    "publication": "Journal of Personality and Social Psychology",
    "experiment_design": "Four studies of humor, grammar, and logical reasoning self-assessment",
    "quantitative_stat": "Bottom-quartile participants averaged the 12th percentile and estimated the 62nd percentile across the reported studies"
  },
  "claims": [],
  "editorial_suggestions": [],
  "script_sha256": "<sha256 of scene text joined with newline>"
}
```

The Wheeler claim must say the paper recounts the story; the exercise must be in `editorial_suggestions`, not `claims`.

- [ ] **Step 3: Apply the approved narration and visual copy**

Set eight scene texts to:

```text
Before you trust your confidence: McArthur Wheeler robbed two banks with lemon juice on his face. What did he miss?
He reportedly thought cameras could not see his face.
Kruger and Dunning opened their 1999 paper with that story.
In their studies, the lowest-scoring quarter averaged the 12th percentile, but estimated the 62nd.
They tested humor, grammar, and logic. Their explanation: limited skill can also make errors harder to recognize.
High scorers sometimes underestimated their relative standing, partly because they overestimated how well their peers performed.
Training improved self-assessment in their experiment. My practical suggestion: predict your performance, then compare it with feedback.
Feeling certain does not prove you are right. Subscribe for the next blind spot.
```

Set scene 4 card to `12th vs 62nd percentile` / `Bottom quartile: average actual vs estimated rank`; scene 5 overlay to `CHECK YOUR ESTIMATE`; scene 6 note to `Kruger & Dunning (1999), Study 3`; scene 7 overlay to `PREDICT, THEN CHECK`; scene 8 overlay to `CHECK THE EVIDENCE`. Remove identity labels from scene 3 imagery and label it as illustrative researchers or use a neutral research visual. Add `citation_verified: true`, `contains_synthetic_media: true`, and the evidence path.

- [ ] **Step 4: Replace the upload kit**

Use the exact title from Global Constraints. The description must summarize only supported study findings, include the primary source URL, disclose illustrative AI reenactments, label the predict/feedback exercise as the creator's suggestion, and end with lowercase `#shorts`. Remove cure language, resource promises, ranking promises, scripted replies, and automatic-engagement instructions. An optional comment may remain clearly marked manual and unapproved.

- [ ] **Step 5: Run content checks**

Run:

```bash
.venv/bin/python -c 'import hashlib,json,re; from pathlib import Path; p=Path("shorts/short_13_dunning_kruger/project.json"); d=json.loads(p.read_text()); s="\n".join(x["text"] for x in d["scenes"]); e=json.loads(Path(d["evidence_bundle"]).read_text()); assert len(d["scenes"])==8; assert 105<=len(re.findall(r"\b\w+\b",s))<=155; assert hashlib.sha256(s.encode()).hexdigest()==e["script_sha256"]; print(len(re.findall(r"\b\w+\b",s)), e["script_sha256"])'
.venv/bin/python -c 'import json; from tools import youtube_skills; d=json.load(open("shorts/short_13_dunning_kruger/project.json")); print(youtube_skills.score_hook(d["scenes"][0]["text"])); print(youtube_skills.check_packaging("Dunning-Kruger: Why 12th Felt Like 62nd"))'
```

Expected: 8 scenes, 105–155 words, matching hash, hook at least 70, title issues empty.

---

### Task 2: Strict existing-artifact release and idempotent uploader

**Files:**
- Modify: `tools/orchestrator/cli.py`
- Modify: `tools/orchestrator/workflows.py`
- Modify: `tools/orchestrator/workers.py`
- Modify: `tools/orchestrator/verifiers.py`
- Modify: `tools/orchestrator/state.py`
- Modify: `tools/upload_api.py`
- Modify: `tools/orchestrator/README.md`
- Modify: `channel_assets/YOUTUBE_API_GUIDE.md`
- Create: `tests/test_release_existing.py`
- Create: `tests/test_upload_safety.py`

**Interfaces:**
- Produces: `workflows.release_existing(project_json: str, evidence: str, publish: bool, privacy: str) -> Workflow`.
- Produces CLI: `master.py release-existing --project PATH --evidence PATH [--privacy unlisted|public] [--publish --yes]`.
- Extends `ReleaseWorker` to import a project, evidence bundle, upload kit, and canonical MP4 without regeneration.
- Extends `upload_via_api(project_dir, public=False, *, expected_channel_id, contains_synthetic_media, receipt_path) -> str`.
- Produces atomic receipt JSON with `operation_key`, hashes, channel, privacy, state, video ID, and verification details.

- [ ] **Step 1: Trace every shared interface**

Run `impact --path --json` for every modified module and `impact --name release-existing --json`; save outputs in the plan workspace. Search all callers of `upload_via_api` before changing its signature.

- [ ] **Step 2: Write failing release-existing tests**

Tests must prove that validation-only mode creates a `release` task with strict evidence, every gate, and no publish task; publish mode adds one approval-required task; the release worker imports rather than regenerates; mismatched video ID, script hash, missing claim locators, or editorial advice presented as research fails critically.

Run:

```bash
.venv/bin/python -m pytest tests/test_release_existing.py -q
```

Expected before implementation: failures because the workflow/CLI and strict verifier do not exist.

- [ ] **Step 3: Implement the release-existing workflow**

The release task carries `project_json`, `evidence`, `video_id`, and `strict_evidence: true`, returns artifacts `project_json`, `upload_kit`, `output_mp4`, and `evidence`, and exposes `dossier`, `claims`, and `scenes` to existing verifiers. Its verifier list is `research`, `script`, `project`, `render`, `packaging`, `precompose`, `consistency`. `RunContext.project_json()` must resolve an explicit release artifact. Validation-only mode performs no network write.

- [ ] **Step 4: Write failing uploader-safety tests**

With a fake YouTube service, test:

```python
def test_wrong_channel_blocks_before_insert(): ...
def test_body_sets_synthetic_disclosure_and_unlisted(): ...
def test_success_never_comments_or_likes(): ...
def test_ambiguous_receipt_blocks_second_insert(): ...
def test_complete_matching_receipt_reuses_verified_video(): ...
def test_tracker_failure_cannot_trigger_second_upload(): ...
```

Run:

```bash
.venv/bin/python -m pytest tests/test_upload_safety.py -q
```

Expected before implementation: failures for missing receipt/channel/disclosure behavior.

- [ ] **Step 5: Implement channel preflight and atomic receipts**

Before `videos.insert`, call `channels.list(mine=True)` and require the exact expected ID. Hash the media bytes and normalized upload metadata, then derive the operation key from video ID plus both hashes. Atomically write the receipt before the insert. A matching completed receipt verifies and returns its remote ID without insertion. `uploading` or `ambiguous` state stops with a reconciliation error. Persist the returned video ID and remote verification before tracker mutation. A tracker exception becomes a receipt note and warning, not upload failure.

- [ ] **Step 6: Remove automatic engagement and set disclosure**

The uploader request body includes:

```python
"status": {
    "privacyStatus": "unlisted",
    "selfDeclaredMadeForKids": False,
    "containsSyntheticMedia": True,
}
```

Delete automatic `commentThreads.insert` and `videos.rate` calls. Do not replace them with an option in this task.

- [ ] **Step 7: Run focused and repository tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_release_existing.py tests/test_upload_safety.py tests/test_tracker_schema.py -q
./check.sh
```

Expected: focused tests pass; full gate exits 0 with no new xfails and zero dangling references.

---

### Task 3: Rebuild Short 13 and verify the release artifact

**Files:**
- Replace: `shorts/short_13_dunning_kruger/output/short_13_dunning_kruger.mp4`
- Replace: `shorts/short_13_dunning_kruger/output/short_13_dunning_kruger.srt`
- Update generated cache entries under: `shorts/short_13_dunning_kruger/cache/`
- Create: `docs/receipts/SH-13-render-2026-11-02.json`

**Interfaces:**
- Consumes: corrected Task 1 project and Task 2 validation-only workflow.
- Produces: final media SHA-256 bound into the render receipt and later upload receipt.

- [ ] **Step 1: Capture the old artifact**

Record old MP4/SRT hashes, sizes, ffprobe metadata, and a contact sheet in the plan workspace. Preserve a temporary backup until the corrected upload is independently verified.

- [ ] **Step 2: Rebuild without forcing motion**

Run:

```bash
.venv/bin/python tools/pipeline.py --build shorts/short_13_dunning_kruger/project.json
```

Do not pass `--force-motion`. Text changes create new narration cache keys; the renderer regenerates captions/timing and final composition while retaining compatible image/motion assets.

- [ ] **Step 3: Run the validation-only master release**

Run:

```bash
.venv/bin/python tools/master.py release-existing --project shorts/short_13_dunning_kruger/project.json --evidence channel_assets/evidence/SH-13-dunning-kruger.json --privacy unlisted
```

Expected: every release task and check passes, no publish task exists, and no YouTube request is made.

- [ ] **Step 4: Independent media inspection**

The verifier runs ffprobe, compares narration text with the generated SRT, samples the opening and every scene boundary, and inspects a contact sheet. All eight scenes must have correct baked-in words, notes, cards, overlays, captions, and illustrative imagery. Confirm 1080×1920, 30 fps, H.264 video, AAC 48 kHz, at least 5 seconds, audible unclipped narration, no stale “%”, “INCOMPETENCE”, “FALSE CONSENSUS”, “FIVE-SECOND”, or “IN JUICE” copy.

- [ ] **Step 5: Write the render receipt and run the repository gate**

Record the project/evidence/media/SRT hashes, stream properties, master run ID, inspection artifacts, and verifier identity. Run `./check.sh`; expected exit 0.

---

### Task 4: Upload unlisted and independently verify remote state

**Files:**
- Create: `channel_assets / upload_receipts / <video-id>.json` (video ID `SH-13`)
- Modify: `CONTENT_TRACKER.md` through the schema-aware tracker writer
- Update: `docs/reports/2026-11-02-master-ledger.md`

**Interfaces:**
- Consumes: Task 3 media hash and release pass.
- Produces: immutable remote video ID and a verified receipt outside the project directory.

- [ ] **Step 1: Read-only live preflight**

Confirm OAuth resolves to channel `UC6hwVBnsfvfUGxfZi2sFT3A`, search the uploads playlist and receipt store for an existing SH-13/media operation, and confirm the target title, hashes, `unlisted` privacy, made-for-kids false, and synthetic disclosure true. Any mismatch blocks before insertion.

- [ ] **Step 2: Run the approved publisher command**

Run exactly:

```bash
.venv/bin/python tools/master.py release-existing --project shorts/short_13_dunning_kruger/project.json --evidence channel_assets/evidence/SH-13-dunning-kruger.json --privacy unlisted --publish --yes
```

The uploader must issue at most one `videos.insert` and no engagement calls.

- [ ] **Step 3: Independent remote verification**

Using the returned ID, confirm owning channel, exact title and description, unlisted privacy, processing success, made-for-kids false, synthetic disclosure when returned, duration/resolution, and playable audio/video. If processing is incomplete, wait with bounded polling; do not re-upload. An omitted disclosure response is recorded as unknown and checked in Studio later, never treated as false.

- [ ] **Step 4: Seal receipt and ledger**

Record the remote ID, URL, hashes, timestamps, channel, privacy, API verification, and playback evidence. Update the tracker to the live link while accurately labeling the video unlisted. Run `./check.sh` after bookkeeping changes.

---

### Task 5: Delete only the two authorized local project directories

**Files:**
- Delete: `shorts/short_13_dunning_kruger/`
- Delete: `shorts/short_16_simulation_argument/`
- Modify active references in: `CONTENT_TRACKER.md`, `GEMINI.md`, `channel_assets/YOUTUBE_API_GUIDE.md`, tests and current docs as reported by impact/`rg`
- Preserve historical receipts and ledgers with explicit “deleted locally after verified upload” notes.

**Interfaces:**
- Consumes: Task 4 receipt state `verified` and remote playback evidence.
- Produces: no active reference that requires either local directory to exist.

- [ ] **Step 1: Resolve exact targets and blast radius**

Require both exact real paths under `/Users/friday/Desktop/FrameForge/shorts`, confirm neither is a symlink, record logical/allocated sizes, and run impact plus `rg` for both slugs, project paths, output filenames, and upload-kit names. Abort if the Task 4 receipt is absent, unverified, or does not match the media hash.

- [ ] **Step 2: Update active references and self-contained tests**

Remove commands that require deleted files, change tracker local-project cells to `Deleted locally 2026-11-02 after verified upload`, and move any regression fixture that needs project data into `tests/fixtures/`. Historical reports retain paths as historical evidence with a deletion note.

- [ ] **Step 3: Delete the two exact directories**

Use only the two validated absolute paths. Do not use a glob or environment variable. This is permanent local deletion authorized by the user; no YouTube API deletion is allowed.

- [ ] **Step 4: Independent cleanup verification**

Confirm both directories are absent; both YouTube video IDs remain remotely present; evidence and upload/render receipts remain; measure reclaimed storage; run `impact --all` and `./check.sh`.

Expected: repository gate exit 0, zero dangling references, and approximately the previously measured 264 MB of project-tree storage removed, subject to filesystem allocation differences.

