# FrameForge

FrameForge is the local and cloud video-production workspace and Python toolset. Its built-in production workflow creates research-grounded YouTube Shorts and long-form videos using the channel preset in `configs/channels/default.yaml` (`FrameForge Studio` / `@FrameForgeStudio` until configured for a live YouTube channel).

The `shorts/` and `long_form/` directories are prepared format destinations and currently contain only documentation, with no active local project. Broader format and channel-neutral production workflows remain proposed.

## Working here

The canonical project directory is `/Users/friday/Desktop/FrameForge`.

Use the master orchestrator for production workflows. From the project directory, list the registered workers and run the repository gate with:

```bash
.venv/bin/python tools/master.py workers
./check.sh
```

[AGENTS.md](AGENTS.md) defines delegation, approval, and release gates. [The orchestrator guide](tools/orchestrator/README.md) describes the supported workflows. [GEMINI.md](GEMINI.md) records the workspace production standards.

## Workspace contents

- `tools/` contains the production pipeline, rendering tools, and orchestrator.
- `shorts/` and `long_form/` currently contain format documentation; no local video projects are retained.
- `channel_assets/` holds the channel voice profile (`channel_assets/voice.md`), research dossiers (`channel_assets/scientific_dossiers.json`), and policy ledger.
- `configs/channels/default.yaml` holds the configurable channel identity and narration defaults.
- `CONTENT_TRACKER.md` tracks the channel's videos.
- `.venv/` contains the single project Python virtual environment.

## Compatibility path

`/Users/friday/Desktop/Yt` is not present in this workspace. Use `/Users/friday/Desktop/FrameForge` for commands and update any external launcher that still points to the old path. Pipeline module names, commands, channel branding, and video assets retain their existing roles.
