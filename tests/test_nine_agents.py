"""Unit and integration tests for FrameForge's 9-Agent Pipeline Architecture.

Verifies the Input -> Output contract and behaviors of:
  1. ConceptAgent        : series bible + episode log -> premise & verified dossier
  2. ScriptAgent         : premise -> scene list (one action each, hook score >= 70 target)
  3. CharacterRefAgent   : character name -> ref image + description + style lock
  4. KeyframePromptAgent : scene + refs -> 6-layer 3-plane Z-depth keyframe prompt
  5. MotionPromptAgent   : keyframe + scene -> motion prompt & 3D camera trajectory
  6. NegativePromptAgent : scene + past QA failures -> negative prompt / affirmative constraints
  7. QAAgent             : clip -> pass/fail + reason (face match, hands, text, flicker)
  8. PolicyAgent         : full episode -> flags (avoid list, novelty, word band, closing ask)
  9. MetadataAgent       : episode -> metadata (title, description, tags, synthetic disclosure)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from tools.agents import (
    CharacterRefAgent,
    ConceptAgent,
    KeyframePromptAgent,
    MetadataAgent,
    MotionPromptAgent,
    NegativePromptAgent,
    PolicyAgent,
    QAAgent,
    ScriptAgent,
)


# --------------------------------------------------------------------------- #
# 1. ConceptAgent Tests
# --------------------------------------------------------------------------- #
def test_concept_agent_proposes_premise_and_checks_novelty(tmp_path: Path):
    agent = ConceptAgent()
    # Test with verified topic
    dossier, report = agent.run(topic="Loss Aversion")
    assert report.status == "PASS"
    assert dossier["topic"] == "Loss Aversion"
    assert "Daniel Kahneman" in dossier["primary_researchers"]
    assert report.metrics["novelty_score"] == 100

    # Test novelty collision against supplied episode_log
    log_file = tmp_path / "episodes.txt"
    log_file.write_text("loss aversion\nbystander effect\n", encoding="utf-8")
    dossier_col, rep_col = agent.run(topic="Loss Aversion", episode_log=log_file)
    assert rep_col.status == "WARN"
    assert rep_col.metrics["novelty_score"] == 15
    assert "collides" in rep_col.summary.lower() or "novelty warning" in rep_col.summary.lower()

    # Test derivation from series bible
    bible = {"suggested_topics": ["Ego Depletion", "The Doorway Effect"]}
    dossier_b, rep_b = agent.run(series_bible=bible)
    assert dossier_b["topic"] == "Ego Depletion"


# --------------------------------------------------------------------------- #
# 2. ScriptAgent Tests
# --------------------------------------------------------------------------- #
def test_script_agent_turns_premise_into_scenes():
    agent = ScriptAgent()
    premise = "Loss Aversion: The 1979 Kahneman Study"
    scenes, report = agent.run(premise, genre="3d_cgi", target_scene_count=6)
    assert report.status in ("PASS", "HEALED")
    assert len(scenes) == 6
    assert all("text" in s for s in scenes)
    assert report.metrics["scene_count"] == 6
    assert report.metrics["hook_score"] >= 60


# --------------------------------------------------------------------------- #
# 3. CharacterRefAgent Tests
# --------------------------------------------------------------------------- #
def test_character_ref_agent_lookups_and_style_lock():
    agent = CharacterRefAgent()
    # Protagonist lookup
    profile, report = agent.run("protagonist")
    assert report.status == "PASS"
    assert profile["name"] == "Alex"
    assert "wardrobe" in profile
    assert "style_lock" in profile
    assert "ref_image" in profile

    # Researcher lookup
    researcher, _ = agent.run("researcher")
    assert researcher["name"] == "Dr. Miller"
    assert "optical glasses" in researcher["wardrobe"]

    # Custom traits override
    custom, _ = agent.run("student", custom_traits={"wardrobe": "dark charcoal hoodie"})
    assert custom["wardrobe"] == "dark charcoal hoodie"


# --------------------------------------------------------------------------- #
# 4. KeyframePromptAgent Tests
# --------------------------------------------------------------------------- #
def test_keyframe_prompt_agent_builds_spatial_prompt():
    agent = KeyframePromptAgent()
    char_agent = CharacterRefAgent()
    ref, _ = char_agent.run("protagonist")

    scene = {
        "scene_idx": 1,
        "topic": "Loss Aversion",
        "text": "If you hold a stock crashing 20%, why does your brain refuse to sell?",
        "action": "Trader staring in panic at red stock chart on glowing monitors",
    }
    prompt, report = agent.run(scene, character_ref=ref, genre="3d_cgi")
    assert report.status == "PASS"
    assert "Subject:" in prompt or "Midground" in prompt
    assert "Alex" in prompt
    assert len(prompt.split()) >= 20


# --------------------------------------------------------------------------- #
# 5. MotionPromptAgent Tests
# --------------------------------------------------------------------------- #
def test_motion_prompt_agent_assigns_3d_trajectory():
    agent = MotionPromptAgent()
    # Scene 1: Realization moment should assign vertigo dolly zoom
    motion_cfg, report = agent.run(scene_idx=1, scene_action="Character freezes and realizes mistake")
    assert report.status == "PASS"
    assert motion_cfg["trajectory"] == "vertigo"
    assert "dolly-zoom" in motion_cfg["description"].lower()
    assert motion_cfg["optical_flow_bounds_px"] == (0.5, 25.0)

    # Scene 2: Standard progression
    motion_2, _ = agent.run(scene_idx=2, scene_action="Scanning office room")
    assert motion_2["trajectory"] in ("orbit", "spiral", "roll", "spatial")


# --------------------------------------------------------------------------- #
# 6. NegativePromptAgent Tests
# --------------------------------------------------------------------------- #
def test_negative_prompt_agent_handles_flux3_and_past_failures():
    agent = NegativePromptAgent()
    prompt = "A man not wearing a hat standing in a room"
    res, report = agent.run(
        prompt=prompt,
        genre="cinematic_35mm",
        target_model="flux3",
        past_qa_failures=["deformed hands", "blurry background"],
    )
    assert report.status == "PASS"
    # FLUX.3 does not use raw negative prompt string, uses affirmative constraints
    assert res.target_model == "flux3"
    assert len(res.affirmative_anchors) > 0
    # Negation trap sanitization ("not wearing a hat" -> "bareheaded")
    assert "bareheaded" in res.sanitized_prompt.lower()
    assert "not wearing a hat" not in res.sanitized_prompt.lower()

    # Past QA failures injected into affirmative anchors
    assert any("hand" in a.lower() for a in res.affirmative_anchors)


# --------------------------------------------------------------------------- #
# 7. QAAgent Tests
# --------------------------------------------------------------------------- #
def test_qa_agent_audits_image_plate_and_flags_failures(tmp_path: Path):
    agent = QAAgent()

    # 1. Non-existent file
    passed, reasons, report = agent.run(tmp_path / "non_existent.mp4")
    assert not passed
    assert report.status == "FAIL"

    # 2. Valid high-contrast sharp image plate
    sharp_img = tmp_path / "sharp_plate.png"
    # Create checkerboard pattern with sharp edges
    pattern = np.array([[255, 0] * 30, [0, 255] * 30] * 30, dtype=np.uint8)
    arr = np.kron(pattern, np.ones((8, 8), dtype=np.uint8)).astype(np.uint8)
    Image.fromarray(arr).save(sharp_img)

    passed_sharp, reasons_sharp, rep_sharp = agent.run(sharp_img, require_motion=False)
    assert passed_sharp
    assert rep_sharp.status == "PASS"
    assert rep_sharp.metrics["plate_audit"]["laplacian_sharpness"] > 20.0

    # 3. Completely flat blurry image
    flat_img = tmp_path / "flat_plate.png"
    Image.fromarray(np.full((200, 200), 128, dtype=np.uint8)).save(flat_img)

    passed_flat, reasons_flat, rep_flat = agent.run(flat_img, require_motion=False)
    assert not passed_flat
    assert rep_flat.status == "FAIL"
    assert any("flat" in r or "blur" in r or "smeared" in r for r in reasons_flat)


# --------------------------------------------------------------------------- #
# 8. PolicyAgent Tests
# --------------------------------------------------------------------------- #
def test_policy_agent_enforces_avoid_list_novelty_and_word_band():
    agent = PolicyAgent()

    # Clean compliant episode
    valid_episode = {
        "concept": "Loss Aversion",
        "format": "short",
        "scenes": [
            {"text": "If you hold a stock down twenty percent, your brain treats the paper loss like physical pain. " * 3},
            {"text": "Daniel Kahneman proved that the agony of losing a dollar hurts twice as much as the joy of winning it. " * 3},
            {"text": "So comment below: what is one decision you are holding onto right now, and follow for part two."},
        ],
    }
    passed, flags, report = agent.run(valid_episode)
    # Check that closing ask is satisfied ("comment below", "follow for part two")
    assert not any("closing-ask" in f.lower() for f in flags)
    assert not any("avoid-list" in f.lower() for f in flags)

    # Episode with banned AI buzzwords and copyright IP
    dirty_episode = {
        "concept": "Harry Potter Magical Landscape",
        "format": "short",
        "scenes": [
            {"text": "Let us delve into this fascinating tapestry and unlock the secrets of the magical realm."},
        ],
    }
    passed_dirty, flags_dirty, rep_dirty = agent.run(dirty_episode)
    assert not passed_dirty
    assert rep_dirty.status == "FAIL"
    assert any("banned ai buzzword 'delve'" in f.lower() for f in flags_dirty)
    assert any("tapestry" in f.lower() for f in flags_dirty)
    assert any("copyright guard" in f.lower() for f in flags_dirty)


# --------------------------------------------------------------------------- #
# 9. MetadataAgent Tests
# --------------------------------------------------------------------------- #
def test_metadata_agent_compiles_upload_metadata():
    agent = MetadataAgent()
    episode = {
        "id": "SH-15",
        "concept": "Loss Aversion",
        "format": "short",
    }
    dossier = {
        "topic": "Loss Aversion",
        "year": "1979",
        "quantitative_stat": "82%",
        "primary_researchers": "Daniel Kahneman & Amos Tversky",
        "publication": "Econometrica",
    }
    meta, report = agent.run(episode, dossier=dossier)
    assert report.status == "PASS"
    assert "Loss Aversion" in meta["title"]
    assert "1979" in meta["title"]
    assert len(meta["title"]) <= 58
    assert "Daniel Kahneman" in meta["description"]
    assert "82%" in meta["description"]
    assert "#shorts" in meta["description"]
    # Tags strictly lowercase
    assert all(t == t.lower() for t in meta["tags"])
    # Synthetic disclosure answers conform to YouTube policy
    assert meta["synthetic_disclosure"]["altered_or_synthetic_content"] is True
    assert meta["synthetic_disclosure"]["studio_setting_answers"]["question_1_realistic_person"] == "Yes"


# --------------------------------------------------------------------------- #
# 10. Integration: Brainstorming & Full 9-Agent Cycle Tests
# --------------------------------------------------------------------------- #
def test_concept_agent_brainstorm_novel_premises():
    agent = ConceptAgent()
    candidates = agent.brainstorm_novel_premises(count=3)
    assert len(candidates) > 0
    for cand in candidates:
        assert "topic" in cand
        assert "primary_researchers" in cand
        assert "hook_candidate" in cand
        assert cand["novelty_score"] == 100
        assert cand["series_arc"] in ("Empirical Behavior Series", "Series Arc")


def test_character_ref_agent_loads_persisted_card():
    agent = CharacterRefAgent()
    profile, report = agent.run("alex")
    assert report.status == "PASS"
    assert profile["name"] == "Alex"
    assert "charcoal textured crewneck" in profile["wardrobe"]


def test_orchestrator_run_nine_agent_cycle():
    from tools.agents import OrchestratorAgent

    orch = OrchestratorAgent()
    blueprint, reports = orch.run_nine_agent_cycle(topic="Loss Aversion", genre="3d_cgi")
    assert len(reports) >= 8
    assert all(r.status in ("PASS", "HEALED", "WARN") for r in reports)
    assert blueprint["topic"] == "Loss Aversion"
    assert len(blueprint["scenes"]) == 8
    assert "title" in blueprint["metadata"]

