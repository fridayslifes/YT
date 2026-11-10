from __future__ import annotations

import base64

import cv2
import numpy as np

from tools.cloud_worker import colab_client, colab_server


def test_colab_schemas():
    """Verify Colab API request/response schemas validate properly."""
    health = colab_server.HealthResponse(
        status="healthy",
        cuda_available=True,
        gpu_name="NVIDIA Tesla T4",
        vram_total_gb=15.0,
        vram_allocated_gb=2.5,
        drive_mounted=True,
        local_disk_free_gb=45.0,
    )
    assert health.status == "healthy"
    assert health.cuda_available is True
    assert health.vram_total_gb == 15.0

    req = colab_server.RenderPhotobookRequest(
        image_base64="dGVzdA==",
        style="magnates_amber",
        duration=3.5,
    )
    assert req.style == "magnates_amber"
    assert req.duration == 3.5

    stick_req = colab_server.RenderStickmanRequest(pose="pointing", duration=1.0)
    assert stick_req.pose == "pointing"
    assert stick_req.mouth == "neutral"

    hyb_req = colab_server.RenderHybridRequest(title="TEST RIDDLE", duration=1.0)
    assert hyb_req.title == "TEST RIDDLE"
    assert hyb_req.style == "magnates_amber"


def test_colab_endpoints_photobook_stickman_and_hybrid():
    """Verify photobook, stickman, and hybrid endpoints render valid MP4 payloads."""
    img = np.full((320, 180, 3), (40, 80, 120), dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", img)
    assert ok
    b64_img = base64.b64encode(encoded.tobytes()).decode("utf-8")

    pb_res = colab_server.render_photobook_api(
        colab_server.RenderPhotobookRequest(
            image_base64=b64_img,
            duration=0.2,
            fps=15,
            width=360,
            height=640,
        )
    )
    assert pb_res.success is True
    assert len(base64.b64decode(pb_res.video_base64)) > 500

    st_res = colab_server.render_stickman_api(
        colab_server.RenderStickmanRequest(
            pose="pointing",
            caption="CLOUD STICKMAN",
            duration=0.2,
            fps=15,
            width=360,
            height=640,
        )
    )
    assert st_res.success is True
    assert len(base64.b64decode(st_res.video_base64)) > 500

    hy_res = colab_server.render_hybrid_api(
        colab_server.RenderHybridRequest(
            image_base64=b64_img,
            title="HYBRID GATEWAY",
            duration=0.2,
            fps=15,
            width=360,
            height=640,
        )
    )
    assert hy_res.success is True
    assert len(base64.b64decode(hy_res.video_base64)) > 500


def test_colab_client_url_formatting():
    """Verify ColabGatewayClient correctly formats endpoint URLs."""
    client = colab_client.ColabGatewayClient("https://example.trycloudflare.com/")
    assert client.gateway_url == "https://example.trycloudflare.com"
