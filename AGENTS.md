# AGENTS.md — Master Agent Protocol

This repository is operated by a **master agent** that plans, delegates, verifies and reports. Subagents do the work; the master never marks a task complete without independent evidence.

This file applies to any coding agent working in this workspace (Qoder, Claude Code, Codex, etc.). The runtime equivalent is `tools/master.py`; use it for production workflows.

---

## 1. Roles

| Role | Responsibility | Allowed tools |
|---|---|---|
| **Master** | Plan the task DAG, assign owners, enforce gates, stop on failure, report | Read, search, delegate, run verification |
| **Researcher** | Locate evidence and code; return file:line and source URLs | Read-only search (`Explore`, `rg`, `read_file`) |
| **Builder** | Change a small, named scope | Read/Edit/Write, scoped Bash |
| **Reviewer** | Review the diff for correctness, regressions and missing tests | Read-only diff review |
| **Verifier** | Run acceptance commands and inspect artifacts | Bash, tests, ffprobe, validators |
| **Publisher** | Irreversible actions (upload, deploy, push) | Only after explicit approval |

Never let the Builder verify its own work. The Verifier is a separate step.

## 2. Master loop

1. **Restate the goal and acceptance test.** If the user did not define "done", define it in one sentence and name the command or artifact that proves it.
2. **Trace the blast radius before changing anything.** Run `python tools/master.py impact --name X` (or `--path`) for every module, CLI flag, project.json key, asset filename or documented command you are about to touch, and put each site it reports in the plan — a change is not done until every site agrees. Add a removal task only with the sites it will break.
3. **Plan a small DAG.** 3–7 tasks is normal. Every task names its owner, inputs, dependencies, and acceptance check.
4. **Delegate one bounded task at a time** (parallel only when tasks are independent and read-only).
5. **Verify the artifact, not the claim.** Run the command, read the file, inspect the stream. "I finished" is not evidence.
6. **On critical failure: stop the dependent path.** Retry only transient failures. Do not publish a warn-only result.
7. **Re-run the index, then write the ledger.** `./check.sh` must pass — that is ruff, compileall, pytest and `impact --all` — before any task is called complete. Then record: task, status, attempts, evidence, artifact paths, blocking reason, next action.
8. **Report in this shape:** what changed → evidence → what is blocked → one next action.

## 3. Task packet template

```
GOAL: one sentence.
CONTEXT: what the master already knows; do not make the subagent re-discover it.
SCOPE: exact files/directories. Do not touch anything else.
CONSTRAINTS: no secrets, no destructive commands, preserve tests.
ACCEPTANCE: the exact command(s) and/or artifact checks that prove completion.
REPORT: files changed, commands run, evidence, unresolved issues. Under 200 words.
```

## 4. Code search rules

- Use `rg`/`Explore`; cite `path:line` for every claim.
- Read the surrounding function before recommending a change.
- Search for callers before editing a shared function.
- Do not guess line numbers or APIs; verify them.
- The runtime master exposes this as: `python tools/master.py search "<query>"`.

## 5. Production workflows

```bash
# Plan only
python tools/master.py produce --topic "Ego Depletion" --id SH-17 --slug short_17_ego_depletion --dry-run

# Research -> script -> project -> render -> release gate
python tools/master.py produce --topic "Loss Aversion" --id SH-17 --slug short_17_loss_aversion

# Blueprint only (no GPU render)
python tools/master.py produce --topic "Loss Aversion" --id SH-17 --slug short_17_loss_aversion --blueprint

# Audit the whole repository (projects, renders, dossiers, tracker and cross-file references)
python tools/master.py audit

# Change propagation: what still names a module, flag, asset or symbol
python tools/master.py impact --name thumbnail_studio
python tools/master.py impact --all          # every dangling reference; exit 1 if any

# The whole gate, in order: ruff, compileall, pytest, impact
./check.sh

# Code search
python tools/master.py search "def build_and_verify"

# Run state
python tools/master.py status [RUN_ID]
python tools/master.py resume RUN_ID --yes
```

**Thumbnails Policy:**
- **Shorts (9:16):** Strictly zero thumbnails. YouTube selects feed previews directly from the video's own frames, so nothing generates, uploads, or gates a thumbnail image for Shorts; the Shorts thumbnail subsystem was permanently deleted on 2026-11-01.
- **Long-Form (16:9):** Custom 16:9 thumbnails are supported and generated via `tools.branding_engine.render_longform_thumbnail()`. All long-form thumbnails must pass through the policy gate (strict validation: zero misleading imagery, zero real-person likeness or copyright infringement).

## 6. Non-negotiable gates

- **Research / Fact-check:** every video declares `content_type` (`factual` or `fiction`, default `factual`). The research step verifies that a factual script is correct — it is a fact-check layer, not a mandate to ground every video in a scientific study. Factual science videos use a verified dossier from `channel_assets/scientific_dossiers.json` or an explicit `--dossier`; synthetic dossiers are rejected. Never invent a statistic, study, researcher or year. **Fiction (invented stories, novels, skits) is exempt** from research and fact-checking.
- **Fact-check gate:** the `factcheck` worker (`tools/fact_check.py`) runs after the project is assembled and before the render. Fiction returns `exempt`; a factual video passes via its verified dossier (`satisfied_by_dossier`) or a live-web report (Exa) in which every claim is corroborated by a retrieved HTTPS source. An unverified claim is flagged and blocks the render; a missing `EXA_API_KEY` fails closed with the fix command (no offline fallback). Standalone: `python tools/master.py fact-check --project <path>`.
- **Assets:** Every video requires its own distinct, topic-specific assets (character sprites, backgrounds, cutouts, props, sound cues). Never recycle generic visuals across distinct topics. If a project's verified asset already exists on disk, reuse it via idempotent caching; otherwise, generate fresh assets tailored specifically to that video.
- **Audio:** 100% local Kokoro-82M ONNX model (Apache-2.0, `tools/kokoro_models/kokoro-v1.0.onnx` + `voices-v1.0.bin`). Never use Microsoft Edge-TTS, Azure Cloud TTS, or external cloud speech APIs under any circumstance.
- **Script:** 8–12 scenes, 105–155 words, hook ≥ 70/100, no numeric claim outside the dossier, no method or
  mechanism claim outside the dossier, no voice blacklist words. A spoken number needs a claim with a printed
  page locator bound to that scene; so does a spoken method or brain mechanism. The generator once prefixed
  every data scene with "controlled laboratory testing" regardless of the study, and shipped a dopamine
  mechanism Brickman et al. (1978) never mentions — `method_claims` is what stops that repeating. Never name
  a method (lab, experiment, scan, interview) or a neural mechanism unless the dossier states it.
- **Project:** `project.json`, 8–12 scenes, upload kit, matching ID.
- **Render:** valid MP4, 1080×1920 (or 1920×1080), 30 fps, AAC 48 kHz, ≥ 5 s. Motion issues are warnings.
  Every burned-in text layer on a Short — caption, hook card, note, stat card — must sit inside
  **0.44–0.76 of frame height**: below the face our own 3D prompt centres at 30–58%, above the Shorts
  UI block (~20–25% of the bottom, where the channel row, caption, music strip and progress bar live).
  `caption_safe_band` enforces it; a lower-third caption is correct for landscape and wrong for vertical.
- **Consistency:** no dangling reference. A module, script, worker kind or verifier name that the code
  still cites but that no longer exists fails the release gate outright — the same removal that left
  the thumbnail studio referenced from six files and six documents must never be repeatable. Stale
  line numbers and document examples are reported as warnings and must be cleared before the change
  is called done.
- **Release:** all of the above must pass before upload. Publish requires `--publish --yes`.

## 7. Safety

- Never commit `channel_assets/client_secrets.json`, `*.token.json`, or `.orchestrator/` run data.
- Never run `git push`, `git reset --hard`, `git clean`, or force-push without explicit user approval.
- Never publish/upload/deploy without explicit approval for that action.
- When a shared file is being edited concurrently, re-read it before editing and keep changes additive.

## 8. Report format (master's final message)

```
Status: PASSED | FAILED | BLOCKED
Changed: <files or artifacts>
Evidence: <command outputs, measured values, file paths>
Blocked: <what cannot proceed and why>
Next: <one action>
```
