# FrameForge

FrameForge is a local and cloud video-production workspace and Python toolset. Its built-in production workflow creates fact-checked YouTube Shorts and long-form videos using the channel preset in `configs/channels/default.yaml` (a neutral `Your Channel` / `@yourchannel` template until configured for a live YouTube channel). Factual claims are verified against a verified study or live web research; fiction (invented stories, novels, skits) is exempt from fact-checking.

## Fact-checking

Every video declares `content_type` (`factual` or `fiction`, default `factual`). The `factcheck` gate runs after a project is assembled and before rendering: factual claims must be grounded in a verified dossier or corroborated by live web research (Exa), and an unverified claim blocks the render. Fiction is exempt. Live web verification needs `EXA_API_KEY` in the environment; without it a factual check fails closed with the fix command.

```bash
.venv/bin/python tools/master.py fact-check --project shorts/<slug>/project.json
.venv/bin/python tools/master.py produce --topic "..." --id SH-01 --slug short_01 --channel default --content-type fiction
```

## Working here

Run all commands from the repository root. Use the master orchestrator for production workflows; list the registered workers and run the repository gate with:

```bash
.venv/bin/python tools/master.py workers
./check.sh
```

[AGENTS.md](AGENTS.md) defines delegation, approval, and release gates. [The orchestrator guide](tools/orchestrator/README.md) describes the supported workflows. [GEMINI.md](GEMINI.md) records the workspace production standards.

## Workspace contents

- `tools/` contains the production pipeline, rendering tools, and orchestrator.
- `configs/` holds encoder settings, uniqueness thresholds, and channel presets (`configs/channels/`).
- `assets/` holds shared fonts, emoji plates, and sound cues.
- `channel_assets/` holds local-only channel data: voice profile, research dossiers, policy ledger, and upload receipts (gitignored).
- `CONTENT_TRACKER.md` is the local-only video inventory (gitignored).
- `.venv/` contains the single project Python virtual environment.

## Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

`ffmpeg` and `ffprobe` must be on PATH. Blender is optional (true-3D camera paths); without it the pipeline renders 2.5D parallax. Local Kokoro-82M ONNX weights live in `tools/kokoro_models/` (gitignored; see requirements-optional.txt).