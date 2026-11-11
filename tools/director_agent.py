"""tools/director_agent.py — Showrunner Director Agent (Option A & B).

The creative conductor that directs the entire video end-to-end:
1. Spatial Blocking & Mise-en-scène:
   - Character positioning in 3D frame ([X, Y] anchors).
   - Movement vectors (where characters, animals, and props move: e.g. dog walking into shadows).
   - Staging, wardrobe, and hand props.
2. Directional Lighting & Shadow:
   - Key light angle, dominant side (left vs right), and brightness ratio.
   - Chiaroscuro shadow falloff and fill illumination.
   - Colored rim/kicker light to separate silhouettes.
3. 3D Camera Optics & Trajectories:
   - Camera moves: vertigo (dolly-zoom), spiral, orbit, dolly, spatial drift.
   - Lens focal length, depth of field, and safe-zone anchors (0.44–0.76).
4. Audio & Musical Direction:
   - Score movement & mood transitions per scene.
   - Word-aligned Foley sound cues with stereo spatialization (L/C/R).
   - Narrator vocal delivery cadence and emotional tone.

Produces the durable `DirectorManifest` and Markdown Pitch Board for creator review.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.channel_config import load_channel_config
from tools.errors import MissingInputError
from tools.genre_director import get_genre_profile

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class SpatialBlocking:
    """Mise-en-scène spatial staging and physical blocking."""
    character_position: str        # e.g., "seated stage-left at [0.35, 0.52], facing stage-right"
    posture_and_wardrobe: str      # e.g., "charcoal button-down shirt with rolled sleeves, leaning forward"
    movement_vector: str           # e.g., "right hand slides the ledger across desk; background dog trots into shadow stage-left"
    focal_props: str               # e.g., "antique brass scales resting on dark oak ledger"
    background_staging: str        # e.g., "deep mahogany archive bookshelves with warm amber dust motes"


@dataclass
class LightingDirection:
    """Directional lighting, shadow dominance, and volumetric atmosphere."""
    key_light_source: str          # e.g., "elevated window stage-left at 45-degree angle"
    dominant_side: str             # e.g., "stage-left illuminated at 85% brightness; stage-right in shadow"
    shadow_ratio: str              # e.g., "4:1 chiaroscuro contrast across facial contour"
    rim_light: str                 # e.g., "subtle cyan rim light tracing shoulders and hair"
    ambient_fill: str              # e.g., "15% warm bounce fill from polished desk surface"


@dataclass
class CameraDirection:
    """Cinematic camera vantage point, 3D trajectory, and safe zones."""
    shot_scale: str                # e.g., "medium close-up" / "macro detail" / "wide atmospheric"
    trajectory_preset: str         # e.g., "depthflow_vertigo", "depthflow_spiral", "depthflow_orbit", "spatial_drift"
    motion_rationale: str          # e.g., "Hitchcock dolly-zoom to physically manifest cognitive realization"
    lens_optics: str               # e.g., "35mm anamorphic prime lens, shallow depth-of-field, f/2.0"
    safe_zone_anchor: float        # e.g., 0.52 (centered inside 0.30–0.58 safe visual band)


@dataclass
class SoundDirection:
    """Acoustic scoring, stereo Foley placement, and narrator tone."""
    score_movement: str            # e.g., "low 45Hz cello drone transitioning to tense staccato piano"
    foley_cue: str                 # e.g., "felt desk thud + brass coin slide on word 'identical'"
    stereo_pan: float              # -1.0 (hard left) to +1.0 (hard right), 0.0 (center)
    narrator_tone: str             # e.g., "measured hushed intrigue with sharp punchy accent on 'identical'"


@dataclass
class SceneDirectionSpec:
    """Complete directorial breakdown for a single scene."""
    scene_index: int
    narrative_beat: str
    text: str
    duration_s: float
    spatial: SpatialBlocking
    lighting: LightingDirection
    camera: CameraDirection
    sound: SoundDirection
    synthesized_prompt: str
    overlay: Optional[Dict[str, Any]] = None
    stat_card: Optional[Dict[str, str]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DirectorManifest:
    """Comprehensive showrunner treatment for an entire video production."""
    video_id: str
    topic: str
    genre: str
    channel: str
    logline: str
    director_vision: str
    color_palette: Dict[str, str]
    soundtrack_theme: str
    scenes: List[SceneDirectionSpec] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def format_director_pitch(self) -> str:
        """Renders an inspectable Markdown pitch board for creator review (Option B)."""
        lines = [
            f"# 🎬 SHOWRUNNER DIRECTORIAL TREATMENT — {self.video_id}: {self.topic}",
            f"**Channel:** {self.channel} | **Aesthetic Genre:** {self.genre}",
            f"**Logline:** {self.logline}",
            f"**Director's Vision:** {self.director_vision}",
            f"**Soundtrack Theme:** {self.soundtrack_theme}",
            f"**Palette:** Primary `{self.color_palette.get('primary', '#FFC83D')}` | Secondary `{self.color_palette.get('secondary', '#6CE8DE')}` | Accent `{self.color_palette.get('accent', '#FF9F1C')}`",
            "",
            "---",
            "## 🎞️ SCENE-BY-SCENE DIRECTORIAL BLOCKING & LIGHTING",
            "",
        ]

        for sc in self.scenes:
            pan_desc = "center" if abs(sc.sound.stereo_pan) < 0.05 else (f"{int(abs(sc.sound.stereo_pan)*100)}% {'left' if sc.sound.stereo_pan < 0 else 'right'}")
            lines.extend([
                f"### Scene {sc.scene_index:02d} [{sc.narrative_beat}] — ~{sc.duration_s:.1f}s",
                f"> *\"{sc.text}\"*",
                "",
                f"- 📍 **Spatial Blocking & Movement:** {sc.spatial.character_position}. {sc.spatial.posture_and_wardrobe}. **Action:** {sc.spatial.movement_vector}.",
                f"- 💡 **Lighting & Shadow:** **Source:** {sc.lighting.key_light_source}. **Dominance:** {sc.lighting.dominant_side}. **Ratio:** {sc.lighting.shadow_ratio}. **Rim:** {sc.lighting.rim_light}.",
                f"- 🎥 **Camera & Optics:** **Shot:** {sc.camera.shot_scale}. **Trajectory:** `{sc.camera.trajectory_preset}` ({sc.camera.motion_rationale}). **Optics:** {sc.camera.lens_optics} [Safe-Y: {sc.camera.safe_zone_anchor:.2f}].",
                f"- 🎧 **Sound & Foley:** **Score:** {sc.sound.score_movement}. **SFX:** {sc.sound.foley_cue} (Pan: {pan_desc}). **Voice Delivery:** {sc.sound.narrator_tone}.",
                f"- 🎨 **Synthesized Prompt:** `{sc.synthesized_prompt}`",
                "",
            ])

        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Showrunner Director Implementation
# --------------------------------------------------------------------------- #

class ShowrunnerDirector:
    """Synthesizes physical mise-en-scène, directional lighting, 3D camera moves, and audio scoring."""

    def __init__(
        self,
        channel: str = "default",
        genre: str = "3d_cgi",
    ):
        self.channel_name = channel
        try:
            self.channel_cfg = load_channel_config(channel)
        except Exception:
            self.channel_cfg = None

        self.genre_key = genre
        self.genre_profile = get_genre_profile(genre)

    def direct_video(
        self,
        script_scenes: List[Dict[str, Any]],
        dossier: Dict[str, Any],
        video_id: str = "SH-01",
        topic: str = "",
    ) -> DirectorManifest:
        """Directs the complete visual and acoustic performance for the video."""
        if not script_scenes:
            raise MissingInputError(
                stage="director_agent",
                artifact=video_id,
                cause="Cannot direct video with zero script scenes.",
            )

        logline = self._synthesize_logline(topic, dossier)
        vision = self._synthesize_vision(topic, self.genre_profile.name, dossier)
        sound_theme = self._synthesize_sound_theme(topic, dossier)
        palette = self.genre_profile.color_palette

        directed_scenes: List[SceneDirectionSpec] = []
        total_scenes = len(script_scenes)

        for idx, raw_scene in enumerate(script_scenes, start=1):
            beat = self._classify_beat(idx, total_scenes, raw_scene)
            text = str(raw_scene.get("text", "")).strip()
            dur = float(raw_scene.get("duration", 3.6))

            spatial = self._direct_spatial_blocking(idx, total_scenes, beat, text, dossier)
            lighting = self._direct_lighting(idx, total_scenes, beat, spatial)
            camera = self._direct_camera(idx, total_scenes, beat, spatial)
            sound = self._direct_sound(idx, total_scenes, beat, text, dossier)

            prompt = self._synthesize_directed_prompt(
                spatial=spatial,
                lighting=lighting,
                camera=camera,
                beat=beat,
                genre=self.genre_profile,
            )

            overlay = raw_scene.get("overlay")
            stat_card = raw_scene.get("stat_card")

            directed_scenes.append(
                SceneDirectionSpec(
                    scene_index=idx,
                    narrative_beat=beat,
                    text=text,
                    duration_s=dur,
                    spatial=spatial,
                    lighting=lighting,
                    camera=camera,
                    sound=sound,
                    synthesized_prompt=prompt,
                    overlay=overlay,
                    stat_card=stat_card,
                )
            )

        return DirectorManifest(
            video_id=video_id,
            topic=topic,
            genre=self.genre_key,
            channel=self.channel_name,
            logline=logline,
            director_vision=vision,
            color_palette=palette,
            soundtrack_theme=sound_theme,
            scenes=directed_scenes,
        )

    # ----------------------------------------------------------------------- #
    # Narrative & Directorial Intelligence
    # ----------------------------------------------------------------------- #

    def _classify_beat(self, idx: int, total: int, scene: Dict[str, Any]) -> str:
        """Identifies dramatic function in the 8–12 scene retention structure."""
        if idx == 1:
            return "Visceral Hook"
        if idx == 2:
            return "Empirical Context"
        if idx == 3:
            return "Experimental Setup"
        if idx == total - 1:
            return "Action Ask & Reset"
        if idx == total:
            return "Infinite Loop Bridge"
        if idx >= total - 3:
            return "Psychological Mechanism"
        return "Complication & Stakes"

    def _synthesize_logline(self, topic: str, dossier: Dict[str, Any]) -> str:
        stat = dossier.get("quantitative_stat") or "statistically proven"
        broken = dossier.get("broken_assumption") or f"You assume control, but {topic} governs your choices."
        return f"{topic}: {broken} Backed by {dossier.get('primary_researchers', 'empirical research')} ({stat})."

    def _synthesize_vision(self, topic: str, genre_name: str, dossier: Dict[str, Any]) -> str:
        return (
            f"An intimate psychological thriller aesthetic in {genre_name}. "
            f"Grounding abstract decision theory in tangible physical textures, dramatic directional chiaroscuro, "
            f"and purposeful camera choreography that mirrors the cognitive trap of {topic}."
        )

    def _synthesize_sound_theme(self, topic: str, dossier: Dict[str, Any]) -> str:
        return (
            f"Analog suspense score anchored at 45Hz sub-bass, Mid/Side vocal pocket ducking, "
            f"and tactile physical Foley reflecting {topic}."
        )

    # ----------------------------------------------------------------------- #
    # 1. Spatial Blocking (Characters, Directions, Movement, Staging)
    # ----------------------------------------------------------------------- #

    def _direct_spatial_blocking(
        self,
        idx: int,
        total: int,
        beat: str,
        text: str,
        dossier: Dict[str, Any],
    ) -> SpatialBlocking:
        """Determines where characters stand, how they are posed, and movement vectors."""
        t_low = text.lower()
        protagonist = dossier.get("protagonist") or "a thoughtful 30-year-old analyst in a crisp dark wool sweater"

        # Movement and action blocking
        if idx == 1:
            topic_clean = str(dossier.get("topic", "")).lower()
            chapter_clean = str(dossier.get("chapter_title", "")).lower()
            pos = "standing mid-ground stage-left at [0.36, 0.50], angled 30 degrees toward frame-center"
            wardrobe = f"{protagonist}, frozen in place with intense questioning eye contact"

            if "simulation" in topic_clean or "glass render" in chapter_clean:
                action = "staring through an architectural glass window pane, observing a subtle refractive glitch in the morning light"
                props = "a digital stylus and a glass pane catching angled morning sunbeams"
                bg = "modernist high-rise studio with floor-to-ceiling glass looking out over a foggy skyline"
            elif "choice" in topic_clean or "twenty-four" in chapter_clean or "jam" in topic_clean:
                action = "standing before a vast display of twenty-four identical glass jars, hand hovering in complete hesitation"
                props = "twenty-four neatly arranged artisanal glass jars on floating minimalist oak shelves"
                bg = "sunlit gourmet market aisle with clean architectural wood shelving receding into soft focus"
            elif "fresh start" in topic_clean or "monday ledger" in chapter_clean or "calendar" in topic_clean:
                action = "turning the crisp first page of a fresh black-linen desk ledger, pen poised above the empty line"
                props = "an unblemished Monday calendar page, a brass mechanical pen, and an analog desk clock"
                bg = "airy corner office with warm morning sun illuminating a clean oak desk surface"
            elif "depletion" in topic_clean or "empty tank" in chapter_clean or "willpower" in topic_clean:
                action = "resting forehead against one hand beside an empty ceramic mug, watching neon city rain streak down the window"
                props = "an empty dark ceramic espresso mug and a stack of sorted case files illuminated by cool screen glow"
                bg = "late-night urban desk overlooking rain-slicked streets bathed in amber and cyan neon reflection"
            elif "implementation" in topic_clean or "monday trap" in chapter_clean or "intentions" in topic_clean:
                action = "pinning a handwritten index card reading 'IF 8:00 AM, THEN BEGIN' onto a corkboard above the desk"
                props = "a yellow index card with clear conditional rules, pushpins, and a ticking mechanical stopwatch"
                bg = "focused minimalist workspace with clean white walls and a single warm directional task lamp"
            elif "loss" in topic_clean or "coin" in topic_clean:
                action = "holding a single vintage silver coin at eye level, hesitating as fingers refuse to let it go"
                props = "a silver fifty-cent coin and a leather wager notebook"
                bg = "quiet wood-paneled archive illuminated by low-angled tungsten library lamps"
            elif "hedonic" in topic_clean or "paradise" in chapter_clean:
                action = "standing in the center of an opulent high-ceilinged room, looking around with a numb neutral expression"
                props = "an unread congratulatory telegram and a heavy brass desk paperweight"
                bg = "grand sunlit conservatory with marble floors and lush palm silhouettes"
            else:
                action = "holding an everyday object, glancing up suddenly; in the deep background, blurred figures cross right to left"
                props = "a steaming ceramic mug and a scatter of unopened mail"
                bg = "dimly lit apartment hallway with morning light cutting through tall vertical blinds"

        elif "dog" in t_low or "animal" in t_low:
            pos = "subject seated at table edge stage-left at [0.32, 0.52]"
            wardrobe = f"{protagonist}, looking downward with guarded expression"
            action = "subject's hand drops toward the floor; in background stage-right, a sleek dog trots into the deep shadows"
            props = "a brass key and an unrolled architectural sketch"
            bg = "quiet mid-century studio with exposed brick and dusty shafts of sunlight"

        elif "coin" in t_low or "money" in t_low or "bet" in t_low or "loss" in t_low:
            pos = "subject seated at dark oak desk stage-right at [0.65, 0.48], leaning forward"
            wardrobe = f"{protagonist}, sleeves rolled to the forearms with fingers hovering over the surface"
            action = "sliding a single brass token across the polished wood grain from right to left"
            props = "two antique betting ledgers and a balanced mechanical brass scale"
            bg = "vintage 1970s laboratory carrel with green shaded banker's lamp"

        elif "brain" in t_low or "neural" in t_low or "scan" in t_low or "amygdala" in t_low:
            pos = "subject framed in profile stage-left at [0.34, 0.52]"
            wardrobe = f"{protagonist}, head tilted slightly upward in contemplation"
            action = "silhouette motionless; in background right, floating 3D blueprint projections slowly rotate"
            props = "luminescent architectural neural blueprints glowing in warm amber"
            bg = "dark academic amphitheater with towering chalkboard diagrams receding into gloom"

        elif beat == "Action Ask & Reset":
            pos = "subject framed center-left at [0.42, 0.49], upright and direct"
            wardrobe = f"{protagonist}, calm resolved demeanor making grounded eye contact"
            action = "closing a leather-bound notebook and placing a brass pen down with deliberate finality"
            props = "open leather notebook with handwritten notes and a clean porcelain saucer"
            bg = "warmly illuminated study with floor-to-ceiling wooden bookshelves"

        elif beat == "Infinite Loop Bridge":
            pos = "subject standing stage-left at [0.35, 0.51], turning back toward the doorway"
            wardrobe = f"{protagonist}, coat draped over one arm, caught in mid-motion"
            action = "stepping through the threshold as the door begins to swing closed from right to left"
            props = "brass door handle and a coat hook on dark paneled wall"
            bg = "threshold between dimly lit study and brightly sunlit corridor"

        else:
            # Alternating rhythm for middle scenes
            if idx % 2 == 0:
                pos = "subject standing stage-right at [0.62, 0.51], facing stage-left"
                action = "pacing two paces forward, pausing as realization dawns"
            else:
                pos = "subject seated stage-left at [0.38, 0.50], facing forward"
                action = "tracing a finger across handwritten experimental trial results"
            wardrobe = f"{protagonist}, deep in analytical thought"
            props = "a vintage magnifying loupe and sorted statistical survey sheets"
            bg = "quiet archive reading room flanked by towering filing drawers"

        return SpatialBlocking(
            character_position=pos,
            posture_and_wardrobe=wardrobe,
            movement_vector=action,
            focal_props=props,
            background_staging=bg,
        )

    # ----------------------------------------------------------------------- #
    # 2. Directional Lighting & Shadows (Angles, Brightness Side, Falloff)
    # ----------------------------------------------------------------------- #

    def _direct_lighting(
        self,
        idx: int,
        total: int,
        beat: str,
        spatial: SpatialBlocking,
    ) -> LightingDirection:
        """Choreographs light source direction, dominant brightness side, and shadow ratio."""
        # Key light matches spatial composition (illuminate the face from the open side)
        is_stage_left = "stage-left" in spatial.character_position

        if is_stage_left:
            source = "tall window stage-left at a 45-degree angle"
            dominance = "stage-left illuminated at 85% brightness; stage-right side of face in shadow"
        else:
            source = "high directional lantern on stage-right at a 40-degree angle"
            dominance = "stage-right illuminated at 80% brightness; stage-left side of face in shadow"

        if idx == 1:
            ratio = "3:1 high-contrast documentary chiaroscuro"
            rim = "soft cyan edge light tracing the left shoulder and jawline"
            fill = "10% subtle ambient bounce from the floor"
        elif beat in {"Experimental Setup", "Complication & Stakes"}:
            ratio = "4:1 dramatic shadow ratio emphasizing cognitive tension"
            rim = "warm amber rim light separating silhouette from dark oak backdrop"
            fill = "15% warm desk bounce"
        elif "neural" in spatial.focal_props or "blueprint" in spatial.focal_props:
            ratio = "5:1 moody cinematic contrast with internal volumetric glow"
            rim = "luminescent golden backlight outlining the cranial silhouette"
            fill = "5% ultra-low fill"
        else:
            ratio = "3:1 balanced natural portrait lighting"
            rim = "subtle warm kicker light along the right collar"
            fill = "20% soft diffused daylight bounce"

        return LightingDirection(
            key_light_source=source,
            dominant_side=dominance,
            shadow_ratio=ratio,
            rim_light=rim,
            ambient_fill=fill,
        )

    # ----------------------------------------------------------------------- #
    # 3. 3D Camera Optics & Trajectories
    # ----------------------------------------------------------------------- #

    def _direct_camera(
        self,
        idx: int,
        total: int,
        beat: str,
        spatial: SpatialBlocking,
    ) -> CameraDirection:
        """Assigns 3D camera trajectory, focal optics, and safe-zone anchors."""
        if idx == 1:
            scale = "medium close-up"
            traj = "depthflow_vertigo"
            rationale = "Hitchcock dolly-zoom to physically induce disorientation on the hook"
            anchor = 0.50
        elif beat == "Empirical Context":
            scale = "medium shot"
            traj = "depthflow_orbit"
            rationale = "360-degree rotational inspection of the archival experimental setting"
            anchor = 0.48
        elif beat == "Experimental Setup":
            scale = "macro detail insert"
            traj = "depthflow_dolly"
            rationale = "slow, deliberate push-in toward the tactile experimental apparatus"
            anchor = 0.52
        elif beat == "Complication & Stakes":
            scale = "medium close-up"
            traj = "depthflow_spiral"
            rationale = "helical camera spiral rising upward as psychological pressure builds"
            anchor = 0.49
        elif beat == "Psychological Mechanism":
            scale = "profile close-up"
            traj = "depthflow_vertigo"
            rationale = "dolly-zoom at moment of realization when mechanism is revealed"
            anchor = 0.50
        elif beat == "Action Ask & Reset":
            scale = "intimate portrait"
            traj = "spatial_drift"
            rationale = "calm, grounded spatial drift as viewer receives direct instruction"
            anchor = 0.47
        else:
            scale = "medium cinematic"
            traj = "depthflow_spiral" if idx % 2 == 0 else "depthflow_orbit"
            rationale = "dynamic parallax perspective shifting across visual depth planes"
            anchor = 0.50

        lens = "35mm anamorphic prime lens, shallow depth-of-field, f/2.0 aperture"
        return CameraDirection(
            shot_scale=scale,
            trajectory_preset=traj,
            motion_rationale=rationale,
            lens_optics=lens,
            safe_zone_anchor=anchor,
        )

    # ----------------------------------------------------------------------- #
    # 4. Audio & Musical Direction (Score, Foley, Panning, Tone)
    # ----------------------------------------------------------------------- #

    def _direct_sound(
        self,
        idx: int,
        total: int,
        beat: str,
        text: str,
        dossier: Dict[str, Any],
    ) -> SoundDirection:
        """Plans acoustic score energy, word-aligned Foley sound, and stereo panning."""
        if idx == 1:
            score = "isolated 45Hz sub-bass felt drone; silence on the first three words"
            foley = "heavy felt sub-thud on hook punchline + subtle tape hiss"
            pan = 0.0
            tone = "hushed, urgent inquiry drawing the listener in"
        elif beat == "Empirical Context":
            score = "low analog synthesizer bed entering softly with warm tape warmth"
            foley = "mechanical film camera shutter transient on study citation"
            pan = 0.25
            tone = "measured, authoritative historical documentation"
        elif beat == "Experimental Setup":
            score = "staccato piano ostinato beginning in minor third intervals"
            foley = "tactile wooden desk tap and sliding brass weight"
            pan = -0.30
            tone = "precise, analytical presentation of the trial setup"
        elif beat == "Psychological Mechanism":
            score = "rising resonant low-pass filter opening as tension peaks"
            foley = "metallic resonance chime on neural revelation"
            pan = 0.15
            tone = "intense clarity revealing the biological trigger"
        elif beat == "Action Ask & Reset":
            score = "resolving warm harmonic pad; music ducks 40% for direct address"
            foley = "paper turn and soft ceramic cup placement"
            pan = 0.0
            tone = "grounded, pragmatic second-person behavioral reset"
        elif beat == "Infinite Loop Bridge":
            score = "score filters down to fundamental sub-frequency, leading directly into scene 1"
            foley = "gentle door latch click fading into silence"
            pan = -0.20
            tone = "intriguing unfinished thought bridging the infinite loop"
        else:
            score = "pulsing heartbeat sub-bass rhythm under steady synthetic strings"
            foley = "low-pass whoosh transition on visual scene cut"
            pan = -0.15 if idx % 2 == 0 else 0.15
            tone = "compelling narrative momentum"

        return SoundDirection(
            score_movement=score,
            foley_cue=foley,
            stereo_pan=pan,
            narrator_tone=tone,
        )

    # ----------------------------------------------------------------------- #
    # 5. Synthesize 6-Layer Multi-Modal Prompt
    # ----------------------------------------------------------------------- #

    def _synthesize_directed_prompt(
        self,
        spatial: SpatialBlocking,
        lighting: LightingDirection,
        camera: CameraDirection,
        beat: str,
        genre: Any,
    ) -> str:
        """Fuses spatial blocking, lighting angles, and camera optics into an explicit FLUX prompt."""
        parts = [
            genre.prompt_prefix.strip(" ,"),
            f"{camera.shot_scale} of {spatial.character_position}",
            f"{spatial.posture_and_wardrobe}",
            f"Action: {spatial.movement_vector}",
            f"Foreground props: {spatial.focal_props}",
            f"Setting: {spatial.background_staging}",
            f"Lighting: Key light from {lighting.key_light_source}, {lighting.dominant_side}, {lighting.shadow_ratio}, {lighting.rim_light}",
            f"Camera optics: {camera.lens_optics}, focal center at {camera.safe_zone_anchor:.2f} vertical height",
            genre.prompt_suffix.strip(" ,"),
        ]
        raw = ", ".join(p for p in parts if p).strip()
        cleaned = re.sub(r"\s{2,}", " ", raw)
        cleaned = re.sub(r",\s*,+", ",", cleaned).strip(" ,.")
        return cleaned + "."
