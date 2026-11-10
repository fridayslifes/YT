---
name: cutout-cartoon-shorts
description: Turn a short script (and optionally a reference picture) into a vertical 2D cartoon Short in the cut-out style of "Can we throw trash in a volcano?" - transparent cut-outs (every pose / expression, props, set pieces), local voiceover (Kokoro-82M ONNX conversational blend), Remotion and Python code that animates it all (2.5D multiplane camera, squash-swap poses, real projectile physics, code effects, cartoon faces on objects), decibel-budget sound effects, and vertical 1080x1920/4K render.
---

# Cut-out cartoon Shorts (Cutout Pictures + Code Animation)

What this makes: a vertical Short (1080x1920 comp, 60 fps / 30 fps) where a flat cartoon character acts out a script with a voice-over. Every character pose and expression is its own picture with a transparent background; the motion, camera, physics, effects, and timing are code.

## 0. Setup
- Remotion project (`src/Root.tsx`, `public/`) or Python/OpenCV 2.5D multiplane compositor.
- Local Kokoro-82M ONNX speech engine (`tools/kokoro_models/kokoro-v1.0.onnx` + `voices-v1.0.bin`) or local voice model.
- Faster-Whisper with `word_timestamps=True` for millisecond-level word timing and RMS silence detection.
- Python 3 with `pillow numpy opencv-python faster-whisper`.
- Local sound synthesis & Foley engine (`tools/sound_architect.py` & `tools/audio_bank.py`).

## 1. Script -> Beat Sheet (Before Generating Anything)
1. Split script into lines. 10–15s Shorts = 4–6 lines, ~25–35 words; 20–30s Shorts = ~50–70 words.
2. Natural, conversational English (*"so"*, *"basically"*, *"right?"*). Zero narrator phrases (*"here's the thing"*), zero hype words (*incredible, shocking, insane*), zero `!` marks.
3. One visual beat per line on the exact word: "throw" = throw, "steam" = steam, "no THANKS" = catch.
4. Frame 0 states the premise (character + object + setting, readable like a thumbnail).
5. As few hard cuts as possible (one continuous camera move is best).
6. One gag per beat (object comes alive, eyes open, anticipation inhale before blast, "> <" eyes, sweat drop).
7. End loops back to frame 0.

## 2. Voice & Word Times
- Natural conversational voice via local Kokoro-82M neural blend (`am_adam` + `bm_george` or conversational preset).
- Faster-whisper word timestamps. Detect real pauses by loudness (RMS below -42 dB for >= 0.18s).
- Place voice at 0.1s and define every beat as a constant: `T = {turn: 2.05, release: 3.7, land: 4.8, ...}`.
- Big sounds (explosions, climax impacts) go strictly into a speech pause, not over words.

## 3. Pictures & Transparent Cutouts
- Fixed style prompt for characters (`STYLE_CHAR`) and objects (`STYLE_OBJ`).
- Clean vector-like linework, flat colors, no texture, no text, no border.
- Isolated on a fully transparent background.
- Check every cutout on a colored background sheet (`qa/sheet.png`) before using it.
- Auto-key opaque backgrounds if needed using flood-fill and 3px un-blended edge.

## 4. Prep: Trim, Measure, Align (`tools/sprite_aligner.py`)
- Trim each PNG to its alpha box + 12px.
- **HEAD Detection**: Largest inscribed disc of the hole-filled silhouette via `cv2.distanceTransform(solid, cv2.DIST_L2, 5)`. Scale every pose so its head radius is identical -> swaps never pop head size.
- **FEET Detection**: Middle of opaque pixels in bottom 3.5% rows -> full-body poses stand on the exact same world coordinate.
- **ECC Affine Alignment**: `cv2.findTransformECC` on the head region to lock edited pose pairs.

## 5. The World: 2.5D Multiplane Camera
- Layers at depth $Z$ (foreground 650, character 1000, midground 1800, set piece 3000).
- Scale: $k = \frac{1000}{Z - \text{cam.z}}$.
- Log-space zoom interpolation: `exp(lerp(log k0, log k1, u))` so camera moves feel completely optical.
- Depth of field: blur far layers 2.5–3.6px while camera is close on the character.
- Procedural screen shake: sums of sines ($13.3\text{ Hz} + 7.1\text{ Hz}$) multiplied by a decay envelope.

## 6. Animating Cut-Out Poses (Squash-Swap)
- NEVER cross-fade two drawings (ghosting is forbidden).
- **Turn**: squash `scaleX` to 0.8 (`scaleY` 1.03) and swap on the narrowest frame.
- **Action**: anticipation squash (`scaleY` 0.94) $\to$ swap $\to$ stretch (1.03) settling with damped spring.
- **Throw**: swap to follow-through pose at release; lean snaps -5 deg to +5 deg.
- **Catch**: swap to holding pose the frame flying object reaches hand, with small weight dip.
- **Life on holds**: idle breathing (`scaleY` $1.00 \pm 0.9\%$ at $0.6\text{ Hz}$ about feet), contact shadow (soft ellipse).

## 7. Props with Real Physics
- Thrown object is its own sprite with its own depth.
- Parabolic gravity trajectory: $x$ and $z$ move at constant speed; $y$ follows a gravity parabola with apex time $t_a$.
- Spin (~1 turn), perspective scaling, liquid sinking with clip path.

## 8. Code Effects
- Flat cartoon look: clusters of circles with merged outline (steam/smoke), liquid lava without black outline.
- Faces on objects: white ellipses + black pupils + white glint, eyelids with tilt, "> <" squeeze, sweat drops.

## 9. Decibel-Budget Sound Design
- Voice at $0\text{ dBFS}$.
- Exact decibel budget:
  - Whooshes / air movement: **$-25$ to $-31\text{ dB}$**
  - Impacts / thuds: **$-14$ to $-19\text{ dB}$**
  - Ambient beds (drone, rumble): **$-26$ to $-33\text{ dB}$**
  - Climax blasts: **$-8$ to $-10\text{ dB}$** inside a speech pause.
- Master integrated loudness normalized to **$-14\text{ LUFS}$** (EBU R128).

## 10. Verification Before Release
- Contact sheet grid of every beat.
- Pop scan: preview difference $> 2.2\times$ local median to catch accidental glitches.
- Stream compliance: 1080x1920 (or 2160x3840), 30/60 fps, 48kHz AAC stereo.
