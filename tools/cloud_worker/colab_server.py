#!/usr/bin/env python3
"""FrameForge Google Colab Cloud Worker Gateway (tools/cloud_worker/colab_server.py).

Runs headlessly inside a Google Colab GPU session (12GB T4/L4 VRAM + 5TB Google Drive).
Exposes a high-speed FastAPI endpoint connected via free cloudflared tunnel.

Features:
  1. Zero-FUSE Latency Staging:
     - Copies active checkpoints from 5TB Drive (/content/drive/MyDrive/models/)
       to local 60GB NVMe (/content/) for maximum PyTorch throughput.
  2. Multi-Archetype Remote Rendering:
     - Remote execution of Cinematic Photobook, Stickman Explainer, and Hybrid Canvas.
  3. Real-Time Telemetry:
     - Reports GPU VRAM allocation, CUDA health, and Drive mount status.
"""

from __future__ import annotations

import base64
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
    import uvicorn
except ImportError:
    uvicorn = None  # type: ignore

    class _FallbackBaseModel:
        """Lightweight Pydantic-compatible model fallback when FastAPI/Pydantic are not installed."""

        def __init__(self, **kwargs: Any) -> None:
            for cls in reversed(self.__class__.__mro__):
                if cls is object or cls is _FallbackBaseModel:
                    continue
                for k, v in cls.__dict__.items():
                    if not k.startswith("_") and not callable(v):
                        setattr(self, k, v)
                ann = getattr(cls, "__annotations__", {})
                for k in ann:
                    if not hasattr(self, k):
                        setattr(self, k, None)
            for k, v in kwargs.items():
                setattr(self, k, v)

        def model_dump(self) -> Dict[str, Any]:
            return dict(self.__dict__)

        def dict(self) -> Dict[str, Any]:
            return dict(self.__dict__)

    class _FallbackHTTPException(Exception):
        def __init__(self, status_code: int = 500, detail: str = "") -> None:
            super().__init__(f"HTTP {status_code}: {detail}")
            self.status_code = status_code
            self.detail = detail

    class _FallbackFastAPI:
        def __init__(self, title: str = "", version: str = "1.0.0", **kwargs: Any) -> None:
            self.title = title
            self.version = version
            self.extra = kwargs
            self.routes: List[Dict[str, Any]] = []

        def get(self, path: str, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
            def _decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
                self.routes.append({"method": "GET", "path": path, "endpoint": fn, **kwargs})
                return fn
            return _decorator

        def post(self, path: str, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
            def _decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
                self.routes.append({"method": "POST", "path": path, "endpoint": fn, **kwargs})
                return fn
            return _decorator

    FastAPI = _FallbackFastAPI  # type: ignore
    BaseModel = _FallbackBaseModel  # type: ignore
    HTTPException = _FallbackHTTPException  # type: ignore

app = FastAPI(title="FrameForge Colab GPU Gateway", version="1.0.0")


# ---------------------------------------------------------------------------
# SCHEMAS
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    cuda_available: bool
    gpu_name: str
    vram_total_gb: float
    vram_allocated_gb: float
    drive_mounted: bool
    local_disk_free_gb: float


class SyncModelRequest(BaseModel):
    model_filename: str
    drive_dir: str = "/content/drive/MyDrive/FrameForge_Models"
    local_dir: str = "/content/models"


class RenderPhotobookRequest(BaseModel):
    image_base64: str
    style: str = "magnates_amber"
    trajectory: str = "magnates_drift"
    duration: float = 3.5
    fps: int = 30
    width: int = 1080
    height: int = 1920


class RenderStickmanRequest(BaseModel):
    pose: str = "thinking"
    mouth: str = "neutral"
    accessory: str = "flat_cap"
    prop: Optional[str] = "magnifying_glass"
    caption: Optional[str] = None
    duration: float = 3.5
    fps: int = 30
    width: int = 1080
    height: int = 1920


class RenderHybridRequest(BaseModel):
    image_base64: Optional[str] = None
    title: str = "FIND THE FLAW"
    pose: str = "pointing"
    mouth: str = "neutral"
    accessory: str = "flat_cap"
    prop: Optional[str] = "magnifying_glass"
    style: str = "magnates_amber"
    trajectory: str = "magnates_drift"
    duration: float = 3.5
    fps: int = 30
    width: int = 1080
    height: int = 1920


class RenderResponse(BaseModel):
    success: bool
    duration_sec: float
    video_base64: str
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# ENDPOINTS
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Returns GPU telemetry, VRAM status, and Drive mount state."""
    cuda_avail = False
    gpu_name = "CPU Only"
    total_vram = 0.0
    alloc_vram = 0.0

    try:
        import torch
        if torch.cuda.is_available():
            cuda_avail = True
            gpu_name = torch.cuda.get_device_name(0)
            total_vram = round(torch.cuda.get_device_properties(0).total_memory / (1024 ** 3), 2)
            alloc_vram = round(torch.cuda.memory_allocated(0) / (1024 ** 3), 2)
    except Exception:
        pass

    drive_mounted = Path("/content/drive/MyDrive").exists()
    disk_free = round(shutil.disk_usage("/content").free / (1024 ** 3), 2) if Path("/content").exists() else 0.0

    return HealthResponse(
        status="healthy",
        cuda_available=cuda_avail,
        gpu_name=gpu_name,
        vram_total_gb=total_vram,
        vram_allocated_gb=alloc_vram,
        drive_mounted=drive_mounted,
        local_disk_free_gb=disk_free,
    )


@app.post("/sync_model")
def sync_model(req: SyncModelRequest) -> Dict[str, Any]:
    """Copies a model checkpoint from 5TB Google Drive to fast local NVMe."""
    safe_filename = Path(req.model_filename).name
    drive_src = (Path(req.drive_dir) / safe_filename).resolve()
    local_dst = (Path(req.local_dir) / safe_filename).resolve()

    if not drive_src.exists():
        raise HTTPException(status_code=404, detail=f"Model not found on Google Drive: {drive_src}")

    local_dst.parent.mkdir(parents=True, exist_ok=True)
    if not local_dst.exists() or local_dst.stat().st_size != drive_src.stat().st_size:
        shutil.copy2(drive_src, local_dst)

    return {
        "synced": True,
        "local_path": str(local_dst),
        "size_mb": round(local_dst.stat().st_size / (1024 * 1024), 2),
    }


@app.post("/render/photobook", response_model=RenderResponse)
def render_photobook_api(req: RenderPhotobookRequest) -> RenderResponse:
    """Renders a cinematic photobook clip on Colab GPU and returns base64 MP4."""
    try:
        import cv2
        import numpy as np
        from tools import photobook_engine

        img_bytes = base64.b64decode(req.image_base64)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return RenderResponse(success=False, duration_sec=0.0, video_base64="", error="Invalid image_base64 payload")

        layers = photobook_engine.decompose_single_image(img, req.width, req.height)
        out_mp4 = Path(tempfile.gettempdir()) / f"photobook_{uuid.uuid4().hex}.mp4"

        ok = photobook_engine.render_photobook_scene(
            layers=layers,
            output_path=out_mp4,
            style=req.style,
            trajectory=req.trajectory,
            duration=req.duration,
            fps=req.fps,
            width=req.width,
            height=req.height,
        )

        if not ok or not out_mp4.exists():
            return RenderResponse(success=False, duration_sec=0.0, video_base64="", error="Render failed")

        vid_bytes = out_mp4.read_bytes()
        out_mp4.unlink(missing_ok=True)
        return RenderResponse(
            success=True,
            duration_sec=req.duration,
            video_base64=base64.b64encode(vid_bytes).decode("utf-8"),
        )
    except Exception as exc:
        return RenderResponse(success=False, duration_sec=0.0, video_base64="", error=str(exc))


@app.post("/render/stickman", response_model=RenderResponse)
def render_stickman_api(req: RenderStickmanRequest) -> RenderResponse:
    """Renders an expressive 2D vector stickman scene clip and returns base64 MP4."""
    try:
        from tools import stickman_engine

        out_mp4 = Path(tempfile.gettempdir()) / f"stickman_{uuid.uuid4().hex}.mp4"
        pose_spec = stickman_engine.StickmanPoseSpec(pose=req.pose, mouth=req.mouth, prop=req.prop)
        app_spec = stickman_engine.StickmanAppearance(accessory=req.accessory)
        ok = stickman_engine.render_stickman_scene(
            pose_spec=pose_spec,
            app=app_spec,
            output_path=out_mp4,
            caption_text=req.caption,
            duration=req.duration,
            fps=req.fps,
            width=req.width,
            height=req.height,
        )
        if not ok or not out_mp4.exists():
            return RenderResponse(success=False, duration_sec=0.0, video_base64="", error="Stickman render failed")

        vid_bytes = out_mp4.read_bytes()
        out_mp4.unlink(missing_ok=True)
        return RenderResponse(
            success=True,
            duration_sec=req.duration,
            video_base64=base64.b64encode(vid_bytes).decode("utf-8"),
        )
    except Exception as exc:
        return RenderResponse(success=False, duration_sec=0.0, video_base64="", error=str(exc))


@app.post("/render/hybrid", response_model=RenderResponse)
def render_hybrid_api(req: RenderHybridRequest) -> RenderResponse:
    """Renders a hybrid mixed-media (35mm plate + 2D stickman + riddle HUD) clip and returns base64 MP4."""
    try:
        import cv2
        import numpy as np
        from tools import hybrid_engine, riddle_director, stickman_engine

        if req.image_base64:
            img_bytes = base64.b64decode(req.image_base64)
            nparr = np.frombuffer(img_bytes, np.uint8)
            bg_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if bg_img is None:
                return RenderResponse(success=False, duration_sec=0.0, video_base64="", error="Invalid image_base64 payload")
        else:
            bg_img = np.full((req.height, req.width, 3), (24, 30, 42), dtype=np.uint8)

        out_mp4 = Path(tempfile.gettempdir()) / f"hybrid_{uuid.uuid4().hex}.mp4"
        pose_spec = stickman_engine.StickmanPoseSpec(pose=req.pose, mouth=req.mouth, prop=req.prop)
        app_spec = stickman_engine.StickmanAppearance(accessory=req.accessory)
        riddle_spec = riddle_director.RiddleSceneSpec(
            title=req.title,
            inventory=[
                riddle_director.InventoryItem(label="Clues", count=2, color=(255, 255, 255)),
                riddle_director.InventoryItem(label="Suspects", count=3, color=(40, 180, 255)),
            ],
            characters=[
                riddle_director.CharacterAnchor(id="1", name="Suspect 1", x=0.28, y=0.56, badge_label="1"),
                riddle_director.CharacterAnchor(id="2", name="Suspect 2", x=0.72, y=0.56, badge_label="2"),
            ],
            sightlines=[riddle_director.SightlineRay(from_id="2", to_id="1", blocked=False)],
        )

        ok = hybrid_engine.render_hybrid_scene(
            bg_image=bg_img,
            pose_spec=pose_spec,
            appearance=app_spec,
            riddle_spec=riddle_spec,
            output_path=out_mp4,
            style=req.style,
            trajectory=req.trajectory,
            duration=req.duration,
            fps=req.fps,
            width=req.width,
            height=req.height,
        )
        if not ok or not out_mp4.exists():
            return RenderResponse(success=False, duration_sec=0.0, video_base64="", error="Hybrid render failed")

        vid_bytes = out_mp4.read_bytes()
        out_mp4.unlink(missing_ok=True)
        return RenderResponse(
            success=True,
            duration_sec=req.duration,
            video_base64=base64.b64encode(vid_bytes).decode("utf-8"),
        )
    except Exception as exc:
        return RenderResponse(success=False, duration_sec=0.0, video_base64="", error=str(exc))


def run_server(port: int = 8000) -> None:
    """Starts the FastAPI daemon on the given port."""
    if uvicorn is None:
        raise RuntimeError("uvicorn and fastapi must be installed to run the HTTP server.")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    run_server()
