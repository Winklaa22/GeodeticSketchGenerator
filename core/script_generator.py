from __future__ import annotations

from typing import Dict, List, Optional

from core.config import GenerationConfig
from core.script_builder import AutoCADScriptBuilder
from core.strategy_registry import get_strategy
from core.validation import ensure_has_data, ensure_selection, resolve_layer_name
from models.point import Point


class ScriptGenerator:

    def __init__(self, builder: Optional[AutoCADScriptBuilder] = None) -> None:
        self._builder = builder or AutoCADScriptBuilder()

    def generate(self, points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig) -> str:

        ensure_has_data(points)
        resolve_layer_name(config.layer_name)
        ensure_selection(selected_numbers)
        drawer = get_strategy(config.draw_mode)
        return self._builder.build(drawer, points, selected_numbers, config)
