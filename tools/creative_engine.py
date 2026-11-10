#!/usr/bin/env python3
"""FrameForge Creative & Dialectic Argument Engine (v7.0 - Unified 3D Spatial & Multi-Agent Synthesis).

Responsibilities:
  - Loads empirical dossiers from `channel_assets/scientific_dossiers.json`; missing evidence stops generation.
  - Scores spoken hooks via `youtube_skills.score_hook` (>= 70 target).
  - Choreographs 8-scene Short blueprints or multi-chapter Long-Form blueprints with 3D spatial presets.
  - Generates zero-placeholder YouTube Studio `UPLOAD_KIT_*.md` files directly (eliminating the legacy `prompt_architect.py` middleman).
"""

from __future__ import annotations

import json
import re
import sys
import zlib
from pathlib import Path
from typing import Any, Dict, List, Tuple

TOOLS_DIR = Path(__file__).resolve().parent
YT_ROOT = TOOLS_DIR.parent
DOSSIERS_PATH = YT_ROOT / "channel_assets" / "scientific_dossiers.json"
VENV_PYTHON = YT_ROOT / ".venv" / "bin" / "python"

if str(YT_ROOT) not in sys.path:
    sys.path.insert(0, str(YT_ROOT))
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

if __name__ == "__main__":
    from tools.runtime import ensure_venv_cli

    ensure_venv_cli(Path(__file__), sys.argv[1:])

from tools import genre_director  # noqa: E402
from tools import output_format as fmt  # noqa: E402
from tools import youtube_skills  # noqa: E402
from tools.schemas import PROJECT_SCHEMA_VERSION, validate_project  # noqa: E402
from tools.visual_director import S4VisualDirector  # noqa: E402


def load_dossiers() -> Dict[str, Any]:
    if DOSSIERS_PATH.exists():
        try:
            data = json.loads(DOSSIERS_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            print(f"[WARNING] Unreadable scientific_dossiers.json: {exc}", file=sys.stderr)
            return {}
    return {}


def normalize_topic_key(topic: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", topic.strip().lower()).strip("_")


def score_hook_candidate(hook: str) -> Tuple[int, str, str]:
    """Return (numeric_score, band_label, weakest_dimension) from youtube_skills.score_hook."""
    res = youtube_skills.score_hook(hook)
    score = int(res.get("verdict", 0))
    band = str(res.get("band", "weak")).upper()
    weakest = str(res.get("weakest", ""))
    return score, band, weakest


class MissingDossier(KeyError):
    """Raised when a topic has no verified study on file.

    The previous behaviour here invented one: "Stanford & Princeton Cognitive
    Labs", 1984, "3.1x Friction". voice.md forbids misattributed research, and
    YouTube treats a fabricated citation as misleading metadata.
    """


class AmbiguousDossier(MissingDossier):
    """Raised when a partial topic identifies more than one local study."""


def _require_field(dossier: Dict[str, Any], key: str, topic: str) -> str:
    """Read a dossier field that must exist, naming the topic that is short one field."""
    value = str(dossier.get(key) or "").strip()
    if not value:
        raise MissingDossier(
            f"Dossier for '{topic}' is missing '{key}'. Fill it in "
            f"channel_assets/scientific_dossiers.json with the verified value."
        )
    return value


def find_dossier_entry(topic: str, dossiers: Dict[str, Any] | None = None) -> tuple[str, Dict[str, Any]]:
    """Resolve one local dossier, preferring exact key or topic matches over partial ones."""
    dossiers = load_dossiers() if dossiers is None else dossiers
    norm = normalize_topic_key(topic)
    if not norm:
        raise MissingDossier(
            f"'{topic}' names no topic at all. An empty key is a substring of every dossier key, so "
            "matching it would hand this video someone else's study - state the topic or add the "
            "entry to channel_assets/scientific_dossiers.json."
        )

    exact_matches = []
    partial_matches = []
    for key, dossier in dossiers.items():
        if not isinstance(dossier, dict):
            continue
        key_norm = normalize_topic_key(str(key))
        stored_topic = normalize_topic_key(str(dossier.get("topic") or ""))
        if norm in {key_norm, stored_topic}:
            exact_matches.append((key, dossier))
        elif (key_norm and (key_norm in norm or norm in key_norm)) or (stored_topic and stored_topic in norm):
            partial_matches.append((key, dossier))
    matches = exact_matches or partial_matches
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise AmbiguousDossier(f"Multiple dossiers match '{topic}'; pass a reviewed --dossier file instead of guessing.")

    known = ", ".join(sorted(dossiers)) or "none yet"
    raise MissingDossier(
        f"No verified study on file for '{topic}'.\n"
        f"  Add an entry to channel_assets/scientific_dossiers.json before producing this video,\n"
        f"  with a real researcher, institution, year and the quantitative result you intend to say\n"
        f"  out loud on camera. Existing keys: {known}."
    )


def synthesize_dossier(topic: str) -> Dict[str, Any]:
    """Return the one matching local dossier, or raise MissingDossier."""
    return find_dossier_entry(topic)[1]


# The long-form anchors a Short's "Related Video" points at, keyed by the id an operator types into
# the Studio selector. The titles here must match what is actually published: this table used to be
# two copies of the LV-02 string, and every kit in the repo inherited whatever the copy said.
LONGFORM_ANCHORS = {
    "LV-01": "Dopamine Exhaustion: Why You Can’t Focus Anymore",
    "LV-02": "The 3 Hidden Brain Traps Destroying Your Focus",
}

# Watch URLs for the same two anchors, verified live on the channel on 2026-11-03. A kit description
# has to name a destination the viewer can actually reach: the versions of this template that shipped
# told viewers to "tap the Related Video button above" (a Studio-only field the API can neither read
# nor set, so an empty one makes the call-to-action dead) and to "check the bio link" for a "Focus
# Architecture OS" — the channel has no channel links at all. Every Short inherited both.
LONGFORM_URLS = {
    "LV-01": "https://youtu.be/f2vsYJOyZ3U",
    "LV-02": "https://youtu.be/1Tg-y7fqAn4",
}
CHANNEL_URL = "https://www.youtube.com/@CognitiveCoreOfficial"


def _search_tag(text: str) -> str:
    """Fold one candidate into a single Studio tag, or return "" when it cannot be one.

    The tag field splits on commas and YouTube caps a tag at 30 characters, so a raw citation
    ("Philip Brickman, Dan Coates & Ronnie Janoff-Bulman (1978)") used to reach the kit as two
    oversized fragments that YouTube drops silently — and every kit inherits its tag block from
    here, so the fix belongs in this function rather than in one hand-edited kit. Surnames plus
    the year is what actually searches ("kahneman tversky 1979" is what SH-15 carries live), so
    build that and shed surnames from the right until the tag fits.
    """
    raw = str(text or "")
    body = re.sub(r"\s+", " ", raw.strip().lower().split("(")[0])
    year = re.search(r"\b(?:1[89]\d{2}|20\d{2})\b", raw)
    parts = [p.strip(" .&;") for p in re.split(r",| & | and ", body) if p.strip(" .&;")]
    if not parts:
        return ""
    words = [p.split()[-1] for p in parts] if (len(parts) > 1 or year) else body.split()
    suffix = f" {year.group(0)}" if year else ""
    while words:
        tag = " ".join(words) + suffix
        if len(tag) <= 30:
            return tag if len(tag) >= 3 else ""
        words = words[:-1]
    return ""


def resolve_related_target(topic: str) -> tuple[str, str]:
    """Smart related video selection matching topic cluster to long-form anchor."""
    t_low = topic.lower()
    anchor = "LV-01" if any(
        k in t_low for k in ["dopamine", "exhaustion", "screen", "scrolling", "phone", "burnout", "sleep", "baseline"]
    ) else "LV-02"
    return anchor, LONGFORM_ANCHORS[anchor]


def _percent_stat(stat: str) -> str:
    """Return the stat only if it really is a percentage; otherwise an empty string.

    "31% vs 3%" -> "31%". "2.4x Asymmetry" -> "" (it is a ratio, so putting it in
    "Why {x} of People Freeze" would state a number the study never reported).
    """
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*%", str(stat or ""))
    if not m:
        return ""
    percentage = float(m.group(1))
    return f"{m.group(1)}%" if 0 < percentage < 100 else ""


def generate_title_suite(topic: str, year: str = "", stat: str = "") -> List[dict[str, str]]:
    """Generate high-CTR title angles, dropping any angle whose evidence slot is empty."""
    clean_topic = topic.strip().title()
    title_stat = _percent_stat(stat)
    candidates = [
        (
            bool(year),
            {
                "angle": "Primary (Visceral Second-Person Hook)",
                "title": f"{clean_topic}: The {year} Study On Why You Freeze",
                "notes": "Under 55 characters | Challenges common assumption with the study year",
            },
        ),
        (
            bool(title_stat),
            {
                "angle": "Curiosity Paradox (Contrarian Number)",
                "title": f"Why {title_stat} of People Freeze During {clean_topic}",
                "notes": "Only used when the dossier carries a real percentage",
            },
        ),
        (
            True,
            {
                "angle": "Negativity Bias (Threat Urgency)",
                "title": f"Stop Letting {clean_topic} Hijack Your Brain",
                "notes": "Direct second-person stakes targeting subconscious mental friction",
            },
        ),
        (
            True,
            {
                "angle": "Behavioral Reset (5-Second Protocol)",
                "title": f"The 5-Second Trick That Stops {clean_topic}",
                "notes": "Action-oriented framing that compels viewer to stay through the loop",
            },
        ),
        (
            bool(year),
            {
                "angle": "Empirical Archive (Primary Source)",
                "title": f"The {year} {clean_topic} Experiment That Changed Psychology",
                "notes": "Documentary-style credibility framing for analytical audience",
            },
        ),
    ]
    titles = [t for ok, t in candidates if ok]
    if len(titles) < 3:
        raise MissingDossier(
            f"'{topic}' needs a real study year or a real percentage to title honestly. "
            "Fill 'year' and 'quantitative_stat' in channel_assets/scientific_dossiers.json."
        )
    return titles[:5]


DESCRIPTION_OPENINGS = [
    "Ever notice how {topic_lower} happens the exact moment you need your brain to perform? It is not bad luck or lack of discipline. {citation} measured what the brain does with priority when this triggers.",
    "If you find yourself freezing or overthinking during {topic_lower}, the mechanism is not a broken prefrontal cortex. {citation} tested this directly, and the result is specific.",
    "There is a quiet cost running every time {topic_lower} triggers. {citation} documented how the reflex distorts risk and locks you into the same loop.",
    "In {year}, {citation} measured it: {stat}. That number is why {topic_lower} costs more than it looks like it should.",
    "Your brain conserves energy and avoids perceived loss. During {topic_lower} that instinct misfires. {citation} is where the evidence comes from, and the override is at the end.",
]

PINNED_COMMENTS = [
    "How many times did your brain pull this exact glitch on you this week? Be honest 👇🚨",
    "What's the one moment this week where you caught yourself in this loop? Drop it below 👇",
    "Did you realize your brain was running this penalty, or did you think it was just tiredness? Be honest 👇🧠",
    "Have you ever tried using a physical reset when this hits? Tell me what happened 👇",
    "Which cognitive trap do you want us to dissect in our next documentary? Let us know below 👇",
]


def generate_upload_kit_content(
    video_id: str,
    title: str,
    topic: str,
    citation: str,
    related_target: str | None = None,
    related_target_title: str | None = None,
    is_synthetic: bool = True,
    playlist_name: str = "Cognitive Biases & Mental Glitches",
    slug: str | None = None,
    year: str = "",
    stat: str = "",
) -> str:
    """Generate complete, humanized 0-to-1 UPLOAD_KIT markdown with prominent top verification notices."""
    slug_hint = slug or f"short_{video_id.lower().replace('sh-', '')}_{topic.lower().replace(' ', '_')}"
    synthetic_label = "Yes" if is_synthetic else "No"
    synthetic_reason = (
        "Photorealistic 3D Spatial FLUX scenes"
        if is_synthetic
        else "Stylized motion graphic animation"
    )
    clean_title = re.sub(r"\s*#Shorts\b", "", title, flags=re.IGNORECASE).strip()

    # Smart related target resolution if not explicitly overridden
    if not related_target:
        auto_target, auto_target_title = resolve_related_target(topic)
        rel_target = auto_target
        rel_title = auto_target_title
    else:
        rel_target = related_target
        rel_title = related_target_title or LONGFORM_ANCHORS.get(related_target, related_target)
    rel_url = LONGFORM_URLS.get(rel_target, CHANNEL_URL)

    # Pick an opening deterministically, and only from templates whose evidence
    # slots are actually filled — an empty year or stat must not silently print
    # the placeholder default into a published description.
    h_idx = zlib.crc32(f"{video_id}_{topic}".encode())
    candidates = [
        t for t in DESCRIPTION_OPENINGS
        if ("{year}" not in t or year) and ("{stat}" not in t or stat)
    ] or [DESCRIPTION_OPENINGS[0]]
    opening_template = candidates[h_idx % len(candidates)]
    opening_text = opening_template.format(
        topic_lower=topic.lower(),
        citation=citation,
        year=year,
        stat=stat,
    )
    pinned_comment = PINNED_COMMENTS[h_idx % len(PINNED_COMMENTS)]

    # Generate 5 diverse title angles
    titles = generate_title_suite(topic, year=year, stat=stat)
    title_markdown_blocks = []
    for idx, t in enumerate(titles, 1):
        clean_t = re.sub(r"\s*#Shorts\b", "", t["title"], flags=re.IGNORECASE).strip()
        heading = f"**Primary Title — Option {idx}: {t['angle']}**" if idx == 1 else f"**Option {idx}: {t['angle']}**"
        title_markdown_blocks.append(
            f"* {heading}:\n"
            f"> `{clean_t} #shorts`\n"
            f"  *({t['notes']})*"
        )
    titles_rendered = "\n".join(title_markdown_blocks)

    # Sanitize tags: strictly lowercase, one field each, inside YouTube's own cap.
    tags_list = [
        topic,
        citation,
        "cognitive biases",
        "psychology facts",
        "neuroscience of focus",
        "human behavior",
        "behavioral psychology",
        "cognitive core",
        "brain glitches",
        "habit science",
    ]
    # Deduplicate and clean
    tags_clean = ", ".join(dict.fromkeys(t for t in (_search_tag(x) for x in tags_list) if t))

    return f"""# YouTube Upload Kit — {video_id}: {clean_title}
**Channel**: Cognitive Core ([@CognitiveCoreOfficial](https://www.youtube.com/@CognitiveCoreOfficial))  
**Target Video File**: `shorts/{slug_hint}/output/{slug_hint}.mp4`  

---

> ### ⚠️ UPLOAD-TIME ACTION & VALUE VERIFICATION NOTICE
> **Review these settings before clicking publish in YouTube Studio:**
> 
> * **Hardcoded Global Channel Defaults (Pre-set for Channel Safety):**
>   * `Audience (COPPA)`: **"No, it's not made for kids"** (Enables comments, notifications, and viewer analytics).
>   * `Video Language`: **English (United States)**
>   * `Caption Certification`: **"This content has never aired on television in the U.S."**
>   * `License`: **Standard YouTube License** (Prevents unauthorized Creative Commons scraping).
>   * `Shorts Remixing`: **"Allow video and audio remixing"** (Maximizes organic viral reach).
>   * `Distribution`: **"Publish to subscriptions feed and notify subscribers"** (Checked).
> * **Values You Must Verify / Swap for this Specific Upload:**
>   * `Related Video Target`: Link to **`{rel_target}` (*{rel_title}*)**. *Search "{rel_target}" in the YouTube Studio Related Video selector.*
>   * `Altered / Synthetic Media Disclosure`: Select **"{synthetic_label}"** ({synthetic_reason}).
>   * `Target Playlist`: Add to **"{playlist_name}"** (or create if missing).
>   * `Visibility State`: Upload as **Unlisted** first $\\to$ wait 10–15 min for 1080p VP09 processing $\\to$ switch to **Public**.

---

## 0. Build & Verification Commands
```bash
# 1. Build 3D spatial video assets (FLUX plates, 3-plane 3D camera render, studio TTS +1%/-2Hz, 0.18 BGM mid/side ducking, 14 Mbps MP4):
python tools/pipeline.py --build shorts/{slug_hint}/project.json

# 2. Run automated Pre-Upload Quality Gate:
python tools/pipeline.py --verify-all
```

---

## 1. High-CTR Humanized Titles (Test & Pick One)

{titles_rendered}

---

## 2. Humanized Description (100% Ready to Copy & Paste)

```text
{opening_text}

Here is the simple 5-second behavioral reset to snap out of the trance before it derails your focus.

Full focus breakdown: {rel_url}

More on focus, habits and cognitive science: {CHANNEL_URL}

#{topic.lower().replace(' ', '')} #psychology #brainhacks #shorts
```

---

## 3. High-Engagement Pinned Comment & Golden-Hour Strategy

### Pinned Comment (Copy & Paste within 60 Seconds of Going Public)
> **"{pinned_comment}"**

### Golden-Hour Engagement Protocol (First 60 Minutes)
1. **Pin Immediately**: Pin the prompt comment above the second the Short is switched to Public.
2. **First 10 Replies**: Heart and reply to the first 5–10 viewer comments within the first 45 minutes to trigger YouTube's initial velocity algorithm.
3. **Funnel Inquiries**: If a viewer asks a question about focus or memory, reply with the long-form link
   itself ({rel_url}) — the Related Video button is set by hand in Studio and is empty until someone sets it,
   so never point a viewer at "the link above the title".

---

## 4. Complete YouTube Studio Settings Checklist (All 10 Settings)

| # | Setting | Required Value | Notes |
| :-: | :--- | :--- | :--- |
| **1** | **Title** | `[Selected title from Section 1]` | Under 60 chars recommended for mobile feeds. |
| **2** | **Description** | `[Copy from Section 2]` | Contextual grounding for NLP; includes Related Video CTA. |
| **3** | **Related Video** | Select **`{rel_target}`** | **CRITICAL**: The ONLY interactive 1-tap link on Shorts. |
| **4** | **Playlist** | **"{playlist_name}"** | Maximizes consecutive autoplay watch time. |
| **5** | **Audience** | **"No, it's not made for kids"** | Mandatory COPPA rule; preserves comments & bell. |
| **6** | **Altered Content**| **"{synthetic_label}"** | {synthetic_reason}. |
| **7** | **Shorts Remixing**| **"Allow video and audio remixing"** | Enables viewer sound re-use and viral reach. |
| **8** | **Language & Cert**| **English (US)** \\| **Never aired on US TV** | Accelerates automated subtitle indexing. |
| **9** | **License** | **Standard YouTube License** | Prevents unauthorized commercial CC re-uploads. |
| **10**| **Visibility** | **Unlisted** $\\to$ wait 10m $\\to$ **Public** | Allows 1080p VP09 encoding & copyright scan. |

---

## 5. Defensive Search Tags & Keywords (100% Lowercase)
```text
{tags_clean}
```
"""


def choreograph_scenes(dossier: Dict[str, Any], genre: str = "3d_cgi") -> List[Dict[str, Any]]:
    """Build bespoke 8-scene 3D spatial narrative with exact empirical evidence and 6-layer 3D visual direction."""
    topic = _require_field(dossier, "topic", "requested topic")
    grounded = {
        key: _require_field(dossier, key, topic)
        for key in (
            "year", "publication", "primary_researchers", "institution", "quantitative_stat",
            "best_hook", "broken_assumption", "comparison_text", "biological_mechanism",
            "real_world_tax", "willpower_trap", "five_second_override", "loop_bridge",
        )
    }
    prof = genre_director.get_genre_profile(genre)
    year = grounded["year"]
    researchers = grounded["primary_researchers"]
    citation = f"{researchers} ({year})"
    hook = grounded["best_hook"]
    overlay = dossier.get("overlay_text") or topic.upper()[:22]
    comp_text = grounded["comparison_text"]
    stat_title = grounded["quantitative_stat"]
    stat_sub = dossier.get("stat_subtitle") or citation
    mech = grounded["biological_mechanism"]
    tax = grounded["real_world_tax"]
    willpower = grounded["willpower_trap"]
    override = grounded["five_second_override"]
    loop = grounded["loop_bridge"]

    presets = list(prof.recommended_presets)
    p_len = len(presets)

    verb_prefix = "" if comp_text.strip().lower().startswith(("showed", "experienced", "suffered", "refused", "lost", "had", "if ", "within ", "the ")) else "showed "
    # Never name a method the dossier has not earned: Brickman's lottery study was field
    # interviews, Iyengar's booth was in-store, and only a genuine lab test deserves "laboratory".
    scene_3_text = (
        f"In mathematical modeling, {comp_text}."
        if comp_text.strip().lower().startswith("if ")
        else f"In the published data, {comp_text}."
        if comp_text.strip().lower().startswith(("within ", "the "))
        else f"In the published data, participants {verb_prefix}{comp_text}."
    )

    raw_scenes = [
        {
            "image": "images/s01_hook.jpg",
            "video": "videos/s01_hook.mp4",
            "shots": [
                {"video": "videos/s01_hook.mp4", "motion": presets[0 % p_len], "zoom": 1.0},
                {"video": "videos/s01_hook.mp4", "motion": presets[0 % p_len], "focus": [0.5, 0.42], "zoom": 1.18},
            ],
            "motion": presets[0 % p_len],
            "preset": presets[0 % p_len],
            "text": hook,
            "overlay": {"text": overlay, "until": 2.6},
            "cap_y": 0.66,
        },
        {
            "image": "images/s02_researchers.jpg",
            "video": "videos/s02_researchers.mp4",
            "motion": presets[1 % p_len],
            "preset": presets[1 % p_len],
            "text": grounded["broken_assumption"],
            "note": citation,
            "cap_y": 0.66,
        },
        {
            "image": "images/s03_stat.jpg",
            "video": "videos/s03_stat.mp4",
            "motion": presets[2 % p_len],
            "preset": presets[2 % p_len],
            "text": scene_3_text,
            "stat_card": {"title": stat_title, "subtitle": stat_sub},
            "cap_y": 0.66,
        },
        {
            "image": "images/s04_biology.jpg",
            "video": "videos/s04_biology.mp4",
            "motion": presets[3 % p_len],
            "preset": presets[3 % p_len],
            "text": f"{mech}",
            "cap_y": 0.66,
        },
        {
            "image": "images/s05_consequence.jpg",
            "video": "videos/s05_consequence.mp4",
            "motion": presets[0 % p_len],
            "preset": presets[0 % p_len],
            "text": f"{tax}",
            "cap_y": 0.66,
        },
        {
            "image": "images/s06_trap.jpg",
            "video": "videos/s06_trap.mp4",
            "motion": presets[1 % p_len],
            "preset": presets[1 % p_len],
            "text": f"{willpower}",
            "cap_y": 0.66,
        },
        {
            "image": "images/s07_override.jpg",
            "video": "videos/s07_override.mp4",
            "motion": presets[2 % p_len],
            "preset": presets[2 % p_len],
            "text": f"{override}",
            "cap_y": 0.70,
        },
        {
            "image": "images/s08_loop.jpg",
            "video": "videos/s08_loop.mp4",
            "motion": "depthflow_spiral",
            "preset": "depthflow_spiral",
            "text": f"{loop}",
            "pause": 0.0,
            "cap_y": 0.66,
        },
    ]

    director = S4VisualDirector(genre_key=prof.id, topic=topic, default_aspect="9:16", dossier=dossier)
    return director.process_project_scenes(raw_scenes, genre=prof.id)


def generate_creative_project(
    topic: str,
    video_id: str,
    slug: str,
    genre: str | None = None,
    output_root: Path | None = None,
    dossier: Dict[str, Any] | None = None,
    scenes: List[Dict[str, Any]] | None = None,
    overwrite: bool = False,
    voice: str = "kokoro",
    variant: str = "cinematic_35mm",
    channel_id: str = "UC6hwVBnsfvfUGxfZi2sFT3A",
) -> Path:
    """End-to-end dialectic blueprint synthesis: Research Dossier -> Hook Verification -> 8-Scene 3D Choreography -> Upload Kit.

    `dossier` and `scenes` may be supplied by a verified orchestrator run. Otherwise
    the dossier must resolve from the local source, and missing narration fields stop generation.
    """
    base_dir = (output_root or (YT_ROOT / "shorts")) / slug
    proj_path = base_dir / "project.json"
    if proj_path.exists() and not overwrite:
        raise FileExistsError(f"Project already exists: {proj_path}")

    dossier = dossier or synthesize_dossier(topic)
    eff_genre = genre or dossier.get("recommended_genre", "3d_cgi")
    prof = genre_director.get_genre_profile(eff_genre)

    if scenes is None:
        scenes = choreograph_scenes(dossier, genre=prof.id)
    if isinstance(scenes, list):
        scenes = [scene.copy() if isinstance(scene, dict) else scene for scene in scenes]
        for index, scene in enumerate(scenes, 1):
            if isinstance(scene, dict):
                scene.setdefault("id", f"s{index:02d}")
                scene.setdefault("caption", scene.get("text"))

    draft = {
        "schema_version": PROJECT_SCHEMA_VERSION,
        "id": video_id,
        "variant": variant,
        "format": "short",
        "voice": voice,
        "channel_id": channel_id,
        "scenes": scenes,
    }
    errors = validate_project(draft, project_path=proj_path)
    if errors:
        raise ValueError("\n".join(errors))

    hook_text = scenes[0]["text"]
    h_score, h_band, h_weak = score_hook_candidate(hook_text)

    for sub in ("images", "videos", "output", "cache"):
        (base_dir / sub).mkdir(parents=True, exist_ok=True)

    all_words = len(re.findall(r"\b\w+\b", " ".join(s["text"] for s in scenes)))
    est_duration = round((all_words / 150.0) * 60.0, 1)

    year = _require_field(dossier, "year", topic)
    primary_title = f"{dossier['topic']}: The {year} Study On Why You Freeze"
    if len(primary_title) > 58:
        primary_title = f"The {year} {dossier['topic']} Study: Why You Freeze"

    proj_data = {
        **draft,
        "title": f"{dossier['topic']} - {video_id}",
        "concept": dossier["topic"],
        "science": f"{dossier.get('primary_researchers')} ({year})",
        "citation_stat": dossier.get("quantitative_stat", ""),
        "citation_verified": True,
        "contains_synthetic_media": True,
        "genre": prof.id,
        "genre_name": prof.name,
        "color_palette": prof.color_palette,
        "bgm_mood": prof.bgm_mood,
        "rate": "+1%",
        "pitch": "-2Hz",
        "gap": 0.08,
        "tail": 0.2,
        "progress_bar": True,
        "music": {
            "volume": 0.18,
            "sfx_volume": 0.12,
            "seed": 42,
            "bpm": 74,
        },
        "metadata": {
            "cluster": dossier.get("cluster"),
            "story_arc": dossier.get("story_arc", "The Midnight Desk Chronicles"),
            "chapter_number": dossier.get("chapter_number", 1),
            "chapter_title": dossier.get("chapter_title", f"Chapter: {dossier['topic']}"),
            "protagonist": dossier.get("protagonist", ""),
            "prev_episode": dossier.get("prev_episode", ""),
            "next_episode": dossier.get("next_episode", ""),
            "dossier_source": dossier.get("publication"),
            "hook_score": h_score,
            "hook_band": h_band,
            "hook_weakest": h_weak,
            "word_count": all_words,
            "estimated_duration_sec": est_duration,
        },
    }

    # Exclusive creation also protects a project created after the preflight check.
    with proj_path.open("w" if overwrite else "x", encoding="utf-8") as handle:
        handle.write(json.dumps(proj_data, indent=2))

    kit_path = base_dir / f"UPLOAD_KIT_{video_id.replace('-', '')}.md"
    kit_content = generate_upload_kit_content(
        video_id=video_id,
        title=primary_title,
        topic=dossier["topic"],
        citation=f"{dossier.get('primary_researchers')} ({year}, {dossier.get('publication')})",
        related_target=dossier.get("related_target"),
        related_target_title=dossier.get("related_title"),
        slug=slug,
        year=year,
        stat=dossier.get("quantitative_stat", ""),
    )
    kit_path.write_text(kit_content, encoding="utf-8")

    try:
        display_path = proj_path.resolve().relative_to(YT_ROOT.resolve())
    except ValueError:
        display_path = proj_path.resolve()
    card = fmt.project_card(
        video_id=video_id,
        topic=dossier["topic"],
        genre=prof.name,
        hook_score=h_score,
        hook_band=h_band,
        word_count=all_words,
        est_duration=est_duration,
        scene_count=len(scenes),
        researchers=dossier.get("primary_researchers", "Researchers"),
        year=year,
        proj_path=str(display_path),
    )
    fmt.emit(card)
    return proj_path
