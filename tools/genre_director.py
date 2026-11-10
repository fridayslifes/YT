#!/usr/bin/env python3
"""FrameForge Multi-Genre Visual Director & 3D Style Engine (v5.1 — Humanized Documentary Edition).

Defines 5 SOTA humanized visual genres with specialized prompt architectures, 3D camera physics,
color grading, BGM profiles, and subtitle aesthetics:

  1. 3d_cgi / unreal_octane     : Tactile 3D spatial documentary, natural subsurface skin warmth, physical materials.
  2. 3d_minimalist / spatial    : Editorial minimalist studio lighting, warm wood/glass textures, calm human presence.
  3. kinetic_explainer          : Tactile investigative research table, handwritten notes, warm brass lamp, human hands.
  4. cyberpunk_neon             : Late-night urban documentary noir, rain-streaked glass, neon & warm streetlight on skin.
  5. cinematic_35mm             : Candid 35mm documentary photography, Kodak Portra 400 skin tones, natural eye contact.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class GenreProfile:
    id: str
    name: str
    description: str
    prompt_prefix: str
    prompt_suffix: str
    negative_prompt: str
    default_3d_preset: str
    recommended_presets: List[str]
    color_palette: Dict[str, str]
    bgm_mood: str


GENRE_REGISTRY: Dict[str, GenreProfile] = {
    # ------------------------------------------------------------------------- #
    # 1. 3D CGI / Tactile Humanized Spatial Visuals
    # ------------------------------------------------------------------------- #
    "3d_cgi": GenreProfile(
        id="3d_cgi",
        name="3D Tactile Spatial Documentary (Humanized PBR)",
        description="Warm tactile 3D spatial storytelling with natural subsurface skin warmth, physical materials, and depth.",
        prompt_prefix="Humanized 3D spatial documentary frame, tactile physical materials, natural subsurface skin warmth, ",
        prompt_suffix=(
            "expressive human micro-expressions, warm tungsten and soft cyan rim lighting, natural depth of field, "
            "lived-in architectural textures, soft atmospheric dust motes, "
            "primary human subject centered vertically between 30% and 58% height, unobstructed face, "
            "9:16 vertical composition"
        ),
        negative_prompt="flat 2d, robotic HUD circles on face, target reticle on face, plastic skin, lifeless eyes, cartoon, blurry",
        default_3d_preset="depthflow_spiral",
        recommended_presets=["depthflow_spiral", "depthflow_orbit", "depthflow_vertigo", "depthflow_dolly"],
        color_palette={"primary": "#00E5FF", "secondary": "#7C4DFF", "accent": "#FFB300", "background": "#0B0E14"},
        bgm_mood="deep_ambient_synth",
    ),
    # ------------------------------------------------------------------------- #
    # 2. 3D Spatial Minimalist (Editorial Documentary / Aperture)
    # ------------------------------------------------------------------------- #
    "3d_minimalist": GenreProfile(
        id="3d_minimalist",
        name="3D Editorial Minimalist (Humanized Spatial)",
        description="Warm editorial studio lighting, tactile paper and glass textures, calm human presence.",
        prompt_prefix="Editorial minimalist documentary frame, warm studio architecture, tactile physical objects, ",
        prompt_suffix=(
            "soft diffused natural window light, subtle glass and warm wood textures, calm human posture, "
            "clean breathing room and negative space, focal subject centered between 32% and 56% frame height, "
            "shallow depth of field, unobstructed human expression, 9:16 vertical composition"
        ),
        negative_prompt="grungy, dirty, sci-fi HUD reticle, target circle on face, cluttered, plastic skin",
        default_3d_preset="depthflow_vertigo",
        recommended_presets=["depthflow_vertigo", "depthflow_orbit", "spatial_drift", "depthflow_dolly"],
        color_palette={"primary": "#FFFFFF", "secondary": "#E0E7FF", "accent": "#6366F1", "background": "#0A0D14"},
        bgm_mood="minimalist_electronic_piano",
    ),
    # ------------------------------------------------------------------------- #
    # 3. Kinetic 3D Explainer (Vox / Johnny Harris Editorial Style)
    # ------------------------------------------------------------------------- #
    "kinetic_explainer": GenreProfile(
        id="kinetic_explainer",
        name="Humanized Editorial Explainer (Vox & Johnny Harris Style)",
        description="Tactile archival research table, physical documents, warm desk lamp, and human hands.",
        prompt_prefix="Tactile investigative documentary explainer, warm archival desk setting, authentic human hands and posture, ",
        prompt_suffix=(
            "textured archival paper ledgers, warm brass desk lamp, natural directional shadows, "
            "clear visual storytelling metaphor, primary focal point centered vertically between 30% and 58% height, "
            "9:16 vertical composition"
        ),
        negative_prompt="sci-fi HUD, target circles on face, robotic wireframe, noisy, chaotic, illegible text",
        default_3d_preset="depthflow_orbit",
        recommended_presets=["depthflow_orbit", "depthflow_roll", "depthflow_horizontal", "depthflow_vertigo"],
        color_palette={"primary": "#FFBE0B", "secondary": "#FB5607", "accent": "#3A86FF", "background": "#141724"},
        bgm_mood="energetic_plucked_synth",
    ),
    # ------------------------------------------------------------------------- #
    # 4. Cyberpunk Neon (Humanized Late-Night Urban Noir)
    # ------------------------------------------------------------------------- #
    "cyberpunk_neon": GenreProfile(
        id="cyberpunk_neon",
        name="Late-Night Urban Documentary Noir (Neon & Rain)",
        description="Candid late-night city reflections, rain-streaked glass, expressive human face in neon glow.",
        prompt_prefix="Candid late-night urban documentary portrait, rain-streaked window reflections, ",
        prompt_suffix=(
            "warm amber streetlight and cool cyan city neon reflecting naturally on expressive human skin, "
            "shallow depth of field, creamy bokeh, authentic emotional micro-expression, unobstructed face, "
            "focal subject centered at 30% to 58% vertical height, 9:16 vertical composition"
        ),
        negative_prompt="sci-fi HUD circle on face, target reticle, cartoon, flat 2d, plastic skin",
        default_3d_preset="depthflow_roll",
        recommended_presets=["depthflow_roll", "depthflow_spiral", "depthflow_orbit", "depthflow_vertigo"],
        color_palette={"primary": "#00F0FF", "secondary": "#FF0055", "accent": "#FFE600", "background": "#05050A"},
        bgm_mood="cyberpunk_dark_synthwave",
    ),
    # ------------------------------------------------------------------------- #
    # 5. Cinematic 35mm Documentary (Cognitive Core Baseline)
    # ------------------------------------------------------------------------- #
    "cinematic_35mm": GenreProfile(
        id="cinematic_35mm",
        name="Cinematic 35mm Documentary (Humanized Portra 400)",
        description="Authentic 35mm film photography, Kodak Portra 400 skin tones, candid human emotion.",
        prompt_prefix="Candid 35mm documentary photograph, shot on Leica 35mm cinema lens, f/2.0 aperture, ",
        prompt_suffix=(
            "shallow depth of field, natural optical falloff, authentic warm human skin pores, candid micro-expression, "
            "organic 35mm film grain, Kodak Portra 400 and Vision3 500T color profile, warm practical tungsten and soft window light, "
            "primary human subject strictly centered vertically between 30% and 58% frame height, unobstructed face, "
            "clean headroom, natural posture, 9:16 vertical composition"
        ),
        negative_prompt="3D render, CGI, HUD circle on face, target reticle, plastic skin, anime, illustration, extra fingers, cartoon, blurry, watermark",
        default_3d_preset="depthflow_orbit",
        recommended_presets=["depthflow_orbit", "depthflow_dolly", "depthflow_horizontal", "depthflow_vertigo"],
        color_palette={"primary": "#FFC83D", "secondary": "#00E5FF", "accent": "#FF453A", "background": "#000000"},
        bgm_mood="warm_acoustic_ambient",
    ),
    # ------------------------------------------------------------------------- #
    # 6. Tactile Archival Detective Casebook (Johnny Harris & LEMMiNO Style)
    # ------------------------------------------------------------------------- #
    "storybook_casebook": GenreProfile(
        id="storybook_casebook",
        name="Tactile Archival Detective Casebook (Johnny Harris & LEMMiNO)",
        description="Physical desk spread, aged parchment paper, Polaroid/document cutouts with real drop shadows, scotch tape, and rubber stamps.",
        prompt_prefix="Tactile archival casebook plate, aged cream paper document, vintage physical evidence photograph, ",
        prompt_suffix=(
            "soft physical drop shadow onto aged parchment background, warm directional tungsten desk lamp illumination, "
            "tactile paper grain texture, authentic historical forensic detail, primary subject centered vertically between 30% and 58% height, "
            "35mm documentary depth of field"
        ),
        negative_prompt="digital CGI wallpaper, borderless full screen image, futuristic HUD, plastic skin, anime, illustration, blurry",
        default_3d_preset="depthflow_dolly",
        recommended_presets=["depthflow_dolly", "depthflow_horizontal", "spatial_drift", "depthflow_orbit"],
        color_palette={"primary": "#E6C280", "secondary": "#C85A32", "accent": "#D62828", "background": "#1A120B"},
        bgm_mood="tactile_casebook_mystery",
    ),
    # ------------------------------------------------------------------------- #
    # 7. Classic Illustrated Storybook & Lore (Bedtime Stories & Folklore Style)
    # ------------------------------------------------------------------------- #
    "storybook_classic": GenreProfile(
        id="storybook_classic",
        name="Classic Illustrated Storybook & Lore (Bedtime Stories & Folklore)",
        description="Rich leather-bound physical book spread with ornate gilded gold borders, warm textured linen paper, deckled edges, and spine gutter.",
        prompt_prefix="Classic illustrated storybook spread, ornate antique book page with gilded gold borders, rich textured linen paper, ",
        prompt_suffix=(
            "soft chiaroscuro bookplate lighting, warm candlelight glow, rich artisanal bookbinding details, "
            "primary subject centered vertically between 30% and 58% height, elegant vintage storybook illustration depth"
        ),
        negative_prompt="modern digital photo, flat 2d cartoon, neon, sci-fi, blurry, plastic skin",
        default_3d_preset="spatial_drift",
        recommended_presets=["spatial_drift", "depthflow_vertigo", "depthflow_spiral", "depthflow_orbit"],
        color_palette={"primary": "#FFD700", "secondary": "#D4AF37", "accent": "#8B0000", "background": "#2B1810"},
        bgm_mood="storybook_acoustic_cello",
    ),
}

# Aliases for convenient shorthand
GENRE_ALIASES = {
    "unreal": "3d_cgi",
    "octane": "3d_cgi",
    "cgi": "3d_cgi",
    "3d": "3d_cgi",
    "spatial": "3d_minimalist",
    "minimalist": "3d_minimalist",
    "apple": "3d_minimalist",
    "explainer": "kinetic_explainer",
    "vox": "kinetic_explainer",
    "kurzgesagt": "kinetic_explainer",
    "vector": "kinetic_explainer",
    "cyberpunk": "cyberpunk_neon",
    "neon": "cyberpunk_neon",
    "glitch": "cyberpunk_neon",
    "cinematic": "cinematic_35mm",
    "photo": "cinematic_35mm",
    "documentary": "cinematic_35mm",
    "casebook": "storybook_casebook",
    "dossier": "storybook_casebook",
    "picture_book": "storybook_casebook",
    "storybook_picturebook": "storybook_casebook",
    "storybook": "storybook_classic",
    "classic_storybook": "storybook_classic",
    "folklore": "storybook_classic",
}


def get_genre_profile(genre_key: str | None) -> GenreProfile:
    """Retrieve genre profile by ID or alias, defaulting to 3d_cgi or cinematic_35mm."""
    if not genre_key:
        return GENRE_REGISTRY["3d_cgi"]
    cleaned = genre_key.lower().strip().replace("-", "_").replace(" ", "_")
    target_id = GENRE_ALIASES.get(cleaned, cleaned)
    return GENRE_REGISTRY.get(target_id, GENRE_REGISTRY["3d_cgi"])


def get_negative_prompt(genre_key: str | None) -> str:
    """Genre-specific FLUX negative prompt, forwarded to `mflux-generate --negative-prompt`.

    Every genre steers away from the same failure modes (HUD reticles drawn on faces, plastic skin,
    flat 2D look), so this is a real per-genre signal rather than boilerplate: it is the field that
    keeps the render humanised.
    """
    return get_genre_profile(genre_key).negative_prompt


def format_genre_prompt(scene_description: str, genre_key: str = "3d_cgi", mood: str = "candid documentary") -> str:
    """Combine scene description with humanized genre-specific prefix and suffix."""
    profile = get_genre_profile(genre_key)
    return f"{profile.prompt_prefix}{scene_description}, {mood} mood, {profile.prompt_suffix}"


def list_available_genres() -> List[Dict[str, str]]:
    """Return all available genres and descriptions."""
    return [{"id": p.id, "name": p.name, "description": p.description, "preset": p.default_3d_preset} for p in GENRE_REGISTRY.values()]


def print_genre_menu() -> None:
    """Prints a structured visual catalog of all 7 production styles with concrete examples."""
    print("\n" + "=" * 78)
    print("  🎬 FRAMEFORGE MULTI-GENRE & STORYBOOK PRODUCTION CATALOG")
    print("=" * 78)
    print("Select an aesthetic genre for production (--genre <id>):\n")

    for idx, (gid, p) in enumerate(GENRE_REGISTRY.items(), 1):
        print(f"[{idx}] {p.name.upper()}  (ID: {gid})")
        print(f"    • Description : {p.description}")
        print(f"    • Palette     : Primary {p.color_palette['primary']} | Secondary {p.color_palette['secondary']} | Accent {p.color_palette['accent']}")
        print(f"    • 3D Preset   : {p.default_3d_preset}")
        print(f"    • Audio Mood  : {p.bgm_mood}")
        print("-" * 78)
    print("\nRun: python tools/pipeline.py --genre <id> OR python tools/master.py produce --genre <id>\n")


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="FrameForge Visual Genre & Storybook Director")
    ap.add_argument("--list", "-l", action="store_true", help="List all visual genres with examples")
    ap.add_argument("--genre", "-g", type=str, default=None, help="Inspect specific genre")
    args = ap.parse_args()

    if args.genre:
        p = get_genre_profile(args.genre)
        print(f"\nProfile: {p.name} ({p.id})")
        print(f"Description: {p.description}")
        print(f"Prompt Prefix: {p.prompt_prefix}")
        print(f"Prompt Suffix: {p.prompt_suffix}")
        print(f"Negative: {p.negative_prompt}")
        return 0

    print_genre_menu()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

