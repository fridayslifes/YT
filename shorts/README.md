# Shorts Production Directory (`9:16`)

This directory houses all YouTube Shorts projects for **Cognitive Core** (`@CognitiveCoreOfficial`).

---

## 1. Directory Structure & Naming Standard

All short folders follow zero-padded numbering to ensure chronological filesystem sorting:
`short_<01..99><optional_letter>_<slug>/` (e.g., `short_01_doorway_effect`, `short_01b_doorway_part_2`, `short_02_attention_residue`).

```
shorts/
├── short_01_doorway_effect/
│   ├── project.json            # Scene script, camera motions, overlays, notes
│   ├── images/                 # 9:16 cinematic visuals (no flat grids)
│   ├── cache/                  # Edge TTS / Kokoro cache
│   ├── output/                 # Rendered MP4, SRT subtitles, cover image
│   └── UPLOAD_KIT_SHORT_1.md   # Titles, description, pinned comment, tags
...
```

---

## 2. Standards & Verification

- **Format**: `1080×1920` (9:16 vertical HD), 30 FPS.
- **Length**: 105–155 spoken words, which is the band `tools/pipeline.py` enforces. The technical render floor is 5 seconds; there are no retained Short renders in this repository to measure.
- **Quality Gate**: Run `python tools/pipeline.py --verify-all`, then `./check.sh` (ruff, compileall, pytest and the change index).
- **Preview frame**: YouTube picks it from the video. This pipeline generates no thumbnail image, so the hook has to land in the first frames and the on-screen banner.
- **Related Video**: Always route to the current anchor long-form video (e.g. `LV-01`) via YouTube Studio.
- **Tracker**: Always maintain `CONTENT_TRACKER.md` at the project root.
