#!/usr/bin/env python3
"""build_avatar_3d.py - Generates 3D Raytraced / Embossed Channel Icon (Avatar) for Cognitive Core.

Features:
- 3D Metallic Beveled Gold Labyrinth Arcs with directional specular highlights & ambient occlusion
- Luminous 3D Glass / Refractive Cyan Core Orb with volumetric radial glow
- Cast drop shadows between geometry layers on deep obsidian brushed canvas
- Subtle radial vignette and dual-mode outer hairline rim for sharp visibility at 32x32 mobile scale
"""
import math
import os
import cv2
import numpy as np
from PIL import Image, ImageDraw

ASSETS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "channel_assets"))
os.makedirs(ASSETS_DIR, exist_ok=True)

SIZE = 800
CX, CY = SIZE // 2, SIZE // 2

def create_3d_avatar():
    # 1. Base dark obsidian brushed metal canvas
    canvas = np.zeros((SIZE, SIZE, 3), dtype=np.float32)
    for y in range(SIZE):
        for x in range(SIZE):
            dist = math.sqrt((x - CX) ** 2 + (y - CY) ** 2) / (SIZE / 2.0)
            # Radial dark gradient #12151D -> #08090C -> #040507
            base = 18.0 * (1.0 - 0.7 * dist)
            canvas[y, x] = [base * 0.9, base * 1.0, base * 1.2]

    # Brushed texture
    noise = np.random.normal(0, 3.0, (SIZE, SIZE, 1))
    canvas = np.clip(canvas + noise, 0, 255).astype(np.uint8)

    # Convert to PIL for anti-aliased drawing of geometry
    geom_img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(geom_img)

    # Outer Safety Rim
    draw.ellipse((CX - 380, CY - 380, CX + 380, CY + 380), outline=(0, 229, 255, 90), width=3)
    draw.ellipse((CX - 372, CY - 372, CX + 372, CY + 372), outline=(255, 179, 0, 70), width=2)

    # Geometry paths for the 3 concentric labyrinth rings
    # Ring 3 (Outer): r=320, width=28
    # Ring 2 (Middle): r=240, width=28
    # Ring 1 (Inner): r=160, width=30
    # Spoke Blades
    mask_gold = Image.new("L", (SIZE, SIZE), 0)
    draw_gold = ImageDraw.Draw(mask_gold)

    # Ring 3 arcs
    draw_gold.arc((CX - 320, CY - 320, CX + 320, CY + 320), start=0, end=90, fill=255, width=28)
    draw_gold.arc((CX - 320, CY - 320, CX + 320, CY + 320), start=180, end=275, fill=255, width=28)

    # Ring 2 arcs
    draw_gold.arc((CX - 240, CY - 240, CX + 240, CY + 240), start=90, end=270, fill=255, width=28)
    draw_gold.arc((CX - 240, CY - 240, CX + 240, CY + 240), start=315, end=450, fill=255, width=28)

    # Ring 1 arcs
    draw_gold.arc((CX - 160, CY - 160, CX + 160, CY + 160), start=0, end=90, fill=255, width=30)
    draw_gold.arc((CX - 160, CY - 160, CX + 160, CY + 160), start=155, end=315, fill=255, width=30)

    # Aperture Spoke Blades
    draw_gold.line((CX, CY - 160, CX, CY - 240), fill=255, width=28)
    draw_gold.line((CX + 160, CY, CX + 240, CY), fill=255, width=28)
    draw_gold.line((CX, CY + 240, CX, CY + 320), fill=255, width=28)
    draw_gold.line((CX - 240, CY, CX - 320, CY), fill=255, width=28)

    gold_mask_arr = np.array(mask_gold, dtype=np.float32) / 255.0

    # Generate 3D Bevel & Lighting Normals for Gold Arcs
    # Sobel gradients of mask give surface slope
    grad_x = cv2.Sobel(gold_mask_arr, cv2.CV_32F, 1, 0, ksize=5)
    grad_y = cv2.Sobel(gold_mask_arr, cv2.CV_32F, 0, 1, ksize=5)

    # Light source: Top-Left (vector: [-0.6, -0.6, 0.8])
    lx, ly, lz = -0.577, -0.577, 0.577

    # Calculate diffuse & specular shading
    diffuse = np.clip(-(grad_x * lx + grad_y * ly) * 2.5 + 0.5, 0.2, 1.4)
    # Specular reflection (gleam)
    specular = np.clip(-(grad_x * lx + grad_y * ly) * 3.5, 0.0, 1.0) ** 4 * 1.5

    # Base Gold Color (BGR: #FFB300 -> [0, 179, 255])
    gold_bgr = np.zeros((SIZE, SIZE, 3), dtype=np.float32)
    gold_bgr[:, :, 0] = np.clip(15 * diffuse + 200 * specular, 0, 255)       # B
    gold_bgr[:, :, 1] = np.clip(160 * diffuse + 240 * specular, 0, 255)      # G
    gold_bgr[:, :, 2] = np.clip(255 * diffuse + 255 * specular, 0, 255)      # R

    # 3D Drop Shadow of gold geometry onto canvas
    shadow_mask = cv2.GaussianBlur(gold_mask_arr, (25, 25), 9)
    # Shift shadow down-right
    M_shadow = np.float32([[1, 0, 12], [0, 1, 14]])
    shifted_shadow = cv2.warpAffine(shadow_mask, M_shadow, (SIZE, SIZE))

    canvas_bgr = canvas.astype(np.float32)
    # Apply drop shadow (darken canvas)
    canvas_bgr *= (1.0 - (shifted_shadow[..., None] * 0.65))

    # Composite 3D Gold onto canvas
    canvas_bgr = canvas_bgr * (1.0 - gold_mask_arr[..., None]) + gold_bgr * gold_mask_arr[..., None]

    # Center Cyan Core Containment Chamber (Ring 0)
    mask_cyan_ring = Image.new("L", (SIZE, SIZE), 0)
    draw_cyan = ImageDraw.Draw(mask_cyan_ring)
    draw_cyan.ellipse((CX - 92, CY - 92, CX + 92, CY + 92), outline=255, width=14)
    cyan_ring_arr = np.array(mask_cyan_ring, dtype=np.float32) / 255.0

    # Glow layer for cyan ring
    cyan_glow = cv2.GaussianBlur(cyan_ring_arr, (35, 35), 14)
    canvas_bgr[:, :, 0] += cyan_glow * 255 * 0.8  # Blue
    canvas_bgr[:, :, 1] += cyan_glow * 229 * 0.8  # Green
    canvas_bgr[:, :, 2] += cyan_glow * 0   * 0.8  # Red

    # Composite cyan ring
    canvas_bgr = canvas_bgr * (1.0 - cyan_ring_arr[..., None]) + np.array([255, 229, 0], dtype=np.float32) * cyan_ring_arr[..., None]

    # Luminous 3D Glass Focal Core Orb (r = 55)
    for y in range(CY - 70, CY + 70):
        for x in range(CX - 70, CX + 70):
            r = math.sqrt((x - CX) ** 2 + (y - CY) ** 2)
            if r <= 55:
                # 3D sphere normal
                nz = math.sqrt(max(0, 1.0 - (r / 55.0) ** 2))
                nx = (x - CX) / 55.0
                ny = (y - CY) / 55.0
                # Specular glint from top-left
                glint = max(0, -(nx * lx + ny * ly + nz * lz)) ** 8
                # Core gradient: pure white center, electric cyan rim
                glow_int = (1.0 - (r / 55.0)) ** 1.5
                b_val = min(255, 255 * glow_int + 255 * glint)
                g_val = min(255, 229 * glow_int + 255 * glint)
                r_val = min(255, 120 * glow_int + 255 * glint)
                canvas_bgr[y, x] = [b_val, g_val, r_val]

    # Volumetric Core Bloom
    core_bloom = np.zeros((SIZE, SIZE), dtype=np.float32)
    cv2.circle(core_bloom, (CX, CY), 65, 1.0, -1)
    core_bloom = cv2.GaussianBlur(core_bloom, (61, 61), 22)
    canvas_bgr[:, :, 0] += core_bloom * 255 * 0.6
    canvas_bgr[:, :, 1] += core_bloom * 200 * 0.5
    canvas_bgr[:, :, 2] += core_bloom * 80  * 0.3

    # Add outer hairline rims from geom_img
    geom_arr = np.array(geom_img, dtype=np.float32)
    geom_alpha = geom_arr[:, :, 3:] / 255.0
    geom_bgr = geom_arr[:, :, :3][:, :, ::-1] # RGBA to BGR
    canvas_bgr = canvas_bgr * (1.0 - geom_alpha) + geom_bgr * geom_alpha

    # Final circular clip at 390px radius
    mask_circle = np.zeros((SIZE, SIZE), dtype=np.uint8)
    cv2.circle(mask_circle, (CX, CY), 390, 255, -1)
    final_bgr = np.clip(canvas_bgr, 0, 255).astype(np.uint8)

    # Transparent background outside circle for PNG
    final_rgba = cv2.cvtColor(final_bgr, cv2.COLOR_BGR2BGRA)
    final_rgba[:, :, 3] = mask_circle

    return final_rgba

def main():
    print("🎨 Rendering 3D Channel Icon Master...")
    rgba = create_3d_avatar()

    out_3d_png = os.path.join(ASSETS_DIR, "avatar_3d_labyrinth_800x800.png")
    cv2.imwrite(out_3d_png, rgba)
    print(f"✅ Saved 3D Master Avatar: {out_3d_png}")

    # Generate 32x32 mobile preview
    preview_32 = cv2.resize(rgba, (32, 32), interpolation=cv2.INTER_AREA)
    out_preview_32 = os.path.join(ASSETS_DIR, "avatar_3d_preview_32x32.png")
    cv2.imwrite(out_preview_32, preview_32)
    print(f"✅ Saved 32x32 mobile preview: {out_preview_32}")

    # Generate side-by-side contrast test on YouTube Dark (#0F0F0F) and Light (#FFFFFF)
    test_w, test_h = 600, 300
    test_img = np.zeros((test_h, test_w, 3), dtype=np.uint8)
    # Left: Dark Mode #0F0F0F
    test_img[:, :300] = [15, 15, 15]
    # Right: Light Mode #FFFFFF
    test_img[:, 300:] = [255, 255, 255]

    icon_180 = cv2.resize(rgba, (180, 180), interpolation=cv2.INTER_AREA)
    alpha = icon_180[:, :, 3] / 255.0
    icon_bgr = icon_180[:, :, :3]

    # Paste on Dark
    y1, y2 = 60, 240
    x1, x2 = 60, 240
    test_img[y1:y2, x1:x2] = (test_img[y1:y2, x1:x2] * (1.0 - alpha[..., None]) + icon_bgr * alpha[..., None]).astype(np.uint8)

    # Paste on Light
    x1, x2 = 360, 540
    test_img[y1:y2, x1:x2] = (test_img[y1:y2, x1:x2] * (1.0 - alpha[..., None]) + icon_bgr * alpha[..., None]).astype(np.uint8)

    out_contrast = os.path.join(ASSETS_DIR, "avatar_3d_contrast_test.png")
    cv2.imwrite(out_contrast, test_img)
    print(f"✅ Saved Contrast Test: {out_contrast}")

if __name__ == "__main__":
    main()
