"""tests/test_visual_prompts.py - the image-prompt uniqueness rule behind tools/visual_director.py.

Two Shorts that open on the same plate read as one video, and the previous SH-18 was withdrawn for
exactly that: its scene 1 shared a byte-identical opening with SH-17 and its scene 8 was identical
end to end. Scene 1 was fixed at the time; scene 8 was not, because the role-8 fallback template
named no topic, no dossier field and no project, so every generic-path topic got the same dusk
window. That is the regression this file holds shut.

Only prompt text is built here - no image model, no render, no network.
"""

from __future__ import annotations

import json

from conftest import REPO_ROOT
from tools import creative_engine as ce

DOSSIERS = json.loads(
    (REPO_ROOT / "channel_assets" / "scientific_dossiers.json").read_text(encoding="utf-8")
)


def _prompts_by_topic() -> dict[str, list[str]]:
    out = {}
    for key, dossier in DOSSIERS.items():
        scenes = ce.choreograph_scenes(dossier)
        out[key] = [sc["prompt"] for sc in scenes]
    return out


def test_no_scene_prompt_is_shared_between_dossiers():
    """Every scene of one topic must differ from the same scene of every other topic."""
    by_topic = _prompts_by_topic()
    topics = sorted(by_topic)
    assert len(topics) >= 2, "the invariant needs at least two dossiers to compare"

    collisions = [
        f"{a} vs {b} scene {i + 1}"
        for i in range(max(len(p) for p in by_topic.values()))
        for x, a in enumerate(topics)
        for b in topics[x + 1:]
        if i < len(by_topic[a]) and i < len(by_topic[b]) and by_topic[a][i] == by_topic[b][i]
    ]
    assert not collisions, f"identical image prompts across videos: {collisions}"


def test_hook_and_loop_scenes_differ_within_one_video():
    """The bookend frames of a single Short must not be the same picture."""
    for key, prompts in _prompts_by_topic().items():
        assert prompts[0] != prompts[-1], f"{key} opens and closes on the same plate"


def test_hook_scene_names_a_distinct_figure_per_topic():
    """Two Shorts whose hook frame holds the same person read as a series of one video."""
    figures = {}
    for key, dossier in DOSSIERS.items():
        prompt = ce.choreograph_scenes(dossier)[0]["prompt"]
        figures[key] = prompt.split("Subject (Midground Z-Plane): ")[-1][:60]
    duplicated = {f for f in figures.values() if list(figures.values()).count(f) > 1}
    assert not duplicated, f"hook figure shared by topics: {duplicated}"
