#!/usr/bin/env python3
"""Forensic Casebook Engine v6.0 (LEMMiNO-Tier Broadcast Documentary Engine)

Full-Screen 1080p dynamic investigative montage with:
- Connected Spatial Virtual Camera (dynamic gliding, panning, and zooming across wide exhibits)
- Frame-Accurate Word-Level Foley Sound Synchronization
- Stereo Spatial Audio Panning (matching on-screen evidence positions)
- Two-Act Dynamic Mystery & Thriller Soundtrack with Vocal Mid-Side Ducking
- Local Kokoro-82M Neural Narration with Dramatic Noir Sentence Chunking
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import subprocess
import sys
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from tools.production_ledger import record_ledger_event  # noqa: E402
from tools.sound_architect import (  # noqa: E402
    DECIBEL_BUDGET,
    detect_speech_pauses,
    get_cue_decibel,
    get_cue_linear_gain,
    snap_cue_to_breath_pause,
)

# ---------------------------------------------------------------------------
# Logging & System Constants
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ForensicEngine")

MODELS_DIR = REPO_ROOT / "tools" / "kokoro_models"
KOKORO_MODEL = MODELS_DIR / "kokoro-v1.0.onnx"
KOKORO_VOICES = MODELS_DIR / "voices-v1.0.bin"

SFX_DIR = REPO_ROOT / "assets" / "audio" / "sfx"
BGM_FILE_1 = REPO_ROOT / "assets" / "audio" / "bgm" / "echoes_mystery.mp3"
BGM_FILE_2 = REPO_ROOT / "assets" / "audio" / "bgm" / "vertigo_tension.mp3"

FONT_MONO = "/System/Library/Fonts/Supplemental/Courier New.ttf"
FONT_SANS = "/System/Library/Fonts/Helvetica.ttc"
FONT_BEBAS = str(REPO_ROOT / "tools" / "fonts" / "BebasNeue-Regular.ttf")
FONT_BOLD = str(REPO_ROOT / "tools" / "fonts" / "BeVietnamPro-Bold.ttf")

WIDTH = 1920
HEIGHT = 1080


# ---------------------------------------------------------------------------
# Story Scene Dataclass & Complete 18-Scene Saga
# ---------------------------------------------------------------------------
@dataclass
class StoryScene:
    scene_id: str
    act: str
    title: str
    text: str
    highlighter_phrase: str
    timestamp_text: str
    location_text: str
    exhibit_code: str
    stamp_text: str
    hero_image: str
    cutout_image: str
    secondary_trigger_word: str
    sound_cues: List[Dict[str, Any]]
    speech_chunks: List[Tuple[str, float, float]] = field(default_factory=list)


DB_COOPER_FORENSIC_SERIES: List[StoryScene] = [
    StoryScene(
        scene_id="s01",
        act="Act 1: The Boarding",
        title="PORTLAND INTERNATIONAL AIRPORT",
        text="On a rainy Wednesday afternoon before Thanksgiving, a man in a dark business suit walked up to the Northwest Orient counter in Portland and bought a one-way ticket for twenty dollars.",
        highlighter_phrase="twenty dollars",
        timestamp_text="14:36 PST  •  NOV 24, 1971",
        location_text="PORTLAND INTL AIRPORT (PDX)",
        exhibit_code="EXHIBIT 01: NW ORIENT TICKET #0281319",
        stamp_text="CONFIRMED",
        hero_image="s01.jpg",
        cutout_image="s01_cutout_ticket.png",
        secondary_trigger_word="ticket",
        sound_cues=[
            {"name": "typewriter_sfx0281319", "word_trigger": "ticket", "offset": 11.5, "vol": 0.22, "pan": "left"},
            {"name": "cash_register", "word_trigger": "twenty", "offset": 12.4, "vol": 0.24, "pan": "left"},
        ],
        speech_chunks=[
            ("On a rainy Wednesday afternoon before Thanksgiving...", 0.92, 0.45),
            ("A quiet man in a dark business suit walked up to the Northwest Orient counter in Portland.", 0.92, 0.40),
            ("And bought a one-way ticket for twenty dollars.", 0.90, 0.55),
        ],
    ),
    StoryScene(
        scene_id="s02",
        act="Act 1: The Passenger",
        title="BOEING 727 CABIN - SEAT 18C",
        text="He gave the name Dan Cooper. He boarded Boeing 727 Flight 305, took Seat 18C, lit a cigarette, and ordered a bourbon and soda with crisp ice.",
        highlighter_phrase="Seat 18C",
        timestamp_text="14:50 PST  •  SEAT 18C",
        location_text="FLIGHT 305 AIRBORNE",
        exhibit_code="EXHIBIT 02: PASSENGER MANIFEST 18C",
        stamp_text="BOARDED",
        hero_image="s02.jpg",
        cutout_image="s02_cutout_bourbon.png",
        secondary_trigger_word="bourbon",
        sound_cues=[
            {"name": "match_strike", "word_trigger": "cigarette", "offset": 9.4, "vol": 0.24, "pan": "right"},
            {"name": "ice_in_bourbon", "word_trigger": "bourbon", "offset": 11.4, "vol": 0.22, "pan": "right"},
        ],
        speech_chunks=[
            ("He gave the name Dan Cooper.", 0.90, 0.40),
            ("He boarded Boeing 727 Flight 305, took Seat 18C...", 0.92, 0.35),
            ("Lit a cigarette...", 0.92, 0.30),
            ("And ordered a bourbon and soda with crisp ice.", 0.88, 0.60),
        ],
    ),
    StoryScene(
        scene_id="s03",
        act="Act 1: The Threat",
        title="THE HANDWRITTEN EXTORTION NOTE",
        text="Minutes after takeoff, he handed flight attendant Florence Schaffner a folded paper slip. She slipped it into her purse unread until Cooper leaned across: Miss, you better look at that note. I have a bomb.",
        highlighter_phrase="I have a bomb",
        timestamp_text="15:07 PST  •  ALTITUDE: 12,000 FT",
        location_text="AFT CABIN AISLE",
        exhibit_code="EXHIBIT 03: RANSOM DEMAND SLIP",
        stamp_text="BOMB THREAT",
        hero_image="s03.jpg",
        cutout_image="s03_cutout_briefcase.png",
        secondary_trigger_word="bomb",
        sound_cues=[
            {"name": "flight_attendant_ding", "word_trigger": "handed", "offset": 1.7, "vol": 0.24, "pan": "left"},
            {"name": "sub_bass_drop", "word_trigger": "bomb", "offset": 15.1, "vol": 0.28, "pan": "center"},
        ],
        speech_chunks=[
            ("Minutes after takeoff, he handed flight attendant Florence Schaffner a folded note.", 0.92, 0.40),
            ("She slipped it into her purse unread.", 0.90, 0.40),
            ("Until Cooper leaned across the aisle and whispered...", 0.88, 0.45),
            ("Miss, you better look at that note.", 0.88, 0.40),
            ("I have a bomb.", 0.86, 0.65),
        ],
    ),
    StoryScene(
        scene_id="s04",
        act="Act 1: The Demand",
        title="ATTACHÉ EXPLOSIVE SCHEMATIC",
        text="Inside his black briefcase lay eight red cylinders wired to a cylindrical battery. His demand was precise: two hundred thousand dollars in negotiable twenty-dollar bills, and four parachutes.",
        highlighter_phrase="two hundred thousand dollars",
        timestamp_text="15:15 PST  •  EXTORTION DEMANDS",
        location_text="B-727 MID CABIN",
        exhibit_code="EXHIBIT 04: ATTACHÉ CYLINDER ARRAY",
        stamp_text="VERIFIED EVIDENCE",
        hero_image="s04.jpg",
        cutout_image="s04_cutout_parachutes.png",
        secondary_trigger_word="parachutes",
        sound_cues=[
            {"name": "tension_clock", "word_trigger": "briefcase", "offset": 1.2, "vol": 0.22, "pan": "center"},
        ],
        speech_chunks=[
            ("Inside his black briefcase lay eight red cylinders wired to a large battery.", 0.92, 0.45),
            ("His demands were surgical.", 0.90, 0.40),
            ("Two hundred thousand dollars in negotiable twenty-dollar bills.", 0.88, 0.50),
            ("And four military parachutes.", 0.88, 0.60),
        ],
    ),
    StoryScene(
        scene_id="s05",
        act="Act 2: The Exchange",
        title="SEATTLE-TACOMA TARMAC EXCHANGE",
        text="At Seattle-Tacoma Airport, thirty-six innocent passengers were released in exchange for the canvas knapsack of cash. Cooper allowed the plane to refuel, ordering the cockpit crew to fly toward Reno at minimum speed.",
        highlighter_phrase="thirty-six innocent passengers released",
        timestamp_text="17:45 PST  •  SEATTLE-TACOMA (SEA)",
        location_text="SEA-TAC RUNWAY HOLDING AREA",
        exhibit_code="EXHIBIT 05: TARMAC RANSOM TRANSFER",
        stamp_text="HOSTAGES FREED",
        hero_image="s05.jpg",
        cutout_image="s05_cutout_pilot_watch.png",
        secondary_trigger_word="refuel",
        sound_cues=[
            {"name": "cockpit_radio", "word_trigger": "released", "offset": 3.8, "vol": 0.22, "pan": "center"},
        ],
        speech_chunks=[
            ("At Seattle-Tacoma Airport, thirty-six innocent passengers were released in exchange for the cash.", 0.92, 0.45),
            ("Cooper allowed the airliner to refuel.", 0.90, 0.35),
            ("Ordering the cockpit crew to fly toward Reno... at minimum airspeed.", 0.88, 0.60),
        ],
    ),
    StoryScene(
        scene_id="s06",
        act="Act 2: The Flight Specs",
        title="COCKPIT FLIGHT ENVELOPE RESTRICTIONS",
        text="He demanded the landing gear stay down, flaps locked at fifteen degrees, and cabin pressure completely unpressurized.",
        highlighter_phrase="completely unpressurized",
        timestamp_text="19:36 PST  •  ALTITUDE: 10,000 FT",
        location_text="ROUTE V-23 SOUTHBOUND",
        exhibit_code="EXHIBIT 06: B727 FLIGHT ENVELOPE",
        stamp_text="RESTRICTED",
        hero_image="s06.jpg",
        cutout_image="s06_cutout_altimeter.png",
        secondary_trigger_word="pressure",
        sound_cues=[
            {"name": "pressure_drop", "word_trigger": "unpressurized", "offset": 7.2, "vol": 0.24, "pan": "right"},
        ],
        speech_chunks=[
            ("He demanded the landing gear stay down.", 0.90, 0.40),
            ("Flaps locked at fifteen degrees.", 0.90, 0.40),
            ("And the cabin completely unpressurized.", 0.88, 0.65),
        ],
    ),
    StoryScene(
        scene_id="s07",
        act="Act 2: The Ventral Stairs",
        title="VENTRAL AIRSTAIRS DEPLOYMENT",
        text="At eight o'clock, somewhere over southwestern Washington in a freezing winter rainstorm, Cooper ordered the remaining crew into the cockpit and lowered the Boeing 727's rear ventral stairs.",
        highlighter_phrase="lowered the rear ventral stairs",
        timestamp_text="20:00 PST  •  LEWIS RIVER APPROACH",
        location_text="SW WASHINGTON AIRSPACE",
        exhibit_code="EXHIBIT 07: VENTRAL ACTUATOR LOG",
        stamp_text="STAIRS LOWERED",
        hero_image="s07.jpg",
        cutout_image="s07_cutout_blueprint.png",
        secondary_trigger_word="stairs",
        sound_cues=[
            {"name": "wind_howl", "word_trigger": "stairs", "offset": 12.4, "vol": 0.26, "pan": "center"},
        ],
        speech_chunks=[
            ("At eight o'clock, somewhere over southwestern Washington in a freezing winter storm...", 0.92, 0.45),
            ("Cooper ordered the remaining crew into the cockpit.", 0.90, 0.40),
            ("And lowered the Boeing 727's rear ventral stairs into the freezing sky.", 0.88, 0.65),
        ],
    ),
    StoryScene(
        scene_id="s08",
        act="Act 3: The Jump",
        title="8:13 PM PRESSURE OSCILLATION",
        text="At 8:13 PM, pilots felt a sudden upward bump of the tail section as cabin air pressure surged. Cooper had jumped into the pitch-black void at ten thousand feet, in minus fifty-seven degree wind chill.",
        highlighter_phrase="jumped into the pitch-black void",
        timestamp_text="20:13 PST  •  TAIL UPWARD BUMP",
        location_text="ARIEL, WASHINGTON (APPROX)",
        exhibit_code="EXHIBIT 08: 8:13 PM PRESSURE OSCILLOSCOPE",
        stamp_text="JUMP CONFIRMED",
        hero_image="s08.jpg",
        cutout_image="s08_cutout_pressure_graph.png",
        secondary_trigger_word="jumped",
        sound_cues=[
            {"name": "thunder_crack", "word_trigger": "bump", "offset": 3.9, "vol": 0.28, "pan": "center"},
            {"name": "dramatic_whoosh", "word_trigger": "void", "offset": 9.8, "vol": 0.26, "pan": "center"},
        ],
        speech_chunks=[
            ("At 8:13 PM, pilots felt a sudden upward bump of the tail section.", 0.92, 0.45),
            ("Cabin pressure surged.", 0.90, 0.40),
            ("Dan Cooper had jumped into the pitch-black void at ten thousand feet...", 0.88, 0.50),
            ("In minus fifty-seven degree wind chill.", 0.86, 0.70),
        ],
    ),
    StoryScene(
        scene_id="s09",
        act="Act 3: The Vanishing",
        title="USAF F-106 PURSUIT INTERCEPTORS",
        text="He had no helmet, no night-vision, and wore loafers and a light raincoat. Two Air Force fighter jets trailing the airliner saw nothing drop into the darkness below.",
        highlighter_phrase="saw nothing drop",
        timestamp_text="20:20 PST  •  F-106 PURSUIT",
        location_text="RADAR CONTACT: NEGATIVE",
        exhibit_code="EXHIBIT 09: USAF CHASE MISSION LOG",
        stamp_text="TARGET LOST",
        hero_image="s09.jpg",
        cutout_image="s09_cutout_loafers.png",
        secondary_trigger_word="raincoat",
        sound_cues=[
            {"name": "wind_howl", "word_trigger": "darkness", "offset": 10.5, "vol": 0.22, "pan": "center"},
        ],
        speech_chunks=[
            ("He had no helmet. No night-vision.", 0.88, 0.45),
            ("Loafers and a light trench coat.", 0.88, 0.45),
            ("Two supersonic Air Force fighter jets trailing the airliner saw nothing drop into the darkness below.", 0.90, 0.65),
        ],
    ),
    StoryScene(
        scene_id="s10",
        act="Act 3: Operation NORJAK",
        title="OPERATION NORJAK GROUND SWEEP",
        text="The FBI launched Operation NORJAK—the largest manhunt in aviation history. Over one thousand federal agents, soldiers, and search dogs combed the rugged Washington wilderness, finding nothing.",
        highlighter_phrase="largest manhunt in aviation history",
        timestamp_text="WINTER 1971  •  1,000 AGENTS",
        location_text="LEWIS RIVER DRAINAGE BASIN",
        exhibit_code="EXHIBIT 10: SEARCH GRID SECTORS",
        stamp_text="NO CONTACT",
        hero_image="s11.jpg",
        cutout_image="s11_cutout_evidence_board.png",
        secondary_trigger_word="manhunt",
        sound_cues=[
            {"name": "dramatic_whoosh", "word_trigger": "manhunt", "offset": 3.2, "vol": 0.24, "pan": "center"},
        ],
        speech_chunks=[
            ("The FBI launched Operation NORJAK—the largest manhunt in aviation history.", 0.92, 0.45),
            ("Over one thousand federal agents, soldiers, and search dogs combed the rugged Washington wilderness.", 0.90, 0.40),
            ("Finding absolutely nothing.", 0.88, 0.60),
        ],
    ),
    StoryScene(
        scene_id="s11",
        act="Act 4: The Physical Evidence",
        title="PHYSICAL ARTIFACTS RECOVERED",
        text="Left behind on Seat 18C was a black clip-on necktie with a mother-of-pearl tie clasp, two of the four parachutes, and sixty-six cigarette butts.",
        highlighter_phrase="black clip-on necktie",
        timestamp_text="NOV 25, 1971  •  EVIDENCE RECOVERY",
        location_text="RENO AIRPORT INSPECTION",
        exhibit_code="EXHIBIT 11: PHYSICAL EVIDENCE RECOVERED",
        stamp_text="PHYSICAL EVIDENCE",
        hero_image="s12.jpg",
        cutout_image="s12_cutout_tie.png",
        secondary_trigger_word="tie",
        sound_cues=[
            {"name": "shutter", "word_trigger": "necktie", "offset": 3.8, "vol": 0.24, "pan": "right"},
        ],
        speech_chunks=[
            ("Left behind on Seat 18C was a black clip-on necktie with a mother-of-pearl tie clasp.", 0.92, 0.45),
            ("Two of the four parachutes.", 0.90, 0.35),
            ("And sixty-six smoked cigarette butts.", 0.88, 0.60),
        ],
    ),
    StoryScene(
        scene_id="s12",
        act="Act 4: The Facial Composite",
        title="FBI OFFICIAL COMPOSITE SKETCHES",
        text="From the testimony of flight attendants Florence Schaffner and Tina Mucklow, the FBI compiled the iconic composite sketches of a calm, middle-aged man with dark sunglasses.",
        highlighter_phrase="iconic composite sketches",
        timestamp_text="DEC 1971  •  WITNESS DESCRIPTIONS",
        location_text="FBI PORTLAND FIELD OFFICE",
        exhibit_code="EXHIBIT 12: FBI COMPOSITE #1 & #2",
        stamp_text="WANTED BY FBI",
        hero_image="s13.jpg",
        cutout_image="s13_cutout_sketches.png",
        secondary_trigger_word="sketches",
        sound_cues=[
            {"name": "typewriter_sfx0281319", "word_trigger": "sketches", "offset": 6.8, "vol": 0.22, "pan": "right"},
        ],
        speech_chunks=[
            ("From the testimony of flight attendants Florence Schaffner and Tina Mucklow...", 0.92, 0.45),
            ("The FBI compiled the iconic composite sketches of a calm, middle-aged man in dark sunglasses.", 0.90, 0.55),
        ],
    ),
    StoryScene(
        scene_id="s13",
        act="Act 4: The Serial Ledger",
        title="34-PAGE SERIAL NUMBER DIRECTORY",
        text="The FBI distributed thirty-four-page booklets listing every single twenty-dollar serial number to banks, casinos, and racetracks worldwide. In four decades, not one bill ever surfaced in circulation.",
        highlighter_phrase="not one bill ever surfaced",
        timestamp_text="1971–2016  •  10,000 SERIAL NUMBERS",
        location_text="GLOBAL FINANCIAL MONITORING",
        exhibit_code="EXHIBIT 13: 10,000 SERIAL NUMBERS",
        stamp_text="ZERO CIRCULATION",
        hero_image="s14.jpg",
        cutout_image="s14_cutout_serial_ledger.png",
        secondary_trigger_word="serial",
        sound_cues=[
            {"name": "tension_clock", "word_trigger": "booklets", "offset": 3.4, "vol": 0.22, "pan": "center"},
        ],
        speech_chunks=[
            ("The FBI distributed thirty-four-page booklets listing every single twenty-dollar serial number.", 0.92, 0.45),
            ("To banks, casinos, and racetracks worldwide.", 0.90, 0.40),
            ("In four decades... not one single bill ever surfaced in circulation.", 0.88, 0.65),
        ],
    ),
    StoryScene(
        scene_id="s14",
        act="Act 5: The River Sand",
        title="1980 TINA BAR DISCOVERY",
        text="Then in 1980, an eight-year-old boy digging in the sand at Tina Bar along the Columbia River uncovered fifty-eight hundred dollars in decaying twenties, rubber bands still holding them together.",
        highlighter_phrase="fifty-eight hundred dollars in decaying twenties",
        timestamp_text="FEB 10, 1980  •  COLUMBIA RIVER",
        location_text="TINA BAR, WASHINGTON",
        exhibit_code="EXHIBIT 14: TINA BAR EXCAVATION SITE",
        stamp_text="RECOVERED CASH",
        hero_image="s10.jpg",
        cutout_image="s10_cutout_rotting_bills.png",
        secondary_trigger_word="rotting",
        sound_cues=[
            {"name": "vinyl_needle", "word_trigger": "decaying", "offset": 8.5, "vol": 0.24, "pan": "right"},
        ],
        speech_chunks=[
            ("Then in 1980, an eight-year-old boy digging in the sand at Tina Bar uncovered fifty-eight hundred dollars in decaying twenties...", 0.92, 0.50),
            ("With the rubber bands still intact.", 0.88, 0.60),
        ],
    ),
    StoryScene(
        scene_id="s15",
        act="Act 5: Suspect One",
        title="PRIMARY SUSPECT: RICHARD MCCOY JR.",
        text="Five months after Cooper vanished, an Army Green Beret named Richard McCoy Jr. hijacked a Boeing 727 using identical demands and jumped over Utah with five hundred thousand dollars.",
        highlighter_phrase="jumped over Utah with five hundred thousand dollars",
        timestamp_text="APRIL 1972  •  SALT LAKE CITY",
        location_text="PROVO, UTAH",
        exhibit_code="EXHIBIT 15: SUSPECT: RICHARD MCCOY JR.",
        stamp_text="COPYCAT HIJACKER",
        hero_image="s15.jpg",
        cutout_image="s15_cutout_mccoy.png",
        secondary_trigger_word="McCoy",
        sound_cues=[
            {"name": "boom", "word_trigger": "McCoy", "offset": 4.5, "vol": 0.26, "pan": "right"},
        ],
        speech_chunks=[
            ("Five months after Cooper vanished, an Army Green Beret named Richard McCoy Jr. hijacked a Boeing 727 with identical demands.", 0.92, 0.45),
            ("And jumped over Utah with five hundred thousand dollars.", 0.88, 0.60),
        ],
    ),
    StoryScene(
        scene_id="s16",
        act="Act 5: Suspect Two",
        title="PRIMARY SUSPECT: ROBERT RACKSTRAW",
        text="Another prime suspect was Robert Rackstraw—a decorated Vietnam veteran, paratrooper, and pilot who possessed the specialized airborne training required to survive the drop.",
        highlighter_phrase="specialized airborne training",
        timestamp_text="1978–2016  •  VIETNAM VET",
        location_text="SAN DIEGO, CALIFORNIA",
        exhibit_code="EXHIBIT 16: SUSPECT: ROBERT RACKSTRAW",
        stamp_text="SUSPECT: RACKSTRAW",
        hero_image="s16.jpg",
        cutout_image="s16_cutout_rackstraw.png",
        secondary_trigger_word="Rackstraw",
        sound_cues=[
            {"name": "shutter", "word_trigger": "Rackstraw", "offset": 2.8, "vol": 0.24, "pan": "right"},
        ],
        speech_chunks=[
            ("Another prime suspect was Robert Rackstraw.", 0.90, 0.40),
            ("A decorated Vietnam veteran, paratrooper, and pilot who possessed the specialized airborne training required to survive the drop.", 0.90, 0.60),
        ],
    ),
    StoryScene(
        scene_id="s17",
        act="Act 6: Modern Forensic Science",
        title="2007 TITANIUM TIE ANALYSIS",
        text="In 2007, forensic scientists used scanning electron microscopes on Cooper's tie and discovered rare particles of pure titanium and bismuth—tracing his workplace directly to high-tech aerospace alloy laboratories.",
        highlighter_phrase="pure titanium and bismuth",
        timestamp_text="2007  •  ELECTRON MICROSCOPY",
        location_text="THE CITIZEN SLEUTHS LAB",
        exhibit_code="EXHIBIT 17: TITANIUM ALLOY SPECTRA",
        stamp_text="FORENSIC MATCH",
        hero_image="s17.jpg",
        cutout_image="s17_cutout_titanium_graph.png",
        secondary_trigger_word="titanium",
        sound_cues=[
            {"name": "seatbelt_chime", "word_trigger": "microscopes", "offset": 4.2, "vol": 0.24, "pan": "right"},
        ],
        speech_chunks=[
            ("In 2007, forensic scientists used scanning electron microscopes on Cooper's clip-on tie...", 0.92, 0.45),
            ("And discovered rare particles of pure titanium and bismuth.", 0.90, 0.40),
            ("Tracing his workplace directly to high-tech aerospace alloy laboratories.", 0.88, 0.65),
        ],
    ),
    StoryScene(
        scene_id="s18",
        act="Act 6: The Unsolved Legend",
        title="THE ONLY UNSOLVED SKYJACKING",
        text="In 2016, after forty-five years and over a thousand suspects, the FBI officially suspended its active investigation. Did Dan Cooper die in the freezing storm, or pull off the perfect crime? Subscribe for the next forensic deep dive.",
        highlighter_phrase="the perfect crime",
        timestamp_text="JULY 12, 2016  •  ACTIVE CASE SUSPENDED",
        location_text="FBI HEADQUARTERS, WASHINGTON D.C.",
        exhibit_code="EXHIBIT 18: CASE STATUS: SUSPENDED",
        stamp_text="CASE SUSPENDED",
        hero_image="s18.jpg",
        cutout_image="s18_cutout_norjak_seal.png",
        secondary_trigger_word="ghost",
        sound_cues=[
            {"name": "sub_bass_drop", "word_trigger": "perfect", "offset": 12.8, "vol": 0.28, "pan": "center"},
        ],
        speech_chunks=[
            ("In 2016, after forty-five years and over a thousand suspects, the FBI officially suspended its active investigation.", 0.92, 0.50),
            ("Did Dan Cooper die in the freezing storm...", 0.88, 0.45),
            ("Or pull off the perfect crime?", 0.86, 0.60),
            ("Subscribe for the next forensic deep dive.", 0.90, 0.70),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Visual Element & Forensic Compositing Utilities
# ---------------------------------------------------------------------------
def smoothstep(edge0: float, edge1: float, x: float) -> float:
    t = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def render_camera_viewport(
    canvas: np.ndarray,
    cam_cx: float,
    cam_cy: float,
    zoom: float,
    angle_deg: float = 0.0,
    out_w: int = 1920,
    out_h: int = 1080,
) -> np.ndarray:
    """Transforms wide forensic canvas through sub-pixel virtual camera trajectory."""
    M = cv2.getRotationMatrix2D((cam_cx, cam_cy), angle_deg, zoom)
    M[0, 2] += (out_w / 2.0) - cam_cx
    M[1, 2] += (out_h / 2.0) - cam_cy
    return cv2.warpAffine(canvas, M, (out_w, out_h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT_101)


def draw_frosted_scotch_tape(
    canvas: np.ndarray,
    cx: int,
    cy: int,
    width: int = 85,
    height: int = 26,
    angle_deg: float = -25.0,
) -> np.ndarray:
    """Draws realistic translucent matte Scotch tape with soft specular highlights and torn edges."""
    tape = np.full((height, width, 4), (220, 235, 245, 175), dtype=np.uint8)
    tape[2:4, :] = (255, 255, 255, 210)
    noise = np.random.normal(0, 10, (height, width)).astype(np.float32)
    tape[:, :, 3] = np.clip(tape[:, :, 3].astype(np.float32) + noise, 120, 210).astype(np.uint8)

    rad = math.radians(angle_deg)
    cos_a, sin_a = abs(math.cos(rad)), abs(math.sin(rad))
    rot_w = int(width * cos_a + height * sin_a) + 6
    rot_h = int(width * sin_a + height * cos_a) + 6

    M = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), angle_deg, 1.0)
    M[0, 2] += (rot_w - width) / 2.0
    M[1, 2] += (rot_h - height) / 2.0

    rot_t = cv2.warpAffine(tape, M, (rot_w, rot_h), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
    x1 = cx - rot_w // 2
    y1 = cy - rot_h // 2
    x2, y2 = x1 + rot_w, y1 + rot_h

    c_h, c_w = canvas.shape[:2]
    if x2 <= c_w and y2 <= c_h and x1 >= 0 and y1 >= 0:
        a = rot_t[:, :, 3].astype(np.float32) / 255.0
        bgr = rot_t[:, :, :3].astype(np.float32)
        roi = canvas[y1:y2, x1:x2].astype(np.float32)
        canvas[y1:y2, x1:x2] = np.clip(roi * (1.0 - a[..., None]) + bgr * a[..., None], 0, 255).astype(np.uint8)

    return canvas


def draw_brass_pushpin(canvas: np.ndarray, cx: int, cy: int, radius: int = 14) -> np.ndarray:
    """Draws a tactile metallic brass pushpin with directional drop shadow and specular glint."""
    cv2.circle(canvas, (cx + 3, cy + 5), radius + 1, (15, 18, 24), -1)
    cv2.circle(canvas, (cx, cy), radius, (38, 165, 215), -1, cv2.LINE_AA)
    cv2.circle(canvas, (cx, cy), radius - 3, (28, 130, 180), -1, cv2.LINE_AA)
    cv2.circle(canvas, (cx - radius // 3, cy - radius // 3), radius // 3, (120, 220, 255), -1, cv2.LINE_AA)
    return canvas


def draw_rubber_stamp(
    canvas: np.ndarray,
    text: str,
    cx: int,
    cy: int,
    angle_deg: float = -14.0,
    color_bgr: Tuple[int, int, int] = (30, 30, 195),
) -> np.ndarray:
    """Draws an official archival weathered rubber stamp with double border and ink splatter."""
    text = text.upper()
    font_scale = 0.72
    thickness = 2
    (tw, th), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)

    pad_x, pad_y = 20, 14
    s_w = tw + pad_x * 2
    s_h = th + pad_y * 2 + baseline

    stamp_mat = np.zeros((s_h, s_w, 4), dtype=np.uint8)
    cv2.rectangle(stamp_mat, (2, 2), (s_w - 3, s_h - 3), (*color_bgr, 230), 2)
    cv2.rectangle(stamp_mat, (6, 6), (s_w - 7, s_h - 7), (*color_bgr, 210), 1)
    cv2.putText(stamp_mat, text, (pad_x, s_h - pad_y - baseline // 2), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (*color_bgr, 240), thickness, cv2.LINE_AA)

    noise = np.random.uniform(0.68, 1.0, (s_h, s_w)).astype(np.float32)
    stamp_mat[:, :, 3] = (stamp_mat[:, :, 3].astype(np.float32) * noise).astype(np.uint8)

    rad = math.radians(angle_deg)
    cos_a, sin_a = abs(math.cos(rad)), abs(math.sin(rad))
    rot_w = int(s_w * cos_a + s_h * sin_a) + 10
    rot_h = int(s_w * sin_a + s_h * cos_a) + 10

    M = cv2.getRotationMatrix2D((s_w / 2.0, s_h / 2.0), angle_deg, 1.0)
    M[0, 2] += (rot_w - s_w) / 2.0
    M[1, 2] += (rot_h - s_h) / 2.0

    rot_s = cv2.warpAffine(stamp_mat, M, (rot_w, rot_h), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
    x1 = cx - rot_w // 2
    y1 = cy - rot_h // 2
    x2, y2 = x1 + rot_w, y1 + rot_h

    c_h, c_w = canvas.shape[:2]
    if x2 <= c_w and y2 <= c_h and x1 >= 0 and y1 >= 0:
        a = rot_s[:, :, 3].astype(np.float32) / 255.0
        bgr = rot_s[:, :, :3].astype(np.float32)
        roi = canvas[y1:y2, x1:x2].astype(np.float32)
        canvas[y1:y2, x1:x2] = np.clip(roi * (1.0 - a[..., None]) + bgr * a[..., None], 0, 255).astype(np.uint8)

    return canvas


def draw_highlighter_bar(
    canvas: np.ndarray,
    x: int,
    y: int,
    w: int,
    h: int,
    progress: float = 1.0,
) -> np.ndarray:
    """Overlays dynamic fluorescent yellow highlighter sweep across text."""
    if progress <= 0.0 or w <= 0 or h <= 0:
        return canvas
    cur_w = int(w * max(0.0, min(1.0, progress)))
    if cur_w <= 0:
        return canvas

    c_h, c_w = canvas.shape[:2]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(c_w, x + cur_w), min(c_h, y + h)

    if x2 > x1 and y2 > y1:
        roi = canvas[y1:y2, x1:x2].astype(np.float32)
        yellow = np.array([25, 235, 255], dtype=np.float32)
        alpha = 0.38
        canvas[y1:y2, x1:x2] = np.clip(roi * (1.0 - alpha) + yellow * alpha, 0, 255).astype(np.uint8)

    return canvas


def composite_evidence_card_with_shadow(
    canvas: np.ndarray,
    card: np.ndarray,
    cx: int,
    cy: int,
    angle_deg: float = 0.0,
    shadow_blur: int = 28,
    shadow_alpha: float = 0.55,
) -> np.ndarray:
    """Composites an evidence card with sub-pixel rotation and realistic elevation drop shadow."""
    h, w = card.shape[:2]
    rad = math.radians(angle_deg)
    cos_a, sin_a = abs(math.cos(rad)), abs(math.sin(rad))
    rot_w = int(w * cos_a + h * sin_a) + 12
    rot_h = int(w * sin_a + h * cos_a) + 12

    M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle_deg, 1.0)
    M[0, 2] += (rot_w - w) / 2.0
    M[1, 2] += (rot_h - h) / 2.0

    rot_card = cv2.warpAffine(card, M, (rot_w, rot_h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))

    mask = np.full((h, w), 255, dtype=np.uint8)
    rot_mask = cv2.warpAffine(mask, M, (rot_w, rot_h), flags=cv2.INTER_LINEAR, borderValue=0)

    c_h, c_w = canvas.shape[:2]
    sx1 = cx - rot_w // 2 + 12
    sy1 = cy - rot_h // 2 + 18
    sx2, sy2 = sx1 + rot_w, sy1 + rot_h

    if sx2 <= c_w and sy2 <= c_h and sx1 >= 0 and sy1 >= 0:
        shadow_patch = cv2.GaussianBlur(rot_mask, (shadow_blur | 1, shadow_blur | 1), 0)
        s_factor = 1.0 - (shadow_patch.astype(np.float32) / 255.0) * shadow_alpha
        roi = canvas[sy1:sy2, sx1:sx2].astype(np.float32)
        canvas[sy1:sy2, sx1:sx2] = np.clip(roi * s_factor[..., None], 0, 255).astype(np.uint8)

    x1 = cx - rot_w // 2
    y1 = cy - rot_h // 2
    x2, y2 = x1 + rot_w, y1 + rot_h

    if x2 <= c_w and y2 <= c_h and x1 >= 0 and y1 >= 0:
        alpha_m = (rot_mask > 20).astype(np.float32)[..., None]
        roi = canvas[y1:y2, x1:x2].astype(np.float32)
        card_f = rot_card.astype(np.float32)
        canvas[y1:y2, x1:x2] = np.clip(roi * (1.0 - alpha_m) + card_f * alpha_m, 0, 255).astype(np.uint8)

    return canvas


def draw_top_bottom_telemetry_hud(
    canvas: np.ndarray,
    scene: StoryScene,
    scene_idx: int,
    total_scenes: int = 18,
) -> np.ndarray:
    """Renders professional investigative documentary telemetry bars on top and bottom margins."""
    h, w = canvas.shape[:2]

    # Semi-transparent top bar (Height: 52px)
    top_bar = np.zeros((52, w, 3), dtype=np.uint8)
    top_bar[:] = (16, 18, 22)
    canvas[0:52, :] = cv2.addWeighted(canvas[0:52, :], 0.30, top_bar, 0.70, 0)
    cv2.line(canvas, (0, 52), (w, 52), (65, 75, 88), 1)

    # Semi-transparent bottom bar (Height: 46px)
    bot_bar = np.zeros((46, w, 3), dtype=np.uint8)
    bot_bar[:] = (16, 18, 22)
    canvas[h - 46 : h, :] = cv2.addWeighted(canvas[h - 46 : h, :], 0.30, bot_bar, 0.70, 0)
    cv2.line(canvas, (0, h - 46), (w, h - 46), (65, 75, 88), 1)

    cv2.putText(
        canvas,
        "FBI NORJAK INVESTIGATIVE DOSSIER  •  CASE FILE #44-1298  •  CLASSIFIED",
        (38, 34),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.52,
        (225, 230, 240),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        f"{scene.act.upper()}  •  EXHIBIT {scene_idx + 1:02d}/{total_scenes:02d}",
        (w - 380, 34),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        (214, 180, 100),
        1,
        cv2.LINE_AA,
    )

    cv2.putText(
        canvas,
        f"TIME: {scene.timestamp_text}   |   LOC: {scene.location_text}",
        (38, h - 18),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.44,
        (190, 205, 215),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        scene.exhibit_code.upper(),
        (w - 420, h - 18),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.44,
        (130, 185, 235),
        1,
        cv2.LINE_AA,
    )

    return canvas


# ---------------------------------------------------------------------------
# Specialized Forensic Visual Renderers (1080p Broadcast Full-Screen)
# ---------------------------------------------------------------------------
def cubic_bezier(
    p0: Tuple[float, float],
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
    t: float,
) -> Tuple[float, float]:
    u = 1.0 - t
    x = (u**3) * p0[0] + 3 * (u**2) * t * p1[0] + 3 * u * (t**2) * p2[0] + (t**3) * p3[0]
    y = (u**3) * p0[1] + 3 * (u**2) * t * p1[1] + 3 * u * (t**2) * p2[1] + (t**3) * p3[1]
    return (x, y)


def render_cartography_flight_radar(
    progress: float,
    time_sec: float,
    width: int = 1920,
    height: int = 1080,
) -> np.ndarray:
    """Renders a 1080p full-screen archival cartography map of Puget Sound with vector flight trajectory."""
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    canvas[:] = (26, 30, 36)

    # Pacific ocean & coastal shelf
    ocean_poly = np.array([
        [0, 0],
        [int(0.24 * width), 0],
        [int(0.22 * width), int(0.18 * height)],
        [int(0.20 * width), int(0.32 * height)],
        [int(0.22 * width), int(0.46 * height)],
        [int(0.19 * width), int(0.60 * height)],
        [int(0.18 * width), int(0.78 * height)],
        [int(0.16 * width), int(0.92 * height)],
        [int(0.15 * width), height],
        [0, height],
    ], np.int32)
    cv2.fillPoly(canvas, [ocean_poly], (34, 26, 20))

    # Puget Sound waterways
    puget_poly = np.array([
        [int(0.21 * width), int(0.12 * height)],
        [int(0.32 * width), int(0.11 * height)],
        [int(0.35 * width), int(0.18 * height)],
        [int(0.36 * width), int(0.26 * height)],
        [int(0.33 * width), int(0.31 * height)],
        [int(0.29 * width), int(0.28 * height)],
        [int(0.26 * width), int(0.20 * height)],
        [int(0.21 * width), int(0.18 * height)],
    ], np.int32)
    cv2.fillPoly(canvas, [puget_poly], (34, 26, 20))

    # Graticule grid
    grid = canvas.copy()
    for gx in range(120, width, 120):
        cv2.line(grid, (gx, 0), (gx, height), (75, 88, 102), 1, cv2.LINE_AA)
    for gy in range(90, height, 90):
        cv2.line(grid, (0, gy), (width, gy), (75, 88, 102), 1, cv2.LINE_AA)
    cv2.addWeighted(grid, 0.28, canvas, 0.72, 0, canvas)

    # Waypoints: Portland (PDX) to Seattle-Tacoma (SEA)
    pdx = (int(0.48 * width), int(0.72 * height))
    sea = (int(0.45 * width), int(0.24 * height))
    jump_zone = (int(0.47 * width), int(0.52 * height))

    p0 = pdx
    p1 = (int(0.47 * width), int(0.56 * height))
    p2 = (int(0.44 * width), int(0.38 * height))
    p3 = sea

    # Trajectory Spline
    num_samples = 140
    curve_points = [cubic_bezier(p0, p1, p2, p3, i / float(num_samples)) for i in range(num_samples + 1)]
    active_samples = int(progress * num_samples)
    dash_len, gap_len = 6, 5
    cycle = dash_len + gap_len

    glow_layer = np.zeros_like(canvas)
    for idx in range(active_samples):
        if (idx % cycle) < dash_len:
            pt1 = (int(curve_points[idx][0]), int(curve_points[idx][1]))
            pt2 = (int(curve_points[idx + 1][0]), int(curve_points[idx + 1][1]))
            cv2.line(glow_layer, pt1, pt2, (0, 180, 255), 6, cv2.LINE_AA)
            cv2.line(canvas, pt1, pt2, (255, 255, 255), 3, cv2.LINE_AA)

    cv2.addWeighted(glow_layer, 0.50, canvas, 1.0, 0, canvas)

    # Radar sweep pulses
    pulse_r = 6 + int((time_sec * 30) % 60)
    pulse_a = max(0.0, 1.0 - (pulse_r / 60.0))
    cv2.circle(canvas, pdx, pulse_r, (0, int(200 * pulse_a), int(255 * pulse_a)), 2, cv2.LINE_AA)
    cv2.circle(canvas, pdx, 7, (0, 215, 255), -1, cv2.LINE_AA)
    cv2.circle(canvas, sea, 7, (0, 215, 255), -1, cv2.LINE_AA)

    cv2.putText(canvas, "PORTLAND INTL AIRPORT (PDX)", (pdx[0] + 16, pdx[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (240, 240, 245), 2, cv2.LINE_AA)
    cv2.putText(canvas, "ORIGIN: 14:36 PST  •  B-727 NW ORIENT", (pdx[0] + 16, pdx[1] + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (190, 180, 160), 1, cv2.LINE_AA)

    cv2.putText(canvas, "SEATTLE-TACOMA INTL (SEA)", (sea[0] + 16, sea[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (240, 240, 245), 2, cv2.LINE_AA)
    cv2.putText(canvas, "DESTINATION: 17:45 PST  •  36 HOSTAGES", (sea[0] + 16, sea[1] + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (190, 180, 160), 1, cv2.LINE_AA)

    cv2.circle(canvas, jump_zone, 10, (40, 40, 220), 2, cv2.LINE_AA)
    cv2.putText(canvas, "ESTIMATED JUMP COORDINATES", (jump_zone[0] + 16, jump_zone[1] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (70, 70, 255), 2, cv2.LINE_AA)
    cv2.putText(canvas, "LEWIS RIVER / ARIEL, WA  •  8:13 PM", (jump_zone[0] + 16, jump_zone[1] + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (180, 180, 180), 1, cv2.LINE_AA)

    return canvas


def render_cockpit_flight_instruments(time_sec: float, width: int = 1920, height: int = 1080) -> np.ndarray:
    """Renders 1080p full-screen cockpit instrument telemetry with rotating Altimeter needle and Airspeed dial."""
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    canvas[:] = (20, 22, 26)

    cv2.rectangle(canvas, (180, 120), (width - 180, height - 120), (32, 35, 42), -1)
    cv2.rectangle(canvas, (180, 120), (width - 180, height - 120), (70, 78, 92), 2)

    # Gauge 1: Altimeter
    c1 = (int(width * 0.35), int(height * 0.48))
    r = 170
    cv2.circle(canvas, c1, r, (15, 16, 20), -1)
    cv2.circle(canvas, c1, r, (214, 180, 100), 3, cv2.LINE_AA)
    cv2.circle(canvas, c1, r - 12, (55, 62, 75), 1, cv2.LINE_AA)

    for deg in range(0, 360, 30):
        rad = math.radians(deg)
        x_in = int(c1[0] + (r - 24) * math.cos(rad))
        y_in = int(c1[1] + (r - 24) * math.sin(rad))
        x_out = int(c1[0] + (r - 8) * math.cos(rad))
        y_out = int(c1[1] + (r - 8) * math.sin(rad))
        cv2.line(canvas, (x_in, y_in), (x_out, y_out), (220, 220, 225), 2, cv2.LINE_AA)

    alt_angle = -90.0 + math.sin(time_sec * 8.0) * 1.5
    rad_alt = math.radians(alt_angle)
    nx = int(c1[0] + (r - 35) * math.cos(rad_alt))
    ny = int(c1[1] + (r - 35) * math.sin(rad_alt))
    cv2.line(canvas, c1, (nx, ny), (40, 50, 235), 4, cv2.LINE_AA)
    cv2.circle(canvas, c1, 12, (214, 180, 100), -1)

    cv2.putText(canvas, "ALTIMETER", (c1[0] - 65, c1[1] + 65), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (214, 180, 100), 2, cv2.LINE_AA)
    cv2.putText(canvas, "10,000 FT", (c1[0] - 55, c1[1] + 95), cv2.FONT_HERSHEY_SIMPLEX, 0.70, (255, 255, 255), 2, cv2.LINE_AA)

    # Gauge 2: Airspeed Indicator
    c2 = (int(width * 0.65), int(height * 0.48))
    cv2.circle(canvas, c2, r, (15, 16, 20), -1)
    cv2.circle(canvas, c2, r, (214, 180, 100), 3, cv2.LINE_AA)
    cv2.circle(canvas, c2, r - 12, (55, 62, 75), 1, cv2.LINE_AA)

    for deg in range(0, 360, 30):
        rad = math.radians(deg)
        x_in = int(c2[0] + (r - 24) * math.cos(rad))
        y_in = int(c2[1] + (r - 24) * math.sin(rad))
        x_out = int(c2[0] + (r - 8) * math.cos(rad))
        y_out = int(c2[1] + (r - 8) * math.sin(rad))
        cv2.line(canvas, (x_in, y_in), (x_out, y_out), (220, 220, 225), 2, cv2.LINE_AA)

    spd_angle = 35.0 + math.sin(time_sec * 6.5) * 1.8
    rad_spd = math.radians(spd_angle)
    sx = int(c2[0] + (r - 35) * math.cos(rad_spd))
    sy = int(c2[1] + (r - 35) * math.sin(rad_spd))
    cv2.line(canvas, c2, (sx, sy), (40, 50, 235), 4, cv2.LINE_AA)
    cv2.circle(canvas, c2, 12, (214, 180, 100), -1)

    cv2.putText(canvas, "AIRSPEED", (c2[0] - 60, c2[1] + 65), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (214, 180, 100), 2, cv2.LINE_AA)
    cv2.putText(canvas, "170 KNOTS", (c2[0] - 65, c2[1] + 95), cv2.FONT_HERSHEY_SIMPLEX, 0.70, (255, 255, 255), 2, cv2.LINE_AA)

    cx = width // 2
    cv2.putText(canvas, "FLAPS: LOCKED AT 15°", (cx - 150, int(height * 0.38)), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (240, 240, 245), 2, cv2.LINE_AA)
    cv2.putText(canvas, "CABIN: UNPRESSURIZED", (cx - 160, int(height * 0.55)), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (50, 50, 235), 2, cv2.LINE_AA)
    cv2.putText(canvas, "GEAR: DOWN & LOCKED", (cx - 150, int(height * 0.70)), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (80, 220, 120), 2, cv2.LINE_AA)

    return canvas


# ---------------------------------------------------------------------------
# Dynamic Spatial Virtual Camera Trajectory Calculator
# ---------------------------------------------------------------------------
def get_forensic_camera_trajectory(
    scene_id: str,
    t_sec: float,
    dur: float,
    trigger_time: float,
    width: int = 1920,
    height: int = 1080,
) -> Tuple[float, float, float, float]:
    """Calculates smooth cinematic camera viewport coordinates (cx, cy, zoom, angle_deg)."""
    t_norm = min(1.0, max(0.0, t_sec / dur))

    if scene_id == "s01":
        # Follow airplane vector route along Puget Sound
        pdx = (int(0.48 * width), int(0.72 * height))
        sea = (int(0.45 * width), int(0.24 * height))
        p0, p1, p2, p3 = pdx, (int(0.47 * width), int(0.56 * height)), (int(0.44 * width), int(0.38 * height)), sea
        plane_t = min(0.95, max(0.05, t_sec / (dur * 0.85)))
        pos = cubic_bezier(p0, p1, p2, p3, plane_t)
        cx = float(pos[0])
        cy = float(pos[1])
        zoom = 1.32 + math.sin(t_norm * math.pi) * 0.05
        rot = math.sin(t_norm * math.pi * 2.0) * 0.5
        return cx, cy, zoom, rot

    elif scene_id == "s06":
        # Cockpit flight specs to Altimeter & Airspeed dials
        if t_sec < trigger_time:
            s = smoothstep(0.0, trigger_time, t_sec)
            return 960.0 - s * 140.0, 540.0, 1.25 + s * 0.05, -0.5
        elif t_sec < trigger_time + 1.8:
            s = smoothstep(trigger_time, trigger_time + 1.8, t_sec)
            cx = 820.0 + (1250.0 - 820.0) * s
            cy = 540.0 + (520.0 - 540.0) * s
            zoom = 1.30 + (1.42 - 1.30) * s
            rot = -0.5 + 1.2 * s
            return cx, cy, zoom, rot
        else:
            return 1250.0, 520.0, 1.40, 0.6

    else:
        # Standard Scenes:
        # Phase 1: Zone A (Memo & Headline Document) on Left (cx ≈ 580, cy ≈ 520, zoom ≈ 1.32)
        # Phase 2: Dynamic Glide across the investigative board to Zone B (Evidence Cutout on Right)
        # Phase 3: Pull back slightly near end to reveal the complete connected board
        t_glide_start = max(1.5, trigger_time - 0.4)
        t_glide_end = min(dur - 1.2, t_glide_start + 1.8)

        if t_sec < t_glide_start:
            s = smoothstep(0.0, t_glide_start, t_sec)
            cx = 560.0 + s * 25.0
            cy = 520.0 - s * 15.0
            zoom = 1.30 + s * 0.04
            rot = -0.8 + s * 0.2
            return cx, cy, zoom, rot
        elif t_sec < t_glide_end:
            s = smoothstep(t_glide_start, t_glide_end, t_sec)
            cx = 585.0 + (1360.0 - 585.0) * s
            cy = 505.0 + (500.0 - 505.0) * s
            zoom = 1.34 + (1.46 - 1.34) * s
            rot = -0.6 + (0.8 - (-0.6)) * s
            return cx, cy, zoom, rot
        else:
            rem = dur - t_sec
            if rem < 1.0:
                s_out = smoothstep(1.0, 0.0, rem)
                cx = 1360.0 - (1360.0 - 960.0) * s_out
                cy = 500.0 + (540.0 - 500.0) * s_out
                zoom = 1.46 - (1.46 - 1.15) * s_out
                rot = 0.8 - 0.8 * s_out
                return cx, cy, zoom, rot
            else:
                return 1360.0, 500.0, 1.46, 0.8


# ---------------------------------------------------------------------------
# Base Scene Compositor (Builds Wide Forensic Canvas Without Telemetry HUD)
# ---------------------------------------------------------------------------
def build_forensic_scene_frame(
    scene: StoryScene,
    scene_idx: int,
    images_dir: Path,
    cutouts_dir: Path,
    t_sec: float,
    dur: float,
    hl_progress: float = 0.0,
    width: int = 1920,
    height: int = 1080,
) -> np.ndarray:
    """Assembles a full-screen 1080p broadcast composite canvas before camera transformation."""
    if scene.scene_id == "s01":
        bg = render_cartography_flight_radar(min(1.0, t_sec / (dur * 0.85)), t_sec, width, height)
    elif scene.scene_id == "s06":
        bg = render_cockpit_flight_instruments(t_sec, width, height)
    else:
        hero_p = images_dir / scene.hero_image
        if not hero_p.exists():
            hero_p = Path("scratch/test_flux.png")

        if hero_p.exists():
            src_hero = cv2.imread(str(hero_p))
            if src_hero is not None:
                if src_hero.shape[:2] != (height, width):
                    src_hero = cv2.resize(src_hero, (width, height), interpolation=cv2.INTER_LANCZOS4)
                t_norm = min(1.0, max(0.0, t_sec / dur))
                zoom = 1.00 + 0.05 * t_norm
                pan_x = math.sin(t_norm * math.pi) * 20.0
                pan_y = -t_norm * 14.0

                M = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), 0.0, zoom)
                M[0, 2] += pan_x
                M[1, 2] += pan_y
                bg = cv2.warpAffine(src_hero, M, (width, height), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT_101)

                y_idx, x_idx = np.ogrid[:height, :width]
                dist_from_c = np.sqrt((x_idx - width / 2.0) ** 2 + (y_idx - height / 2.0) ** 2)
                max_d = np.sqrt((width / 2.0) ** 2 + (height / 2.0) ** 2)
                vig = np.clip(1.0 - 0.45 * (dist_from_c / max_d) ** 1.8, 0.40, 1.0)[..., None]
                bg = np.clip(bg.astype(np.float32) * vig, 0, 255).astype(np.uint8)
            else:
                bg = np.full((height, width, 3), (24, 26, 32), dtype=np.uint8)
        else:
            bg = np.full((height, width, 3), (24, 26, 32), dtype=np.uint8)

    # Zone B: Composite Hero Evidence Card on Right (cx: 1360, cy: 500)
    cutout_p = cutouts_dir / scene.cutout_image
    if cutout_p.exists():
        cutout_bgr = cv2.imread(str(cutout_p))
        if cutout_bgr is not None:
            c_w, c_h = 580, 440
            cutout_res = cv2.resize(cutout_bgr, (c_w, c_h))
            framed_card = np.full((c_h + 60, c_w + 34, 3), (245, 248, 252), dtype=np.uint8)
            framed_card[16:16 + c_h, 17:17 + c_w] = cutout_res

            cv2.putText(
                framed_card,
                scene.exhibit_code[:34].upper(),
                (20, c_h + 44),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.46,
                (35, 45, 60),
                1,
                cv2.LINE_AA,
            )

            settle = min(1.0, t_sec / 0.8)
            card_cx = int(width * 0.72)
            card_cy = int(height * 0.50 - (1.0 - settle) * 35.0)
            card_ang = -2.2 + settle * 0.5

            bg = composite_evidence_card_with_shadow(bg, framed_card, card_cx, card_cy, angle_deg=card_ang, shadow_blur=30, shadow_alpha=0.62)
            bg = draw_frosted_scotch_tape(bg, card_cx - (c_w // 2) + 24, card_cy - (c_h // 2) + 10, width=85, height=26, angle_deg=-26.0)
            bg = draw_brass_pushpin(bg, card_cx + (c_w // 2) - 18, card_cy - (c_h // 2) + 14, radius=13)

    # Zone A: Narrative Headline Box on Left (cx: 560, cy: 520)
    memo_w, memo_h = 620, 240
    memo_cx = int(width * 0.28)
    memo_cy = int(height * 0.50)
    memo = np.full((memo_h, memo_w, 3), (248, 250, 252), dtype=np.uint8)
    cv2.rectangle(memo, (2, 2), (memo_w - 2, memo_h - 2), (160, 175, 190), 1)

    cv2.putText(memo, f"NORTHWEST ORIENT ARCHIVE  •  {scene.act.upper()}", (20, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (90, 100, 115), 1, cv2.LINE_AA)
    cv2.putText(memo, scene.title[:32], (20, 68), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (20, 25, 35), 2, cv2.LINE_AA)
    cv2.line(memo, (20, 84), (memo_w - 20, 84), (200, 210, 220), 1)

    words_list = scene.text.split()
    line1 = " ".join(words_list[:8])
    line2 = " ".join(words_list[8:16])
    line3 = " ".join(words_list[16:24]) if len(words_list) > 16 else ""

    cv2.putText(memo, line1, (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (40, 48, 60), 1, cv2.LINE_AA)
    cv2.putText(memo, line2, (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (40, 48, 60), 1, cv2.LINE_AA)
    if line3:
        cv2.putText(memo, line3, (20, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (40, 48, 60), 1, cv2.LINE_AA)

    cv2.putText(memo, f"EVIDENCE FILE: {scene.exhibit_code}", (20, 215), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (120, 40, 40), 1, cv2.LINE_AA)

    bg = composite_evidence_card_with_shadow(bg, memo, memo_cx, memo_cy, angle_deg=1.8, shadow_blur=26, shadow_alpha=0.58)
    bg = draw_brass_pushpin(bg, memo_cx - (memo_w // 2) + 20, memo_cy - (memo_h // 2) + 18, radius=13)

    if hl_progress > 0.0:
        hl_x = memo_cx - (memo_w // 2) + 16
        hl_y = memo_cy - (memo_h // 2) + 132
        bg = draw_highlighter_bar(bg, hl_x, hl_y, int(memo_w * 0.85), 28, hl_progress)

    if t_sec >= 1.2 and scene.stamp_text:
        stamp_ang = -14.0 + math.sin(scene_idx * 1.5) * 4.0
        bg = draw_rubber_stamp(bg, scene.stamp_text, memo_cx + 180, memo_cy + 40, angle_deg=stamp_ang)

    return bg


# ---------------------------------------------------------------------------
# Dynamic 30FPS Scene Video Clip Generator (With Connected Virtual Camera)
# ---------------------------------------------------------------------------
def render_forensic_scene_clip(
    scene: StoryScene,
    scene_idx: int,
    images_dir: Path,
    cutouts_dir: Path,
    dur: float,
    words: List[Dict[str, Any]],
    output_mp4: Path,
    fps: int = 30,
) -> Path:
    """Renders a dynamic 30fps full-screen scene clip with connected spatial camera motion."""
    total_frames = int(dur * fps)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    tmp_raw = output_mp4.with_suffix(".raw.mp4")
    out = cv2.VideoWriter(str(tmp_raw), fourcc, fps, (WIDTH, HEIGHT))

    # Resolve highlighter trigger timestamp
    hl_time = 0.6
    if scene.highlighter_phrase:
        hl_target = scene.highlighter_phrase.lower().split()[0].strip(".,!?\"'")
        for w in words:
            if hl_target in w["word"].lower():
                hl_time = w["start"]
                break

    # Resolve secondary exhibit trigger timestamp
    sec_trigger_time = dur * 0.45
    if scene.secondary_trigger_word:
        trig = scene.secondary_trigger_word.lower().strip(".,!?\"'")
        for w in words:
            if trig in w["word"].lower() or ("20" in w["word"] and trig == "ticket"):
                sec_trigger_time = w["start"]
                break

    for f in range(total_frames):
        t_sec = f / float(fps)
        hl_progress = max(0.0, min(1.0, (t_sec - hl_time) / 0.35)) if t_sec >= hl_time else 0.0

        # 1. Build base wide canvas
        canvas = build_forensic_scene_frame(
            scene=scene,
            scene_idx=scene_idx,
            images_dir=images_dir,
            cutouts_dir=cutouts_dir,
            t_sec=t_sec,
            dur=dur,
            hl_progress=hl_progress,
            width=WIDTH,
            height=HEIGHT,
        )

        # 2. Calculate dynamic camera trajectory
        cam_cx, cam_cy, zoom, rot = get_forensic_camera_trajectory(
            scene_id=scene.scene_id,
            t_sec=t_sec,
            dur=dur,
            trigger_time=sec_trigger_time,
            width=WIDTH,
            height=HEIGHT,
        )

        # 3. Transform canvas through virtual camera viewport
        viewport = render_camera_viewport(canvas, cam_cx, cam_cy, zoom, rot, WIDTH, HEIGHT)

        # 4. Render stable telemetry HUD on top of viewport
        final_frame = draw_top_bottom_telemetry_hud(viewport, scene, scene_idx, total_scenes=len(DB_COOPER_FORENSIC_SERIES))

        out.write(final_frame)

    out.release()

    cmd = [
        "ffmpeg", "-y", "-i", str(tmp_raw),
        "-c:v", "h264_videotoolbox",
        "-b:v", "14M",
        "-pix_fmt", "yuv420p",
        str(output_mp4),
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    tmp_raw.unlink(missing_ok=True)

    return output_mp4


# ---------------------------------------------------------------------------
# Audio Synthesis & Multi-Layer Forensic Mixing (Local Kokoro-82M ONNX)
# ---------------------------------------------------------------------------
def synthesize_noir_narration(
    scenes: List[StoryScene],
    cache_dir: Path,
) -> Tuple[List[Path], List[float], List[List[Dict[str, Any]]]]:
    """Synthesizes humanized documentary noir narration using local Kokoro-82M ONNX."""
    import kokoro_onnx
    from faster_whisper import WhisperModel

    kokoro = kokoro_onnx.Kokoro(str(KOKORO_MODEL), str(KOKORO_VOICES))
    voice_george = kokoro.get_voice_style("bm_george")
    voice_michael = kokoro.get_voice_style("am_michael")
    doc_voice = 0.65 * voice_george + 0.35 * voice_michael

    whisper_model = WhisperModel("base", device="cpu", compute_type="int8")

    scene_audio_files: List[Path] = []
    scene_durations: List[float] = []
    scene_words: List[List[Dict[str, Any]]] = []

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
        clean_text = sc.text.replace("*", "")
        wav_path = cache_dir / f"forensic_{sc.scene_id}.wav"
        raw_tmp = cache_dir / f"raw_forensic_{sc.scene_id}.wav"

        needs_build = True
        if wav_path.exists():
            try:
                with wave.open(str(wav_path), "rb") as cur_wf:
                    if cur_wf.getframerate() == 48000 and cur_wf.getnchannels() == 2:
                        needs_build = False
            except Exception:
                needs_build = True

        if needs_build:
            chunks = sc.speech_chunks
            if chunks:
                all_samples = []
                last_sr = 24000
                for chunk_text, spd, pause_after in chunks:
                    s_chunk, sr = kokoro.create(chunk_text, voice=doc_voice, speed=spd)
                    all_samples.append(s_chunk)
                    last_sr = sr
                    if pause_after > 0.0:
                        all_samples.append(np.zeros(int(pause_after * sr), dtype=np.float32))
                samples = np.concatenate(all_samples)
                sr = last_sr
            else:
                samples, sr = kokoro.create(clean_text, voice=doc_voice, speed=0.90)

            with wave.open(str(raw_tmp), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sr)
                audio_int16 = (samples * 32767.0).clip(-32768, 32767).astype(np.int16)
                wf.writeframes(audio_int16.tobytes())

            cmd = [
                "ffmpeg", "-y", "-i", str(raw_tmp),
                "-af", eq_filter,
                "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le",
                str(wav_path)
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            raw_tmp.unlink(missing_ok=True)

        with wave.open(str(wav_path), "rb") as wf:
            dur = wf.getnframes() / float(wf.getframerate())

        json_path = wav_path.with_suffix(".json")
        words: List[Dict[str, Any]] = []
        if json_path.exists():
            try:
                with open(json_path, "r") as f:
                    words = json.load(f)
            except Exception:
                pass

        if not words:
            segments, _ = whisper_model.transcribe(str(wav_path), word_timestamps=True)
            for s in segments:
                for w in s.words:
                    words.append({"word": w.word.strip(), "start": round(w.start, 2), "end": round(w.end, 2)})
            with open(json_path, "w") as f:
                json.dump(words, f, indent=2)

        scene_audio_files.append(wav_path)
        scene_durations.append(round(dur + 0.30, 2))
        scene_words.append(words)
        logger.info(f"  [{sc.scene_id}] {dur:.2f}s narration ({len(words)} words) -> scene {scene_durations[-1]:.2f}s")

    return scene_audio_files, scene_durations, scene_words


# ---------------------------------------------------------------------------
# End-to-End Forensic Production Orchestrator
# ---------------------------------------------------------------------------
def produce_forensic_documentary(
    project_slug: str = "long_01_db_cooper_1971",
    output_mp4_override: Optional[Path] = None,
) -> Path:
    """Renders the complete 18-scene LEMMiNO-tier forensic documentary video."""
    project_dir = REPO_ROOT / "projects" / project_slug
    images_dir = project_dir / "images"
    cutouts_dir = images_dir / "cutouts"
    videos_dir = project_dir / "videos"
    cache_dir = project_dir / "cache"
    output_dir = REPO_ROOT / "output"

    for d in [videos_dir, cache_dir, output_dir]:
        d.mkdir(parents=True, exist_ok=True)

    if output_mp4_override:
        output_mp4 = output_mp4_override
    else:
        output_mp4 = output_dir / f"{project_slug}_forensic_casebook_16x9.mp4"

    logger.info("=== STEP 1: KOKORO-82M NEURAL NARRATION SYNTHESIS & NOIR CHUNKING ===")
    scene_audios, scene_durs, scene_words = synthesize_noir_narration(
        DB_COOPER_FORENSIC_SERIES, cache_dir
    )

    logger.info("=== STEP 2: RENDERING 30FPS CONNECTED SPATIAL CAMERA VIDEO CLIPS ===")
    raw_clips: List[Path] = []
    for idx, sc in enumerate(DB_COOPER_FORENSIC_SERIES):
        clip_p = videos_dir / f"forensic_{sc.scene_id}.mp4"
        dur = scene_durs[idx]
        words = scene_words[idx]

        render_forensic_scene_clip(
            scene=sc,
            scene_idx=idx,
            images_dir=images_dir,
            cutouts_dir=cutouts_dir,
            dur=dur,
            words=words,
            output_mp4=clip_p,
            fps=30,
        )
        raw_clips.append(clip_p)
        logger.info(f"  ✓ Rendered connected spatial clip {clip_p.name} ({dur:.2f}s)")

    logger.info("=== STEP 3: CINEMATIC DISSOLVE TRANSITIONS TIMELINE STITCH ===")
    filter_parts = []
    cur_v = "[0:v]"
    cur_offset = 0.0
    trans_dur = 0.50

    for i in range(len(raw_clips) - 1):
        dur_a = scene_durs[i]
        cur_offset += dur_a - trans_dur
        next_v = f"[{i+1}:v]"
        out_v = f"[v{i+1}]"
        filter_parts.append(f"{cur_v}{next_v}xfade=transition=dissolve:duration={trans_dur}:offset={cur_offset:.2f}{out_v}")
        cur_v = out_v

    full_filter = ";".join(filter_parts)
    visual_timeline = cache_dir / "visual_timeline_forensic.mp4"

    cmd_stitch = ["ffmpeg", "-y"]
    for rc in raw_clips:
        cmd_stitch.extend(["-i", str(rc)])
    cmd_stitch.extend([
        "-filter_complex", full_filter,
        "-map", cur_v,
        "-c:v", "h264_videotoolbox",
        "-b:v", "14M",
        "-pix_fmt", "yuv420p",
        str(visual_timeline),
    ])
    subprocess.run(cmd_stitch, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    logger.info(f"Visual Timeline Assembled: {visual_timeline}")

    logger.info("=== STEP 4: FRAME-ACCURATE STEREO FOLEY SFX MIXING & TWO-ACT SOUNDTRACK ===")
    concat_list = cache_dir / "narration_forensic_list.txt"
    with open(concat_list, "w") as f:
        for sa in scene_audios:
            f.write(f"file '{sa.resolve()}'\n")

    master_voice = cache_dir / "master_voice_forensic.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(master_voice)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
    )

    total_voice_dur = sum(scene_durs) - (len(scene_durs) - 1) * trans_dur

    # Frame-Accurate Word-Level SFX Synchronization with Stereo Panning
    master_sfx = cache_dir / "master_sfx_forensic.wav"
    sfx_inputs = []
    amix_filters = []
    sfx_count = 0
    cur_scene_time = 0.0

    for idx, sc in enumerate(DB_COOPER_FORENSIC_SERIES):
        words = scene_words[idx]
        wav_path = scene_audios[idx]
        scene_pauses = detect_speech_pauses(wav_path)

        for cue in sc.sound_cues:
            sfx_f = SFX_DIR / f"{cue['name']}.mp3"
            if not sfx_f.exists():
                sfx_f = SFX_DIR / f"{cue['name']}.wav"
            if sfx_f.exists():
                target_word = cue.get("word_trigger", "").lower().strip(".,!?\"'")
                word_offset = None
                if target_word:
                    for w in words:
                        w_clean = w["word"].lower().strip(".,!?\"'")
                        if target_word in w_clean or w_clean in target_word:
                            word_offset = w["start"]
                            break
                        if target_word == "twenty" and ("20" in w["word"] or "$20" in w["word"]):
                            word_offset = w["start"]
                            break

                raw_offset = word_offset if word_offset is not None else cue.get("offset", 0.5)

                cue_db = get_cue_decibel(cue["name"])
                is_climax = cue_db >= DECIBEL_BUDGET["climax_blast"] - 0.5
                if is_climax:
                    snapped_offset = snap_cue_to_breath_pause(raw_offset, scene_pauses, search_window_sec=1.0)
                else:
                    snapped_offset = raw_offset

                offset = cur_scene_time + snapped_offset
                vol = get_cue_linear_gain(cue["name"])
                sfx_inputs.extend(["-i", str(sfx_f)])
                delay_ms = int(offset * 1000)

                pan_zone = cue.get("pan", "center")
                if pan_zone == "left":
                    pan_filter = "pan=stereo|c0=0.75*c0|c1=0.25*c0"
                elif pan_zone == "right":
                    pan_filter = "pan=stereo|c0=0.25*c0|c1=0.75*c0"
                else:
                    pan_filter = "volume=1.0"

                amix_filters.append(f"[{sfx_count+1}:a]adelay={delay_ms}|{delay_ms},{pan_filter},volume={vol}[sfx{sfx_count}]")
                sfx_count += 1

        cur_scene_time += scene_durs[idx] - trans_dur

    if sfx_count > 0:
        sfx_mix_filter = ";".join(amix_filters) + ";" + "".join(f"[sfx{i}]" for i in range(sfx_count)) + f"amix=inputs={sfx_count}:normalize=0[sfx_out]"
        cmd_sfx = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo:d={total_voice_dur:.2f}"]
        cmd_sfx.extend(sfx_inputs)
        cmd_sfx.extend(["-filter_complex", sfx_mix_filter, "-map", "[sfx_out]", "-c:a", "pcm_s16le", str(master_sfx)])
        subprocess.run(cmd_sfx, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    else:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo:d={total_voice_dur:.2f}", "-c:a", "pcm_s16le", str(master_sfx)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
        )

    # Two-Act Dynamic Mystery & Thriller Soundtrack
    full_bgm_wav = cache_dir / "master_bgm_crossfade.wav"
    if BGM_FILE_1.exists() and BGM_FILE_2.exists():
        cmd_bgm = [
            "ffmpeg", "-y",
            "-i", str(BGM_FILE_1),
            "-i", str(BGM_FILE_2),
            "-filter_complex",
            "[0:a]atrim=0:140,asetpts=PTS-STARTPTS[a1];[1:a]atrim=0:150,asetpts=PTS-STARTPTS[a2];[a1][a2]acrossfade=d=8:c1=tri:c2=tri[bgm_full]",
            "-map", "[bgm_full]",
            "-t", f"{total_voice_dur:.2f}",
            "-c:a", "pcm_s16le",
            str(full_bgm_wav),
        ]
        subprocess.run(cmd_bgm, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    elif BGM_FILE_1.exists():
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(BGM_FILE_1), "-t", f"{total_voice_dur:.2f}", "-c:a", "pcm_s16le", str(full_bgm_wav)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
        )

    # Master Audio Mix with Vocal Mid-Side Ducking
    mixed_audio = cache_dir / "mixed_audio_forensic.wav"
    if full_bgm_wav.exists():
        audio_filter = (
            "[0:a]volume=1.0[voice];"
            "[1:a]volume=1.0[sfx];"
            "[2:a]volume=0.18[bgm];"
            "[voice][bgm]sidechaincompress=threshold=0.08:ratio=3.5:attack=20:release=350[ducked_bgm];"
            "[voice][sfx][ducked_bgm]amix=inputs=3:normalize=0[mixed]"
        )
        cmd_mix = [
            "ffmpeg", "-y",
            "-i", str(master_voice),
            "-i", str(master_sfx),
            "-i", str(full_bgm_wav),
            "-filter_complex", audio_filter,
            "-map", "[mixed]",
            "-t", f"{total_voice_dur:.2f}",
            str(mixed_audio),
        ]
    else:
        cmd_mix = [
            "ffmpeg", "-y",
            "-i", str(master_voice),
            "-i", str(master_sfx),
            "-filter_complex", "[0:a][1:a]amix=inputs=2:normalize=0[mixed]",
            "-map", "[mixed]",
            "-t", f"{total_voice_dur:.2f}",
            str(mixed_audio),
        ]
    subprocess.run(cmd_mix, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    logger.info("=== STEP 5: FINAL BROADCAST MUX & LOUDNORM (-14.0 LUFS) ===")
    cmd_mux = [
        "ffmpeg", "-y",
        "-i", str(visual_timeline),
        "-i", str(mixed_audio),
        "-c:v", "copy",
        "-af", "loudnorm=I=-14.0:TP=-1.5:LRA=7.0",
        "-c:a", "aac",
        "-b:a", "320k",
        "-ar", "48000",
        "-shortest",
        str(output_mp4),
    ]
    subprocess.run(cmd_mux, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    cmd_probe = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration,size,bit_rate:stream=width,height,codec_name,sample_rate",
        "-of", "json",
        str(output_mp4),
    ]
    probe_res = subprocess.run(cmd_probe, capture_output=True, text=True, check=True)
    probe_data = json.loads(probe_res.stdout)
    fmt = probe_data.get("format", {})
    dur_final = float(fmt.get("duration", 0.0))
    size_mb = float(fmt.get("size", 0.0)) / (1024 * 1024)

    logger.info(f"✓ Master Forensic Video Rendered: {output_mp4}")
    logger.info(f"  Duration: {dur_final:.2f}s ({dur_final / 60:.2f} mins) | Size: {size_mb:.2f} MB")

    record_ledger_event(
        slug=project_slug,
        stage="render",
        status="PASS",
        details={
            "video_id": "LV-01",
            "title": "The Skyjacker Who Vanished at 10,000 Feet: The True Story of D.B. Cooper",
            "topic": "D.B. Cooper Skyjacking (18-Scene Connected Spatial Casebook)",
            "output_file": str(output_mp4),
            "scenes": len(DB_COOPER_FORENSIC_SERIES),
            "notes": f"Connected Spatial Camera & Stereo Foley Engine; 18 scenes; duration: {dur_final:.1f}s; {size_mb:.1f} MB; -14 LUFS",
        },
        evidence={"duration": dur_final, "size_mb": size_mb, "lufs": -14.0},
    )

    return output_mp4


def main() -> None:
    parser = argparse.ArgumentParser(description="Forensic Casebook Video Engine")
    parser.add_argument("--slug", default="long_01_db_cooper_1971", help="Project slug")
    parser.add_argument("--output", type=Path, default=None, help="Output MP4 path")
    args = parser.parse_args()

    produce_forensic_documentary(project_slug=args.slug, output_mp4_override=args.output)


if __name__ == "__main__":
    main()
