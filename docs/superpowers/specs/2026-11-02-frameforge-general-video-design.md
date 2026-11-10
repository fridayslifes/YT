# FrameForge: general YouTube production

This is a design snapshot. The [later pipeline code audit](../../reports/2026-11-02-pipeline-code-audit.md) fixed several defects listed below and records current release behavior; the broader profile and local-model design remains unimplemented.

Status at this checkpoint: DESIGN FOR REVIEW, 2026-11-02. The user selected the approach below; the wider general-video implementation awaited approval at that time. This document alone authorizes no production behavior change.

## Intent, scope, and alternatives

Make FrameForge useful for varied YouTube videos, with one master responsible for planning, specialist dispatch, independent review, evidence, and release. Cognitive Core remains a channel profile, not the definition of every video.

| Approach | Tradeoff | Decision |
| --- | --- | --- |
| Extend the existing master with local-model agent adapters and profiles | Reuses the ledger, renderers, and checks; requires correcting their current assumptions | User-selected |
| Replace the master with an agent framework | More orchestration features immediately; migration and framework coupling risk losing existing safeguards | Not selected |
| Keep deterministic workers with manual agent assistance | Lowest integration cost; cannot deliver autonomous specialist coordination | Not selected |

Goals: support Shorts and long-form presentation, tutorial, documentary, and other configured recipes; improve factual, editorial, audiovisual, and operational quality; release existing renders without regeneration. Non-goals: a new editor UI, renderer rewrite, channel rename, thumbnails, automatic engagement, or automatic deletion. Anti-goals: fabricated evidence, hidden model selection, silent quality downgrades, duplicated uploads, and an agent approving its own work.

## Confirmed baseline and proposed corrections

These are source-review findings, except the explicitly identified resume probe; this design does not claim new production reproductions.

| Current behavior and evidence | Correction |
| --- | --- |
| Research overwrites verification/synthetic flags: `tools/orchestrator/workers.py:58`, `:85`; verifier trusts them at `tools/orchestrator/verifiers.py:158` | Preserve provenance; separate source ingestion from independent claim approval |
| Numeric check searches dossier substrings and exempts 5: `tools/orchestrator/verifiers.py:235` | Validate structured claims, exact values, units, populations, and context |
| Missing fields invent neuroscience/cortisol assertions: `tools/creative_engine.py:399` | Missing factual content becomes a research request or an omitted claim |
| Production forces short format and 9:16: `tools/creative_engine.py:492`, `:535`; short-only script gates at `tools/orchestrator/verifiers.py:199` | Resolve format and editorial policy from profiles |
| One existing asset hides missing secondary assets: `tools/pipeline.py:511` | Check every required asset, including audio and overlays; distinguish explicit alternatives |
| Precompose issues become warnings at `tools/orchestrator/verifiers.py:448`; warnings can pass at `tools/orchestrator/master.py:281` | Explicit profile release policy; unresolved quality warnings block release |
| Resume trusts existence at `tools/orchestrator/master.py:87`, `:336` | Hash inputs/outputs; invalidate descendants. Earlier memory-only probe left release PASSED when build became PENDING |
| `timeout_s` exists at `tools/orchestrator/contracts.py:56`, but worker dispatch at `tools/orchestrator/master.py:241` does not enforce it | Enforce deadlines and cancellation outside the worker |
| Upload always starts an insert at `tools/upload_api.py:360`; comment/like occur at `:401`, `:424` | Durable upload journal; separately authorized engagement operations |

## Profiles and artifact contracts

Use versioned, validated records. Preserve current project fields through an explicit migration reader; never rewrite existing videos merely to migrate metadata.

- **Channel profile:** channel ID, credential reference, voice, branding, vocabulary, category, audience declarations, metadata defaults. Cognitive Core retains its present identity. Credentials stay outside prompts, artifacts, and logs.
- **Video profile:** format, target duration, aspect/resolution/frame rate, language, speech backend/voice, content recipe, editorial requirements, and evidence policy. Resolve channel defaults, recipe defaults, then explicit video overrides; record the immutable snapshot. Reject contradictory or unsupported combinations.
- **Evidence bundle:** source IDs/URLs, retrieved date, supporting excerpt/location, claim IDs, exact quantities/units, scope, and reviewer verdict. Factual assertions require primary evidence appropriate to their domain. Demonstrations can use captured original results; opinions/fiction are identified as such. Scientific study fields are required only when those claims are made. Missing evidence never becomes invented evidence.
- **Project package:** scenes/chapters, narration, storyboard, asset manifest, claim references, captions, metadata, profile versions, and content hashes.
- **Task envelope:** role, inputs/hashes, dependencies, named write scope, allowed tools, skill/version references, local runtime/model version, model artifact hash/license, deadline, RAM/context/token limits, and acceptance checks. Results contain artifacts, citations, diagnostics, usage, and failure classification—not authoritative pass declarations.
- **Release receipt:** exact channel, media and metadata hashes, resolved privacy/audience settings, independent review/check results, and authorized action. Any change invalidates the receipt.

Initial renderer capability contract: English narration; short 1080×1920 or long 1920×1080; 30 fps; final AAC 48 kHz. `tools/build_video.py:67` and `:73` fix frame rate/dimensions; local speech currently fixes English at `:210`. Reject other languages, resolutions, frame rates, or unsupported voices before generation. Declaring a profile field does not make it supported. A scoped renderer/TTS propagation stage must validate these settings end to end, route an explicit speech backend/voice, include them in cache identity, and verify the actual output; additional combinations require separate capability tests.

## Master and specialist execution

The master dispatches research, script, storyboard, packaging, build, and publishing specialists through a bounded DAG. Their language-model reasoning uses a **local model server**, with no Codex CLI, cloud LLM, or cloud LLM fallback. Adapters implement start/status/cancel/result with auditable events and explicit model/tool/resource configuration. Deterministic render/build/API operations remain scoped tools.

This is not an entirely offline media pipeline. Speech currently uses remote Edge TTS for ordinary voice names (`tools/build_video.py:237`–`:243`), transmitting narration text; Kokoro is a separate local path. The local-LLM choice does not authorize new remote speech use. Profiles must disclose and authorize Edge speech explicitly, or select validated local speech and block if unavailable. Never substitute a remote speech backend or a different voice silently.

Use separate execution identities and contexts for creator, editorial reviewer, and technical verifier. Reviewers receive sources plus artifacts, not a creator's pass assertion. The master alone records acceptance. Enforce scoped writes at the executor boundary; run one writer at a time and parallelize only independent read-only tasks. Restrict publication credentials to the publisher. Route legacy production entry points through the same master contract, preserving documented compatibility or reporting explicit deprecation.

Host inventory reports an Apple M5 MacBook Pro, 16GB RAM, about 200GiB free disk, and no instruction LLM/runtime. Existing image/Whisper/depth models do not supply specialist reasoning. After approval, benchmark candidate models with llama.cpp or MLX locally; record provenance, hash, license, peak RAM, latency, structured-output/tool reliability, and evidence-review accuracy. Nothing is installed or quality-proven. Runtime/weights require several GB; disclose exact disk/cache requirements before installation.

Default to one local inference request at a time with bounded RAM, context, tokens, and wall time. Unload the LLM before GPU-heavy image/depth/video rendering; the scheduler must prevent overlap. Implement the selected local adapter plus a fake test adapter, independently of this chat's tools. Network retrieval and authorized YouTube API calls remain possible: research retains primary-source URLs/provenance and independent review; local inference does not make unsupported claims trustworthy.

## Workflow, recovery, and publication

1. Resolve brief/profiles and plan; reject unsupported capabilities before expensive work.
2. Research and claim review; script and independent editorial review; bounded revision loop.
3. Storyboard/assets and packaging; preflight every required input; build through existing render tools.
4. Independent checks inspect streams, duration, audio levels/clipping, caption timing/fidelity/readability, representative frames, asset continuity, and title-to-content agreement. Subjective checks produce reviewer evidence, not manufactured objective scores.
5. Release only after required checks pass, warnings are resolved, and repository consistency passes. Existing global policies remain enforced until approved profile-aware policies replace them; Cognitive Core's current limits become its preset, not silently weakened defaults.
6. Upload only the authorized receipt. Re-read channel identity and privacy before transmission. Persist operation key, media hash, resumable-session state, and returned video ID atomically. Retry only classified transient failures within limits. A lost final response triggers reconciliation or human attention, never a blind new insert. Tracker failure retries bookkeeping, not upload.
7. Independently confirm remote video identity, processing/status, privacy, and receipt association before reporting success. Comments, likes, publication/privacy changes, and local cleanup are separate actions requiring their own authorization. Upload authorization does not imply them.

A **release-existing** workflow imports a project/render, reconstructs evidence and profiles, then executes the same review/release/upload path. Missing provenance blocks; it never silently regenerates sources or uploads a substitute render.

The ledger records task owners, attempts, dependencies, hashes, decisions, budgets, errors, and next action. Checkpoints are atomic. Resume revalidates fingerprints and propagates invalidation; publication receipts remain immutable. Enforce wall-clock deadlines and process cancellation, classify permanent versus transient errors, and bound repair attempts. Ambiguous external side effects enter reconciliation state. Audit distinguishes drafts, blocked releases, and verified uploads.

## Acceptance and sequencing

| Area | Independent acceptance evidence |
| --- | --- |
| Profiles | Short and long-form fixtures use different gates; non-scientific content needs no study dossier; unsupported language/resolution/fps requests fail before generation |
| Evidence | Synthetic provenance, substring-only numeric matches, exempt 5, and missing neuroscience fields cannot pass; supported claims retain source context |
| Agents | Local benchmark meets RAM/time/quality limits; LLM never overlaps GPU-heavy rendering; no cloud LLM fallback; creator cannot approve its own work; timeout cancels and blocks descendants |
| Speech | Explicit authorized backend/voice reaches synthesis and cache identity; local-only speech never calls Edge; unsupported/unavailable settings block; English output and captions are inspected |
| Media | Missing secondary/audio assets and stale captions fail; real short/long exports satisfy profile stream and editorial checks |
| Recovery | Modified input invalidates downstream passes; unchanged artifacts are reused; permanent errors do not loop |
| Upload | Mocked success, lost response, tracker failure, and resume never initiate duplicate uploads; no automatic comment/like; existing render follows identical gates |
| Repository | Separate reviewer approves; verifier runs focused regressions, `./check.sh`, and artifact inspection; ledger records evidence |

Implement after approval: provenance/release defects; profiles/migration and renderer/TTS propagation; local executor and independent review; existing-release/upload journal; end-to-end fixtures/documentation. No live upload is a test without specific authorization.

Risks: local-model quality and correlated reviewer errors, memory pressure, download/storage overhead, insufficient source access, cancellation limits, irreversible upload ambiguity, and legacy assumptions. Mitigate with measured benchmarks, source-backed review, deterministic checks, resource limits, immutable artifacts, and fail-closed reconciliation. This design promises no view or retention gains.

Implementation call after approval: choose exact local model/runtime and operating limits from the benchmark evidence. Optional user preference: a maximum disk allowance for runtime, weights, and caches; absent a cap, propose a measured storage budget before installation. Backend choice is settled as local inference.

## Recorded blast radius

Ran `.venv/bin/python tools/master.py impact --path <module> --json` for the original eleven proposed modules and, during review, `tools/build_video.py` (17 sites); all exited 0. Locations are audit snapshots. Duplicate kinds at one location are collapsed. Preserve interfaces or update affected callers/examples/tests; retain historical evidence with superseding notes. Re-run symbol/flag/key traces before implementation. The index includes basename matches: `tools/visual_engine.py:449` imports third-party `transformers.pipeline`.

For compactness, **O** means `tools/orchestrator/`; **L** means `docs/reports/2026-11-02-rename-ledger.md`. These are path prefixes/aliases, not new files.

| Proposed module | All indexed sites, grouped by file |
| --- | --- |
| O/contracts.py | O/README.md:23 |
| O/master.py | AGENTS.md:5,25,50,56,59,62,65,68,69,75,78,79; GEMINI.md:244,322,326,329,332,335,336,337,340,341; README.md:14; L:100,357; pyproject.toml:6; tests/test_impact.py:121; O/README.md:19,21,50,51,52,53,54,55,56,57,58,59,106 |
| O/workers.py | L:127,128,129,130,282,283; O/README.md:26; O/cli.py:265 |
| O/workflows.py | tests/test_impact.py:44,87; O/README.md:22 |
| O/verifiers.py | GEMINI.md:159; L:279,280,281,341; requirements.txt:23; tests/test_hookscore.py:199; tests/test_impact.py:40; tests/test_project_contract.py:556; O/README.md:28,90 |
| O/cli.py | L:500; tests/test_impact.py:122 |
| O/state.py | L:101; O/README.md:24 |
| tools/creative_engine.py | GEMINI.md:71; L:117,141,189,320; tests/test_creative_engine.py:35; tests/test_project_contract.py:506; tools/agents.py:43; O/workers.py:45,116,197,343; tools/pipeline.py:62 |
| tools/pipeline.py | CONTENT_TRACKER.md:118,123,127,132,133; GEMINI.md:9,14,17,20,25,39,48,54,56,61,153,157,159,164,169,174,179,184,210,212,290,293,313; channel_assets/YOUTUBE_API_GUIDE.md:28,31,38; L:115,131,164,176,177,178,190,193,307,342; pyproject.toml:6; requirements-optional.txt:67; requirements.txt:21; shorts/README.md:28,29; shorts/short_13_dunning_kruger/UPLOAD_KIT_SHORT_13.md:28,31; shorts/short_16_simulation_argument/UPLOAD_KIT_SH16.md:28,31; tests/test_fidelity.py:21; tests/test_impact.py:30,83; tests/test_output_format.py:213; tests/test_project_contract.py:398,542; tools/agents.py:301,334; O/verifiers.py:190,361,432; O/workers.py:235,343; tools/visual_engine.py:449 |
| tools/upload_api.py | channel_assets/YOUTUBE_API_GUIDE.md:43; docs/reports/2026-11-02-sh13-release-proposal.md:24; requirements-optional.txt:65; tests/test_tracker_schema.py:109; tools/agents.py:374; O/workers.py:281; tools/pipeline.py:1154,1158 |
| tools/agents.py | GEMINI.md:9,322; L:96,126,166,188,277,278,319; O/README.md:104,106; tools/pipeline.py:1118,1127,1140 |
| tools/build_video.py | CONTENT_TRACKER.md:68; GEMINI.md:95; VIDEO_GUIDE_SHORTS_AND_LONG.md:188; assets/audio/sfx/README.md:3; L:97,98,114,147,340; requirements-optional.txt:40,49; requirements.txt:21,30; tests/test_branding.py:17,18; tests/test_project_contract.py:359; tools/pipeline.py:61 |

Relative-import and semantic callers need additional symbol tracing; the index is not a complete dependency graph. Proposed schema/adapters/tests are new work, not existing implemented interfaces. The later implementation plan must trace policy/document changes too, especially the currently global gates in AGENTS.md and GEMINI.md.
