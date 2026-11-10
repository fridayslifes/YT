# Short 13 release proposal — 2 November 2026

**Status: awaiting approval of corrections.** Proposal only; no production files, uploads, comments, likes, or deletions changed.

## Current evidence and blockers

The master's media inspection reports a 48.9-second, 1080×1920, 30 fps H.264 MP4 with AAC audio at 48 kHz, approximately 86.6 MB. These technical properties do not establish factual accuracy. The current hook scores **57/100**, below the **70** gate. There is no verified Dunning–Kruger dossier, and `project.json` lacks `citation_verified`. That flag must follow evidence review, not substitute for it. The project title and upload-kit title disagree; the uploader reads the kit.

Evidence sources: [Kruger and Dunning's original 1999 paper](https://gwern.net/doc/psychology/1999-kruger.pdf), especially printed pages 1121, 1126–1131; [PubMed record and abstract](https://pubmed.ncbi.nlm.nih.gov/10626367/). Distinguish three categories: the paper's experimental findings; the Wheeler newspaper anecdote it recounts; and our editorial suggestion. The anecdote is not experimental evidence. Universal claims about certainty or experts exceed this study's findings.

## Errors and proposed corrections

Line references below describe the files inspected before any proposed edits. “Project” means `shorts/short_13_dunning_kruger/project.json`; “kit” means its `UPLOAD_KIT_SHORT_13.md`.

| Current issue | Proposed correction |
| --- | --- |
| Project line 3 versus kit line 39: different titles; kit uses uppercase `#Shorts` | Use the approved public title consistently, retain `SH-13` as the internal ID, and use lowercase `#shorts`. |
| Project lines 36 and 48; kit lines 53–55: dramatized quotation and claim that the heist caused the research | Qualify the anecdote as reported, remove the embellished quotation, and say the paper opens with the story. Label visuals as illustrative reenactments. |
| Contact-sheet scene 3 labels photorealistic researchers “DAVID DUNNING,” implying an authentic likeness | Prefer a neutral paper/laboratory visual. If retaining generated people, label them **ILLUSTRATIVE RESEARCHERS**, remove identity labels from faces, and keep the paper citation separate. |
| Project lines 60–63; kit line 57: “bottom twelfth percentile,” plus `%` attached to percentile labels | Describe the lowest-scoring quarter and its average rank. Card: **12th vs 62nd percentile**; subtitle: **Bottom quartile: average actual vs estimated rank**. |
| Project lines 75 and 87; kit line 57: universal certainty and expert self-doubt; contact-sheet scene 5 says “INCOMPETENCE” | Use the narrower findings below; replace the stigmatizing scene-5 overlay with **CHECK YOUR ESTIMATE**. |
| Project line 88 and contact-sheet scene 6 cite “The False Consensus Effect (Ross et al.)” | Replace the visual citation with **Kruger & Dunning (1999), Study 3** to match the narration. Retaining Ross requires separate source verification. |
| Project line 99; kit lines 45 and 59: instant cure/diagnostic exercise; scene 7 says “THE FIVE-SECOND” | Remove those promises; use **PREDICT, THEN CHECK** on scene 7 and separate the training finding from the editorial exercise. |
| Contact-sheet scene 8 says “IN JUICE,” a callback absent from the revised close | Replace with **CHECK THE EVIDENCE**, matching the closing message. |
| Kit line 66: “Focus Architecture OS” resource promise | Omit unless its destination and availability are independently verified. Confirm the related video before retaining its call to action. |
| Kit lines 76 and 80–81: invites labeling others and promises an algorithmic boost from rapid replies | Replace with optional self-reflection; remove unsupported ranking claims and scripted funnel replies. |
| `tools/upload_api.py:401` and `tools/upload_api.py:424`: automatic creator comment and like | Use a reviewed upload-only path or approve a scoped uploader change first. Neither action is authorized merely by asking to upload. |

## Exact proposed narration

Reuse the existing scene positions and visual assets where compatible; regenerate timing and captions.

1. **Bank exterior:** Before you trust your confidence: McArthur Wheeler robbed two banks wearing lemon juice. What did he miss?
2. **Surveillance footage:** He reportedly thought cameras could not see his face.
3. **Illustrative researchers or neutral paper visual:** Kruger and Dunning opened their 1999 paper with that story.
4. **Student/stat card:** In their studies, the lowest-scoring quarter averaged the 12th percentile, but estimated the 62nd.
5. **Confident speaker:** They tested humor, grammar, and logic. Their explanation: limited skill can also make errors harder to recognize.
6. **Contemplative scientist:** High scorers sometimes underestimated their relative standing, partly because they overestimated how well their peers performed.
7. **Thinker:** Training improved self-assessment in their experiment. My practical suggestion: predict your performance, then compare it with feedback.
8. **Mirror:** Feeling certain does not prove you are right. Subscribe for the next blind spot.

The draft has **116 regex-counted words**, approximately 46 seconds at 150 words/minute; hook **79/100** with the current scorer. This heuristic is not audience-retention evidence. Independently inspect **all eight scenes** against `/tmp/frameforge-sh13-contact.png` and the approved narration: imagery, every overlay/citation/card, baked-in text, captions, and spoken timing. No stale cure language, callback, or implied researcher likeness may survive the rebuild.

## Upload-kit replacement plan

Proposed title: **Dunning-Kruger: Why 12th Felt Like 62nd**. The current `tools.youtube_skills.title.check` reports **39 characters, 100/100, no issues**. “Felt like” summarizes estimated rank; the description and scene 4 must clarify that these are averages for the lowest-scoring quarter, not percentages or every individual's result. Put lowercase **#shorts** in the description.

Replace the description with scenes 3–6's findings, both source links, anecdote/reenactment disclosure, and the exercise's editorial status. Remove cure/resource/reach promises and uppercase hashtags. Optional comment, separately approved: **“When has feedback changed your estimate of your own skill?”** Never post automatically.

For these photorealistic AI reenactments, propose **`status.containsSyntheticMedia: true`** in the upload request; the current uploader omits it. [Official `videos.insert` documentation](https://developers.google.com/youtube/data/reference/rest/v3/videos/insert) explicitly supports this field. Verify the saved value through the API or Studio; an omitted response field means unknown, not false. Correct the tracker's stale claim that the API cannot set disclosure.

## Execution order and independent gates

**Implementation prerequisite, not currently runnable:** add a master **release-existing** CLI workflow in `tools/orchestrator/cli.py` and `tools/orchestrator/workflows.py`, with an upload-only publisher in `tools/orchestrator/workers.py`. It imports reviewed artifacts, runs research/script/project/render/packaging/consistency checks, and never regenerates content. Implementation requires approval and independent review before Short 13 can use it.

Concrete proposed command, represented as argument tokens to identify the future interface:

```json
[".venv/bin/python", "tools/master.py", "release-existing", "--project", "shorts/short_13_dunning_kruger/project.json", "--evidence", "<approved-evidence-bundle.json>", "--privacy", "unlisted", "--publish", "--yes"]
```

Omitting `--publish` and `--yes` must run validation only. Mock gates must reject missing evidence, stale hashes, wrong channel, and failed checks before insertion; success/resume/lost-response/tracker-failure tests must prevent duplicate inserts, comments, and likes, and assert synthetic disclosure. Live preflight is read-only until all gates pass.

1. **Researcher → reviewer:** prepare the sourced dossier and claim-to-source ledger; independently review every narration, overlay, title, and description claim. Approve corrections before a builder edits production files.
2. **Builder → separate verifier:** apply approved content changes; rebuild narration, captions, scene timing, and MP4. Inspect every scene's text and visuals, including the scene 3 depiction and scene 7/8 overlays; check audio/video, caption fidelity, cuts, readability, and stream properties. Run the master release checks and `./check.sh`; resolve failures before upload.
3. **Publisher preflight:** use the implemented, independently tested workflow above. Verify authenticated channel ID against Cognitive Core, inspect existing uploads and tracker, and bind approval to final media/metadata hashes. Persist the returned video ID immediately; reconcile ambiguous outcomes instead of creating duplicates.
4. **Upload:** unlisted upload is already authorized, once the approved repairs and gates pass. Disable automatic social actions. Independently confirm video ID, owning channel, processing result, metadata, and unlisted status, then inspect playback. Public release is a subsequent step after inspection and confirmation of visibility preference.
5. **Cleanup:** only after confirmed upload, delete the two local project directories for Shorts 13 and 16; never delete YouTube videos. Preserve upload receipts outside those directories. Update affected references and tests first, then rerun the index and `./check.sh`. Record exact logical and allocated bytes before removal and measured storage reclaimed afterward. No bytes have been freed by this proposal.

## Change propagation evidence

Before writing, `impact --path` was run for the project, kit, dossier, uploader, tracker, and both directory paths. It returned 3 generic project-DAG matches, 4 dossier references, and 8 uploader references. Other queries returned no matches/exit 1; directory references are incompletely indexed.

The workflow revision additionally traced the CLI, workflows, and workers modules: 4, 4, and 13 indexed sites respectively. These span the general design, rename ledger, impact tests, orchestrator README, and CLI worker listing. The proposed `release-existing` name has no indexed implementation.

Supplemental `rg` found cleanup-sensitive sites in `CONTENT_TRACKER.md`, `GEMINI.md`, `channel_assets/YOUTUBE_API_GUIDE.md`, `tests/test_fidelity.py`, `tests/test_project_contract.py`, `tests/test_tracker_schema.py`, uploader CLI help, and the rename ledger. Preserve historical receipts, replace active missing-file references, and move regression coverage to self-contained fixtures. The uploader's eight sites include its API guide, optional requirements, tracker tests, legacy agents, orchestrator worker, and pipeline imports. Every affected site must agree before completion.
