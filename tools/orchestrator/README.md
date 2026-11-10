# Master Orchestrator

A thin supervisor + specialist workers + independent verifiers + durable ledger, built for the FrameForge production pipeline. It is deliberately **not** a chat loop: the master's job is to make sure a claimed completion is actually true.

## Why this structure

The design combines four established patterns:

- **Orchestrator–workers** (Anthropic): a lead decomposes the goal and delegates to specialists; use workflows when the steps are predictable.
- **Supervisor + handoffs** (LangGraph / OpenAI Agents SDK): a central controller routes to named agents and owns the state; agents do not free-run the whole process.
- **Manager + expected output** (CrewAI hierarchical process): every delegated task has a concrete expected artifact, not a vibe.
- **Task ledger + progress ledger** (Magentic-One): the orchestrator records facts, the plan and per-step progress, and replans when a step stalls.

The important inversion: **verification belongs to the master, not the worker.** A worker saying "done" is a claim; the master's gate is the evidence.

## Architecture

```
tools/master.py                         CLI entry point
tools/orchestrator/
  master.py        MasterAgent           DAG, dispatch, retries, blocking, report, resume
  workflows.py     Workflow builders     produce, release_existing, audit, search, custom
  contracts.py     TaskSpec/Record       typed task, result, check and run contracts
  state.py         RunStore/RunContext   .orchestrator/runs/<id>/run.json + events.jsonl
  impact.py        Change index          what still names a module, flag, asset or citation
  workers.py       specialists           research, script, project, build, release,
                                         publish, search, audit
  verifiers.py     independent gates     research, script, project, packaging, render,
                                         precompose, publish, consistency
  tools.py         ProjectTools          read-only code search, file read, safe commands
```

Run state is durable at `.orchestrator/runs/<run_id>/run.json`; the human report is `REPORT.md`; every log line is appended to `events.jsonl`.

## Contract

Each task has an id, worker kind, parameters, dependency list, verifier list, retry budget and optional approval flag.

A task passes only when:

1. the worker returns `ok=True`,
2. every declared artifact exists and is non-empty,
3. every verifier returns no critical failure.

Warnings are reported but do not silently become success. A failed required task blocks every dependent task.

## Workflows

```bash
python tools/master.py produce --topic "Loss Aversion" --id SH-17 --slug short_17_loss_aversion
python tools/master.py produce --topic "Loss Aversion" --id SH-17 --slug short_17_loss_aversion --blueprint
python tools/master.py produce --topic "Loss Aversion" --id SH-17 --slug short_17_loss_aversion --dry-run
python tools/master.py audit
python tools/master.py impact --name thumbnail_studio
python tools/master.py impact --all
python tools/master.py search "def build_and_verify"
python tools/master.py status
python tools/master.py resume <run_id> --yes
python tools/master.py run --spec path/to/workflow.json
```

Validate reviewed existing artifacts without research, script, asset, project or render generation:

```bash
python tools/master.py release-existing --project path/to/project.json --evidence path/to/evidence.json --privacy unlisted
```

Prepare a non-publishable review draft from an authored project:

```bash
python tools/master.py prepare-release --project path/to/project.json [--output path/to/release_evidence.draft.json]
```

The command copies only supplied project/dossier facts. Its evidence is always
`schema_version: 1`, `status: draft`, and intentionally unreviewed; it cannot pass
`release-existing` until a human supplies page-level evidence and marks it reviewed.

Validation-only mode creates a single `release` task and makes no YouTube requests. Add
`--publish --yes` only when upload is authorized. The resulting approval-required publisher
depends on all seven strict release verifiers. `--privacy` accepts `unlisted` (default) or
`public`; public visibility requires its own authorization.

`release-existing` binds the evidence video ID, page-level claims, editorial suggestions and
ordered scene-text SHA-256 to the project. Citation verification, the evidence-bundle path and
synthetic-media declaration must agree. Numeric narration must be supported by a claim for that
scene; there is no numeric exemption. Warnings declared as strict-release checks (including
packaging, precompose, motion and consistency) block that release. Ordinary `produce` retains its
existing warning behavior and may pass with warnings.

A strict release saves resolved paths and SHA-256 fingerprints for the project, evidence,
upload kit and canonical MP4, plus a hash of normalized upload metadata. Every publisher attempt,
including a resumed failed/interrupted publisher, compares those fingerprints before upload.
Changed inputs, changed requested privacy, or older run records without fingerprints block
fail-closed. Start a fresh `release-existing` validation for changed inputs; approval cannot
reuse an earlier release pass for different artifacts.

`produce` DAG:

```
research -> script -> project -> build -> release
```

`--blueprint` stops after `project`. `produce --publish` is retired; publish the completed project through `release-existing` with a reviewed evidence bundle and explicit `--publish --yes`.

## Gates

| Gate | Critical checks |
|---|---|
| research | dossier fields, provenance, year, quantitative stat |
| script | 8–12 scenes, 105–155 words, hook ≥ 70, prompts, no unsourced number, claims ledger |
| project | project.json, scene count, matching ID, upload kit |
| render | MP4 streams, dimensions, 30 fps, AAC 48 kHz, duration ≥ 5 s; motion quality is a warning |
| packaging | title exists, internal IDs (warning), title lint (warning) |
| publish | 11-char video ID, external upload receipt; tracker bookkeeping reported separately |
| consistency | no dangling import, script, worker kind or verifier name; document and citation drift is a warning |

There is no thumbnail gate. YouTube selects the Shorts feed preview from the video's own frames, so the subsystem was deleted on 2026-11-01 — and the removal itself is what the `consistency` gate exists to police: six source files and six documents kept naming the thumbnail studio after it was gone, and no gate noticed until a run tried to execute one of them.

## Adding a worker

1. Subclass `Worker`, set `kind`, implement `run(spec, ctx) -> WorkerResult`.
2. Return real artifact paths in `result.artifacts`; the master verifies they exist.
3. Put fact claims in `result.facts` and structured evidence in `result.data`.
4. Add it to `default_workers()`.
5. Add a verifier in `verifiers.py` and register it with `@verifier("name")`.
6. Add a task to a workflow and a test.

## Adding a verifier

A verifier receives `(spec, result, ctx)` and returns `CheckResult`s. Critical failures block the task; warnings are surfaced in the report. Never verify by reading `result.ok` alone.

## Safety model

- Code search and file reads are root-scoped; shell commands are allowlisted.
- Publish/upload requires `--yes`; the master never publishes on its own.
- The research worker does not fall back to synthetic evidence. An unknown topic fails with instructions to add a dossier.
- Uploads preflight the exact Cognitive Core channel ID and default to unlisted, with made-for-kids false. The publisher passes the project's synthetic-media setting.
- Atomic receipts live under `channel_assets/upload_receipts/<internal-video-id>.json`, outside project directories. Operation identity binds the internal ID, media hash and normalized request metadata hash. A receipt lock serializes concurrent callers.
- Receipt states are `prepared`, `uploading`, `ambiguous`, `uploaded`, `verified`. An uploading/ambiguous receipt requires manual reconciliation and blocks all later inserts. Changed operation metadata also blocks reuse until reconciled.
- Uploaded/verified receipts query their existing remote ID and validate ownership, title and privacy without inserting again. Returned synthetic disclosure is recorded; omission means unknown. A known disclosure mismatch blocks verification.
- Remote ID and receipt are saved before tracker bookkeeping. Tracker failure adds a receipt note and does not retry the upload. No uploader posts comments, replies, likes, pins or playlist changes.
- Run data is local and ignored by git; credentials are ignored too.

## Relation to `tools/agents.py`

`tools/agents.py` is the legacy "7-agent" procedural crew. It remains for compatibility, but it is not a supervisor: it runs a fixed sequence. Its research stage now requires a complete dossier instead of inventing a study. Its `--upload` option requires `--evidence PATH --yes` and delegates to the master's strict reviewed release. Use `tools/master.py` for production and release verification.

## Sources

- Anthropic, [Building effective AI agents](https://www.anthropic.com/research/building-effective-agents)
- Microsoft Research, [Magentic-One](https://www.microsoft.com/en-us/research/articles/magentic-one-a-generalist-multi-agent-system-for-solving-complex-tasks/) and [paper](https://arxiv.org/html/2411.04468v1)
- LangGraph, [multi-agent supervisor](https://reference.langchain.com/python/langgraph-supervisor)
- OpenAI Agents SDK, [handoffs](https://openai.github.io/openai-agents-python/handoffs/) and [guardrails](https://openai.github.io/openai-agents-python/guardrails/)
- CrewAI, [hierarchical process FAQ](https://docs-platform.crewai.com/platform/en/resources/frequently-asked-questions)
- Claude Code, [subagents](https://academy.claude.com/courses/claude-code-101/subagents)
