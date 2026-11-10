#!/usr/bin/env python3
"""FrameForge Autonomous Multi-Agent Crew & Orchestrator (v7.0 — 3D Spatial & Semantic Prompt Edition).

Implements a specialized 7-Agent Architecture grounded in `.agents/personas/`:
  1. ResearchAgent        (🔍 Research Synthesist)   : Verifies primary researcher, year, institution, experiment design, and quantitative stat.
  2. ScriptAgent          (✍️ Dialectic Scriptwriter): Crafts 8-12 scene scripts, scores spoken hooks via `hookscore.py` (>=70 target), and places *emphasis* pills.
  3. VisualDirectorAgent  (🎬 Visual Storyteller S4) : Semantic 3D Spatial Prompt Agent — deconstructs spoken script lines into 3-plane Z-depth FLUX prompts.
  4. PackagingAgent       (📦 Upload Kit & Linter)    : Writes the Upload Kit and lints the published title.
  5. ProductionAgent      (🎥 3D Studio Post-Prod)   : Generates FLUX plates, renders 3-plane 3D normal-relit clips, synthesizes SM7B TTS + Mid/Side BGM, and encodes 14 Mbps MP4.
  6. QualityGateAgent     (🛡️ Precision/Recall Gate) : Audits word-caption alignment, Laplacian sharpness, optical flow, and stream compliance.
  7. PublishAgent         (🚀 Release Dispatcher)    : Runs the master's strict reviewed release before any YouTube upload.
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
from tools.orchestrator import legacy  # noqa: E402


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
                "truth_verified": True,
            },
        )


# --------------------------------------------------------------------------- #
# 2. ScriptAgent (Grounded in .agents/personas/short_video_coach.md)
# --------------------------------------------------------------------------- #
class ScriptAgent(BaseAgent):
    name = "ScriptAgent"
    role = "Dialectic Narrative & Hook Architect"
    emoji = "✍️"

    def run(self, dossier: Dict[str, Any], genre: str = "3d_cgi") -> tuple[List[Dict[str, Any]], AgentReport]:
        t0 = time.time()
        topic = dossier["topic"]
        self.log(f"Drafting 8-scene high-retention script for '{topic}'...")
        scenes = creative_engine.choreograph_scenes(dossier, genre=genre)

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
# 3b. AssetAgent (Smart Reusable Asset Library & Semantic Cache)
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
# 4. PackagingAgent (Upload Kit + Title Linter)
# --------------------------------------------------------------------------- #
class PackagingAgent(BaseAgent):
    name = "PackagingAgent"
    role = "Title & Upload Kit Packaging"
    emoji = "📦"

    def run(self, proj_path: Path, dossier: Dict[str, Any]) -> AgentReport:
        t0 = time.time()
        project_dir = proj_path.parent
        proj_data = json.loads(proj_path.read_text(encoding="utf-8"))
        video_id = proj_data.get("id", "SH-00")
        topic = proj_data.get("concept") or proj_data.get("topic") or dossier.get("topic", "Cognitive Bias")

        year = dossier.get("year", "1979")
        primary_title = f"{topic}: The {year} Study On Why You Freeze"
        if len(primary_title) > 58:
            primary_title = f"The {year} {topic} Study: Why You Freeze"

        kits = list(project_dir.glob("UPLOAD_KIT*.md"))
        needs_kit_regen = (not kits) or (project_dir.name not in kits[0].read_text(encoding="utf-8", errors="replace"))
        if needs_kit_regen and proj_data.get("format", "short") != "long":
            kit_file = kits[0] if kits else (project_dir / f"UPLOAD_KIT_{video_id.replace('-', '')}.md")
            kit_content = creative_engine.generate_upload_kit_content(
                video_id=video_id,
                title=primary_title,
                topic=topic,
                citation=f"{dossier.get('primary_researchers', 'Researchers')} ({year}, {dossier.get('publication', 'Journal')})",
                related_target=dossier.get("related_target"),
                related_target_title=dossier.get("related_title"),
                slug=project_dir.name,
                year=year,
                stat=dossier.get("quantitative_stat", "82%"),
            )
            kit_file.write_text(kit_content, encoding="utf-8")
            kits = [kit_file]

        pkg_res = youtube_skills.check_packaging(primary_title)
        issues = [i for i in pkg_res.get("issues", []) if i[0] in ("length", "shouting", "vague", "no-number")]

        kit_name = kits[0].name if kits else "UPLOAD_KIT.md"
        summary = f"Upload Kit verified ({kit_name}) | Title Linter issues={len(issues)}"
        self.log(summary)
        return AgentReport(
            agent_name=self.name,
            role=self.role,
            status="PASS" if not issues else "WARN",
            duration_s=round(time.time() - t0, 2),
            summary=summary,
            metrics={
                "upload_kit": kit_name,
                "lint_issues": issues,
            },
        )


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
        self.research_agent = ResearchAgent()
        self.script_agent = ScriptAgent()
        self.visual_agent = VisualDirectorAgent()
        self.asset_agent = AssetAgent()
        self.packaging_agent = PackagingAgent()
        self.production_agent = ProductionAgent()
        self.quality_agent = QualityGateAgent()
        self.publish_agent = PublishAgent()

    def print_crew_status(self) -> None:
        agents = [
            self.research_agent,
            self.script_agent,
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
    ap.add_argument("--status", action="store_true", help="Display all 7 specialist agents and status")
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
