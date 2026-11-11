#!/usr/bin/env python3
"""FrameForge Unified 3D Spatial & Multi-Plane Engine (v5.0 — True 3D Z-Planes + Normal Relighting + DoF).

Pure 3D Architecture (Zero Legacy 2D / 2.5D Single-Sheet Fallbacks):
  1. 3-Plane Spatial Decomposition (`extract_3d_layers`):
     - Near Plane (Z-Near): High-precision ISNet (`rembg`) foreground subject alpha cutout.
     - Mid & Far Planes (Z-Mid / Z-Far): Clean LaMa / Telea inpainted background plate + edge-preserving
       Bilateral-filtered `Depth-Anything-V2` continuous depth map (preserving crisp 3D object relief).
  2. True 3D Pinhole Camera Trajectories (`render_3d_spatial_scene`):
     - Full 3D perspective camera projection across `depthflow_spiral`, `depthflow_orbit`, `depthflow_vertigo`
       (Hitchcock Dolly-Zoom), `depthflow_dolly`, `depthflow_roll`, and `spatial_drift`.
     - Independent multi-plane 1/Z parallax with dynamic 3D drop shadows cast from the foreground subject onto the midground.
  3. Dynamic 3D Surface-Normal Relighting & Fresnel Rim Light:
     - Computes per-pixel 3D surface normals N(x,y) = normalize(-dZ/dx, -dZ/dy, 1) from the depth map and sweeps a
       moving 3D directional key light + Fresnel rim light across facial contours, hands, and room geometry.
  4. Physical Aperture Rack-Focus Depth-of-Field (DoF) & 3D Volumetric Depth Particles:
     - Continuous depth-dependent bokeh blur proportional to |Z(x,y) - Z_focus(t)| plus multi-depth 3D floating
       dust/bokeh particles moving at true 1/Z parallax speeds.
  5. Procedural & Displaced 3D Wavefront `.obj` Mesh Generator & PBR/Wireframe Renderer (`studio_3d.py` / `BlenderBridge`).
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import os
import select
import shutil
import subprocess
import sys
import time
import zlib
from dataclasses import dataclass
from pathlib import Path

for _bin_dir in ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"):
    if os.path.isdir(_bin_dir) and _bin_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{_bin_dir}:{os.environ.get('PATH', '')}"

TOOLS_DIR = Path(__file__).resolve().parent
YT_ROOT = TOOLS_DIR.parent
# Unified root .venv holds mflux 0.24 alongside Pillow 13.
FLUX2_BIN = YT_ROOT / ".venv" / "bin" / "mflux-generate-flux2"
FLUX3_BIN = YT_ROOT / ".venv" / "bin" / "mflux-generate-flux3"


def _resolve_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RenderingError(
            stage="resolve_binary",
            artifact="ffmpeg",
            cause="ffmpeg executable not found on system PATH",
        )
    return path


def _resolve_ffprobe() -> str:
    path = shutil.which("ffprobe")
    if not path:
        raise RenderingError(
            stage="resolve_binary",
            artifact="ffprobe",
            cause="ffprobe executable not found on system PATH",
        )
    return path

# Weight stores sit in models/, which .gitignore excludes — so a fresh clone of this repo has no
# renderer at all, and _renderer_for raises rather than downloading one. Set YT_MODELS_DIR to keep
# the store elsewhere, e.g. an external SSD.
MODELS_ROOT = Path(os.environ.get("YT_MODELS_DIR") or (YT_ROOT / "models"))
LOCAL_FLUX3_DIR = MODELS_ROOT / "flux-3-image-klein-mflux-q8"


def _weights_complete(model_dir: Path) -> bool:
    """A directory exists long before its download finishes; hf parks partial shards in .incomplete."""
    if not (model_dir / "transformer" / "model.safetensors.index.json").exists():
        return False
    return not any(model_dir.rglob("*.incomplete"))


# FLUX.3 image klein Q8 is the plate renderer. Of the three models tested on the same 6-layer
# prompt it gave the best skin micro-texture, a correctly defocused foreground plane and real
# directional falloff, at the lowest memory: 6.33 GB peak against FLUX.2 Klein's 8.03 GB. The
# price is 16 steps rather than 4, so a 768x1360 plate takes ~250s instead of ~50s.
DEFAULT_MODEL = str(LOCAL_FLUX3_DIR)


@dataclass(frozen=True)
class _Renderer:
    """How to invoke mflux for one model family. `steps` is the checkpoint's distilled count, not
    a tunable: FLUX.3 klein is trained for 16 and FLUX.2 klein for 4, and under-stepping either
    yields an unconverged frame rather than a faster one."""
    binary: Path
    flags: list[str]
    steps: int
    supports_negative_prompt: bool


def _renderer_for(model: str) -> _Renderer:
    """Route a model to its mflux binary and the family flags that binary requires.

    There is deliberately no fallback. An absent or partial store, or a model this pipeline does
    not support, raises instead of quietly rendering with a weaker model or triggering an
    unplanned multi-gigabyte download.
    """
    path = Path(model)
    if path.is_absolute() and not _weights_complete(path):
        raise RuntimeError(
            f"{model} is not a complete weight store. Restore it with: "
            f"hf download mflux-community/{path.name} --local-dir {model}"
        )
    if not FLUX3_BIN.exists():
        raise RuntimeError(
            f"{model} needs mflux 0.24 in .venv: "
            "uv pip install --python .venv/bin/python 'mflux==0.24.0'"
        )
    name = (path.name if path.is_absolute() else str(model)).lower()
    # Tested before klein: the FLUX.3 store is named "...image-klein...", so a klein check first
    # would hand it to the FLUX.2 binary, which rejects it.
    if "flux3" in name or "flux-3" in name:
        # FLUX.3's distilled checkpoint has no guidance embedding, so its CLI hard-errors on
        # --negative-prompt rather than ignoring it.
        return _Renderer(FLUX3_BIN, ["--base-model", "flux3-image-klein"], 16, False)
    if "klein" in name or "flux2" in name:
        # No --small-text-encoder: mflux restricts it to the 4B builds and errors on 9B, and the
        # 9B Q5 peaks at 8.03 GB under --low-ram alone.
        return _Renderer(FLUX2_BIN, [], 4, True)
    raise RuntimeError(f"{model}: no renderer for this store (FLUX.3 klein or FLUX.2 klein only)")


if str(YT_ROOT) not in sys.path:
    sys.path.insert(0, str(YT_ROOT))
from tools.runtime import ensure_venv_cli  # noqa: E402

if __name__ == "__main__":
    ensure_venv_cli(Path(__file__), sys.argv[1:])

if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
if str(YT_ROOT) not in sys.path:
    sys.path.insert(0, str(YT_ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageFilter  # noqa: E402

VENV_SITE = YT_ROOT / ".venv" / "lib" / "python3.11" / "site-packages"
if VENV_SITE.exists() and str(VENV_SITE) not in sys.path:
    sys.path.append(str(VENV_SITE))

from tools.errors import RenderingError  # noqa: E402

from tools import genre_director  # noqa: E402
from tools import visual_director  # noqa: E402
from tools.processes import ProcessDeadlineExceeded, process_group, run_process  # noqa: E402

_REMBG_SESSION = None
_DEPTH_PIPE = None
_VIDEOTOOLBOX_AVAILABLE: bool | None = None
_NVENC_AVAILABLE: bool | None = None


# --------------------------------------------------------------------------- #
# 1. Shared Physics & Hardware Self-Healing Primitives
# --------------------------------------------------------------------------- #
@dataclass
class SpringConfig:
    damping: float = 12.0
    mass: float = 1.0
    stiffness: float = 120.0
    overshoot_clamping: bool = False


def remotion_spring(
    t: float,
    config: SpringConfig | None = None,
    damping: float | None = None,
    stiffness: float | None = None,
    mass: float | None = None,
) -> float:
    """Analytical solution of damped harmonic oscillator: m*x'' + c*x' + k*x = 0."""
    cfg = config or SpringConfig()
    m = mass if mass is not None else cfg.mass
    c = damping if damping is not None else cfg.damping
    k = stiffness if stiffness is not None else cfg.stiffness
    omega_0 = math.sqrt(max(1e-6, k / max(1e-6, m)))
    zeta = c / (2.0 * math.sqrt(max(1e-6, m * k)))

    if zeta < 1.0:
        omega_d = omega_0 * math.sqrt(1.0 - zeta * zeta)
        decay = math.exp(-zeta * omega_0 * t)
        val = 1.0 - decay * (math.cos(omega_d * t) + (zeta / math.sqrt(1.0 - zeta * zeta)) * math.sin(omega_d * t))
    elif zeta == 1.0:
        val = 1.0 - math.exp(-omega_0 * t) * (1.0 + omega_0 * t)
    else:
        gamma1 = -omega_0 * (zeta - math.sqrt(zeta * zeta - 1.0))
        gamma2 = -omega_0 * (zeta + math.sqrt(zeta * zeta - 1.0))
        val = 1.0 - (gamma2 * math.exp(gamma1 * t) - gamma1 * math.exp(gamma2 * t)) / (gamma2 - gamma1)

    if cfg.overshoot_clamping and val > 1.0:
        return 1.0
    return float(val)


def _heal_gpu_memory() -> None:
    """Actively flush Python GC, Apple Silicon MLX Metal cache, and PyTorch MPS/CUDA cache."""
    gc.collect()
    if "torch" in sys.modules:
        import torch
        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    if "mlx.core" in sys.modules:
        import mlx.core as mx
        if hasattr(mx, "clear_cache"):
            mx.clear_cache()
        elif hasattr(mx, "metal") and hasattr(mx.metal, "clear_cache"):
            mx.metal.clear_cache()


def _can_use_nvenc() -> bool:
    """Probe once whether NVIDIA NVENC H.264 hardware encoding is actually usable."""
    global _NVENC_AVAILABLE
    if _NVENC_AVAILABLE is None:
        try:
            ffmpeg_bin = _resolve_ffmpeg()
            res = subprocess.run(
                [
                    ffmpeg_bin, "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=128x128:r=30:d=0.05",
                    "-frames:v", "1", "-c:v", "h264_nvenc", "-f", "null", "-",
                ],
                capture_output=True,
                timeout=5,
            )
            _NVENC_AVAILABLE = (res.returncode == 0)
        except Exception:
            _NVENC_AVAILABLE = False
    return _NVENC_AVAILABLE


def _can_use_videotoolbox() -> bool:
    """Probe once whether Apple VideoToolbox hardware encoding is accessible."""
    global _VIDEOTOOLBOX_AVAILABLE
    if _VIDEOTOOLBOX_AVAILABLE is None:
        try:
            ffmpeg_bin = _resolve_ffmpeg()
            res = subprocess.run(
                [
                    ffmpeg_bin, "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:r=30:d=0.05",
                    "-frames:v", "1", "-c:v", "h264_videotoolbox", "-allow_sw", "1", "-f", "null", "-",
                ],
                capture_output=True,
                timeout=5,
            )
            _VIDEOTOOLBOX_AVAILABLE = (res.returncode == 0)
        except Exception:
            _VIDEOTOOLBOX_AVAILABLE = False
    return _VIDEOTOOLBOX_AVAILABLE


def select_h264_encoder_args(bitrate: str = "14M", preview: bool = False, hw_accel: bool = True) -> list[str]:
    """Select verified H.264 encoder args: NVENC when usable -> VideoToolbox on Mac -> libx264."""
    if hw_accel and not preview:
        if _can_use_nvenc():
            return [
                "-c:v", "h264_nvenc", "-b:v", bitrate, "-profile:v", "high",
            ]
        if _can_use_videotoolbox():
            return [
                "-c:v", "h264_videotoolbox", "-b:v", bitrate, "-profile:v", "high", "-allow_sw", "1", "-prio_speed", "0",
            ]
    return [
        "-c:v", "libx264", "-preset", "ultrafast" if preview else "fast",
        "-b:v", "4M" if preview else bitrate, "-maxrate", "16M", "-bufsize", "28M", "-profile:v", "high",
    ]


def _ffmpeg_stderr_log_path(output_path: Path) -> Path:
    """Sidecar log path for ffmpeg stderr (never an unread PIPE that can deadlock the child)."""
    return output_path.parent / f"{output_path.name}.ffmpeg.log"


def _probe_video_metadata(video_path: Path, timeout: int = 20) -> dict:
    """Fast ffprobe of an encoded clip; returns {} when the file is not a readable video."""
    ffprobe_bin = _resolve_ffprobe()
    try:
        res = subprocess.run(
            [
                ffprobe_bin, "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=codec_type,width,height,nb_frames:format=duration",
                "-of", "json", str(video_path),
            ],
            capture_output=True, text=True, timeout=timeout,
        )
        if res.returncode != 0:
            return {}
        data = json.loads(res.stdout or "{}")
        streams = data.get("streams") or []
        if not streams:
            return {}
        meta = dict(streams[0])
        meta["duration"] = float((data.get("format") or {}).get("duration") or 0.0)
        meta["src_fps"] = 0.0
        return meta
    except Exception:
        return {}


def verify_encoded_output(output_path: Path, min_bytes: int = 2048) -> tuple[bool, str]:
    """True only when the file exists, is non-trivial, and ffprobe/ffmpeg can decode its tail frame."""
    if not output_path.exists():
        return False, "output file missing"
    size = output_path.stat().st_size
    if size < min_bytes:
        return False, f"truncated output ({size} bytes)"
    return verify_video_decodable(output_path)


def verify_video_decodable(output_path: Path, timeout: float = 90.0) -> tuple[bool, str]:
    """Decode a real tail frame; a successful exit with zero frames is not success."""
    if not output_path.exists():
        return False, "output file missing"
    size = output_path.stat().st_size
    meta = _probe_video_metadata(output_path, timeout=min(20.0, timeout))
    if not meta or meta.get("codec_type") != "video":
        return False, "ffprobe found no decodable video stream (corrupt moov/headers)"
    if not meta.get("width") or not meta.get("height"):
        return False, "video stream reports zero dimensions"

    # Tail decode: a render killed mid-stream usually leaves a readable moov atom with cut-off frames.
    ffmpeg_bin = _resolve_ffmpeg()
    dur = float(meta.get("duration") or 0.0)
    seek = max(0.0, dur - 0.5) if dur > 0.5 else 0.0
    try:
        res = subprocess.run(
            [ffmpeg_bin, "-v", "error", "-xerror", "-ss", f"{seek:.3f}", "-i", str(output_path),
             "-map", "0:v:0", "-frames:v", "1", "-an", "-progress", "pipe:1", "-f", "null", "-"],
            capture_output=True, text=True, timeout=timeout,
        )
        if res.returncode != 0:
            return False, f"last frame at {seek:.1f}s is undecodable: {res.stderr.strip()}"
        if not any(line.startswith("frame=") and line.partition("=")[2].strip().isdigit()
                   and int(line.partition("=")[2]) > 0 for line in res.stdout.splitlines()):
            return False, f"tail decode produced no video frame at {seek:.1f}s: {res.stderr.strip()}"
    except Exception as e:
        return False, f"tail decode probe failed: {e}"

    return True, f"{size // 1024}KB @ {meta.get('width')}x{meta.get('height')}"


class _FFmpegWriter:
    """Managed ffmpeg raw-video encoder: stderr goes to a sidecar log, the child is always reaped.

    Use as a context manager so an exception inside the frame loop kills ffmpeg instead of
    orphaning it, and `finish()` verifies return code + output decodability instead of trusting
    `output_path.exists()`.
    """

    def __init__(self, proc: subprocess.Popen, output_path: Path, log_path: Path):
        self.proc = proc
        self.output_path = output_path
        self.log_path = log_path
        self.finished = False

    def __enter__(self) -> "_FFmpegWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self._cleanup(kill=exc_type is not None)
        return False

    def write(self, frame_u8) -> None:
        if self.proc.poll() is not None:
            raise RuntimeError(
                f"ffmpeg encoder exited early with code {self.proc.returncode} while writing {self.output_path.name}"
                f" -> {_tail_stderr(self.log_path)}"
            )
        try:
            self.proc.stdin.write(frame_u8.tobytes())
        except (BrokenPipeError, OSError) as e:
            raise RuntimeError(
                f"ffmpeg pipe broke while writing {self.output_path.name}: {e} -> {_tail_stderr(self.log_path)}"
            ) from e

    def _cleanup(self, kill: bool = False) -> None:
        if self.proc.stdin and not self.proc.stdin.closed:
            self.proc.stdin.close()
        if kill or self.proc.poll() is None:
            if not kill:
                try:
                    self.proc.wait(timeout=120)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait(timeout=10)
            else:
                self.proc.kill()
                self.proc.wait(timeout=10)
        self.log_path.unlink(missing_ok=True)
        self.finished = True

    def finish(self, min_bytes: int = 2048) -> tuple[bool, str]:
        """Close the stream, reap ffmpeg, check the return code, then probe the encoded file."""
        if self.proc.stdin and not self.proc.stdin.closed:
            self.proc.stdin.close()
        try:
            rc = self.proc.wait(timeout=180)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
            self.log_path.unlink(missing_ok=True)
            self.finished = True
            return False, "ffmpeg timed out and was killed"
        log_tail = _tail_stderr(self.log_path)
        self.log_path.unlink(missing_ok=True)
        self.finished = True
        if rc != 0:
            return False, f"ffmpeg exited with code {rc}{f' -> {log_tail}' if log_tail else ''}"
        ok, why = verify_encoded_output(self.output_path, min_bytes=min_bytes)
        return ok, (why if ok else f"{why}{f' -> {log_tail}' if log_tail else ''}")


def _tail_stderr(log_path: Path, chars: int = 240) -> str:
    """Read the tail of the ffmpeg stderr log for diagnostics (best effort)."""
    if log_path.exists():
        return log_path.read_text(errors="ignore").strip()[-chars:]
    return ""


def _open_ffmpeg_writer(output_path: Path, W: int, H: int, fps: int = 30, bitrate: str = "14M") -> _FFmpegWriter:
    """Open high-precision H.264 writer (NVENC -> VideoToolbox -> libx264 High-Profile self-healing)."""
    ffmpeg_bin = _resolve_ffmpeg()
    vcodec_args = select_h264_encoder_args(bitrate=bitrate, preview=False, hw_accel=True)
    log_path = _ffmpeg_stderr_log_path(output_path)
    cmd = [
        ffmpeg_bin, "-v", "error", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{W}x{H}", "-pix_fmt", "bgr24", "-r", str(fps), "-i", "-",
        *vcodec_args,
        "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
        str(output_path),
    ]
    with open(log_path, "wb") as log_fh:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=log_fh)
    return _FFmpegWriter(proc, output_path, log_path)


# --------------------------------------------------------------------------- #
# 2. Self-Healing SOTA AI Models (Depth-Anything-V2 & ISNet Segmentation)
# --------------------------------------------------------------------------- #
def get_rembg_session(force_reset: bool = False):
    """Load high-precision isnet-general-use session with self-healing reset on ONNX state errors.

    Returns None when every session model failed to load; callers must not treat that as a
    clean ISNet cutout, so the failure is announced explicitly instead of silently.
    """
    global _REMBG_SESSION
    if force_reset:
        _REMBG_SESSION = None
        _heal_gpu_memory()
    if _REMBG_SESSION is None:
        try:
            import rembg
        except Exception as e:
            print(f"  [rembg] Import failed ({e}); ISNet cutout unavailable -> depth-salience silhouette will be used.")
            return None
        for attempt, model_name in enumerate(("isnet-general-use", "isnet-general-use", "u2net")):
            try:
                _REMBG_SESSION = rembg.new_session(model_name)
                break
            except Exception as e:
                print(f"  [Self-Heal: rembg] Attempt {attempt+1} ({model_name}) failed: {e}. Clearing cache and retrying...")
                _heal_gpu_memory()
                time.sleep(0.5)
        if _REMBG_SESSION is None:
            print(
                "  [rembg] WARNING: all segmentation sessions failed to load -> returning None; "
                "foreground cutout will fall back to the synthetic depth-salience mask."
            )
    return _REMBG_SESSION


def get_depth_pipeline(force_cpu: bool = False):
    """Load Depth Anything V2 Small pipeline with MPS self-healing."""
    global _DEPTH_PIPE
    if force_cpu:
        _DEPTH_PIPE = None
        _heal_gpu_memory()
    if _DEPTH_PIPE is None:
        import torch
        from transformers import pipeline
        devices = ["cpu"] if force_cpu else (["mps", "cpu"] if torch.backends.mps.is_available() else ["cpu"])
        for dev in devices:
            try:
                _DEPTH_PIPE = pipeline(
                    task="depth-estimation",
                    model="depth-anything/Depth-Anything-V2-Small-hf",
                    device=dev,
                )
                break
            except Exception as e:
                print(f"  [Self-Heal: Depth-Anything-V2] Device '{dev}' init error ({e}), healing & retrying...")
                _heal_gpu_memory()
    return _DEPTH_PIPE


def _estimate_optical_salience_depth(bgr: np.ndarray) -> np.ndarray:
    """Multi-scale focus + Lab boundary salience + geometric depth estimator (0.0=far, 1.0=near)."""
    H, W = bgr.shape[:2]
    small_w, small_h = max(128, W // 2), max(128, H // 2)
    small_bgr = cv2.resize(bgr, (small_w, small_h), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0

    lap = np.abs(cv2.Laplacian(gray, cv2.CV_32F, ksize=3))
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    focus_energy = cv2.GaussianBlur(0.55 * np.hypot(gx, gy) + 0.45 * lap, (31, 31), 10.0)
    focus_norm = (focus_energy - focus_energy.min()) / max(1e-6, float(focus_energy.max() - focus_energy.min()))

    lab = cv2.cvtColor(small_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    b_pad = max(8, min(small_w, small_h) // 16)
    border_pixels = np.concatenate(
        [
            lab[:b_pad, :, :].reshape(-1, 3),
            lab[:, :b_pad, :].reshape(-1, 3),
            lab[:, -b_pad:, :].reshape(-1, 3),
        ],
        axis=0,
    )
    bg_mean = np.median(border_pixels, axis=0)
    color_dist = np.linalg.norm(lab - bg_mean[None, None, :], axis=2)
    color_sal = cv2.GaussianBlur(color_dist, (35, 35), 11.0)
    color_norm = (color_sal - color_sal.min()) / max(1e-6, float(color_sal.max() - color_sal.min()))

    yy, xx = np.mgrid[0:small_h, 0:small_w].astype(np.float32)
    yn, xn = yy / max(1.0, float(small_h - 1)), xx / max(1.0, float(small_w - 1))
    radial_prior = np.exp(-(((xn - 0.5) / 0.38) ** 2 + ((yn - 0.48) / 0.36) ** 2))
    ground_prior = np.clip(0.25 + 0.75 * yn, 0.0, 1.0)

    combined = 0.42 * focus_norm + 0.28 * color_norm + 0.20 * radial_prior + 0.10 * ground_prior
    combined = cv2.bilateralFilter(combined.astype(np.float32), d=9, sigmaColor=0.18, sigmaSpace=15.0)
    depth_full = cv2.resize(combined, (W, H), interpolation=cv2.INTER_CUBIC)
    d_min, d_max = float(depth_full.min()), float(depth_full.max())
    if d_max > d_min:
        depth_full = (depth_full - d_min) / (d_max - d_min)
    return depth_full.astype(np.float32)


def estimate_depth(image: Image.Image | np.ndarray) -> np.ndarray:
    """Estimate continuous 0.0-1.0 depth map using Depth Anything V2 with bilateral edge-preserving filtering."""
    if isinstance(image, np.ndarray):
        H, W = image.shape[:2]
        bgr_img = image
        pil_img = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    else:
        W, H = image.size
        pil_img = image.convert("RGB")
        bgr_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    for attempt in range(2):
        try:
            pipe = get_depth_pipeline(force_cpu=(attempt == 1))
            if pipe is None:
                break
            res = pipe(pil_img)
            depth_arr = np.array(res["depth"]).astype(np.float32)
            if depth_arr.shape != (H, W):
                depth_arr = cv2.resize(depth_arr, (W, H), interpolation=cv2.INTER_CUBIC)
            d_min, d_max = float(depth_arr.min()), float(depth_arr.max())
            if d_max > d_min:
                norm_d = (depth_arr - d_min) / (d_max - d_min)
                # Edge-preserving bilateral filter preserves 3D object relief without rubber-sheet cliffs
                small_d = cv2.resize(norm_d, (W // 2, H // 2), interpolation=cv2.INTER_AREA)
                filt_d = cv2.bilateralFilter(small_d, d=9, sigmaColor=0.14, sigmaSpace=12.0)
                return cv2.resize(filt_d, (W, H), interpolation=cv2.INTER_CUBIC)
        except Exception as e:
            if attempt == 0 and "torch" not in str(e).lower():
                print(f"  [Self-Heal: Depth Inference] Attempt {attempt+1} error ({e}); resetting pipeline to CPU float32...")
                _heal_gpu_memory()
            else:
                break

    return _estimate_optical_salience_depth(bgr_img)


def _compute_surface_normals(depth: np.ndarray) -> np.ndarray:
    """Compute 3D unit surface normal map N(x,y) = (Nx, Ny, Nz) from continuous depth map Z(x,y)."""
    d_smooth = cv2.GaussianBlur(depth, (15, 15), 3.2)
    dz_dx = cv2.Sobel(d_smooth, cv2.CV_32F, 1, 0, ksize=3) * 2.2
    dz_dy = cv2.Sobel(d_smooth, cv2.CV_32F, 0, 1, ksize=3) * 2.2
    nz = np.ones_like(d_smooth, dtype=np.float32)
    norm = np.sqrt(dz_dx ** 2 + dz_dy ** 2 + nz ** 2) + 1e-6
    normals = np.stack([-dz_dx / norm, -dz_dy / norm, nz / norm], axis=-1)
    return normals


# --------------------------------------------------------------------------- #
# 3. Reference Precision & Recall Visual Verifier + Self-Healing FLUX Generator
# --------------------------------------------------------------------------- #
# Gate floors, calibrated against the 216 delivered renders already in output/, shorts/ and
# channel_assets/: softest legit Laplacian variance was 20.0, flattest contrast 24.3, and the
# leanest asset 41.8 KB/MP. A GaussianBlur(8) wreck scores 0.7 here, so these separate
# genuinely broken renders from stylistically soft ones with room to spare.
# MIN_KB_PER_MEGAPIXEL is reported as `note`/`kb_per_megapixel` only; it does not affect `valid`.
MIN_SHARPNESS = 12.0
MIN_CONTRAST = 15.0
MIN_KB_PER_MEGAPIXEL = 25.0


def verify_image_precision_recall(img_path: Path) -> dict:
    """Reject renders that are actually broken: smeared, flat/blank, or over-compressed."""
    if not img_path.exists():
        return {"valid": False, "precision": 0.0, "recall": 0.0, "reason": "File missing"}
    bgr = cv2.imread(str(img_path))
    if bgr is None:
        return {"valid": False, "precision": 0.0, "recall": 0.0, "reason": "Corrupt image"}

    H, W = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    contrast_std = float(gray.std())
    sharp_score = min(1.0, lap_var / 85.0)
    contrast_score = min(1.0, contrast_std / 38.0)
    precision = round(0.55 * sharp_score + 0.45 * contrast_score, 3)

    sobel_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    grad_mag = np.hypot(sobel_x, sobel_y)
    y0, y1 = int(H * 0.25), int(H * 0.65)
    safe_zone_density = float(grad_mag[y0:y1, :].mean())
    global_density = max(1e-6, float(grad_mag.mean()))
    recall = round(min(1.0, (safe_zone_density / global_density) / 0.95), 3)

    file_kb = img_path.stat().st_size // 1024
    kb_per_mp = file_kb / max(0.05, (H * W) / 1e6)

    reasons = []
    if lap_var < MIN_SHARPNESS:
        reasons.append(f"smeared (lap {lap_var:.1f} < {MIN_SHARPNESS})")
    if contrast_std < MIN_CONTRAST:
        reasons.append(f"flat tonality (contrast {contrast_std:.1f} < {MIN_CONTRAST})")

    # Byte-size floors are informational only, never a validity test: a legitimately smooth, dark or
    # minimal FLUX frame encodes small, and gating on KB/MP used to drive the render loop to
    # UnsharpMask exactly those clean frames (visible ringing halos).
    notes = []
    if kb_per_mp < MIN_KB_PER_MEGAPIXEL:
        notes.append(f"low bitrate for its detail level ({kb_per_mp:.0f} KB/MP < {MIN_KB_PER_MEGAPIXEL}, informational)")

    return {
        "valid": not reasons,
        "precision": precision,
        "recall": recall,
        "laplacian_sharpness": round(lap_var, 1),
        "contrast_std": round(contrast_std, 1),
        "kb_per_megapixel": round(kb_per_mp, 1),
        "size_kb": file_kb,
        "reason": "ok" if not reasons else "; ".join(reasons),
        "note": "; ".join(notes),
    }


MFLUX_TIMEOUT = 600  # FLUX.3 at 768x1360 measures ~250s on the baseline rung, ~280s on the 18-step rung


def generate_scene_image(
    prompt: str,
    output_path: Path,
    width: int = 768,
    height: int = 1360,
    steps: int | None = None,
    model: str = DEFAULT_MODEL,
    seed: int | None = None,
    lora_style: str | None = None,
    negative_prompt: str | None = None,
    auto_sharpen: bool = False,
    genre: str | None = None,
) -> bool:
    """Generate an image via Apple Silicon MLX FLUX, retrying the same seed under lighter memory.

    Returns False when every attempt rendered but the gate rejected the result, and raises only
    when no attempt produced a file at all — a broken tool should not look like a weak render.

    `steps` defaults to the checkpoint's own distilled count, so callers should leave it unset
    unless they have a specific reason to deviate. `negative_prompt` is forwarded as
    `--negative-prompt` on families that accept it. On models rejecting `--negative-prompt`
    (e.g. FLUX.3), `NegativePromptAgent` automatically converts negative constraints into
    affirmative optical anchors and sanitizes negation traps.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    width = max(512, (width // 16) * 16)
    height = max(512, (height // 16) * 16)

    renderer = _renderer_for(model)
    if steps is None:
        steps = renderer.steps

    effective_prompt = prompt
    effective_negative = negative_prompt
    inversion_applied = False
    if not renderer.supports_negative_prompt:
        try:
            from tools.negative_prompt_agent import NegativePromptAgent
            neg_agent = NegativePromptAgent()
            custom_negs = [tok.strip() for tok in negative_prompt.split(",") if tok.strip()] if negative_prompt else None
            res = neg_agent.process(
                prompt=prompt,
                genre=genre or "cinematic_35mm",
                target_model=model,
                custom_negatives=custom_negs,
            )
            effective_prompt = res.optimized_prompt
            effective_negative = None
            inversion_applied = True
        except Exception as exc:
            print(f"  [NegativePromptAgent Warning] Failed to invert negative constraints: {exc}")

    is_jpeg = output_path.suffix.lower() in [".jpg", ".jpeg"]
    actual_mflux_output = output_path.with_suffix(".png") if is_jpeg else output_path

    # --low-ram already implies VAE tiling; --vae-tile-size is the only lever that matters, and
    # shrinking it is the escape hatch when a rung peaks past available unified memory.
    configs = [
        {"tile": "512", "steps": steps, "why": "baseline"},
        {"tile": "256", "steps": steps, "why": "memory relief"},
        {"tile": "256", "steps": steps + 2, "why": "extra convergence"},
    ]

    rendered = False
    last_metrics: dict | None = None
    for attempt, cfg in enumerate(configs, 1):
        cmd = [
            str(renderer.binary),
            "--model", model,
            *renderer.flags,
            "--low-ram",
            "--vae-tile-size", cfg["tile"],
            "--width", str(width),
            "--height", str(height),
            "--steps", str(cfg["steps"]),
            "--prompt", effective_prompt,
            "--output", str(actual_mflux_output),
        ]
        if lora_style:
            cmd.extend(["--lora-style", lora_style])
        # Held constant across rungs on purpose: a retry re-renders the same composition, so a
        # saved seed still predicts the frame. Re-rolling would silently restage the scene.
        if seed is not None:
            cmd.extend(["--seed", str(seed)])
        if effective_negative and renderer.supports_negative_prompt:
            cmd.extend(["--negative-prompt", effective_negative])
        elif attempt == 1 and inversion_applied:
            print(f"  [NegativePromptAgent] {renderer.binary.name} rejects raw --negative-prompt; "
                  f"constraints inverted into affirmative optical anchors.")

        print(f"  [{renderer.binary.name}] Attempt {attempt}/{len(configs)}: {output_path.name} "
              f"({width}x{height}, steps={cfg['steps']}, tile={cfg['tile']}, {cfg['why']})...")
        t0 = time.time()
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=MFLUX_TIMEOUT)
        except subprocess.CalledProcessError as e:
            print(f"  [Self-Heal: MLX FLUX] Renderer failed on attempt {attempt}: "
                  f"{(e.stderr or e.stdout or '').strip()[-240:]}. Flushing Metal cache...")
            _heal_gpu_memory()
            time.sleep(1.0)
            continue
        except subprocess.TimeoutExpired:
            print(f"  [Self-Heal: MLX FLUX] Timed out after {MFLUX_TIMEOUT}s on attempt {attempt}. Flushing Metal cache...")
            _heal_gpu_memory()
            continue
        except Exception as e:
            print(f"  [Self-Heal: MLX FLUX] Exception on attempt {attempt}: {e}. Retrying...")
            _heal_gpu_memory()
            continue

        if is_jpeg and actual_mflux_output.exists():
            with Image.open(actual_mflux_output) as raw_img:
                raw_img.convert("RGB").save(output_path, quality=98, subsampling=0)
            actual_mflux_output.unlink(missing_ok=True)

        metrics = verify_image_precision_recall(output_path)

        # Opt-in only: sharpening to satisfy a metric injects ringing halos into clean renders.
        if auto_sharpen and metrics["laplacian_sharpness"] < MIN_SHARPNESS:
            print(f"  [Opt-in Sharpen] {output_path.name} lap={metrics['laplacian_sharpness']} "
                  f"< {MIN_SHARPNESS} -> UnsharpMask(radius=2.2, percent=85) requested by caller.")
            with Image.open(output_path) as soft_img:
                repaired = soft_img.convert("RGB").filter(
                    ImageFilter.UnsharpMask(radius=2.2, percent=85, threshold=2)
                )
                repaired.save(output_path, quality=98, subsampling=0)
            metrics = verify_image_precision_recall(output_path)

        last_metrics = metrics
        rendered = True
        print(f"  [MLX FLUX] Done in {time.time() - t0:.1f}s | gate={metrics['valid']} "
              f"({metrics['reason']}) | lap={metrics['laplacian_sharpness']} | {metrics['size_kb']}KB"
              + (f" | note: {metrics['note']}" if metrics.get("note") else ""))
        if metrics["valid"]:
            return True

        _heal_gpu_memory()

    if not rendered:
        raise RuntimeError(f"FLUX renderer produced no file for {output_path.name} after {len(configs)} attempts.")

    print(f"  [MLX FLUX] {output_path.name} rejected by gate on every attempt: {last_metrics['reason']}")
    return False


def process_project(
    project_path: Path,
    overwrite: bool = False,
    model: str = DEFAULT_MODEL,
    lora_style: str | None = None,
    steps: int | None = None,
) -> int:
    """Generate and verify all required scene visuals for a project."""
    if not project_path.exists():
        print(f"Project file not found: {project_path}")
        return 1

    project_dir = project_path.parent
    proj_data = json.loads(project_path.read_text())
    is_long = proj_data.get("format", "short") == "long"
    img_w, img_h = (1280, 720) if is_long else (768, 1360)
    scenes = proj_data.get("scenes", [])
    project_negative = genre_director.get_negative_prompt(proj_data.get("genre"))
    print(f"=== Generating & Verifying Visuals for {proj_data.get('title', project_dir.name)} ({len(scenes)} scenes, {'16:9' if is_long else '9:16'}) ===")

    success_count = 0
    for idx, sc in enumerate(scenes, 1):
        rel_img = sc.get("image")
        if not rel_img or Path(rel_img).suffix.lower() in {".mp4", ".mov", ".webm"}:
            stem = Path(rel_img).stem if rel_img else f"s{idx:02d}"
            target_file = project_dir / "images" / f"{stem}.jpg"
        else:
            target_file = project_dir / rel_img

        if target_file.exists() and not overwrite:
            metrics = verify_image_precision_recall(target_file)
            if metrics["valid"]:
                print(f"  Scene {idx}: Verified -> {target_file.name} (Precision={metrics['precision']}, Recall={metrics['recall']})")
                success_count += 1
                continue
            print(f"  Scene {idx}: Existing image failed precision gate ({metrics}), healing...")

        raw_prompt = sc.get("prompt")
        if not raw_prompt:
            scene_text = sc.get("text", f"Scene {idx}")
            raw_prompt = visual_director.format_scene_visual_prompt(
                scene_text,
                aspect="16:9" if is_long else "9:16",
            )

        scene_steps = sc.get("steps", steps)
        if generate_scene_image(
            prompt=raw_prompt,
            output_path=target_file,
            width=img_w,
            height=img_h,
            steps=scene_steps,
            model=sc.get("model", model),
            lora_style=sc.get("lora_style", lora_style),
            seed=idx * 17 + 42,
            negative_prompt=sc.get("negative_prompt") or project_negative,
            genre=proj_data.get("genre"),
        ):
            success_count += 1

    print(f"\n=== Visual Generation Complete: {success_count}/{len(scenes)} scenes verified ===")
    return 0 if success_count == len(scenes) else 1


# --------------------------------------------------------------------------- #
# 4. Optical Flow Precision & Recall Gate
# ---------------------------------------------------------------------------
# Full-resolution Farneback over every 3rd decoded frame was the single hottest cost in the
# pipeline (~10s for a 5s clip, minutes per long-form clip -> `--verify-all` timed out).
# The gate now decodes through an ffmpeg pipe at ~1/4 resolution and samples a fixed, evenly
# spread number of frame pairs. Flow magnitudes are rescaled back to source-pixel units and the
# blur/erode kernels are divided by the same factor, so the reported metrics stay comparable to
# the old full-resolution gate. `pipeline.PRESETS`-side samplers mirror this cadence.
MOTION_SAMPLE_GAP = 3      # source frames between the two halves of a sampled pair
MOTION_MAX_FRAMES = 24     # pairs analysed per clip, spread evenly over its whole duration
MOTION_SAMPLE_WIDTH = 480  # long side of the decode target (~1/4 of a 1080-class frame)
PROBE_TIMEOUT_S = 20.0
MEDIA_TIMEOUT_S = 90.0
BLENDER_TIMEOUT_S = 600.0


def _probe_video_shape(video_path: Path) -> tuple[int, int, float, int]:
    """Return (width, height, fps, n_frames) for a clip via ffprobe."""
    ffprobe_bin = _resolve_ffprobe()
    try:
        res = run_process(
            [
                ffprobe_bin, "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height,r_frame_rate,nb_frames:format=duration",
                "-of", "json", str(video_path),
            ],
            capture_output=True, text=True, timeout_s=PROBE_TIMEOUT_S, check=True,
        )
        data = json.loads(res.stdout or "{}")
        stream = (data.get("streams") or [{}])[0]
        w, h = int(stream.get("width") or 0), int(stream.get("height") or 0)
        num, _, den = str(stream.get("r_frame_rate") or "30/1").partition("/")
        try:
            fps = float(num) / max(1e-6, float(den or 1))
        except ValueError:
            fps = 30.0
        n = int(stream.get("nb_frames") or 0)
        if n <= 0:
            n = int(round(float((data.get("format") or {}).get("duration") or 0.0) * fps))
        if w > 0 and h > 0:
            return w, h, fps, max(0, n)
    except ProcessDeadlineExceeded:
        raise
    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError, IndexError, ValueError) as exc:
        raise RenderingError(
            stage="render_probe",
            artifact=video_path,
            cause=f"ffprobe failed to probe video {video_path}: {exc}",
        ) from exc
    raise RenderingError(
        stage="render_probe",
        artifact=video_path,
        cause=f"ffprobe returned invalid dimensions for video {video_path}: {w}x{h}",
    )


def _read_exact(stream, nbytes: int, *, deadline: float | None = None) -> bytes | None:
    """Read exactly nbytes from a pipe, or None at EOF."""
    buf = bytearray()
    while len(buf) < nbytes:
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([stream], [], [], remaining)[0]:
                raise ProcessDeadlineExceeded("motion frame decode", MEDIA_TIMEOUT_S)
            chunk = os.read(stream.fileno(), min(nbytes - len(buf), 1 << 20))
        else:
            chunk = stream.read(min(nbytes - len(buf), 1 << 20))
        if not chunk:
            return None
        buf += chunk
    return bytes(buf)


def _decode_gray_frames(
    video_path: Path,
    w_out: int,
    h_out: int,
    wanted: list[int],
    select_expr: str | None,
) -> dict[int, np.ndarray]:
    """Decode `wanted` frame indices as grayscale via one ffmpeg pipe.

    When `select_expr` is given the drop happens inside ffmpeg (only the sampled frames are scaled
    and piped). If the emitted frame count does not line up with the request, the call retries with
    no select filter and indexes the frames in Python, so pairing never silently misaligns.
    stderr is discarded instead of piped, so a chatty decoder cannot fill a 64KB pipe and hang.
    """
    ffmpeg_bin = _resolve_ffmpeg()
    wanted_sorted = sorted(set(wanted))

    def _run(expr: str | None) -> dict[int, np.ndarray]:
        vf = [expr, f"scale={w_out}:{h_out}"] if expr else [f"scale={w_out}:{h_out}"]
        cmd = [
            ffmpeg_bin, "-v", "error", "-i", str(video_path),
            "-vf", ",".join(vf), "-fps_mode", "passthrough", "-an", "-sn",
            "-f", "rawvideo", "-pix_fmt", "gray", "-",
        ]
        frame_bytes = w_out * h_out
        out: dict[int, np.ndarray] = {}
        deadline = time.monotonic() + MEDIA_TIMEOUT_S
        with process_group(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as proc:
            ordinal = 0
            while True:
                raw = _read_exact(proc.stdout, frame_bytes, deadline=deadline)
                if raw is None:
                    break
                if expr is None:
                    if ordinal in wanted_set:
                        out[ordinal] = np.frombuffer(raw, dtype=np.uint8).reshape(h_out, w_out)
                elif ordinal < len(wanted_sorted):
                    out[wanted_sorted[ordinal]] = np.frombuffer(raw, dtype=np.uint8).reshape(h_out, w_out)
                ordinal += 1
            try:
                proc.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired as exc:
                raise ProcessDeadlineExceeded(cmd, MEDIA_TIMEOUT_S) from exc
            finally:
                proc.stdout.close()
        return out

    wanted_set = set(wanted_sorted)
    frames = _run(select_expr)
    if select_expr is not None and len(frames) != len(wanted_sorted):
        frames = _run(None)
    return frames


def _flow_pair_metrics(prev_gray: np.ndarray, cur_gray: np.ndarray, scale: float,
                      win_size: int, blur_k: int, erode_k: int) -> tuple[float, float, float, float | None]:
    """One sampled frame pair -> (mean_flow, angle_std, coverage, shear_ratio|None) in source-pixel units."""
    flow = cv2.calcOpticalFlowFarneback(
        prev_gray, cur_gray, None, 0.5, 3, win_size, 3, 5, 1.2, 0,
    )
    mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1])
    # F_orig = scale * F_low while x_orig = scale * x_low, so magnitudes need the scale factor and
    # dF/dx computed on the raw low-res field is already resolution invariant.
    mag_src = mag * scale
    active = mag_src > 0.12
    coverage = float(np.mean(active))
    if not np.any(active):
        return 0.0, 0.0, coverage, None

    mean_mag = float(mag_src[active].mean())
    angle_std = float(np.std(ang[active]))
    p90_mag = float(np.percentile(mag_src[active], 90))
    if p90_mag < 0.85 or coverage < 0.15:
        return mean_mag, angle_std, coverage, None

    flow_s = cv2.GaussianBlur(flow, (blur_k, blur_k), max(0.5, 5.0 / scale))
    gx_u = cv2.Sobel(flow_s[..., 0], cv2.CV_32F, 1, 0, ksize=3) / 8.0
    gy_u = cv2.Sobel(flow_s[..., 0], cv2.CV_32F, 0, 1, ksize=3) / 8.0
    gx_v = cv2.Sobel(flow_s[..., 1], cv2.CV_32F, 1, 0, ksize=3) / 8.0
    gy_v = cv2.Sobel(flow_s[..., 1], cv2.CV_32F, 0, 1, ksize=3) / 8.0
    grad_mag = np.sqrt(gx_u ** 2 + gy_u ** 2 + gx_v ** 2 + gy_v ** 2)
    active_interior = cv2.erode(active.astype(np.uint8), np.ones((erode_k, erode_k), np.uint8)) > 0
    eval_region = grad_mag[active_interior] if np.any(active_interior) else grad_mag
    shear = float(np.percentile(eval_region, 99.0)) / max(1.25, p90_mag)
    return mean_mag, angle_std, coverage, shear


def _score_motion(mags: list[float], angle_stds: list[float], active_ratios: list[float],
                  shear_ratios: list[float]) -> dict:
    """Fold sampled flow-pair statistics into the Reference Precision & Recall verdict (unchanged math)."""
    mean_mag = float(np.mean(mags))
    mean_angle_std = float(np.mean(angle_stds)) if angle_stds else 0.0
    mean_coverage = float(np.mean(active_ratios)) if active_ratios else 0.0
    mean_shear = float(np.mean(shear_ratios)) if shear_ratios else 0.0
    max_shear = float(np.max(shear_ratios)) if shear_ratios else 0.0

    has_disocclusion_tear = mean_shear > 0.34 or max_shear > 0.55

    if 0.40 <= mean_mag <= 25.0:
        base_prec = min(1.0, 0.82 + 0.18 * (1.0 - abs(mean_mag - 3.5) / 22.0))
    elif mean_mag < 0.40:
        base_prec = max(0.1, mean_mag / 0.40)
    else:
        base_prec = max(0.1, 25.0 / mean_mag)

    if has_disocclusion_tear:
        tear_penalty = max(0.25, 1.0 - (max(mean_shear - 0.30, max_shear - 0.48) * 0.85))
        precision = round(base_prec * tear_penalty, 3)
    else:
        precision = round(base_prec, 3)

    recall = round(min(1.0, 0.55 * min(1.0, mean_angle_std / 0.18) + 0.45 * min(1.0, mean_coverage / 0.50)), 3)

    is_organic = mean_angle_std >= 0.08
    has_momentum = 0.40 <= mean_mag <= 26.0
    if has_disocclusion_tear:
        rating = "DISOCCLUSION_TEAR"
    elif has_momentum and is_organic:
        rating = "EXCELLENT"
    elif has_momentum:
        rating = "GOOD"
    elif mean_mag < 0.45:
        rating = "TOO_STATIC"
    else:
        rating = "EXCESSIVE_TEAR"

    return {
        "valid": rating in ["EXCELLENT", "GOOD"],
        "score": rating,
        "precision": precision,
        "recall": recall,
        "mean_flow_px": round(mean_mag, 2),
        "non_rigidity_std": round(mean_angle_std, 2),
        "flow_shear_ratio": round(mean_shear, 3),
        "max_shear_ratio": round(max_shear, 3),
        "frames_sampled": len(mags),
    }


def verify_motion_quality(video_path: Path, max_frames: int = MOTION_MAX_FRAMES, width: int = MOTION_SAMPLE_WIDTH) -> dict:
    """Measure Optical Flow Precision (smoothness, zero disocclusion tearing) and Recall (3D non-rigidity, active coverage).

    `pipeline.py` and `orchestrator/verifiers.py` call this positionally; the optional keyword args
    only retune the sampler (more pairs / higher decode width) and never change the returned keys.
    """
    if not video_path.exists():
        return {"valid": False, "score": "MISSING", "precision": 0.0, "recall": 0.0, "mean_flow_px": 0.0, "non_rigidity_std": 0.0, "flow_shear_ratio": 0.0}

    max_frames = max(2, int(max_frames))
    src_w, src_h, _fps, n_total = _probe_video_shape(video_path)
    if src_w <= 0 or src_h <= 0:
        return {"valid": False, "score": "ERROR", "precision": 0.0, "recall": 0.0, "reason": "Cannot read video frames"}

    scale = max(1.0, float(max(src_w, src_h)) / float(max(64, int(width))))
    w_out = max(2, int(round(src_w / scale)))
    h_out = max(2, int(round(src_h / scale)))

    gap = MOTION_SAMPLE_GAP
    predecoded: dict[int, np.ndarray] | None = None
    if n_total <= 0:
        # Unknown frame count (no nb_frames/duration metadata): stream every downscaled frame and
        # derive the pair schedule from what actually arrived.
        predecoded = _decode_gray_frames(video_path, w_out, h_out, [], None)
        if not predecoded:
            return {"valid": False, "score": "ERROR", "precision": 0.0, "recall": 0.0, "reason": "Cannot read video frames"}
        n_total = max(predecoded) + 1

    if n_total > gap * max_frames:
        step = max(gap + 1, int(math.ceil((n_total - gap) / max(1, max_frames - 1))))
    else:
        step = gap
    starts = [s for s in range(0, max(0, n_total - gap), step)][:max_frames]
    if not starts:
        return {"valid": False, "score": "TOO_STATIC", "precision": 0.0, "recall": 0.0, "mean_flow_px": 0.0, "non_rigidity_std": 0.0, "flow_shear_ratio": 0.0, "max_shear_ratio": 0.0, "frames_sampled": 0}

    wanted = sorted({s for s in starts} | {s + gap for s in starts})
    if step == gap:
        select_expr = f"select='not(mod(n\\,{step}))'"
    else:
        select_expr = f"select='eq(mod(n\\,{step})\\,0)+eq(mod(n\\,{step})\\,{gap})'"

    frames = predecoded if predecoded is not None else _decode_gray_frames(video_path, w_out, h_out, wanted, select_expr)

    win_size = max(8, int(round(15 / scale)))
    blur_k = max(3, int(round(21 / scale)) | 1)
    erode_k = max(3, int(round(9 / scale)) | 1)

    mags, angle_stds, active_ratios, shear_ratios = [], [], [], []
    for s in starts:
        prev_gray, cur_gray = frames.get(s), frames.get(s + gap)
        if prev_gray is None or cur_gray is None:
            continue
        mean_mag, angle_std, coverage, shear = _flow_pair_metrics(prev_gray, cur_gray, scale, win_size, blur_k, erode_k)
        active_ratios.append(coverage)
        if shear is None and mean_mag == 0.0:
            continue
        mags.append(mean_mag)
        angle_stds.append(angle_std)
        if shear is not None:
            shear_ratios.append(shear)

    if not mags:
        return {"valid": False, "score": "TOO_STATIC", "precision": 0.0, "recall": 0.0, "mean_flow_px": 0.0, "non_rigidity_std": 0.0, "flow_shear_ratio": 0.0, "max_shear_ratio": 0.0, "frames_sampled": 0}

    return _score_motion(mags, angle_stds, active_ratios, shear_ratios)


def _enforce_monotonic_remap(
    map_x: np.ndarray,
    map_y: np.ndarray,
    W: int,
    H: int,
    cam_zoom: float,
    max_elasticity: float = 0.22,
) -> tuple[np.ndarray, np.ndarray]:
    """Guarantee tear-free sampling coordinates while allowing rich 3D perspective foreshortening (±22% elasticity)."""
    base_step = 1.0 / max(1.0, cam_zoom)
    min_step = base_step * (1.0 - max_elasticity)
    max_step = base_step * (1.0 + max_elasticity)

    dx = np.diff(map_x, axis=1)
    if float(dx.min()) < min_step or float(dx.max()) > max_step:
        dx_clamped = np.clip(dx, min_step, max_step)
        mid_x = W // 2
        left_sum = np.cumsum(dx_clamped[:, :mid_x][:, ::-1], axis=1)[:, ::-1]
        right_sum = np.cumsum(dx_clamped[:, mid_x:], axis=1)
        center_col = map_x[:, mid_x:mid_x + 1]
        map_x = np.concatenate([center_col - left_sum, center_col, center_col + right_sum], axis=1)

    dy = np.diff(map_y, axis=0)
    if float(dy.min()) < min_step or float(dy.max()) > max_step:
        dy_clamped = np.clip(dy, min_step, max_step)
        mid_y = H // 2
        top_sum = np.cumsum(dy_clamped[:mid_y, :][::-1, :], axis=0)[::-1, :]
        bot_sum = np.cumsum(dy_clamped[mid_y:, :], axis=0)
        center_row = map_y[mid_y:mid_y + 1, :]
        map_y = np.concatenate([center_row - top_sum, center_row, center_row + bot_sum], axis=0)

    map_x = np.clip(map_x, 1.0, float(W - 2)).astype(np.float32)
    map_y = np.clip(map_y, 1.0, float(H - 2)).astype(np.float32)
    return map_x, map_y


# --------------------------------------------------------------------------- #
# 5. Unified 3-Plane Spatial Decomposition & True 3D Relit Perspective Engine
# --------------------------------------------------------------------------- #
def extract_3d_layers(
    src_img_path: Path,
    target_w: int = 1080,
    target_h: int = 1920,
) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int], np.ndarray, np.ndarray]:
    """Decompose a 2D image into:
      1. `fg_bgra`: Near-Plane RGBA foreground subject cutout (ISNet / GrabCut self-healing)
      2. `bg_bgr`: Inpainted Mid/Far-Plane background plate (SimpleLama / Telea)
      3. `bbox`: Foreground subject bounding box (x1, y1, x2, y2)
      4. `depth_map`: Edge-preserving bilateral continuous depth map Z(x,y) in [0, 1]
      5. `normals`: 3D unit surface normal map N(x,y) = (Nx, Ny, Nz)
    """
    pil_orig = Image.open(src_img_path).convert("RGB")
    if pil_orig.size != (target_w, target_h):
        src_w, src_h = pil_orig.size
        scale = max(target_w / float(src_w), target_h / float(src_h))
        nw, nh = int(round(src_w * scale)), int(round(src_h * scale))
        pil_resized = pil_orig.resize((nw, nh), Image.LANCZOS)
        x0, y0 = (nw - target_w) // 2, (nh - target_h) // 2
        pil_img = pil_resized.crop((x0, y0, x0 + target_w, y0 + target_h))
    else:
        pil_img = pil_orig

    W, H = target_w, target_h
    orig_rgb = np.array(pil_img)
    orig_bgr = cv2.cvtColor(orig_rgb, cv2.COLOR_RGB2BGR)

    depth_map = estimate_depth(pil_img)
    if depth_map.shape != (H, W):
        depth_map = cv2.resize(depth_map, (W, H), interpolation=cv2.INTER_CUBIC)
    normals = _compute_surface_normals(depth_map)

    cutout_rgba = None
    try:
        import rembg
        session = get_rembg_session()
        try:
            cutout_pil = rembg.remove(pil_img, session=session, post_process_mask=True)
        except Exception:
            session = get_rembg_session(force_reset=True)
            cutout_pil = rembg.remove(pil_img, session=session, post_process_mask=True)
        cutout_rgba = np.array(cutout_pil)
        alpha = cutout_rgba[..., 3]
        fg_cov = float(np.mean(alpha > 24))
        if fg_cov < 0.03 or fg_cov > 0.90:
            # Blend with depth-salience mask so foreground subject is cleanly isolated without swallowing the whole room
            fg_prob = np.clip((depth_map - 0.52) / 0.28, 0.0, 1.0)
            yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
            radial = np.exp(-(((xx / W - 0.5) / 0.38) ** 2 + ((yy / H - 0.48) / 0.36) ** 2))
            synth_alpha = (np.clip(fg_prob * radial * 255.0, 0, 255)).astype(np.uint8)
            cutout_rgba[..., 3] = np.maximum(alpha if fg_cov < 0.90 else 0, synth_alpha)
    except Exception:
        fg_prob = np.clip((depth_map - 0.52) / 0.28, 0.0, 1.0)
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        radial = np.exp(-(((xx / W - 0.5) / 0.38) ** 2 + ((yy / H - 0.48) / 0.36) ** 2))
        synth_alpha = cv2.GaussianBlur((np.clip(fg_prob * radial * 255.0, 0, 255)).astype(np.uint8), (15, 15), 4.0)
        cutout_rgba = np.dstack([orig_rgb, synth_alpha])

    # Soften alpha silhouette edge for seamless 3D multi-plane compositing
    alpha = cv2.GaussianBlur(cutout_rgba[..., 3], (9, 9), 2.2)
    cutout_rgba[..., 3] = alpha
    mask = (alpha > 20).astype(np.uint8) * 255

    coords = cv2.findNonZero(mask)
    if coords is not None:
        x, y, w, h = cv2.boundingRect(coords)
        bbox = (x, y, x + w, y + h)
    else:
        bbox = (int(W * 0.2), int(H * 0.28), int(W * 0.8), int(H * 0.72))

    # Dilate mask before background inpainting so zero foreground silhouette halos remain on the background plate
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (29, 29))
    dilated_mask = cv2.dilate(mask, kernel, iterations=2)

    bg_bgr = None
    try:
        from simple_lama_inpainting import SimpleLama
        lama = SimpleLama()
        lama_res = lama(pil_img, Image.fromarray(dilated_mask))
        bg_bgr = cv2.cvtColor(np.array(lama_res), cv2.COLOR_RGB2BGR)
        if bg_bgr.shape[:2] != (H, W):
            bg_bgr = cv2.resize(bg_bgr, (W, H), interpolation=cv2.INTER_LANCZOS4)
        del lama
        _heal_gpu_memory()
    except Exception:
        small_bgr = cv2.resize(orig_bgr, (W // 3, H // 3), interpolation=cv2.INTER_AREA)
        small_mask = cv2.resize(dilated_mask, (W // 3, H // 3), interpolation=cv2.INTER_NEAREST)
        small_inpainted = cv2.inpaint(small_bgr, small_mask, inpaintRadius=9, flags=cv2.INPAINT_TELEA)
        bg_bgr = cv2.resize(small_inpainted, (W, H), interpolation=cv2.INTER_LANCZOS4)

    outer_mask = cv2.dilate(dilated_mask, kernel, iterations=1)
    inv_mask = cv2.GaussianBlur((1.0 - (outer_mask.astype(np.float32) / 255.0)), (27, 27), 8.0)[..., None]
    bg_bgr = (orig_bgr * inv_mask + bg_bgr * (1.0 - inv_mask)).astype(np.uint8)
    fg_bgra = cv2.cvtColor(cutout_rgba, cv2.COLOR_RGBA2BGRA)
    return fg_bgra, bg_bgr, bbox, depth_map, normals


def _crc32_seed(stem: str) -> int:
    """Stable per-clip PRNG seed.

    Never use `hash()` here: CPython randomises str hashing per process (PYTHONHASHSEED), which
    makes renders non-reproducible across runs.
    """
    return zlib.crc32(stem.encode("utf-8")) % 10000


def _generate_3d_particles(num_particles: int = 38, seed: int = 42) -> np.ndarray:
    """Initialize 3D volumetric atmospheric dust/bokeh particles [x_norm, y_norm, z_depth, radius, brightness]."""
    rng = np.random.default_rng(seed)
    pts = np.zeros((num_particles, 5), dtype=np.float32)
    pts[:, 0] = rng.uniform(0.06, 0.94, num_particles)  # X in [0, 1]
    pts[:, 1] = rng.uniform(0.10, 0.90, num_particles)  # Y in [0, 1]
    pts[:, 2] = rng.uniform(0.22, 0.92, num_particles)  # Z depth (0.22=far, 0.92=near lens)
    pts[:, 3] = rng.uniform(1.8, 5.2, num_particles)    # Base radius px
    pts[:, 4] = rng.uniform(0.18, 0.52, num_particles)  # Opacity
    return pts


def render_3d_spatial_scene(
    src_img_path: Path,
    output_path: Path,
    preset: str = "depthflow_orbit",
    duration: float = 3.5,
    fps: int = 30,
    target_w: int = 1080,
    target_h: int = 1920,
    _retry_depth: int = 0,
    render_report: dict | None = None,
) -> bool:
    """Unified True-3D Multi-Plane Spatial & Normal-Relit Perspective Engine (v5.0).

    Combines:
      1. 3-Plane Z-Space Decomposition (Inpainted Far/Mid Environment + Bilateral Depth Field + Near Subject Cutout)
      2. Pinhole 3D Perspective Camera Trajectories (`vertigo`, `spiral`, `orbit`, `roll`, `spatial_drift`, `dolly`)
      3. Dynamic 3D Surface-Normal Relighting & Fresnel Rim Light
      4. Physical Aperture Rack-Focus Depth-of-Field (DoF) & 3D Drop Shadows
      5. Multi-Depth 3D Volumetric Dust / Bokeh Particles

    The compositional path is never silent: the plane mode actually used (plus the reason for any
    single-plane fallback) is recorded in `render_report` when supplied and always printed, so a
    flat fallback can never be reported as a multi-plane render.
    """
    t0 = time.time()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not src_img_path.exists():
        raise FileNotFoundError(f"Source image missing for 3D spatial render: {src_img_path}")

    W, H = (target_w // 2) * 2, (target_h // 2) * 2
    fg_bgra, bg_bgr, bbox, depth_map, normals = extract_3d_layers(src_img_path, target_w=W, target_h=H)

    # Smooth mid/far background depth field for continuous pinhole projection while foreground layer moves independently
    bg_depth = cv2.GaussianBlur(depth_map, (65, 65), 22.0)
    bg_depth_c = (bg_depth - 0.45).astype(np.float32)

    # Precompute bokeh-blurred background plate for physical Rack-Focus DoF
    bg_bokeh = cv2.GaussianBlur(bg_bgr, (27, 27), 8.0)

    # Extract foreground alpha and precompute soft 3D drop shadow mask
    fg_bgr = fg_bgra[..., :3].astype(np.float32)
    fg_alpha = (fg_bgra[..., 3].astype(np.float32) / 255.0)
    fg_coverage = float(np.mean(fg_alpha > 0.1))
    in_coverage_band = 0.03 <= fg_coverage <= 0.78
    use_multiplane = in_coverage_band and (_retry_depth == 0)
    if use_multiplane:
        plane_mode, plane_reason = "multi_plane_3layer", ""
    elif not in_coverage_band:
        plane_mode = "single_plane_flat"
        plane_reason = f"cutout coverage {fg_coverage:.2f} outside the 0.03-0.78 multi-plane band"
    else:
        plane_mode = "single_plane_flat"
        plane_reason = f"self-heal retry depth {_retry_depth} forces the damped flat path"
    if render_report is not None:
        render_report.update(
            {
                "plane_mode": plane_mode,
                "plane_reason": plane_reason,
                "fg_coverage": round(fg_coverage, 4),
                "preset": preset,
                "particle_seed": _crc32_seed(src_img_path.stem),
            }
        )
    if plane_mode != "multi_plane_3layer":
        print(
            f"  [3DSpatialEngine] WARNING {output_path.name}: NOT a multi-plane render "
            f"({plane_reason}). Do not report this clip as 3-plane."
        )

    shadow_mask = cv2.GaussianBlur(fg_alpha, (45, 45), 16.0) * 0.42
    bx1, by1, bx2, by2 = bbox
    subj_cx, subj_cy = (bx1 + bx2) / 2.0, (by1 + by2) / 2.0

    # Precompute Fresnel rim term from 3D surface normals (edges where Nz is small)
    fresnel_rim = np.power(1.0 - np.clip(normals[..., 2], 0.0, 1.0), 1.65)

    grid_x, grid_y = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
    cx, cy = W / 2.0, H / 2.0
    nx = (grid_x - cx) / float(W)

    # Deterministic across runs: hash() is PYTHONHASHSEED-randomised, so the same project would
    # render differently every time and a quality regression could never be bisected.
    particle_seed = _crc32_seed(src_img_path.stem)
    particles = _generate_3d_particles(num_particles=34, seed=particle_seed)
    # Single-plane path: decode/resize the source ONCE. Doing it per frame (the old code reopened
    # the PNG inside the loop) cost roughly 2x the render time and re-decoded identical pixels.
    if use_multiplane:
        flat_plate = flat_bokeh = None
    else:
        with Image.open(src_img_path) as src_im:
            flat_rgb = np.array(src_im.convert("RGB").resize((W, H), Image.LANCZOS))
        flat_plate = cv2.cvtColor(flat_rgb, cv2.COLOR_RGB2BGR)
        flat_bokeh = cv2.GaussianBlur(flat_plate, (25, 25), 7.5)

    total_frames = max(15, int(duration * fps))
    with _open_ffmpeg_writer(output_path, W, H, fps=fps) as proc:
        p_low = preset.lower()
        damp = 0.65 if _retry_depth == 1 else (0.35 if _retry_depth >= 2 else 1.0)

        for i in range(total_frames):
            p = i / max(1, total_frames - 1)
            t = p * p * (3.0 - 2.0 * p)

            cam_zoom = 1.13
            pan_x, pan_y = 0.0, 0.0
            roll_deg = 0.0
            par_x = np.zeros_like(grid_x)
            par_y = np.zeros_like(grid_y)
            fg_shift_x, fg_shift_y = 0.0, 0.0
            fg_scale = 1.0
            fg_tilt = 0.0
            z_focus = 0.62
            dof_strength = 0.35

            if "vertigo" in p_low:
                # Hitchcock Dolly-Zoom: Camera dollys in on foreground subject while background stretches in Z-space
                cam_zoom = 1.12 + 0.04 * t
                vertigo_stretch = 0.048 * (t - 0.5) * damp
                par_x = (grid_x - cx) * bg_depth_c * vertigo_stretch
                par_y = (grid_y - cy) * bg_depth_c * vertigo_stretch
                pan_x = (W * 0.012) * math.sin(p * math.pi)
                fg_scale = 1.02 + 0.035 * (1.0 - t) * damp
                fg_shift_x = -(W * 0.008) * math.sin(p * math.pi) * damp
                z_focus = 0.65
                dof_strength = 0.55 * math.sin(p * math.pi)
            elif "spiral" in p_low:
                # 3D Helical Spiral Ascend: Orbital sweep + vertical crane rise + 3D perspective keystone
                angle = p * math.pi * 1.35
                cam_zoom = 1.14 + 0.05 * math.sin(p * math.pi)
                pan_x = (W * 0.032) * math.sin(angle)
                pan_y = (H * 0.028) * (0.5 - t)
                keystone = (W * 0.010) * (nx * bg_depth_c) * math.sin(angle) * damp
                par_x = ((W * 0.024) * bg_depth_c * math.sin(angle) + (grid_x - cx) * bg_depth_c * (0.018 * t)) * damp + keystone
                par_y = ((H * 0.020) * bg_depth_c * (0.5 - t) + (grid_y - cy) * bg_depth_c * (0.018 * t)) * damp
                roll_deg = 1.15 * math.sin(p * math.pi) * damp
                fg_scale = 1.01 + 0.045 * t * damp
                fg_shift_x = -(W * 0.016) * math.sin(angle) * damp
                fg_shift_y = -(H * 0.012) * (0.5 - t) * damp
                fg_tilt = -0.65 * math.sin(p * math.pi) * damp
                dof_strength = 0.42
            elif "roll" in p_low:
                # Dynamic 3D Z-Axis Roll + Sweeping Lateral Tracking
                cam_zoom = 1.15 + 0.04 * t
                roll_deg = 2.4 * math.sin(p * math.pi) * damp
                pan_x = (W * 0.034) * (t - 0.5)
                pan_y = (H * 0.014) * math.sin(p * 2.0 * math.pi)
                par_x = (W * 0.024) * bg_depth_c * (t - 0.5) * damp
                par_y = (H * 0.014) * bg_depth_c * math.cos(p * math.pi) * damp
                fg_scale = 1.02 + 0.03 * t * damp
                fg_shift_x = -(W * 0.018) * (t - 0.5) * damp
                fg_tilt = 0.85 * math.sin(p * math.pi) * damp
                dof_strength = 0.38
            elif "spatial" in p_low:
                # 3D Spatial Drift + Deep Aperture Rack-Focus from Background to Foreground
                cam_zoom = 1.13 + 0.04 * t
                pan_x = (W * 0.026) * math.sin(p * math.pi)
                pan_y = -(H * 0.020) * math.cos(p * math.pi)
                par_x = (W * 0.022) * bg_depth_c * math.sin(p * math.pi) * damp
                par_y = -(H * 0.018) * bg_depth_c * math.cos(p * math.pi) * damp
                fg_scale = 1.01 + 0.035 * t * damp
                fg_shift_x = -(W * 0.014) * math.sin(p * math.pi) * damp
                z_focus = 0.30 + 0.38 * t
                dof_strength = 0.62 * (1.0 - 0.4 * t)
            elif "dolly" in p_low or "zoom_in" in p_low or "punch" in p_low:
                snap = ((1.0 - math.exp(-5.0 * p)) * 0.06) if "punch" in p_low else 0.0
                cam_zoom = 1.08 + 0.11 * t + snap
                par_x = (grid_x - cx) * bg_depth_c * (0.030 * t * damp)
                par_y = (grid_y - cy) * bg_depth_c * (0.030 * t * damp)
                fg_scale = 1.0 + (0.055 * t + snap * 0.5) * damp
                dof_strength = 0.30 + 0.25 * t
            elif "zoom_out" in p_low or "dolly_out" in p_low:
                cam_zoom = 1.20 - 0.11 * t
                par_x = (grid_x - cx) * bg_depth_c * (0.028 * (1.0 - t) * damp)
                par_y = (grid_y - cy) * bg_depth_c * (0.028 * (1.0 - t) * damp)
                fg_scale = 1.05 - 0.045 * t * damp
                dof_strength = 0.45 * (1.0 - t)
            else:  # orbit / orbital / horizontal / vertical
                angle = p * math.pi * 1.25
                cam_zoom = 1.14 + 0.04 * math.sin(p * math.pi)
                pan_x = (W * 0.032) * math.sin(angle)
                pan_y = (H * 0.018) * math.cos(angle)
                keystone_x = (W * 0.010) * (nx * bg_depth_c) * math.sin(angle) * damp
                par_x = (W * 0.024) * bg_depth_c * math.sin(angle) * damp + keystone_x
                par_y = (H * 0.016) * bg_depth_c * math.cos(angle) * damp
                fg_scale = 1.01 + 0.035 * math.sin(p * math.pi) * damp
                fg_shift_x = -(W * 0.016) * math.sin(angle) * damp
                fg_shift_y = -(H * 0.009) * math.cos(angle) * damp
                dof_strength = 0.40

            # 1. Apply 3D camera roll & perspective warp to the background/midground plate
            dx_c = grid_x - cx
            dy_c = grid_y - cy
            if abs(roll_deg) > 1e-3:
                rad = math.radians(roll_deg)
                cr, sr = math.cos(rad), math.sin(rad)
                rx = dx_c * cr - dy_c * sr
                ry = dx_c * sr + dy_c * cr
            else:
                rx, ry = dx_c, dy_c

            max_par_x = float(np.max(np.abs(par_x))) + abs(pan_x) + abs(math.sin(math.radians(roll_deg))) * H * 0.5
            max_par_y = float(np.max(np.abs(par_y))) + abs(pan_y) + abs(math.sin(math.radians(roll_deg))) * W * 0.5
            req_zoom_x = (cx + max_par_x) / max(1.0, cx - 4.0)
            req_zoom_y = (cy + max_par_y) / max(1.0, cy - 4.0)
            safe_zoom = max(cam_zoom, req_zoom_x * 1.01, req_zoom_y * 1.01)

            map_x = cx + (rx + pan_x) / safe_zoom - par_x
            map_y = cy + (ry + pan_y) / safe_zoom - par_y
            map_x, map_y = _enforce_monotonic_remap(map_x, map_y, W, H, safe_zoom)

            # Physical Aperture Rack-Focus DoF on background plate
            base_plate = bg_bgr if use_multiplane else flat_plate
            if dof_strength > 0.02:
                coc = np.clip(np.abs(depth_map - z_focus) * 2.1 * dof_strength, 0.0, 0.85)[..., None].astype(np.float32)
                bokeh_plate = bg_bokeh if use_multiplane else flat_bokeh
                dof_plate = (base_plate.astype(np.float32) * (1.0 - coc) + bokeh_plate.astype(np.float32) * coc).astype(np.uint8)
            else:
                dof_plate = base_plate

            warped_bg = cv2.remap(dof_plate, map_x, map_y, interpolation=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE).astype(np.float32)

            # 2. Multi-Plane Foreground Subject Projection + Dynamic 3D Drop Shadow
            if use_multiplane:
                # Cast 3D shadow onto the midground opposite the moving light source
                sh_dx = int(round(fg_shift_x * 1.35 + 14.0 * math.cos(p * math.pi)))
                sh_dy = int(round(fg_shift_y * 1.35 + 10.0))
                sh_mat = np.float32([[1.0, 0.0, sh_dx], [0.0, 1.0, sh_dy]])
                warped_shadow = cv2.warpAffine(shadow_mask, sh_mat, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)[..., None]
                warped_bg = warped_bg * (1.0 - warped_shadow)

                # Warp foreground subject plane at its near-plane 1/Z scale & tilt
                total_fg_zoom = safe_zoom * fg_scale
                fg_mat = cv2.getRotationMatrix2D((subj_cx, subj_cy), fg_tilt - roll_deg * 0.65, total_fg_zoom)
                fg_mat[0, 2] += fg_shift_x - pan_x / safe_zoom
                fg_mat[1, 2] += fg_shift_y - pan_y / safe_zoom
                warped_fg_bgr = cv2.warpAffine(fg_bgr, fg_mat, (W, H), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT)
                warped_fg_alpha = cv2.warpAffine(fg_alpha, fg_mat, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)[..., None]
                comp = warped_fg_bgr * warped_fg_alpha + warped_bg * (1.0 - warped_fg_alpha)
            else:
                comp = warped_bg

            # 3. Dynamic 3D Surface-Normal Relighting & Fresnel Rim Light
            light_angle = (p - 0.5) * math.pi * 1.4
            lx = 0.55 * math.sin(light_angle)
            ly = -0.32 + 0.18 * math.cos(light_angle)
            lz = 0.78
            l_norm = math.sqrt(lx * lx + ly * ly + lz * lz)
            lx, ly, lz = lx / l_norm, ly / l_norm, lz / l_norm

            ndotl = np.clip(normals[..., 0] * lx + normals[..., 1] * ly + normals[..., 2] * lz, 0.0, 1.0)
            # Warm tungsten directional key highlight + cool cyan Fresnel rim wrap on 3D edges
            key_boost = (ndotl - 0.45) * 0.11 * damp
            rim_mask = (fresnel_rim * np.clip(depth_map - 0.35, 0.0, 1.0) * 0.16 * damp)[..., None]
            comp[..., 2] = np.clip(comp[..., 2] * (1.0 + key_boost) + rim_mask[..., 0] * 45.0, 0.0, 255.0)  # R (warm key)
            comp[..., 1] = np.clip(comp[..., 1] * (1.0 + key_boost * 0.85) + rim_mask[..., 0] * 185.0, 0.0, 255.0)  # G
            comp[..., 0] = np.clip(comp[..., 0] * (1.0 + key_boost * 0.55) + rim_mask[..., 0] * 235.0, 0.0, 255.0)  # B (cyan Fresnel rim)

            frame_u8 = np.clip(comp, 0, 255).astype(np.uint8)

            # 4. Multi-Depth 3D Volumetric Dust / Bokeh Particles (1/Z Parallax)
            if damp > 0.4:
                overlay_p = frame_u8.copy()
                for pt in particles:
                    px_n, py_n, pz, prad, _popa = float(pt[0]), float(pt[1]), float(pt[2]), float(pt[3]), float(pt[4])
                    # Near particles (pz -> 0.9) move 3.5x faster than far particles (pz -> 0.2)
                    px_cur = int((px_n * W - (pan_x + fg_shift_x * 1.8) * (0.4 + 1.8 * pz) + math.sin(p * math.pi * 2.0 + pz * 9.0) * 14.0) % W)
                    py_cur = int((py_n * H - (pan_y + i * 0.45 * pz)) % H)
                    r_px = max(1, int(round(prad * (0.6 + 0.9 * pz))))
                    col = (235, 225, 195) if pz < 0.6 else (255, 235, 180)
                    cv2.circle(overlay_p, (px_cur, py_cur), r_px, col, -1, lineType=cv2.LINE_AA)
                frame_u8 = cv2.addWeighted(frame_u8, 0.90, cv2.GaussianBlur(overlay_p, (5, 5), 1.4), 0.10, 0)

            proc.write(frame_u8)

        enc_ok, enc_why = proc.finish()
    if not enc_ok:
        print(f"  [3DSpatialEngine] ENCODE FAILED {output_path.name}: {enc_why}")
        return False

    q = verify_motion_quality(output_path)
    if not q.get("valid", True) and _retry_depth < 2:
        print(
            f"  [Self-Heal: 3DSpatialEngine] {output_path.name} flagged {q.get('score')} "
            f"(shear={q.get('flow_shear_ratio')}) -> adjusting 3D plane damping and re-rendering..."
        )
        return render_3d_spatial_scene(
            src_img_path=src_img_path,
            output_path=output_path,
            preset=preset,
            duration=duration,
            fps=fps,
            target_w=W,
            target_h=H,
            _retry_depth=_retry_depth + 1,
            render_report=render_report,
        )

    valid = bool(q.get("valid", True))
    print(
        f"  [3DSpatialEngine] {output_path.name} ({preset}, {plane_mode}, {duration:.1f}s) in {time.time() - t0:.1f}s | "
        f"Score={q['score']} Precision={q.get('precision')} Recall={q.get('recall')} "
        f"(flow={q.get('mean_flow_px')}px, shear={q.get('flow_shear_ratio')})"
        + ("" if valid else " -> REJECTED by motion gate")
    )
    if render_report is not None:
        render_report.update({"motion_valid": valid, "motion_score": q.get("score")})
    return valid


# Aliases so studio_3d.py and pipeline.py route directly into the Unified 3D Spatial Engine
def render_depthflow_scene(
    src_img_path: Path,
    output_path: Path,
    preset: str = "depthflow_orbit",
    duration: float = 3.5,
    fps: int = 30,
    target_w: int = 1080,
    target_h: int = 1920,
    render_report: dict | None = None,
) -> bool:
    """Route all 3D scene renders through the Unified 3-Plane Spatial & Normal-Relit 3D Engine."""
    return render_3d_spatial_scene(
        src_img_path=src_img_path,
        output_path=output_path,
        preset=preset,
        duration=duration,
        fps=fps,
        target_w=target_w,
        target_h=target_h,
        render_report=render_report,
    )


def generate_hybrid_motion_clip(
    src_img_path: Path,
    output_path: Path,
    preset: str = "depthflow_orbit",
    duration: float = 3.5,
    fps: int = 30,
    target_w: int = 1080,
    target_h: int = 1920,
    apply_ntsc: bool = False,
) -> bool:
    """Unified entry point for pipeline.py 3D scene rendering."""
    return render_3d_spatial_scene(
        src_img_path=src_img_path,
        output_path=output_path,
        preset=preset,
        duration=duration,
        fps=fps,
        target_w=target_w,
        target_h=target_h,
    )


# --------------------------------------------------------------------------- #
# 6. Procedural & Depth-Displaced 3D Wavefront (.obj) Mesh Engine & BlenderBridge
# --------------------------------------------------------------------------- #
def generate_procedural_3d_obj(
    archetype: str,
    output_obj: Path,
    image_path: Path | None = None,
    grid_res: int = 64,
) -> Path:
    """Generate a Wavefront .obj 3D mesh model (procedural 3D geometry or Depth-Anything-V2 3D relief mesh)."""
    output_obj.parent.mkdir(parents=True, exist_ok=True)
    arch = archetype.lower().strip()
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []

    if arch == "depth_mesh" or (image_path is not None and image_path.exists()):
        src_img = Image.open(image_path).convert("RGB") if (image_path and image_path.exists()) else Image.new("RGB", (512, 512), (20, 30, 45))
        depth = estimate_depth(src_img)
        depth_s = cv2.resize(depth, (grid_res, grid_res), interpolation=cv2.INTER_CUBIC)
        depth_s = cv2.GaussianBlur(depth_s, (5, 5), 1.2)
        for r in range(grid_res):
            y = (0.5 - r / float(grid_res - 1)) * 2.4
            for c in range(grid_res):
                x = (c / float(grid_res - 1) - 0.5) * 1.6
                z = (float(depth_s[r, c]) - 0.5) * 0.85
                verts.append((x, y, z))
        for r in range(grid_res - 1):
            for c in range(grid_res - 1):
                i0 = r * grid_res + c + 1
                i1 = i0 + 1
                i2 = (r + 1) * grid_res + c + 1
                i3 = i2 + 1
                faces.append((i0, i2, i1))
                faces.append((i1, i2, i3))
    elif "labyrinth" in arch or "monolith" in arch:
        for ring_idx, (rad_in, rad_out, h_top) in enumerate([(0.25, 0.42, 0.95), (0.55, 0.72, 0.65), (0.85, 1.02, 0.40)]):
            segs = 28
            base_idx = len(verts) + 1
            for s in range(segs):
                ang = 2.0 * math.pi * s / segs
                ca, sa = math.cos(ang), math.sin(ang)
                notch = -0.25 if (s + ring_idx * 5) % 7 == 0 else h_top
                verts.append((rad_in * ca, -0.65, rad_in * sa))
                verts.append((rad_out * ca, -0.65, rad_out * sa))
                verts.append((rad_out * ca, notch, rad_out * sa))
                verts.append((rad_in * ca, notch, rad_in * sa))
            for s in range(segs):
                ns = (s + 1) % segs
                b0 = base_idx + s * 4
                b1 = base_idx + ns * 4
                faces.append((b0 + 1, b1 + 1, b1 + 2))
                faces.append((b0 + 1, b1 + 2, b0 + 2))
                faces.append((b0 + 3, b1 + 2, b0 + 2))
                faces.append((b0 + 3, b1 + 3, b1 + 2))
                faces.append((b0, b0 + 3, b1 + 3))
                faces.append((b0, b1 + 3, b1))
    else:
        lat_n, lon_n = 20, 32
        for i in range(lat_n + 1):
            theta = math.pi * i / lat_n
            st, ct = math.sin(theta), math.cos(theta)
            for j in range(lon_n):
                phi = 2.0 * math.pi * j / lon_n
                r_mod = 0.78 + 0.08 * math.sin(4.0 * theta) * math.cos(5.0 * phi)
                x = r_mod * st * math.cos(phi)
                y = r_mod * ct * 1.12
                z = r_mod * st * math.sin(phi)
                verts.append((x, y, z))
        for i in range(lat_n):
            for j in range(lon_n):
                nj = (j + 1) % lon_n
                i0 = i * lon_n + j + 1
                i1 = i * lon_n + nj + 1
                i2 = (i + 1) * lon_n + j + 1
                i3 = (i + 1) * lon_n + nj + 1
                faces.append((i0, i2, i1))
                faces.append((i1, i2, i3))
        ring_base = len(verts) + 1
        r_segs = 36
        for s in range(r_segs):
            ang = 2.0 * math.pi * s / r_segs
            rx, rz = 1.22 * math.cos(ang), 1.22 * math.sin(ang)
            ry = 0.22 * math.sin(ang)
            verts.append((rx, ry - 0.04, rz))
            verts.append((rx * 1.06, ry + 0.04, rz * 1.06))
        for s in range(r_segs):
            ns = (s + 1) % r_segs
            b0 = ring_base + s * 2
            b1 = ring_base + ns * 2
            faces.append((b0, b1, b1 + 1))
            faces.append((b0, b1 + 1, b0 + 1))

    lines = ["# FrameForge SOTA Procedural 3D Mesh (.obj)", f"# Archetype: {archetype}"]
    for vx, vy, vz in verts:
        lines.append(f"v {vx:.5f} {vy:.5f} {vz:.5f}")
    for f0, f1, f2 in faces:
        lines.append(f"f {f0} {f1} {f2}")
    output_obj.write_text("\n".join(lines) + "\n")
    print(f"  [3D Model Generator] Saved {len(verts)} vertices, {len(faces)} faces -> {output_obj.name}")
    return output_obj


def render_obj_mesh_native(
    obj_path: Path,
    output_mp4: Path,
    duration: float = 3.5,
    fps: int = 30,
    width: int = 1080,
    height: int = 1920,
    preset: str = "orbit",
) -> bool:
    """Render any Wavefront .obj 3D mesh with true 3D perspective camera projection, Lambertian + Rim PBR shading,
    z-sorted triangles, glowing wireframe telemetry, and volumetric bloom."""
    t0 = time.time()
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    if not obj_path.exists():
        generate_procedural_3d_obj("neural_core", obj_path)

    verts_list = []
    faces_list = []
    for raw_line in obj_path.read_text(errors="ignore").splitlines():
        line = raw_line.strip()
        if line.startswith("v "):
            parts = line.split()
            if len(parts) >= 4:
                verts_list.append([float(parts[1]), float(parts[2]), float(parts[3])])
        elif line.startswith("f "):
            parts = line.split()[1:]
            idx = [int(p.split("/")[0]) - 1 for p in parts if p.split("/")[0].lstrip("-").isdigit()]
            if len(idx) >= 3:
                for k in range(1, len(idx) - 1):
                    faces_list.append([idx[0], idx[k], idx[k + 1]])

    if not verts_list or not faces_list:
        generate_procedural_3d_obj("neural_core", obj_path)
        return render_obj_mesh_native(obj_path, output_mp4, duration, fps, width, height, preset)

    V = np.array(verts_list, dtype=np.float32)
    v_center = V.mean(axis=0)
    V = V - v_center
    max_r = max(1e-5, float(np.max(np.linalg.norm(V, axis=1))))
    V = V / max_r * 1.15
    F = np.array(faces_list, dtype=np.int32)
    F = np.clip(F, 0, len(V) - 1)

    total_frames = max(15, int(duration * fps))
    with _open_ffmpeg_writer(output_mp4, width, height, fps=fps) as proc:
        yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
        cx, cy = width / 2.0, height / 2.0
        rad2 = ((xx - cx) / (width * 0.55)) ** 2 + ((yy - cy) / (height * 0.45)) ** 2
        glow = np.exp(-rad2 * 1.4)
        base_bg = np.zeros((height, width, 3), dtype=np.uint8)
        base_bg[:, :, 0] = np.clip(14 + glow * 52, 0, 255).astype(np.uint8)
        base_bg[:, :, 1] = np.clip(10 + glow * 34, 0, 255).astype(np.uint8)
        base_bg[:, :, 2] = np.clip(8 + glow * 16, 0, 255).astype(np.uint8)

        focal_base = min(width, height) * 1.18
        light_dir = np.array([0.55, 0.45, -0.70], dtype=np.float32)
        light_dir /= np.linalg.norm(light_dir)

        p_low = preset.lower()
        for i in range(total_frames):
            p = i / max(1, total_frames - 1)
            t = p * p * (3.0 - 2.0 * p)

            if "vertigo" in p_low:
                yaw = 0.55 * (p - 0.5)
                pitch = 0.18 + 0.12 * math.sin(p * math.pi)
                roll = 0.0
                cam_dist = 3.2 - 1.15 * t
                focal = focal_base * (cam_dist / 2.65)
            elif "spiral" in p_low:
                yaw = 1.35 * p - 0.4
                pitch = 0.35 - 0.45 * t
                roll = 0.06 * math.sin(p * math.pi)
                cam_dist = 2.85 - 0.35 * t
                focal = focal_base
            elif "roll" in p_low:
                yaw = 0.65 * (p - 0.5)
                pitch = 0.20
                roll = 0.24 * math.sin(p * math.pi)
                cam_dist = 2.70 - 0.25 * t
                focal = focal_base
            else:
                yaw = 1.10 * (p - 0.35)
                pitch = 0.22 + 0.12 * math.cos(p * math.pi)
                roll = 0.03 * math.sin(p * math.pi * 2.0)
                cam_dist = 2.75 - 0.25 * math.sin(p * math.pi)
                focal = focal_base

            cy_a, sy_a = math.cos(yaw), math.sin(yaw)
            cp_a, sp_a = math.cos(pitch), math.sin(pitch)
            cr_a, sr_a = math.cos(roll), math.sin(roll)

            Ry = np.array([[cy_a, 0.0, sy_a], [0.0, 1.0, 0.0], [-sy_a, 0.0, cy_a]], dtype=np.float32)
            Rx = np.array([[1.0, 0.0, 0.0], [0.0, cp_a, -sp_a], [0.0, sp_a, cp_a]], dtype=np.float32)
            Rz = np.array([[cr_a, -sr_a, 0.0], [sr_a, cr_a, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32)
            R = Rz @ Rx @ Ry

            Vw = V @ R.T
            Vw[:, 2] += cam_dist
            z_safe = np.maximum(0.25, Vw[:, 2])
            px = cx + (Vw[:, 0] / z_safe) * focal
            py = cy - (Vw[:, 1] / z_safe) * focal
            pts_2d = np.stack([px, py], axis=1).astype(np.int32)

            v0 = Vw[F[:, 0]]
            v1 = Vw[F[:, 1]]
            v2 = Vw[F[:, 2]]
            fn = np.cross(v1 - v0, v2 - v0)
            fn_norm = np.linalg.norm(fn, axis=1, keepdims=True) + 1e-6
            fn = fn / fn_norm

            face_z = (v0[:, 2] + v1[:, 2] + v2[:, 2]) / 3.0
            order = np.argsort(-face_z)

            ndotl = np.abs(np.sum(fn * light_dir[None, :], axis=1))
            rim = np.power(1.0 - np.clip(np.abs(fn[:, 2]), 0.0, 1.0), 1.8)

            frame = base_bg.copy()
            wire_layer = np.zeros_like(frame)
            tri_pts = pts_2d[F]

            for f_idx in order:
                tri = tri_pts[f_idx]
                d_val = float(ndotl[f_idx])
                r_val = float(rim[f_idx])
                b_col = int(np.clip(28 + 165 * d_val + 95 * r_val, 15, 255))
                g_col = int(np.clip(22 + 135 * d_val + 75 * r_val, 12, 245))
                r_col = int(np.clip(14 + 45 * d_val + 110 * (r_val ** 2), 10, 235))
                cv2.fillConvexPoly(frame, tri, (b_col, g_col, r_col), lineType=cv2.LINE_AA)
                if f_idx % 2 == 0:
                    cv2.polylines(wire_layer, [tri], True, (255, 215, 40), 1, lineType=cv2.LINE_AA)

            bloom = cv2.GaussianBlur(wire_layer, (15, 15), 4.0)
            frame = cv2.addWeighted(frame, 1.0, wire_layer, 0.55, 0)
            frame = cv2.addWeighted(frame, 1.0, bloom, 0.65, 0)
            proc.write(frame)

        enc_ok, enc_why = proc.finish()
    if not enc_ok:
        print(f"  [Native3DMesh] ENCODE FAILED {output_mp4.name}: {enc_why}")
        return False

    q = verify_motion_quality(output_mp4)
    print(f"  [Native3DMesh] {output_mp4.name} ({preset}) in {time.time()-t0:.1f}s | Score={q['score']} Precision={q.get('precision')} Recall={q.get('recall')}")
    return output_mp4.exists()


class BlenderBridge:
    """Headless 3D rendering bridge to Blender."""

    @staticmethod
    def get_blender_path() -> str | None:
        which_path = shutil.which("blender")
        if which_path:
            return which_path
        app_path = Path("/Applications/Blender.app/Contents/MacOS/Blender")
        if app_path.exists():
            return str(app_path)
        return None

    @classmethod
    def is_available(cls) -> bool:
        return cls.get_blender_path() is not None

    @classmethod
    def render_mesh(
        cls,
        obj_path: Path,
        output_mp4: Path,
        duration: float = 3.5,
        fps: int = 30,
        width: int = 1080,
        height: int = 1920,
        preset: str = "orbit",
    ) -> bool:
        output_mp4.parent.mkdir(parents=True, exist_ok=True)
        blender_bin = cls.get_blender_path()
        if not blender_bin:
            raise RenderingError(
                stage="render",
                artifact=output_mp4,
                cause="Blender is not installed or not found on PATH. Auto-fallback to native mesh engine is prohibited per Rule B.",
            )
        script = f"""
import bpy, math
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.resolution_x = {width}
scene.render.resolution_y = {height}
scene.render.fps = {fps}
scene.frame_end = int({duration} * {fps})
scene.render.image_settings.file_format = 'FFMPEG'
scene.render.ffmpeg.format = 'MPEG4'
scene.render.ffmpeg.codec = 'H264'
scene.render.filepath = '{str(output_mp4)}'

cam_data = bpy.data.cameras.new('Camera')
cam = bpy.data.objects.new('Camera', cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
cam.location = (0, -4.5, 1.2)
cam.rotation_euler = (math.radians(75), 0, 0)

light_data = bpy.data.lights.new('KeyLight', type='SUN')
light = bpy.data.objects.new('KeyLight', light_data)
scene.collection.objects.link(light)
light.rotation_euler = (math.radians(45), math.radians(30), 0)

if hasattr(bpy.ops.wm, 'obj_import'):
    bpy.ops.wm.obj_import(filepath='{str(obj_path)}')
else:
    bpy.ops.import_scene.obj(filepath='{str(obj_path)}')
bpy.ops.render.render(animation=True)
"""
        tmp_script = output_mp4.parent / "_blender_tmp_render.py"
        tmp_script.write_text(script)
        try:
            run_process([blender_bin, "-b", "-P", str(tmp_script)], check=True,
                        capture_output=True, timeout_s=BLENDER_TIMEOUT_S)
            if output_mp4.exists():
                return True
        except Exception as e:
            print(f"  [BlenderBridge] Blender CLI error ({e}); using Native 3D Mesh Engine...")
        finally:
            tmp_script.unlink(missing_ok=True)
        return render_obj_mesh_native(obj_path, output_mp4, duration, fps, width, height, preset)


def main() -> int:
    ap = argparse.ArgumentParser(description="FrameForge Unified 3D Spatial & Multi-Plane Engine (v5.0)")
    ap.add_argument("--project", type=Path, help="Generate & verify FLUX images for a project.json")
    ap.add_argument("--overwrite", action="store_true", help="Overwrite existing images")
    ap.add_argument("--image", type=Path, help="Input image to render into a 3D spatial clip")
    ap.add_argument("--output", type=Path, help="Output MP4 path")
    ap.add_argument("--preset", type=str, default="depthflow_orbit", help="3D camera trajectory preset")
    ap.add_argument("--duration", type=float, default=3.5, help="Clip duration in seconds")
    args = ap.parse_args()

    if args.project:
        return process_project(args.project.resolve(), overwrite=args.overwrite)
    if args.image and args.output:
        ok = render_3d_spatial_scene(args.image.resolve(), args.output.resolve(), preset=args.preset, duration=args.duration)
        return 0 if ok else 1
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
