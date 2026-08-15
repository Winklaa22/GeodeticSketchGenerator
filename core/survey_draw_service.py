"""Turns parsed survey points + selection + a `GenerationConfig` into a
ready-to-run `Command` — the direct-to-DXF replacement for the old
`core/script_generator.py` (which built .scr script text instead)."""
from __future__ import annotations

from typing import Dict, List

from core.commands.base import Command
from core.commands.survey import get_survey_builder
from core.config import GenerationConfig
from core.validation import ensure_has_data, ensure_selection, resolve_layer_name
from models.point import Point


class SurveyDrawService:
    def build_command(
        self, points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig
    ) -> Command:
        ensure_has_data(points)
        layer_name = resolve_layer_name(config.layer_name)
        ensure_selection(selected_numbers)
        builder = get_survey_builder(config.draw_mode)
        return builder(points, selected_numbers, config, layer_name)
