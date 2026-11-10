"""Typed error hierarchy for FrameForge production pipeline.

Enforces Global Rule B: A missing or failed input raises a typed error naming
stage, artifact, and cause. The run is FAILED with a diagnostic report and stops.
"""

from __future__ import annotations

from pathlib import Path


class FrameForgeError(Exception):
    """Base exception for all FrameForge errors."""


class StageError(FrameForgeError):
    """Typed error naming stage, artifact, and cause."""

    def __init__(
        self,
        stage: str,
        artifact: str | Path | None,
        cause: str | Exception,
        details: str | None = None,
    ) -> None:
        self.stage = stage
        self.artifact = str(artifact) if artifact is not None else None
        self.cause = cause
        self.details = details
        msg = f"[{stage}] Failed on artifact {self.artifact!r}: {cause}"
        if details:
            msg += f" ({details})"
        super().__init__(msg)


class MissingInputError(StageError):
    """Raised when a mandatory input artifact or file is missing."""


class RenderingError(StageError):
    """Raised when a video rendering, encoding, or compositing operation fails."""


class AudioDesignError(StageError):
    """Raised when voiceover, Foley SFX, music bed, or mastering fails."""


class PolicyGateError(StageError):
    """Raised when a video, asset, or metadata violates publishing policy."""


class UniquenessGateError(StageError):
    """Raised when a video fails perceptual, audio, or SFX uniqueness checks."""
