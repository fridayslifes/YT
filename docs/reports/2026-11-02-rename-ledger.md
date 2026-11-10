# FrameForge rename ledger — 2026-11-02

This is a historical rename checkpoint. The compatibility `/Users/friday/Desktop/Yt` symlink observed then is absent now; use `/Users/friday/Desktop/FrameForge`. See the [later pipeline code audit](2026-11-02-pipeline-code-audit.md) for current workspace status.

Status: PASSED for the local repository rename. The Codex app's saved project label still reads `yt`; its project registry has no supported agent-side rename operation.

Task: Rename the local project to FrameForge while preserving Cognitive Core channel identity and all existing videos.

Attempts: 2 mutation passes, including the documentation review correction. Builder acceptance tests: not run; verification belongs to a separate verifier.

## Goal and acceptance

Done means the canonical directory is `/Users/friday/Desktop/FrameForge`, the old `/Users/friday/Desktop/Yt` path resolves through a compatibility symlink to the same directory, pipeline-facing labels say FrameForge, Cognitive Core remains the channel preset, the existing Python environments remain usable, and the independent repository gate passes.

The independent reviewer inspected the text patch and identified two README inaccuracies; the builder corrected them. The master then checked the directory and symlink inode relationship, both environment executables, the worker CLI, the scoped file hashes and media presence, and ran `./check.sh` from the new canonical directory. Evidence is recorded below.

## Task DAG

| Task | Owner | Inputs | Dependencies | Acceptance check | Status |
| --- | --- | --- | --- | --- | --- |
| R1 — Trace references | Builder (read-only preflight) | The 17 scoped existing text files; master CLI and gate references used by the new README | None | Every reported site appears in the impact plan below | Trace recorded |
| R2 — Back up and move the directory | Builder | Existing root; exact text originals; destination absence precondition | R1 | Independent verifier checks real new directory, compatibility symlink, and matching directory inode | Passed |
| R3 — Rename pipeline labels and document scope | Builder | Named docstrings, CLI/report banners, heading, channel setup asset links; new README | R2 | Independent reviewer confirms only authorized text changes and accurate current capabilities | Passed after documentation correction |
| R4 — Review the diff | Separate Reviewer | Original text backups, unified patch, manifest, channel-preservation constraints | R3 | No behavior or channel identity changes; no asset deletion | Passed after correction |
| R5 — Exercise environments and repository gate | Separate Verifier | New root, old alias, existing environments, reviewed changes | R4 | Executables/help work and `./check.sh` passes, including the full impact index | Passed |
| R6 — Record evidence and report | Master | Reviewer findings and verifier command outputs | R5 | Final status, attempts, evidence, artifacts, blockers, and one next action are recorded | Passed |

## Compatibility decision

The entire project directory is moved with a filesystem rename, then the old path is created as a symbolic link to the new directory. This avoids copying or regenerating videos and keeps embedded absolute paths in existing environment launchers, saved app roots, skills, and historical ledgers resolving. Environment wrappers and historical run data are deliberately not rewritten.

## Change scope

The existing files in the impact plan receive pipeline identity text changes only. `GEMINI.md` retains Cognitive Core as the preset in its heading. The channel setup kit receives only absolute-root link updates. The new README distinguishes the currently built-in Shorts/Cognitive Core production workflow from proposed broader workflows, and records `long_form/` as a prepared destination containing only format documentation, with no active local project.

Channel-specific upload copy, the channel's genre baseline, generated asset metadata, tracker, voice profile, upload API, branding engine, video projects, credentials, and media assets are outside the text-edit scope. Existing behavior and previously reported defects are not repaired by this rename.

## Artifacts and evidence

- Pre-edit impact results: `/tmp/frameforge-rename-review/impact-before.json`.
- Exact original text files: `/tmp/frameforge-rename-review/originals/`.
- Unified text patch: `/tmp/frameforge-rename-review/changes.patch`.
- File hashes and directory move intent: `/tmp/frameforge-rename-review/manifest.json`.
- Mechanical mutation record: `/tmp/frameforge-rename-review/mutation-log.json`.
- Builder trace commands used the existing environment and the master impact CLI for each scoped path. A zero-site impact query returns exit 1; those results are listed explicitly below and are not a repository gate result.

Independent verification, 2 November 2026: the canonical root retains device `16777229` and inode `26748092` from the pre-move manifest; the old path is a symlink resolving to that same inode. All 19 scoped manifest file hashes matched before this ledger closeout. Both `.venv` and `.venv-flux2` run Python 3.11.14; the old path's `.venv` launcher also works. The master worker list and both Short 13/16 media files remain present. The complete `./check.sh` run passed: Ruff, compileall, 250 pytest passes with 16 known xfails, and `impact --all` with zero dangling references. The first post-rename gate had failed on an inaccurate README command example; the corrected second run passed.

Blocking reason: none for the repository rename. The separate Codex desktop saved project still displays `yt` at the compatibility path; the app exposes no supported project-rename tool to this agent. Pipeline and content defects identified during the wider audit remain separate work.

Next action: Change the Codex sidebar project label to FrameForge through the app's project menu when that control is available.

## Impact plan

Every reported site below has the same disposition: preserve the referenced module path, import, definition, asset path, and command interface. Existing edited lines keep their line count, so these pre-edit line locations remain aligned. Constructor and third-party-name matches are included even where the index's name matching is broader than the edited module. No module, CLI flag, project key, or asset filename is removed or renamed.

### requirements.txt

Reported sites: 0. Query exit code: 1.

No indexed reference sites were returned. Preserve the filename and existing interface.

### pyproject.toml

Reported sites: 0. Query exit code: 1.

No indexed reference sites were returned. Preserve the filename and existing interface.

### tests/conftest.py

Reported sites: 6. Query exit code: 0.

| Reported site | Kind | Planned disposition |
| --- | --- | --- |
| `tests/test_creative_engine.py:34` | import | Preserve reference and interface |
| `tests/test_fidelity.py:20` | import | Preserve reference and interface |
| `tests/test_hookscore.py:23` | import | Preserve reference and interface |
| `tests/test_project_contract.py:31` | import | Preserve reference and interface |
| `tests/test_project_contract.py:178` | import | Preserve reference and interface |
| `tests/test_tracker_schema.py:21` | import | Preserve reference and interface |

### tools/orchestrator/README.md

Reported sites: 1. Query exit code: 0.

| Reported site | Kind | Planned disposition |
| --- | --- | --- |
| `GEMINI.md:349` | doc-asset | Preserve reference and interface |

### tools/orchestrator/__init__.py

Reported sites: 13. Query exit code: 0.

| Reported site | Kind | Planned disposition |
| --- | --- | --- |
| `pyproject.toml:5` | doc-script | Preserve reference and interface |
| `tests/test_orchestrator.py:14` | definition | Preserve reference and interface |
| `tests/test_output_format.py:25` | definition | Preserve reference and interface |
| `tests/test_output_format.py:35` | definition | Preserve reference and interface |
| `tools/agents.py:406` | definition | Preserve reference and interface |
| `tools/build_video.py:665` | definition | Preserve reference and interface |
| `tools/build_video.py:814` | definition | Preserve reference and interface |
| `tools/orchestrator/impact.py:107` | definition | Preserve reference and interface |
| `tools/orchestrator/master.py:18` | definition | Preserve reference and interface |
| `tools/orchestrator/state.py:47` | definition | Preserve reference and interface |
| `tools/orchestrator/tools.py:31` | definition | Preserve reference and interface |
| `tools/visual_director.py:329` | definition | Preserve reference and interface |
| `tools/visual_engine.py:294` | definition | Preserve reference and interface |

### tools/audio_bank.py

Reported sites: 4. Query exit code: 0.

| Reported site | Kind | Planned disposition |
| --- | --- | --- |
| `GEMINI.md:95` | doc-script | Preserve reference and interface |
| `GEMINI.md:104` | doc-script | Preserve reference and interface |
| `tools/build_video.py:63` | import | Preserve reference and interface |
| `tools/pipeline.py:60` | import | Preserve reference and interface |

### tools/creative_engine.py

Reported sites: 9. Query exit code: 0.

| Reported site | Kind | Planned disposition |
| --- | --- | --- |
| `GEMINI.md:71` | doc-script | Preserve reference and interface |
| `tests/test_creative_engine.py:35` | import | Preserve reference and interface |
| `tests/test_project_contract.py:506` | import | Preserve reference and interface |
| `tools/agents.py:43` | import | Preserve reference and interface |
| `tools/orchestrator/workers.py:45` | import | Preserve reference and interface |
| `tools/orchestrator/workers.py:116` | import | Preserve reference and interface |
| `tools/orchestrator/workers.py:197` | import | Preserve reference and interface |
| `tools/orchestrator/workers.py:343` | import | Preserve reference and interface |
| `tools/pipeline.py:62` | import | Preserve reference and interface |

### tools/genre_director.py

Reported sites: 7. Query exit code: 0.

| Reported site | Kind | Planned disposition |
| --- | --- | --- |
| `GEMINI.md:253` | doc-script | Preserve reference and interface |
| `requirements-optional.txt:11` | doc-script | Preserve reference and interface |
| `tools/creative_engine.py:38` | import | Preserve reference and interface |
| `tools/studio_3d.py:47` | import | Preserve reference and interface |
| `tools/studio_3d.py:138` | import | Preserve reference and interface |
| `tools/visual_director.py:46` | import | Preserve reference and interface |
| `tools/visual_engine.py:135` | import | Preserve reference and interface |

### tools/build_video.py

Reported sites: 12. Query exit code: 0.

| Reported site | Kind | Planned disposition |
| --- | --- | --- |
| `CONTENT_TRACKER.md:68` | doc-script | Preserve reference and interface |
| `GEMINI.md:95` | doc-script | Preserve reference and interface |
| `VIDEO_GUIDE_SHORTS_AND_LONG.md:188` | doc-script | Preserve reference and interface |
| `assets/audio/sfx/README.md:3` | doc-script | Preserve reference and interface |
| `requirements-optional.txt:40` | doc-script | Preserve reference and interface |
| `requirements-optional.txt:49` | doc-script | Preserve reference and interface |
| `requirements.txt:21` | doc-script | Preserve reference and interface |
| `requirements.txt:30` | doc-script | Preserve reference and interface |
| `tests/test_branding.py:17` | import | Preserve reference and interface |
| `tests/test_branding.py:18` | import | Preserve reference and interface |
| `tests/test_project_contract.py:359` | import | Preserve reference and interface |
| `tools/pipeline.py:61` | import | Preserve reference and interface |

### tools/agents.py

Reported sites: 7. Query exit code: 0.

| Reported site | Kind | Planned disposition |
| --- | --- | --- |
| `GEMINI.md:9` | doc-script | Preserve reference and interface |
| `GEMINI.md:322` | doc-script | Preserve reference and interface |
| `tools/orchestrator/README.md:104` | doc-script | Preserve reference and interface |
| `tools/orchestrator/README.md:106` | doc-script | Preserve reference and interface |
| `tools/pipeline.py:1118` | import | Preserve reference and interface |
| `tools/pipeline.py:1127` | import | Preserve reference and interface |
| `tools/pipeline.py:1140` | import | Preserve reference and interface |

### tools/output_format.py

Reported sites: 6. Query exit code: 0.

| Reported site | Kind | Planned disposition |
| --- | --- | --- |
| `tests/test_output_format.py:16` | import | Preserve reference and interface |
| `tests/test_title.py:127` | import | Preserve reference and interface |
| `tools/agents.py:44` | import | Preserve reference and interface |
| `tools/creative_engine.py:39` | import | Preserve reference and interface |
| `tools/pipeline.py:63` | import | Preserve reference and interface |
| `tools/visual_director.py:47` | import | Preserve reference and interface |

### tools/pipeline.py

Reported sites: 86. Query exit code: 0.

| Reported site | Kind | Planned disposition |
| --- | --- | --- |
| `CONTENT_TRACKER.md:118` | doc-command | Preserve reference and interface |
| `CONTENT_TRACKER.md:118` | doc-script | Preserve reference and interface |
| `CONTENT_TRACKER.md:123` | doc-command | Preserve reference and interface |
| `CONTENT_TRACKER.md:123` | doc-script | Preserve reference and interface |
| `CONTENT_TRACKER.md:127` | doc-script | Preserve reference and interface |
| `CONTENT_TRACKER.md:127` | doc-command | Preserve reference and interface |
| `CONTENT_TRACKER.md:132` | doc-script | Preserve reference and interface |
| `CONTENT_TRACKER.md:132` | doc-command | Preserve reference and interface |
| `CONTENT_TRACKER.md:133` | doc-script | Preserve reference and interface |
| `CONTENT_TRACKER.md:133` | doc-command | Preserve reference and interface |
| `GEMINI.md:9` | doc-script | Preserve reference and interface |
| `GEMINI.md:14` | doc-script | Preserve reference and interface |
| `GEMINI.md:14` | doc-command | Preserve reference and interface |
| `GEMINI.md:17` | doc-command | Preserve reference and interface |
| `GEMINI.md:17` | doc-script | Preserve reference and interface |
| `GEMINI.md:20` | doc-command | Preserve reference and interface |
| `GEMINI.md:20` | doc-script | Preserve reference and interface |
| `GEMINI.md:25` | doc-command | Preserve reference and interface |
| `GEMINI.md:25` | doc-script | Preserve reference and interface |
| `GEMINI.md:39` | doc-command | Preserve reference and interface |
| `GEMINI.md:39` | doc-script | Preserve reference and interface |
| `GEMINI.md:48` | doc-command | Preserve reference and interface |
| `GEMINI.md:48` | doc-script | Preserve reference and interface |
| `GEMINI.md:54` | doc-script | Preserve reference and interface |
| `GEMINI.md:54` | doc-command | Preserve reference and interface |
| `GEMINI.md:56` | doc-command | Preserve reference and interface |
| `GEMINI.md:56` | doc-script | Preserve reference and interface |
| `GEMINI.md:61` | doc-command | Preserve reference and interface |
| `GEMINI.md:61` | doc-script | Preserve reference and interface |
| `GEMINI.md:153` | doc-script | Preserve reference and interface |
| `GEMINI.md:157` | doc-script | Preserve reference and interface |
| `GEMINI.md:157` | doc-command | Preserve reference and interface |
| `GEMINI.md:159` | doc-script | Preserve reference and interface |
| `GEMINI.md:164` | doc-script | Preserve reference and interface |
| `GEMINI.md:164` | doc-command | Preserve reference and interface |
| `GEMINI.md:169` | doc-script | Preserve reference and interface |
| `GEMINI.md:169` | doc-command | Preserve reference and interface |
| `GEMINI.md:174` | doc-command | Preserve reference and interface |
| `GEMINI.md:174` | doc-script | Preserve reference and interface |
| `GEMINI.md:179` | doc-script | Preserve reference and interface |
| `GEMINI.md:179` | doc-command | Preserve reference and interface |
| `GEMINI.md:184` | doc-command | Preserve reference and interface |
| `GEMINI.md:184` | doc-script | Preserve reference and interface |
| `GEMINI.md:210` | doc-script | Preserve reference and interface |
| `GEMINI.md:212` | doc-command | Preserve reference and interface |
| `GEMINI.md:212` | doc-script | Preserve reference and interface |
| `GEMINI.md:290` | doc-script | Preserve reference and interface |
| `GEMINI.md:290` | doc-command | Preserve reference and interface |
| `GEMINI.md:293` | doc-script | Preserve reference and interface |
| `GEMINI.md:293` | doc-command | Preserve reference and interface |
| `GEMINI.md:313` | doc-command | Preserve reference and interface |
| `GEMINI.md:313` | doc-script | Preserve reference and interface |
| `channel_assets/YOUTUBE_API_GUIDE.md:28` | doc-command | Preserve reference and interface |
| `channel_assets/YOUTUBE_API_GUIDE.md:28` | doc-script | Preserve reference and interface |
| `channel_assets/YOUTUBE_API_GUIDE.md:31` | doc-command | Preserve reference and interface |
| `channel_assets/YOUTUBE_API_GUIDE.md:31` | doc-script | Preserve reference and interface |
| `channel_assets/YOUTUBE_API_GUIDE.md:38` | doc-command | Preserve reference and interface |
| `channel_assets/YOUTUBE_API_GUIDE.md:38` | doc-script | Preserve reference and interface |
| `pyproject.toml:6` | doc-script | Preserve reference and interface |
| `requirements-optional.txt:67` | doc-script | Preserve reference and interface |
| `requirements.txt:21` | doc-script | Preserve reference and interface |
| `shorts/README.md:28` | doc-script | Preserve reference and interface |
| `shorts/README.md:29` | doc-command | Preserve reference and interface |
| `shorts/README.md:29` | doc-script | Preserve reference and interface |
| `shorts/short_13_dunning_kruger/UPLOAD_KIT_SHORT_13.md:28` | doc-command | Preserve reference and interface |
| `shorts/short_13_dunning_kruger/UPLOAD_KIT_SHORT_13.md:28` | doc-script | Preserve reference and interface |
| `shorts/short_13_dunning_kruger/UPLOAD_KIT_SHORT_13.md:31` | doc-command | Preserve reference and interface |
| `shorts/short_13_dunning_kruger/UPLOAD_KIT_SHORT_13.md:31` | doc-script | Preserve reference and interface |
| `shorts/short_16_simulation_argument/UPLOAD_KIT_SH16.md:28` | doc-command | Preserve reference and interface |
| `shorts/short_16_simulation_argument/UPLOAD_KIT_SH16.md:28` | doc-script | Preserve reference and interface |
| `shorts/short_16_simulation_argument/UPLOAD_KIT_SH16.md:31` | doc-command | Preserve reference and interface |
| `shorts/short_16_simulation_argument/UPLOAD_KIT_SH16.md:31` | doc-script | Preserve reference and interface |
| `tests/test_fidelity.py:21` | import | Preserve reference and interface |
| `tests/test_impact.py:30` | script-ref | Preserve reference and interface |
| `tests/test_impact.py:83` | script-ref | Preserve reference and interface |
| `tests/test_output_format.py:213` | script-ref | Preserve reference and interface |
| `tests/test_project_contract.py:398` | import | Preserve reference and interface |
| `tests/test_project_contract.py:542` | script-ref | Preserve reference and interface |
| `tools/agents.py:301` | import | Preserve reference and interface |
| `tools/agents.py:334` | import | Preserve reference and interface |
| `tools/orchestrator/verifiers.py:190` | import | Preserve reference and interface |
| `tools/orchestrator/verifiers.py:361` | import | Preserve reference and interface |
| `tools/orchestrator/verifiers.py:432` | import | Preserve reference and interface |
| `tools/orchestrator/workers.py:235` | import | Preserve reference and interface |
| `tools/orchestrator/workers.py:343` | import | Preserve reference and interface |
| `tools/visual_engine.py:449` | import | Preserve reference and interface |

### tools/studio_3d.py

Reported sites: 16. Query exit code: 0.

| Reported site | Kind | Planned disposition |
| --- | --- | --- |
| `GEMINI.md:44` | doc-command | Preserve reference and interface |
| `GEMINI.md:44` | doc-script | Preserve reference and interface |
| `GEMINI.md:253` | doc-script | Preserve reference and interface |
| `GEMINI.md:269` | doc-script | Preserve reference and interface |
| `GEMINI.md:272` | doc-command | Preserve reference and interface |
| `GEMINI.md:272` | doc-script | Preserve reference and interface |
| `GEMINI.md:275` | doc-script | Preserve reference and interface |
| `GEMINI.md:275` | doc-command | Preserve reference and interface |
| `GEMINI.md:278` | doc-command | Preserve reference and interface |
| `GEMINI.md:278` | doc-script | Preserve reference and interface |
| `GEMINI.md:281` | doc-script | Preserve reference and interface |
| `GEMINI.md:281` | doc-command | Preserve reference and interface |
| `GEMINI.md:284` | doc-command | Preserve reference and interface |
| `GEMINI.md:284` | doc-script | Preserve reference and interface |
| `pyproject.toml:6` | doc-script | Preserve reference and interface |
| `tools/pipeline.py:1115` | script-ref | Preserve reference and interface |

### tools/visual_director.py

Reported sites: 7. Query exit code: 0.

| Reported site | Kind | Planned disposition |
| --- | --- | --- |
| `GEMINI.md:28` | doc-script | Preserve reference and interface |
| `GEMINI.md:34` | doc-command | Preserve reference and interface |
| `GEMINI.md:34` | doc-script | Preserve reference and interface |
| `GEMINI.md:299` | doc-script | Preserve reference and interface |
| `tools/agents.py:45` | import | Preserve reference and interface |
| `tools/creative_engine.py:41` | import | Preserve reference and interface |
| `tools/visual_engine.py:136` | import | Preserve reference and interface |

### tools/visual_engine.py

Reported sites: 15. Query exit code: 0.

| Reported site | Kind | Planned disposition |
| --- | --- | --- |
| `GEMINI.md:83` | doc-script | Preserve reference and interface |
| `requirements-optional.txt:12` | doc-script | Preserve reference and interface |
| `requirements-optional.txt:17` | doc-script | Preserve reference and interface |
| `requirements-optional.txt:26` | doc-script | Preserve reference and interface |
| `requirements-optional.txt:32` | doc-script | Preserve reference and interface |
| `requirements-optional.txt:55` | doc-script | Preserve reference and interface |
| `requirements-optional.txt:60` | doc-script | Preserve reference and interface |
| `requirements.txt:22` | doc-script | Preserve reference and interface |
| `requirements.txt:41` | doc-script | Preserve reference and interface |
| `requirements.txt:44` | doc-script | Preserve reference and interface |
| `requirements.txt:48` | doc-script | Preserve reference and interface |
| `tools/build_video.py:64` | import | Preserve reference and interface |
| `tools/orchestrator/verifiers.py:361` | import | Preserve reference and interface |
| `tools/pipeline.py:65` | import | Preserve reference and interface |
| `tools/studio_3d.py:46` | import | Preserve reference and interface |

### GEMINI.md

Reported sites: 0. Query exit code: 1.

No indexed reference sites were returned. Preserve the filename and existing interface.

### channel_assets/CHANNEL_SETUP_KIT.md

Reported sites: 0. Query exit code: 1.

No indexed reference sites were returned. Preserve the filename and existing interface.

### tools/master.py

Reported sites: 66. Query exit code: 0.

| Reported site | Kind | Planned disposition |
| --- | --- | --- |
| `AGENTS.md:5` | doc-script | Preserve reference and interface |
| `AGENTS.md:25` | doc-script | Preserve reference and interface |
| `AGENTS.md:25` | doc-command | Preserve reference and interface |
| `AGENTS.md:50` | doc-command | Preserve reference and interface |
| `AGENTS.md:50` | doc-script | Preserve reference and interface |
| `AGENTS.md:56` | doc-script | Preserve reference and interface |
| `AGENTS.md:56` | doc-command | Preserve reference and interface |
| `AGENTS.md:59` | doc-command | Preserve reference and interface |
| `AGENTS.md:59` | doc-script | Preserve reference and interface |
| `AGENTS.md:62` | doc-script | Preserve reference and interface |
| `AGENTS.md:62` | doc-command | Preserve reference and interface |
| `AGENTS.md:65` | doc-script | Preserve reference and interface |
| `AGENTS.md:65` | doc-command | Preserve reference and interface |
| `AGENTS.md:68` | doc-script | Preserve reference and interface |
| `AGENTS.md:68` | doc-command | Preserve reference and interface |
| `AGENTS.md:69` | doc-command | Preserve reference and interface |
| `AGENTS.md:69` | doc-script | Preserve reference and interface |
| `AGENTS.md:75` | doc-script | Preserve reference and interface |
| `AGENTS.md:75` | doc-command | Preserve reference and interface |
| `AGENTS.md:78` | doc-script | Preserve reference and interface |
| `AGENTS.md:78` | doc-command | Preserve reference and interface |
| `AGENTS.md:79` | doc-script | Preserve reference and interface |
| `AGENTS.md:79` | doc-command | Preserve reference and interface |
| `GEMINI.md:244` | doc-script | Preserve reference and interface |
| `GEMINI.md:322` | doc-script | Preserve reference and interface |
| `GEMINI.md:326` | doc-script | Preserve reference and interface |
| `GEMINI.md:326` | doc-command | Preserve reference and interface |
| `GEMINI.md:329` | doc-command | Preserve reference and interface |
| `GEMINI.md:329` | doc-script | Preserve reference and interface |
| `GEMINI.md:332` | doc-command | Preserve reference and interface |
| `GEMINI.md:332` | doc-script | Preserve reference and interface |
| `GEMINI.md:335` | doc-command | Preserve reference and interface |
| `GEMINI.md:335` | doc-script | Preserve reference and interface |
| `GEMINI.md:336` | doc-command | Preserve reference and interface |
| `GEMINI.md:336` | doc-script | Preserve reference and interface |
| `GEMINI.md:337` | doc-command | Preserve reference and interface |
| `GEMINI.md:337` | doc-script | Preserve reference and interface |
| `GEMINI.md:340` | doc-command | Preserve reference and interface |
| `GEMINI.md:340` | doc-script | Preserve reference and interface |
| `GEMINI.md:341` | doc-command | Preserve reference and interface |
| `GEMINI.md:341` | doc-script | Preserve reference and interface |
| `pyproject.toml:6` | doc-script | Preserve reference and interface |
| `tests/test_impact.py:121` | script-ref | Preserve reference and interface |
| `tools/orchestrator/README.md:19` | doc-script | Preserve reference and interface |
| `tools/orchestrator/README.md:21` | doc-script | Preserve reference and interface |
| `tools/orchestrator/README.md:50` | doc-script | Preserve reference and interface |
| `tools/orchestrator/README.md:50` | doc-command | Preserve reference and interface |
| `tools/orchestrator/README.md:51` | doc-script | Preserve reference and interface |
| `tools/orchestrator/README.md:51` | doc-command | Preserve reference and interface |
| `tools/orchestrator/README.md:52` | doc-command | Preserve reference and interface |
| `tools/orchestrator/README.md:52` | doc-script | Preserve reference and interface |
| `tools/orchestrator/README.md:53` | doc-command | Preserve reference and interface |
| `tools/orchestrator/README.md:53` | doc-script | Preserve reference and interface |
| `tools/orchestrator/README.md:54` | doc-command | Preserve reference and interface |
| `tools/orchestrator/README.md:54` | doc-script | Preserve reference and interface |
| `tools/orchestrator/README.md:55` | doc-script | Preserve reference and interface |
| `tools/orchestrator/README.md:55` | doc-command | Preserve reference and interface |
| `tools/orchestrator/README.md:56` | doc-script | Preserve reference and interface |
| `tools/orchestrator/README.md:56` | doc-command | Preserve reference and interface |
| `tools/orchestrator/README.md:57` | doc-command | Preserve reference and interface |
| `tools/orchestrator/README.md:57` | doc-script | Preserve reference and interface |
| `tools/orchestrator/README.md:58` | doc-command | Preserve reference and interface |
| `tools/orchestrator/README.md:58` | doc-script | Preserve reference and interface |
| `tools/orchestrator/README.md:59` | doc-script | Preserve reference and interface |
| `tools/orchestrator/README.md:59` | doc-command | Preserve reference and interface |
| `tools/orchestrator/README.md:106` | doc-script | Preserve reference and interface |

### check.sh

Reported sites: 0. Query exit code: 1.

No indexed reference sites were returned. Preserve the filename and existing interface.


## Documentation review correction

The separate reviewer identified inaccurate long-form inventory and voice-profile wording. The master also reported that the initial repository gate rejected the README command example in the documentation index. This correction documents the current Shorts workflow, the empty long-form destination with format documentation, the channel voice-profile path, and the registered workers command. No behavior repair is included.

Correction impact evidence: `/tmp/frameforge-rename-review/impact-before-review-correction.json`. Exact preceding documentation is saved under `/tmp/frameforge-rename-review/review-correction-originals/`.

All reported sites below retain their existing paths and interfaces. The README query includes other files with the same basename; those references are preserved.

### Review correction trace: README.md

Reported sites: 29. Query exit code: 0.

| Reported site | Kind | Planned disposition |
| --- | --- | --- |
| `GEMINI.md:349` | doc-asset | Preserve reference and interface |
| `README.md:18` | doc-asset | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:78` | doc-asset | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:156` | doc-asset | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:174` | doc-asset | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:175` | doc-asset | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:406` | doc-asset | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:407` | doc-asset | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:408` | doc-asset | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:409` | doc-asset | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:410` | doc-asset | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:411` | doc-asset | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:412` | doc-asset | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:413` | doc-asset | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:414` | doc-asset | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:415` | doc-asset | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:416` | doc-asset | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:417` | doc-asset | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:418` | doc-asset | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:419` | doc-asset | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:420` | doc-asset | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:421` | doc-asset | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:422` | doc-asset | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:423` | doc-asset | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:424` | doc-asset | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:425` | doc-asset | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:426` | doc-asset | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:427` | doc-asset | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:428` | doc-asset | Preserve reference and interface |

### Review correction trace: docs/reports/2026-11-02-rename-ledger.md

Reported sites: 0. Query exit code: 1.

No indexed reference sites were returned. Preserve the filename.

### Review correction trace: workers

Reported sites: 8. Query exit code: 0.

| Reported site | Kind | Planned disposition |
| --- | --- | --- |
| `docs/reports/2026-11-02-rename-ledger.md:127` | doc-script | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:128` | doc-script | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:129` | doc-script | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:130` | doc-script | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:282` | doc-script | Preserve reference and interface |
| `docs/reports/2026-11-02-rename-ledger.md:283` | doc-script | Preserve reference and interface |
| `tools/orchestrator/README.md:26` | doc-script | Preserve reference and interface |
| `tools/orchestrator/cli.py:265` | subcommand-declared | Preserve reference and interface |

