"""Content identity and persisted clip reuse, without media/model execution."""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def manifest_inputs(tmp_path):
    source = tmp_path / "images" / "s01.jpg"
    source.parent.mkdir()
    source.write_bytes(b"first-image")
    return {
        "scene_index": 0, "scene": {"prompt": "A glass maze"},
        "source_image": source, "duration_s": 3.5,
        "preset": "depthflow_orbit", "width": 1080, "height": 1920,
    }


def test_manifest_roundtrip_reuses_unchanged_content_and_records_relative_output(tmp_path, manifest_inputs):
    from tools.render_manifest import RenderManifest, scene_fingerprint

    output = tmp_path / "videos" / "s01.mp4"
    output.parent.mkdir()
    output.write_bytes(b"scene-one")
    path = tmp_path / "cache" / "render_manifest.json"
    manifest = RenderManifest.load(path)
    fingerprint = scene_fingerprint(**manifest_inputs)
    assert not manifest.can_reuse("0", fingerprint, output)
    manifest.record("0", fingerprint, output)
    manifest.save()

    assert RenderManifest.load(path).can_reuse("0", fingerprint, output)
    data = json.loads(path.read_text())
    assert data["schema_version"] == 1
    assert data["renderer_contract_version"]
    assert data["scenes"]["0"]["output_path"] == "videos/s01.mp4"
    assert data["scenes"]["0"]["output_sha256"] == "8814c612b726f156c69334351c397aa7e37b6e513677a0835b64752fbb0b4ddd"


@pytest.mark.parametrize("changed", ["prompt", "source", "source_stem", "duration", "preset", "dimensions", "renderer", "steps", "index"])
def test_fingerprint_invalidation_affects_only_the_changed_scene(tmp_path, manifest_inputs, monkeypatch, changed):
    from tools import render_manifest as rm

    output = tmp_path / "videos" / "s01.mp4"
    output.parent.mkdir()
    output.write_bytes(b"scene-one")
    manifest = rm.RenderManifest.load(tmp_path / "cache" / "render_manifest.json")
    baseline = rm.scene_fingerprint(**manifest_inputs)
    other = {**manifest_inputs, "scene_index": 1}
    other_source = tmp_path / "images" / "s02.jpg"
    other_source.write_bytes(b"second-image")
    other["source_image"] = other_source
    other_baseline = rm.scene_fingerprint(**other)
    manifest.record("0", baseline, output)
    manifest.record("1", other_baseline, output)
    changed_inputs = {**manifest_inputs, "scene": dict(manifest_inputs["scene"])}
    if changed == "prompt":
        changed_inputs["scene"]["prompt"] = "A stone maze"
    elif changed == "source":
        manifest_inputs["source_image"].write_bytes(b"edited-image")
    elif changed == "source_stem":
        renamed = manifest_inputs["source_image"].with_name("renamed.jpg")
        manifest_inputs["source_image"].rename(renamed)
        changed_inputs["source_image"] = renamed
    elif changed == "duration":
        changed_inputs["duration_s"] = 4.5
    elif changed == "preset":
        changed_inputs["preset"] = "depthflow_dolly"
    elif changed == "dimensions":
        changed_inputs["width"], changed_inputs["height"] = 1920, 1080
    elif changed == "renderer":
        monkeypatch.setattr(rm, "RENDERER_CONTRACT_VERSION", "test-new-contract")
    elif changed == "steps":
        changed_inputs["scene"]["steps"] = 8
    else:
        changed_inputs["scene_index"] = 2

    changed_fingerprint = rm.scene_fingerprint(**changed_inputs)
    assert changed_fingerprint != baseline
    assert not manifest.can_reuse("0", changed_fingerprint, output)
    # A contract upgrade affects all fingerprints computed under that contract;
    # checking the untouched scene's original fingerprint proves record isolation.
    assert manifest.can_reuse("1", other_baseline, output)


def test_manifest_rejects_output_tampering_deletion_and_different_path(tmp_path, manifest_inputs):
    from tools.render_manifest import RenderManifest, scene_fingerprint

    output = tmp_path / "videos" / "s01.mp4"
    output.parent.mkdir()
    output.write_bytes(b"scene-one")
    fingerprint = scene_fingerprint(**manifest_inputs)
    manifest = RenderManifest.load(tmp_path / "cache" / "render_manifest.json")
    manifest.record("0", fingerprint, output)
    renamed = output.with_name("other.mp4")
    renamed.write_bytes(b"scene-one")
    assert not manifest.can_reuse("0", fingerprint, renamed)
    output.write_bytes(b"scene-two")
    assert not manifest.can_reuse("0", fingerprint, output)
    output.unlink()
    assert not manifest.can_reuse("0", fingerprint, output)


@pytest.mark.parametrize("payload", ["{", "[]", '{"schema_version": 99, "scenes": {}}'])
def test_manifest_unreadable_or_unsupported_data_is_a_cache_miss(tmp_path, payload):
    from tools.render_manifest import RenderManifest

    path = tmp_path / "cache" / "render_manifest.json"
    path.parent.mkdir()
    path.write_text(payload)
    assert not RenderManifest.load(path).can_reuse("0", "unknown", tmp_path / "s01.mp4")
