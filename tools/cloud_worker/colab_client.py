#!/usr/bin/env python3
"""FrameForge Google Colab Cloud Worker Client (tools/cloud_worker/colab_client.py).

Connects your local Mac FrameForge pipeline to the remote Google Colab GPU instance
via a secure cloudflared tunnel HTTPS URL.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict


class ColabGatewayClient:
    """Client for dispatching GPU render tasks to Google Colab."""

    def __init__(self, gateway_url: str):
        self.gateway_url = gateway_url.rstrip("/")

    def get_health(self) -> Dict[str, Any]:
        """Queries remote Colab GPU health and VRAM allocation."""
        url = f"{self.gateway_url}/health"
        req = urllib.request.Request(url, headers={"User-Agent": "FrameForge-Client/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def render_photobook_remote(
        self,
        image_path: Path,
        output_mp4: Path,
        style: str = "magnates_amber",
        trajectory: str = "magnates_drift",
        duration: float = 3.5,
    ) -> bool:
        """Sends an image to Colab GPU, renders the photobook clip, and saves MP4."""
        img_bytes = image_path.read_bytes()
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")

        payload = {
            "image_base64": img_b64,
            "style": style,
            "trajectory": trajectory,
            "duration": duration,
            "fps": 30,
            "width": 1080,
            "height": 1920,
        }

        url = f"{self.gateway_url}/render/photobook"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "FrameForge-Client/1.0"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if not result.get("success"):
                    print(f"Error from Colab worker: {result.get('error')}", file=sys.stderr)
                    return False

                vid_bytes = base64.b64decode(result["video_base64"])
                output_mp4.parent.mkdir(parents=True, exist_ok=True)
                output_mp4.write_bytes(vid_bytes)
                return True
        except urllib.error.URLError as err:
            print(f"Network error contacting Colab Gateway: {err}", file=sys.stderr)
            return False


def main() -> int:
    ap = argparse.ArgumentParser(description="FrameForge Colab Gateway CLI Client")
    ap.add_argument("--gateway", "-g", type=str, required=True, help="Colab cloudflared HTTPS URL")
    ap.add_argument("--health", action="store_true", help="Check remote GPU status and VRAM")
    ap.add_argument("--render-photobook", type=Path, help="Render photobook clip on remote GPU from image")
    ap.add_argument("--output", "-o", type=Path, default=Path("remote_photobook.mp4"), help="Output MP4 path")

    args = ap.parse_args()
    client = ColabGatewayClient(args.gateway)

    if args.health:
        print(f"📡 Querying Colab Gateway at {args.gateway}...")
        try:
            health = client.get_health()
            print("=" * 60)
            print("  REMOTE GOOGLE COLAB GPU STATUS")
            print("=" * 60)
            print(f"  GPU Name        : {health.get('gpu_name')}")
            print(f"  CUDA Available  : {health.get('cuda_available')}")
            print(f"  VRAM Total      : {health.get('vram_total_gb')} GB")
            print(f"  VRAM Allocated  : {health.get('vram_allocated_gb')} GB")
            print(f"  Google Drive 5TB: {'CONNECTED' if health.get('drive_mounted') else 'NOT MOUNTED'}")
            print(f"  Local NVMe Free : {health.get('local_disk_free_gb')} GB")
            print("=" * 60)
            return 0
        except Exception as err:
            print(f"❌ Failed to reach Colab Gateway: {err}", file=sys.stderr)
            return 1

    if args.render_photobook:
        print(f"🚀 Dispatching 35mm Photobook render to Colab GPU: {args.render_photobook}...")
        ok = client.render_photobook_remote(args.render_photobook, args.output)
        if ok:
            print(f"✅ Render completed and downloaded: {args.output}")
            return 0
        else:
            print("❌ Remote render failed", file=sys.stderr)
            return 1

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
