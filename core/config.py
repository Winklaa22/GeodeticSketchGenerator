from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from core.draw_modes import DrawMode


@dataclass(frozen=True)
class PointsOptions:
    """Options for the 'Points' drawing mode."""

    numbers_enabled: bool = False
    font_size: float = 0.6
    diameter: float = 0.05


@dataclass(frozen=True)
class HeightsOptions:
    """Options for the 'Heights marks' drawing mode."""

    font_size: float = 0.6
    frequency: int = 5


@dataclass(frozen=True)
class CableOptions:
    """Options for the 'Cable marks' drawing mode."""

    font_size: float = 0.6
    frequency: int = 5
    marks_text: str = "eN"


@dataclass(frozen=True)
class PipeOptions:
    """Options for the 'Pipe' drawing mode — a protective casing pipe (RURA
    OSŁONOWA) drawn as two parallel lines straddling the cable route."""

    width: float = 0.16


@dataclass(frozen=True)
class GenerationConfig:
    """Everything needed to generate a script for one drawing mode."""

    layer_name: str
    draw_mode: DrawMode
    cabinet_mode: bool = False
    points: PointsOptions = field(default_factory=PointsOptions)
    heights: HeightsOptions = field(default_factory=HeightsOptions)
    cable: CableOptions = field(default_factory=CableOptions)
    pipe: PipeOptions = field(default_factory=PipeOptions)
    # The color to create `layer_name` with if it doesn't exist yet - never
    # applied to an already-existing layer (e.g. one imported from a DXF),
    # see core.commands.layers.AddLayerCommand.
    layer_rgb: Optional[Tuple[int, int, int]] = None
