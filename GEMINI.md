# FrameForge Production, Visual & Monetization Standards (Cognitive Core preset — v4.0 SOTA Engine)

Always adhere strictly to these rules before producing, modifying, or uploading any YouTube video (Short or Long-Form) in this workspace.

---


---

### ⚠️ MANDATORY RULE: STRICT LOCAL KOKORO-82M NEURAL AUDIO (NEVER CLOUD TTS)
- **STRICT PROHIBITION**: Never use Microsoft Edge-TTS, Azure Cloud TTS, or external voice APIs.
- **MANDATORY AUDIO ENGINE**: All voiceover synthesis across the workspace, pipeline, and universal engines MUST run strictly and exclusively on the local **Kokoro-82M ONNX** neural model (`tools/kokoro_models/kokoro-v1.0.onnx` + `voices-v1.0.bin`).
- **HOUSE BLEND**: The default channel narrator is the custom vector blend of `am_adam` (68%) and `bm_george` (32%), processed through the Shure SM7B studio EQ and dynamic mastering chain.
- **IMMUTABLE POLICY**: This audio engine is permanently locked. Under no circumstances should any agent switch to cloud voice APIs.

### 0. Complete 0-to-1 Video Creation & Upload Workflow (End-to-End Multi-Agent Guide)

Legacy production flags in `tools/agents.py` and `tools/pipeline.py` are compatibility front ends to the canonical master workflow in `tools/orchestrator/`:

0. **Canonical Production Workflow (legacy-compatible commands)**:
   ```bash
   # Create a blueprint through the canonical research, script, project, and verification workers:
   python tools/pipeline.py --topic "Loss Aversion" --id SH-15 --slug short_15_loss_aversion --genre cinematic_35mm --agents

   # Full production and release checks through the same master workflow:
   python tools/pipeline.py --topic "The Simulation Argument" --id SH-16 --slug short_16_simulation_argument --genre 3d_cgi --auto

   # Audit or upgrade all existing unrendered blueprints in place:
   python tools/pipeline.py --upgrade-blueprints
   ```

1. **Step 1 — Initialize Project & Upload Kit**:
   ```bash
   python tools/pipeline.py --topic "Loss Aversion" --id SH-15 --slug short_15_loss_aversion
   ```
   - Creates `shorts/<slug>/project.json`, `UPLOAD_KIT_<ID>.md`, and `images/`, `videos/`, `output/`, `cache/` folders.
2. **Step 2 — Script & 6-Layer Scene Design (`project.json` & `tools/visual_director.py` v6.0)**:
   - Write an 8–12 scene script (`105–155 words` for a 38–52s Short; `1,100–1,500 words` for an 8–12 min Long-Form video).
   - **End on one ask.** The last scene names a single action the viewer can take inside YouTube — subscribe, the next video, a comment — before the loop tail. `pre_compose_validate()` warns when the closing two scenes contain no ask; 17 of the 18 scripts on this channel today ship an aphorism and never ask for anything, which is why a finished Short converts a watch into nothing. Keep the `…` loop tail if the ask is the fragment that loops (`…and subscribe for Part 3.`), but the ask has to be in there.
   - Ensure every scene changes visual angle every `2.5s–3.8s` and wraps key words in `*asterisks*` for animated genre-palette pill emphasis.
   - Upgrade or synthesize 6-layer story-grounded prompts (`[Shot Scale & Angle] + [Subject, Age & Wardrobe] + [Action & Experiment Props] + [Era & Setting] + [Lighting & Mood] + [Optics & Safe-Zone]`):
     ```bash
     python tools/visual_director.py --project shorts/<slug>/project.json --inplace
     ```
3. **Step 3 — Generate Dynamic Motion Clips & Mastered MP4 (Never Static Slideshows)**:
   - **Standard 2.5D Photorealistic / DepthFlow Pipeline**:
     ```bash
     python tools/pipeline.py --build shorts/<slug>/project.json
     ```
     *(Automatically generates FLUX images in `images/`, renders 2.5D Depth-Anything-V2 parallax motion clips into `videos/s01.mp4`..., synthesizes studio narration, mixes genre-specific `0.18` BGM + `0.12` warm Foley SFX, styles captions dynamically from `color_palette`, encodes 14 Mbps H.264 MP4 + cover frame + SRT, and updates `CONTENT_TRACKER.md`.)*
   - **Standalone 3D Studio Camera Trajectories (Optional)**:
     ```bash
     python tools/studio_3d.py --image shorts/<slug>/images/s01.jpg --preset vertigo -d 3.5 -o shorts/<slug>/videos/s01.mp4
     ```
4. **Step 4 — Pre-Upload Quality Gate Verification**:
   ```bash
   python tools/pipeline.py --verify-all
   ```
   - Checks Reference Precision & Recall across both `shorts/` and `long_form/` projects: word-caption alignment, image sharpness, safe-zone salience, optical-flow motion, and 1080×1920 @ 30fps / 48kHz AAC stream compliance (distinguishing rendered `[PASS]` videos from pre-render `[BLUEPRINT]` projects).
5. **Step 5 — Reviewed YouTube Release & Tracker Update**:
   - **Validate the reviewed project and evidence before upload**:
     ```bash
     python tools/master.py release-existing --project shorts/<slug>/project.json --evidence path/to/reviewed-evidence.json
     # After explicit upload authorization:
     python tools/master.py release-existing --project shorts/<slug>/project.json --evidence path/to/reviewed-evidence.json --publish --yes
     ```
     *(The uploader uses Google's YouTube Data API v3 with chunked resumable transfer and a durable receipt. It verifies the channel, privacy, and remote video identity, then updates `CONTENT_TRACKER.md`. It does not post comments or other engagement actions. Compatibility commands `tools/pipeline.py --upload` and `--upload-api` require the same `--evidence` and `--yes` and run this strict release.)*
   - **Live Channel Stats & Views Synchronization**:
     ```bash
     python tools/pipeline.py --sync-stats
     ```
     *(Fetches live views, likes, and subscribers in 2 seconds directly via YouTube Data API and updates `CONTENT_TRACKER.md`).*

---

### 1. Mandatory Pre-Production Research & Zero-Placeholder Rule
- **Never generate scripts in a vacuum**: Ground every topic in (1) a visceral 2nd-person real-life symptom (`"You..."`), (2) a verified scientific study, researcher, year, and quantitative stat, and (3) a punchy 5-second behavioral reset.
- **The Citation Contract (machine-enforced since v4.1)**:
  - Every `project.json` carries `science` (researcher + year exactly as the channel will cite it on camera), optional `citation_stat` (a number the study really reported), and `citation_verified` (`true` only when the claim has been matched to the paper).
  - `tools/creative_engine.py` **raises `MissingDossier`** for any topic with no entry in `channel_assets/scientific_dossiers.json`. It no longer invents one. Add the real study; do not restore the fallback.
  - On-screen telemetry cards and description stats render **only** from `science` / `citation_stat`. No citation means **no card** — never a placeholder institution. Headline copy must not contain a number that `citation_stat` does not support.
  - `quantitative_stat` must be the study's own figure. A trilemma, ratio or effect size must not be dressed up as a percentage of people.
- **Strict Zero-Placeholder ("No Hidden Holders") Rule**:
  - **NEVER leave silent dummy links** (such as `https://amzn.to/example`) or wrong handles (`@CognitiveCoreHQ`) inside copy-paste descriptions or Upload Kits.
  - Always use the verified channel handle **`@CognitiveCoreOfficial`** (`https://www.youtube.com/@CognitiveCoreOfficial`).
  - If an Upload Kit includes an optional slot for an external affiliate link or Notion template URL that the creator must supply, **do not put a fake URL in the copy-paste block**. Instead, keep the copy-paste block 100% ready to publish as-is, and place a clearly labeled **`⚠️ CREATOR PLACEHOLDER NOTICE`** box above or below telling the creator exactly what optional link they can swap in.

---

### 2. Visual & Motion Quality Standards (Zero Static Images)
- **Every Scene Must Be a Dynamic Motion Video (`videos/*.mp4`)**:
  - Never render a video that looks like a static image slideshow. Every scene (`s01`–`s12`) must be rendered into an audio-synced `.mp4` motion clip via `tools/visual_engine.py` before final assembly:
    - **Cinematic Documentary Format (Default)**: Full-bleed `9:16` (`1080×1920`) photorealistic 35mm scenes converted into **2.5D Depth-Anything-V2 Parallax**, **3D DepthFlow GLSL Camera Moves**, or **Multi-Plane Foreground/Background Hybrid CGI** clips (`0.5–25 px` optical flow). Never use flat 2D grids or simple geometric charts on documentary videos.
- **Safe-Zone Composition (`1080×1920` Vertical)**:
  - Keep primary visual subjects centered between **30% and 58% vertical height** so focal points are never covered by:
    - Top `16%`: Dynamic hook banner (`overlay`) and YouTube account header.
    - Height `27%`: Study citation badge (`note`).
    - Height `40%`: Frosted glassmorphic stat card (`stat_card`).
    - Height `63%`: Word-by-word Remotion spring-animated pill captions.
    - Bottom `20%` & Right Edge: YouTube Shorts UI buttons (Like, Comment, Remix, Sound).

---

### 3. Audio Engineering, TTS & Render Standards (`tools/build_video.py` v4.0 & `tools/audio_bank.py` v5.0)
- **Studio Ribbon-Mic TTS Narration**:
  - Primary voice: `en-US-AndrewNeural` (or local `Kokoro-82M` neural blend `am_adam` + `bm_george` fallback) at **`rate: "+1%"`** and **`pitch: "-2Hz"`** (`gap: 0.08s`).
  - Processed through the warm Shure SM7B / Studio Ribbon EQ & dynamics chain:
    `highpass=f=65,equalizer=f=135:t=q:w=1.1:g=+2.4,equalizer=f=2400:t=q:w=1.4:g=+0.8,equalizer=f=3400:t=q:w=1.6:g=-1.6,lowpass=f=13500,deesser=i=0.6:m=0.4:f=0.5:s=o,acompressor=threshold=-16dB:ratio=2.0:attack=15:release=160,alimiter=limit=-1.2dB`
- **Rich Audible BGM (`0.18`) with Mid/Side Vocal Pocket Ducking**:
  - Background music volume defaults to **`0.18`** (upgraded from the old `0.08` which was too quiet on mobile speakers).
  - During active speech, `mix_audio()` carves a **34% Mid-channel vocal pocket** (`mid_duck`) while keeping **90% of the Side-channel stereo warmth** (`side_duck`), so the music feels full and impactful without masking the voice.
- **Warm Non-Tonal Studio Foley SFX (`0.12`)**:
  - SFX volume defaults to **`0.12`** using `tools/audio_bank.py` v5.0 (`assets/audio/sfx/`):
    - `whoosh.wav`: 100% non-tonal 3-stage low-passed brown noise + `50Hz` felt sub-thud on scene cuts (zero high-pitched sine whistle).
    - `boom.wav` / `shutter.wav` / `chime.wav` / `pop.wav`: Warm low-frequency cinema sub-bass and mechanical film transients.
- **Master Loudness & Video Encoding**:
  - Final broadcast loudness normalized to **`-14 LUFS`** (`loudnorm=I=-14:TP=-1.5:LRA=11`), `48kHz` stereo AAC (`320 kbps`).
  - Video encoded via Apple Silicon `h264_videotoolbox` at **`14 Mbps`** High Profile (`1080×1920` for Shorts, `1920×1080` for Long-Form, `30 fps`, BT.709 color space).

---

### 4. Algorithmic Retention, Pacing & Structure Rules
- **Beat the 3-Second Swipe Gate (70%+ Viewed Target)**:
  - Open immediately in 2nd-person visceral action (*"If you collapse on a busy sidewalk..."* or *"You stare at..."*).
  - Activate the top hook banner for the first `2.4s–2.6s` (`overlay: {"text": "HOOK TITLE", "until": 2.6}`).
- **Proportional Visual Pacing (The 3.5-Second Cut Rule)**:
  - Never hold a single static shot for more than `3.5–4.0 seconds`.
  - Use **8–10 scenes** for `30–38s` Shorts and **10–12 scenes** for `42–55s` Shorts.
  - Alternate camera motions (`punch` $\rightarrow$ `zoom_in` $\rightarrow$ `pan_up` $\rightarrow$ `zoom_out` $\rightarrow$ `drift_left` $\rightarrow$ `drift_right`).
- **Seamless Infinite Replay Loop**:
  - End the final scene with a mid-thought loop bridge (*"...which explains why..."*) and `"pause": 0.0` so the Short replays seamlessly.
- **Standalone Sister Titles**:
  - Never put `"Part 2"` in a video title; give sequel Shorts standalone curiosity titles and bridge them via Pinned Comments and Related Video links.

---

### 5. Mandatory Content Tracking (`CONTENT_TRACKER.md`) & Upload Kit (`UPLOAD_KIT_*.md`) Rules
1. **Master Table Columns (`CONTENT_TRACKER.md`)**:
   - Every entry in Section 2 of `CONTENT_TRACKER.md` must include: `ID`, `Format`, `Title & Topic`, `Scientific Grounding`, `Live YouTube Link & ID`, `Output File`, `Upload Kit`, `Status`, `Views`, and `Related Video Target`.
   - Never mark a video `**Ready**` in `CONTENT_TRACKER.md` until its final `.mp4` exists in `output/` and passes `verify_rendered_mp4()`. If rendering was paused mid-way, mark it `**Paused (Scenes X–Y Built)**`.
2. **Strict YouTube Studio Metadata Rules**:
   - **The Strict Lowercase `#shorts` & Tags Rule**:
     - Always use **`#shorts`** (strictly lowercase, NEVER `#Shorts` or `#SHORTS`) across all Shorts titles, descriptions, and hashtags. Never include `#shorts` in a `16:9` Long-Form video title.
     - **All Search Tags Must Be Strictly Lowercase**: All keywords and tags must be 100% lowercase without capital letters (e.g. `bystander effect, darley and latane 1968, cognitive core, deep work`).
   - **AI & Synthetic Media Disclosure**:
     - If YouTube auto-flags a video as **`Yes [Set by YouTube]`**, **leave it as Yes**.
     - During manual upload: select **`Yes`** for photorealistic 35mm human scenes (`SH-01`–`SH-13`, `LV-01`, `LV-02`), and **`No`** for non-photorealistic stylized animations.
   - **YPP State Awareness (Pre-Monetization)**:
     - Do not instruct placing manual mid-roll ads while the channel is below YPP thresholds (`1,000 subs + 4,000 watch hours`).
   - **Live-Inventory Rule for Cards & End Screens**:
     - Only recommend Info Cards, End Screens, or Related Video links to videos already marked **`Uploaded`** in `CONTENT_TRACKER.md` (such as `LV-01`, `LV-02`, and `SH-01`–`SH-10`). Never tell the creator to link a card to a video still marked `Pending Upload`.
   - **Exact Timestamp Fidelity**:
     - Long-Form chapter timestamps and End Screen windows in `UPLOAD_KIT_*.md` must match the actual rendered `.srt` / `.mp4` duration.
3. **Humanized Upload Kit & Top Notice Standard (SOTA 2026)**:
   - Every `UPLOAD_KIT_*.md` must open with a prominent **`⚠️ UPLOAD-TIME ACTION & VALUE VERIFICATION NOTICE`** banner explicitly separating hardcoded global defaults from dynamic per-upload values that require verification or swapping.
   - Descriptions must use authentic human creator phrasing (banning corporate AI buzzwords like *delve, tapestry, testament, landscape, realm, game-changer* and capping hashtags at 3–4 maximum).
   - Every kit must include the complete 11-Setting YouTube Studio checklist (Shorts Remixing permissions, Standard YouTube License, Language/Caption cert, Playlist mapping, Related Video linking, AI disclosure, and Golden-Hour first-hour velocity plan).

---

### 6. Integrated YouTube Skills & Heuristics CLI (Pre-Production & Retention Engine)
The complete `youtube-agent-skill` suite is natively integrated into both the Antigravity agent environment and the local pipeline (`tools/pipeline.py` & `tools/youtube_skills/`):

- **Spoken Hook Scorer (`--hook`)**:
  ```bash
  .venv/bin/python tools/pipeline.py --hook "If you collapse on a busy sidewalk, why do 85% of people walk past you?"
  ```
  Evaluates 5 properties (Specificity, Address, Stakes, Curiosity, Brevity) against 21 hook formulas. Verdict $= 60\%$ mean $+ 40\%$ mean of the two weakest properties, and any property below `LEAK_FLOOR` (30) caps the verdict at 69 so a hook with one dead property cannot print `STRONG`. Bands: `WEAK < WORKABLE_MIN (48) ≤ WORKABLE < STRONG_MIN (70) = STRONG`; `STRONG_MIN` is the single pass mark the repo gates on (`orchestrator/verifiers.py` defaults `hook_min` to it, `output_format._hook_display` colours from the band rather than its own literals, `pipeline.py` warns below `WORKABLE_MIN`). Automated during `pipeline.py --build` and `pipeline.py --verify-all`.
  - **The calibration is measured, not claimed**: `python3 tools/youtube_skills/hookscore.py --calibrate` re-derives it from `hooks.json` (21 worked examples) against `hook_controls.txt` (10 dead hooks) and exits non-zero if a dead control ever reaches `WORKABLE` or the two populations stop separating. `WORKABLE_MIN` sits above the control ceiling for that reason.
  - **What a verdict is worth**: on this channel's own 14 Shorts the hook verdict has **no measurable relationship with views** (Spearman $\\rho = +0.05$, and cumulative views are further confounded by video age). Use the scorer to rank your five options against each other, never to predict an outcome. Topic recognisability and the replay loop have moved these numbers, not hook wording.
- **Title Linter (`--lint-package`)**:
  ```bash
  .venv/bin/python tools/pipeline.py --lint-package --title "Why 85% of People Walk Past Someone in Danger"
  ```
  Detects mobile ($40$ char) and desktop ($60$ char) truncation, shouting, vague adjectives, and a missing concrete figure.
- **Transcript Dead Air & Retake Cleaner (`--deadair`)**:
  ```bash
  .venv/bin/python tools/pipeline.py --deadair shorts/<slug>/cache/narration.srt
  ```
  Generates an Edit Decision List (EDL) flagging pauses $>0.45\text{s}$, whole cues containing only filler (*um, uh, basically*), and false starts/repeated takes. Filler within a meaningful sentence is retained for manual review because cue timestamps do not locate individual words. The EDL proposes cuts; it does not edit media.
- **Audience Retention Diagnostics (`--retention`)**:
  ```bash
  .venv/bin/python tools/pipeline.py --retention analytics.csv --transcript narration.srt
  ```
  Ingests YouTube Studio audience retention CSVs, diagnoses first-30s Hook Leak, detects steep cliff drop-offs, correlates drop-off timecodes to exact spoken transcript sentences, and calculates middle slide rate.
- **Strict YouTube Chapter Validator (`--chapters`)**:
  ```bash
  .venv/bin/python tools/pipeline.py --chapters long_form/<slug>/narration.srt
  ```
  Generates chapters based on acoustic pause duration and vocabulary shifts, enforcing YouTube's strict rendering requirements ($00:00$ start, $\ge 3$ chapters, $\ge 10\text{s}$ minimum each).
- **Viral Outlier Discovery (`--swipe`)**:
  ```bash
  .venv/bin/python tools/pipeline.py --swipe collected.json --min-multiple 1.8
  ```
  Ranks niche videos by how far each beat its **own channel's median** rather than vanity subscriber metrics.
- **Channel Voice Profile (`voice.md`)**:
  - Anchored at `channel_assets/voice.md` and mirrored to `~/.gemini/youtube/voice.md` & `~/.claude/youtube/voice.md`.
  - Defines the Shure SM7B tone, 2nd-person visceral perspective, mandatory scientific study grounding, and the corporate AI buzzword blacklist.
- **Antigravity Interactive Slash Commands**:
  - `/yt-script`: Pre-scores 5 hooks against 21 formulas, builds script with `[ON SCREEN: ...]` retention tags.
  - `/yt-package`: Lints a published title for truncation, shouting and vagueness.
  - `/yt-edit`: Creates an EDL from transcript.
  - `/yt-retention`: Pinpoints exact seconds and lines where viewers churn.
  - `/yt-viral`: Identifies outlier ideas in your niche.
  - `/yt-shorts`: Discovers short clips inside long-form videos.
  - `/yt-chapters`, `/yt-seo`, `/yt-comment`, `/yt-plan`, `/yt-audit`.

---

### 7. Unified Branding & Cinema Suite (SOTA 2026)
Automated tools ensuring high mobile CTR and algorithmic retention across both Long-Form and Shorts:

- **Master Channel Icon & Silhouette Builder (`tools/build_avatar.py`)**:
  ```bash
  .venv/bin/python tools/build_avatar.py
  ```
  Generates `avatar_labyrinth_800x800.png` and `.svg` using the Labyrinth-Aperture design with heavy geometric gold arcs (`#FFB300`), electric cyan core (`#00E5FF`), and dual-mode hairline rim. Calibrated and verified for sharp visibility at 32×32 px mobile size (`channel_assets/avatar_contrast_test.png`).

- **Unified Master Cinema Suite (`tools/branding_engine.py` / `pipeline.py --branding`)**:
  ```bash
  .venv/bin/python tools/pipeline.py --branding
  ```
  Renders the complete 4-file broadcast intro & outro package:
  1. `channel_assets/intro_16x9.mp4`: 2.5s Long-Form Stinger with volumetric cyan bloom, chromatic edge dispersion, 45Hz sub-transient + 35mm shutter.
  2. `channel_assets/intro_9x16.mp4`: 2.0s Shorts vertical stinger.
  3. `channel_assets/outro_16x9_endscreen.mp4`: 15.0s YouTube End Screen Master with interactive safe-zone target slots for "Next Recommended Video" and "Subscribe Avatar", with 15s ambient synthesizer drone and vinyl crackle.
  4. `channel_assets/outro_9x16_loop.mp4`: 2.5s Shorts infinite loop bridge.

  Every master is encoded BT.709 limited-range with the channel's loudnorm filter, and
  `branding_engine.run_branding_check()` prints the measured LUFS/dBTP after each render instead of
  restating the target. Measured today: the 15s end screen sits at −14.5 LUFS; the three sub-3s
  stingers stay near −18 because their true peak is already at the −1.5 dBTP ceiling, so loudnorm's
  +4 dB of linear gain is refused. That is a property of a short transient, not a defect to chase.

- **Branding attachment (`build_video.attach_branding`, long-form only)**:
  A master nobody reads is 39 MB of decoration. `project.json` opts a render in:
  ```json
  "format": "long",
  "branding": { "intro": true, "outro": true }
  ```
  The step splices the stinger ahead of the film and the 15s slate behind it with `concat -c copy`,
  shifts the caption sidecar by the intro duration, and refuses to run if the master's codec, size,
  frame rate or colour tags differ from the film, if the output does not decode, or if its duration
  does not equal the sum of the parts. Re-running it on an already-branded file is a no-op, so a
  second pass cannot stack a second slate. **Shorts are refused by design**: a Short's rewatch comes
  from its last frame cutting back to its first, and the feed judges the first frame — a logo ahead
  of the hook and a bridge behind the punchline cost both. `tests/test_branding.py` holds the rule
  that every `long_form` project declares an end screen, because that slate is where YouTube lets a
  subscribe button exist.

- **No thumbnail subsystem.** YouTube selects the feed preview from the video's own frames, so this
  pipeline generates no thumbnail image, uploads none, and gates none. The thumbnail studio, its
  `thumbball` alias, the pipeline's thumbnail flags and the `master.py thumbnails` command were all
  deleted on 2026-11-01, together with the pixel audit board that reported a fabricated exposure and
  contrast score for every plate it measured. What carries a Short's click now is the first second of
  footage and the on-screen caption pill inside the 30%–58% safe band, both set in `project.json` and
  rendered by the build step.

---

### 8. Multi-Genre Visual Director & SOTA 3D Studio (v5.0 Engine)
The workspace supports multi-genre aesthetic direction and real-time GPU-accelerated 3D camera trajectories (`tools/genre_director.py` & `tools/studio_3d.py`):

- **5 Distinct Aesthetic Genres**:
  1. `3d_cgi` (Unreal Engine 5 & Octane 3D raytracing, volumetric caustics, subsurface glow).
  2. `3d_minimalist` (Aperture / Apple spatial design, frosted glassmorphism, floating 3D cards).
  3. `kinetic_explainer` (Vox / Kurzgesagt style, 3D isometric vector shapes, bold geometric depth).
  4. `cyberpunk_neon` (Dark sci-fi, 3D holographic wireframe HUDs, chromatic aberration, glitch).
  5. `cinematic_35mm` (35mm photorealism, Portra 400, soft chiaroscuro, natural depth).

- **SOTA 3D Camera Trajectories (Zero Lag, 70+ FPS on Apple Silicon Metal)**:
  - `depthflow_vertigo` / `vertigo`: Hitchcock Dolly-Zoom (camera dollys in while FOV widens for realization moments).
  - `depthflow_spiral` / `spiral`: 3D Helical camera orbiting around the focal plane while rising.
  - `depthflow_orbit` / `orbit`: 360-degree rotational 3D parallax around centered subjects.
  - `depthflow_roll` / `roll`: Dynamic 3D tilted camera roll with horizontal sweeping pan.
  - `spatial_drift` / `spatial`: Minimalist 3D spatial drift with shifting focal depth planes.

- **Standalone 3D Studio CLI (`tools/studio_3d.py`)**:
  ```bash
  # List all 6 genres, palettes, and BGM profiles
  .venv/bin/python tools/studio_3d.py --list-genres

  # List all SOTA 3D camera trajectories
  .venv/bin/python tools/studio_3d.py --list-presets

  # Render a 3D vertigo camera move on any existing image
  .venv/bin/python tools/studio_3d.py --image input.jpg --preset vertigo -d 3.5 -o output.mp4

  # Generate from prompt in 3D CGI genre and render spiral camera move
  .venv/bin/python tools/studio_3d.py --prompt "Synaptic neural network glowing" --genre 3d_cgi --preset spiral -o brain.mp4

  # Check Blender headless bridge status
  .venv/bin/python tools/studio_3d.py --blender-status
  ```

- **One-Command Multi-Genre Project Creation**:
  ```bash
  # Initialize Short in 3D CGI style:
  .venv/bin/python tools/pipeline.py --topic "The Simulation Argument" --genre 3d_cgi --id SH-16 --slug short_16_simulation_argument

  # Initialize Short in 3D Minimalist / Spatial style:
  .venv/bin/python tools/pipeline.py --topic "Dopamine Fasting" --genre 3d_minimalist --id SH-17 --slug short_17_dopamine_fasting
  ```

---

### 9. S4 Visual Director Engine (Semantic Spatial Scene Synthesizer v5.0)
The visual prompt engine (`tools/visual_director.py`) solves diffusion model spatial binding and eliminates the camera-facing pointing bug:

- **Semantic Script Deconstruction**: Parses spoken narrative text to extract active actors, props, wardrobe, actions, and scene archetypes (`directed_interaction`, `internal_psychology`, `empirical_evidence`, `environmental_hazard`, `ambient_loop`).
- **Lateral Parallel Profile Camera Solver**:
  - Prohibits unconstrained $Z$-axis camera-facing vectors during multi-subject interactions.
  - Enforces a 90° cross-axial profile two-shot: Subject A on Left ($X: 15\%-35\%$) facing right $\rightarrow$ Subject B on Right ($X: 65\%-85\%$) in target wardrobe facing left.
  - Explicit camera gaze negation: *"Neither subject looks at the camera; their line of sight and pointing vector are strictly horizontal across the frame toward each other."*
- **Photochemical Optical Realism (POR-35)**:
  - Permanently bans 2022 AI slop tokens (`UE5`, `Octane render`, `8k`, `hyperrealistic`, `masterpiece`, `cognitive mastery`).
  - Eliminates inline negative tokens that poison T5-XXL attention weights.
  - Enforces authentic 35mm optical camera mechanics (`35mm prime`, `f/2.2`, `Kodak Vision3 500T`, `Portra 400`).
- **Safe-Zone Spatial Bounding**: Strictly centers all primary dramatic action between 30% and 58% vertical height window for 9:16 Shorts.
- **1-Command Project Upgrade CLI**:
  ```bash
  .venv/bin/python tools/pipeline.py --upgrade-blueprints
  ```
  The flag has never taken a path: it walks the blueprint projects and rewrites their scene prompts
  through the S4 visual director in place.

---

### 10. Master Orchestrator (Supervisor + Workers + Verification Gates)

The production control plane lives in `tools/orchestrator/` and is entered through `tools/master.py`. The master plans a task DAG, assigns typed workers, verifies the actual artifacts, blocks dependents on critical failure, and writes a durable report. `tools/agents.py --run`, `tools/pipeline.py --agents`, and `tools/pipeline.py --auto` are compatibility commands that dispatch this same canonical production workflow.

```bash
# Plan a production without touching the GPU
.venv/bin/python tools/master.py produce --topic "Loss Aversion" --id SH-17 --slug short_17_loss_aversion --dry-run

# Research -> script -> project -> render -> release gate
.venv/bin/python tools/master.py produce --topic "Loss Aversion" --id SH-17 --slug short_17_loss_aversion

# Blueprint only (no render)
.venv/bin/python tools/master.py produce --topic "Loss Aversion" --id SH-17 --slug short_17_loss_aversion --blueprint

# Audit the repo, trace a change's blast radius, search code
.venv/bin/python tools/master.py audit
.venv/bin/python tools/master.py impact --all
.venv/bin/python tools/master.py search "def build_and_verify"

# Inspect or resume a run
.venv/bin/python tools/master.py status
.venv/bin/python tools/master.py resume <run_id> --yes
```

**Rules:**
- Research fails closed: no verified dossier in `channel_assets/scientific_dossiers.json` and no `--dossier` means no script. Never synthesize a study, statistic, researcher or year.
- A task passes only if its declared artifacts exist and every critical verifier passes. Warnings do not become success.
- The release gate checks the MP4, packaging, pre-compose state and that the repo carries no dangling reference. Upload requires `--publish --yes`; the master never publishes on its own.
- Run ledgers and reports live in `.orchestrator/runs/<run_id>/` (`run.json`, `events.jsonl`, `REPORT.md`).
- The coding-agent protocol is in `AGENTS.md`; the architecture and extension guide is in `tools/orchestrator/README.md`.


