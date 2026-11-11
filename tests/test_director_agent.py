"""Unit tests for tools/director_agent.py (Showrunner Director Agent)."""

from __future__ import annotations

import json
import pytest

from tools.director_agent import ShowrunnerDirector
from tools.errors import MissingInputError


def _sample_dossier() -> dict:
    return {
        "topic": "Loss Aversion",
        "primary_researchers": "Daniel Kahneman & Amos Tversky",
        "year": "1979",
        "quantitative_stat": "losses loom 2x larger than equivalent gains",
        "broken_assumption": "You think gains and losses weigh the same, but loss triggers twice the neural pain.",
        "protagonist": "a 34-year-old architect named Julian in a charcoal button-down shirt",
    }


def _sample_script_scenes() -> list[dict]:
    return [
        {"id": "s01", "text": "Why does losing ten dollars hurt twice as much as finding ten dollars?", "duration": 3.4},
        {"id": "s02", "text": "In 1979, psychologists mapped this exact cognitive pain asymmetry in controlled trials.", "duration": 3.8},
        {"id": "s03", "text": "Volunteers were offered a simple coin toss with an even fifty fifty chance.", "duration": 3.5},
        {"id": "s04", "text": "A stray dog outside would run from danger faster than toward food; human brains do the same.", "duration": 3.7},
        {"id": "s05", "text": "Brain scans revealed that potential losses light up the amygdala with alarm bells.", "duration": 3.6},
        {"id": "s06", "text": "This evolutionary instinct kept ancestors safe when a single loss was fatal.", "duration": 3.5},
        {"id": "s07", "text": "Next time you freeze on a decision, ask if fear is exaggerating the risk. Comment your thoughts.", "duration": 3.8},
        {"id": "s08", "text": "Because the moment you let sunken loss masquerade as loyalty...", "duration": 2.8},
    ]


def test_showrunner_director_initialization() -> None:
    director = ShowrunnerDirector(channel="cognitive_core", genre="3d_cgi")
    assert director.channel_name == "cognitive_core"
    assert director.genre_key == "3d_cgi"
    assert director.genre_profile.id == "3d_cgi"


def test_showrunner_director_fails_on_empty_scenes() -> None:
    director = ShowrunnerDirector()
    with pytest.raises(MissingInputError) as exc_info:
        director.direct_video([], _sample_dossier(), video_id="SH-TEST")
    assert exc_info.value.stage == "director_agent"


def test_showrunner_director_directs_full_video() -> None:
    director = ShowrunnerDirector(channel="cognitive_core", genre="3d_cgi")
    manifest = director.direct_video(
        script_scenes=_sample_script_scenes(),
        dossier=_sample_dossier(),
        video_id="SH-99",
        topic="Loss Aversion",
    )

    assert manifest.video_id == "SH-99"
    assert manifest.topic == "Loss Aversion"
    assert len(manifest.scenes) == 8
    assert "Loss Aversion" in manifest.logline

    # Verify per-scene directional blocking & lighting
    for sc in manifest.scenes:
        # Spatial blocking checks
        assert sc.spatial.character_position != ""
        assert sc.spatial.posture_and_wardrobe != ""
        assert sc.spatial.movement_vector != ""
        assert sc.spatial.focal_props != ""
        assert sc.spatial.background_staging != ""

        # Lighting direction checks
        assert "stage-" in sc.lighting.dominant_side
        assert "brightness" in sc.lighting.dominant_side
        assert sc.lighting.key_light_source != ""
        assert sc.lighting.shadow_ratio != ""
        assert sc.lighting.rim_light != ""

        # Camera trajectory & safe zones
        assert sc.camera.trajectory_preset in {
            "depthflow_vertigo",
            "depthflow_spiral",
            "depthflow_orbit",
            "depthflow_dolly",
            "spatial_drift",
        }
        assert 0.44 <= sc.camera.safe_zone_anchor <= 0.58
        assert sc.camera.lens_optics != ""

        # Sound direction checks
        assert sc.sound.score_movement != ""
        assert sc.sound.foley_cue != ""
        assert -1.0 <= sc.sound.stereo_pan <= 1.0
        assert sc.sound.narrator_tone != ""

        # Synthesized prompt integrates spatial & lighting
        assert "Lighting:" in sc.synthesized_prompt
        assert "Key light from" in sc.synthesized_prompt
        assert "Camera optics:" in sc.synthesized_prompt


def test_showrunner_director_movement_vectors_and_staging() -> None:
    director = ShowrunnerDirector(genre="3d_cgi")
    manifest = director.direct_video(
        script_scenes=_sample_script_scenes(),
        dossier=_sample_dossier(),
        video_id="SH-99",
        topic="Loss Aversion",
    )

    # Scene 3 mentions "coin toss"
    sc3 = manifest.scenes[2]
    assert "brass" in sc3.spatial.focal_props.lower() or "scale" in sc3.spatial.focal_props.lower()

    # Scene 4 mentions "dog"
    sc4 = manifest.scenes[3]
    assert "dog" in sc4.spatial.movement_vector.lower()

    # Scene 7 is Action Ask & Reset
    sc7 = manifest.scenes[6]
    assert sc7.narrative_beat == "Action Ask & Reset"
    assert "Action Ask & Reset" in sc7.narrative_beat


def test_director_pitch_format() -> None:
    director = ShowrunnerDirector(genre="3d_cgi")
    manifest = director.direct_video(
        script_scenes=_sample_script_scenes(),
        dossier=_sample_dossier(),
        video_id="SH-99",
        topic="Loss Aversion",
    )

    pitch = manifest.format_director_pitch()
    assert "# 🎬 SHOWRUNNER DIRECTORIAL TREATMENT" in pitch
    assert "SCENE-BY-SCENE DIRECTORIAL BLOCKING & LIGHTING" in pitch
    assert "Scene 01" in pitch
    assert "Spatial Blocking & Movement:" in pitch
    assert "Lighting & Shadow:" in pitch
    assert "Sound & Foley:" in pitch


def test_manifest_serialization() -> None:
    director = ShowrunnerDirector(genre="3d_cgi")
    manifest = director.direct_video(
        script_scenes=_sample_script_scenes(),
        dossier=_sample_dossier(),
        video_id="SH-99",
        topic="Loss Aversion",
    )

    d = manifest.to_dict()
    assert d["video_id"] == "SH-99"
    assert len(d["scenes"]) == 8

    j = manifest.to_json()
    parsed = json.loads(j)
    assert parsed["topic"] == "Loss Aversion"
    assert parsed["scenes"][0]["scene_index"] == 1


def test_director_worker_and_verifier_integration(tmp_path) -> None:
    from tools.orchestrator.contracts import TaskSpec
    from tools.orchestrator.state import RunContext, RunStore
    from tools.orchestrator.tools import ProjectTools
    from tools.orchestrator.verifiers import verify_direction
    from tools.orchestrator.workers import DirectorWorker

    store = RunStore(tmp_path / ".orchestrator")
    spec = TaskSpec(
        id="director",
        kind="director",
        title="Showrunner direction",
        params={"topic": "Loss Aversion", "video_id": "SH-99", "slug": "short_99"},
        depends_on=["script"],
        verifiers=["direction"],
    )
    state = store.create("produce", "test", [spec])
    ctx = RunContext(tmp_path, store.run_dir(state.run_id), state, store, ProjectTools(tmp_path))

    class FakeTaskRecord:
        def __init__(self, data):
            self.status = "passed"
            self.data = data
            self.artifacts = {}

    ctx.state.tasks["script"] = FakeTaskRecord({
        "scenes": _sample_script_scenes(),
        "dossier": _sample_dossier(),
    })
    worker = DirectorWorker()

    result = worker.run(spec, ctx)
    assert result.ok is True
    assert "director_manifest" in result.artifacts
    assert "director_pitch" in result.artifacts

    checks = verify_direction(spec, result, ctx)
    assert all(c.passed for c in checks), f"Direction verifier failed: {[c.message for c in checks if not c.passed]}"

