# Hybrid Organic SFX Bank

Drop optional broadcast-quality, royalty-free `.wav` (or `.mp3`) audio files here to blend organic physical Foley with `tools/build_video.py`'s procedural sound engine.

### Supported File Names:
1. `shutter.wav` / `click.wav`: Blended with the Frame 0 (0.0s) tactile opening transient.
2. `pop.wav` / `bubble.wav`: Blended with the subtitle `*emphasis*` micro-pops.
3. `chime.wav` / `bell.wav`: Blended with the glassmorphic stat card & citation reveals.
4. `whoosh.wav`: Blended with shot cut transition whooshes.
5. `boom.wav` / `impact.wav`: Blended with climactic sub-bass drops.

### Fallback Behavior:
If this folder is empty or any individual file is missing, the engine automatically synthesizes mathematically pure, harmonically-saturated, 100% claim-safe procedural sounds using NumPy and SciPy.
