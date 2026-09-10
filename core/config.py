from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from core.draw_modes import DrawMode


@dataclass(frozen=True)
class PointsOptions:

    numbers_enabled: bool = False
    font_size: float = 0.6
    cabinet_font_size_enabled: bool = False
    cabinet_font_size: float = 0.6
    diameter: float = 0.05


@dataclass(frozen=True)
class HeightsOptions:

    font_size: float = 0.6
    frequency: int = 5


@dataclass(frozen=True)
class CableOptions:

    font_size: float = 0.6
    frequency: int = 5
    marks_text: str = "eN"


@dataclass(frozen=True)
class PipeOptions:

    width: float = 0.16


@dataclass(frozen=True)
class MeasurementsOptions:
    font_size: float = 0.6
    offset: float = 0.3


@dataclass(frozen=True)
class GenerationConfig:

    layer_name: str
    draw_mode: DrawMode
    points: PointsOptions = field(default_factory=PointsOptions)
    heights: HeightsOptions = field(default_factory=HeightsOptions)
    cable: CableOptions = field(default_factory=CableOptions)
    pipe: PipeOptions = field(default_factory=PipeOptions)
    measurements: MeasurementsOptions = field(default_factory=MeasurementsOptions)
    layer_rgb: Optional[Tuple[int, int, int]] = None
    quantum: float = 1.0
