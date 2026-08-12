from __future__ import annotations

from abc import ABC, abstractmethod
from enum import IntEnum
from typing import TYPE_CHECKING, Dict, List

from models.point import Point

if TYPE_CHECKING:
    from core.config import GenerationConfig


class DrawMode(IntEnum):

    POINTS = 1
    LINES = 2
    PLINES = 3
    POLY3D = 4
    HEIGHTS = 5
    CABLE_MARKS = 6


class ScriptDrawer(ABC):

    def preamble(self) -> List[str]:
        return []

    @abstractmethod
    def generate(
        self, points: Dict[int, Point], selected_numbers: List[int], config: "GenerationConfig"
    ) -> List[str]:
        raise NotImplementedError
