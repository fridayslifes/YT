"""Universal Humanizer & Sound Immersion Director (FrameForge v4.2).

Transforms any investigative case, heist, historical mystery, or deep-dive topic
into sensory, human, novelistic storytelling with context-aware diegetic soundscapes,
trending punctuation, and authentic physical open-storybook visual staging across
both Short and Long formats.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# FrameForge Workspace Imports
REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
ASSETS_DIR = REPO_ROOT / "assets"
SFX_DIR = ASSETS_DIR / "audio" / "sfx"
EMOJI_DIR = ASSETS_DIR / "emojis"
BGM_FILE = ASSETS_DIR / "audio" / "bgm" / "vertigo_tension.mp3"
KOKORO_MODEL = TOOLS_DIR / "kokoro_models" / "kokoro-v1.0.onnx"
KOKORO_VOICES = TOOLS_DIR / "kokoro_models" / "voices-v1.0.bin"
OUTPUT_DIR = REPO_ROOT / "output"

FONT_PATH = str(TOOLS_DIR / "fonts" / "BeVietnamPro-Regular.ttf")
FONT_BOLD = str(TOOLS_DIR / "fonts" / "BeVietnamPro-Bold.ttf")

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.multimedia_director import (  # noqa: E402
    get_fluent_3d_emoji,
    get_myinstants_sound,
    search_myinstants,
)
from tools.storybook_engine import (  # noqa: E402
    composite_plate_with_shadow,
    draw_brass_pushpin,
    draw_gold_embossed_seal,
    draw_highlighter_bar,
    draw_rubber_stamp,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("humanizer_director")

# ---------------------------------------------------------------------- #
# 1. Novelist Language Guard & AI Buzzword Blacklist
# ---------------------------------------------------------------------- #
BANNED_AI_WORDS = {
    "delve", "delving", "tapestry", "testament", "landscape", "realm",
    "game-changer", "unraveling", "fascinating", "imagine a world",
    "little did they know", "in a shocking twist", "testament to",
    "it is important to remember", "dive deep", "beacon of", "pivotal moment",
    "ever-evolving", "rich history", "in conclusion", "furthermore"
}


def validate_human_prose(text: str) -> List[str]:
    """Lints narrative text for banned corporate AI buzzwords and robotic cadences."""
    violations = []
    low = text.lower()
    for word in BANNED_AI_WORDS:
        pattern = r"\b" + re.escape(word) + r"\b"
        if re.search(pattern, low):
            violations.append(f"Contains banned AI buzzword: '{word}'")
    return violations


# ---------------------------------------------------------------------- #
# 2. Context-Aware Diegetic Sound Definitions
# ---------------------------------------------------------------------- #
def resolve_diegetic_sound(sound_name: str, search_query: str) -> Optional[Path]:
    """Ensures the diegetic sound file is cached locally in assets/audio/sfx/."""
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    local_path = SFX_DIR / f"{sound_name}.mp3"
    local_wav = SFX_DIR / f"{sound_name}.wav"
    if local_path.exists() and local_path.stat().st_size > 1024:
        return local_path
    if local_wav.exists() and local_wav.stat().st_size > 1024:
        return local_wav

    logger.info(f"Resolving diegetic sound '{sound_name}' (query: '{search_query}')...")
    results = search_myinstants(search_query, max_results=3)
    if results:
        best_url = results[0]["url"]
        try:
            return get_myinstants_sound(best_url, f"{sound_name}.mp3")
        except Exception as e:
            logger.warning(f"Failed to download sound '{sound_name}': {e}")

    for fallback in ["whoosh.wav", "boom.wav", "shutter.wav", "chime.wav"]:
        cand = SFX_DIR / fallback
        if cand.exists():
            return cand
    return None


# ---------------------------------------------------------------------- #
# 3. Novelistic Script Architecture: The 1971 D.B. Cooper Master (3-Act)
# ---------------------------------------------------------------------- #
@dataclass
class HumanScene:
    scene_id: str
    act: str
    text: str
    sound_cues: List[Dict[str, Any]]
    left_plate_text: str
    center_focus: str
    right_prop: str
    highlighter_phrase: str
    left_emoji: str
    right_emoji: str
    stamp_text: Optional[str] = None


DB_COOPER_LONGFORM_SCRIPT: List[HumanScene] = [
    # --- ACT 1: THE SETUP & SENSORY HOOK (0:00 - 0:45) ---
    HumanScene(
        scene_id="s01",
        act="Act 1: The Setup",
        text="On a rainy Wednesday afternoon before Thanksgiving, a man in a dark business suit walked up to the Northwest Orient counter in Portland and bought a one-way ticket for twenty dollars.",
        sound_cues=[{"name": "seatbelt_chime", "search": "airplane seatbelt chime", "offset": 0.2, "vol": 0.22}],
        left_plate_text="PORTLAND INTL AIRPORT - NOV 24 1971",
        center_focus="Flight 305 Boarding Gate",
        right_prop="NW Orient Ticket $20",
        highlighter_phrase="twenty dollars",
        left_emoji="airplane",
        right_emoji="dollar",
        stamp_text="CLASSIFIED",
    ),
    HumanScene(
        scene_id="s02",
        act="Act 1: Seat 18C",
        text="He gave the name Dan Cooper. He boarded Boeing 727 Flight 305, took Seat 18C, lit a cigarette, and ordered a bourbon and soda with crisp ice.",
        sound_cues=[
            {"name": "match_strike", "search": "match lighting strike flame", "offset": 0.4, "vol": 0.22},
            {"name": "ice_in_bourbon", "search": "ice clinking in glass cup", "offset": 2.2, "vol": 0.20},
        ],
        left_plate_text="BOEING 727 CABIN - SEAT 18C",
        center_focus="Gentleman in Black Sunglasses",
        right_prop="Bourbon Cup & Raleigh Pack",
        highlighter_phrase="Seat 18C",
        left_emoji="fire",
        right_emoji="eyes",
        stamp_text="EVIDENCE",
    ),
    HumanScene(
        scene_id="s03",
        act="Act 1: The Ransom Note",
        text="Minutes after takeoff, he handed flight attendant Florence Schaffner a folded paper slip. She slipped it into her purse unread until Cooper leaned across: *Miss, you better look at that note. I have a bomb.*",
        sound_cues=[
            {"name": "flight_attendant_ding", "search": "flight attendant call button ding", "offset": 0.3, "vol": 0.24},
            {"name": "sub_bass_drop", "search": "cinema sub bass boom drop impact", "offset": 2.4, "vol": 0.28},
        ],
        left_plate_text="HANDWRITTEN RANSOM SLIP",
        center_focus="Briefcase with Red Cylinders",
        right_prop="Florence Schaffner Statement",
        highlighter_phrase="I have a bomb",
        left_emoji="bomb",
        right_emoji="warning",
        stamp_text="EVIDENCE",
    ),
    # --- ACT 2: THE DEMAND & THE AIRPORT TENSION (0:45 - 1:35) ---
    HumanScene(
        scene_id="s04",
        act="Act 2: The Demand",
        text="Inside his black briefcase lay eight red cylinders wired to a cylindrical battery. His demand was precise: *two* *hundred* *thousand* dollars in negotiable twenty-dollar bills, and four parachutes.",
        sound_cues=[{"name": "tension_clock", "search": "clock ticking dramatic suspense", "offset": 0.5, "vol": 0.20}],
        left_plate_text="SERIALIZED RANSOM LEDGER",
        center_focus="10,000 Unmarked $20 Bills",
        right_prop="Four Parachute Packs",
        highlighter_phrase="two hundred thousand dollars",
        left_emoji="briefcase",
        right_emoji="money",
        stamp_text="NORJAK",
    ),
    HumanScene(
        scene_id="s05",
        act="Act 2: The Exchange",
        text="At Seattle-Tacoma Airport, thirty-six innocent passengers were released in exchange for the canvas knapsack of cash. Cooper allowed the plane to refuel, ordering the cockpit crew to fly toward Reno at minimum speed.",
        sound_cues=[{"name": "cockpit_radio", "search": "air traffic control radio squawk", "offset": 0.8, "vol": 0.20}],
        left_plate_text="SEATTLE-TACOMA TARMAC",
        center_focus="Refueling Tanker 11:45 PM",
        right_prop="Canvas Bank Knapsack",
        highlighter_phrase="minimum speed",
        left_emoji="search",
        right_emoji="clock",
        stamp_text="CONFIRMED",
    ),
    HumanScene(
        scene_id="s06",
        act="Act 2: Flight Path",
        text="He demanded the landing gear stay down, flaps locked at fifteen degrees, and cabin pressure completely unpressurized.",
        sound_cues=[{"name": "pressure_drop", "search": "compressed air release hiss", "offset": 0.4, "vol": 0.22}],
        left_plate_text="COCKPIT FLIGHT INSTRUMENTS",
        center_focus="Altimeter 10,000 Feet",
        right_prop="Throttle Control Quadrant",
        highlighter_phrase="unpressurized",
        left_emoji="airplane",
        right_emoji="warning",
        stamp_text="NORJAK",
    ),
    # --- ACT 3: THE FREEZING JUMP & THE UNEXPLAINED PARADOX (1:35 - 2:40) ---
    HumanScene(
        scene_id="s07",
        act="Act 3: The Freezing Sky",
        text="At eight o'clock, somewhere over southwestern Washington in a freezing winter rainstorm, Cooper ordered the remaining crew into the cockpit and lowered the Boeing 727's rear ventral stairs.",
        sound_cues=[{"name": "wind_howl", "search": "freezing howling wind blizzard storm", "offset": 0.6, "vol": 0.24}],
        left_plate_text="BOEING 727 AFT STAIRWAY",
        center_focus="Ventral Stairs Extending Down",
        right_prop="Rain Streaked Tail Fin",
        highlighter_phrase="lowered the rear stairs",
        left_emoji="cloud_lightning",
        right_emoji="warning",
        stamp_text="URGENT",
    ),
    HumanScene(
        scene_id="s08",
        act="Act 3: The Jump",
        text="At 8:13 PM, pilots felt a sudden upward bump of the tail section as cabin air pressure surged. Cooper had jumped into the pitch-black void at ten thousand feet, in minus fifty-seven degree wind chill.",
        sound_cues=[
            {"name": "thunder_crack", "search": "distant thunder strike cinematic", "offset": 0.2, "vol": 0.26},
            {"name": "dramatic_whoosh", "search": "cinematic deep whoosh transition", "offset": 1.8, "vol": 0.24},
        ],
        left_plate_text="COCKPIT PRESSURE SENSOR LOG",
        center_focus="Oscilloscope Bump at 8:13 PM",
        right_prop="Lewis River Wilderness Map",
        highlighter_phrase="jumped into the pitch-black void",
        left_emoji="explosion",
        right_emoji="cloud_lightning",
        stamp_text="MISSING",
    ),
    HumanScene(
        scene_id="s09",
        act="Act 3: The Vanishing",
        text="He had no helmet, no night-vision, and wore loafers and a light raincoat. Two Air Force fighter jets trailing the airliner saw nothing drop into the darkness below.",
        sound_cues=[{"name": "wind_howl", "search": "freezing howling wind blizzard storm", "offset": 0.4, "vol": 0.20}],
        left_plate_text="F-106 DELTA DART CHASE LOG",
        center_focus="Infrared Radar Blank Screen",
        right_prop="Loafer Shoes & Black Trenchcoat",
        highlighter_phrase="saw nothing drop",
        left_emoji="eyes",
        right_emoji="skull",
        stamp_text="UNSOLVED",
    ),
    HumanScene(
        scene_id="s10",
        act="Act 3: The Discovery",
        text="For forty-five years, the FBI tracked every serial number—not a single bill was ever spent. Then in 1980, an eight-year-old boy digging at Tina Bar uncovered fifty-eight hundred dollars in rotting twenties with rubber bands intact.",
        sound_cues=[{"name": "vinyl_needle", "search": "vinyl record scratch needle stop", "offset": 0.5, "vol": 0.22}],
        left_plate_text="TINA BAR EXCAVATION SITE - 1980",
        center_focus="Brian Ingram $5,800 Discovery",
        right_prop="Decaying Rubber Band Stacks",
        highlighter_phrase="rotting twenties",
        left_emoji="dollar",
        right_emoji="search",
        stamp_text="CONFIRMED",
    ),
    HumanScene(
        scene_id="s11",
        act="Act 3: The Legend",
        text="No body, no parachute, and no trace of the remaining hundred and ninety-four thousand dollars has ever been found. Did he die in the freezing canopy, or walk into the night as a ghost? *Subscribe* for the next unsolved forensic case.",
        sound_cues=[{"name": "sub_bass_drop", "search": "cinema sub bass boom drop impact", "offset": 1.2, "vol": 0.26}],
        left_plate_text="FBI OFFICIAL CASE STATUS: SUSPENDED",
        center_focus="The Mystery of D.B. Cooper",
        right_prop="Empty Parachute Harness",
        highlighter_phrase="walk into the night as a ghost",
        left_emoji="skull",
        right_emoji="thumbs_up",
        stamp_text="UNSOLVED",
    ),
]


# ---------------------------------------------------------------------- #
# 4. Master Physical Open-Storybook Compositor
# ---------------------------------------------------------------------- #
def render_humanized_plate_16x9(scene: HumanScene, width: int = 1920, height: int = 1080) -> np.ndarray:
    """Renders a true physical open-storybook spread with printed novel text, clipped evidence photo, and 3D Fluent Emojis."""
    # 1. Base Desk Canvas (Rich dark mahogany wood with soft grain)
    canvas = np.full((height, width, 3), (22, 28, 42), dtype=np.uint8)
    wood_noise = np.random.normal(0, 3.5, (height, width, 1)).astype(np.float32)
    canvas = np.clip(canvas.astype(np.float32) + wood_noise, 0, 255).astype(np.uint8)

    # 2. Hardcover Leather Book Casing (Burgundy leather outer rim with gilded border)
    book_margin_x = int(width * 0.045)
    book_margin_y = int(height * 0.05)
    book_w = width - (2 * book_margin_x)
    book_h = height - (2 * book_margin_y)
    bx, by = book_margin_x, book_margin_y

    cv2.rectangle(canvas, (bx, by), (bx + book_w, by + book_h), (28, 32, 68), -1)
    cv2.rectangle(canvas, (bx + 8, by + 8), (bx + book_w - 8, by + book_h - 8), (55, 175, 212), 2, cv2.LINE_AA)

    # 3. Two Open Parchment Pages (Left & Right)
    page_inset_x = 22
    page_inset_y = 18
    total_pages_w = book_w - (2 * page_inset_x)
    total_pages_h = book_h - (2 * page_inset_y)
    px = bx + page_inset_x
    py = by + page_inset_y
    single_page_w = total_pages_w // 2

    # Aged parchment color (#F7F3E9 BGR)
    parchment_color = (233, 243, 247)
    pages_bg = np.full((total_pages_h, total_pages_w, 3), parchment_color, dtype=np.float32)

    # Center gutter fold shadow (3D book spine depth)
    y_idx, x_idx = np.ogrid[:total_pages_h, :total_pages_w]
    gutter_x = total_pages_w // 2
    gutter_dist = np.abs(x_idx - gutter_x)
    gutter_shadow = np.clip(1.0 - 0.42 * np.exp(- (gutter_dist ** 2) / (2.0 * (45 ** 2))), 0.58, 1.0)[..., None]
    pages_bg = pages_bg * gutter_shadow

    # Page edge shading
    edge_dist_l = np.clip(x_idx / 60.0, 0.82, 1.0)[..., None]
    edge_dist_r = np.clip((total_pages_w - x_idx) / 60.0, 0.82, 1.0)[..., None]
    pages_bg = pages_bg * edge_dist_l * edge_dist_r

    paper_noise = np.random.normal(0, 2.8, (total_pages_h, total_pages_w, 1)).astype(np.float32)
    pages_bg = np.clip(pages_bg + paper_noise, 0, 255).astype(np.uint8)

    # Center spine stitch marks
    for sy in range(30, total_pages_h - 30, 45):
        cv2.line(pages_bg, (gutter_x - 3, sy), (gutter_x + 3, sy + 15), (75, 85, 110), 1, cv2.LINE_AA)

    canvas[py:py + total_pages_h, px:px + total_pages_w] = pages_bg

    # 4. Render Novel Story Text on Left Page using Pillow
    img_pil = Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)

    font_header = ImageFont.truetype(FONT_BOLD, 22)
    font_dropcap = ImageFont.truetype(FONT_BOLD, 64)
    font_body = ImageFont.truetype(FONT_PATH, 28)

    left_content_x = px + 65
    left_content_y = py + 55
    left_max_w = single_page_w - 130

    # Header & Chapter Title
    header_str = f"THE NORJAK DOSSIER  •  {scene.act.upper()}"
    draw.text((left_content_x, left_content_y), header_str, font=font_header, fill=(95, 105, 120))
    draw.line([(left_content_x, left_content_y + 32), (px + single_page_w - 65, left_content_y + 32)], fill=(180, 190, 205), width=1)

    # Word Wrap Body Text
    clean_text = scene.text.replace("*", "")
    words = clean_text.split()
    lines = []
    cur_line = []
    for w in words:
        test_line = " ".join(cur_line + [w])
        bbox = draw.textbbox((0, 0), test_line, font=font_body)
        if bbox[2] - bbox[0] <= left_max_w:
            cur_line.append(w)
        else:
            lines.append(" ".join(cur_line))
            cur_line = [w]
    if cur_line:
        lines.append(" ".join(cur_line))

    # Draw Drop Cap for first line
    text_y = left_content_y + 65
    if lines:
        first_line = lines[0]
        drop_char = first_line[0]
        rest_first = first_line[1:]
        draw.text((left_content_x, text_y), drop_char, font=font_dropcap, fill=(120, 35, 45))
        drop_bbox = draw.textbbox((left_content_x, text_y), drop_char, font=font_dropcap)
        drop_w = drop_bbox[2] - drop_bbox[0] + 12
        draw.text((left_content_x + drop_w, text_y + 12), rest_first, font=font_body, fill=(35, 33, 30))
        text_y += 58

        for line in lines[1:]:
            draw.text((left_content_x, text_y), line, font=font_body, fill=(35, 33, 30))
            text_y += 44

    canvas = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

    # 5. Fluorescent Yellow Highlighter across target phrase
    if scene.highlighter_phrase:
        hl_y = min(text_y - 20, py + int(total_pages_h * 0.58))
        canvas = draw_highlighter_bar(canvas, left_content_x, hl_y, int(left_max_w * 0.85), height=30, color=(35, 235, 255), alpha=0.45)

    # 6. Clipped Small Archival Ticket/Card on Left Page
    small_card_w = int(single_page_w * 0.52)
    small_card_h = int(total_pages_h * 0.26)
    small_card = np.full((small_card_h, small_card_w, 3), (242, 246, 250), dtype=np.uint8)
    cv2.rectangle(small_card, (2, 2), (small_card_w - 2, small_card_h - 2), (170, 180, 195), 1)
    cv2.putText(small_card, "NORTHWEST ORIENT ARCHIVE", (14, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (45, 55, 70), 1, cv2.LINE_AA)
    cv2.putText(small_card, f"REF: {scene.scene_id.upper()} • NORJAK-71", (14, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (25, 35, 50), 2, cv2.LINE_AA)
    cv2.putText(small_card, scene.left_plate_text[:28], (14, 84), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (120, 40, 40), 1, cv2.LINE_AA)

    card_cx = px + int(single_page_w * 0.38)
    card_cy = py + total_pages_h - int(small_card_h * 0.70)
    canvas = composite_plate_with_shadow(canvas, small_card, card_cx, card_cy, angle_deg=-3.5)
    canvas = draw_brass_pushpin(canvas, card_cx - (small_card_w // 2) + 15, card_cy - (small_card_h // 2) + 12, radius=12)

    # 7. Right Page: Large Clipped Evidence Plate
    right_page_cx = px + single_page_w + (single_page_w // 2)
    right_card_w = int(single_page_w * 0.76)
    right_card_h = int(total_pages_h * 0.72)

    right_plate = np.full((right_card_h, right_card_w, 3), (240, 244, 248), dtype=np.uint8)
    cv2.rectangle(right_plate, (4, 4), (right_card_w - 4, right_card_h - 4), (160, 175, 190), 2)

    inner_photo_h = int(right_card_h * 0.74)
    inner_photo_w = right_card_w - 32
    photo_surface = np.full((inner_photo_h, inner_photo_w, 3), (35, 42, 52), dtype=np.uint8)

    # Flight path / radar grid
    for gx in range(0, inner_photo_w, 40):
        cv2.line(photo_surface, (gx, 0), (gx, inner_photo_h), (48, 58, 70), 1)
    for gy in range(0, inner_photo_h, 40):
        cv2.line(photo_surface, (0, gy), (inner_photo_w, gy), (48, 58, 70), 1)

    cv2.putText(photo_surface, scene.center_focus.upper(), (24, inner_photo_h // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (220, 235, 250), 2, cv2.LINE_AA)
    right_plate[16:16 + inner_photo_h, 16:16 + inner_photo_w] = photo_surface
    cv2.putText(right_plate, f"EXHIBIT: {scene.right_prop}", (20, inner_photo_h + 46), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (35, 40, 50), 2, cv2.LINE_AA)

    right_plate_cy = py + (total_pages_h // 2)
    canvas = composite_plate_with_shadow(canvas, right_plate, right_page_cx, right_plate_cy, angle_deg=2.2)
    canvas = draw_brass_pushpin(canvas, right_page_cx + (right_card_w // 2) - 20, right_plate_cy - (right_card_h // 2) + 14, radius=14)

    # Rubber Stamp
    if scene.stamp_text:
        canvas = draw_rubber_stamp(canvas, scene.stamp_text, right_page_cx + 80, right_plate_cy + (right_card_h // 3), angle_deg=-16.0, style="classic")

    # Gold Embossed Seal at lower right corner
    canvas = draw_gold_embossed_seal(canvas, bx + book_w - 70, by + book_h - 70, radius=38)

    # 8. Physical 3D Fluent Emojis with Cast Drop Shadow!
    def overlay_3d_emoji(target_bgr: np.ndarray, emoji_name: str, cx: int, cy: int, size: int = 120):
        if not emoji_name:
            return target_bgr
        emoji_path = EMOJI_DIR / f"{emoji_name}_3d.png"
        if not emoji_path.exists():
            return target_bgr
        em_rgba = cv2.imread(str(emoji_path), cv2.IMREAD_UNCHANGED)
        if em_rgba is None:
            return target_bgr
        em_resized = cv2.resize(em_rgba, (size, size), interpolation=cv2.INTER_AREA)

        sh_color = (20, 24, 32)
        sh_offset = (8, 12)
        alpha = em_resized[:, :, 3].astype(np.float32) / 255.0

        x1 = cx - size // 2
        y1 = cy - size // 2
        x2 = x1 + size
        y2 = y1 + size

        sx1 = x1 + sh_offset[0]
        sy1 = y1 + sh_offset[1]
        sx2 = sx1 + size
        sy2 = sy1 + size

        th, tw = target_bgr.shape[:2]
        if sx2 <= tw and sy2 <= th and sx1 >= 0 and sy1 >= 0:
            roi_sh = target_bgr[sy1:sy2, sx1:sx2].astype(np.float32)
            sh_mask = (alpha * 0.42)[..., None]
            target_bgr[sy1:sy2, sx1:sx2] = np.clip(roi_sh * (1.0 - sh_mask) + np.array(sh_color, dtype=np.float32) * sh_mask, 0, 255).astype(np.uint8)

        if x2 <= tw and y2 <= th and x1 >= 0 and y1 >= 0:
            roi = target_bgr[y1:y2, x1:x2].astype(np.float32)
            em_bgr = em_resized[:, :, :3].astype(np.float32)
            em_a = alpha[..., None]
            target_bgr[y1:y2, x1:x2] = np.clip(roi * (1.0 - em_a) + em_bgr * em_a, 0, 255).astype(np.uint8)
        return target_bgr

    # Left Page 3D Emoji (Upper Right margin of left page)
    if scene.left_emoji:
        em_lx = px + single_page_w - 95
        em_ly = py + 115
        canvas = overlay_3d_emoji(canvas, scene.left_emoji, em_lx, em_ly, size=115)

    # Right Page 3D Emoji (Lower Right corner of evidence photo)
    if scene.right_emoji:
        em_rx = right_page_cx + (right_card_w // 2) - 45
        em_ry = right_plate_cy + (right_card_h // 2) - 45
        canvas = overlay_3d_emoji(canvas, scene.right_emoji, em_rx, em_ry, size=125)

    return canvas


# ---------------------------------------------------------------------- #
# 5. Full End-to-End Production & Video Mastering
# ---------------------------------------------------------------------- #
def assemble_storybook_film(proj_dir: Path, output_mp4: Path) -> Path:
    """Assembles all storybook plates into motion clips, synthesizes Kokoro audio, mixes Foley + BGM, and encodes master MP4."""
    import wave
    import kokoro_onnx
    from tools.storybook_engine import render_storybook_clip

    videos_dir = proj_dir / "videos"
    cache_dir = proj_dir / "cache"
    videos_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    with open(proj_dir / "project.json", "r") as f:
        project_data = json.load(f)

    scenes = project_data["scenes"]
    logger.info(f"Assembling storybook film for {project_data['title']} ({len(scenes)} scenes)")

    # 1. Kokoro-82M Voiceover
    kokoro = kokoro_onnx.Kokoro(str(KOKORO_MODEL), str(KOKORO_VOICES))
    voice_adam = kokoro.get_voice_style("am_adam")
    voice_george = kokoro.get_voice_style("bm_george")
    house_blend = 0.68 * voice_adam + 0.32 * voice_george

    scene_audio_files = []
    scene_durations = []

    eq_filter = (
        "highpass=f=65,"
        "equalizer=f=135:t=q:w=1.1:g=+2.4,"
        "equalizer=f=2400:t=q:w=1.4:g=+0.8,"
        "equalizer=f=3400:t=q:w=1.6:g=-1.6,"
        "lowpass=f=13500,"
        "deesser=i=0.6:m=0.4:f=0.5:s=o,"
        "acompressor=threshold=-16dB:ratio=2.0:attack=15:release=160,"
        "alimiter=limit=-1.2dB"
    )

    for sc in scenes:
        clean_text = sc["text"].replace("*", "")
        wav_path = cache_dir / f"narration_{sc['id']}.wav"
        raw_tmp = cache_dir / f"raw_{sc['id']}.wav"

        samples, sr = kokoro.create(clean_text, voice=house_blend, speed=1.01)
        with wave.open(str(raw_tmp), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            audio_int16 = (samples * 32767.0).clip(-32768, 32767).astype(np.int16)
            wf.writeframes(audio_int16.tobytes())

        cmd = ["ffmpeg", "-y", "-i", str(raw_tmp), "-af", eq_filter, str(wav_path)]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        raw_tmp.unlink(missing_ok=True)

        with wave.open(str(wav_path), "rb") as wf:
            dur = wf.getnframes() / float(wf.getframerate())

        scene_audio_files.append(wav_path)
        scene_durations.append(round(dur + 0.35, 2))

    total_voice_duration = sum(scene_durations)
    logger.info(f"Total Narration Duration: {total_voice_duration:.2f}s ({total_voice_duration/60:.2f} mins)")

    # 2. Render Motion Clips for each Storybook Plate
    motion_presets = [
        "spread_pan", "dolly_in", "spread_pan", "dolly_in",
        "spread_pan", "dolly_in", "spread_pan", "dolly_in",
        "spread_pan", "dolly_in", "spread_pan",
    ]
    clip_paths = []
    for idx, sc in enumerate(scenes):
        img_path = proj_dir / sc["image"]
        clip_mp4 = videos_dir / f"{sc['id']}.mp4"
        dur = scene_durations[idx]
        motion = motion_presets[idx % len(motion_presets)]
        logger.info(f"Rendering storybook motion clip {sc['id']} ({dur}s, motion='{motion}')...")
        render_storybook_clip(
            image_path=img_path,
            output_mp4=clip_mp4,
            duration_s=dur,
            fps=30,
            width=1920,
            height=1080,
            style="classic",
            motion_preset=motion,
        )
        clip_paths.append(clip_mp4)

    # 3. Concatenate Visual Timeline
    concat_list = cache_dir / "clips_concat.txt"
    with open(concat_list, "w") as f:
        for cp in clip_paths:
            f.write(f"file '{cp.resolve()}'\n")

    merged_video = cache_dir / "visual_timeline.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(merged_video),
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # 4. Concatenate Voice Track with Padded Gaps
    audio_concat_list = cache_dir / "audio_concat.txt"
    with open(audio_concat_list, "w") as f:
        for idx, ap in enumerate(scene_audio_files):
            f.write(f"file '{ap.resolve()}'\n")
            gap_file = cache_dir / f"gap_{idx}.wav"
            with wave.open(str(ap), "rb") as awf:
                actual_dur = awf.getnframes() / float(awf.getframerate())
            pad_dur = max(0.05, scene_durations[idx] - actual_dur)
            pad_samples = int(pad_dur * 48000)
            with wave.open(str(gap_file), "wb") as gwf:
                gwf.setnchannels(1)
                gwf.setsampwidth(2)
                gwf.setframerate(48000)
                gwf.writeframes(np.zeros(pad_samples, dtype=np.int16).tobytes())
            f.write(f"file '{gap_file.resolve()}'\n")

    master_voice = cache_dir / "master_voice.wav"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(audio_concat_list),
        "-ar", "48000", "-ac", "2",
        str(master_voice),
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # 5. Composite Timed Diegetic Foley SFX
    sfx_track = np.zeros(int((total_voice_duration + 5.0) * 48000), dtype=np.float32)
    accum_time = 0.0
    for idx, sc in enumerate(scenes):
        for cue in sc.get("sound_cues", []):
            s_name = cue["name"]
            offset = cue.get("offset", 0.0)
            vol = cue.get("vol", 0.20)
            t_pos = accum_time + offset

            s_file = SFX_DIR / f"{s_name}.mp3"
            if not s_file.exists():
                s_file = SFX_DIR / f"{s_name}.wav"

            if s_file.exists():
                pcm_tmp = cache_dir / f"tmp_{s_name}.wav"
                subprocess.run([
                    "ffmpeg", "-y", "-i", str(s_file),
                    "-ar", "48000", "-ac", "1",
                    str(pcm_tmp),
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if pcm_tmp.exists():
                    with wave.open(str(pcm_tmp), "rb") as swf:
                        data = np.frombuffer(swf.readframes(swf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
                    start_s = int(t_pos * 48000)
                    end_s = min(len(sfx_track), start_s + len(data))
                    n_copy = end_s - start_s
                    if n_copy > 0:
                        sfx_track[start_s:end_s] += data[:n_copy] * vol
                    pcm_tmp.unlink(missing_ok=True)
        accum_time += scene_durations[idx]

    master_sfx = cache_dir / "master_sfx.wav"
    with wave.open(str(master_sfx), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(48000)
        wf.writeframes((sfx_track.clip(-1.0, 1.0) * 32767.0).astype(np.int16).tobytes())

    # 6. Audio Mixing with Mid-Duck Vocal Pocket & Broadcast -14 LUFS Loudnorm
    final_audio = cache_dir / "final_mixed_audio.wav"
    bgm_cand = BGM_FILE if BGM_FILE.exists() else master_voice
    complex_filter = (
        f"[1:a]aloop=loop=-1:size=2e+09,atrim=0:{total_voice_duration:.2f},volume=0.18[bgm];"
        "[bgm][0:a]sidechaincompress=threshold=0.08:ratio=3.0:attack=20:release=250[ducked_bgm];"
        "[0:a][ducked_bgm][2:a]amix=inputs=3:duration=first:weights=1.0 0.85 1.0[mix];"
        "[mix]loudnorm=I=-14.0:TP=-1.5:LRA=11[master]"
    )
    subprocess.run([
        "ffmpeg", "-y",
        "-i", str(master_voice),
        "-i", str(bgm_cand),
        "-i", str(master_sfx),
        "-filter_complex", complex_filter,
        "-map", "[master]",
        "-ar", "48000",
        str(final_audio),
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # 7. Final H.264 MP4 Broadcast Mastering
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "ffmpeg", "-y",
        "-i", str(merged_video),
        "-i", str(final_audio),
        "-c:v", "h264_videotoolbox",
        "-b:v", "14M",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "320k",
        "-ar", "48000",
        "-shortest",
        str(output_mp4),
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    logger.info(f"Broadcast Master MP4 complete: {output_mp4} ({output_mp4.stat().st_size / 1024 / 1024:.2f} MB)")
    return output_mp4


def produce_db_cooper_longform(render_video: bool = True, format: str = "long") -> Path:
    """Generates and masters the complete 2.5-minute physical storybook documentary."""
    project_slug = "long_01_db_cooper_1971"
    proj_dir = REPO_ROOT / ("projects" if format == "long" else "shorts") / project_slug
    images_dir = proj_dir / "images"
    videos_dir = proj_dir / "videos"
    cache_dir = proj_dir / "cache"
    output_dir = OUTPUT_DIR

    for d in [proj_dir, images_dir, videos_dir, cache_dir, output_dir]:
        d.mkdir(parents=True, exist_ok=True)

    logger.info("=== STEP 1: VALIDATING HUMAN NOVELISTIC PROSE ===")
    total_words = 0
    for sc in DB_COOPER_LONGFORM_SCRIPT:
        violations = validate_human_prose(sc.text)
        if violations:
            raise ValueError(f"Prose violation in {sc.scene_id}: {violations}")
        total_words += len(sc.text.split())

    logger.info(f"Verified {len(DB_COOPER_LONGFORM_SCRIPT)} scenes, {total_words} words. Zero AI buzzwords.")

    logger.info("=== STEP 2: STAGING & DOWNLOADING 3D EMOJIS & FOLEY SOUNDS ===")
    sound_assets: Dict[str, Path] = {}
    for sc in DB_COOPER_LONGFORM_SCRIPT:
        # Download 3D Fluent Emojis
        for em in [sc.left_emoji, sc.right_emoji]:
            if em:
                get_fluent_3d_emoji(em)
        # Download Foley SFX
        for cue in sc.sound_cues:
            s_name = cue["name"]
            s_query = cue["search"]
            if s_name not in sound_assets:
                p = resolve_diegetic_sound(s_name, s_query)
                if p:
                    sound_assets[s_name] = p
                    logger.info(f"  [SOUND READY] {s_name} -> {p.name}")

    logger.info("=== STEP 3: RENDERING PHYSICAL OPEN-STORYBOOK SCENE PLATES ===")
    rendered_plates: List[Path] = []
    for sc in DB_COOPER_LONGFORM_SCRIPT:
        plate_path = images_dir / f"{sc.scene_id}.jpg"
        plate_img = render_humanized_plate_16x9(sc, width=1920, height=1080)
        cv2.imwrite(str(plate_path), plate_img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        logger.info(f"  [STORYBOOK PLATE CREATED] {plate_path.name}")
        rendered_plates.append(plate_path)

    logger.info("=== STEP 4: GENERATING PROJECT METADATA ===")
    project_meta = {
        "id": "LV-01",
        "slug": project_slug,
        "format": "long",
        "genre": "storybook_classic",
        "voice": "kokoro",
        "rate": "+1%",
        "gap": 0.08,
        "music": {
            "volume": 0.18,
            "sfx_volume": 0.12,
        },
        "branding": {
            "intro": True,
            "outro": True,
        },
        "title": "The Skyjacker Who Vanished at 10,000 Feet: The True Story of D.B. Cooper",
        "topic": "The 1971 D.B. Cooper Skyjacking",
        "science": "Ralph Himmelsbach (FBI 1971)",
        "citation_stat": "$200,000 & 10,000 ft",
        "citation_verified": True,
        "scenes": [
            {
                "id": sc.scene_id,
                "text": sc.text,
                "prompt": f"16:9 cinematic open storybook, {sc.center_focus}, {sc.left_plate_text}, {sc.right_prop}, 3D emojis, brass pushpins",
                "duration": round(len(sc.text.split()) * 0.44, 1),
                "image": f"images/{sc.scene_id}.jpg",
                "sound_cues": sc.sound_cues,
            }
            for sc in DB_COOPER_LONGFORM_SCRIPT
        ],
    }

    proj_json = proj_dir / "project.json"
    with open(proj_json, "w") as f:
        json.dump(project_meta, f, indent=2)
    logger.info(f"Saved project metadata -> {proj_json}")

    if not render_video:
        return proj_json

    logger.info("=== STEP 5: FULL VIDEO ASSEMBLY & MASTERING ===")
    final_film = OUTPUT_DIR / "the_1971_db_cooper_skyjacking_16x9.mp4"
    assemble_storybook_film(proj_dir, final_film)
    logger.info(f"Final Master Film Ready: {final_film}")
    return final_film


def main():
    parser = argparse.ArgumentParser(description="Universal Humanizer & Sound Immersion Director")
    parser.add_argument("--story", type=str, default="D.B. Cooper 1971", help="Story topic")
    parser.add_argument("--format", type=str, choices=["short", "long"], default="long", help="Video format")
    parser.add_argument("--render", action="store_true", help="Render full video")
    parser.add_argument("--blueprint", action="store_true", help="Generate blueprint only")
    args = parser.parse_args()

    logger.info(f"Starting Humanizer Director for story '{args.story}' ({args.format})...")
    out_path = produce_db_cooper_longform(render_video=args.render, format=args.format)
    logger.info(f"Process completed successfully: {out_path}")


if __name__ == "__main__":
    main()
