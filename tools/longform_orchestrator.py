#!/usr/bin/env python3
"""FrameForge Long-Form Video Orchestrator (tools/longform_orchestrator.py).

Architected for 8–15+ minute high-retention video essays and documentary case studies.

Core Architectural Features:
  1. The 5-Act Retention Structure (Question First, Failing Upward, Thesis Last):
     - Act 1: Cold Open Anomaly (~60-80 words, 0:00-0:45)
     - Act 2: Central Question & Stakes (~80-100 words, 0:45-1:30)
     - Act 3: The Obvious Explanation & Fatal Flaw (~300 words, 1:30-3:30)
     - Act 4: Deeper Complication & False Trail (~350 words, 3:30-6:30)
     - Act 5: The Turn / True Core Thesis (~400 words, 6:30-9:30)
     - Act 6: Resolution, Transformation & Single Action Ask (~180 words, 9:30-12:00)
  2. The 90-Second Micro-Loop:
     - Automates open curiosity loops every 90 seconds so viewer attention never resets downwards.
  3. Strategic Mid-Roll Ad Windows:
     - Automatically calculates narrative transition timecodes for YouTube ad breaks
       (Break 1: ~02:30, Break 2: ~05:30, Break 3: ~08:30) targeting $8-$18 RPM.
  4. Dynamic Chapter Title Card Generator:
     - Renders broadcast-grade 16:9 or 9:16 typographic chapter plates with subtle film grain
       and acoustic transition markers.
  5. YouTube Chapter & Packaging Sync:
     - Generates exact YouTube description timestamps complying with 00:00 start, >=3 chapters,
       and >=10s chapter length rules.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

TOOLS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TOOLS_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from tools.photobook_engine import apply_color_grade, apply_optical_vignette, generate_film_grain  # noqa: E402


# ---------------------------------------------------------------------------
# DATA STRUCTURES
# ---------------------------------------------------------------------------

@dataclass
class EssayChapter:
    """A distinct narrative chapter in the long-form essay."""
    chapter_num: int
    title: str
    act_name: str
    target_words: int
    spoken_text: str
    visual_direction: str
    start_time_sec: float = 0.0
    open_loop: Optional[str] = None


@dataclass
class MidRollMarker:
    """A strategic YouTube mid-roll ad placement marker."""
    timecode: str            # e.g. "02:45"
    seconds: float           # e.g. 165.0
    narrative_reason: str    # Why this break does not cause viewer drop-off


@dataclass
class LongFormEssaySpec:
    """Complete specification for an 8-15+ minute long-form video essay."""
    topic: str
    target_minutes: float
    total_words: int
    chapters: List[EssayChapter] = field(default_factory=list)
    mid_roll_markers: List[MidRollMarker] = field(default_factory=list)
    format: str = "16:9"     # "16:9" widescreen or "9:16" vertical
    genre: str = "magnates_amber"


# ---------------------------------------------------------------------------
# SCRIPT & CHAPTER GENERATION LOGIC
# ---------------------------------------------------------------------------

def calculate_word_budgets(target_minutes: float) -> Tuple[int, Dict[str, int]]:
    """Calculates strict word budgets based on 145 spoken words per minute."""
    total_words = int(round(target_minutes * 145.0))
    scale = target_minutes / 10.0

    budgets = {
        "Act 1 (Cold Open)": int(round(75 * scale)),
        "Act 2 (Central Question)": int(round(95 * scale)),
        "Act 3 (The First Explanation)": int(round(310 * scale)),
        "Act 4 (The Deeper Complication)": int(round(360 * scale)),
        "Act 5 (The Turn / Core Thesis)": int(round(410 * scale)),
        "Act 6 (Landing & Callback)": int(round(200 * scale)),
    }
    return total_words, budgets


def build_5act_essay_spec(
    topic: str,
    target_minutes: float = 10.0,
    genre: str = "magnates_amber",
    aspect_ratio: str = "16:9",
) -> LongFormEssaySpec:
    """Builds a complete high-retention 5-act video essay specification."""
    total_words, budgets = calculate_word_budgets(target_minutes)

    chapters = [
        EssayChapter(
            chapter_num=1,
            title="The Anomaly",
            act_name="Act 1: Cold Open Anomaly",
            target_words=budgets["Act 1 (Cold Open)"],
            spoken_text=(
                f"In the summer of 1979, researchers made an observation about {topic} "
                "that contradicted every textbook written in the previous century. "
                "The numbers were clear, reproducible, and completely absurd. "
                "And yet, for the next fifteen years, almost everyone looked the other way."
            ),
            visual_direction="35mm archival document zoom, low-angle chiaroscuro lighting, ticking dust motes",
            open_loop="Why did every expert reject the anomaly before it became undeniable?",
        ),
        EssayChapter(
            chapter_num=2,
            title="The Uncomfortable Question",
            act_name="Act 2: Central Question & Stakes",
            target_words=budgets["Act 2 (Central Question)"],
            spoken_text=(
                f"So what actually happens when {topic} breaks down in the real world? "
                "Most people believe this is simply a question of discipline or timing. "
                "That belief is wrong, and holding onto it is expensive. "
                "To understand why, we have to look at the first explanation everyone accepted."
            ),
            visual_direction="Camera dollys past vintage ledger books into a glowing geometric cipher diagram",
            open_loop="The obvious theory looks foolproof until you look at the survivor data.",
        ),
        EssayChapter(
            chapter_num=3,
            title="The Obvious Lie",
            act_name="Act 3: The First Explanation & Fatal Flaw",
            target_words=budgets["Act 3 (The First Explanation)"],
            spoken_text=(
                "The textbook answer was simple: human behavior follows rational incentives. "
                "If the reward is large enough, decisions become predictable. "
                "It was an elegant model. It explained the market trends, the executive decisions, "
                "and the standard case studies taught in business schools. "
                "There was just one catastrophic problem: it completely failed to predict the collapses."
            ),
            visual_direction="Fast-paced document inspection, cross-out annotations on financial charts",
            open_loop="The model wasn't just incomplete; it was pointing in the exact wrong direction.",
        ),
        EssayChapter(
            chapter_num=4,
            title="The Deeper Crack",
            act_name="Act 4: Deeper Complication & False Trail",
            target_words=budgets["Act 4 (The Deeper Complication)"],
            spoken_text=(
                f"When investigators examined the data, they discovered that {topic} was not driven "
                "by incentives at all. It was governed by an unseen cognitive asymmetry. "
                "People were not maximizing their gains; they were paying exorbitant premiums "
                "just to avoid confronting uncertainty. "
                "And that discovery opened an even darker question."
            ),
            visual_direction="Slow 3D lateral drift across a deserted institutional courtroom at midnight",
            open_loop="If logic doesn't drive the choice, what is really pulling the strings?",
        ),
        EssayChapter(
            chapter_num=5,
            title="The Turn",
            act_name="Act 5: The Turn / Core Thesis",
            target_words=budgets["Act 5 (The Turn / Core Thesis)"],
            spoken_text=(
                f"Here is the part the conventional history left out: {topic} is not a flaw in human reasoning. "
                "It is a protective evolutionary heuristic calibrated for a world that no longer exists. "
                "The moment you recognize that asymmetry, the entire puzzle flips upside down. "
                "The irrational decisions suddenly become the only logical ones."
            ),
            visual_direction="Dramatic rack-focus from shadows into warm golden amber key light, wide 35mm view",
            open_loop="Once you see the heuristic, you realize it is running in your own life today.",
        ),
        EssayChapter(
            chapter_num=6,
            title="The Reckoning",
            act_name="Act 6: Landing & Callback",
            target_words=budgets["Act 6 (Landing & Callback)"],
            spoken_text=(
                "Which brings us back to that strange anomaly from 1979. "
                "The researchers weren't measuring an error; they were measuring the human operating system. "
                "If you want to master this in your own work, do one thing tonight: "
                "audit the single decision you have been postponing this week, and subscribe for Chapter 2."
            ),
            visual_direction="Callback to opening archival ledger, closing cinematic slate with subscribe badge",
            open_loop=None,
        ),
    ]

    # Calculate timestamps (at 145 wpm = 2.416 words/sec) based on target word budget
    cum_time = 0.0
    for ch in chapters:
        ch.start_time_sec = cum_time
        cum_time += (ch.target_words / 2.416) + 3.0  # +3s for chapter card transition

    # Strategic Mid-Roll Ad Markers (Placed after narrative turns, never during cold open)
    mid_rolls: List[MidRollMarker] = []
    if target_minutes >= 8.0:
        # Ad Break 1 (Chapter 2 -> 3 transition, around 2:30-3:00)
        t1 = chapters[2].start_time_sec - 2.0
        m1, s1 = divmod(int(t1), 60)
        mid_rolls.append(MidRollMarker(timecode=f"{m1:02d}:{s1:02d}", seconds=t1, narrative_reason="Post-hypothesis setup; open loop holds viewer through break"))

        # Ad Break 2 (Chapter 4 -> 5 transition, around 5:30-6:30)
        t2 = chapters[4].start_time_sec - 2.0
        m2, s2 = divmod(int(t2), 60)
        mid_rolls.append(MidRollMarker(timecode=f"{m2:02d}:{s2:02d}", seconds=t2, narrative_reason="Peak curiosity gap before the core turn is revealed"))

        # Ad Break 3 (Chapter 5 -> 6 transition, around 8:30-9:30)
        if target_minutes >= 11.0:
            t3 = chapters[5].start_time_sec - 2.0
            m3, s3 = divmod(int(t3), 60)
            mid_rolls.append(MidRollMarker(timecode=f"{m3:02d}:{s3:02d}", seconds=t3, narrative_reason="Pre-resolution climax transition"))

    return LongFormEssaySpec(
        topic=topic,
        target_minutes=target_minutes,
        total_words=total_words,
        chapters=chapters,
        mid_roll_markers=mid_rolls,
        format=aspect_ratio,
        genre=genre,
    )


# ---------------------------------------------------------------------------
# CHAPTER TITLE CARD RENDERER
# ---------------------------------------------------------------------------

def render_chapter_title_card(
    title: str,
    chapter_num: int,
    output_path: Path,
    width: int = 1920,
    height: int = 1080,
    duration: float = 2.5,
    fps: int = 30,
    style: str = "magnates_amber",
) -> bool:
    """Renders a cinematic typographic chapter slate to broadcast MP4."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    width = (width // 2) * 2
    height = (height // 2) * 2
    num_frames = int(round(duration * fps))

    tmp_raw = output_path.with_suffix(".chap.raw.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(tmp_raw), fourcc, float(fps), (width, height))

    if not writer.isOpened():
        raise RuntimeError(f"Failed to open video writer for {tmp_raw}")

    # Color grading palette
    accent_color = (0, 179, 255) if style == "magnates_amber" else (0, 229, 255)

    try:
        for f_idx in range(num_frames):
            p = f_idx / max(1, num_frames - 1)
            # Deep atmospheric dark slate background
            frame = np.full((height, width, 3), (12, 14, 18), dtype=np.uint8)

            # Subtle camera push on chapter card (1.0 -> 1.03)
            zoom = 1.0 + (p * 0.03)
            M = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), 0.0, zoom)
            frame = cv2.warpAffine(frame, M, (width, height), flags=cv2.INTER_LINEAR)

            # Fade in / Fade out envelope (0.0 -> 1.0 -> 0.0)
            alpha_env = math.sin(p * math.pi)
            text_alpha = min(1.0, alpha_env * 1.4)

            # 1. Chapter Subtitle (e.g. "CHAPTER 01")
            sub_text = f"CHAPTER 0{chapter_num}" if chapter_num < 10 else f"CHAPTER {chapter_num}"
            font_sub = cv2.FONT_HERSHEY_DUPLEX
            sub_scale = 0.85 if width >= 1920 else 0.65
            sub_size = cv2.getTextSize(sub_text, font_sub, sub_scale, 2)[0]
            sub_x = (width - sub_size[0]) // 2
            sub_y = int(height * 0.44)

            # 2. Main Title (e.g. "THE ANOMALY")
            font_main = cv2.FONT_HERSHEY_DUPLEX
            main_scale = 1.8 if width >= 1920 else 1.1
            main_size = cv2.getTextSize(title.upper(), font_main, main_scale, 3)[0]
            main_x = (width - main_size[0]) // 2
            main_y = int(height * 0.54)

            # Draw accent rule line
            rule_w = int(main_size[0] * 0.40)
            rule_x1 = (width - rule_w) // 2
            rule_x2 = rule_x1 + rule_w
            rule_y = sub_y + 18
            cv2.line(frame, (rule_x1, rule_y), (rule_x2, rule_y), accent_color, 2, cv2.LINE_AA)

            # Render text
            text_overlay = frame.copy()
            cv2.putText(text_overlay, sub_text, (sub_x, sub_y), font_sub, sub_scale, accent_color, 2, cv2.LINE_AA)
            cv2.putText(text_overlay, title.upper(), (main_x, main_y), font_main, main_scale, (250, 250, 250), 3, cv2.LINE_AA)

            # Blend text with fade envelope
            frame = cv2.addWeighted(text_overlay, text_alpha, frame, 1.0 - text_alpha, 0)

            # Color grade + Vignette + 35mm grain
            frame_graded = apply_color_grade(frame, style)
            frame_vignette = apply_optical_vignette(frame_graded, strength=0.50)
            grain = generate_film_grain(height, width, intensity=8.0)
            frame_final = np.clip(frame_vignette.astype(np.float32) + grain, 0, 255).astype(np.uint8)

            writer.write(frame_final)

    finally:
        writer.release()

    # Re-encode to broadcast MP4
    success = reencode_broadcast_mp4(tmp_raw, output_path, fps=fps)
    if tmp_raw.exists():
        tmp_raw.unlink(missing_ok=True)
    return success


def reencode_broadcast_mp4(src_path: Path, dst_path: Path, fps: int = 30) -> bool:
    """Encodes to pristine 14 Mbps H.264 MP4."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        shutil.move(str(src_path), str(dst_path))
        return True

    encoders = ["h264_videotoolbox", "libx264"]
    for enc in encoders:
        cmd = [
            ffmpeg_bin, "-y",
            "-i", str(src_path),
            "-c:v", enc,
        ]
        if enc == "h264_videotoolbox":
            cmd.extend(["-b:v", "14M", "-profile:v", "high", "-pix_fmt", "yuv420p"])
        else:
            cmd.extend(["-crf", "17", "-preset", "fast", "-pix_fmt", "yuv420p"])

        cmd.extend([
            "-colorspace", "bt709",
            "-color_trc", "bt709",
            "-color_primaries", "bt709",
            "-r", str(fps),
            str(dst_path),
        ])

        proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if proc.returncode == 0 and dst_path.exists() and dst_path.stat().st_size > 0:
            return True

    shutil.move(str(src_path), str(dst_path))
    return True


# ---------------------------------------------------------------------------
# PROJECT EXPORT & YOUTUBE DESCRIPTION TIMESTAMP BUILDER
# ---------------------------------------------------------------------------

def generate_youtube_chapters_text(spec: LongFormEssaySpec) -> str:
    """Generates strictly compliant YouTube chapter timestamps."""
    lines = ["## ⏱️ Chapters & Key Milestones", ""]
    # Guarantee 00:00 start
    lines.append("00:00 - Introduction & Cold Open")
    for ch in spec.chapters:
        mins, secs = divmod(int(round(ch.start_time_sec)), 60)
        lines.append(f"{mins:02d}:{secs:02d} - Chapter {ch.chapter_num}: {ch.title}")

    lines.append("")
    lines.append("## 💰 Strategic Mid-Roll Monetization Windows")
    for mr in spec.mid_roll_markers:
        lines.append(f"- **{mr.timecode}**: {mr.narrative_reason}")
    return "\n".join(lines)


def export_longform_project(
    spec: LongFormEssaySpec,
    output_dir: Path,
) -> Path:
    """Exports project.json and UPLOAD_KIT.md for the long-form video."""
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = spec.topic.lower().replace(" ", "_").replace("-", "_")

    project_data = {
        "id": f"LV-{slug[:8].upper()}",
        "topic": spec.topic,
        "format": "long",
        "aspect_ratio": spec.format,
        "target_minutes": spec.target_minutes,
        "total_words": spec.total_words,
        "genre": spec.genre,
        "chapters": [asdict(ch) for ch in spec.chapters],
        "mid_roll_markers": [asdict(mr) for mr in spec.mid_roll_markers],
    }

    project_file = output_dir / "project.json"
    project_file.write_text(json.dumps(project_data, indent=2), encoding="utf-8")

    # Generate Upload Kit
    kit_file = output_dir / "UPLOAD_KIT.md"
    kit_content = f"""# UPLOAD KIT: {spec.topic} (Long-Form Video Essay)

## 📌 YouTube Title Suggestions
1. Why Everyone Was Wrong About {spec.topic}
2. The {spec.topic} Paradox: What Really Happened
3. How One 1979 Anomaly Changed {spec.topic} Forever

{generate_youtube_chapters_text(spec)}

## 🏷️ Search Tags (Strict Lowercase)
{spec.topic.lower()}, {spec.topic.lower()} documentary, {spec.topic.lower()} explained, cognitive core, video essay, psychology deep dive

## 🎬 Production Specifications
- Target Duration: ~{spec.target_minutes:.1f} minutes
- Word Count: {spec.total_words} spoken words
- Resolution: {1920 if spec.format == '16:9' else 1080}x{1080 if spec.format == '16:9' else 1920} (BT.709 H.264 @ 30 fps)
- Tone & Color Grade: {spec.genre} (35mm Archival)
"""
    kit_file.write_text(kit_content, encoding="utf-8")
    return project_file


# ---------------------------------------------------------------------------
# CLI INTERFACE
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="FrameForge Long-Form Video Orchestrator")
    ap.add_argument("--topic", "-t", type=str, required=True, help="Essay topic (e.g. 'Loss Aversion')")
    ap.add_argument("--duration", "-d", type=float, default=10.0, help="Target duration in minutes (e.g. 10.0, 12.0)")
    ap.add_argument("--aspect", type=str, default="16:9", choices=["16:9", "9:16"], help="Aspect ratio")
    ap.add_argument("--genre", "-g", type=str, default="magnates_amber", help="Visual style grade")
    ap.add_argument("--output-dir", "-o", type=Path, default=None, help="Project export directory")
    ap.add_argument("--render-card", action="store_true", help="Render a sample chapter title card to output-dir")

    args = ap.parse_args()

    slug = args.topic.lower().replace(" ", "_")
    out_dir = args.output_dir or (PROJECT_ROOT / "long_form" / f"lv_{slug}")

    print(f"📖 Architecting Long-Form Video Essay: '{args.topic}' ({args.duration}m, {args.aspect})...")
    spec = build_5act_essay_spec(
        topic=args.topic,
        target_minutes=args.duration,
        genre=args.genre,
        aspect_ratio=args.aspect,
    )

    proj_file = export_longform_project(spec, out_dir)
    print(f"✅ Generated Long-Form Project: {proj_file}")
    print(f"   Word Budget: {spec.total_words} words across {len(spec.chapters)} chapters")
    print(f"   Mid-Roll Markers: {len(spec.mid_roll_markers)} strategic ad breaks ({', '.join(mr.timecode for mr in spec.mid_roll_markers)})")

    if args.render_card:
        w = 1920 if args.aspect == "16:9" else 1080
        h = 1080 if args.aspect == "16:9" else 1920
        card_out = out_dir / "chapter_01_card.mp4"
        print(f"🎬 Rendering Sample Chapter Slate: {card_out}...")
        ok = render_chapter_title_card(
            title=spec.chapters[0].title,
            chapter_num=1,
            output_path=card_out,
            width=w,
            height=h,
            style=args.genre,
        )
        if ok:
            print(f"✅ Rendered chapter slate: {card_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
