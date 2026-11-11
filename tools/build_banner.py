#!/usr/bin/env python3
"""build_banner.py - Generates SOTA official 2560x1440 YouTube Channel Banner for FrameForge Studio.

Features:
- Canvas: 2560x1440 px (Official YouTube TV display resolution)
- Mobile Safe Zone: Central 1546x423 px (Visible across 100% of Mobile, Tablet, and Desktop screens)
  * X: 507 to 2053 px
  * Y: 508 to 931 px
- Visual Design Enhancements:
  * Atmospheric deep obsidian noir background with dual chiaroscuro lighting (Warm amber key + Electric cyan rim)
  * Subtle faint geometric lattice / neural network grid at 7% opacity
  * Hero 3D Labyrinth Aperture emblem with illuminated glass core and compass reticle rings
  * Crisp, bold cinematic typography loaded from configs/channels/default.yaml with subtle drop shadow
  * Three sleek glassmorphic topic badges: [ 🧠 EMPIRICAL RESEARCH ], [ 🔍 BEHAVIORAL INSIGHTS ], [ 📁 STORYTELLING ]
  * Vibrant upload cadence badge: [ ⚡ NEW RELEASES WEEKLY ]
"""
import math
import os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ASSETS_DIR = os.path.join(ROOT_DIR, "channel_assets")
FONTS_DIR = os.path.join(ROOT_DIR, "tools", "fonts")
os.makedirs(ASSETS_DIR, exist_ok=True)

WIDTH, HEIGHT = 2560, 1440
SAFE_W, SAFE_H = 1546, 423
SAFE_X1 = (WIDTH - SAFE_W) // 2   # 507
SAFE_X2 = SAFE_X1 + SAFE_W        # 2053
SAFE_Y1 = (HEIGHT - SAFE_H) // 2  # 508
SAFE_Y2 = SAFE_Y1 + SAFE_H        # 931
CY = HEIGHT // 2

def get_font(size: int, bold: bool = True):
    font_name = "BeVietnamPro-Bold.ttf" if bold else "BeVietnamPro-Medium.ttf"
    font_path = os.path.join(FONTS_DIR, font_name)
    try:
        return ImageFont.truetype(font_path, size)
    except Exception:
        return ImageFont.load_default()

def draw_pill(draw, x, y, text, font, text_color, border_color, bg_color=None, pad_x=14, pad_y=7):
    bbox = draw.textbbox((x, y), text, font=font)
    box = (bbox[0] - pad_x, bbox[1] - pad_y, bbox[2] + pad_x, bbox[3] + pad_y)
    if bg_color:
        draw.rounded_rectangle(box, radius=8, fill=bg_color)
    if border_color:
        draw.rounded_rectangle(box, radius=8, outline=border_color, width=1)
    draw.text((x, y), text, fill=text_color, font=font)
    return box[2]  # return right edge

def create_banner():
    # 1. Base dark cinematic background with volumetric lighting
    canvas = np.zeros((HEIGHT, WIDTH, 3), dtype=np.float32)

    # Base gradient: Deep rich dark slate / obsidian #080A0F -> #040507
    for y in range(HEIGHT):
        v = 1.0 - 0.45 * (abs(y - CY) / (HEIGHT / 2.0))
        canvas[y, :] = [14.0 * v, 10.0 * v, 8.0 * v] # BGR

    # Dual Chiaroscuro Spotlights:
    # A) Warm Amber Key Light from top-left (center: [400, 300])
    y_grid, x_grid = np.ogrid[:HEIGHT, :WIDTH]
    dist_amber = np.sqrt((x_grid - 550) ** 2 + (y_grid - 450) ** 2)
    spot_amber = np.clip(1.0 - dist_amber / 950.0, 0, 1) ** 2
    canvas[:, :, 0] += spot_amber * 12   # Blue
    canvas[:, :, 1] += spot_amber * 40   # Green
    canvas[:, :, 2] += spot_amber * 68   # Red

    # B) Electric Cyan Rim Light from right (center: [2100, 800])
    dist_cyan = np.sqrt((x_grid - 2000) ** 2 + (y_grid - 750) ** 2)
    spot_cyan = np.clip(1.0 - dist_cyan / 850.0, 0, 1) ** 2
    canvas[:, :, 0] += spot_cyan * 55    # Blue
    canvas[:, :, 1] += spot_cyan * 42    # Green
    canvas[:, :, 2] += spot_cyan * 8     # Red

    # Center horizontal anamorphic glow beam
    dist_y = np.abs(y_grid - CY)
    beam = np.clip(1.0 - dist_y / 160.0, 0, 1) ** 2
    canvas[:, :, 0] += beam * 30
    canvas[:, :, 1] += beam * 22
    canvas[:, :, 2] += beam * 5

    # Faint Sacred Geometry / Reticle Grid Lines in background
    grid_img = np.zeros((HEIGHT, WIDTH), dtype=np.float32)
    # Concentric circles around emblem center
    ecx, ecy = SAFE_X1 + 220, CY
    for r in [260, 380, 520, 680, 880]:
        cv2.circle(grid_img, (ecx, ecy), r, 1.0, 1, cv2.LINE_AA)
    # Radial tick lines
    for angle_deg in range(0, 360, 30):
        rad = math.radians(angle_deg)
        x1 = int(ecx + 220 * math.cos(rad))
        y1 = int(ecy + 220 * math.sin(rad))
        x2 = int(ecx + 950 * math.cos(rad))
        y2 = int(ecy + 950 * math.sin(rad))
        cv2.line(grid_img, (x1, y1), (x2, y2), 1.0, 1, cv2.LINE_AA)

    grid_img = cv2.GaussianBlur(grid_img, (3, 3), 0)
    # Blend grid at subtle 6% opacity
    canvas[:, :, 0] += grid_img * 15
    canvas[:, :, 1] += grid_img * 12
    canvas[:, :, 2] += grid_img * 5

    # Vignette
    vignette = np.zeros((HEIGHT, WIDTH), dtype=np.float32)
    cv2.circle(vignette, (WIDTH // 2, CY), int(WIDTH * 0.62), 1.0, -1)
    vignette = cv2.GaussianBlur(vignette, (201, 201), 90)
    canvas *= (0.25 + 0.75 * vignette[..., None])

    # Convert to PIL
    img = Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8)[:, :, ::-1], mode="RGB")
    draw = ImageDraw.Draw(img)

    # 2. Hero 3D Emblem with Glow and Reticle Rings
    avatar_path = os.path.join(ASSETS_DIR, "avatar_3d_labyrinth_800x800.png")
    if not os.path.exists(avatar_path):
        avatar_path = os.path.join(ASSETS_DIR, "avatar_labyrinth_800x800.png")

    emblem_size = 330
    emblem_x = SAFE_X1 + 55
    emblem_y = CY - (emblem_size // 2)

    # Deep Drop Shadow & Volumetric Cyan Halo behind emblem
    halo = Image.new("RGBA", (emblem_size + 140, emblem_size + 140), (0, 0, 0, 0))
    h_draw = ImageDraw.Draw(halo)
    hc = (emblem_size + 140) // 2
    h_draw.ellipse((hc - 150, hc - 150, hc + 150, hc + 150), fill=(0, 229, 255, 85))
    h_draw.ellipse((hc - 110, hc - 110, hc + 110, hc + 110), fill=(0, 0, 0, 180))
    halo = halo.filter(ImageFilter.GaussianBlur(32))
    img.paste(halo, (emblem_x - 70, emblem_y - 70), mask=halo)

    if os.path.exists(avatar_path):
        avatar = Image.open(avatar_path).convert("RGBA")
        avatar_scaled = avatar.resize((emblem_size, emblem_size), Image.Resampling.LANCZOS)
        img.paste(avatar_scaled, (emblem_x, emblem_y), mask=avatar_scaled)

    # 3. Typography & Badges strictly inside Safe Zone
    text_x = emblem_x + emblem_size + 65

    # Main Channel Title loaded from default channel preset
    from tools.channel_config import load_channel_config

    try:
        title_text = (load_channel_config("default").channel_name or "FrameForge Studio").upper()
    except Exception:
        title_text = "FRAMEFORGE STUDIO"
    font_title = get_font(78, bold=True)

    # Soft drop shadow behind main title
    draw.text((text_x + 3, CY - 118), title_text, fill=(0, 0, 0), font=font_title)
    draw.text((text_x + 1, CY - 120), title_text, fill=(255, 255, 255), font=font_title)

    # Tagline 1: The Architecture of Human Thought
    font_tag = get_font(25, bold=True)
    tag_text = "THE ARCHITECTURE OF HUMAN THOUGHT"
    draw.text((text_x + 2, CY - 30), tag_text, fill=(0, 229, 255), font=font_tag)

    # Tagline 2: Explainer sentence
    font_desc = get_font(19, bold=False)
    desc_text = "Decoding psychological quirks, focus traps, and historical mysteries through science."
    draw.text((text_x + 2, CY + 10), desc_text, fill=(195, 202, 215), font=font_desc)

    # Three Topic Pill Badges
    font_pills = get_font(16, bold=True)
    cur_x = text_x + 2
    pill_y = CY + 52
    cur_x = draw_pill(
        draw, cur_x, pill_y, "🧠  EMPIRICAL RESEARCH", font_pills,
        text_color=(240, 245, 255), border_color=(70, 95, 130), bg_color=(15, 22, 35),
    ) + 14
    cur_x = draw_pill(
        draw, cur_x, pill_y, "🔍  BEHAVIORAL QUIRKS", font_pills,
        text_color=(240, 245, 255), border_color=(70, 95, 130), bg_color=(15, 22, 35),
    ) + 14
    draw_pill(
        draw, cur_x, pill_y, "📁  COLD CASE MYSTERIES", font_pills,
        text_color=(240, 245, 255), border_color=(70, 95, 130), bg_color=(15, 22, 35),
    )

    # Prominent Upload Cadence Badge
    font_cadence = get_font(17, bold=True)
    cadence_y = CY + 96
    draw_pill(
        draw, text_x + 2, cadence_y, "⚡  NEW RELEASES WEEKLY", font_cadence,
        text_color=(255, 185, 35), border_color=(255, 179, 0), bg_color=(35, 25, 8),
        pad_x=16, pad_y=8,
    )

    # Fine 35mm grain pass
    arr = np.array(img, dtype=np.int16)
    grain = np.random.randint(-5, 5, (HEIGHT, WIDTH, 3), dtype=np.int16)
    arr = np.clip(arr + grain, 0, 255).astype(np.uint8)

    final_img = Image.fromarray(arr)
    return final_img

def main():
    print("🎨 Rendering Upgraded Official YouTube Channel Banner (2560x1440)...")
    banner = create_banner()

    out_jpg = os.path.join(ASSETS_DIR, "channel_banner_2560x1440.jpg")
    banner.save(out_jpg, "JPEG", quality=95)
    print(f"✅ Saved Upgraded Channel Banner: {out_jpg}")

    # Generate Safe Zone Inspection Overlay for verification
    debug_img = banner.copy()
    debug_draw = ImageDraw.Draw(debug_img)
    # Draw green rectangle around Mobile Safe Zone
    debug_draw.rectangle((SAFE_X1, SAFE_Y1, SAFE_X2, SAFE_Y2), outline=(0, 255, 0), width=4)
    # Draw Desktop width guide
    debug_draw.rectangle((0, SAFE_Y1, WIDTH, SAFE_Y2), outline=(255, 255, 0), width=2)
    debug_out = os.path.join(ASSETS_DIR, "channel_banner_safe_zone_test.jpg")
    debug_img.save(debug_out, "JPEG", quality=90)
    print(f"✅ Saved Safe Zone Inspection Plate: {debug_out}")

if __name__ == "__main__":
    main()
