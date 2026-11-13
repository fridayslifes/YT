#!/usr/bin/env python3
"""FrameForge S4 Visual Director & Semantic 3D Spatial Prompt Agent (v7.0).

Replaces legacy template middlemen (`prompt_architect.py`) with a 4-stage Semantic 3D Spatial Prompt Agent:
  - S1: Semantic Script, Entity & Dossier Deconstruction:
        Parses each scene's exact spoken script (`text`), `note`, `stat_card`, and `overlay` to extract
        historical year/era, setting, physical props, and human action. No named person and no
        neurological mechanism reaches a FLUX prompt unless the dossier states it (see the
        method_claims and named_subject checks in tools/orchestrator/verifiers.py). Covers both
        8-scene 9:16 Shorts and 26+ scene 16:9 Long-Form videos with zero truncation.
  - S2: 6-Layer 3D Multi-Plane Cinematographic Composition:
        Explicitly structures every FLUX prompt into 3 distinct Z-depth planes (`Foreground Z-Near`, `Midground Subject Z-Mid`,
        `Background Z-Far`) so `Depth-Anything-V2` and `ISNet` extract maximum 3D spatial parallax:
        [Layer 1: Shot Scale & 3D Camera Angle] +
        [Layer 2: Midground Subject, Wardrobe & Micro-Expression (Z-Mid)] +
        [Layer 3: Tactile Action & Foreground Parallax Props (Z-Near)] +
        [Layer 4: Authentic Era Setting & Deep Architectural Perspective (Z-Far)] +
        [Layer 5: 3-Point Chiaroscuro & Rim Lighting Architecture] +
        [Layer 6: Optical Specs + Aspect-Accurate Safe-Zone Bounding (9:16 or 16:9)]
  - S3: Cross-Axial Profile Camera Solver & Prompt Sanitization:
        Enforces 90-degree lateral profile two-shots for multi-person interactions and strips AI slop tokens.
  - S4: Multi-Scene 3D Trajectory Choreography & Asset Integrity:
        Assigns varied 3D spatial camera trajectories (`depthflow_spiral`, `depthflow_orbit`, `depthflow_vertigo`,
        `depthflow_dolly`, `depthflow_roll`, `spatial_drift`) and ensures clean `images/*.jpg` and `videos/*.mp4` paths.

CLI Usage:
    python tools/visual_director.py --project long_form/lv_02_focus_protocol/project.json --inplace
    python tools/visual_director.py --project shorts/short_12_parkinsons_law/project.json --inplace
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

TOOLS_DIR = Path(__file__).resolve().parent
YT_ROOT = TOOLS_DIR.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
if str(YT_ROOT) not in sys.path:
    sys.path.insert(0, str(YT_ROOT))

from tools.genre_director import get_genre_profile  # noqa: E402
from tools import output_format as out_fmt  # noqa: E402


BANNED_PHOTOREAL_TOKENS = [
    r"\b8k\b",
    r"\b4k\b",
    r"\bunreal engine 5\b",
    r"\bunreal engine\b",
    r"\bue5\b",
    r"\boctane render\b",
    r"\bhyper-realistic\b",
    r"\bhyperrealistic\b",
    r"\bmasterpiece\b",
    r"\bbest quality\b",
    r"\bultra-detailed\b",
    r"\bphotorealistic\b",
    r"\baward-winning\b",
    r"\btrending on artstation\b",
    r"\bvray\b",
    r"\b3d render\b",
    r"\bcgi render\b",
    r"\btarget reticle\b",
    r"\bhud circle\b",
    r"\bbiometric hud\b",
]

UNIVERSAL_BANNED_SLOP = [
    r"\bmasterpiece\b",
    r"\bbest quality\b",
    r"\btrending on artstation\b",
    r"\baward-winning\b",
    r"\btarget reticle\b",
    r"\bhud circle\b",
    r"\bbiometric hud\b",
]


# Bespoke 3D-Spatial Topic Blueprints (with explicit foreground/midground/background Z-depth planes)
TOPIC_VISUAL_BLUEPRINTS: Dict[str, Dict[int, Dict[str, str]]] = {
    "loss_aversion": {
        1: {
            "scale": "High-tension medium close-up 3D spatial documentary shot at eye-level",
            "subject": "a 34-year-old investor in a tailored charcoal button-down shirt with sleeves rolled up, beads of sweat on his brow, jaw clenched in acute psychological dread",
            "action": "staring down at two physical stacks of hundred-dollar bills on a dark walnut table—one small foreground stack being pulled away by a brass croupier rake in the near Z-plane while his hand hovers hesitatingly over a larger stack",
            "setting": "dimly lit behavioral economics testing room with receding dark wood paneling and soft-focus vintage ledger books in the deep background",
            "lighting": "dramatic chiaroscuro warm tungsten overhead key light with deep obsidian shadows and cool cyan rim highlight separating the subject from the background",
            "archetype": "visceral_hook",
        },
        2: {
            "scale": "Authentic 1979 archival scientific documentation medium two-shot with multi-plane depth",
            "subject": "two behavioral psychologists in late-1970s corduroy blazers and wire-rimmed glasses, leaning forward in intense intellectual debate",
            "action": "plotting an asymmetric S-shaped Prospect Theory value curve on a large green chalkboard, with a blurred stack of typewritten 1979 manuscripts and a brass desk lamp in the immediate foreground plane",
            "setting": "1979 Princeton & Hebrew University psychology seminar room with wooden bookshelves receding into soft background bokeh",
            "lighting": "warm afternoon slanting window light cutting through volumetric chalk dust motes with natural shadow falloff",
            "archetype": "empirical_evidence",
        },
        3: {
            "scale": "Tactile macro tabletop 3D spatial close-up shot at a 35-degree angle",
            "subject": "a person's tense human hand in a wool sleeve in crisp midground focus",
            "action": "holding a heavy vintage silver half-dollar coin mid-flip above a typewritten 1979 betting ledger headed '50/50 CHANCE TO WIN OR LOSE', with an out-of-focus analog brass stopwatch in the immediate foreground",
            "setting": "worn oak desk receding into a dim university seminar room in shallow depth of field",
            "lighting": "warm directional tungsten desk lamp casting crisp 3D side-shadows across the paper grain and silver coin edge",
            "archetype": "empirical_evidence",
        },
        4: {
            "scale": "High-contrast documentary 3D spatial profile portrait",
            "subject": "a human head and upper shoulders in crisp side-profile silhouette in the midground plane",
            "action": "positioned beside a translucent glass light-box displaying a hand-drawn asymmetric value curve whose loss side falls steeply while its gain side flattens, with optical glass lenses softly blurred in the foreground",
            "setting": "dark chart-review suite with receding glass monitor panels in deep bokeh",
            "lighting": "bioluminescent amber key light and electric cyan Fresnel rim light tracing the facial profile",
            "archetype": "internal_psychology",
        },
        5: {
            "scale": "Candid over-the-shoulder 3D multi-plane medium close-up",
            "subject": "an exhausted 30-year-old professional in an unbuttoned Oxford shirt at 1:30 AM, rubbing aching eyes with one hand",
            "action": "watching a glowing financial portfolio screen plunging downward in red candlestick lines while refusing to click the sell button, framed past a softly blurred cold coffee mug in the near foreground",
            "setting": "quiet dark apartment study at night with rain streaks on the window glass and receding city lights in deep bokeh",
            "lighting": "cool blue-red monitor glow reflecting off tired skin and eyes, balanced by a warm amber background rim lamp",
            "archetype": "internal_psychology",
        },
        6: {
            "scale": "Intimate psychological close-up portrait with strong Z-axis corridor depth",
            "subject": "a tense individual standing alone in a narrow shadowy corridor, both hands pressed against their temples, eyes wide with racing thoughts",
            "action": "locked in internal mental paralysis as foreground glass reflections of ticking clock hands double-expose faintly across the near plane",
            "setting": "minimalist dark architectural hallway with strong converging 3D perspective lines receding behind the subject",
            "lighting": "split chiaroscuro lighting—half the face lit in warm amber, the other half sculpted by cool slate rim shadow",
            "archetype": "internal_psychology",
        },
        7: {
            "scale": "Grounded eye-level medium shot with decisive 3D spatial separation",
            "subject": "a composed, clear-eyed person in a crisp dark sweater sitting upright with relaxed shoulders and direct, calm focus",
            "action": "firmly writing a single bold question in black ink on a clean white index card ('Would I buy this today?') while closing a laptop lid in the foreground plane",
            "setting": "sunlit minimalist wooden desk by an open morning window with deep architectural breathing room behind",
            "lighting": "warm golden morning sunlight wrapping naturally around the face and shoulders with high-contrast 3D rim clarity",
            "archetype": "five_second_override",
        },
        8: {
            "scale": "Atmospheric wide 3D spatial documentary tableau",
            "subject": "a solitary figure seen in contemplative three-quarter profile standing beside a floor-to-ceiling window at dusk",
            "action": "looking out over a vast receding grid of glowing city office buildings while a brass pendulum on the foreground desk hangs at the exact turning point of its swing",
            "setting": "high-floor architectural study at twilight blending warm tungsten interior depth with deep indigo evening horizon",
            "lighting": "moody noir twilight palette with warm practical rim light and soft volumetric halation",
            "archetype": "ambient_loop",
        },
    },
    "simulation_argument": {
        1: {
            "scale": "Intimate medium close-up 3D spatial documentary frame",
            "subject": "a 30-year-old person in a dark tailored coat standing frozen at a rain-slicked pedestrian crosswalk, expression shifting from everyday calm to sudden existential awe",
            "action": "looking closely at their own palm and a falling raindrop suspended in the near foreground Z-plane with subtle geometric light refraction inside the droplet",
            "setting": "wet urban street corridor at twilight with receding yellow headlights and dark glass building facades in deep bokeh",
            "lighting": "warm amber streetlight key meeting cool electric cyan Fresnel rim reflection off wet pavement",
            "archetype": "visceral_hook",
        },
        2: {
            "scale": "Candid editorial 3D medium shot inside an Oxford-style study",
            "subject": "a philosophical researcher in a dark wool blazer seated at an antique library table, holding a fountain pen with an intense, questioning gaze",
            "action": "examining a 2003 printed manuscript titled 'Philosophical Quarterly' alongside three distinct brass balance weights arranged on a foreground wooden trilemma scale",
            "setting": "classic Oxford university library with towering oak bookshelves and arched leaded glass windows receding into deep Z-space",
            "lighting": "soft directional natural window light combined with a warm green-shaded banker's lamp casting 3D rim highlights",
            "archetype": "empirical_evidence",
        },
        3: {
            "scale": "Tactile macro spatial 3D close-up shot",
            "subject": "a researcher's hand in crisp midground focus adjusting a precision optical glass prism on a dark slate table",
            "action": "projecting a beam of warm white light that splits through a foreground crystal lattice into hundreds of nested reflected light points receding into an infinity mirror chamber",
            "setting": "dark optics and probability study with mathematical notes in soft foreground blur",
            "lighting": "volumetric light beams cutting through dark studio air with crisp specular 3D glass caustics",
            "archetype": "empirical_evidence",
        },
        4: {
            "scale": "High-contrast documentary 3D close-up",
            "subject": "a human eye and side profile in sharp midground macro focus, pupil slightly dilated",
            "action": "reflecting incoming light points that assemble into a translucent 3D glass lattice of nested observer counts in the foreground plane",
            "setting": "dark argument-mapping study with optical test lenses receding into background shadow",
            "lighting": "warm subsurface skin glow contrasted with crisp cyan optical fiber rim pathways",
            "archetype": "internal_psychology",
        },
        5: {
            "scale": "Moody over-the-shoulder 3D documentary portrait",
            "subject": "a stressed professional sitting alone on the edge of a bed at midnight, head tilted down, gripping their phone",
            "action": "staring at an unwritten message while dramatic shadows cast by foreground window blinds form prison-like bars across the room depth",
            "setting": "dimly lit bedroom with minimalist furniture and soft city glow outside the receding window",
            "lighting": "cool moonlight cyan and warm bedside tungsten creating deep 3D chiaroscuro separation",
            "archetype": "internal_psychology",
        },
        6: {
            "scale": "Tight psychological portrait at eye level with infinity mirror depth",
            "subject": "an anxious individual standing between two opposing wall mirrors in a dim hallway, brow furrowed in overthinking",
            "action": "looking sideways at their own repeating 3D reflections receding into the glass, hands raised to their temples in mental exhaustion",
            "setting": "quiet wood-and-glass interior corridor with deep receding mirror planes",
            "lighting": "moody low-key tungsten lighting with soft halation around the mirror edges",
            "archetype": "internal_psychology",
        },
        7: {
            "scale": "Grounded eye-level 3D medium shot",
            "subject": "a calm, decisive person in a textured knit sweater standing beside a wooden desk in morning light",
            "action": "placing one palm flat against the solid physical grain of the oak table in the near plane while writing a verified factual observation on a physical notepad",
            "setting": "bright, lived-in studio room with natural wood, stone, and plants in soft background depth",
            "lighting": "warm golden morning sunlight illuminating authentic skin texture and crisp shoulder rim edges",
            "archetype": "five_second_override",
        },
        8: {
            "scale": "Atmospheric wide 3D cinematic shot",
            "subject": "a lone silhouette standing on a quiet stone courtyard at dusk looking up at the horizon",
            "action": "framed past a foreground stone archway while watching warm interior window lights flicker on across a receding university quadrangle",
            "setting": "historic stone courtyard at blue hour with wet cobblestones reflecting warm golden windows in deep perspective",
            "lighting": "deep twilight indigo sky balanced by warm tungsten architectural rim glow",
            "archetype": "ambient_loop",
        },
    },
    "parkinsons_law": {
        1: {
            "scale": "High-tension medium close-up 3D spatial documentary shot at eye-level",
            "subject": "an overwhelmed 30-year-old professional in a rolled-sleeve dark shirt seated at a wooden desk, brow furrowed in acute deadline paralysis",
            "action": "staring at a single two-page brief on a glowing laptop while a large brass mechanical clock in the blurred foreground Z-plane looms beside a calendar with Friday circled in red",
            "setting": "lived-in architectural study with receding bookshelves and rain-streaked evening window glass in deep background bokeh",
            "lighting": "high-contrast chiaroscuro warm tungsten desk key light balanced by cool cyan monitor rim light",
            "archetype": "visceral_hook",
        },
        2: {
            "scale": "Authentic 1955 archival British documentary medium shot with multi-plane depth",
            "subject": "historian Cyril Northcote Parkinson in a classic 1950s tweed jacket and spectacles, seated with sharp analytical poise",
            "action": "writing with a fountain pen across a bureaucratic Admiralty ledger while stacks of rubber-stamped folders and a brass inkwell sit in the near foreground plane",
            "setting": "1955 London oak-paneled study with floor-to-ceiling archival filing cabinets receding into warm shadow",
            "lighting": "slanting afternoon window beams cutting through dust motes and warm green banker's lamp glow",
            "archetype": "empirical_evidence",
        },
        3: {
            "scale": "Tactile macro 3D spatial laboratory close-up at a 35-degree angle",
            "subject": "a researcher's hand in crisp midground focus turning a brass valve on a glass vacuum chamber",
            "action": "watching luminous amber vapor expand to fill every corner of a large glass vessel on a workbench, with an open stopwatch blurred in the immediate foreground",
            "setting": "vintage physics and behavioral testing room with dark slate surfaces and soft background bokeh",
            "lighting": "volumetric warm tungsten side-light illuminating the swirling glass chamber and specular brass edges",
            "archetype": "empirical_evidence",
        },
        4: {
            "scale": "Authentic 1967 behavioral psychology experiment medium two-shot",
            "subject": "two psychologists observing a study participant across a testing table with clipboards and mechanical chronographs",
            "action": "comparing a steep high-speed task completion curve against a flat, dragging excess-time curve plotted on a foreground transparency board",
            "setting": "1967 university psychology laboratory with acoustic wall tiles and receding observation glass",
            "lighting": "warm directional tungsten key light with crisp shadow separation across the foreground chart and midground subjects",
            "archetype": "empirical_evidence",
        },
        5: {
            "scale": "Candid over-the-shoulder 3D multi-plane close-up",
            "subject": "a perfectionist professional at midnight rubbing their temple in mental fatigue",
            "action": "obsessively rearranging color-coded sticky notes and twenty overlapping folder tabs on a glowing screen, framed past a cold mug of coffee in the near foreground",
            "setting": "dim modern apartment workspace with deep receding room shadows and soft city lights outside",
            "lighting": "cool slate monitor reflection on skin contrasted with a warm amber rim light on hair and shoulders",
            "archetype": "internal_psychology",
        },
        6: {
            "scale": "High-contrast medical neuroscience 3D profile portrait",
            "subject": "a human head and upper shoulders in sharp side-profile silhouette in the midground plane",
            "action": "aligned beside a translucent 3D glass brain model where dormant prefrontal norepinephrine pathways ignite into focused electric cyan and gold circuits under time compression",
            "setting": "dark clinical neuroimaging studio with receding optical monitors in soft bokeh",
            "lighting": "bioluminescent amber and cyan Fresnel rim light sculpting the facial profile and glass cortex",
            "archetype": "internal_psychology",
        },
        7: {
            "scale": "Grounded eye-level 3D medium shot with decisive physical action",
            "subject": "a calm, razor-focused individual in a dark knit sweater leaning forward with decisive clarity",
            "action": "twisting a physical high-contrast mechanical countdown timer to 45 minutes in the near foreground plane while writing a single bold target on a notepad",
            "setting": "sunlit minimalist wooden desk beside an open window with deep clean architectural space behind",
            "lighting": "warm golden morning sunlight wrapping around the subject's face and casting crisp 3D shadows across the desk",
            "archetype": "five_second_override",
        },
        8: {
            "scale": "Atmospheric wide 3D spatial documentary tableau",
            "subject": "a composed figure standing in three-quarter profile by a tall sunlit window, looking out in calm mastery",
            "action": "holding a closed leather notebook while a finished mechanical timer rests quietly in the foreground desk plane",
            "setting": "high-ceilinged architectural studio overlooking a vast city skyline at golden hour",
            "lighting": "warm amber sunset rim light meeting deep indigo shadow depth for a seamless visual loop",
            "archetype": "ambient_loop",
        },
    },
    "paradox_of_choice": {
        1: {
            "scale": "High-impact medium close-up 3D spatial documentary shot",
            "subject": "a 29-year-old shopper in a casual jacket standing frozen in a gourmet market aisle, expression paralysed by cognitive overload",
            "action": "staring at a towering illuminated display shelf packed with twenty-four glass jars of artisan jam, with two jars blurred in the immediate foreground plane",
            "setting": "upscale wooden market interior with receding Edison bulbs and deep aisle perspective in bokeh",
            "lighting": "warm amber shelf backlighting with soft chiaroscuro facial shadows and cyan rim separation",
            "archetype": "visceral_hook",
        },
        2: {
            "scale": "Authentic 2000 field-experiment documentary 3D two-shot",
            "subject": "two behavioral researchers with clipboards and stopwatches in a midground observation corner",
            "action": "recording customer conversion rates past a foreground tasting table comparing a crowded 24-option display against a clean 6-option booth",
            "setting": "California gourmet grocery store interior with receding wooden shelves in shallow depth of field",
            "lighting": "natural warm indoor market lighting with crisp 3D multi-plane depth falloff",
            "archetype": "empirical_evidence",
        },
    },
    "speckled_band": {
        1: {
            "scale": "Authentic 1892 Victorian illustrated storybook medium close-up shot at eye-level",
            "subject": "a Victorian detective in an Inverness cape with sharp keen eyes and an analytical gaze holding a brass magnifying glass",
            "action": "inspecting a dark bedroom ceiling ventilator shaft with intense focus, framed past a blurred brass candlestick in the near Z-plane",
            "setting": "Victorian manor bedroom with dark oak wood paneling, heavy velvet curtains, and rain-streaked windowpanes in deep background",
            "lighting": "warm gaslight illumination casting dramatic chiaroscuro shadows across the wooden ceiling beams",
            "archetype": "visceral_hook",
        },
        2: {
            "scale": "Victorian detective study archival two-shot with multi-plane depth",
            "subject": "Sherlock Holmes and Dr. John Watson in period morning coats leaning over a dark mahogany table",
            "action": "examining a handwritten telegram and a diagram of Stoke Moran manor, framed past a steaming cup of tea and morning papers",
            "setting": "221B Baker Street sitting room with overflowing bookshelves, violin case, and Persian slipper on the mantelpiece",
            "lighting": "soft London morning fog filtering through tall Victorian windows with volumetric dust motes",
            "archetype": "empirical_evidence",
        },
        3: {
            "scale": "Tactile macro tabletop close-up shot at a 35-degree angle",
            "subject": "a person's gloved hand gently tugging a thick crimson silk bell-rope hanging beside a mahogany bedstead",
            "action": "revealing that the bell-rope is a dummy fastener connected to no bell wire, attached directly beneath a small ventilation grill",
            "setting": "Victorian bedroom with clamped iron bedstead bolted to the wooden floorboards",
            "lighting": "warm directional lantern beam highlighting the brass ventilator grill and the woven texture of the crimson rope",
            "archetype": "empirical_evidence",
        },
        4: {
            "scale": "High-contrast dramatic close-up in the midground plane",
            "subject": "a speckled yellow and brown swamp adder serpent slithering silently through a narrow iron ventilator grate in the wall",
            "action": "descending the crimson bell-rope in the dark towards the sleeping pillow below, coils moving with lethal grace",
            "setting": "dark stone wall corner between two Victorian manor rooms in deep shadow",
            "lighting": "pale moonlight glinting off the speckled scales and cold unblinking reptilian eye",
            "archetype": "internal_psychology",
        },
        5: {
            "scale": "Tense atmospheric medium two-shot with deep Z-axis perspective",
            "subject": "Holmes sitting motionless in a wicker armchair with a loaded revolver and cane, Watson watching beside him in silence",
            "action": "waiting in complete pitch darkness for the midnight whistle, eyes locked on the ceiling ventilator",
            "setting": "gloomy Stoke Moran bedroom illuminated only by a single slit of candlelight beneath the door",
            "lighting": "deep obsidian shadows with a razor-thin golden edge light defining the detective's resolute profile",
            "archetype": "internal_psychology",
        },
        6: {
            "scale": "Dynamic dramatic action shot with sudden lighting transition",
            "subject": "Dr. Grimesby Roylott sitting paralyzed in an antique wooden chair in the adjoining room",
            "action": "with the speckled band coiled tightly around his brow, a look of petrified terror frozen upon his contorted face",
            "setting": "cluttered study filled with Indian brass curios, iron safe, and a saucer of milk on the carpet",
            "lighting": "flickering yellow lantern light casting jagged shadows against the stone walls",
            "archetype": "internal_psychology",
        },
        7: {
            "scale": "Grounded eye-level medium shot with elegant Victorian storybook framing",
            "subject": "Sherlock Holmes standing calmly at the mantelpiece lighting his pipe, expression thoughtful and serene",
            "action": "closing his leather casebook with a brass clasp as Watson records the final notes in his journal",
            "setting": "cozy 221B Baker Street study with glowing hearth fire and warm bookshelves in the background",
            "lighting": "warm crackling fireplace amber glow bathing the room in comforting relief",
            "archetype": "resolution",
        },
        8: {
            "scale": "Atmospheric Victorian London exterior shot with deep receding perspective",
            "subject": "a horse-drawn hansom cab disappearing into the thick amber-lit London fog on Baker Street",
            "action": "turning the corner past glowing street gaslamps as a whistle echoes faintly in the damp night air",
            "setting": "Victorian cobblestone street with brick townhouses receding into the swirling mist",
            "lighting": "warm gaslight halos piercing through cool midnight London fog",
            "archetype": "infinite_loop",
        },
    },
    "dorian_gray": {
        1: {
            "scale": "Gothic Victorian illustrated storybook medium close-up shot at eye-level",
            "subject": "a handsome Victorian gentleman in an exquisite tailored velvet evening jacket staring in horror at an easel in an antique attic",
            "action": "pulling aside a heavy purple-and-gold satin pall to reveal the hideous sneering face on the hidden canvas",
            "setting": "dusty locked schoolroom attic with spiderwebs, discarded antique toys, and barred windows in deep bokeh",
            "lighting": "flickering candlelight casting long eerie shadows across the decaying painted canvas",
            "archetype": "visceral_hook",
        },
        2: {
            "scale": "Luminous Victorian artist studio medium two-shot with multi-plane depth",
            "subject": "young Dorian Gray possessing radiant golden beauty standing beside artist Basil Hallward holding a palette",
            "action": "admiring the newly finished life-size oil portrait on a heavy mahogany easel, surrounded by sweet scent of lilacs",
            "setting": "sun-drenched artist studio in Mayfair with open garden French doors and white marble sculptures",
            "lighting": "warm golden afternoon sunlight streaming across the pristine painted portrait and polished floorboards",
            "archetype": "empirical_evidence",
        },
        3: {
            "scale": "Tactile macro tabletop close-up shot at a 35-degree angle",
            "subject": "an antique gilt-edged Venetian mirror resting beside a heavy brass padlock key on a dark velvet cloth",
            "action": "a trembling young hand touching the flawless smooth skin of his own reflection while glancing at the painted canvas",
            "setting": "ornate Victorian dressing table with crystal perfume flacons and leather-bound French novels",
            "lighting": "intimate warm lamp glow reflecting off the beveled mirror glass and polished brass key",
            "archetype": "empirical_evidence",
        },
        4: {
            "scale": "High-contrast dramatic close-up in the midground plane",
            "subject": "the painted oil face on the canvas showing a subtle, cruel sneer around the lips that was never painted there",
            "action": "the oil pigment appearing slightly altered, lines of cruelty etching across the perfect painted features",
            "setting": "dimly lit library room with heavy damask curtains drawn shut against the morning light",
            "lighting": "cold gray dawn light creeping between velvet drapes, exposing the strange corruption of the paint",
            "archetype": "internal_psychology",
        },
        5: {
            "scale": "Haunting gothic interior shot with strong Z-axis perspective",
            "subject": "Dorian Gray standing alone before the locked heavy oak door with an iron bolt at the top of the stairs",
            "action": "turning the heavy key in the lock, holding a lantern as he climbs to visit his decaying secret soul",
            "setting": "narrow dark Victorian stairwell with peeling wallpaper and creaking floorboards receding into shadow",
            "lighting": "single swinging oil lantern casting undulating pools of amber light and clutching shadows",
            "archetype": "internal_psychology",
        },
        6: {
            "scale": "Grotesque gothic portrait reveal in the midground plane",
            "subject": "the life-size oil painting now depicting a withered, leering demon with blood-stained hands and rotting skin",
            "action": "the eyes of the portrait gleaming with malevolent life while the living Dorian stands before it unaged and flawless",
            "setting": "the dark attic surrounded by locked iron trunks and dust-covered relics of forgotten childhood",
            "lighting": "harsh theatrical lantern beam illuminating the grotesque rotting visage of the painting",
            "archetype": "internal_psychology",
        },
        7: {
            "scale": "Grounded eye-level medium shot with reflective Victorian storybook framing",
            "subject": "a somber Victorian gentleman standing in a quiet Mayfair study gazing into an antique fireplace",
            "action": "holding the heavy brass attic key over the glowing coals, realizing that the soul cannot be severed from truth",
            "setting": "luxurious London study filled with rare tapestries, carved ivory, and leather-bound volumes",
            "lighting": "soft glowing embers casting warm contemplative highlights across his immaculate face",
            "archetype": "resolution",
        },
        8: {
            "scale": "Dramatic midnight attic tableau with sudden stillness",
            "subject": "an antique silver knife lying on the floor beside the slashed canvas, where the painting is suddenly radiant and young again",
            "action": "an unrecognizable withered corpse lying on the floor in evening dress with a knife in its heart",
            "setting": "the locked attic chamber illuminated by the cold pale light of the full moon through barred windows",
            "lighting": "volumetric silver moonlight spilling across the pristine portrait and the dark shadows on the floorboards",
            "archetype": "infinite_loop",
        },
    },
    "the_clever_hans_effect": {
        1: {
            "scale": "High-tension 3D spatial medium close-up documentary shot at eye-level",
            "subject": "a sleek black stallion standing alert in a cobblestone courtyard with intelligent focused eyes",
            "action": "tapping a polished wooden counting board with his front hoof while spectators watch in silent tension",
            "setting": "1904 Berlin courtyard surrounded by brick archways and gas lamps receding into morning mist",
            "lighting": "soft morning sunlight with crisp cool rim lighting highlighting his muscular dark coat",
            "archetype": "visceral_hook",
        },
    },
}


def format_scene_visual_prompt(scene_desc: str, mood: str = "psychological suspense", aspect: str = "9:16") -> str:
    """Standalone helper replacing legacy prompt_architect.format_scene_visual_prompt."""
    director = S4VisualDirector(genre_key="3d_cgi", topic=scene_desc[:60], default_aspect=aspect)
    direction = director.synthesize_6_layer_scene(scene_desc, scene_idx=1)
    return direction.sanitized_prompt


@dataclass
class SceneDirection:
    scene_index: int
    narrative_beat: str
    shot_scale: str
    subject_desc: str
    action_and_props: str
    setting_and_era: str
    lighting: str
    motion_preset: str
    cap_y: float
    sanitized_prompt: str


# Role 1 was one fixed sentence, so every Short opened on the same "relatable 30-year-old" in the
# same "lived-in architectural room" - and with the old per-index seed the frames came out near
# identical across videos (SH-17 and SH-18 scene 1 were the same man at the same desk). The person,
# their clothing and the room now vary deterministically with the topic. The house look stays fixed:
# tactile 3D medium close-up, chiaroscuro tungsten plus cyan rim, three Z-depth planes.
# These are illustrative viewer-side scenes. None may name a method or a brain region, because
# visual_method_claims in tools/orchestrator/verifiers.py checks the image prompt against the dossier.
HOOK_PEOPLE = (
    "a woman in her late twenties wearing a worn cotton hoodie",
    "a man in his mid thirties in a creased office shirt with a loosened collar",
    "a student in a denim jacket over a plain tee",
    "a woman in her forties in a soft cardigan over a work blouse",
    "a bearded man in his forties in a flannel overshirt",
    "a young man with short-cropped hair in a plain grey sweater",
    "a focused woman in her thirties in a tailored navy knit sweater",
    "a researcher in his late twenties wearing wire-rimmed spectacles and a linen shirt",
    "a tired professional in a charcoal henley shirt leaning over an analytical desk",
    "an observant architect in her early thirties in a minimalist black turtleneck",
    "a quiet writer in a heather-grey crewneck surrounded by notebooks",
    "a thoughtful analyst in a dark wool vest over an Oxford shirt",
)
HOOK_ROOMS = (
    "a cluttered kitchen table behind a cold mug and a stack of unopened mail",
    "an open-plan office corner behind a laptop and a paper planner",
    "a commuter train seat with the window glass reflecting the carriage",
    "a dim bedroom edge with a phone face-down on the duvet",
    "a laundromat bench beside a row of tumbling machines",
    "a home workshop bench under a single bare bulb",
    "a quiet library carrel flanked by tall mahogany bookshelves and a brass lamp",
    "a sunlit drafting table covered with sketches, tracing paper, and vintage rulers",
    "an archive reading room with catalog cards, wooden flat files, and deep shadow",
    "a corner coffee shop table beside a rain-streaked window and a half-read journal",
    "a minimalist home studio with an easel, canvas boards, and dim northern light",
    "a dimly lit conservatory alcove with analog instruments and wooden cabinets",
)


class S4VisualDirector:
    """Synthesizes bespoke, 6-layer 3D-spatial FLUX prompts from script lines, scene notes, and scientific dossiers."""

    def __init__(
        self,
        genre_key: str = "3d_cgi",
        topic: str = "Cognitive Psychology",
        default_aspect: str = "9:16",
        default_genre: str | None = None,
        dossier: Optional[Dict[str, Any]] = None,
    ):
        effective_genre = default_genre or genre_key
        self.genre = get_genre_profile(effective_genre)
        self.topic = topic
        self.default_aspect = default_aspect
        self.dossier = dossier or {}

    def sanitize_prompt(self, raw_prompt: str) -> str:
        """S3: Strip banned AI slop tokens, deduplicate repeated clauses, and enforce clean grammar."""
        cleaned = raw_prompt
        is_3d_genre = self.genre.id in {"3d_cgi", "3d_minimalist", "kinetic_explainer", "cyberpunk_neon"}
        token_list = UNIVERSAL_BANNED_SLOP if is_3d_genre else BANNED_PHOTOREAL_TOKENS
        for pattern in token_list:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bA\s+(individual|experiment|archive|apparatus|hour|optical|exhausted|anxious|intimate|overwhelmed|awake|early)\b", r"An \1", cleaned)
        cleaned = re.sub(r"\ba\s+(individual|experiment|archive|apparatus|hour|optical|exhausted|anxious|intimate|overwhelmed|awake|early)\b", r"an \1", cleaned)
        cleaned = re.sub(r"\s*,\s*,+", ",", cleaned)
        cleaned = re.sub(r"\.\s*\.+", ".", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,.")
        return cleaned + "."

    def _normalize_topic_key(self, topic_str: str) -> str:
        norm = re.sub(r"[^a-z0-9]+", "_", topic_str.lower()).strip("_")
        for k in TOPIC_VISUAL_BLUEPRINTS:
            if k in norm or norm in k:
                return k
        return norm

    def _detect_directed_interaction(self, text: str) -> bool:
        t_low = text.lower()
        return any(
            phrase in t_low
            for phrase in ["point at one person", "you in the", "tell one person", "look at them", "two people", "conversation between"]
        )

    def _deconstruct_script_semantics(
        self,
        text: str,
        scene_idx: int,
        note: str = "",
        stat_card: Optional[Dict[str, str]] = None,
        overlay: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """Semantic Script Deconstructor: Extracts concrete 3D foreground/midground/background visual planes from any script line."""
        clean_t = re.sub(r"\*", "", text).strip()
        low = (clean_t + " " + note + " " + (overlay.get("text", "") if overlay else "")).lower()

        # 1. Detect specific narrative/scientific scenes from script keywords (works across Shorts & 26-scene Long-Form)
        if any(k in low for k in ["twenty browser tabs", "sit down at your desk with coffee", "ninety seconds"]):
            return {
                "scale": "High-tension 3D multi-plane medium close-up shot",
                "subject": "an overwhelmed 32-year-old professional seated at a dark walnut desk, eyes fatigued and brow tense, one hand hovering hesitantly over a mechanical keyboard",
                "action": "surrounded by glowing dual monitors reflecting twenty overlapping browser windows, framed past a steaming ceramic coffee mug and silenced smartphone in the near foreground Z-plane",
                "setting": "modern architectural study with deep receding bookshelves and shadowed glass walls in soft bokeh",
                "lighting": "cool blue monitor key light meeting warm tungsten side-rim illumination with deep chiaroscuro shadows",
            }
        if any(k in low for k in ["gloria mark", "twenty-three minutes", "23m 15s", "irvine"]):
            return {
                "scale": "Authentic 2008 empirical behavioral observation 3D medium two-shot",
                "subject": "a cognitive researcher in analytical academic attire holding a stopwatch and observation log in crisp midground focus",
                "action": "tracking a knowledge worker's interrupted workflow while a translucent foreground data glass displays a 23-minute-15-second recovery curve",
                "setting": "UC Irvine informatics observation suite with receding glass office cubicles in shallow depth of field",
                "lighting": "warm directional tungsten key light balanced by cool cyan telemetry rim highlights",
            }
        if any(k in low for k in ["every three minutes", "self-interruptions", "subconscious craving"]):
            return {
                "scale": "Tactile macro 3D spatial close-up at a 30-degree angle",
                "subject": "a professional's hand and wrist in sharp midground focus unconsciously reaching toward a glowing smartphone face-up on a dark oak desk",
                "action": "frozen mid-reach beside an unfinished report keyboard, with an out-of-focus mechanical chronograph ticking in the immediate foreground plane",
                "setting": "dimly lit office workspace with receding monitor glow and deep background bokeh",
                "lighting": "crisp cyan screen glow uplighting the fingers against warm amber side-rim shadows",
            }
        if any(k in low for k in ["autotelic flow", "three or four times an hour", "reclaim total cognitive autonomy"]):
            return {
                "scale": "Atmospheric 3D spatial medium-wide documentary shot",
                "subject": "a solitary, deeply focused thinker in a dark tailored sweater seated in calm mastery at a clean architectural desk",
                "action": "working with unbroken concentration on a single illuminated page while a foreground glass partition reflects warm twilight city lights",
                "setting": "high-floor minimalist studio at dusk overlooking a receding metropolitan horizon in creamy bokeh",
                "lighting": "warm golden rim light wrapping around the subject's profile against deep indigo evening shadows",
            }
        if any(k in low for k in ["email ping", "glance at it for five seconds", "poisoned your cognitive throughput"]):
            return {
                "scale": "Candid over-the-shoulder 3D multi-plane close-up",
                "subject": "a writer's tense face and shoulders reflected faintly in a dark laptop screen, eyes darting toward an incoming notification popup",
                "action": "pausing mid-sentence over a backlit keyboard while a blurred smartphone vibrates on the desk edge in the near foreground plane",
                "setting": "quiet dark study room with receding architectural shadows and rain-streaked glass",
                "lighting": "high-contrast split chiaroscuro lighting with urgent amber alert glow and cool slate shadow falloff",
            }
        if any(k in low for k in ["sophie leroy", "organization science", "ram flushing"]):
            return {
                "scale": "Authentic 2009 university psychology laboratory 3D medium shot",
                "subject": "an organizational psychologist in a tailored blazer reviewing cognitive load charts at an oak research table",
                "action": "comparing Task A and Task B working-memory decay logs, framed past an open 2009 Organization Science journal and fountain pen in the near foreground",
                "setting": "university behavioral laboratory with vintage wooden bookshelves and glass observation panels in deep bokeh",
                "lighting": "warm slanting window light and brass banker's lamp casting crisp 3D rim contours",
            }
        if any(k in low for k in ["switch from task a to task b", "stuck processing the previous project"]):
            return {
                "scale": "High-contrast neuroscience 3D spatial profile close-up",
                "subject": "a contemplative human subject in sharp side-profile silhouette in the midground plane",
                "action": "positioned beside a translucent 3D glass cortex model where glowing amber neural fibers remain anchored to Task A while cyan fibers struggle to shift to Task B, with optical lenses blurred in the foreground",
                "setting": "dark neuroimaging studio with receding glass instrumentation in shallow depth of field",
                "lighting": "bioluminescent amber and electric cyan Fresnel rim lighting sculpting the facial profile",
            }
        if any(k in low for k in ["word puzzles", "subsequent decision-making task", "cognitive lag"]):
            return {
                "scale": "Controlled laboratory experiment 3D medium shot",
                "subject": "a study participant seated at a clean testing booth, rubbing their forehead in measurable cognitive fatigue",
                "action": "staring at a complex decision matrix sheet while an incomplete crossword puzzle sheet and brass timer sit in the near foreground Z-plane",
                "setting": "university cognitive testing room with receding partition walls and soft overhead light",
                "lighting": "moody directional tungsten key light with deep shadow separation across the desk planes",
            }
        if any(k in low for k in ["two in the morning", "2 am", "unsent email", "insomnia"]):
            return {
                "scale": "Moody 3D spatial close-up portrait at 2:00 AM",
                "subject": "an exhausted person lying awake in bed, staring wide-eyed at the ceiling with racing thoughts etched across their face",
                "action": "framed past a softly blurred bedside alarm clock glowing '2:14 AM' in the immediate foreground plane",
                "setting": "dark minimalist bedroom where moonlight slices through venetian blinds across the receding wall",
                "lighting": "cool silver-cyan moonlight bars contrasted with warm skin subsurface tones and deep obsidian shadows",
            }
        if any(k in low for k in ["vienna", "zeigarnik", "kurt lewin", "waiters"]):
            return {
                "scale": "Authentic 1927 Vienna café archival 3D spatial medium shot",
                "subject": "two psychologists seated at a marble café table in 1920s wool attire, observing a formal Viennese waiter in crisp midground focus",
                "action": "the waiter balancing a silver tray of coffee cups from memory without a notepad, framed past a foreground porcelain espresso cup and handwritten notebook",
                "setting": "bustling 1927 Viennese coffeehouse with arched mirrors, bentwood chairs, and warm chandeliers receding into deep bokeh",
                "lighting": "warm golden incandescent café glow and slanting afternoon sunbeams cutting through atmospheric steam",
            }
        if any(k in low for k in ["ninety percent better", "+90% recall", "interrupted tasks"]):
            return {
                "scale": "Tactile 1927 psychological laboratory 3D tabletop medium shot",
                "subject": "a participant's hands assembling a wooden puzzle on a velvet-lined testing table while a researcher's hand places an interruption barrier across the work",
                "action": "framed past a foreground handwritten 1927 German experimental ledger showing '+90% Recall for Unfinished Tasks' and a pocket watch",
                "setting": "Berlin University psychological institute room with tall oak cabinets receding into soft focus",
                "lighting": "warm directional tungsten lamp casting deep 3D relief shadows across the puzzle pieces and ledger",
            }
        if any(k in low for k in ["open loops", "background apps on a phone", "cognitive battery"]):
            return {
                "scale": "Conceptual 3D spatial medium close-up portrait",
                "subject": "a fatigued knowledge worker seated in a dark studio, eyes closed in mental overload",
                "action": "surrounded in 3D space by translucent glass task cards and half-written pages suspended at near and mid Z-depths around their shoulders",
                "setting": "deep obsidian architectural space with subtle volumetric light haze receding into darkness",
                "lighting": "warm amber key light on the face with glowing cyan Fresnel rim edges on the floating glass task planes",
            }
        if any(k in low for k in ["two weeks to clean out", "manager suddenly demands", "deadline illusion"]):
            return {
                "scale": "Dramatic 3D spatial medium shot inside an executive office",
                "subject": "a sharp-eyed professional leaning over a glass conference table with sudden high-urgency focus",
                "action": "typing rapidly on a laptop while a foreground wall calendar flips from two weeks down to a glowing 90-minute countdown clock",
                "setting": "modern glass boardroom overlooking a receding metropolitan skyline at dusk",
                "lighting": "crisp warm tungsten key light meeting cool twilight blue glass reflections",
            }
        if any(k in low for k in ["cyril northcote parkinson", "1955", "the economist", "gas expanding"]):
            return TOPIC_VISUAL_BLUEPRINTS["parkinsons_law"][2]
        if any(k in low for k in ["bryan and edwin locke", "bryan and locke", "1967", "excess time"]):
            return TOPIC_VISUAL_BLUEPRINTS["parkinsons_law"][4]
        if any(k in low for k in ["artificial complexity", "color palettes", "reorganize digital folders"]):
            return TOPIC_VISUAL_BLUEPRINTS["parkinsons_law"][5]
        if any(k in low for k in ["five-step attention reclaim", "protocol overview"]):
            return {
                "scale": "Grounded 3D spatial medium shot with architectural depth",
                "subject": "a composed strategist standing at a clean walnut drafting table with calm, assertive eye contact",
                "action": "arranging five physical brass and slate protocol markers in sequence across the desk, with the first marker blurred in the immediate foreground",
                "setting": "sunlit architectural studio with receding glass and warm wood panels",
                "lighting": "warm golden key light and crisp cyan rim accent sculpting the subject and table planes",
            }
        if any(k in low for k in ["external ram dump", "step one", "physical notebook"]):
            return {
                "scale": "Tactile 3D spatial overhead-angled medium close-up",
                "subject": "a focused person's hands and calm lower face in crisp midground focus at a morning desk",
                "action": "writing bold numbered open-loop items with a matte black fountain pen into a heavy leather notebook, framed past a closed laptop in the near foreground",
                "setting": "sunlit wooden study with morning dust motes floating in deep background bokeh",
                "lighting": "warm slanting morning sunlight casting crisp 3D shadows across the paper grain and knuckles",
            }
        if any(k in low for k in ["attention air gap", "ready-to-resume", "ninety-minute ultradian"]):
            return {
                "scale": "Intimate 3D spatial medium shot",
                "subject": "a deep-work practitioner wearing matte studio over-ear headphones, writing a compact two-line 'Ready-to-Resume' index card",
                "action": "placing the index card upright beside the keyboard in the near foreground plane before stepping away cleanly",
                "setting": "minimalist dark-mode workstation with soft warm architectural depth behind",
                "lighting": "warm tungsten key light on the face and index card with soft cyan rim separation",
            }
        if any(k in low for k in ["half-life timebox", "step three", "battery hits four percent", "sixty minutes"]):
            return TOPIC_VISUAL_BLUEPRINTS["parkinsons_law"][7]
        if any(k in low for k in ["friction engineering", "step four", "shawn achor", "twenty seconds", "another room"]):
            return {
                "scale": "Tactile 3D spatial medium shot",
                "subject": "a decisive professional standing in a doorway, placing a glowing smartphone inside a physical matte-black timer lockbox",
                "action": "closing the heavy lid in the near foreground plane while a clean, distraction-free wooden desk awaits in the midground",
                "setting": "warm architectural study room with receding bookshelves in soft depth of field",
                "lighting": "warm amber key light wrapping around the hands and face against deep slate shadows",
            }
        if any(k in low for k in ["evening autonomy buffer", "step five", "revenge bedtime", "thirty-minute non-screen"]):
            return {
                "scale": "Atmospheric 3D spatial medium portrait",
                "subject": "a relaxed reader seated in a leather armchair at night, turning the page of a physical hardcover book with calm focus",
                "action": "framed past a steaming porcelain teacup on a foreground side table with zero digital screens in sight",
                "setting": "cozy wood-lined evening sanctuary with warm 2700K floor lamp and deep shadowed bookshelves",
                "lighting": "warm golden lamplight sculpting the face and book pages with soft optical halation",
            }
        if any(k in low for k in ["seventy-two hours", "72-hour", "dopamine withdrawal", "neuroplasticity"]):
            return {
                "scale": "High-contrast 3D spatial profile portrait",
                "subject": "a resilient individual in crisp three-quarter profile looking toward a sunlit window with steady determination",
                "action": "framed past a foreground hourglass running golden sand while subtle warm light traces their silhouette",
                "setting": "architectural studio transitioning from cool dawn shadows to warm golden daylight in deep Z-space",
                "lighting": "dramatic split lighting—cool dawn cyan on one side, warm golden sunrise rim light on the other",
            }
        if any(k in low for k in ["personal sovereignty", "cognitive sovereignty", "control their trajectory"]):
            return {
                "scale": "Inspiring wide 3D spatial documentary tableau",
                "subject": "a composed figure standing on a high architectural terrace in three-quarter profile, looking out over a vast horizon",
                "action": "hands resting calmly on a foreground stone parapet with wind gently moving their coat",
                "setting": "panoramic metropolitan skyline at sunrise with receding sunlit towers and atmospheric mist",
                "lighting": "golden hour volumetric rim light wrapping around the silhouette against deep sky contrast",
            }
        if any(k in low for k in ["notion template", "focus os", "subscribe", "channel page"]):
            return {
                "scale": "Tactile 3D spatial tabletop medium shot",
                "subject": f"a strategist's hands holding a sleek dossier on {self.topic} alongside a physical leather journal",
                "action": "framed past a foreground brass compass and fountain pen on a dark walnut desk",
                "setting": "warm studio library with receding bookshelves and soft amber rim lighting in deep bokeh",
                "lighting": "crisp directional tungsten key light with cyan screen accent and natural shadow falloff",
            }

        # 2. General Semantic Extraction for any new topic or scene (extracts year, stat, and narrative role)
        year_m = re.search(r"\b(19\d{2}|20\d{2})\b", clean_t + " " + note)
        year = year_m.group(1) if year_m else self.dossier.get("year", "1979")
        stat_str = stat_card.get("title", "") if stat_card else self.dossier.get("quantitative_stat", "")

        role_idx = ((scene_idx - 1) % 8) + 1
        # Roles 1 and 8 both draw their figure and room from the same tables at different offsets, so
        # one video keeps its own bookend frames apart while two videos on different topics can never
        # land on the same plate. Scene 8 used to be a fixed dusk-window tableau with no topic in it at
        # all, which is what made SH-18's closing frame byte-identical to SH-17's.
        pick = int(hashlib.sha256(self.topic.encode("utf-8")).hexdigest()[:8], 16)
        if role_idx == 1:
            return {
                "scale": "High-tension 3D spatial medium close-up documentary shot at eye-level",
                "subject": f"{HOOK_PEOPLE[pick % len(HOOK_PEOPLE)]}, frozen mid-task with an unposed micro-expression of sudden cognitive freeze and acute tension",
                "action": f"caught in the physical moment of {self.topic}, framed past a tactile out-of-focus foreground object from {HOOK_ROOMS[(pick >> 8) % len(HOOK_ROOMS)]} in the near Z-plane",
                "setting": f"{HOOK_ROOMS[(pick >> 8) % len(HOOK_ROOMS)]} with deep receding foreground, midground, and background depth planes",
                "lighting": "high-contrast chiaroscuro warm tungsten key light and cool cyan Fresnel rim shadow falloff",
            }
        # Method-neutral by construction: this branch renders for whichever topic reaches it, so it
        # may not assert a lab, an experiment, a trial or a brain region the dossier never reported.
        # Brickman et al. (1978) interviewed winners by telephone and face to face, yet these three
        # templates put "controlled behavioral trials", "laboratory testing table" and "prefrontal
        # cortex and amygdala pathways" into the image prompt - so the frame claimed what the
        # narration denied. No named person either: a generation prompt that asks for a real
        # researcher's likeness is a publicity-rights exposure (FLUX Kommunity License s4.a(v)).
        if role_idx == 2:
            return {
                "scale": f"Authentic {year} archival scientific documentation 3D medium two-shot",
                "subject": "two research investigators in period-accurate academic attire with focused analytical expressions",
                "action": f"reviewing handwritten study records and annotated data sheets about {self.topic}, framed past archival paper files in the near foreground plane",
                "setting": f"{self.dossier.get('institution', 'University')} research office with wood paneling and receding bookshelves in soft bokeh",
                "lighting": "warm slanting window light cutting through volumetric dust motes with brass desk lamp rim illumination",
            }
        if role_idx == 3:
            return {
                "scale": "Tactile macro tabletop 3D spatial close-up shot at a 35-degree angle",
                "subject": "a person's expressive hands and forearm in crisp midground focus",
                "action": f"handling the physical paper records from the {self.topic} study beside an open ledger ({stat_str or year}) and a blurred brass stopwatch in the immediate foreground",
                "setting": f"{year} study desk receding into shallow depth of field",
                "lighting": "crisp directional tungsten side key light highlighting paper texture and metal edges",
            }
        if role_idx == 4:
            return {
                "scale": "High-contrast documentary 3D spatial profile portrait",
                "subject": "a contemplative human subject in crisp side-profile silhouette in the midground plane",
                "action": f"positioned beside a translucent 3D glass display charting hand-annotated response scales and comparison curves for {self.topic}, with optical glass elements in foreground blur",
                "setting": "dark review studio with receding glass reflections",
                "lighting": "warm amber and electric cyan optical Fresnel rim lighting tracing the facial profile",
            }
        if role_idx == 5:
            return {
                "scale": "Candid over-the-shoulder 3D multi-plane medium close-up",
                "subject": "a fatigued professional late at night rubbing their brow with honest human vulnerability",
                "action": f"experiencing the real-world daily tax of {self.topic} in front of an open notebook, framed past a cold coffee mug in the near foreground plane",
                "setting": "quiet dark study with rain-streaked window glass and receding city bokeh",
                "lighting": "cool screen reflection on skin balanced by a warm tungsten background rim lamp",
            }
        if role_idx == 6:
            return {
                "scale": "Intimate psychological close-up portrait with deep corridor perspective",
                "subject": "a lone individual with fingers resting tensely against their temple, eyes reflecting internal cognitive friction",
                "action": f"trying to force sheer willpower against {self.topic}, framed past a blurred foreground glass reflection",
                "setting": "dimly lit architectural hallway with strong converging 3D perspective lines receding behind",
                "lighting": "split chiaroscuro lighting with warm highlight roll-off and deep slate shadows",
            }
        if role_idx == 7:
            return {
                "scale": "Grounded eye-level 3D medium shot with razor-sharp focus",
                "subject": "a composed, decisive individual with relaxed shoulders and clear, direct eye contact",
                "action": f"executing a physical reset for {self.topic}—writing a single concrete action note in a leather journal while pushing distractions out of the foreground plane",
                "setting": "sunlit wooden desk beside an open morning window with clean architectural depth behind",
                "lighting": "warm golden morning rim light wrapping around the subject's shoulders and face",
            }
        return {
            "scale": "Atmospheric wide 3D spatial documentary tableau",
            "subject": (
                f"{HOOK_PEOPLE[(pick >> 4) % len(HOOK_PEOPLE)]} in three-quarter profile standing "
                f"quietly by a tall window at dusk"
            ),
            "action": (
                f"framed past a foreground furnishing from {HOOK_ROOMS[(pick >> 12) % len(HOOK_ROOMS)]} "
                f"while looking out over softly blurred city lights, the everyday pause that surrounds "
                f"{self.topic} in contemplative stillness"
            ),
            "setting": (
                f"{HOOK_ROOMS[(pick >> 12) % len(HOOK_ROOMS)]} at dusk, its own window meeting a deep "
                f"receding evening horizon"
            ),
            "lighting": "moody dusk indigo and warm interior tungsten rim reflection",
        }

    def synthesize_6_layer_scene(
        self,
        text: str,
        scene_idx: int = 1,
        note: str = "",
        stat_card: Optional[Dict[str, str]] = None,
        overlay: Optional[Dict[str, Any]] = None,
    ) -> SceneDirection:
        """S1 & S2: Build a 6-layer 3D spatial scene prompt grounded in the exact spoken script line and dossier metadata."""
        t_key = self._normalize_topic_key(self.topic)

        beats = [
            "HOOK_SYMPTOM",
            "FALSE_ASSUMPTION_INTERRUPT",
            "EMPIRICAL_DATA_PROOF",
            "INTERNAL_MECHANISM",
            "REAL_WORLD_CONSEQUENCE",
            "WILLPOWER_FRICTION_TRAP",
            "FIVE_SECOND_OVERRIDE",
            "INFINITE_LOOP_BRIDGE",
        ]
        beat = beats[(scene_idx - 1) % len(beats)]
        # 9:16 captions sit in the one band the Shorts UI and our own face framing both leave free
        # (see SHORT_TEXT_BAND in tools/build_video.py). Scene 1 used to be 0.34, which pasted the
        # hook caption straight across the subject's mouth.
        cap_y = 0.86 if self.default_aspect == "16:9" else 0.66

        blueprint_scene = TOPIC_VISUAL_BLUEPRINTS.get(t_key, {}).get(scene_idx)

        if self._detect_directed_interaction(text):
            scale = "Side-profile view captured strictly parallel to the interaction plane, sharp lateral 3D two-shot composition"
            subject = (
                "on the left side of the frame, an individual in sharp focus wearing dark tailored outerwear facing right; "
                "on the right side of the frame, a startled counterpart in side-profile facing left"
            )
            action = (
                "the left subject extending their arm horizontally to point directly across the frame at the person on the right, "
                "neither subject looking at the camera, their line of sight and pointing vector strictly horizontal across the frame toward each other"
            )
            setting = "bustling urban street corridor with foreground blur and background commuters in soft optical bokeh"
            lighting = "warm directional tungsten rim light with deep chiaroscuro shadow separation"
        elif blueprint_scene:
            scale = blueprint_scene["scale"]
            subject = blueprint_scene["subject"]
            action = blueprint_scene["action"]
            setting = blueprint_scene["setting"]
            lighting = blueprint_scene["lighting"]
        else:
            sem = self._deconstruct_script_semantics(text, scene_idx, note=note, stat_card=stat_card, overlay=overlay)
            scale = sem["scale"]
            subject = sem["subject"]
            action = sem["action"]
            setting = sem["setting"]
            lighting = sem["lighting"]

        presets = list(self.genre.recommended_presets)
        motion_preset = "depthflow_spiral" if scene_idx == 1 else ("depthflow_orbit" if scene_idx % 4 == 0 else presets[(scene_idx - 1) % len(presets)])

        # Aspect-accurate optical tail (16:9 widescreen vs 9:16 vertical safe-zone)
        base_suffix = re.sub(r",?\s*primary (?:human )?subject.*?composition", "", self.genre.prompt_suffix, flags=re.IGNORECASE).strip(" ,.")
        if self.default_aspect == "16:9":
            optical_tail = (
                f"{base_suffix}, distinct 3-plane Z-depth separation (tactile foreground blur, razor-sharp midground subject, deep background bokeh), "
                f"unobstructed human face positioned in rule-of-thirds, 16:9 widescreen cinematic composition"
            )
        else:
            optical_tail = (
                f"{base_suffix}, distinct 3-plane Z-depth separation (tactile foreground blur, razor-sharp midground subject, deep background bokeh), "
                f"primary human subject strictly centered vertically between 30% and 58% frame height, unobstructed face, 9:16 vertical composition"
            )

        raw_6_layer = (
            f"{self.genre.prompt_prefix}{scale}. "
            f"Subject (Midground Z-Plane): {subject}, {action}. "
            f"Environment (Deep Background Z-Plane): {setting}. "
            f"3D Lighting & Mood: {lighting}, {beat.lower().replace('_', ' ')} atmosphere. "
            f"Optics: {optical_tail}"
        )
        clean_prompt = self.sanitize_prompt(raw_6_layer)

        return SceneDirection(
            scene_index=scene_idx,
            narrative_beat=beat,
            shot_scale=scale,
            subject_desc=subject,
            action_and_props=action,
            setting_and_era=setting,
            lighting=lighting,
            motion_preset=motion_preset,
            cap_y=cap_y,
            sanitized_prompt=clean_prompt,
        )

    def process_project_scenes(
        self,
        scenes_or_project: list[dict] | dict,
        genre: str | None = None,
        overwrite_custom_prompts: bool = True,
    ) -> list[dict]:
        """S4: Enrich and sanitize all scenes in a project with 6-layer 3D spatial prompts and true 3D camera trajectories."""
        if isinstance(scenes_or_project, dict):
            self.topic = scenes_or_project.get("topic") or scenes_or_project.get("concept") or self.topic
            genre = genre or scenes_or_project.get("genre")
            fmt = scenes_or_project.get("format", "short")
            self.default_aspect = "16:9" if fmt == "long" else "9:16"
            scenes = scenes_or_project.get("scenes", [])
        else:
            scenes = scenes_or_project

        if genre:
            self.genre = get_genre_profile(genre)

        seen_prompts: set[str] = set()
        enriched_scenes = []

        for idx, sc in enumerate(scenes):
            sc_copy = dict(sc)
            text = sc_copy.get("text", "")
            direction = self.synthesize_6_layer_scene(
                text,
                scene_idx=idx + 1,
                note=sc_copy.get("note", ""),
                stat_card=sc_copy.get("stat_card"),
                overlay=sc_copy.get("overlay"),
            )

            existing_prompt = sc_copy.get("prompt", "").strip()
            is_generic_boilerplate = any(
                phrase in existing_prompt.lower()
                for phrase in [
                    "lone intellectual figure frozen in sudden realization beside a mahogany desk",
                    "two scientists analyzing handwritten statistical equations and experiment logs on a large chalkboard",
                    "macro close-up of historical laboratory testing apparatus illustrating",
                    "lone exhausted person sitting in front of a glowing monitor at midnight",
                    "reacting physically to the dilemma described in",
                    "conducting controlled laboratory trials measuring",
                ]
            )

            if existing_prompt and not overwrite_custom_prompts and not is_generic_boilerplate and existing_prompt not in seen_prompts:
                clean_prompt = self.sanitize_prompt(existing_prompt)
            else:
                clean_prompt = direction.sanitized_prompt

            if clean_prompt in seen_prompts:
                clean_prompt = self.sanitize_prompt(f"Scene {idx + 1} ({direction.narrative_beat}): {clean_prompt}")
            seen_prompts.add(clean_prompt)

            sc_copy["prompt"] = clean_prompt
            sc_copy["narrative_beat"] = direction.narrative_beat
            sc_copy["genre"] = self.genre.id
            sc_copy["cap_y"] = direction.cap_y

            # Always assign 3D spatial presets instead of legacy 2D pan/zoom strings
            sc_copy["preset"] = direction.motion_preset
            sc_copy["motion"] = direction.motion_preset

            # Normalize image & video asset paths so `image` is always images/*.jpg and `video` is always videos/*.mp4
            raw_img = sc_copy.get("image", "")
            raw_vid = sc_copy.get("video", "")
            stem = Path(raw_vid or raw_img or f"s{idx+1:02d}").stem
            sc_copy["image"] = f"images/{stem}.jpg"
            sc_copy["video"] = f"videos/{stem}.mp4"

            if "shots" in sc_copy:
                fixed_shots = []
                for sh in sc_copy["shots"]:
                    if isinstance(sh, dict):
                        sh_copy = dict(sh)
                        sh_copy["video"] = sc_copy["video"]
                        sh_copy["image"] = sc_copy["image"]
                        sh_copy["motion"] = direction.motion_preset
                        fixed_shots.append(sh_copy)
                sc_copy["shots"] = fixed_shots

            enriched_scenes.append(sc_copy)

        return enriched_scenes


def upgrade_project_file(project_path: Path, genre: Optional[str] = None, overwrite: bool = True) -> dict:
    """Load a project.json, enrich all scene prompts using S4VisualDirector + Dossier, and save."""
    if not project_path.exists():
        raise FileNotFoundError(f"Project file not found: {project_path}")

    proj_data = json.loads(project_path.read_text(encoding="utf-8"))
    topic = proj_data.get("concept") or proj_data.get("topic") or proj_data.get("title", "Cognitive Psychology")
    eff_genre = genre or proj_data.get("genre", "3d_cgi")
    fmt = proj_data.get("format", "short")
    aspect = "16:9" if fmt == "long" else "9:16"

    def _norm(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")

    norm = _norm(topic)
    if not norm:
        raise ValueError(
            "dossier lookup needs a real topic - a blank one is a substring of every dossier key "
            "and silently borrows someone else's study"
        )
    dossiers_path = YT_ROOT / "channel_assets" / "scientific_dossiers.json"
    dossier = {}
    if dossiers_path.exists():
        all_dossiers = json.loads(dossiers_path.read_text(encoding="utf-8"))
        dossier = all_dossiers.get(norm, {})
        if not dossier:
            for k, v in all_dossiers.items():
                k_norm, topic_norm = _norm(k), _norm(v.get("topic"))
                if (k_norm and (k_norm in norm or norm in k_norm)) or (topic_norm and topic_norm in norm):
                    dossier = v
                    break
        if not dossier:
            print(f"  [dossier] no entry matches topic '{topic}' - visuals carry no citation grounding")
    else:
        print(f"  [dossier] {dossiers_path} is missing - visuals carry no citation grounding")

    director = S4VisualDirector(genre_key=eff_genre, topic=topic, default_aspect=aspect, dossier=dossier)
    proj_data["scenes"] = director.process_project_scenes(proj_data, genre=eff_genre, overwrite_custom_prompts=overwrite)
    proj_data["genre"] = director.genre.id
    proj_data["genre_name"] = director.genre.name
    project_path.write_text(json.dumps(proj_data, indent=2), encoding="utf-8")
    return proj_data


def main() -> int:
    ap = argparse.ArgumentParser(description="FrameForge S4 Visual Director & Semantic 3D Spatial Prompt Agent (v7.0)")
    ap.add_argument("--project", "-p", type=Path, required=True, help="Path to project.json")
    ap.add_argument("--genre", "-g", type=str, default=None, help="Optional visual genre override")
    ap.add_argument("--inplace", action="store_true", default=True, help="Update project.json in place")
    ap.add_argument("--keep-custom", action="store_true", help="Keep existing non-boilerplate custom prompts")
    args = ap.parse_args()

    updated = upgrade_project_file(args.project.resolve(), genre=args.genre, overwrite=not args.keep_custom)
    scenes = updated.get("scenes", [])
    out_fmt.emit(out_fmt.header(
        f"S4 Visual Director v7.0: {args.project.parent.name}",
        f"{len(scenes)} scenes upgraded — Genre: {updated.get('genre')}",
        "🎬"
    ))
    rows = []
    for idx, sc in enumerate(scenes, 1):
        p_raw = sc.get('prompt', '')
        prompt_snippet = (p_raw[:62] + "...") if len(p_raw) > 65 else p_raw
        rows.append([f"S{idx:02d}", sc.get('narrative_beat', 'BEAT'), sc.get('preset', '3D'), prompt_snippet])
    out_fmt.emit(out_fmt.table(["Scene", "Narrative Beat", "3D Motion", "6-Layer Prompt"], rows))
    out_fmt.emit("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
