"""Compatibility adapter for production commands predating the canonical master."""

from __future__ import annotations

from pathlib import Path

from tools.orchestrator.contracts import RunState

ROOT = Path(__file__).resolve().parents[2]


def run_production_compat(
    *,
    topic: str,
    video_id: str,
    slug: str,
    genre: str = "3d_cgi",
    blueprint_only: bool = False,
    force_motion: bool = False,
    dossier: str | None = None,
    hook_min: int = 70,
    dry_run: bool = False,
) -> RunState:
    """Run the canonical production workflow for an older CLI caller."""
    from tools.orchestrator.cli import run_production_workflow

    return run_production_workflow(
        topic=topic,
        video_id=video_id,
        slug=slug,
        genre=genre,
        hook_min=hook_min,
        build=not blueprint_only,
        force_motion=force_motion,
        dossier=dossier,
        dry_run=dry_run,
    )
