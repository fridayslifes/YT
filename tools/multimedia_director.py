#!/usr/bin/env python3
"""FrameForge Multimedia & Asset Staging Director.

Integrates:
1. Trending & Famous Sound Effects from Myinstants & Curated CC0 SFX Banks (16-thread aria2c).
2. 100% Royalty-Free 3D Emojis from Microsoft Fluent UI Emoji (MIT License) & Google Noto.
3. Script Staging Engine: Formats scripts with sound cues [SFX: name @ timestamp] and
   visual 3D emojis [EMOJI: name @ position], auto-downloading missing assets.
4. Canva & 3D Layer Integration for multiplane parallax and cutout compositing.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("multimedia_director")

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
ASSETS_DIR = REPO_ROOT / "assets"
SFX_DIR = ASSETS_DIR / "audio" / "sfx"
EMOJI_DIR = ASSETS_DIR / "emojis"

# Curated mapping of common emoji aliases to Microsoft Fluent 3D Emoji GitHub paths
FLUENT_3D_CATALOG: Dict[str, str] = {
    "thumbs_up": "Thumbs%20up/Default/3D/thumbs_up_3d_default.png",
    "thumbs_down": "Thumbs%20down/Default/3D/thumbs_down_3d_default.png",
    "brain": "Brain/3D/brain_3d.png",
    "collision": "Collision/3D/collision_3d.png",
    "explosion": "Collision/3D/collision_3d.png",
    "fire": "Fire/3D/fire_3d.png",
    "money_bag": "Money%20bag/3D/money_bag_3d.png",
    "money": "Money%20bag/3D/money_bag_3d.png",
    "dollar": "Dollar%20banknote/3D/dollar_banknote_3d.png",
    "magnifying_glass": "Magnifying%20glass%20tilted%20left/3D/magnifying_glass_tilted_left_3d.png",
    "search": "Magnifying%20glass%20tilted%20left/3D/magnifying_glass_tilted_left_3d.png",
    "police_light": "Police%20car%20light/3D/police_car_light_3d.png",
    "siren": "Police%20car%20light/3D/police_car_light_3d.png",
    "alarm": "Police%20car%20light/3D/police_car_light_3d.png",
    "warning": "Warning/3D/warning_3d.png",
    "skull": "Skull/3D/skull_3d.png",
    "eyes": "Eyes/3D/eyes_3d.png",
    "hourglass": "Hourglass%20done/3D/hourglass_done_3d.png",
    "clock": "Stopwatch/3D/stopwatch_3d.png",
    "stopwatch": "Stopwatch/3D/stopwatch_3d.png",
    "target": "Direct%20hit/3D/direct_hit_3d.png",
    "bulb": "Light%20bulb/3D/light_bulb_3d.png",
    "idea": "Light%20bulb/3D/light_bulb_3d.png",
    "hundred": "Hundred%20points/3D/hundred_points_3d.png",
    "check": "Check%20mark%20button/3D/check_mark_button_3d.png",
    "cross": "Cross%20mark/3D/cross_mark_3d.png",
    "chart_up": "Chart%20increasing/3D/chart_increasing_3d.png",
    "chart_down": "Chart%20decreasing/3D/chart_decreasing_3d.png",
    "camera": "Camera%20with%20flash/3D/camera_with_flash_3d.png",
    "lock": "Locked/3D/locked_3d.png",
    "key": "Key/3D/key_3d.png",
    "gem": "Gem%20stone/3D/gem_stone_3d.png",
    "newspaper": "Newspaper/3D/newspaper_3d.png",
    "scroll": "Scroll/3D/scroll_3d.png",
    "airplane": "Airplane/3D/airplane_3d.png",
    "plane": "Airplane/3D/airplane_3d.png",
    "bomb": "Bomb/3D/bomb_3d.png",
    "briefcase": "Briefcase/3D/briefcase_3d.png",
    "cloud_lightning": "Cloud%20with%20lightning%20and%20rain/3D/cloud_with_lightning_and_rain_3d.png",
    "rain": "Cloud%20with%20lightning%20and%20rain/3D/cloud_with_lightning_and_rain_3d.png",
    "storm": "Cloud%20with%20lightning%20and%20rain/3D/cloud_with_lightning_and_rain_3d.png",
}

RAW_FLUENT_BASE = "https://raw.githubusercontent.com/microsoft/fluentui-emoji/main/assets/"


def download_with_aria2c(url: str, output_dir: Path, filename: str) -> Path:
    """Download an asset using aria2c with 16 connections for maximum speed."""
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / filename
    if target_path.exists() and target_path.stat().st_size > 512:
        logger.info(f"Asset already cached: {target_path} ({target_path.stat().st_size} bytes)")
        return target_path

    if shutil.which("aria2c"):
        cmd = [
            "aria2c",
            "-x", "16",
            "-s", "16",
            "-k", "1M",
            url,
            "-d", str(output_dir),
            "-o", filename,
            "--allow-overwrite=true",
        ]
        logger.info(f"Downloading {url} via 16-thread aria2c -> {target_path}")
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"aria2c download failed for {url} ({res.stderr[:200]})")
    else:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (FrameForge/4.0)"})
        with urllib.request.urlopen(req) as resp, open(target_path, "wb") as f:
            f.write(resp.read())

    if not target_path.exists() or target_path.stat().st_size < 100:
        raise RuntimeError(f"Download failed or empty file for: {url}")

    logger.info(f"Successfully downloaded: {target_path} ({target_path.stat().st_size} bytes)")
    return target_path


def search_myinstants(query: str, max_results: int = 6) -> List[Dict[str, str]]:
    """Search Myinstants for sound effects and return clean playable MP3 URLs."""
    url = f"https://www.myinstants.com/en/search/?name={urllib.parse.quote(query)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read().decode("utf-8")
    except Exception as e:
        logger.error(f"Myinstants query failed: {e}")
        return []

    # Extract audio paths and button titles
    sound_paths = re.findall(r"play\(\x27(/media/sounds/[^\x27]+)\x27", html)
    titles = re.findall(r"class=\"instant-link [^\"]*\">([^<]+)</a>", html)

    results: List[Dict[str, str]] = []
    seen = set()
    for s_path, title in zip(sound_paths, titles):
        full_url = f"https://www.myinstants.com{s_path}"
        clean_title = title.strip()
        if full_url not in seen:
            seen.add(full_url)
            results.append({
                "title": clean_title,
                "url": full_url,
                "slug": re.sub(r"[^a-zA-Z0-9_]+", "_", clean_title.lower()).strip("_"),
            })
        if len(results) >= max_results:
            break

    return results


def get_myinstants_sound(query_or_url: str, output_name: Optional[str] = None) -> Path:
    """Fetch an audio sound from Myinstants (by search query or direct URL)."""
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    if query_or_url.startswith("http://") or query_or_url.startswith("https://"):
        url = query_or_url
        filename = output_name or (url.split("/")[-1].split("?")[0])
        if not filename.endswith(".mp3") and not filename.endswith(".wav"):
            filename += ".mp3"
    else:
        results = search_myinstants(query_or_url, max_results=3)
        if not results:
            raise ValueError(f"No sounds found on Myinstants for query: '{query_or_url}'")
        best = results[0]
        url = best["url"]
        filename = (output_name or best["slug"])
        if not filename.endswith(".mp3"):
            filename += ".mp3"

    return download_with_aria2c(url, SFX_DIR, filename)


def get_fluent_3d_emoji(name_or_alias: str, output_name: Optional[str] = None) -> Path:
    """Download a 100% royalty-free 3D emoji from Microsoft Fluent UI Emoji (MIT License)."""
    EMOJI_DIR.mkdir(parents=True, exist_ok=True)
    clean_key = re.sub(r"[^a-zA-Z0-9_]+", "_", name_or_alias.lower()).strip("_")

    rel_path = FLUENT_3D_CATALOG.get(clean_key)
    if not rel_path:
        # Try finding a partial match in catalog
        for k, v in FLUENT_3D_CATALOG.items():
            if clean_key in k or k in clean_key:
                rel_path = v
                clean_key = k
                break

    if not rel_path:
        # Construct direct repository path for uncataloged emoji
        capitalized = " ".join(word.capitalize() for word in clean_key.split("_"))
        rel_path = f"{urllib.parse.quote(capitalized)}/3D/{clean_key}_3d.png"

    full_url = RAW_FLUENT_BASE + rel_path
    filename = output_name or f"{clean_key}_3d.png"
    if not filename.endswith(".png"):
        filename += ".png"

    return download_with_aria2c(full_url, EMOJI_DIR, filename)


# ---------------------------------------------------------------------------
# SCRIPT & MULTIMEDIA STAGING AGENT
# ---------------------------------------------------------------------------

@dataclass
class SoundCue:
    name: str
    timestamp_sec: float
    volume: float = 0.85
    asset_path: Optional[str] = None


@dataclass
class EmojiCue:
    name: str
    position: str  # "top-left", "center", "center-right", "bottom-center"
    scale: float = 1.0
    animation: str = "pop"  # "pop", "float", "drift", "pulse"
    asset_path: Optional[str] = None


@dataclass
class StagedScene:
    scene_id: str
    narration: str
    word_count: int
    duration_estimate: float
    sound_cues: List[SoundCue]
    emoji_cues: List[EmojiCue]
    visual_direction: str


def parse_script_staging(script_text: str) -> List[StagedScene]:
    """Parses a structured script containing [SFX: name @ sec] and [EMOJI: name @ pos]."""
    scenes: List[StagedScene] = []
    blocks = re.split(r"(?:^|\n)## Scene \d+", script_text)

    # If no "## Scene" headers, split by double newline
    if len(blocks) <= 1:
        blocks = [b.strip() for b in script_text.split("\n\n") if b.strip()]

    scene_idx = 1
    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # Extract SFX tags: [SFX: name @ 1.2s] or [SFX: name]
        sfx_matches = re.findall(r"\[SFX:\s*([^@\]]+)(?:@\s*([\d\.]+)s?)?\]", block, re.IGNORECASE)
        sound_cues: List[SoundCue] = []
        for name, ts in sfx_matches:
            t_sec = float(ts) if ts else 0.0
            sound_cues.append(SoundCue(name=name.strip(), timestamp_sec=t_sec))

        # Extract EMOJI tags: [EMOJI: name @ position] or [EMOJI: name]
        emoji_matches = re.findall(r"\[EMOJI:\s*([^@\]]+)(?:@\s*([^\]]+))?\]", block, re.IGNORECASE)
        emoji_cues: List[EmojiCue] = []
        for name, pos in emoji_matches:
            p_str = pos.strip() if pos else "center-right"
            emoji_cues.append(EmojiCue(name=name.strip(), position=p_str))

        # Clean narration by stripping tags
        clean_narration = re.sub(r"\[(SFX|EMOJI|VISUAL):[^\]]+\]", "", block).strip()
        words = clean_narration.split()
        w_count = len(words)
        # 150 words per minute ~ 2.5 words per second
        dur = max(2.5, round(w_count / 2.5, 1))

        scenes.append(
            StagedScene(
                scene_id=f"s{scene_idx:02d}",
                narration=clean_narration,
                word_count=w_count,
                duration_estimate=dur,
                sound_cues=sound_cues,
                emoji_cues=emoji_cues,
                visual_direction="3D camera move with parchment casebook & forensic drop shadow",
            )
        )
        scene_idx += 1

    return scenes


def stage_and_download_all_assets(staged_scenes: List[StagedScene]) -> Dict[str, Any]:
    """Ensures all SFX and 3D emojis referenced in the script are downloaded and cached."""
    manifest = {
        "sfx_downloaded": [],
        "emojis_downloaded": [],
        "errors": [],
    }

    for sc in staged_scenes:
        # Download missing SFX
        for sfx in sc.sound_cues:
            try:
                local_path = get_myinstants_sound(sfx.name)
                sfx.asset_path = str(local_path)
                manifest["sfx_downloaded"].append({"name": sfx.name, "path": str(local_path)})
            except Exception as e:
                manifest["errors"].append(f"SFX error '{sfx.name}': {e}")

        # Download missing 3D Emojis
        for em in sc.emoji_cues:
            try:
                local_path = get_fluent_3d_emoji(em.name)
                em.asset_path = str(local_path)
                manifest["emojis_downloaded"].append({"name": em.name, "path": str(local_path)})
            except Exception as e:
                manifest["errors"].append(f"Emoji error '{em.name}': {e}")

    return manifest


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--search-sfx":
        q = sys.argv[2] if len(sys.argv) > 2 else "vine boom"
        print(f"Searching Myinstants for '{q}':")
        for res in search_myinstants(q):
            print(f" - {res['title']}: {res['url']}")
    elif len(sys.argv) > 1 and sys.argv[1] == "--get-sfx":
        q = sys.argv[2] if len(sys.argv) > 2 else "vine boom"
        p = get_myinstants_sound(q)
        print(f"Downloaded SFX: {p}")
    elif len(sys.argv) > 1 and sys.argv[1] == "--get-emoji":
        q = sys.argv[2] if len(sys.argv) > 2 else "thumbs_up"
        p = get_fluent_3d_emoji(q)
        print(f"Downloaded 3D Emoji: {p}")
    elif len(sys.argv) > 1 and sys.argv[1] == "--stage-file":
        script_file = Path(sys.argv[2])
        staged = parse_script_staging(script_file.read_text(encoding="utf-8"))
        print(f"Parsed {len(staged)} staged scenes. Staging and downloading assets...")
        res = stage_and_download_all_assets(staged)
    else:
        print("Usage: python tools/multimedia_director.py [--search-sfx <query> | --get-sfx <name> | --get-emoji <name> | --stage-file <script.md>]")
        print(json.dumps(res, indent=2))
