#!/usr/bin/env python3
"""build_avatar.py - Generate high-contrast, scalable Channel Icon (Avatar) for FrameForge Studio.

Generates:
1. channel_assets/avatar_labyrinth_800x800.svg (Vector Master)
2. channel_assets/avatar_labyrinth_800x800.png (High-Res YouTube PFP Master)
3. channel_assets/avatar_preview_32x32.png (Mobile UI scale preview)
4. channel_assets/avatar_contrast_test.png (Side-by-side test on Dark Mode #0F0F0F and Light Mode #FFFFFF)

Design Specifications:
- Concept: The Labyrinth-Aperture (Observational Maze)
- Outer Boundary: 760px diameter (safely inside 800px circular crop)
- Line Weight: 26-30px strokes for sharp visibility at 32x32 mobile scale
- Color Palette:
    * Canvas: Deep Obsidian (#08090C) with subtle radial vignette
    * Aperture / Labyrinth: Warm Chiaroscuro Amber / Gold (#FFB82E, #E59819)
    * Focal Center Core: Vivid Electric Cyan (#00E5FF, #70F7FF)
    * Outer Safety Rim: Crisp dual-mode hairline rim (#00E5FF at 45% opacity)
"""
import math
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ASSETS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "channel_assets"))
os.makedirs(ASSETS_DIR, exist_ok=True)

WIDTH, HEIGHT = 800, 800
CENTER_X, CENTER_Y = WIDTH // 2, HEIGHT // 2

def generate_svg():
    """Generates a clean, optimized SVG vector asset."""
    svg_path = os.path.join(ASSETS_DIR, "avatar_labyrinth_800x800.svg")
    cx, cy = CENTER_X, CENTER_Y
    
    # 4 concentric labyrinth arcs with aperture blade angles
    svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}">
  <defs>
    <!-- Background Radial Gradient -->
    <radialGradient id="bgGrad" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#12151D" />
      <stop offset="70%" stop-color="#08090C" />
      <stop offset="100%" stop-color="#040507" />
    </radialGradient>

    <!-- Warm Amber Gold Gradient -->
    <linearGradient id="goldGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#FFE082" />
      <stop offset="40%" stop-color="#FFB300" />
      <stop offset="100%" stop-color="#FF8F00" />
    </linearGradient>

    <!-- Cyan Energy Core Gradient -->
    <radialGradient id="cyanCore" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#FFFFFF" />
      <stop offset="35%" stop-color="#70F7FF" />
      <stop offset="75%" stop-color="#00E5FF" />
      <stop offset="100%" stop-color="#00838F" />
    </radialGradient>

    <!-- Outer Rim Glow Filter -->
    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="8" result="blur" />
      <feComposite in="SourceGraphic" in2="blur" operator="over" />
    </filter>
  </defs>

  <!-- Circular Mask Background -->
  <clipPath id="circleClip">
    <circle cx="{cx}" cy="{cy}" r="390" />
  </clipPath>

  <g clip-path="url(#circleClip)">
    <!-- Base Canvas -->
    <rect width="{WIDTH}" height="{HEIGHT}" fill="url(#bgGrad)" />

    <!-- Outer Contrast Rim (Guarantees separation in YouTube Dark Mode and Light Mode) -->
    <circle cx="{cx}" cy="{cy}" r="380" fill="none" stroke="#00E5FF" stroke-opacity="0.3" stroke-width="3" />
    <circle cx="{cx}" cy="{cy}" r="372" fill="none" stroke="#FFB300" stroke-opacity="0.2" stroke-width="1.5" />

    <!-- Ring 4: Outermost Labyrinth Wall (Radius ~320) -->
    <path d="M {cx + 320} {cy} A 320 320 0 1 0 {cx} {cy + 320}" fill="none" stroke="url(#goldGrad)" stroke-width="26" stroke-linecap="round" />
    <path d="M {cx - 320} {cy} A 320 320 0 0 0 {cx - 70} {cy - 312}" fill="none" stroke="url(#goldGrad)" stroke-width="26" stroke-linecap="round" />

    <!-- Ring 3: Middle Labyrinth Aperture Wall (Radius ~240) -->
    <path d="M {cx} {cy - 240} A 240 240 0 1 1 {cx - 240} {cy}" fill="none" stroke="url(#goldGrad)" stroke-width="26" stroke-linecap="round" />
    <path d="M {cx - 170} {cy + 170} A 240 240 0 0 0 {cx + 240} {cy}" fill="none" stroke="url(#goldGrad)" stroke-width="26" stroke-linecap="round" />

    <!-- Ring 2: Inner Aperture Wall (Radius ~160) -->
    <path d="M {cx + 160} {cy} A 160 160 0 1 0 {cx} {cy + 160}" fill="none" stroke="url(#goldGrad)" stroke-width="28" stroke-linecap="round" />
    <path d="M {cx - 145} {cy - 68} A 160 160 0 0 1 {cx + 113} {cy - 113}" fill="none" stroke="url(#goldGrad)" stroke-width="28" stroke-linecap="round" />

    <!-- Intersecting Aperture Spoke Blades (Radial Iris Geometry) -->
    <line x1="{cx}" y1="{cy - 160}" x2="{cx}" y2="{cy - 240}" stroke="url(#goldGrad)" stroke-width="26" stroke-linecap="round" />
    <line x1="{cx + 160}" y1="{cy}" x2="{cx + 240}" y2="{cy}" stroke="url(#goldGrad)" stroke-width="26" stroke-linecap="round" />
    <line x1="{cx}" y1="{cy + 240}" x2="{cx}" y2="{cy + 320}" stroke="url(#goldGrad)" stroke-width="26" stroke-linecap="round" />
    <line x1="{cx - 240}" y1="{cy}" x2="{cx - 320}" y2="{cy}" stroke="url(#goldGrad)" stroke-width="26" stroke-linecap="round" />

    <!-- Ring 1: The Core Containment Chamber (Radius ~95) -->
    <circle cx="{cx}" cy="{cy}" r="92" fill="none" stroke="#00E5FF" stroke-width="12" stroke-opacity="0.9" />
    <circle cx="{cx}" cy="{cy}" r="92" fill="none" stroke="#FFB300" stroke-width="6" stroke-dasharray="35 25" />

    <!-- Center Studio Core Glow -->
    <circle cx="{cx}" cy="{cy}" r="56" fill="url(#cyanCore)" filter="url(#glow)" />
    <circle cx="{cx}" cy="{cy}" r="22" fill="#FFFFFF" />
  </g>
</svg>
"""
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg_content)
    print(f"Generated Vector SVG: {svg_path}")
    return svg_path

def render_master_png():
    """Renders high-fidelity anti-aliased 800x800 master PNG with chiaroscuro depth."""
    png_path = os.path.join(ASSETS_DIR, "avatar_labyrinth_800x800.png")
    
    # Render at 2x resolution (1600x1600) for supersampled anti-aliasing
    SCALE = 2
    W, H = WIDTH * SCALE, HEIGHT * SCALE
    cx, cy = CENTER_X * SCALE, CENTER_Y * SCALE

    # 1. Base Image - Subtle radial gradient on background
    y_coords, x_coords = np.ogrid[:H, :W]
    dist_from_center = np.sqrt((x_coords - cx) ** 2 + (y_coords - cy) ** 2)
    max_radius = 390 * SCALE
    
    # Background radial lighting map
    bg_arr = np.zeros((H, W, 4), dtype=np.uint8)
    norm_dist = np.clip(dist_from_center / max_radius, 0.0, 1.0)
    
    # Center dark blue-gray (18, 22, 32), edges obsidian (6, 7, 10)
    r = (18 - (18 - 6) * norm_dist).astype(np.uint8)
    g = (22 - (22 - 7) * norm_dist).astype(np.uint8)
    b = (32 - (32 - 10) * norm_dist).astype(np.uint8)
    bg_arr[:, :, 0] = r
    bg_arr[:, :, 1] = g
    bg_arr[:, :, 2] = b
    bg_arr[:, :, 3] = 255
    bg_img = Image.fromarray(bg_arr, mode="RGBA")
    
    # 2. Draw Geometric Aperture & Labyrinth Arcs on separate overlay
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)

    GOLD_MAIN = (255, 185, 35, 255)
    CYAN_CORE = (0, 229, 255, 255)
    WHITE = (255, 255, 255, 255)

    # Helper to draw thick circular arcs with smooth ends
    def draw_thick_arc(center_x, center_y, radius, start_deg, end_deg, width, color):
        bbox = (center_x - radius, center_y - radius, center_x + radius, center_y + radius)
        ov_draw.arc(bbox, start=start_deg, end=end_deg, fill=color, width=width)
        # Add rounded caps at start and end
        for deg in (start_deg, end_deg):
            rad = math.radians(deg)
            cap_x = center_x + radius * math.cos(rad)
            cap_y = center_y + radius * math.sin(rad)
            r_cap = width / 2.0
            ov_draw.ellipse((cap_x - r_cap, cap_y - r_cap, cap_x + r_cap, cap_y + r_cap), fill=color)

    # Outer Contrast Safety Rim (Protects against dark and light YouTube UI)
    ov_draw.ellipse((cx - 380 * SCALE, cy - 380 * SCALE, cx + 380 * SCALE, cy + 380 * SCALE),
                    outline=(0, 229, 255, 110), width=6 * SCALE)
    ov_draw.ellipse((cx - 370 * SCALE, cy - 370 * SCALE, cx + 370 * SCALE, cy + 370 * SCALE),
                    outline=(255, 185, 35, 75), width=3 * SCALE)

    # Ring 4: Outermost Labyrinth Wall (Radius ~320)
    w4 = 28 * SCALE
    r4 = 320 * SCALE
    draw_thick_arc(cx, cy, r4, 0, 270, w4, GOLD_MAIN)
    draw_thick_arc(cx, cy, r4, 290, 340, w4, GOLD_MAIN)

    # Ring 3: Middle Labyrinth Aperture Wall (Radius ~240)
    w3 = 28 * SCALE
    r3 = 240 * SCALE
    draw_thick_arc(cx, cy, r3, 90, 360, w3, GOLD_MAIN)
    draw_thick_arc(cx, cy, r3, 20, 70, w3, GOLD_MAIN)

    # Ring 2: Inner Aperture Wall (Radius ~160)
    w2 = 30 * SCALE
    r2 = 160 * SCALE
    draw_thick_arc(cx, cy, r2, 180, 450, w2, GOLD_MAIN)
    draw_thick_arc(cx, cy, r2, 110, 160, w2, GOLD_MAIN)

    # Intersecting Aperture Spoke Blades (Radial Maze connections)
    spoke_w = 28 * SCALE
    ov_draw.line([(cx, cy - 160 * SCALE), (cx, cy - 240 * SCALE)], fill=GOLD_MAIN, width=spoke_w)
    ov_draw.line([(cx + 160 * SCALE, cy), (cx + 240 * SCALE, cy)], fill=GOLD_MAIN, width=spoke_w)
    ov_draw.line([(cx, cy + 240 * SCALE), (cx, cy + 320 * SCALE)], fill=GOLD_MAIN, width=spoke_w)
    ov_draw.line([(cx - 240 * SCALE, cy), (cx - 320 * SCALE, cy)], fill=GOLD_MAIN, width=spoke_w)

    # Add rounded end caps to spokes
    for p in [(cx, cy - 160 * SCALE), (cx, cy - 240 * SCALE),
              (cx + 160 * SCALE, cy), (cx + 240 * SCALE, cy),
              (cx, cy + 240 * SCALE), (cx, cy + 320 * SCALE),
              (cx - 240 * SCALE, cy), (cx - 320 * SCALE, cy)]:
        ov_draw.ellipse((p[0] - spoke_w/2, p[1] - spoke_w/2, p[0] + spoke_w/2, p[1] + spoke_w/2), fill=GOLD_MAIN)

    # Ring 1: The Core Containment Chamber (Radius ~96)
    r1 = 96 * SCALE
    ov_draw.ellipse((cx - r1, cy - r1, cx + r1, cy + r1), outline=CYAN_CORE, width=14 * SCALE)

    # Center Cyan Core with multi-pass bloom
    glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)
    glow_draw.ellipse((cx - 75 * SCALE, cy - 75 * SCALE, cx + 75 * SCALE, cy + 75 * SCALE), fill=(0, 229, 255, 120))
    glow_draw.ellipse((cx - 50 * SCALE, cy - 50 * SCALE, cx + 50 * SCALE, cy + 50 * SCALE), fill=(112, 247, 255, 200))
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=16 * SCALE))

    # Center white-hot pupil
    ov_draw.ellipse((cx - 50 * SCALE, cy - 50 * SCALE, cx + 50 * SCALE, cy + 50 * SCALE), fill=(0, 229, 255, 240))
    ov_draw.ellipse((cx - 22 * SCALE, cy - 22 * SCALE, cx + 22 * SCALE, cy + 22 * SCALE), fill=WHITE)

    # 3. Composite layers
    master = Image.alpha_composite(bg_img, glow_layer)
    master = Image.alpha_composite(master, overlay)

    # 4. Circular Mask crop to ensure crisp round edges
    mask = Image.new("L", (W, H), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((cx - 388 * SCALE, cy - 388 * SCALE, cx + 388 * SCALE, cy + 388 * SCALE), fill=255)
    
    final_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    final_img.paste(master, (0, 0), mask=mask)

    # 5. Downsample with Lanczos filter to 800x800 for pristine anti-aliasing
    final_800 = final_img.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    final_800.save(png_path, "PNG", optimize=True)
    print(f"Generated Master PNG (800x800): {png_path}")
    return final_800

def generate_scale_tests(master_img):
    """Generates 32x32 mobile preview and side-by-side Dark/Light mode contrast test."""
    # 1. 32x32 mobile preview
    prev_32 = master_img.resize((32, 32), Image.Resampling.LANCZOS)
    prev_32_path = os.path.join(ASSETS_DIR, "avatar_preview_32x32.png")
    prev_32.save(prev_32_path, "PNG")

    # 2. Side-by-side Contrast Test Sheet (Dark Mode #0F0F0F vs Light Mode #FFFFFF)
    # Canvas: 900 x 420 px
    test_w, test_h = 900, 420
    test_sheet = Image.new("RGBA", (test_w, test_h), (20, 22, 28, 255))
    test_draw = ImageDraw.Draw(test_sheet)

    # Left panel: Dark Mode (#0F0F0F)
    test_draw.rectangle([0, 0, 450, test_h], fill=(15, 15, 15, 255))
    # Right panel: Light Mode (#FFFFFF)
    test_draw.rectangle([450, 0, test_w, test_h], fill=(255, 255, 255, 255))

    # Paste preview at 176x176 (Desktop Channel Header scale)
    p_176 = master_img.resize((176, 176), Image.Resampling.LANCZOS)
    test_sheet.paste(p_176, (50, 100), mask=p_176)
    test_sheet.paste(p_176, (500, 100), mask=p_176)

    # Paste preview at 48x48 (Video Watch Page scale)
    p_48 = master_img.resize((48, 48), Image.Resampling.LANCZOS)
    test_sheet.paste(p_48, (260, 160), mask=p_48)
    test_sheet.paste(p_48, (710, 160), mask=p_48)

    # Paste preview at 32x32 (Mobile Comment / Notification scale)
    test_sheet.paste(prev_32, (340, 170), mask=prev_32)
    test_sheet.paste(prev_32, (790, 170), mask=prev_32)

    contrast_test_path = os.path.join(ASSETS_DIR, "avatar_contrast_test.png")
    test_sheet.save(contrast_test_path, "PNG")
    print(f"Generated Mobile Scale & Contrast Test: {contrast_test_path}")

if __name__ == "__main__":
    generate_svg()
    master = render_master_png()
    generate_scale_tests(master)
    print("Avatar build completed successfully.")
