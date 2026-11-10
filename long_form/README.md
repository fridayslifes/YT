# Long-Form Pillar Videos (`16:9`)

This directory houses full-length anchor videos for **Cognitive Core** (`@CognitiveCoreOfficial`).

---

## 1. Directory Structure per Long Video

Each long-form video should be placed in its own dedicated subfolder following this naming convention:
`lv_<number>_<slug>/` (e.g., `lv_01_core_cognitive_traps/` or `lv_02_focus_protocol/`).

```
long_form/
└── lv_01_core_cognitive_traps/
    ├── project.json            # Scene scripts, visual cues, timestamps, audio spec
    ├── images/                 # Photorealistic / 3D cinematic scenes & B-roll
    ├── cache/                  # Generated TTS audio chunks & voice cache
    ├── output/                 # Final rendered 16:9 MP4 and SRT subtitles
    └── UPLOAD_KIT_LV_01.md     # Complete YouTube metadata, timestamps, and affiliate funnel links
```

---

## 2. Standards & Monetization Funnel Requirements

Per [`GEMINI.md`](../GEMINI.md) and [`VIDEO_GUIDE_SHORTS_AND_LONG.md`](../VIDEO_GUIDE_SHORTS_AND_LONG.md):

1. **Format & Duration**:
   - `16:9` (`1920×1080`), 30 FPS.
   - Target duration: **8–12 minutes** (qualifies for mid-roll ad placements).
2. **Audio & Loudness**:
   - Normalized to `-14 LUFS` (`loudnorm=I=-14:TP=-1.5:LRA=11`).
   - Claim-safe audio (YouTube Audio Library or custom procedural synth).
3. **The Watch-Hour Bridge**:
   - All 9:16 Shorts on the channel point to these pillar videos via YouTube Studio's **Related Video** feature.
   - Long videos harvest watch hours toward YPP thresholds (3,000 / 4,000 hrs).
4. **Description Funnel (Top 2 Lines)**:
   - Clickable lead magnet (e.g. *Cognitive Core Focus & Anti-Procrastination Notion OS*).
   - High-converting affiliate links (Audible / Amazon Associates for cited psychology research).
5. **Exact Timestamps / Chapters**:
   - Complete chapter list starting at `00:00 Intro` in `UPLOAD_KIT_LV_*.md`.
