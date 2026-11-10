#!/usr/bin/env python3
"""FrameForge Unified 3D & Spatial Studio (studio_3d.py).

Single entry point for:
  1. Depth-Anything-V2 + DepthFlow / Native 3D Perspective Shader Engine
  2. Procedural 3D Mesh (.obj) Generation & Native/Blender 3D Mesh Video Rendering
  3. 5-Genre Visual Style Profiles (3D CGI, Editorial Minimalist, Editorial Explainer, Urban Noir, 35mm Documentary)
  4. SOTA 3D Camera Trajectories:
     - vertigo      (Hitchcock Dolly-Zoom: camera dollys in while FOV widens)
     - spiral       (3D Helical Orbit + Vertical Rise)
     - orbit        (360-degree Elliptical 3D Parallax)
     - roll         (Dynamic 3D Roll + Sweeping Pan)
     - spatial_drift (Minimalist 3D Spatial Drift + Rack-Focus DoF)
     - dolly        (Deep 3D Z-Axis Push-In)

Usage:
  # Render a 3D Vertigo Dolly-Zoom from an existing image:
  python tools/studio_3d.py --image path/to/scene.jpg --preset vertigo -o scene_3d.mp4

  # Generate a procedural 3D model (.obj) and render a 3D animated clip:
  python tools/studio_3d.py --model-3d neural_core --export-obj output/neural_core.obj --preset spiral -o output/neural_3d.mp4

  # Convert a 2D image into a 3D displaced relief .obj mesh and render 3D orbit:
  python tools/studio_3d.py --image path/to/scene.jpg --model-3d depth_mesh --export-obj output/relief.obj -o output/relief_3d.mp4

  # Generate a new 3D CGI scene from a prompt and animate it in 3D:
  python tools/studio_3d.py --prompt "Glowing neural network inside a glass brain" --genre 3d_cgi --preset spiral -o brain_3d.mp4

  # List all genres & 3D capabilities:
  python tools/studio_3d.py --status
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
YT_ROOT = TOOLS_DIR.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
if str(YT_ROOT) not in sys.path:
    sys.path.insert(0, str(YT_ROOT))

from tools import visual_engine  # noqa: E402
from tools.genre_director import GENRE_REGISTRY, get_genre_profile, list_available_genres  # noqa: E402


def print_studio_status() -> None:
    print("=" * 74)
    print("  FRAMEFORGE 3D & MULTI-GENRE VISUAL STUDIO STATUS")
    print("=" * 74)
    print("  [ACTIVE] 1. Depth-Anything-V2 Monocular Depth Estimation (Apple Metal / Optical Salience)")
    print("  [ACTIVE] 2. DepthFlow GLSL + Native 3D Perspective Displacement Engine (1080x1920 @ 30/60fps)")
    print("  [ACTIVE] 3. SOTA 3D Camera Presets: vertigo, spiral, orbit, roll, spatial_drift, dolly")
    print("  [ACTIVE] 4. Procedural 3D .obj Mesh Generator & Native PBR/Wireframe 3D Mesh Renderer")
    print("              Archetypes: neural_core, labyrinth, depth_mesh, custom .obj files")
    print("  [ACTIVE] 5. FLUX.3 Image Klein Q8 Neural Generator + Genre Prompt Stylizer")
    print("  [ACTIVE] 6. Multi-Plane Foreground/Background Layer Separator")
    if visual_engine.BlenderBridge.is_available():
        print(f"  [ACTIVE] 7. Blender 3D CLI Bridge ({visual_engine.BlenderBridge.get_blender_path()})")
    else:
        print("  [SELF-HEALING] 7. Blender 3D Bridge -> Active Native 3D .obj Mesh Perspective Engine")
        print("                    (Optional external Blender: `brew install --cask blender`)")
    print("-" * 74)
    print(list_available_genres())


def main() -> int:
    ap = argparse.ArgumentParser(description="FrameForge Unified 3D & Spatial Studio")
    ap.add_argument("--status", action="store_true", help="Show 3D capabilities and available genres")
    ap.add_argument("--list-genres", action="store_true", help="List all available visual genres and palettes")
    ap.add_argument("--list-presets", action="store_true", help="List all SOTA 3D camera trajectory presets")
    ap.add_argument("--blender-status", action="store_true", help="Show Blender 3D CLI bridge status")
    ap.add_argument("--image", "-i", type=Path, help="Input 2D image to convert to 3D video or 3D relief mesh")
    ap.add_argument("--prompt", "-p", type=str, help="Generate fresh image with Genre Stylizer before 3D render")
    ap.add_argument("--genre", "-g", type=str, default="3d_cgi", choices=list(GENRE_REGISTRY.keys()), help="Visual genre profile")
    ap.add_argument(
        "--preset",
        type=str,
        default="spiral",
        choices=["vertigo", "spiral", "orbit", "roll", "spatial_drift", "dolly", "circle", "horizontal", "vertical"],
        help="3D camera trajectory",
    )
    ap.add_argument(
        "--model-3d",
        type=str,
        default=None,
        help="Render a 3D .obj mesh model ('neural_core', 'labyrinth', 'depth_mesh', or path to an .obj file)",
    )
    ap.add_argument("--export-obj", type=Path, default=None, help="Optional output path to save generated Wavefront .obj 3D model")
    ap.add_argument("--duration", "-d", type=float, default=3.5, help="Clip duration in seconds")
    ap.add_argument("--fps", type=int, default=30, help="Frame rate (30 or 60)")
    ap.add_argument("--width", type=int, default=1080, help="Output width (default: 1080)")
    ap.add_argument("--height", type=int, default=1920, help="Output height (default: 1920)")
    ap.add_argument("--output", "-o", type=Path, default=YT_ROOT / "channel_assets" / "studio_3d_preview.mp4", help="Output MP4 path")
    args = ap.parse_args()

    if args.status or args.list_genres or args.list_presets or args.blender_status:
        print_studio_status()
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)

    # Path A: 3D Mesh (.obj) Modeling & Rendering
    if args.model_3d or args.export_obj:
        model_spec = args.model_3d or "neural_core"
        if Path(model_spec).suffix.lower() == ".obj" and Path(model_spec).exists():
            obj_path = Path(model_spec).resolve()
        else:
            obj_path = (args.export_obj or args.output.with_suffix(".obj")).resolve()
            print(f"=== [3D Studio] Generating 3D Mesh Model ({model_spec}) -> {obj_path.name} ===")
            visual_engine.generate_procedural_3d_obj(
                archetype=model_spec,
                output_obj=obj_path,
                image_path=args.image.resolve() if args.image else None,
            )

        print(f"=== [3D Studio] Rendering 3D Mesh Animation (preset={args.preset}, duration={args.duration}s) ===")
        ok = visual_engine.BlenderBridge.render_mesh(
            obj_path=obj_path,
            output_mp4=args.output.resolve(),
            duration=args.duration,
            fps=args.fps,
            width=args.width,
            height=args.height,
            preset=args.preset,
        )
        if ok:
            print(f"=== [SUCCESS] 3D Mesh Video Ready: {args.output} (Model: {obj_path}) ===")
            return 0
        return 1

    # Path B: Image / Prompt -> 3D Camera Trajectory Video
    img_path = args.image
    if args.prompt:
        from tools.genre_director import format_genre_prompt
        prof = get_genre_profile(args.genre)
        styled_prompt = format_genre_prompt(args.prompt, genre_key=prof.id)
        img_path = args.output.with_suffix(".jpg")
        print(f"=== [3D Studio] Generating '{prof.name}' Concept Frame ===")
        print(f"  Prompt: {styled_prompt}")
        visual_engine.generate_scene_image(styled_prompt, img_path, width=768, height=1360)

    if not img_path or not img_path.exists():
        print("Error: Provide --image path/to/img.jpg, --prompt '...', or --model-3d <archetype> (or run with --status).")
        return 1

    print(f"=== [3D Studio] Rendering 3D Camera Trajectory: {args.preset.upper()} ({args.duration}s @ {args.fps}fps) ===")
    ok = visual_engine.render_depthflow_scene(
        src_img_path=img_path.resolve(),
        output_path=args.output.resolve(),
        preset=args.preset,
        duration=args.duration,
        fps=args.fps,
        target_w=args.width,
        target_h=args.height,
    )
    if ok:
        q = visual_engine.verify_motion_quality(args.output)
        print(f"=== [SUCCESS] 3D Video Ready: {args.output} ===")
        print(f"  Optical Audit: Score={q.get('score')} | Precision={q.get('precision')} | Recall={q.get('recall')} | Flow={q.get('mean_flow_px')}px")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
