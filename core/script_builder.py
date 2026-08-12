from __future__ import annotations

from typing import Dict, List

from core.config import GenerationConfig
from core.draw_modes import ScriptDrawer
from models.point import Point


class AutoCADScriptBuilder:

    @staticmethod
    def build_header(layer_name: str) -> List[str]:
        return ["-LAYER", f"MAKE {layer_name}", ""]

    def build(
        self, drawer: ScriptDrawer, points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig
    ) -> str:
        lines = self.build_header(config.layer_name)
        lines.extend(drawer.preamble())
        lines.extend(drawer.generate(points, selected_numbers, config))
        return "\n".join(lines)
