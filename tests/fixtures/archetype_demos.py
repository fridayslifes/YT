#!/usr/bin/env python3
"""Extracted 30-second archetype showcase demos (demos/archetype_demos.py).

These standalone showcase demos (Wall Street 1920, 3 Prisoners Hat Riddle,
2 AM Productive Procrastination, Quantum Vault 7 Heist) are isolated from
production project dispatch so `universal_engine.build_project` never replays
a hardcoded demo narrative.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from tools.visual_engine import remotion_spring


def render_30s_photobook_hd_with_audio(output_path: Path, fps: int = 30) -> Path:
    """Renders 30s broadcast Full HD Photobook demo (Wall Street 1920 Bombing)."""
    from tools.universal_engine import (
        BEBAS_NEUE,
        BE_VIETNAM_BOLD,
        build_master_audio_track,
        get_font,
        reencode_broadcast_mp4_with_audio,
        render_caption_pill,
        synthesize_studio_speech,
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    text = (
        "On September 16, 1920, at exactly 12:01 PM, a horse-drawn cart stops in front of J.P. Morgan on Wall Street. "
        "The driver walks away. Thirty seconds later, five hundred pounds of TNT detonate, shattering windows for a mile. "
        "Over thirty million dollars in bonds vanished in the smoke. The driver? Never seen again. "
        "Until one detective discovered a single clue left in the rubble that baffled the FBI for a century."
    )
    tmp_voice = output_path.with_suffix(".p1_voice.wav")
    _, words = synthesize_studio_speech(text, tmp_voice, voice="bm_george")

    sfx = [("whoosh.wav", 0.5, 0.5)]
    for sec in range(2, 13):
        sfx.append(("click.wav", float(sec), 0.25))
    sfx.extend([
        ("boom.wav", 11.8, 0.85),
        ("impact.wav", 12.0, 0.70),
        ("whoosh.wav", 17.5, 0.50),
        ("chime.wav", 23.5, 0.60),
    ])
    master_wav = output_path.with_suffix(".p1_master.wav")
    build_master_audio_track(tmp_voice, master_wav, 30.0, lead_in=0.8, sfx_events=sfx, drone_freqs=(45.0, 68.0), drone_vol=0.12)
    tmp_voice.unlink(missing_ok=True)

    duration = 30.0
    total_frames = int(duration * fps)
    w_2x, h_2x = 2160, 3840
    w_final, h_final = 1080, 1920

    font_headline = get_font(BEBAS_NEUE, 108)
    font_sub_head = get_font(BE_VIETNAM_BOLD, 46)
    font_callout = get_font(BEBAS_NEUE, 120)
    font_hud_1k = get_font(BE_VIETNAM_BOLD, 36)
    font_cap_1k = get_font(BE_VIETNAM_BOLD, 44)
    font_cta_1k = get_font(BE_VIETNAM_BOLD, 38)

    np_w, np_h = 1520, 960
    newspaper = Image.new("RGBA", (np_w, np_h), (242, 236, 222, 255))
    np_draw = ImageDraw.Draw(newspaper)
    np_draw.rectangle([20, 20, np_w - 20, np_h - 20], outline=(160, 145, 120, 255), width=6)
    np_draw.text((np_w // 2, 85), "THE WALL STREET CHRONICLE", fill=(20, 18, 16, 255), font=font_headline, anchor="mm")
    np_draw.line([(60, 150), (np_w - 60, 150)], fill=(80, 70, 60, 255), width=4)
    np_draw.text((np_w // 2, 210), "SEPTEMBER 16, 1920 — FIVE HUNDRED POUNDS TNT DETONATE", fill=(185, 35, 35, 255), font=font_sub_head, anchor="mm")
    np_draw.line([(60, 270), (np_w - 60, 270)], fill=(120, 110, 100, 255), width=3)
    for row in range(320, np_h - 60, 68):
        np_draw.rectangle([60, row, np_w - 60, row + 24], fill=(70, 65, 60, 220))

    np_shadow = Image.new("RGBA", (np_w + 120, np_h + 120), (0, 0, 0, 0))
    ImageDraw.Draw(np_shadow).rectangle([60, 60, np_w + 60, np_h + 60], fill=(0, 0, 0, 180))
    np_shadow = np_shadow.filter(ImageFilter.GaussianBlur(40))
    np_shadow.paste(newspaper, (60, 60), newspaper)
    np_rotated = np_shadow.rotate(-4.0, expand=True, resample=Image.BICUBIC)

    map_2x = Image.new("RGBA", (w_2x, h_2x), (232, 222, 204, 255))
    m_draw = ImageDraw.Draw(map_2x)
    for x in range(160, w_2x, 260):
        m_draw.line([(x, 0), (x, h_2x)], fill=(210, 196, 175, 255), width=3)
    for y in range(160, h_2x, 260):
        m_draw.line([(0, y), (w_2x, y)], fill=(210, 196, 175, 255), width=3)

    wall_st_y = 1920
    broad_st_x = 1080
    m_draw.rectangle([broad_st_x - 380, wall_st_y - 480, broad_st_x + 380, wall_st_y + 480], fill=(215, 200, 175, 255), outline=(155, 135, 110, 255), width=8)
    m_draw.line([(0, wall_st_y), (w_2x, wall_st_y)], fill=(110, 95, 78, 255), width=32)
    m_draw.line([(broad_st_x, 0), (broad_st_x, h_2x)], fill=(110, 95, 78, 255), width=32)

    m_draw.rounded_rectangle([broad_st_x + 60, wall_st_y - 440, broad_st_x + 340, wall_st_y - 60], radius=12, fill=(185, 168, 142, 255), outline=(120, 100, 80, 255), width=6)
    m_draw.text((broad_st_x + 200, wall_st_y - 250), "J.P. MORGAN & CO.", fill=(40, 32, 26, 255), font=font_sub_head, anchor="mm")
    m_draw.rounded_rectangle([broad_st_x - 340, wall_st_y - 440, broad_st_x - 60, wall_st_y - 60], radius=12, fill=(185, 168, 142, 255), outline=(120, 100, 80, 255), width=6)
    m_draw.text((broad_st_x - 200, wall_st_y - 250), "US SUB-TREASURY", fill=(40, 32, 26, 255), font=font_sub_head, anchor="mm")

    m_draw.text((280, wall_st_y - 45), "WALL STREET", fill=(245, 235, 220, 255), font=font_sub_head, anchor="mm")
    m_draw.text((broad_st_x + 45, 340), "BROAD STREET", fill=(245, 235, 220, 255), font=font_sub_head, anchor="lm")

    cart_x, cart_y = broad_st_x + 50, wall_st_y + 45

    dossier_2x = Image.new("RGBA", (w_2x, h_2x), (32, 26, 22, 255))
    dos_draw = ImageDraw.Draw(dossier_2x)
    dos_draw.rounded_rectangle([200, 480, w_2x - 200, h_2x - 480], radius=32, fill=(218, 192, 148, 255), outline=(145, 120, 85, 255), width=10)
    dos_draw.rounded_rectangle([200, 360, 880, 520], radius=24, fill=(205, 178, 134, 255), outline=(145, 120, 85, 255), width=8)
    dos_draw.text((540, 440), "CLASSIFIED FILE 1920-WS", fill=(45, 35, 25, 255), font=font_sub_head, anchor="mm")
    dos_draw.rounded_rectangle([w_2x // 2 - 460, 1400, w_2x // 2 + 460, 1680], radius=24, outline=(195, 35, 35, 240), width=12)
    dos_draw.text((w_2x // 2, 1540), "UNSOLVED: COLD CASE", fill=(195, 35, 35, 240), font=font_callout, anchor="mm")
    dos_draw.rectangle([340, 820, 960, 1340], fill=(245, 240, 230, 255), outline=(110, 95, 80, 255), width=6)
    dos_draw.rectangle([370, 850, 930, 1260], fill=(55, 48, 42, 255))
    dos_draw.text((650, 1300), "HORSE-DRAWN CART REMNANTS", fill=(20, 18, 16, 255), font=font_sub_head, anchor="mm")
    det_w, det_h = 840, 1120
    detective = Image.new("RGBA", (det_w, det_h), (0, 0, 0, 0))
    d_draw = ImageDraw.Draw(detective)
    d_draw.ellipse([det_w // 2 - 150, 80, det_w // 2 + 150, 440], fill=(18, 16, 20, 255))
    d_draw.polygon([
        (det_w // 2 - 360, det_h),
        (det_w // 2 - 280, 480),
        (det_w // 2 + 280, 480),
        (det_w // 2 + 360, det_h),
    ], fill=(22, 20, 24, 255))
    d_draw.arc([det_w // 2 - 152, 78, det_w // 2 + 152, 442], start=210, end=350, fill=(255, 195, 75, 230), width=12)

    np.random.seed(1920)
    dust_x = np.random.uniform(80, w_2x - 80, 50)
    dust_y = np.random.uniform(80, h_2x - 80, 50)
    dust_spd = np.random.uniform(0.6, 2.2, 50)

    tmp_raw = output_path.with_suffix(".p1_raw.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(tmp_raw), fourcc, float(fps), (w_final, h_final))

    try:
        for f in range(total_frames):
            t = f / fps
            if t < 7.5:
                shot_p = t / 7.5
                frame_2x = Image.new("RGBA", (w_2x, h_2x), (18, 14, 12, 255))
                f_draw_2x = ImageDraw.Draw(frame_2x)
                for r in range(max(w_2x, h_2x), 0, -80):
                    alpha = int(45 * (1.0 - r / max(w_2x, h_2x)))
                    f_draw_2x.ellipse([w_2x // 2 - r, h_2x // 2 - r, w_2x // 2 + r, h_2x // 2 + r], fill=(220, 145, 55, alpha))

                np_scale = 1.05 + 0.04 * shot_p
                cur_nw, cur_nh = int(np_rotated.width * np_scale), int(np_rotated.height * np_scale)
                scaled_np = np_rotated.resize((cur_nw, cur_nh), Image.Resampling.BILINEAR)
                np_x = (w_2x - cur_nw) // 2 + int(math.sin(t * 0.4) * 35)
                np_y = int(680 + math.cos(t * 0.5) * 25)
                frame_2x.paste(scaled_np, (np_x, np_y), scaled_np)

                tape_y = h_2x - 300
                f_draw_2x.rectangle([0, tape_y, w_2x, tape_y + 110], fill=(24, 20, 18, 255), outline=(212, 143, 56, 255), width=4)
                tape_shift = int((f * 9) % 1200)
                for tx in range(-tape_shift, w_2x + 1200, 720):
                    f_draw_2x.text((tx, tape_y + 55), "JPM +4.2 | US STEEL -1.8 | DOW 1920 | STANDARD OIL +6.5", fill=(245, 205, 115, 255), font=font_sub_head, anchor="lm")

                push = 1.0 + 0.03 * shot_p
                vw, vh = int(1850 / push), int(3288 / push)
                vx = int((w_2x - vw) // 2)
                vy = int(950 - vh // 2)

            elif 7.5 <= t < 15.0:
                shot_p = (t - 7.5) / 7.5
                frame_2x = map_2x.copy()
                f_draw_2x = ImageDraw.Draw(frame_2x)
                blast_rad = int(320 + 280 * min(1.0, shot_p * 1.5))
                for a in range(0, 360, 15):
                    f_draw_2x.arc([cart_x - blast_rad, cart_y - blast_rad, cart_x + blast_rad, cart_y + blast_rad], start=a, end=a + 8, fill=(215, 35, 35, 255), width=8)

                pin_jp = (broad_st_x + 200, wall_st_y - 250)
                pin_sub = (broad_st_x - 200, wall_st_y - 250)
                pin_cart = (cart_x, cart_y)
                f_draw_2x.line([pin_cart, pin_jp], fill=(225, 35, 35, 220), width=6)
                f_draw_2x.line([pin_cart, pin_sub], fill=(225, 35, 35, 220), width=6)
                for px, py in [pin_cart, pin_jp, pin_sub]:
                    f_draw_2x.ellipse([px - 28, py - 28, px + 28, py + 28], fill=(225, 25, 25, 255), outline=(140, 15, 15, 255), width=4)
                    f_draw_2x.ellipse([px - 10, py - 18, px + 10, py - 2], fill=(255, 180, 180, 255))

                push = 1.0 + 0.04 * shot_p
                vw, vh = int(1400 / push), int(2488 / push)
                vx = int(broad_st_x - vw // 2)
                vy = int(wall_st_y - vh // 2 - shot_p * 30)

            elif 15.0 <= t < 22.5:
                shot_p = (t - 15.0) / 7.5
                frame_2x = Image.new("RGBA", (w_2x, h_2x), (14, 10, 8, 255))
                f_draw_2x = ImageDraw.Draw(frame_2x)
                for r in range(max(w_2x, h_2x), 0, -90):
                    alpha = int(55 * (1.0 - r / max(w_2x, h_2x)))
                    f_draw_2x.ellipse([w_2x // 2 - r, h_2x // 2 - r, w_2x // 2 + r, h_2x // 2 + r], fill=(245, 125, 35, alpha))

                det_scale = 1.35 + 0.05 * shot_p
                cur_dw, cur_dh = int(det_w * det_scale), int(det_h * det_scale)
                scaled_det = detective.resize((cur_dw, cur_dh), Image.Resampling.BILINEAR)
                frame_2x.paste(scaled_det, ((w_2x - cur_dw) // 2, h_2x - cur_dh - 80), scaled_det)

                for bi, (bx, by, rot) in enumerate([(420, 1100, -12), (1580, 1400, 15), (960, 800, 6)]):
                    bond = Image.new("RGBA", (480, 280), (242, 235, 218, 240))
                    b_d = ImageDraw.Draw(bond)
                    b_d.rectangle([10, 10, 470, 270], outline=(150, 130, 90, 255), width=4)
                    b_d.text((240, 60), "UNITED STATES BEARER BOND", fill=(30, 26, 20, 255), font=font_sub_head, anchor="mm")
                    b_d.text((240, 160), "$10,000", fill=(185, 35, 35, 255), font=font_headline, anchor="mm")
                    rotated_bond = bond.rotate(rot + math.sin(t * 1.5 + bi) * 4, expand=True, resample=Image.BICUBIC)
                    frame_2x.paste(rotated_bond, (bx, by + int(math.sin(t * 2.0 + bi) * 30)), rotated_bond)

                push = 1.0 + 0.04 * shot_p
                vw, vh = int(1600 / push), int(2844 / push)
                vx = int((w_2x - vw) // 2)
                vy = int(h_2x // 2 - vh // 2)

            else:
                shot_p = (t - 22.5) / 7.5
                frame_2x = dossier_2x.copy()
                push = 1.0 + 0.03 * shot_p
                vw, vh = int(1750 / push), int(3111 / push)
                vx = int((w_2x - vw) // 2)
                vy = int(h_2x // 2 - vh // 2)

            f_draw_2x = ImageDraw.Draw(frame_2x)
            for di in range(len(dust_x)):
                px = int(dust_x[di] + math.sin(t * dust_spd[di]) * 40)
                py = int((dust_y[di] - f * dust_spd[di] * 1.5) % h_2x)
                f_draw_2x.ellipse([px - 4, py - 4, px + 4, py + 4], fill=(255, 215, 120, 160))

            vx = max(0, min(w_2x - vw, vx))
            vy = max(0, min(h_2x - vh, vy))
            zoomed = frame_2x.crop((vx, vy, vx + vw, vy + vh))
            frame_final = zoomed.resize((w_final, h_final), Image.Resampling.LANCZOS)
            f_draw_final = ImageDraw.Draw(frame_final)

            if t < 7.5:
                hw, hh = 620, 72
                hx, hy = (w_final - hw) // 2, 80
                f_draw_final.rounded_rectangle([hx, hy, hx + hw, hy + hh], radius=36, fill=(18, 14, 12, 235), outline=(245, 195, 45, 255), width=3)
                f_draw_final.text((w_final // 2, hy + hh // 2), "NEW YORK  •  SEPTEMBER 16, 1920", fill=(255, 255, 255, 255), font=font_hud_1k, anchor="mm")
            elif 7.5 <= t < 15.0:
                hw, hh = 560, 72
                hx, hy = (w_final - hw) // 2, 80
                f_draw_final.rounded_rectangle([hx, hy, hx + hw, hy + hh], radius=36, fill=(185, 35, 35, 235), outline=(255, 255, 255, 255), width=3)
                f_draw_final.text((w_final // 2, hy + hh // 2), "500 POUNDS TNT DETONATE", fill=(255, 255, 255, 255), font=font_hud_1k, anchor="mm")
            elif 15.0 <= t < 22.5:
                hw, hh = 560, 72
                hx, hy = (w_final - hw) // 2, 80
                f_draw_final.rounded_rectangle([hx, hy, hx + hw, hy + hh], radius=36, fill=(18, 14, 12, 235), outline=(255, 215, 65, 255), width=3)
                f_draw_final.text((w_final // 2, hy + hh // 2), "$30,000,000 VANISHED", fill=(255, 215, 65, 255), font=font_hud_1k, anchor="mm")

            if t >= 22.5:
                cta_sp = remotion_spring(t - 22.5, damping=14.0, stiffness=160.0)
                cw, ch = 960, 100
                cx0 = (w_final - cw) // 2
                cy0 = int(round(h_final * 0.68 + (1.0 - min(1.0, cta_sp)) * 40))
                f_draw_final.rounded_rectangle([cx0, cy0, cx0 + cw, cy0 + ch], radius=24, fill=(18, 14, 12, 245), outline=(245, 195, 45, 255), width=4)
                f_draw_final.text((w_final // 2, cy0 + ch // 2), "WHO PLANTED THE CART? COMMENT YOUR THEORY!", fill=(255, 255, 255, 255), font=font_cta_1k, anchor="mm")

            render_caption_pill(f_draw_final, words, t, w_final, h_final, font_cap_1k, lead_in=0.8)
            arr = cv2.cvtColor(np.array(frame_final), cv2.COLOR_RGBA2BGR)
            writer.write(arr)
    finally:
        writer.release()

    reencode_broadcast_mp4_with_audio(tmp_raw, master_wav, output_path, fps=fps)
    tmp_raw.unlink(missing_ok=True)
    master_wav.unlink(missing_ok=True)
    return output_path


def render_30s_riddle_hd_with_audio(output_path: Path, fps: int = 30) -> Path:
    """Renders 30s broadcast Full HD Riddle demo (The 3 Prisoners Hat Riddle)."""
    from tools.universal_engine import (
        BE_VIETNAM_BOLD,
        build_master_audio_track,
        get_font,
        reencode_broadcast_mp4_with_audio,
        synthesize_studio_speech,
    )
    from tools import riddle_director

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    text = (
        "Three prisoners stand before the fortress wall on the morning of their execution. "
        "The warden offers them one chance to walk free! "
        "He presents five hats: three white, and two black. "
        "Whoever correctly deduces their own hat color will be released! "
        "Prisoner one stays silent. Prisoner two stays silent too. "
        "Suddenly, prisoner three smiles with one hundred percent certainty: "
        "My hat is white! How did he deduce it without turning around?"
    )
    tmp_voice = output_path.with_suffix(".p2_voice.wav")
    _, words = synthesize_studio_speech(text, tmp_voice, voice="kokoro")

    sfx = [("whoosh.wav", 0.5, 0.5), ("pop.wav", 7.2, 0.6)]
    for sec in range(9, 20):
        sfx.append(("click.wav", float(sec), 0.35))
    sfx.extend([("boom.wav", 20.8, 0.70), ("chime.wav", 21.2, 0.60)])
    master_wav = output_path.with_suffix(".p2_master.wav")
    build_master_audio_track(tmp_voice, master_wav, 30.0, lead_in=0.8, sfx_events=sfx, drone_freqs=(55.0, 82.0), drone_vol=0.08)
    tmp_voice.unlink(missing_ok=True)

    w_final, h_final = 1080, 1920
    base_img = np.full((h_final, w_final, 3), (38, 48, 68), dtype=np.uint8)
    spec = riddle_director.RiddleSceneSpec(
        title="3 Prisoners Hat Riddle",
        inventory=[
            riddle_director.InventoryItem(label="White", count=3, color=(255, 255, 255)),
            riddle_director.InventoryItem(label="Black", count=2, color=(40, 40, 40)),
        ],
        characters=[
            riddle_director.CharacterAnchor(id="1", name="P1", x=0.25, y=0.58, badge_label="1", thought_text="?"),
            riddle_director.CharacterAnchor(id="2", name="P2", x=0.52, y=0.58, badge_label="2", thought_text="?"),
            riddle_director.CharacterAnchor(id="3", name="P3", x=0.78, y=0.58, badge_label="3", thought_text="!"),
        ],
        sightlines=[
            riddle_director.SightlineRay(from_id="3", to_id="2"),
            riddle_director.SightlineRay(from_id="2", to_id="1"),
        ],
        countdown_seconds=30.0,
        cta_banner="HOW DID PRISONER 3 DEDUCE IT? COMMENT LOGIC!",
    )
    tmp_raw = output_path.with_suffix(".p2_raw.mp4")
    riddle_director.render_riddle_scene(base_img, spec, tmp_raw, duration=30.0, fps=fps, width=w_final, height=h_final)
    font_cap_1k = get_font(BE_VIETNAM_BOLD, 44)
    _ = font_cap_1k
    reencode_broadcast_mp4_with_audio(tmp_raw, master_wav, output_path, fps=fps)
    tmp_raw.unlink(missing_ok=True)
    master_wav.unlink(missing_ok=True)
    return output_path


def render_30s_stickman_hd_with_audio(output_path: Path, fps: int = 30) -> Path:
    """Renders 30s broadcast Full HD Stickman demo (2 AM Productive Procrastination)."""
    from tools.universal_engine import (
        build_master_audio_track,
        reencode_broadcast_mp4_with_audio,
        synthesize_studio_speech,
    )
    from tools import stickman_engine

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    text = (
        "It is 2:14 in the morning. You have a final exam in six hours that will decide the rest of your life. "
        "Your brain has two logical choices: sleep, or study. "
        "Instead, your prefrontal cortex looks at a dusty sock under your dresser and whispers: "
        "Tonight, we vacuum behind the refrigerator! "
        "Scientists call this Productive Procrastination: your brain will do anything useful just to avoid what matters."
    )
    tmp_voice = output_path.with_suffix(".p3_voice.wav")
    synthesize_studio_speech(text, tmp_voice, voice="am_adam")

    sfx = [
        ("click.wav", 1.8, 0.4),
        ("pop.wav", 8.2, 0.6),
        ("whoosh.wav", 13.5, 0.5),
        ("bubble.wav", 15.2, 0.6),
        ("bell.wav", 22.5, 0.7),
        ("boom.wav", 22.8, 0.5),
    ]
    master_wav = output_path.with_suffix(".p3_master.wav")
    build_master_audio_track(tmp_voice, master_wav, 30.0, lead_in=0.8, sfx_events=sfx, drone_freqs=(60.0, 90.0), drone_vol=0.08)
    tmp_voice.unlink(missing_ok=True)

    tmp_raw = output_path.with_suffix(".p3_raw.mp4")
    app = stickman_engine.StickmanAppearance(accessory="flat_cap")
    pose = stickman_engine.StickmanPoseSpec(pose="thinking", mouth="smile", prop="coffee")
    stickman_engine.render_stickman_scene(
        pose_spec=pose,
        app=app,
        output_path=tmp_raw,
        caption_text="PRODUCTIVE PROCRASTINATION AT 2:14 AM",
        duration=30.0,
        fps=fps,
        width=1080,
        height=1920,
    )
    reencode_broadcast_mp4_with_audio(tmp_raw, master_wav, output_path, fps=fps)
    tmp_raw.unlink(missing_ok=True)
    master_wav.unlink(missing_ok=True)
    return output_path


def render_30s_hybrid_hd_with_audio(output_path: Path, fps: int = 30) -> Path:
    """Renders 30s broadcast Full HD Hybrid demo (Quantum Vault 7 Heist)."""
    from tools.universal_engine import (
        build_master_audio_track,
        reencode_broadcast_mp4_with_audio,
        synthesize_studio_speech,
    )
    from tools import hybrid_engine, riddle_director, stickman_engine

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    text = (
        "Deep beneath Zurich, twenty stories underground, sits Vault Seven. "
        "It holds sixty billion dollars in encrypted bearer bonds protected by a quantum biometric scanner. "
        "In front of the vault stands the rogue hacker, Zero. "
        "Suddenly, the alarm triggers: thirty seconds until permanent lockdown! "
        "Zero inputs the bypass code, syncs the optical pulse, and the vault door unlocks!"
    )
    tmp_voice = output_path.with_suffix(".p4_voice.wav")
    synthesize_studio_speech(text, tmp_voice, voice="am_adam")

    sfx = [
        ("whoosh.wav", 0.5, 0.6),
        ("click.wav", 5.2, 0.4),
        ("impact.wav", 12.0, 0.8),
        ("whoosh.wav", 18.0, 0.6),
        ("boom.wav", 22.5, 0.85),
        ("chime.wav", 22.8, 0.70),
    ]
    master_wav = output_path.with_suffix(".p4_master.wav")
    build_master_audio_track(tmp_voice, master_wav, 30.0, lead_in=0.8, sfx_events=sfx, drone_freqs=(42.0, 84.0), drone_vol=0.14)
    tmp_voice.unlink(missing_ok=True)

    tmp_raw = output_path.with_suffix(".p4_raw.mp4")
    bg_img = np.full((1920, 1080, 3), (18, 24, 36), dtype=np.uint8)
    pose = stickman_engine.StickmanPoseSpec(pose="pointing", prop="magnifying_glass")
    app = stickman_engine.StickmanAppearance(accessory="fedora")
    riddle_spec = riddle_director.RiddleSceneSpec(
        title="Vault 7",
        inventory=[
            riddle_director.InventoryItem(label="Keys", count=3),
            riddle_director.InventoryItem(label="Locks", count=1),
        ],
        characters=[
            riddle_director.CharacterAnchor(id="1", name="Zero", x=0.5, y=0.52, badge_label="1", thought_text="!"),
        ],
        sightlines=[],
        countdown_seconds=30.0,
        cta_banner="COULD YOU BYPASS VAULT 7? COMMENT BELOW!",
    )
    hybrid_engine.render_hybrid_scene(
        bg_image=bg_img,
        pose_spec=pose,
        appearance=app,
        riddle_spec=riddle_spec,
        output_path=tmp_raw,
        duration=30.0,
        fps=fps,
        width=1080,
        height=1920,
    )
    reencode_broadcast_mp4_with_audio(tmp_raw, master_wav, output_path, fps=fps)
    tmp_raw.unlink(missing_ok=True)
    master_wav.unlink(missing_ok=True)
    return output_path


def generate_all_4_archetype_demos(demo_dir: Path) -> Dict[str, Path]:
    """Generates all 4 archetypes as 30s broadcast Full HD MP4s with audio strictly inside demo_dir."""
    demo_dir = Path(demo_dir)
    demo_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    results["photobook"] = render_30s_photobook_hd_with_audio(demo_dir / "demo_01_photobook_30s_hd.mp4")
    results["riddle"] = render_30s_riddle_hd_with_audio(demo_dir / "demo_02_riddle_30s_hd.mp4")
    results["stickman"] = render_30s_stickman_hd_with_audio(demo_dir / "demo_03_stickman_30s_hd.mp4")
    results["hybrid"] = render_30s_hybrid_hd_with_audio(demo_dir / "demo_04_hybrid_30s_hd.mp4")
    return results
