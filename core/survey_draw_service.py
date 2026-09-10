from __future__ import annotations

from typing import Dict, List

from core.commands.base import Command
from core.commands.composite import CompositeCommand
from core.commands.layers import AddLayerCommand, SetLayerColorCommand
from core.commands.survey import build_survey_commands
from core.config import GenerationConfig
from core.validation import ensure_has_data, ensure_selection, resolve_layer_name
from models.point import Point


class SurveyDrawService:
    def build_command(
        self, points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig
    ) -> Command:
        return self.build_commands(points, selected_numbers, [config])[0]

    def build_commands(
        self, points: Dict[int, Point], selected_numbers: List[int], configs: List[GenerationConfig]
    ) -> List[Command]:
        ensure_has_data(points)
        layer_names = [resolve_layer_name(config.layer_name) for config in configs]
        ensure_selection(selected_numbers)
        draw_commands = build_survey_commands(points, selected_numbers, configs, layer_names)

        results: List[Command] = []
        for config, layer_name, draw_command in zip(configs, layer_names, draw_commands):
            if config.layer_rgb is None:
                results.append(draw_command)
            else:
                results.append(
                    CompositeCommand(
                        [AddLayerCommand(layer_name), SetLayerColorCommand(layer_name, config.layer_rgb), draw_command]
                    )
                )
        return results
