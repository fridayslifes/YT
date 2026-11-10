from __future__ import annotations

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


def test_colab_client_url_formatting():
    """Verify ColabGatewayClient correctly formats endpoint URLs."""
    client = colab_client.ColabGatewayClient("https://example.trycloudflare.com/")
    assert client.gateway_url == "https://example.trycloudflare.com"
