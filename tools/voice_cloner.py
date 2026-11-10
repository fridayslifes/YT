#!/usr/bin/env python3
"""tools/voice_cloner.py — Local Zero-Shot Voice Cloner on Apple Silicon Metal.

Uses F5-TTS flow-matching diffusion to clone any voice from a 5–10 second reference WAV clip.
Runs 100% locally on Apple Silicon Metal (MPS) with zero cloud dependencies.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys
import time

REPO_ROOT = Path(__file__).resolve().parent.parent
MODEL_CKPT = REPO_ROOT / "models" / "f5-tts" / "model_1250000.safetensors"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("voice_cloner")


def clone_voice(
    ref_audio: Path,
    ref_text: str,
    gen_text: str,
    output_wav: Path,
    device: str = "mps",
    speed: float = 1.0,
    nfe_step: int = 64,
    cfg_strength: float = 2.5,
    remove_silence: bool = True,
    target_rms: float = 0.15,
) -> Path:
    """Clone voice from ref_audio and synthesize gen_text with studio quality settings."""
    from f5_tts.api import F5TTS
    import soundfile as sf
    import torch

    if not ref_audio.exists():
        raise FileNotFoundError(f"Reference audio not found: {ref_audio}")

    selected_device = device if (device == "mps" and torch.backends.mps.is_available()) else "cpu"
    logger.info("Initializing F5-TTS model on device: %s (steps=%d, cfg=%.1f)...", selected_device, nfe_step, cfg_strength)

    ckpt_str = str(MODEL_CKPT) if MODEL_CKPT.exists() else ""
    t0 = time.time()
    f5tts = F5TTS(ckpt_file=ckpt_str, device=selected_device)
    logger.info("Model loaded in %.2fs. Generating speech...", time.time() - t0)

    t1 = time.time()
    wav, sr, _ = f5tts.infer(
        ref_file=str(ref_audio),
        ref_text=ref_text,
        gen_text=gen_text,
        speed=speed,
        nfe_step=nfe_step,
        cfg_strength=cfg_strength,
        remove_silence=remove_silence,
        target_rms=target_rms,
        seed=42,
    )
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output_wav), wav, sr)
    logger.info("✓ Speech synthesized in %.2fs -> %s", time.time() - t1, output_wav)
    return output_wav


def main() -> int:
    parser = argparse.ArgumentParser(description="Local Zero-Shot Voice Cloner")
    parser.add_argument("--ref-audio", type=Path, required=True, help="Reference audio file (WAV)")
    parser.add_argument("--ref-text", type=str, required=True, help="Transcript of reference audio")
    parser.add_argument("--text", type=str, required=True, help="New text to synthesize in cloned voice")
    parser.add_argument("--output", type=Path, required=True, help="Output WAV path")
    parser.add_argument("--speed", type=float, default=1.0, help="Speech speed multiplier (default: 1.0)")
    parser.add_argument("--nfe-step", type=int, default=64, help="Diffusion sampling steps (default: 64)")
    parser.add_argument("--cfg-strength", type=float, default=2.5, help="Classifier-free guidance strength (default: 2.5)")
    parser.add_argument("--remove-silence", action="store_true", default=True, help="Trim silent ends")
    parser.add_argument("--device", type=str, default="mps", choices=["mps", "cpu"], help="Inference device")

    args = parser.parse_args()

    try:
        out = clone_voice(
            ref_audio=args.ref_audio,
            ref_text=args.ref_text,
            gen_text=args.text,
            output_wav=args.output,
            device=args.device,
            speed=args.speed,
        )
        print(f"✓ Cloned voice generated successfully: {out}")
        return 0
    except Exception as exc:
        logger.error("Failed to clone voice: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
