#!/usr/bin/env python3
"""NegativePromptAgent - Intelligent Negative Constraint & Prompt Sanitization Specialist.

Solves the dual-paradigm negative prompting challenge:
1. Direct Negative Generation: For models supporting a negative prompt tensor (SDXL, FLUX.2 Klein,
   Stable Diffusion), compiles high-potency negative token clusters by aesthetic genre.
2. Semantic Constraint Inversion: For flow-matching models without guidance embeddings (FLUX.3
   distilled / schnell) that hard-error on --negative-prompt, inverts negative constraints into
   affirmative optical and stylistic anchors (e.g. "no cartoon" -> "authentic 35mm photorealistic still").
3. Prompt Sanitization & Pruning: Neutralizes negation traps (e.g. "not wearing a hat" -> "bareheaded")
   and strips hallucination triggers.
4. Asset & Cutout Isolation: Tailors negative constraints for clean transparent asset and prop generation.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class NegativePromptResult:
    """Output bundle from the Negative Prompt Agent."""
    genre: str
    target_model: str
    negative_prompt: str
    inverted_positive_anchors: List[str]
    optimized_prompt: str
    pruned_negations: List[Tuple[str, str]] = field(default_factory=list)
    supports_native_negative: bool = False

    @property
    def affirmative_anchors(self) -> List[str]:
        return self.inverted_positive_anchors

    @property
    def sanitized_prompt(self) -> str:
        return self.optimized_prompt


@dataclass
class AgentReport:
    """Agent execution report."""
    agent_name: str
    role: str
    status: str
    duration_s: float
    summary: str
    metrics: Dict[str, Any] = field(default_factory=dict)


class NegativePromptAgent:
    """Specialized Agent for negative constraint engineering across diffusion and DiT flow models."""

    name: str = "NegativePromptAgent"
    role: str = "Negative Constraint & Prompt Sanitization Specialist"
    emoji: str = "🛡️"

    # Genre-tailored negative prompt clusters (for models supporting --negative-prompt)
    GENRE_NEGATIVES: Dict[str, List[str]] = {
        "cinematic_35mm": [
            "CGI", "3D render", "digital painting", "cartoon", "anime", "illustration",
            "plastic skin", "airbrushed", "oversaturated", "flat lighting", "deformed eyes",
            "extra limbs", "mutated hands", "bad anatomy", "blurry", "low resolution",
            "chromatic aberration artifacts", "jpeg compression", "watermark", "signature", "text",
        ],
        "3d_cgi": [
            "flat 2D vector", "hand-drawn sketch", "watercolor", "low poly", "muddy textures",
            "pixelated", "washed out colors", "harsh clipping", "amateur render", "noisy shadows",
            "deformed geometry", "watermark", "text",
        ],
        "3d_minimalist": [
            "visual clutter", "busy textured background", "chaotic lighting", "harsh grime",
            "photorealistic dirt", "distressed surfaces", "oversaturated neon", "crowded composition",
            "deformed shapes", "watermark", "text",
        ],
        "kinetic_explainer": [
            "photorealistic human face", "organic grunge", "messy textures", "complex background",
            "film grain", "lens dirt", "blurry edges", "distorted typography", "watermark",
        ],
        "cyberpunk_neon": [
            "daylight pastel", "sepia", "rural landscape", "muddy darks", "low contrast",
            "washed out glow", "blurry HUD", "distorted lines", "watermark", "text",
        ],
        "3d_tactile": [
            "flat 2D vector", "hand-drawn sketch", "watercolor", "low poly", "muddy textures",
            "pixelated", "washed out colors", "harsh clipping", "watermark", "text",
        ],
        "asset_cutout": [
            "complex background", "busy scenery", "scene clutter", "drop shadow on backdrop",
            "cropped edges", "partially out of frame", "overlapping objects", "blurry contour",
            "watermark", "text", "signature",
        ],
    }

    # Common negation trap patterns and their affirmative equivalents
    NEGATION_TRAPS: List[Tuple[re.Pattern, str]] = [
        (re.compile(r"\bnot wearing (?:a |an )?hat\b", re.IGNORECASE), "bareheaded"),
        (re.compile(r"\bnot wearing (?:any )?glasses\b", re.IGNORECASE), "unobstructed eyes, without eyewear"),
        (re.compile(r"\bwithout (?:a |an )?beard\b", re.IGNORECASE), "clean-shaven"),
        (re.compile(r"\bnot smiling\b", re.IGNORECASE), "serious stoic expression"),
        (re.compile(r"\bnot crowded\b", re.IGNORECASE), "solitary, isolated"),
        (re.compile(r"\bno background\b", re.IGNORECASE), "isolated on solid neutral backdrop"),
        (re.compile(r"\bnot blurry\b", re.IGNORECASE), "razor-sharp optical focus"),
        (re.compile(r"\bnot cartoon\b", re.IGNORECASE), "photorealistic 35mm documentary still"),
        (re.compile(r"\bno text\b", re.IGNORECASE), "clean visual frame without typography"),
    ]

    # Affirmative optical anchors that invert negative goals for FLUX.3 and flow models
    INVERTED_AFFIRMATIVES: Dict[str, List[str]] = {
        "cinematic_35mm": [
            "authentic 35mm optical capture",
            "genuine skin pores and natural micro-texture",
            "Kodak Portra 400 tonal response",
            "precise anatomical articulation",
            "clean frame without overlay text or logos",
        ],
        "3d_cgi": [
            "high-fidelity Octane and Unreal Engine 5 PBR shaders",
            "subsurface scattering and volumetric depth",
            "crisp specular highlights",
            "clean geometry with smooth bevels",
        ],
        "3d_minimalist": [
            "pristine spatial composition",
            "calm balanced negative space",
            "diffused ambient softbox illumination",
            "pure tactile material finishes",
        ],
        "kinetic_explainer": [
            "bold isometric precision",
            "clean geometric vector depth",
            "crisp contour definition",
            "deliberate color harmony",
        ],
        "cyberpunk_neon": [
            "atmospheric dark sci-fi volumetric neon haze",
            "sharp chromatic contrast and glowing phosphor accents",
            "clean futuristic industrial reflections",
            "precise optical lens flare and high dynamic range",
        ],
        "3d_tactile": [
            "tactile physical clay and matte porcelain material finishes",
            "subtle volumetric rim lighting",
            "soft ambient occlusion shadows",
            "clean macro depth-of-field with tangible surface texture",
        ],
        "asset_cutout": [
            "isolated subject centered in frame",
            "sharp crisp silhouettes with clear boundary contours",
            "uniform high-contrast lighting for seamless extraction",
        ],
    }

    def compile_negative_prompt(self, genre: str, custom_negatives: Optional[List[str]] = None) -> str:
        """Compile a comma-separated negative prompt string for models that support it."""
        genre_key = genre.lower().strip()
        tokens = list(self.GENRE_NEGATIVES.get(genre_key, self.GENRE_NEGATIVES["cinematic_35mm"]))
        if custom_negatives:
            tokens.extend([c.strip() for c in custom_negatives if c.strip()])
        # Deduplicate while preserving order
        seen = set()
        deduped = []
        for t in tokens:
            t_low = t.lower()
            if t_low not in seen:
                seen.add(t_low)
                deduped.append(t)
        return ", ".join(deduped)

    def sanitize_negations(self, prompt: str) -> Tuple[str, List[Tuple[str, str]]]:
        """Convert negative syntax traps ('not wearing X') into affirmative descriptions."""
        sanitized = prompt
        pruned = []
        for pattern, replacement in self.NEGATION_TRAPS:
            if pattern.search(sanitized):
                matched = pattern.search(sanitized).group(0)
                sanitized = pattern.sub(replacement, sanitized)
                pruned.append((matched, replacement))
        return sanitized, pruned

    def invert_negative_constraints(self, genre: str) -> List[str]:
        """Return positive optical anchors that enforce negative goals for models without negative prompts."""
        genre_key = genre.lower().strip()
        return list(self.INVERTED_AFFIRMATIVES.get(genre_key, self.INVERTED_AFFIRMATIVES["cinematic_35mm"]))

    def process(
        self,
        prompt: str,
        genre: str = "cinematic_35mm",
        target_model: str = "flux3",
        custom_negatives: Optional[List[str]] = None,
        is_asset_cutout: bool = False,
    ) -> NegativePromptResult:
        """Process a prompt and return the complete negative and optimized prompt package."""
        effective_genre = "asset_cutout" if is_asset_cutout else genre

        # 1. Sanitize negation traps
        sanitized_prompt, pruned = self.sanitize_negations(prompt)

        # 2. Check model negative prompt support
        model_name = target_model.lower()
        supports_native = not ("flux3" in model_name or "flux-3" in model_name)

        # 3. Generate native negative prompt
        negative_prompt = self.compile_negative_prompt(effective_genre, custom_negatives)

        # 4. Generate affirmative anchors
        anchors = self.invert_negative_constraints(effective_genre)
        if custom_negatives:
            for neg in custom_negatives:
                n_low = neg.lower()
                if "hand" in n_low or "finger" in n_low:
                    anchors.append("anatomically correct hands with five distinct fingers")
                elif "blur" in n_low or "sharp" in n_low:
                    anchors.append("crystal clear sharp optical focus")
                elif "face" in n_low:
                    anchors.append("symmetrical lifelike facial proportions")
                elif "text" in n_low or "watermark" in n_low:
                    anchors.append("clean plate with zero text or overlay typography")

        # 5. Formulate optimized prompt
        if not supports_native:
            # Model doesn't support --negative-prompt; inject affirmative optical anchors into prompt
            anchor_block = ", ".join(anchors)
            optimized_prompt = f"{sanitized_prompt.rstrip('. ')}. {anchor_block}."
        else:
            optimized_prompt = sanitized_prompt

        return NegativePromptResult(
            genre=effective_genre,
            target_model=target_model,
            negative_prompt=negative_prompt,
            inverted_positive_anchors=anchors,
            optimized_prompt=optimized_prompt,
            pruned_negations=pruned,
            supports_native_negative=supports_native,
        )

    def run(
        self,
        prompt: str,
        genre: str = "cinematic_35mm",
        target_model: str = "flux3",
        past_qa_failures: Optional[List[str]] = None,
        is_asset_cutout: bool = False,
    ) -> Tuple[NegativePromptResult, AgentReport]:
        """Agent execution: scene prompt + past QA failures -> negative prompt bundle & report."""
        t0 = time.time()
        custom = list(past_qa_failures or [])
        res = self.process(
            prompt=prompt,
            genre=genre,
            target_model=target_model,
            custom_negatives=custom,
            is_asset_cutout=is_asset_cutout,
        )

        mode_desc = "native --negative-prompt" if res.supports_native_negative else "affirmative optical anchors"
        qa_note = f" (injected {len(custom)} past QA feedback terms)" if custom else ""
        summary = (
            f"Negative Prompt Agent: {res.genre} on {target_model} via {mode_desc}{qa_note} | "
            f"Negatives={len(res.negative_prompt.split(', '))} tokens"
        )

        return res, AgentReport(
            agent_name=self.name,
            role=self.role,
            status="PASS",
            duration_s=round(time.time() - t0, 3),
            summary=summary,
            metrics={
                "genre": res.genre,
                "target_model": res.target_model,
                "supports_native_negative": res.supports_native_negative,
                "negative_token_count": len(res.negative_prompt.split(", ")),
                "pruned_negations_count": len(res.pruned_negations),
                "injected_qa_failures": custom,
            },
        )
