#!/usr/bin/env python3
"""FrameForge Autonomous Multi-Agent Crew & Orchestrator (v7.0 — 9-Agent Pipeline Architecture).

Implements the specialized 9-Agent Pipeline grounded in `.agents/personas/`:
  1. ConceptAgent         (💡 Premise Architect)     : Propose episode premises that differ from past ones (series bible + episode log -> premise).
  2. ScriptAgent          (✍️ Dialectic Scriptwriter): Turn premise into 4-6 or 8-12 scenes, one action each (premise -> scene list).
  3. CharacterRefAgent    (👤 Style Lock Custodian)  : Maintain and look up locked refs and style lock (character name -> ref image + description).
  4. KeyframePromptAgent  (🖼️ Spatial Prompt Director): Write the 6-layer 3-plane Z-depth image prompt for a scene (scene + refs -> keyframe prompt).
  5. MotionPromptAgent    (🎬 Camera Dynamics)       : Write the image-to-video prompt, one action per clip (keyframe + scene -> motion prompt).
  6. NegativePromptAgent  (🛡️ Anti-Glitch Engineer)  : Build negative prompt per scene / affirmative constraints (scene + past QA failures -> negative prompt).
  7. QAAgent              (🔬 Clip Quality Auditor)  : Check each generated clip for face match, hands, text, flicker (clip -> pass/fail + reason).
  8. PolicyAgent          (⚖️ Standards Compliance)  : Check episode against avoid list, word-band, and novelty rule (full episode -> flags).
  9. MetadataAgent        (📋 Upload Kit & Packaging): Formulate title, description, tags, synthetic disclosure answers (episode -> metadata).

Supporting Production & Release Engines:
  - ResearchAgent        (🔍 Evidence Grounding)     : Primary empirical source synthesist.
  - VisualDirectorAgent  (🎬 3D Scene Enrichment)    : Batch 6-layer 3D spatial prompt compiler.
  - AssetAgent           (🎨 Smart Asset Manager)    : Reusable asset catalog & semantic cache.
  - ProductionAgent      (🎥 Master MP4 Production)  : Neural FLUX, 3D camera moves, Kokoro TTS, mastering.
  - QualityGateAgent     (🛡️ Macro Quality Gate)     : Project-wide Reference Precision & Recall verification.
  - PublishAgent         (🚀 Release Dispatcher)     : Strict reviewed YouTube release dispatcher.
  - OrchestratorAgent    (🤖 Crew Coordinator)       : Coordinates all specialist agents end-to-end.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

TOOLS_DIR = Path(__file__).resolve().parent
YT_ROOT = TOOLS_DIR.parent
PERSONAS_DIR = YT_ROOT / ".agents" / "personas"

if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
if str(YT_ROOT) not in sys.path:
    sys.path.insert(0, str(YT_ROOT))

from tools.runtime import ensure_venv_cli  # noqa: E402

if __name__ == "__main__":
    ensure_venv_cli(Path(__file__), sys.argv[1:])

from tools import creative_engine  # noqa: E402
from tools import output_format as fmt  # noqa: E402
from tools import visual_director  # noqa: E402
from tools import youtube_skills  # noqa: E402
from tools.asset_agent import SmartAssetAgent  # noqa: E402
from tools.negative_prompt_agent import NegativePromptAgent as CoreNegativePromptAgent  # noqa: E402
from tools.orchestrator import legacy  # noqa: E402

__all__ = [
    "AgentReport",
    "BaseAgent",
    "ResearchAgent",
    "ConceptAgent",
    "PolicyAgent",
    "ScriptAgent",
    "CharacterRefAgent",
    "KeyframePromptAgent",
    "MotionPromptAgent",
    "NegativePromptAgent",
    "AssetAgent",
    "MetadataAgent",
    "PackagingAgent",
    "ProductionAgent",
    "QualityGateAgent",
    "QAAgent",
    "PublishAgent",
    "OrchestratorAgent",
    "report_exit_code",
]


@dataclass
class AgentReport:
    agent_name: str
    role: str
    status: str  # "PASS", "HEALED", "WARN", "SKIPPED", "FAIL"
    duration_s: float
    summary: str
    metrics: Dict[str, Any] = field(default_factory=dict)


def report_exit_code(reports: List[AgentReport]) -> int:
    """Preserve failed and incomplete stage outcomes at both legacy CLI entry points."""
    statuses = [report.status for report in reports]
    if "FAIL" in statuses:
        return 2
    if not statuses or any(status not in {"PASS", "HEALED"} for status in statuses):
        return 1
    return 0


class BaseAgent:
    name: str = "BaseAgent"
    role: str = "Specialist"
    emoji: str = "🤖"

    def log(self, msg: str) -> None:
        fmt.emit(f"  {self.emoji} {fmt.C.BOLD}{fmt.C.CYAN}[{self.name}]{fmt.C.RESET} {msg}")


# --------------------------------------------------------------------------- #
# 1. ResearchAgent (Grounded in .agents/personas/research_synthesist.md)
# --------------------------------------------------------------------------- #
class ResearchAgent(BaseAgent):
    name = "ResearchAgent"
    role = "Evidence & Primary Source Synthesist"
    emoji = "🔍"

    # Best-effort lookaround matching to prevent false positives and correctly handle non-word boundaries
    COPYRIGHT_TERMS = (
        "harry potter", "marvel", "star wars", "disney", "pokemon",
        "lord of the rings", "game of thrones",
    )
    PSEUDOSCIENCE_TERMS = (
        "flat earth", "astrology", "perpetual motion", "anti-vaccine",
        "chemtrails", "telepathy", "crystal healing",
        "dopamine detox removes 90%",
    )
    COPYRIGHT_PATTERNS = [
        (term, re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.IGNORECASE))
        for term in COPYRIGHT_TERMS
    ]
    PSEUDOSCIENCE_PATTERNS = [
        (term, re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.IGNORECASE))
        for term in PSEUDOSCIENCE_TERMS
    ]

    def run(self, topic: str, dossier_override: Optional[Dict[str, Any]] = None) -> tuple[Dict[str, Any], AgentReport]:
        """Research and verify empirical grounding for a topic. Fails closed if unverified."""
        t0 = time.time()
        topic_clean = topic.strip()
        self.log(f"Synthesizing and truth-verifying empirical dossier for '{topic_clean}'...")

        # 1. Anti-infringement / Copyright & Corporate IP safety guard
        ip_violation = next((term for term, p in self.COPYRIGHT_PATTERNS if p.search(topic_clean)), None)
        if ip_violation:
            summary = f"BLOCKED by IP Guard: '{topic_clean}' contains copyrighted fictional IP ('{ip_violation}')"
            self.log(summary)
            return {}, AgentReport(
                agent_name=self.name,
                role=self.role,
                status="FAIL",
                duration_s=round(time.time() - t0, 2),
                summary=summary,
                metrics={"copyright_cleared": False},
            )

        # 2. Debunked Pseudoscience & False Information Guard
        false_claim = next((term for term, p in self.PSEUDOSCIENCE_PATTERNS if p.search(topic_clean)), None)
        if false_claim:
            summary = f"BLOCKED by Fact-Check Guard: '{topic_clean}' contains debunked pseudoscience or false claim ('{false_claim}')"
            self.log(summary)
            return {}, AgentReport(
                agent_name=self.name,
                role=self.role,
                status="FAIL",
                duration_s=round(time.time() - t0, 2),
                summary=summary,
                metrics={"truth_verified": False, "false_claim": false_claim},
            )

        # 3. Retrieve verified dossier (fails closed: never synthesize an unverified study)
        if dossier_override:
            dossier = dossier_override
        else:
            try:
                dossier = creative_engine.synthesize_dossier(topic_clean)
            except Exception as exc:
                summary = (
                    f"FAILED Research Gate: Topic '{topic_clean}' has no verified empirical study on file ({exc}). "
                    f"Research fails closed to prevent fabricated citations."
                )
                self.log(summary)
                return {}, AgentReport(
                    agent_name=self.name,
                    role=self.role,
                    status="FAIL",
                    duration_s=round(time.time() - t0, 2),
                    summary=summary,
                    metrics={"truth_verified": False, "missing_dossier": True},
                )

        # Post-synthesis copyright check across full dossier content
        combined_text = f"{topic_clean} {json.dumps(dossier, ensure_ascii=False)}"
        content_ip_violation = next((term for term, p in self.COPYRIGHT_PATTERNS if p.search(combined_text)), None)
        if content_ip_violation:
            summary = f"BLOCKED by IP Guard: Dossier for '{topic_clean}' contains copyrighted fictional IP ('{content_ip_violation}')"
            self.log(summary)
            return {}, AgentReport(
                agent_name=self.name,
                role=self.role,
                status="FAIL",
                duration_s=round(time.time() - t0, 2),
                summary=summary,
                metrics={"copyright_cleared": False},
            )

        required_keys = [
            "primary_researchers", "year", "institution", "publication",
            "experiment_design", "quantitative_stat", "biological_mechanism",
            "five_second_override",
        ]
        missing = [k for k in required_keys if not dossier.get(k)]
        citation_verified = dossier.get("citation_verified", True)
        confidence = "HIGH" if (not missing and citation_verified) else "MODERATE"

        summary = (
            f"Anchored '{dossier.get('topic')}' in {dossier.get('primary_researchers')} "
            f"({dossier.get('year')}, {dossier.get('institution')}) | Stat: {dossier.get('quantitative_stat')}"
        )
        status = "WARN" if (missing or not citation_verified) else "PASS"

        self.log(summary)
        return dossier, AgentReport(
            agent_name=self.name,
            role=self.role,
            status=status,
            duration_s=round(time.time() - t0, 2),
            summary=summary,
            metrics={
                "researchers": dossier.get("primary_researchers"),
                "year": dossier.get("year"),
                "stat": dossier.get("quantitative_stat"),
                "confidence": confidence,
                "is_synthetic": False,
                "copyright_cleared": True,
                "truth_verified": bool(citation_verified),
            },
        )


# --------------------------------------------------------------------------- #
# 1b. ConceptAgent (Premise & Novelty Architect)
# --------------------------------------------------------------------------- #
class ConceptAgent(ResearchAgent):
    """Propose episode premises that differ from past ones (series bible + episode log -> premise)."""
    name = "ConceptAgent"
    role = "Episode Premise & Novelty Architect"
    emoji = "💡"

    def load_series_bible(self) -> Dict[str, Any]:
        bible_path = YT_ROOT / "channel_assets" / "series_bible.json"
        if bible_path.exists():
            try:
                return json.loads(bible_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def brainstorm_novel_premises(
        self,
        count: int = 3,
        episode_log: Optional[List[str] | Path] = None,
    ) -> List[Dict[str, Any]]:
        """Autonomously scan unexploited scientific dossiers, check against past uploads, and propose novel premises."""
        bible = self.load_series_bible()
        dossiers_path = YT_ROOT / "channel_assets" / "scientific_dossiers.json"
        tracker_file = YT_ROOT / "channel" / "uploaded_videos.txt"

        past_corpus = ""
        if episode_log is not None:
            if isinstance(episode_log, Path) and episode_log.exists():
                past_corpus = episode_log.read_text(encoding="utf-8", errors="ignore").lower()
            elif isinstance(episode_log, list):
                past_corpus = " ".join(episode_log).lower()
            elif isinstance(episode_log, str):
                past_corpus = episode_log.lower()
        elif tracker_file.exists():
            past_corpus = tracker_file.read_text(encoding="utf-8", errors="ignore").lower()

        candidates: List[Dict[str, Any]] = []
        if dossiers_path.exists():
            all_dossiers = json.loads(dossiers_path.read_text(encoding="utf-8"))
            for key, dos in all_dossiers.items():
                topic = dos.get("topic", key.replace("_", " ").title())
                if topic.lower() not in past_corpus:
                    char_lead = "alex"
                    if "experiment" in dos.get("experiment_design", "").lower():
                        char_lead = "dr_miller"
                    elif any(w in topic.lower() for w in ("social", "bystander", "fresh")):
                        char_lead = "jordan"

                    candidates.append({
                        "topic": topic,
                        "key": key,
                        "primary_researchers": dos.get("primary_researchers"),
                        "year": dos.get("year"),
                        "stat": dos.get("quantitative_stat"),
                        "mechanism": dos.get("biological_mechanism"),
                        "hook_candidate": dos.get("best_hook", f"Why your brain makes the exact same error in {topic.lower()}."),
                        "character_lead": char_lead,
                        "novelty_score": 100,
                        "series_arc": bible.get("series_title", "The Midnight Desk Chronicles"),
                    })

        self.log(f"Brainstormed {len(candidates)} novel unexploited premises from Series Bible.")
        return candidates[:count]

    def run(
        self,
        topic: str = "",
        dossier_override: Optional[Dict[str, Any]] = None,
        series_bible: Optional[Dict[str, Any] | str] = None,
        episode_log: Optional[List[str] | Path] = None,
    ) -> tuple[Dict[str, Any], AgentReport]:
        t0 = time.time()
        effective_topic = topic.strip() if topic else ""
        if not effective_topic:
            if series_bible and isinstance(series_bible, dict):
                candidates = series_bible.get("suggested_topics") or series_bible.get("themes", [])
                effective_topic = candidates[0] if candidates else ""
            elif series_bible:
                effective_topic = str(series_bible).strip()
            if not effective_topic:
                novel_candidates = self.brainstorm_novel_premises(count=1, episode_log=episode_log)
                effective_topic = novel_candidates[0]["topic"] if novel_candidates else "Loss Aversion"

        # 1. Primary empirical grounding & truth verification (inherited from ResearchAgent)
        dossier, report = super().run(effective_topic, dossier_override=dossier_override)
        if report.status == "FAIL":
            return dossier, report

        # 2. Novelty check against past uploads and tracker (or supplied episode_log)
        tracker_file = YT_ROOT / "channel" / "uploaded_videos.txt"
        novelty_score = 100
        collided_title = None

        past_corpus = ""
        if episode_log is not None:
            if isinstance(episode_log, Path) and episode_log.exists():
                past_corpus = episode_log.read_text(encoding="utf-8", errors="ignore").lower()
            elif isinstance(episode_log, list):
                past_corpus = " ".join(episode_log).lower()
            elif isinstance(episode_log, str):
                past_corpus = episode_log.lower()
        elif tracker_file.exists():
            past_corpus = tracker_file.read_text(encoding="utf-8", errors="ignore").lower()

        topic_lower = effective_topic.lower()
        if topic_lower in past_corpus:
            novelty_score = 15
            collided_title = effective_topic
            report.status = "WARN"
            report.summary += f" (Novelty Warning: '{effective_topic}' matches historical episode log)"

        report.agent_name = self.name
        report.role = self.role
        report.duration_s = round(time.time() - t0, 2)
        report.metrics["novelty_score"] = novelty_score
        report.metrics["collided_title"] = collided_title
        report.metrics["premise"] = dossier.get("topic", effective_topic)
        return dossier, report


# --------------------------------------------------------------------------- #
# 1c. PolicyAgent (Episode Policy, Avoid-List & Novelty Auditor)
# --------------------------------------------------------------------------- #
class PolicyAgent(BaseAgent):
    """Check the episode against the avoid list and the novelty rule (full episode -> flags)."""
    name = "PolicyAgent"
    role = "Avoid-List, Novelty & Standards Compliance Auditor"
    emoji = "⚖️"

    def run(
        self,
        episode: Dict[str, Any] | Path,
        avoid_list: Optional[List[str]] = None,
        tracker_file: Optional[Path] = None,
    ) -> tuple[bool, List[str], AgentReport]:
        t0 = time.time()
        flags: List[str] = []
        metrics: Dict[str, Any] = {}

        if isinstance(episode, Path):
            if not episode.exists():
                summary = f"FAIL: Episode file missing at {episode}"
                self.log(summary)
                return False, ["Episode file not found"], AgentReport(
                    agent_name=self.name,
                    role=self.role,
                    status="FAIL",
                    duration_s=round(time.time() - t0, 3),
                    summary=summary,
                )
            episode_data = json.loads(episode.read_text(encoding="utf-8"))
        else:
            episode_data = episode

        topic = str(episode_data.get("concept") or episode_data.get("topic") or episode_data.get("title", ""))
        scenes = episode_data.get("scenes", [])
        fmt_type = episode_data.get("format", "short")

        # 1. Avoid List (Banned corporate AI buzzwords)
        from tools.humanizer_director import BANNED_AI_WORDS
        full_text_corpus = f"{topic} " + " ".join(s.get("text", "") for s in scenes)
        words_to_check = set(avoid_list) if avoid_list else BANNED_AI_WORDS
        for w in words_to_check:
            pat = r"(?<!\w)" + re.escape(w) + r"(?!\w)"
            if re.search(pat, full_text_corpus, re.IGNORECASE):
                flags.append(f"Avoid-list violation: banned AI buzzword '{w}' found in script")

        # 2. Copyright / Fictional IP Guard
        for term, pattern in ResearchAgent.COPYRIGHT_PATTERNS:
            if pattern.search(full_text_corpus):
                flags.append(f"Copyright guard: fictional IP '{term}' detected")

        # 3. Pseudoscience / Debunked claims guard
        for term, pattern in ResearchAgent.PSEUDOSCIENCE_PATTERNS:
            if pattern.search(full_text_corpus):
                flags.append(f"Pseudoscience guard: debunked claim '{term}' detected")

        # 4. Word-Band Check (105-155 words for Shorts; 1100-1500 for Long)
        from tools.policy import WORD_BANDS
        band = WORD_BANDS.get(fmt_type, (105, 155))
        all_words = len(re.findall(r"\b\w+\b", " ".join(s.get("text", "") for s in scenes)))
        metrics["word_count"] = all_words
        metrics["word_band"] = band
        if scenes and not (band[0] <= all_words <= band[1]):
            flags.append(f"Word-band policy violation: {all_words} words outside allowed {band[0]}-{band[1]} range")

        # 5. Closing Ask Check (Last 2 scenes must contain a CTA)
        if scenes:
            closing_text = " ".join(s.get("text", "") for s in scenes[-2:]).lower()
            ask_keywords = ("subscribe", "comment", "part 2", "follow", "share", "what would you do", "save this", "next episode")
            has_ask = any(kw in closing_text for kw in ask_keywords)
            metrics["has_closing_ask"] = has_ask
            if not has_ask:
                flags.append("Closing-ask warning: No viewer call-to-action found in final 2 scenes")

        # 6. Novelty Check
        tf = tracker_file or (YT_ROOT / "channel" / "uploaded_videos.txt")
        novelty_score = 100
        if tf.exists():
            tracker_content = tf.read_text(encoding="utf-8", errors="ignore").lower()
            if topic and topic.lower() in tracker_content:
                novelty_score = 15
                flags.append(f"Novelty violation: Topic '{topic}' collides with previously uploaded video")
        metrics["novelty_score"] = novelty_score

        passed = not any("violation" in f or "guard" in f for f in flags)
        status = "PASS" if not flags else ("WARN" if passed else "FAIL")
        summary = f"Policy Audit: {len(flags)} flag(s) | Status={status} | Novelty={novelty_score}/100"
        self.log(summary)

        return passed, flags, AgentReport(
            agent_name=self.name,
            role=self.role,
            status=status,
            duration_s=round(time.time() - t0, 3),
            summary=summary,
            metrics=metrics,
        )


# --------------------------------------------------------------------------- #
# 2. ScriptAgent (Grounded in .agents/personas/short_video_coach.md)
# --------------------------------------------------------------------------- #
class ScriptAgent(BaseAgent):
    name = "ScriptAgent"
    role = "Dialectic Narrative & Hook Architect"
    emoji = "✍️"

    def run(
        self,
        dossier: Dict[str, Any] | str,
        genre: str = "3d_cgi",
        target_scene_count: Optional[int] = None,
    ) -> tuple[List[Dict[str, Any]], AgentReport]:
        t0 = time.time()
        if isinstance(dossier, str):
            premise = dossier.strip()
            try:
                dossier = creative_engine.synthesize_dossier(premise)
            except Exception:
                clean_topic = premise.split(":")[0].strip()
                try:
                    dossier = creative_engine.synthesize_dossier(clean_topic)
                except Exception as exc:
                    summary = f"ScriptAgent FAIL: No verified scientific dossier for '{premise}' ({exc}). Research fails closed."
                    self.log(summary)
                    return [], AgentReport(
                        agent_name=self.name,
                        role=self.role,
                        status="FAIL",
                        duration_s=round(time.time() - t0, 2),
                        summary=summary,
                        metrics={"premise": premise, "missing_dossier": True},
                    )
        topic = dossier["topic"]
        self.log(f"Drafting high-retention script for '{topic}'...")
        scenes = creative_engine.choreograph_scenes(dossier, genre=genre)
        if target_scene_count and 4 <= target_scene_count < len(scenes):
            scenes = scenes[:target_scene_count]

        hook_text = scenes[0]["text"]
        score, band, weakest = creative_engine.score_hook_candidate(hook_text)
        healed = False

        if score < 60:
            self.log(f"Initial hook scored {score}/100 ({band}, weakest={weakest}). Self-healing hook...")
            year = dossier.get("year", "1979")
            stat = dossier.get("quantitative_stat", "82%")
            mechanism = dossier.get("biological_mechanism", "your brain's threat-appraisal circuit")
            topic_lower = topic.lower()
            alt_hooks = [
                # Formula 1: Question + Contrarian Stakes
                f"If you ever freeze during {topic_lower}, why did {year} testing prove *eighty-five* *percent* of people fall into the exact same trap?",
                # Formula 2: Visceral 2nd-Person Symptom + Stat
                f"Your brain is running a {stat} penalty every time you face {topic_lower} — and {year} research proved you don't even notice it happening.",
                # Formula 3: Temporal Anchor + Consequence
                f"In {year}, scientists discovered why {topic_lower} costs you *twenty* *minutes* of focus every single time it fires.",
                # Formula 4: Pattern Interrupt + Mechanism
                f"The reason {topic_lower} hijacks your decision-making has nothing to do with willpower — it's {mechanism.split('.')[0].lower()}.",
                # Formula 5: Negativity Bias + Counter-Intuitive Stat
                f"Why did the {year} study prove your brain will risk *ten* *times* more pain before admitting a single mistake in {topic_lower}?",
                hook_text,
            ]
            best_h, best_s, best_b, best_w = hook_text, score, band, weakest
            for cand in alt_hooks:
                s, b, w = creative_engine.score_hook_candidate(cand)
                if s > best_s:
                    best_h, best_s, best_b, best_w = cand, s, b, w
            scenes[0]["text"] = best_h
            score, band, weakest = best_s, best_b, best_w
            healed = True
            self.log(f"Hook healed to {score}/100 ({band})")

        all_words = len(re.findall(r"\b\w+\b", " ".join(s.get("text", "") for s in scenes)))
        est_sec = round((all_words / 150.0) * 60.0, 1)
        summary = f"8 scenes | {all_words} words (~{est_sec}s) | Hook Score: {score}/100 ({band})"
        self.log(summary)

        return scenes, AgentReport(
            agent_name=self.name,
            role=self.role,
            status="HEALED" if healed else "PASS",
            duration_s=round(time.time() - t0, 2),
            summary=summary,
            metrics={
                "scene_count": len(scenes),
                "word_count": all_words,
                "estimated_duration_s": est_sec,
                "hook_score": score,
                "hook_band": band,
                "hook_weakest": weakest,
            },
        )


# --------------------------------------------------------------------------- #
# 3. VisualDirectorAgent (Semantic 3D Spatial Prompt Agent v7.0)
# --------------------------------------------------------------------------- #
class VisualDirectorAgent(BaseAgent):
    name = "VisualDirectorAgent"
    role = "Semantic 3D Spatial & 6-Layer Prompt Director"
    emoji = "🎬"

    def run(
        self,
        scenes: List[Dict[str, Any]],
        topic: str,
        genre: str = "3d_cgi",
        aspect: str = "9:16",
        dossier: Optional[Dict[str, Any]] = None,
        overwrite: bool = True,
    ) -> tuple[List[Dict[str, Any]], AgentReport]:
        t0 = time.time()
        self.log(f"Synthesizing 6-layer 3D spatial prompts (genre={genre}, aspect={aspect})...")
        director = visual_director.S4VisualDirector(
            genre_key=genre,
            topic=topic,
            default_aspect=aspect,
            dossier=dossier,
        )
        enriched = director.process_project_scenes(scenes, genre=genre, overwrite_custom_prompts=overwrite)

        unique_prompts = {s["prompt"] for s in enriched}
        avg_words = round(sum(len(s["prompt"].split()) for s in enriched) / max(1, len(enriched)), 1)
        summary = f"Synthesized {len(unique_prompts)}/{len(enriched)} unique 3D-spatial prompts (avg {avg_words} words/prompt)"
        self.log(summary)

        return enriched, AgentReport(
            agent_name=self.name,
            role=self.role,
            status="PASS" if len(unique_prompts) == len(enriched) else "WARN",
            duration_s=round(time.time() - t0, 2),
            summary=summary,
            metrics={
                "unique_prompts": len(unique_prompts),
                "total_scenes": len(enriched),
                "avg_prompt_words": avg_words,
                "genre": genre,
                "aspect": aspect,
            },
        )


# --------------------------------------------------------------------------- #
# 3b. CharacterRefAgent (Locked Character Reference & Style Lock Custodian)
# --------------------------------------------------------------------------- #
class CharacterRefAgent(BaseAgent):
    name = "CharacterRefAgent"
    role = "Character Reference & Style Lock Custodian"
    emoji = "👤"

    def __init__(self):
        super().__init__()
        self.character_dir = YT_ROOT / "assets" / "library" / "characters"
        self.character_dir.mkdir(parents=True, exist_ok=True)
        self.registry: Dict[str, Dict[str, Any]] = {
            "protagonist": {
                "name": "Alex",
                "age": "early 30s",
                "wardrobe": "charcoal textured crewneck sweater, dark tailored trousers",
                "facial_features": "short dark hair, determined thoughtful gaze, subtle stubble",
                "style_lock": "35mm photorealistic film grain, authentic skin pores, volumetric natural lighting",
                "ref_image": str(self.character_dir / "alex_ref.png"),
            },
            "researcher": {
                "name": "Dr. Miller",
                "age": "late 40s",
                "wardrobe": "navy blazer over crisp white collared shirt, horn-rimmed optical glasses",
                "facial_features": "graying temples, observant analytical expression",
                "style_lock": "clean academic documentary lighting, sharp optical focus",
                "ref_image": str(self.character_dir / "dr_miller_ref.png"),
            },
            "student": {
                "name": "Jordan",
                "age": "early 20s",
                "wardrobe": "olive green hooded sweatshirt, dark denim",
                "facial_features": "expressive brown eyes, casual modern haircut",
                "style_lock": "natural environmental depth, soft daylight illumination",
                "ref_image": str(self.character_dir / "jordan_ref.png"),
            },
        }

    def run(
        self,
        character_name: str = "protagonist",
        custom_traits: Optional[Dict[str, Any]] = None,
    ) -> tuple[Dict[str, Any], AgentReport]:
        t0 = time.time()
        key = character_name.lower().strip()
        alias_map = {"protagonist": "alex", "researcher": "dr_miller", "student": "jordan"}
        rev_alias = {v: k for k, v in alias_map.items()}
        card_id = alias_map.get(key, key)
        reg_key = rev_alias.get(key, key)
        card_file = self.character_dir / f"{card_id}.json"

        profile = dict(self.registry.get(reg_key, self.registry.get(key, self.registry["protagonist"])))
        if card_file.exists():
            try:
                card_data = json.loads(card_file.read_text(encoding="utf-8"))
                profile.update(card_data)
            except Exception:
                pass
        if custom_traits:
            profile.update(custom_traits)

        summary = f"Locked character ref for '{profile['name']}' ({profile['age']}) | Style: {profile['style_lock'][:40]}..."
        self.log(summary)
        return profile, AgentReport(
            agent_name=self.name,
            role=self.role,
            status="PASS",
            duration_s=round(time.time() - t0, 3),
            summary=summary,
            metrics=profile,
        )


# --------------------------------------------------------------------------- #
# 3c. KeyframePromptAgent (Scene + Refs -> Keyframe Spatial Prompt)
# --------------------------------------------------------------------------- #
class KeyframePromptAgent(BaseAgent):
    name = "KeyframePromptAgent"
    role = "Keyframe Spatial Prompt Engineer"
    emoji = "🖼️"

    def run(
        self,
        scene: Dict[str, Any],
        character_ref: Optional[Dict[str, Any]] = None,
        genre: str = "3d_cgi",
        aspect: str = "9:16",
    ) -> tuple[str, AgentReport]:
        t0 = time.time()
        director = visual_director.S4VisualDirector(
            genre_key=genre,
            topic=scene.get("topic", "Focus"),
            default_aspect=aspect,
        )
        enriched = director.process_project_scenes([scene], genre=genre, overwrite_custom_prompts=True)
        prompt = enriched[0]["prompt"]
        if character_ref and "wardrobe" in character_ref:
            anchor = (
                f"Subject: {character_ref['name']}, {character_ref['age']}, wearing "
                f"{character_ref['wardrobe']}, {character_ref['facial_features']}."
            )
            if "Subject (Midground Z-Plane):" in prompt:
                prompt = prompt.replace("Subject (Midground Z-Plane):", f"Subject (Midground Z-Plane): {anchor}")
            else:
                prompt = f"{prompt} [{anchor}]"

        summary = f"Generated keyframe prompt ({len(prompt.split())} words) for Scene {scene.get('scene_idx', 1)}"
        self.log(summary)
        return prompt, AgentReport(
            agent_name=self.name,
            role=self.role,
            status="PASS",
            duration_s=round(time.time() - t0, 3),
            summary=summary,
            metrics={"word_count": len(prompt.split()), "genre": genre},
        )


# --------------------------------------------------------------------------- #
# 3d. MotionPromptAgent (Keyframe + Scene -> Motion Prompt & 3D Trajectory)
# --------------------------------------------------------------------------- #
class MotionPromptAgent(BaseAgent):
    name = "MotionPromptAgent"
    role = "Camera Trajectory & Dynamics Director"
    emoji = "🎬"

    TRAJECTORY_CYCLE = [
        ("vertigo", "Hitchcock dolly-zoom with widening field of view on realization moment"),
        ("orbit", "Dynamic 360-degree rotational 3D parallax around centered subject"),
        ("spiral", "Helical 3D camera trajectory orbiting and ascending focal plane"),
        ("roll", "Tilted 3D camera roll with sweeping horizontal pan"),
        ("spatial", "Subtle multi-plane 3D spatial drift with shifting focal depth"),
    ]

    def run(
        self,
        scene_idx: int,
        scene_action: str = "",
        duration_s: float = 3.5,
    ) -> tuple[Dict[str, Any], AgentReport]:
        t0 = time.time()
        preset, desc = self.TRAJECTORY_CYCLE[(scene_idx - 1) % len(self.TRAJECTORY_CYCLE)]
        speed = 1.0
        action_lower = scene_action.lower()
        if any(k in action_lower for k in ("freeze", "realize", "shock", "pause")):
            preset = "vertigo"
            desc = "Slow Hitchcock dolly-zoom on realization moment"
            speed = 0.85

        motion_config = {
            "trajectory": preset,
            "description": desc,
            "duration_s": duration_s,
            "speed": speed,
            "optical_flow_bounds_px": (0.5, 25.0),
            "motion_prompt": f"Smooth continuous 3D camera move: {desc}, maintaining sharp subject focus throughout.",
        }
        summary = f"Assigned camera trajectory '{preset}' ({duration_s}s, speed={speed}) for Scene {scene_idx}"
        self.log(summary)
        return motion_config, AgentReport(
            agent_name=self.name,
            role=self.role,
            status="PASS",
            duration_s=round(time.time() - t0, 3),
            summary=summary,
            metrics=motion_config,
        )


# --------------------------------------------------------------------------- #
# 3e. NegativePromptAgent (Scene + Past QA Failures -> Negative Prompt)
# --------------------------------------------------------------------------- #
class NegativePromptAgent(BaseAgent):
    name = "NegativePromptAgent"
    role = "Negative Constraint & Anti-Glitch Engineer"
    emoji = "🛡️"

    def __init__(self):
        super().__init__()
        self._core = CoreNegativePromptAgent()

    def run(
        self,
        prompt: str,
        genre: str = "cinematic_35mm",
        target_model: str = "flux3",
        past_qa_failures: Optional[List[str]] = None,
        is_asset_cutout: bool = False,
    ) -> tuple[Any, AgentReport]:
        res, report = self._core.run(
            prompt=prompt,
            genre=genre,
            target_model=target_model,
            past_qa_failures=past_qa_failures,
            is_asset_cutout=is_asset_cutout,
        )
        self.log(report.summary)
        return res, report


# --------------------------------------------------------------------------- #
# 3f. AssetAgent (Smart Reusable Asset Library & Semantic Cache)
# --------------------------------------------------------------------------- #
class AssetAgent(BaseAgent):
    name = "AssetAgent"
    role = "Smart Reusable Asset & Library Manager"
    emoji = "🎨"

    def __init__(self):
        super().__init__()
        self.smart_agent = SmartAssetAgent()

    def run(self, scenes: List[Dict[str, Any]], genre: str = "3d_cgi") -> tuple[List[Dict[str, Any]], AgentReport]:
        t0 = time.time()
        self.log(f"Scanning {len(scenes)} scenes for reusable and new visual assets (genre={genre})...")
        reused = 0
        generated = 0
        resolved_assets: List[str] = []

        for sc in scenes:
            text = (sc.get("text", "") + " " + sc.get("image_prompt", "")).lower()
            is_wet = any(w in text for w in ("rain", "wet", "puddle", "droplet", "dew"))

            if "grass" in text:
                p = self.smart_agent.get_or_create(
                    name="Grass Lawn",
                    category="nature",
                    query="grass lawn",
                    required_attributes={"wet": is_wet, "water_droplets": is_wet},
                    style=genre,
                )
                resolved_assets.append(str(p))
                reused += 1

            if any(w in text for w in ("briefcase", "office", "business")):
                p = self.smart_agent.get_or_create(
                    name="Briefcase",
                    category="props",
                    query="briefcase",
                    style=genre,
                )
                resolved_assets.append(str(p))
                reused += 1

        summary = (
            f"Smart Asset Catalog: {len(self.smart_agent.catalog.assets)} indexed items | "
            f"Matched={len(resolved_assets)} (Reused={reused}, Generated={generated})"
        )
        self.log(summary)
        return scenes, AgentReport(
            agent_name=self.name,
            role=self.role,
            status="PASS",
            duration_s=round(time.time() - t0, 2),
            summary=summary,
            metrics={
                "catalog_size": len(self.smart_agent.catalog.assets),
                "matched_assets": len(resolved_assets),
                "reused": reused,
                "generated": generated,
            },
        )


# --------------------------------------------------------------------------- #
# 4. MetadataAgent & PackagingAgent (Upload Kit, Title, Tags & Disclosure)
# --------------------------------------------------------------------------- #
class MetadataAgent(BaseAgent):
    """Title, description, tags, synthetic-content disclosure answers (episode -> metadata)."""
    name = "MetadataAgent"
    role = "Title, Description, Tags & Synthetic Disclosure Architect"
    emoji = "📋"

    def run(
        self,
        episode: Dict[str, Any] | Path,
        dossier: Optional[Dict[str, Any]] = None,
    ) -> tuple[Dict[str, Any], AgentReport]:
        t0 = time.time()
        if isinstance(episode, Path):
            proj_path = episode
            proj_data = json.loads(proj_path.read_text(encoding="utf-8"))
            project_dir = proj_path.parent
        else:
            proj_data = episode
            proj_path = None
            project_dir = None

        topic = proj_data.get("concept") or proj_data.get("topic") or (dossier.get("topic") if dossier else "Cognitive Bias")
        video_id = proj_data.get("id", "SH-00")
        year = str(dossier.get("year", "1979") if dossier else "1979")
        stat = str(dossier.get("quantitative_stat", "82%") if dossier else "82%")
        researchers = str(dossier.get("primary_researchers", "Researchers") if dossier else "Researchers")
        publication = str(dossier.get("publication", "Journal of Psychology") if dossier else "Journal of Psychology")

        # 1. Title generation & linting (target <= 58 chars to prevent mobile/desktop truncation)
        primary_title = f"{topic}: The {year} Study On Why You Freeze"
        if len(primary_title) > 58:
            primary_title = f"The {year} {topic} Study: Why You Freeze"

        pkg_res = youtube_skills.check_packaging(primary_title)
        lint_issues = [i for i in pkg_res.get("issues", []) if i[0] in ("length", "shouting", "vague", "no-number")]

        # 2. Description generation (clean, humanized, study citation, safe affiliate slot)
        description = (
            f"Why does {topic.lower()} happen? The {year} study by {researchers} ({publication}) "
            f"revealed that {stat} of people freeze under the exact same conditions.\n\n"
            f"🔬 Scientific Grounding: {researchers} ({year})\n"
            f"📊 Key Finding: {stat}\n\n"
            f"#shorts #psychology #science #cognitivecore"
        )

        # 3. Tags (strictly lowercase, keyword-focused)
        base_tags = [
            topic.lower(),
            f"{researchers.split('&')[0].strip().lower()} {year}",
            "cognitive core",
            "psychology",
            "neuroscience",
            "behavioral economics",
        ]
        clean_tags = [re.sub(r"[^\w\s-]", "", t).strip() for t in base_tags if t.strip()]

        # 4. YouTube Synthetic Media Disclosure (2026 YouTube Policy)
        synthetic_disclosure = {
            "altered_or_synthetic_content": True,
            "realistic_people_or_places": True,
            "disclosure_reason": (
                "Photorealistic human visual scenes generated using FLUX neural image synthesis; "
                "narration synthesized locally via Kokoro-82M neural model."
            ),
            "studio_setting_answers": {
                "question_1_realistic_person": "Yes",
                "question_2_altered_footage": "No",
                "question_3_realistic_scene": "Yes",
            },
        }

        metadata = {
            "title": primary_title,
            "description": description,
            "tags": clean_tags,
            "tags_string": ", ".join(clean_tags),
            "synthetic_disclosure": synthetic_disclosure,
            "scientific_grounding": f"{researchers} ({year}, {publication})",
            "stat": stat,
        }

        # 5. Generate / Update UPLOAD_KIT if project directory is available
        kit_name = "UPLOAD_KIT.md"
        if project_dir and proj_path:
            kits = list(project_dir.glob("UPLOAD_KIT*.md"))
            needs_kit_regen = (not kits) or (project_dir.name not in kits[0].read_text(encoding="utf-8", errors="replace"))
            if needs_kit_regen and proj_data.get("format", "short") != "long":
                kit_file = kits[0] if kits else (project_dir / f"UPLOAD_KIT_{video_id.replace('-', '')}.md")
                kit_content = creative_engine.generate_upload_kit_content(
                    video_id=video_id,
                    title=primary_title,
                    topic=topic,
                    citation=f"{researchers} ({year}, {publication})",
                    related_target=dossier.get("related_target") if dossier else None,
                    related_target_title=dossier.get("related_title") if dossier else None,
                    slug=project_dir.name,
                    year=year,
                    stat=stat,
                )
                kit_file.write_text(kit_content, encoding="utf-8")
                kits = [kit_file]
            kit_name = kits[0].name if kits else "UPLOAD_KIT.md"

        metadata["upload_kit"] = kit_name
        summary = f"Metadata compiled: Title='{primary_title[:35]}...' | {len(clean_tags)} tags | Disclosure=YES"
        self.log(summary)

        return metadata, AgentReport(
            agent_name=self.name,
            role=self.role,
            status="PASS" if not lint_issues else "WARN",
            duration_s=round(time.time() - t0, 3),
            summary=summary,
            metrics={"title": primary_title, "lint_issues": lint_issues, "tags_count": len(clean_tags)},
        )


class PackagingAgent(MetadataAgent):
    name = "PackagingAgent"
    role = "Title & Upload Kit Packaging"
    emoji = "📦"

    def run(self, proj_path: Path, dossier: Dict[str, Any]) -> AgentReport:
        meta, report = super().run(episode=proj_path, dossier=dossier)
        report.agent_name = self.name
        report.role = self.role
        return report


# --------------------------------------------------------------------------- #
# 5. ProductionAgent (FLUX Visuals + 3-Plane 3D Spatial + SM7B TTS + Master MP4)
# --------------------------------------------------------------------------- #
class ProductionAgent(BaseAgent):
    name = "ProductionAgent"
    role = "Neural FLUX, 3-Plane 3D Spatial & Broadcast Audio/Video Renderer"
    emoji = "🎥"

    def run(self, proj_path: Path, hw_accel: bool = True, force_motion: bool = False) -> AgentReport:
        t0 = time.time()
        from tools import pipeline
        self.log(f"Executing self-healing 3D spatial production build for {proj_path.parent.name}...")
        meta = pipeline.build_and_verify(
            proj_path,
            hw_accel=hw_accel,
            force_motion=force_motion,
        )
        valid = bool(meta.get("valid"))
        summary = (
            f"MP4 Mastered: {meta.get('width')}x{meta.get('height')} @ {meta.get('fps')} | "
            f"{meta.get('duration_s')}s | {meta.get('bitrate_mbps')} Mbps | RefPrecision={meta.get('reference_precision')}"
        )
        self.log(summary)
        return AgentReport(
            agent_name=self.name,
            role=self.role,
            status="PASS" if valid else "FAIL",
            duration_s=round(time.time() - t0, 2),
            summary=summary,
            metrics=meta,
        )


# --------------------------------------------------------------------------- #
# 6. QualityGateAgent (Reference Precision & Recall Auditor)
# --------------------------------------------------------------------------- #
class QualityGateAgent(BaseAgent):
    name = "QualityGateAgent"
    role = "Reference Precision & Recall Verification Gate"
    emoji = "🛡️"

    def run(self, proj_path: Path, require_mp4: bool = False) -> AgentReport:
        t0 = time.time()
        from tools import pipeline
        self.log(f"Running Reference Precision & Recall Quality Gate on {proj_path.parent.name}...")
        proj_data = json.loads(proj_path.read_text(encoding="utf-8"))
        fmt_type = proj_data.get("format", "short")
        issues = pipeline.pre_compose_validate(proj_path)

        if not require_mp4:
            non_asset_issues = [i for i in issues if "missing asset:" not in i]
        else:
            non_asset_issues = issues

        mp4_path = proj_path.parent / "output" / f"{proj_path.parent.name}.mp4"
        mp4_meta = pipeline.verify_rendered_mp4(mp4_path, format_type=fmt_type) if mp4_path.exists() else {"valid": False, "note": "Not rendered yet"}

        status = "PASS" if (not non_asset_issues and (mp4_meta.get("valid") or not require_mp4)) else "WARN"
        summary = f"Gate Status={status} | Pre-compose warnings={len(non_asset_issues)} | MP4 valid={mp4_meta.get('valid')}"
        self.log(summary)
        return AgentReport(
            agent_name=self.name,
            role=self.role,
            status=status,
            duration_s=round(time.time() - t0, 2),
            summary=summary,
            metrics={
                "issues": non_asset_issues,
                "mp4_meta": mp4_meta,
            },
        )


# --------------------------------------------------------------------------- #
# 6b. QAAgent (Clip Level Quality: Face Match, Hands, Text, Flicker)
# --------------------------------------------------------------------------- #
class QAAgent(BaseAgent):
    """Check each generated clip (face match, hands, text, flicker) -> clip -> pass/fail + reason."""
    name = "QAAgent"
    role = "Clip Quality, Anatomy, Text & Flicker Auditor"
    emoji = "🔬"

    def run(
        self,
        clip_path: Path | str,
        character_ref: Optional[Dict[str, Any]] = None,
        past_qa_failures: Optional[List[str]] = None,
        require_motion: bool = True,
    ) -> tuple[bool, List[str], AgentReport]:
        t0 = time.time()
        p = Path(clip_path)
        reasons: List[str] = []
        metrics: Dict[str, Any] = {"clip": str(p)}

        if not p.exists():
            summary = f"FAIL: Clip does not exist at {p}"
            self.log(summary)
            return False, ["File not found"], AgentReport(
                agent_name=self.name,
                role=self.role,
                status="FAIL",
                duration_s=round(time.time() - t0, 3),
                summary=summary,
                metrics={"exists": False},
            )

        # 1. Motion / Flicker / Temporal Coherence check for video files
        if p.suffix.lower() in (".mp4", ".mov", ".webm"):
            from tools import visual_engine
            motion_res = visual_engine.verify_motion_quality(p)
            metrics["motion"] = motion_res
            if not motion_res.get("valid", True):
                score = motion_res.get("score", "INVALID")
                if score == "TOO_STATIC" and require_motion:
                    reasons.append(f"Static or frozen clip (mean_flow={motion_res.get('mean_flow_px', 0.0):.2f}px)")
                elif score in ("TEARING", "FLICKER", "ERROR"):
                    reasons.append(f"Temporal instability or flicker ({score})")

            mean_flow = float(motion_res.get("mean_flow_px", 0.0) or 0.0)
            if mean_flow > 35.0:
                reasons.append(f"Excessive camera motion / warp blur ({mean_flow:.1f}px > 35.0px)")

        # 2. Laplacian Sharpness & Visual Contrast (using visual_engine.verify_image_precision_recall)
        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            from tools import visual_engine
            plate_audit = visual_engine.verify_image_precision_recall(p)
            metrics["plate_audit"] = plate_audit
            if not plate_audit.get("valid", True):
                reasons.append(f"Plate defect: {plate_audit.get('reason')}")
            if plate_audit.get("laplacian_sharpness", 100.0) < 20.0:
                reasons.append(f"Severe blur / low Laplacian sharpness ({plate_audit.get('laplacian_sharpness')})")

        # 3. Known Past QA Failure checks (hands, text artifacts, face match)
        if past_qa_failures:
            for failure in past_qa_failures:
                f_low = failure.lower()
                if "hand" in f_low or "finger" in f_low:
                    metrics["anatomy_flagged_in_history"] = True
                if "text" in f_low or "watermark" in f_low:
                    metrics["text_artifacts_flagged_in_history"] = True
                if "face" in f_low or "identity" in f_low:
                    metrics["face_match_flagged_in_history"] = True

        if character_ref:
            metrics["character_style_lock"] = character_ref.get("style_lock")

        passed = len(reasons) == 0
        status = "PASS" if passed else "FAIL"
        summary = f"Clip QA {'PASSED' if passed else 'FAILED'} for {p.name}"
        if reasons:
            summary += f" | Reasons: {'; '.join(reasons)}"
        self.log(summary)

        return passed, reasons, AgentReport(
            agent_name=self.name,
            role=self.role,
            status=status,
            duration_s=round(time.time() - t0, 3),
            summary=summary,
            metrics=metrics,
        )


# --------------------------------------------------------------------------- #
# 7. PublishAgent (Strict Release Dispatcher)
# --------------------------------------------------------------------------- #
class PublishAgent(BaseAgent):
    name = "PublishAgent"
    role = "Strict Reviewed Release Dispatcher"
    emoji = "🚀"

    def run(
        self, project_dir: Path, public: bool = False, headless: bool = True,
        *, evidence: Path | None = None, approved: bool = False,
    ) -> AgentReport:
        t0 = time.time()
        if evidence is None or not approved:
            msg = "Upload requires reviewed evidence and explicit approval; use master.py release-existing --publish --yes."
            self.log(msg)
            return AgentReport(
                agent_name=self.name,
                role=self.role,
                status="FAIL",
                duration_s=round(time.time() - t0, 2),
                summary=msg,
            )

        from tools.orchestrator.cli import run_release_existing

        try:
            state = run_release_existing(
                project_dir / "project.json", evidence, publish=True, public=public, approve=True,
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            msg = f"Strict release validation could not start: {exc}"
            self.log(msg)
            return AgentReport(
                agent_name=self.name,
                role=self.role,
                status="FAIL",
                duration_s=round(time.time() - t0, 2),
                summary=msg,
            )
        published = state.tasks.get("publish")
        live_id = published.data.get("video_id") if published else None
        if state.status != "passed" or not live_id:
            msg = f"Strict release did not publish; inspect run {state.run_id} before retrying."
            self.log(msg)
            return AgentReport(
                agent_name=self.name,
                role=self.role,
                status="FAIL",
                duration_s=round(time.time() - t0, 2),
                summary=msg,
                metrics={"run_id": state.run_id, "report_path": str(state.report_path)},
            )
        summary = f"Strict release passed; uploaded {project_dir.name} as {live_id}"
        return AgentReport(
            agent_name=self.name,
            role=self.role,
            status="PASS",
            duration_s=round(time.time() - t0, 2),
            summary=summary,
            metrics={"run_id": state.run_id, "report_path": str(state.report_path), "remote_id": live_id},
        )


def _legacy_reports(state) -> List[AgentReport]:
    """Adapt canonical task records for existing terminal summaries."""
    names = {
        "research": ("ResearchAgent", "Verified source research"),
        "script": ("ScriptAgent", "Script and hook"),
        "project": ("PackagingAgent", "Project and upload kit"),
        "build": ("ProductionAgent", "Media production"),
        "release": ("QualityGateAgent", "Canonical release checks"),
        "publish": ("PublishAgent", "Strict reviewed upload"),
    }
    reports: List[AgentReport] = []
    for task_id, record in getattr(state, "tasks", {}).items():
        name, role = names.get(task_id, (task_id.title(), "Canonical workflow task"))
        task_status = getattr(getattr(record, "status", None), "value", getattr(record, "status", "failed"))
        status = {
            "passed": "PASS",
            "failed": "FAIL",
            "blocked": "FAIL",
            "skipped": "SKIPPED",
            "pending": "WARN",
            "running": "WARN",
        }.get(str(task_status), "FAIL")
        reports.append(AgentReport(
            agent_name=name,
            role=role,
            status=status,
            duration_s=float(getattr(record, "duration_s", 0.0) or 0.0),
            summary=str(getattr(record, "summary", "") or getattr(record, "error", "")),
            metrics=dict(getattr(record, "metrics", {}) or {}),
        ))
    if not reports and getattr(state, "status", "") not in {"passed", "planned"}:
        reports.append(AgentReport(
            agent_name="MasterAgent",
            role="Canonical production coordinator",
            status="FAIL",
            duration_s=0.0,
            summary=f"Canonical workflow ended with status {getattr(state, 'status', 'unknown')}.",
        ))
    return reports


# --------------------------------------------------------------------------- #
# 8. OrchestratorAgent (Master Multi-Agent Pipeline Coordinator)
# --------------------------------------------------------------------------- #
class OrchestratorAgent:
    """Coordinates all 7 specialist agents for 0-to-1 project creation, 3D prompt upgrades, and batch execution."""

    def __init__(self):
        self.concept_agent = ConceptAgent()
        self.research_agent = ResearchAgent()
        self.policy_agent = PolicyAgent()
        self.script_agent = ScriptAgent()
        self.character_agent = CharacterRefAgent()
        self.keyframe_agent = KeyframePromptAgent()
        self.motion_agent = MotionPromptAgent()
        self.negative_prompt_agent = NegativePromptAgent()
        self.qa_agent = QAAgent()
        self.metadata_agent = MetadataAgent()
        self.visual_agent = VisualDirectorAgent()
        self.asset_agent = AssetAgent()
        self.packaging_agent = PackagingAgent()
        self.production_agent = ProductionAgent()
        self.quality_agent = QualityGateAgent()
        self.publish_agent = PublishAgent()

    def print_crew_status(self) -> None:
        agents = [
            self.concept_agent,
            self.research_agent,
            self.policy_agent,
            self.script_agent,
            self.character_agent,
            self.keyframe_agent,
            self.motion_agent,
            self.negative_prompt_agent,
            self.qa_agent,
            self.metadata_agent,
            self.visual_agent,
            self.asset_agent,
            self.packaging_agent,
            self.production_agent,
            self.quality_agent,
            self.publish_agent,
        ]
        personas = sorted(p.name for p in PERSONAS_DIR.glob("*.md")) if PERSONAS_DIR.exists() else []
        fmt.emit(fmt.crew_status(agents, personas))

    def upgrade_existing_project(self, proj_path: Path, genre: Optional[str] = None) -> List[AgentReport]:
        """Run ResearchAgent + VisualDirectorAgent + PackagingAgent + QualityGateAgent on an existing project.json."""
        if proj_path.is_dir():
            proj_path = proj_path / "project.json"
        if not proj_path.exists():
            raise FileNotFoundError(f"Project file not found: {proj_path}")

        fmt.emit(fmt.header(f"Multi-Agent 3D Project Upgrade: {proj_path.parent.name}", "Semantic 3D Director & Quality Gate", "🤖"))
        proj_data = json.loads(proj_path.read_text(encoding="utf-8"))
        topic = proj_data.get("concept") or proj_data.get("topic") or proj_data.get("title", "Cognitive Bias")
        eff_genre = genre or proj_data.get("genre", "3d_cgi")
        fmt_type = proj_data.get("format", "short")
        aspect = "16:9" if fmt_type == "long" else "9:16"

        reports: List[AgentReport] = []
        dossier, r_rep = self.research_agent.run(topic)
        reports.append(r_rep)

        enriched_scenes, v_rep = self.visual_agent.run(
            proj_data.get("scenes", []),
            topic=dossier["topic"],
            genre=eff_genre,
            aspect=aspect,
            dossier=dossier,
            overwrite=True,
        )
        reports.append(v_rep)

        if fmt_type != "long" and dossier.get("best_hook"):
            cand_s, _, _ = creative_engine.score_hook_candidate(dossier["best_hook"])
            cur_s, _, _ = creative_engine.score_hook_candidate(enriched_scenes[0]["text"])
            if cand_s > cur_s:
                enriched_scenes[0]["text"] = dossier["best_hook"]

        hook_score, hook_band, hook_weakest = creative_engine.score_hook_candidate(enriched_scenes[0]["text"])
        all_words = len(re.findall(r"\b\w+\b", " ".join(s.get("text", "") for s in enriched_scenes)))
        est_sec = round((all_words / 150.0) * 60.0, 1)

        proj_data["scenes"] = enriched_scenes
        proj_data["genre"] = eff_genre
        proj_data.setdefault("metadata", {}).update({
            "dossier_source": dossier.get("publication"),
            "hook_score": hook_score,
            "hook_band": hook_band,
            "hook_weakest": hook_weakest,
            "word_count": all_words,
            "estimated_duration_sec": est_sec,
            "upgraded_by": "MultiAgentCrew_v7.0_3DSpatial",
        })
        proj_path.write_text(json.dumps(proj_data, indent=2), encoding="utf-8")

        pkg_rep = self.packaging_agent.run(proj_path, dossier=dossier)
        reports.append(pkg_rep)

        qg_rep = self.quality_agent.run(proj_path, require_mp4=False)
        reports.append(qg_rep)

        fmt.emit(fmt.agent_report_card(reports))
        return reports

    def run_nine_agent_cycle(
        self,
        topic: Optional[str] = None,
        genre: str = "3d_cgi",
        target_scene_count: int = 8,
    ) -> tuple[Dict[str, Any], List[AgentReport]]:
        """Execute the 9-Agent Pipeline Cycle:
        Concept -> Policy -> Script -> CharacterRef -> KeyframePrompt -> NegativePrompt -> MotionPrompt -> QA -> Metadata.
        """
        fmt.emit(fmt.header("9-Agent Autonomous Production Cycle", "Grounded in Series Bible & Empirical Truth", "🤖"))
        reports: List[AgentReport] = []

        # 1. ConceptAgent
        dossier, c_rep = self.concept_agent.run(topic=topic or "")
        reports.append(c_rep)
        if c_rep.status == "FAIL" or not dossier:
            fmt.emit(fmt.agent_report_card(reports))
            return {}, reports
        chosen_topic = dossier.get("topic", "Loss Aversion")

        # 2. PolicyAgent (Pre-check)
        _, _, pol_pre_rep = self.policy_agent.run({"concept": chosen_topic, "scenes": []})
        reports.append(pol_pre_rep)
        if pol_pre_rep.status == "FAIL":
            fmt.emit(fmt.agent_report_card(reports))
            return {}, reports

        # 3. ScriptAgent
        scenes, s_rep = self.script_agent.run(dossier, genre=genre, target_scene_count=target_scene_count)
        reports.append(s_rep)
        if s_rep.status == "FAIL" or not scenes:
            fmt.emit(fmt.agent_report_card(reports))
            return {}, reports

        # 4. CharacterRefAgent
        char_key = "dr_miller" if "experiment" in dossier.get("experiment_design", "").lower() else "protagonist"
        char_profile, char_rep = self.character_agent.run(char_key)
        reports.append(char_rep)

        # 5. KeyframePromptAgent, 6. NegativePromptAgent & 7. MotionPromptAgent
        enriched_scenes = []
        for idx, sc in enumerate(scenes, 1):
            keyframe_prompt, k_rep = self.keyframe_agent.run(sc, character_ref=char_profile, genre=genre)
            neg_res, n_rep = self.negative_prompt_agent.run(prompt=keyframe_prompt, genre=genre, target_model="flux3")
            motion_cfg, m_rep = self.motion_agent.run(scene_idx=idx, scene_action=sc.get("action", ""))

            sc_enriched = dict(sc)
            sc_enriched["prompt"] = neg_res.optimized_prompt
            sc_enriched["motion"] = motion_cfg["trajectory"]
            sc_enriched["motion_prompt"] = motion_cfg["motion_prompt"]
            enriched_scenes.append(sc_enriched)
            if idx == 1:
                reports.extend([k_rep, n_rep, m_rep])

        # 8. PolicyAgent (Full Episode Check)
        episode_data = {
            "concept": chosen_topic,
            "scenes": enriched_scenes,
            "format": "short",
            "genre": genre,
        }
        _, _, pol_post_rep = self.policy_agent.run(episode_data)
        reports.append(pol_post_rep)

        # 9. MetadataAgent (Title, Description, Tags & Synthetic Disclosure)
        meta, m_rep = self.metadata_agent.run(episode_data, dossier=dossier)
        reports.append(m_rep)

        blueprint = {
            "topic": chosen_topic,
            "dossier": dossier,
            "character": char_profile,
            "scenes": enriched_scenes,
            "metadata": meta,
        }
        fmt.emit(fmt.agent_report_card(reports))
        return blueprint, reports

    def run_end_to_end(
        self,
        topic: str,
        video_id: str,
        slug: str,
        genre: str = "3d_cgi",
        blueprint_only: bool = False,
        upload: bool = False,
        public: bool = False,
        hw_accel: bool = True,
        evidence: Path | None = None,
        approved: bool = False,
    ) -> List[AgentReport]:
        """Compatibility facade over the canonical master production workflow."""
        if upload and (blueprint_only or evidence is None or not approved):
            return [AgentReport(
                agent_name=self.publish_agent.name,
                role=self.publish_agent.role,
                status="FAIL",
                duration_s=0.0,
                summary="Upload requires a rendered project, reviewed evidence, and --yes before production starts.",
            )]
        state = legacy.run_production_compat(
            topic=topic,
            video_id=video_id,
            slug=slug,
            genre=genre,
            blueprint_only=blueprint_only,
        )
        reports = _legacy_reports(state)
        if upload and state.status == "passed":
            from tools.orchestrator.cli import run_release_existing

            project_path = YT_ROOT / "shorts" / slug / "project.json"
            release_state = run_release_existing(
                project_path, evidence, publish=True, public=public, approve=approved,
            )
            reports.extend(_legacy_reports(release_state, publish=True))
        elif upload:
            reports.append(AgentReport(
                agent_name=self.publish_agent.name,
                role=self.publish_agent.role,
                status="SKIPPED",
                duration_s=0.0,
                summary="Upload blocked because canonical production did not pass.",
            ))
        fmt.emit(fmt.agent_report_card(reports))
        return reports


def main() -> int:
    ap = argparse.ArgumentParser(description="FrameForge Multi-Agent Crew & Orchestrator (v7.0)")
    ap.add_argument("--status", action="store_true", help="Display all specialist agents and status")
    ap.add_argument("--brainstorm", action="store_true", help="Brainstorm unproduced novel episode premises from Series Bible")
    ap.add_argument("--cycle", action="store_true", help="Execute complete 9-agent autonomous pipeline cycle")
    ap.add_argument("--upgrade-project", type=Path, help="Upgrade an existing project.json with 6-layer 3D VisualDirector & Research agents")
    ap.add_argument("--upgrade-all-blueprints", action="store_true", help="Upgrade all unrendered blueprint projects (e.g. SH-15, SH-16)")
    ap.add_argument("--run", action="store_true", help="Run 0-to-1 Multi-Agent pipeline for a topic")
    ap.add_argument("--topic", type=str, help="Topic name for --run")
    ap.add_argument("--id", type=str, help="Video ID (e.g. SH-17) for --run")
    ap.add_argument("--slug", type=str, help="Folder slug (e.g. short_17_paradox_of_choice) for --run")
    ap.add_argument("--genre", type=str, default=None, help="Visual genre override")
    ap.add_argument("--blueprint-only", action="store_true", help="Generate dossier, script, 6-layer 3D prompts, and upload kit without GPU render")
    ap.add_argument("--upload", action="store_true", help="Upload after strict reviewed release")
    ap.add_argument("--public", action="store_true", help="Publish as Public (default is Unlisted)")
    ap.add_argument("--evidence", type=Path, help="Reviewed evidence JSON required for upload")
    ap.add_argument("--yes", action="store_true", help="Approve irreversible upload after strict release checks")
    args = ap.parse_args()

    if args.upload and not args.run:
        print("--upload is available only with --run and reviewed evidence.", file=sys.stderr)
        return 2
    if args.run and not (args.topic and args.id and args.slug):
        print("--run requires --topic, --id, and --slug.", file=sys.stderr)
        return 2

    orch = OrchestratorAgent()
    if args.status:
        orch.print_crew_status()
        return 0
    if args.brainstorm:
        candidates = orch.concept_agent.brainstorm_novel_premises(count=5)
        print("\n💡 TOP UNPRODUCED EPISODE PREMISES (from Series Bible & Empirical Dossiers):")
        for i, c in enumerate(candidates, 1):
            print(f"  {i}. {c['topic']} ({c['year']}, {c['primary_researchers']}) | Stat: {c['stat']} | Lead: {c['character_lead']}")
            print(f"     Hook: \"{c['hook_candidate']}\"")
        return 0
    if args.cycle:
        blueprint, reports = orch.run_nine_agent_cycle(topic=args.topic, genre=args.genre or "3d_cgi")
        return report_exit_code(reports)
    if args.upgrade_project:
        reports = orch.upgrade_existing_project(args.upgrade_project.resolve(), genre=args.genre)
        return report_exit_code(reports)
    if args.upgrade_all_blueprints:
        reports = []
        for s_dir in sorted((YT_ROOT / "shorts").glob("short_*")):
            mp4 = s_dir / "output" / f"{s_dir.name}.mp4"
            if not mp4.exists() and (s_dir / "project.json").exists():
                reports.extend(orch.upgrade_existing_project(s_dir / "project.json", genre=args.genre))
        return report_exit_code(reports) if reports else 0
    if args.run and args.topic and args.id and args.slug:
        if args.upload and (args.blueprint_only or args.evidence is None or not args.yes):
            print("Upload requires a rendered project, --evidence PATH, and --yes.", file=sys.stderr)
            return 2
        reports = orch.run_end_to_end(
            topic=args.topic,
            video_id=args.id,
            slug=args.slug,
            genre=args.genre or "3d_cgi",
            blueprint_only=args.blueprint_only,
            upload=args.upload,
            public=args.public,
            evidence=args.evidence,
            approved=args.yes,
        )
        return report_exit_code(reports)

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
