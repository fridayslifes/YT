"""Shared spatial-composition primitives for vertical Shorts (any topic, any asset set).

The rules live in .agents/personas/scene_composer.md; this module is the executable half:
- every readable text layer must sit inside the 0.44-0.76 vertical band (`text_layer_errors`)
- captions wrap into near-equal lines, never a single orphan word (`wrap_balanced`)
- the ground band gets texture and ripples so it is never blank (`make_ground_texture`)

Compositors pass their own frame size, font, tones and seed, so the same functions cover
2160x3840 and 1080x1920 and any palette.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw

BAND_TOP = 0.44
BAND_BOTTOM = 0.76


def band_pixels(frame_height: int) -> Tuple[int, int]:
    return int(frame_height * BAND_TOP), int(frame_height * BAND_BOTTOM)


def text_layer_errors(layers: Sequence[Tuple[str, int, int]], frame_height: int) -> List[str]:
    """layers: (name, top_px, bottom_px). Returns one message per layer outside the band."""
    top, bottom = band_pixels(frame_height)
    return [
        f"{name}: {lo}-{hi}px outside safe band {top}-{bottom}px"
        for name, lo, hi in layers
        if lo < top or hi > bottom
    ]


def wrap_balanced(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> List[str]:
    """Greedy wrap first to get the line count, then re-wrap to that many near-equal lines."""
    words = text.split()
    lines: List[str] = []
    curr: List[str] = []
    for w in words:
        curr.append(w)
        bbox = draw.textbbox((0, 0), " ".join(curr), font=font)
        if (bbox[2] - bbox[0]) > max_width:
            curr.pop()
            if curr:
                lines.append(" ".join(curr))
            curr = [w]
    if curr:
        lines.append(" ".join(curr))
    n = len(lines)
    if n < 2:
        return lines
    target = draw.textbbox((0, 0), text, font=font)[2] / n
    balanced: List[str] = []
    curr = []
    for w in words:
        curr.append(w)
        if draw.textbbox((0, 0), " ".join(curr), font=font)[2] > target * 1.12 and len(balanced) < n - 1:
            curr.pop()
            balanced.append(" ".join(curr))
            curr = [w]
    if curr:
        balanced.append(" ".join(curr))
    return balanced if len(balanced) == n else lines


def overlay_sprite(
    canvas: np.ndarray,
    sprite_rgba: Optional[np.ndarray],
    cx: int,
    cy: int,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
    angle_deg: float = 0.0,
    pivot_ratio: Tuple[float, float] = (0.5, 0.5),
    opacity: float = 1.0,
) -> np.ndarray:
    """Alpha-composite an RGBA sprite onto a BGR canvas with scale, rotation, pivot and opacity."""
    if sprite_rgba is None or opacity <= 0.0:
        return canvas
    h_s, w_s = sprite_rgba.shape[:2]
    target_w = max(1, int(w_s * abs(scale_x)))
    target_h = max(1, int(h_s * abs(scale_y)))
    scaled = cv2.resize(sprite_rgba, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)
    if scale_x < 0:
        scaled = cv2.flip(scaled, 1)
    if abs(angle_deg) > 0.1:
        m = cv2.getRotationMatrix2D((target_w * pivot_ratio[0], target_h * pivot_ratio[1]), angle_deg, 1.0)
        scaled = cv2.warpAffine(scaled, m, (target_w, target_h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_CONSTANT)
    top_left_x = int(cx - target_w * pivot_ratio[0])
    top_left_y = int(cy - target_h * pivot_ratio[1])
    c_h, c_w = canvas.shape[:2]
    x1_c, y1_c = max(0, top_left_x), max(0, top_left_y)
    x2_c = min(c_w, top_left_x + target_w)
    y2_c = min(c_h, top_left_y + target_h)
    x1_s, y1_s = max(0, -top_left_x), max(0, -top_left_y)
    x2_s = x1_s + (x2_c - x1_c)
    y2_s = y1_s + (y2_c - y1_c)
    if x2_c > x1_c and y2_c > y1_c and x2_s > x1_s and y2_s > y1_s:
        patch = scaled[y1_s:y2_s, x1_s:x2_s]
        alpha = (patch[:, :, 3].astype(np.float32) / 255.0) * opacity
        alpha = alpha[:, :, np.newaxis]
        bgr = patch[:, :, :3].astype(np.float32)
        base = canvas[y1_c:y2_c, x1_c:x2_c].astype(np.float32)
        canvas[y1_c:y2_c, x1_c:x2_c] = (bgr * alpha + base * (1.0 - alpha)).astype(np.uint8)
    return canvas


def draw_pill_caption(
    canvas: np.ndarray,
    text: str,
    frame_width: int,
    font,
    cy: int,
    highlight_words: Optional[List[str]] = None,
    line_h: int = 90,
    max_width: int = 1750,
) -> np.ndarray:
    if not text:
        return canvas
    img_pil = Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    lines = wrap_balanced(draw, text, font, max_width)
    total_h = len(lines) * line_h
    start_y = cy - total_h // 2
    hl = {h.lower() for h in (highlight_words or [])}
    for idx, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        lx = (frame_width - text_w) // 2
        ly = start_y + idx * line_h
        pad_x, pad_y = 42, 18
        draw.rounded_rectangle([lx - pad_x, ly - pad_y, lx + text_w + pad_x, ly + text_h + pad_y],
                               radius=24, fill=(18, 22, 28, 240), outline=(255, 255, 255, 80), width=3)
        word_x = lx
        for w in line.split():
            clean_w = w.strip(".,:;!?\"'-")
            color = (255, 220, 40) if clean_w.lower() in hl else (255, 255, 255)
            draw.text((word_x, ly), w + " ", font=font, fill=color)
            w_bbox = draw.textbbox((0, 0), w + " ", font=font)
            word_x += (w_bbox[2] - w_bbox[0])
    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)


def draw_card(
    canvas: np.ndarray,
    text: str,
    cy: int,
    font,
    fill: Tuple[int, int, int] = (18, 24, 36),
    outline: Tuple[int, int, int] = (0, 225, 255),
    opacity: float = 1.0,
    cx: Optional[int] = None,
) -> np.ndarray:
    if opacity <= 0.01 or not text:
        return canvas
    frame_width = canvas.shape[1]
    img_pil = Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil, "RGBA")
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    cx = frame_width // 2 if cx is None else cx
    pad_x, pad_y = 54, 26
    pill = [cx - tw // 2 - pad_x, cy - th // 2 - pad_y, cx + tw // 2 + pad_x, cy + th // 2 + pad_y]
    a_fill = int(245 * opacity)
    a_line = int(255 * opacity)
    draw.rounded_rectangle(pill, radius=32, fill=(*fill, a_fill), outline=(*outline, a_line), width=5)
    draw.text((cx - tw // 2, cy - th // 2), text, font=font, fill=(255, 255, 255, a_line))
    return cv2.cvtColor(np.array(img_pil.convert("RGB")), cv2.COLOR_BGR2RGB)


def make_ground_texture(frame_width: int, ground_y: int, frame_height: int, seed: int,
                        tone: Tuple[int, int, int], with_puddles: bool = False) -> np.ndarray:
    """Deterministic ground: gradient, speckles, pebbles, and optional puddles. Never a blank band."""
    gh = frame_height - ground_y
    g = np.zeros((gh, frame_width, 3), dtype=np.uint8)
    bottom = tuple(max(0, int(v * 0.78)) for v in tone)
    for c in range(3):
        g[:, :, c] = np.linspace(tone[c], bottom[c], gh, dtype=np.uint8)[:, np.newaxis]
    rng = np.random.default_rng(seed)
    for _ in range(max(600, int(frame_width * gh / 3400))):
        x = int(rng.integers(0, frame_width))
        y = int(rng.integers(14, gh))
        r = int(rng.integers(2, max(4, frame_width // 300)))
        shift = int(rng.integers(-16, 22))
        cv2.circle(g, (x, y), r, tuple(int(np.clip(v + shift, 0, 255)) for v in tone), -1, cv2.LINE_AA)
    for _ in range(max(20, int(frame_width / 27))):
        x = int(rng.integers(20, frame_width - 20))
        y = int(rng.integers(30, max(40, gh - 10)))
        axes = (int(rng.integers(8, 26)), int(rng.integers(5, 14)))
        cv2.ellipse(g, (x, y), axes, 0, 0, 360, tuple(int(np.clip(v + 24, 0, 255)) for v in tone), -1, cv2.LINE_AA)
        cv2.ellipse(g, (x, y), axes, 0, 0, 360, tuple(int(np.clip(v - 22, 0, 255)) for v in tone), 2, cv2.LINE_AA)
    if with_puddles:
        for fx, fy, fw in ((0.19, 0.31, 0.19), (0.73, 0.46, 0.24), (0.44, 0.84, 0.28)):
            px, py, pw = int(frame_width * fx), int((frame_height - ground_y) * fy), int(frame_width * fw)
            cv2.ellipse(g, (px, py), (pw, int(pw * 0.26)), 0, 0, 360,
                        tuple(int(np.clip(v + 24, 0, 255)) for v in tone), -1, cv2.LINE_AA)
            cv2.ellipse(g, (px - pw // 4, py - 6), (pw // 4, int(pw * 0.06)), 0, 0, 360,
                        tuple(int(np.clip(v + 52, 0, 255)) for v in tone), -1, cv2.LINE_AA)
    return g


def add_turf(bg: np.ndarray, ground_y: int, turf: Tuple[int, int, int] = (62, 104, 84)) -> np.ndarray:
    width = bg.shape[1]
    cv2.rectangle(bg, (0, ground_y - 12), (width, ground_y), turf, -1)
    cv2.line(bg, (0, ground_y), (width, ground_y), (35, 45, 55), 8, cv2.LINE_AA)
    step = max(40, width // 29)
    for x in range(0, width, step):
        h = 16 + (x * 37) % 20
        cv2.line(bg, (x, ground_y - 8), (x + 7, ground_y - 8 - h),
                 tuple(int(v * 1.06) for v in turf), 4, cv2.LINE_AA)
        cv2.line(bg, (x + step // 5, ground_y - 8), (x + step // 5 - 4, ground_y - 8 - h + 6),
                 tuple(int(v * 0.94) for v in turf), 3, cv2.LINE_AA)
    return bg


def draw_ripples(canvas: np.ndarray, t_sec: float, ground_y: int, x_min: int = 0,
                 x_max: Optional[int] = None) -> np.ndarray:
    width = canvas.shape[1]
    x_max = width if x_max is None else x_max
    for i in range(11):
        phase = (t_sec * 0.85 + i * 0.19) % 1.0
        rx = x_min + ((i * 397 + 113) % max(1, x_max - x_min))
        ry = ground_y + 70 + (i % 3) * 110
        rad = int(14 + phase * 64)
        fade = max(0.0, 1.0 - phase)
        col = tuple(int(60 * fade + bg * (1 - fade)) for bg in (70, 82, 100))
        cv2.ellipse(canvas, (rx, ry), (rad, int(rad * 0.3)), 0, 0, 360, col, 3, cv2.LINE_AA)
    return canvas