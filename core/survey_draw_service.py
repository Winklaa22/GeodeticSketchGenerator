"""Turns parsed survey points + selection + a `GenerationConfig` into a
ready-to-run `Command` — the direct-to-DXF replacement for the old
`core/script_generator.py` (which built .scr script text instead)."""
from __future__ import annotations

from typing import Dict, List

from core.commands.base import Command
from core.commands.composite import CompositeCommand
from core.commands.layers import AddLayerCommand
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
        draw_command = builder(points, selected_numbers, config, layer_name)
        if config.layer_rgb is None:
            return draw_command
        # AddLayerCommand is a no-op (execute *and* undo) if layer_name
        # already exists - e.g. one imported from a DXF - so this only ever
        # colors a layer this call itself creates, as one undo step with
        # the rest of the drawing.
        return CompositeCommand([AddLayerCommand(layer_name, rgb=config.layer_rgb), draw_command])
